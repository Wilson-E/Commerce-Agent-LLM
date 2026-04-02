"""Product database service with parallel multi-source product fetching.

All configured APIs are queried simultaneously.  A keyword-based intent
classifier selects which specialist (Tier-2) API to pair with the always-on
general (Tier-1) APIs for each query.  Results are deduplicated and ranked
before being returned.

Tier-1 (general — always active when key is present):
  - SerpAPI Google Shopping   (SERPAPI_KEY)
  - RapidAPI Product Search   (RAPIDAPI_KEY)

Tier-2 (specialist — activated by query intent):
  - Best Buy Products API     (BEST_BUY_API_KEY)   ← electronics queries
  - Walmart Affiliate API     (WALMART_API_KEY)    ← general retail (default)
  - Etsy Open API v3          (ETSY_API_KEY)       ← handmade/craft queries
  - Open Food Facts           (OPENFOODFACTS_ENABLED=true) ← food queries

Fallback: local sample_products.json (when no external API is configured)
"""
import asyncio
import json
import logging
import os
import time
from math import ceil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.schemas import Product
from app.services.result_aggregator import aggregate
from app.services.search_intent import classify_search_intent
from app.utils.config import settings

log = logging.getLogger(__name__)

_DEFAULT_DATA_FILE = str(
    Path(__file__).resolve().parent.parent.parent / "data" / "sample_products.json"
)


_SEARCH_CACHE_TTL = 1800   # 30 minutes
_PRODUCT_CACHE_TTL = 3600  # 1 hour


# ── Mapper functions ──────────────────────────────────────────────────────────

