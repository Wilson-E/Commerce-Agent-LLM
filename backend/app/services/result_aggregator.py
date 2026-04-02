"""Stateless product result deduplication and unified ranking.

Operates entirely on List[Product] — no I/O, no external calls.

Optional faster deduplication: install rapidfuzz and swap _jaccard for
  rapidfuzz.fuzz.token_set_ratio(a_str, b_str) / 100
"""
import re
from typing import Dict, List

from app.models.schemas import Product

# Jaccard overlap threshold above which two products are considered the same item
DEDUP_THRESHOLD: float = 0.70

_STOPWORDS: frozenset = frozenset({"a", "an", "the", "of", "with", "for", "and", "in", "on", "at"})

# General APIs produce results already sorted by relevance — reward them slightly
_GENERAL_SOURCES: frozenset = frozenset({"serpapi", "rapidapi"})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_title(name: str) -> frozenset:
    """Lowercase, strip punctuation, remove stopwords, return token frozenset."""
    tokens = re.sub(r"[^\w\s]", " ", name.lower()).split()
    return frozenset(t for t in tokens if t not in _STOPWORDS and len(t) > 1)


def _jaccard(a: frozenset, b: frozenset) -> float:
    """Jaccard similarity between two token sets."""
    if not a and not b:
        return 1.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


# ── Core functions ────────────────────────────────────────────────────────────

def deduplicate(products: List[Product]) -> List[Product]:
    """Collapse near-duplicate products (same item from multiple sources).

    When two products have title Jaccard >= DEDUP_THRESHOLD:
    - Keep the one with the lower price (if both > 0), or higher review_count
      as a tiebreaker.
    - Append the loser's merchant_name to the winner's attributes["also_at"]
      list so the UI can display "also available at X".
    """
    accepted: List[Product] = []
    accepted_tokens: List[frozenset] = []

    for product in products:
        tokens = _normalize_title(product.name)
        matched_idx: int = -1

        for i, existing_tokens in enumerate(accepted_tokens):
            if _jaccard(tokens, existing_tokens) >= DEDUP_THRESHOLD:
                matched_idx = i
                break

        if matched_idx == -1:
            # No duplicate found — add a fresh also_at list and accept
            product.attributes.setdefault("also_at", [])
            accepted.append(product)
            accepted_tokens.append(tokens)
        else:
            existing = accepted[matched_idx]
            incoming_price = product.price
            existing_price = existing.price

            # Decide which variant to keep
            keep_incoming = False
            if incoming_price > 0 and existing_price > 0:
                keep_incoming = incoming_price < existing_price
            elif incoming_price > 0 and existing_price == 0:
                keep_incoming = True
            elif incoming_price == existing_price:
                keep_incoming = product.review_count > existing.review_count

            if keep_incoming:
                # Incoming wins — carry over also_at from existing
                also_at: List[str] = list(existing.attributes.get("also_at", []))
                also_at.append(existing.merchant_name)
                product.attributes["also_at"] = also_at
                accepted[matched_idx] = product
                accepted_tokens[matched_idx] = tokens
            else:
                # Existing wins — record incoming as an alternate source
                existing.attributes.setdefault("also_at", [])
                if product.merchant_name not in existing.attributes["also_at"]:
                    existing.attributes["also_at"].append(product.merchant_name)

    return accepted


def score_product(product: Product) -> float:
    """Compute a unified 0–1 relevance + quality score for ranking.

    Component weights:
      30% — source relevance bonus (general APIs score higher)
      35% — normalized star rating (rating / 5)
      15% — review depth (review_count / 1000, capped at 1.0)
      20% — price availability bonus (product has a known price > 0)
    """
    source = product.attributes.get("source", "")
    source_bonus = 1.0 if source in _GENERAL_SOURCES else 0.8

    rating_component = (product.rating / 5.0) * 0.35
    review_component = min(product.review_count / 1000.0, 1.0) * 0.15
    price_component = 0.20 if product.price > 0 else 0.0
    source_component = source_bonus * 0.30

    return rating_component + review_component + price_component + source_component


def rank_results(products: List[Product]) -> List[Product]:
    """Sort products by score descending."""
    return sorted(products, key=score_product, reverse=True)


def aggregate(raw_lists: Dict[str, List[Product]]) -> List[Product]:
    """Flatten multiple per-source product lists, deduplicate, then rank.

    Args:
        raw_lists: mapping of source_name → List[Product]

    Returns:
        Deduplicated and ranked List[Product]
    """
    all_products: List[Product] = []
    for products in raw_lists.values():
        all_products.extend(products)

    deduplicated = deduplicate(all_products)
    return rank_results(deduplicated)