def _map_rapidapi_product(item: Dict[str, Any]) -> Product:
    """Convert a RapidAPI Real-Time Product Search result to our Product schema."""
    product_id = item.get("product_id", "")
    title = item.get("product_title", "Unknown Product")
    description = item.get("product_description") or title

    # Images
    photos = item.get("product_photos", [])
    image_url = photos[0] if photos else None

    # Rating & reviews
    try:
        rating = float(item.get("product_rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    review_count = int(item.get("product_num_reviews") or 0)

    # Price — prefer the first offer, fall back to typical_price_range
    offer = item.get("offer") or {}
    price_str = offer.get("price_without_symbol") or offer.get("price", "0")
    try:
        price = float(str(price_str).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        price = 0.0

    if price == 0.0:
        price_range = item.get("typical_price_range", [])
        for pr in price_range:
            try:
                price = float(str(pr).replace(",", "").replace("$", "").strip())
                break
            except (TypeError, ValueError):
                continue

    # Merchant
    merchant_name = offer.get("store_name", "Online Retailer")

    # Attributes (brand, color, size, etc.)
    raw_attrs: Dict[str, Any] = item.get("product_attributes") or {}
    attrs_lower = {k.lower(): v for k, v in raw_attrs.items()}
    brand = attrs_lower.get("brand", "")
    sizes = [v for k, v in attrs_lower.items() if "size" in k and v]
    colors = [v for k, v in attrs_lower.items() if "color" in k and v]

    # Category — not provided by the API; use first breadcrumb or default
    categories = item.get("product_breadcrumbs", [])
    category = categories[-1] if categories else "General"

    product_url = item.get("product_page_url") or offer.get("offer_page_url")

    return Product(
        id=product_id,
        sku=product_id,
        name=title,
        description=description,
        category=category,
        category_path=categories,
        price=price,
        stock=10,  # RapidAPI doesn't expose stock counts
        rating=round(min(rating, 5.0), 1),
        review_count=review_count,
        image_url=image_url,
        merchant_id=merchant_name,
        merchant_name=merchant_name,
        product_url=product_url,
        attributes={
            "brand": brand,
            "sizes": sizes,
            "colors": colors,
            "condition": "New",
            "source": "rapidapi",
        },
        key_features=[f"Sold by {merchant_name}"],
    )


def _map_serpapi_product(item: Dict[str, Any]) -> Product:
    """Convert a SerpAPI Google Shopping result to our Product schema."""
    product_id = str(item.get("product_id") or item.get("position", ""))
    title = item.get("title", "Unknown Product")
    description = item.get("snippet") or title

    # Price
    try:
        price = float(item.get("extracted_price") or 0)
    except (TypeError, ValueError):
        price = 0.0

    # Merchant / source
    merchant_name = item.get("source", "Google Shopping")

    # Rating & reviews
    try:
        rating = float(item.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        review_count = int(item.get("reviews") or 0)
    except (TypeError, ValueError):
        review_count = 0

    image_url = item.get("thumbnail")
    product_url = item.get("link")

    # Category — not in search results; may appear in product detail
    category = item.get("type") or "General"

    return Product(
        id=product_id,
        sku=product_id,
        name=title,
        description=description,
        category=category,
        category_path=[category],
        price=price,
        stock=10,  # SerpAPI does not expose stock counts
        rating=round(min(rating, 5.0), 1),
        review_count=review_count,
        image_url=image_url,
        merchant_id=merchant_name,
        merchant_name=merchant_name,
        product_url=product_url,
        attributes={
            "brand": "",
            "sizes": [],
            "colors": [],
            "condition": "New",
            "source": "serpapi",
        },
        key_features=[f"Sold by {merchant_name}"],
    )


def _map_bestbuy_product(item: Dict[str, Any]) -> Product:
    """Convert a Best Buy API product dict to our Product schema."""
    sku = str(item.get("sku", ""))
    name = item.get("name", "Unknown Product")
    description = item.get("shortDescription") or item.get("description") or name

    price = float(item.get("salePrice") or item.get("regularPrice") or 0)
    image_url = item.get("image")
    product_url = item.get("url")

    try:
        rating = float(item.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        review_count = int(item.get("reviewCount") or 0)
    except (TypeError, ValueError):
        review_count = 0

    # categoryPath is a list of dicts with "id" and "name"
    category_path_raw = item.get("categoryPath", [])
    if isinstance(category_path_raw, list):
        category_path = [c.get("name", "") for c in category_path_raw if isinstance(c, dict)]
    else:
        category_path = ["General"]
    category = category_path[-1] if category_path else "General"

    brand = item.get("manufacturer", "")
    stock = 10 if item.get("onlineAvailability", False) else 0

    return Product(
        id=sku,
        sku=sku,
        name=name,
        description=description,
        category=category,
        category_path=category_path,
        price=price,
        stock=stock,
        rating=round(min(rating, 5.0), 1),
        review_count=review_count,
        image_url=image_url,
        merchant_id="Best Buy",
        merchant_name="Best Buy",
        product_url=product_url,
        attributes={"brand": brand, "sizes": [], "colors": [], "condition": "New", "source": "bestbuy"},
        key_features=["Sold by Best Buy"],
    )


def _map_walmart_product(item: Dict[str, Any]) -> Product:
    """Convert a Walmart Affiliate API item dict to our Product schema."""
    item_id = str(item.get("itemId", ""))
    name = item.get("name", "Unknown Product")
    description = item.get("shortDescription") or name

    price = float(item.get("salePrice") or item.get("msrp") or 0)
    image_url = item.get("thumbnailImage") or item.get("largeImage")
    product_url = item.get("productUrl")

    try:
        rating = float(item.get("customerRating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        review_count = int(item.get("numReviews") or 0)
    except (TypeError, ValueError):
        review_count = 0

    category_path_str = item.get("categoryPath", "General")
    category_path = [c.strip() for c in category_path_str.split("/") if c.strip()]
    if not category_path:
        category_path = ["General"]
    category = category_path[-1]

    brand = item.get("brandName", "")
    stock_status = item.get("stock", "")
    stock = 10 if stock_status and "available" in stock_status.lower() else 0

    return Product(
        id=item_id,
        sku=item_id,
        name=name,
        description=description,
        category=category,
        category_path=category_path,
        price=price,
        stock=stock,
        rating=round(min(rating, 5.0), 1),
        review_count=review_count,
        image_url=image_url,
        merchant_id="Walmart",
        merchant_name="Walmart",
        product_url=product_url,
        attributes={"brand": brand, "sizes": [], "colors": [], "condition": "New", "source": "walmart"},
        key_features=["Sold by Walmart"],
    )


def _map_etsy_listing(item: Dict[str, Any]) -> Product:
    """Convert an Etsy API listing dict to our Product schema."""
    listing_id = str(item.get("listing_id", ""))
    name = item.get("title", "Unknown Product")
    description = item.get("description") or name
    if len(description) > 500:
        description = description[:497] + "..."

    # Price: amount / divisor
    price_data = item.get("price", {})
    try:
        price = float(price_data.get("amount", 0)) / float(price_data.get("divisor", 100))
    except (TypeError, ValueError, ZeroDivisionError):
        price = 0.0

    # Image
    images = item.get("images", [])
    image_url = images[0].get("url_570xN") if images else None

    product_url = item.get("url")

    # Shop / merchant
    shop = item.get("shop") or {}
    merchant_name = shop.get("shop_name", "Etsy Seller")

    try:
        rating = float(item.get("avg_score") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        review_count = int(item.get("num_favorers") or 0)
    except (TypeError, ValueError):
        review_count = 0

    # Taxonomy path may be a list of strings or dicts
    taxonomy_path = item.get("taxonomy_path", [])
    if isinstance(taxonomy_path, list) and taxonomy_path:
        category_path = [
            t if isinstance(t, str) else t.get("name", "") for t in taxonomy_path
        ]
    else:
        category_path = ["Handmade"]
    category = category_path[-1] if category_path else "Handmade"

    tags = item.get("tags", [])

    return Product(
        id=listing_id,
        sku=listing_id,
        name=name,
        description=description,
        category=category,
        category_path=category_path,
        price=price,
        stock=int(item.get("quantity", 1)),
        rating=round(min(rating, 5.0), 1),
        review_count=review_count,
        image_url=image_url,
        merchant_id=merchant_name,
        merchant_name=merchant_name,
        product_url=product_url,
        attributes={
            "brand": merchant_name,
            "sizes": [],
            "colors": [],
            "condition": "Handmade",
            "source": "etsy",
        },
        key_features=tags[:3] if tags else [f"Sold by {merchant_name}"],
    )


def _map_openfoodfacts_product(item: Dict[str, Any]) -> Product:
    """Convert an Open Food Facts product dict to our Product schema."""
    barcode = item.get("code") or item.get("_id", "")
    name = item.get("product_name") or item.get("product_name_en") or "Unknown Product"

    brands = item.get("brands", "")
    categories_str = item.get("categories", "")
    category_list = [c.strip() for c in categories_str.split(",") if c.strip()]
    if not category_list:
        category_list = ["Food"]
    category = category_list[-1]

    quantity = item.get("quantity", "")
    description = f"{name} {quantity}".strip() if quantity else name

    image_url = item.get("image_url") or item.get("image_front_url")
    product_url = f"https://world.openfoodfacts.org/product/{barcode}"

    # Convert nutriscore (lower is better, roughly -15 to 40) to a 1–5 star rating
    try:
        ns = float(item.get("nutriscore_score") or 0)
        rating = round(max(1.0, min(5.0, 5.0 - (ns + 15) / 55 * 4)), 1)
    except (TypeError, ValueError):
        rating = 3.0

    return Product(
        id=barcode,
        sku=barcode,
        name=name,
        description=description,
        category=category,
        category_path=category_list[:3],
        price=0.0,  # Open Food Facts does not carry pricing data
        stock=10,
        rating=rating,
        review_count=0,
        image_url=image_url,
        merchant_id="Open Food Facts",
        merchant_name="Open Food Facts",
        product_url=product_url,
        attributes={"brand": brands, "sizes": [], "colors": [], "condition": "Food", "source": "openfoodfacts"},
        key_features=[f"Brand: {brands}"] if brands else [],
    )


# ── Source → mapper lookup (used by _fetch_from_source) ──────────────────────

_MAPPERS = {
    "serpapi": _map_serpapi_product,
    "rapidapi": _map_rapidapi_product,
    "bestbuy": _map_bestbuy_product,
    "walmart": _map_walmart_product,
    "etsy": _map_etsy_listing,
    "openfoodfacts": _map_openfoodfacts_product,
}


class ProductDBService:
    """Fetches products from multiple APIs in parallel with in-memory caching.

    Tier-1 APIs (SerpAPI, RapidAPI) are always queried when their keys are
    present.  A single Tier-2 specialist API is selected per query by
    classify_search_intent().  Results from all active sources are merged,
    deduplicated, and ranked by result_aggregator.aggregate().
    """

    def __init__(self, data_file: str = _DEFAULT_DATA_FILE):
        # ── Enable flags — each is independent (no mutual exclusion) ──────────
        serp_key_names = {"serpapi_key", "serp_api_key", "serpapi_api_key"}
        serp_env_key_present = any(
            k.lower() in serp_key_names and bool(v)
            for k, v in os.environ.items()
        )
        self._use_serpapi = bool(getattr(settings, "SERPAPI_KEY", "")) or serp_env_key_present
        self._use_rapidapi = bool(getattr(settings, "RAPIDAPI_KEY", ""))
        self._use_bestbuy = bool(getattr(settings, "BEST_BUY_API_KEY", ""))
        self._use_walmart = bool(getattr(settings, "WALMART_API_KEY", ""))
        self._use_etsy = bool(getattr(settings, "ETSY_API_KEY", ""))
        self._use_openfoodfacts = bool(getattr(settings, "OPENFOODFACTS_ENABLED", False))

        # Deprecation notice — ALLOW_RAPIDAPI_FALLBACK no longer gates RapidAPI
        if bool(getattr(settings, "ALLOW_RAPIDAPI_FALLBACK", False)):
            log.warning(
                "ALLOW_RAPIDAPI_FALLBACK is deprecated and no longer used. "
                "RapidAPI is now enabled whenever RAPIDAPI_KEY is present."
            )

        active = [
            name for name, flag in {
                "serpapi": self._use_serpapi,
                "rapidapi": self._use_rapidapi,
                "bestbuy": self._use_bestbuy,
                "walmart": self._use_walmart,
                "etsy": self._use_etsy,
                "openfoodfacts": self._use_openfoodfacts,
            }.items() if flag
        ]
        log.info("ProductDB active sources: %s", active if active else ["sample_data"])

        # ── Per-product cache: id/sku → (Product, expires_at) ─────────────────
        self._product_cache: Dict[str, tuple] = {}

        # ── Per-source search cache: source → cache_key → (List[Product], exp) ─
        self._source_search_cache: Dict[str, Dict[str, tuple]] = {
            "serpapi": {},
            "rapidapi": {},
            "bestbuy": {},
            "walmart": {},
            "etsy": {},
            "openfoodfacts": {},
        }

        # ── Merged search cache: cache_key → (List[Dict], expires_at) ─────────
        self._merged_search_cache: Dict[str, tuple] = {}

        # ── Instantiate clients ────────────────────────────────────────────────
        if self._use_serpapi:
            from app.services.serpapi_client import SerpAPIClient
            self._serpapi = SerpAPIClient()
        else:
            self._serpapi = None

        if self._use_rapidapi:
            from app.services.rapidapi_client import RapidAPIProductClient
            self._rapidapi = RapidAPIProductClient()
        else:
            self._rapidapi = None

        if self._use_bestbuy:
            from app.services.bestbuy_client import BestBuyClient
            self._bestbuy = BestBuyClient()
        else:
            self._bestbuy = None

        if self._use_walmart:
            from app.services.walmart_client import WalmartClient
            self._walmart = WalmartClient()
        else:
            self._walmart = None

        if self._use_etsy:
            from app.services.etsy_client import EtsyClient
            self._etsy = EtsyClient()
        else:
            self._etsy = None

        if self._use_openfoodfacts:
            from app.services.openfoodfacts_client import OpenFoodFactsClient
            self._openfoodfacts = OpenFoodFactsClient()
        else:
            self._openfoodfacts = None

        if not self._any_api_active():
            log.warning(
                "No external product API configured — "
                "falling back to sample product data"
            )
            self._load_sample_products(data_file)

    def _any_api_active(self) -> bool:
        return (
            self._use_serpapi
            or self._use_rapidapi
            or self._use_bestbuy
            or self._use_walmart
            or self._use_etsy
            or self._use_openfoodfacts
        )

    # ── Fallback: local sample data ──────────────────────────────────────────

    def _load_sample_products(self, data_file: str):
        try:
            with open(data_file) as f:
                for product_data in json.load(f):
                    product = Product(**product_data)
                    self._cache_product(product, ttl=86400)
        except FileNotFoundError:
            log.warning("Sample product file %s not found", data_file)

    # ── Cache helpers ────────────────────────────────────────────────────────

    def _cache_product(self, product: Product, ttl: int = _PRODUCT_CACHE_TTL):
        expires = time.time() + ttl
        self._product_cache[product.id] = (product, expires)
        self._product_cache[product.sku] = (product, expires)

    def _get_cached_product(self, key: str) -> Optional[Product]:
        entry = self._product_cache.get(key)
        if entry and time.time() < entry[1]:
            return entry[0]
        return None

    # ── Per-source parallel fetch ────────────────────────────────────────────

    async def _fetch_from_source(
        self,
        source_name: str,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[Product]:
        """Fetch and map products from a single source with per-source caching.

        Returns an empty list on any error so a failing source never blocks
        the rest of the parallel gather.
        """
        cache_key = f"{query}|{filters}"
        source_cache = self._source_search_cache.get(source_name, {})
        entry = source_cache.get(cache_key)
        if entry and time.time() < entry[1]:
            return entry[0]

        mapper = _MAPPERS[source_name]
        client_map = {
            "serpapi": self._serpapi,
            "rapidapi": self._rapidapi,
            "bestbuy": self._bestbuy,
            "walmart": self._walmart,
            "etsy": self._etsy,
            "openfoodfacts": self._openfoodfacts,
        }
        client = client_map[source_name]

        try:
            raw_items = await client.search(query, limit=limit, filters=filters)
            products = [mapper(item) for item in raw_items]
            for p in products:
                self._cache_product(p)
            self._source_search_cache[source_name][cache_key] = (
                products,
                time.time() + _SEARCH_CACHE_TTL,
            )
            return products
        except Exception as exc:
            log.warning("[%s] fetch failed for query '%s': %s", source_name, query, exc)
            return []

    # ── Public interface ─────────────────────────────────────────────────────

    async def get_product(self, product_id: str) -> Optional[Product]:
        cached = self._get_cached_product(product_id)
        if cached:
            return cached

        if self._use_serpapi:
            item = await self._serpapi.get_product(product_id)
            if item:
                product = _map_serpapi_product(item)
                self._cache_product(product)
                return product

        if self._use_rapidapi:
            item = await self._rapidapi.get_product(product_id)
            if item:
                product = _map_rapidapi_product(item)
                self._cache_product(product)
                return product

        if self._use_bestbuy:
            item = await self._bestbuy.get_product(product_id)
            if item:
                product = _map_bestbuy_product(item)
                self._cache_product(product)
                return product

        if self._use_walmart:
            item = await self._walmart.get_product(product_id)
            if item:
                product = _map_walmart_product(item)
                self._cache_product(product)
                return product

        if self._use_etsy:
            item = await self._etsy.get_product(product_id)
            if item:
                product = _map_etsy_listing(item)
                self._cache_product(product)
                return product

        if self._use_openfoodfacts:
            item = await self._openfoodfacts.get_product(product_id)
            if item:
                product = _map_openfoodfacts_product(item)
                self._cache_product(product)
                return product

        return None

    async def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        # ── 1. Merged cache check ─────────────────────────────────────────────
        cache_key = f"{query}|{filters}"
        entry = self._merged_search_cache.get(cache_key)
        if entry and time.time() < entry[1]:
            return entry[0]

        # ── 2. Sample-data fast path ──────────────────────────────────────────
        if not self._any_api_active():
            return self._keyword_search_sample(query, filters)

        # ── 3. Build active source list ───────────────────────────────────────
        intent = classify_search_intent(query)
        tier2_source: str = intent["tier2"]

        # Tier-1: general APIs, always included when configured
        active_sources: List[str] = []
        if self._use_serpapi:
            active_sources.append("serpapi")
        if self._use_rapidapi:
            active_sources.append("rapidapi")

        # Tier-2: specialist API selected by intent, added if configured
        tier2_flags = {
            "bestbuy": self._use_bestbuy,
            "walmart": self._use_walmart,
            "etsy": self._use_etsy,
            "openfoodfacts": self._use_openfoodfacts,
        }
        if tier2_flags.get(tier2_source) and tier2_source not in active_sources:
            active_sources.append(tier2_source)

        # If no Tier-1 keys are set, fall back to whichever sources are active
        if not active_sources:
            for src, flag in tier2_flags.items():
                if flag:
                    active_sources.append(src)

        if not active_sources:
            return self._keyword_search_sample(query, filters)

        # ── 4. Per-source fetch limit ─────────────────────────────────────────
        total_limit = getattr(settings, "PARALLEL_SEARCH_LIMIT", 10)
        per_source_limit = max(10, ceil(total_limit / max(len(active_sources), 1)))

        # ── 5. Parallel fetch ─────────────────────────────────────────────────
        coroutines = [
            self._fetch_from_source(src, query, per_source_limit, filters)
            for src in active_sources
        ]
        raw_results = await asyncio.gather(*coroutines, return_exceptions=True)

        # ── 6. Collect successful results ─────────────────────────────────────
        raw_lists: Dict[str, List[Product]] = {}
        for src, result in zip(active_sources, raw_results):
            if isinstance(result, BaseException):
                log.warning("[%s] gather exception for query '%s': %s", src, query, result)
            else:
                raw_lists[src] = result

        # ── 7. Aggregate, deduplicate, rank ───────────────────────────────────
        if raw_lists:
            merged_products = aggregate(raw_lists)
            results = [p.dict() for p in merged_products]
        else:
            # All sources failed — fall back to sample data
            log.warning("All API sources failed for query '%s'; falling back to sample data", query)
            return self._keyword_search_sample(query, filters)

        # ── 8. Store in merged cache and return ───────────────────────────────
        self._merged_search_cache[cache_key] = (results, time.time() + _SEARCH_CACHE_TTL)
        return results

    async def get_by_category(self, category: str, limit: int = 10) -> List[Product]:
        if not self._any_api_active():
            return self._sample_by_category(category, limit)

        cache_key = f"cat:{category}:{limit}"
        entry = self._merged_search_cache.get(cache_key)
        if entry and time.time() < entry[1]:
            return [Product(**d) for d in entry[0]]

        # Activate all configured sources for category browsing (no intent routing)
        active_sources: List[str] = [
            src for src, flag in {
                "serpapi": self._use_serpapi,
                "rapidapi": self._use_rapidapi,
                "bestbuy": self._use_bestbuy,
                "walmart": self._use_walmart,
                "etsy": self._use_etsy,
                "openfoodfacts": self._use_openfoodfacts,
            }.items() if flag
        ]

        per_source_limit = max(limit, ceil(limit / max(len(active_sources), 1)))

        coroutines = [
            self._fetch_from_source(src, category, per_source_limit, None)
            for src in active_sources
        ]
        raw_results = await asyncio.gather(*coroutines, return_exceptions=True)

        raw_lists: Dict[str, List[Product]] = {}
        for src, result in zip(active_sources, raw_results):
            if isinstance(result, BaseException):
                log.warning("[%s] gather exception for category '%s': %s", src, category, result)
            else:
                raw_lists[src] = result

        if not raw_lists:
            return self._sample_by_category(category, limit)

        products = aggregate(raw_lists)

        self._merged_search_cache[cache_key] = (
            [p.dict() for p in products],
            time.time() + _SEARCH_CACHE_TTL,
        )
        return products

    def get_all_products(self) -> List[Product]:
        """Return all currently cached products (used to build the vector index)."""
        seen: set = set()
        products: List[Product] = []
        for key, (product, expires) in self._product_cache.items():
            if product.id == key and product.id not in seen and time.time() < expires:
                seen.add(product.id)
                products.append(product)
        return products

    # ── Sample-data helpers (fallback only) ──────────────────────────────────

    def _keyword_search_sample(
        self, query: str, filters: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        tokens = query.lower().split()
        results = []
        seen: set = set()
        for key, (product, expires) in self._product_cache.items():
            if product.id != key or product.id in seen:
                continue
            seen.add(product.id)
            text = f"{product.name} {product.description} {product.category}".lower()
            if tokens and not all(t in text for t in tokens):
                continue
            if filters:
                if "max_price" in filters and product.price > filters["max_price"]:
                    continue
                if "min_price" in filters and product.price < filters["min_price"]:
                    continue
                if "category" in filters and filters["category"].lower() not in product.category.lower():
                    continue
                if "brand" in filters:
                    brand = product.attributes.get("brand", "").lower()
                    if filters["brand"].lower() not in brand:
                        continue
            results.append(product.dict())
        return results

    def _sample_by_category(self, category: str, limit: int) -> List[Product]:
        cat_lower = category.lower()
        results = []
        seen: set = set()
        for key, (product, _) in self._product_cache.items():
            if product.id != key or product.id in seen:
                continue
            seen.add(product.id)
            if cat_lower in product.category.lower():
                results.append(product)
                if len(results) >= limit:
                    break
        return results
