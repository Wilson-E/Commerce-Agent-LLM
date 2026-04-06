"""Product database service with parallel multi-source product fetching.

APIs are queried based on category routing.  A keyword-based intent
classifier (or an explicit category hint from the frontend) selects
which APIs to call for each query, conserving free-tier quotas.

Category routing:
  - Tech:    SerpAPI + ScraperAPI + Rainforest (Amazon)
  - Fashion: SerpAPI + ASOS (via RapidAPI)
  - Home:    SerpAPI + Home Depot (via RapidAPI)

Food queries are sub-routed to Open Food Facts within the Home category.

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

    photos = item.get("product_photos", [])
    image_url = photos[0] if photos else None

    try:
        rating = float(item.get("product_rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    review_count = int(item.get("product_num_reviews") or 0)

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

    merchant_name = offer.get("store_name", "Online Retailer")

    raw_attrs: Dict[str, Any] = item.get("product_attributes") or {}
    attrs_lower = {k.lower(): v for k, v in raw_attrs.items()}
    brand = attrs_lower.get("brand", "")
    sizes = [v for k, v in attrs_lower.items() if "size" in k and v]
    colors = [v for k, v in attrs_lower.items() if "color" in k and v]

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
        stock=10,
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

    try:
        price = float(item.get("extracted_price") or 0)
    except (TypeError, ValueError):
        price = 0.0

    merchant_name = item.get("source", "Google Shopping")

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
    category = item.get("type") or "General"

    return Product(
        id=product_id,
        sku=product_id,
        name=title,
        description=description,
        category=category,
        category_path=[category],
        price=price,
        stock=10,
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


def _map_rainforest_product(item: Dict[str, Any]) -> Product:
    """Convert a Rainforest API (Amazon) search result to our Product schema."""
    asin = item.get("asin", "")
    title = item.get("title", "Unknown Product")
    description = item.get("description") or title

    # Price
    price_data = item.get("price") or {}
    try:
        price = float(price_data.get("value") or 0)
    except (TypeError, ValueError):
        price = 0.0

    # Rating & reviews
    try:
        rating = float(item.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        review_count = int(item.get("ratings_total") or 0)
    except (TypeError, ValueError):
        review_count = 0

    # Image
    image = item.get("image") or ""
    image_url = image if image else None

    # URL
    link = item.get("link") or ""
    product_url = link if link else f"https://www.amazon.com/dp/{asin}"

    # Category / bestseller rank
    categories_raw = item.get("categories", [])
    if isinstance(categories_raw, list) and categories_raw:
        category_path = [c.get("name", "") for c in categories_raw if isinstance(c, dict)]
    else:
        category_path = ["General"]
    category = category_path[-1] if category_path else "General"

    brand = item.get("brand") or ""

    return Product(
        id=asin,
        sku=asin,
        name=title,
        description=description,
        category=category,
        category_path=category_path,
        price=price,
        stock=10,
        rating=round(min(rating, 5.0), 1),
        review_count=review_count,
        image_url=image_url,
        merchant_id="Amazon",
        merchant_name="Amazon",
        product_url=product_url,
        attributes={
            "brand": brand,
            "sizes": [],
            "colors": [],
            "condition": "New",
            "source": "rainforest",
        },
        key_features=["Sold by Amazon"],
    )


def _map_scraperapi_product(item: Dict[str, Any]) -> Product:
    """Convert a ScraperAPI Amazon structured search result to our Product schema."""
    asin = item.get("asin", "")
    name = item.get("name", "Unknown Product")
    description = name

    # Price — ScraperAPI returns price as a string like "$29.99"
    price_raw = item.get("price", "0")
    try:
        price = float(str(price_raw).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        price = 0.0

    try:
        rating = float(item.get("stars") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        review_count = int(item.get("total_reviews") or 0)
    except (TypeError, ValueError):
        review_count = 0

    image_url = item.get("image") or None
    product_url = item.get("url") or (f"https://www.amazon.com/dp/{asin}" if asin else None)

    return Product(
        id=asin,
        sku=asin,
        name=name,
        description=description,
        category="General",
        category_path=["General"],
        price=price,
        stock=10,
        rating=round(min(rating, 5.0), 1),
        review_count=review_count,
        image_url=image_url,
        merchant_id="Amazon",
        merchant_name="Amazon",
        product_url=product_url,
        attributes={
            "brand": "",
            "sizes": [],
            "colors": [],
            "condition": "New",
            "source": "scraperapi",
        },
        key_features=["Sold by Amazon"],
    )


def _map_asos_product(item: Dict[str, Any]) -> Product:
    """Convert an ASOS product dict to our Product schema."""
    product_id = str(item.get("id", ""))
    name = item.get("name", "Unknown Product")

    price_data = item.get("price", {})
    current = price_data.get("current", {})
    try:
        price = float(current.get("value") or 0)
    except (TypeError, ValueError):
        price = 0.0

    image_url = None
    if item.get("imageUrl"):
        image_url = "https://" + item["imageUrl"].lstrip("/")

    brand = item.get("brandName", "")
    colour = item.get("colour", "")
    product_url = f"https://www.asos.com/us/prd/{product_id}" if product_id else None

    return Product(
        id=product_id,
        sku=product_id,
        name=name,
        description=name,
        category="Fashion",
        category_path=["Fashion"],
        price=price,
        stock=10,
        rating=0.0,
        review_count=0,
        image_url=image_url,
        merchant_id="ASOS",
        merchant_name="ASOS",
        product_url=product_url,
        attributes={
            "brand": brand,
            "sizes": [],
            "colors": [colour] if colour else [],
            "condition": "New",
            "source": "asos",
        },
        key_features=[f"Brand: {brand}"] if brand else ["Sold by ASOS"],
    )


def _map_homedepot_product(item: Dict[str, Any]) -> Product:
    """Convert a Home Depot product dict to our Product schema."""
    item_id = str(item.get("itemId") or item.get("id", ""))
    name = item.get("label") or item.get("title") or "Unknown Product"
    description = item.get("description") or name

    try:
        price = float(item.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0

    try:
        rating = float(item.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        review_count = int(item.get("reviewCount") or item.get("totalReviews") or 0)
    except (TypeError, ValueError):
        review_count = 0

    image_url = item.get("imageUrl") or item.get("image") or None
    product_url = item.get("url") or item.get("productUrl")
    if product_url and not product_url.startswith("http"):
        product_url = f"https://www.homedepot.com{product_url}"

    brand = item.get("brand") or item.get("brandName") or ""

    return Product(
        id=item_id,
        sku=item_id,
        name=name,
        description=description,
        category="Home",
        category_path=["Home"],
        price=price,
        stock=10,
        rating=round(min(rating, 5.0), 1),
        review_count=review_count,
        image_url=image_url,
        merchant_id="Home Depot",
        merchant_name="Home Depot",
        product_url=product_url,
        attributes={
            "brand": brand,
            "sizes": [],
            "colors": [],
            "condition": "New",
            "source": "homedepot",
        },
        key_features=[f"Brand: {brand}"] if brand else ["Sold by Home Depot"],
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
        price=0.0,
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


# ── Source → mapper lookup ────────────────────────────────────────────────────

_MAPPERS = {
    "serpapi": _map_serpapi_product,
    "rapidapi": _map_rapidapi_product,
    "scraperapi": _map_scraperapi_product,
    "rainforest": _map_rainforest_product,
    "asos": _map_asos_product,
    "homedepot": _map_homedepot_product,
    "openfoodfacts": _map_openfoodfacts_product,
}


class ProductDBService:
    """Fetches products from category-specific APIs in parallel with caching.

    The intent classifier determines which category a query belongs to
    (Tech, Fashion, Home) and only the APIs mapped to that category are
    called, conserving free-tier API quotas.
    """

    def __init__(self, data_file: str = _DEFAULT_DATA_FILE):
        serp_key_names = {"serpapi_key", "serp_api_key", "serpapi_api_key"}
        serp_env_key_present = any(
            k.lower() in serp_key_names and bool(v)
            for k, v in os.environ.items()
        )
        self._use_serpapi = bool(getattr(settings, "SERPAPI_KEY", "")) or serp_env_key_present
        self._use_rapidapi = bool(getattr(settings, "RAPIDAPI_KEY", ""))
        self._use_scraperapi = bool(getattr(settings, "SCRAPERAPI_KEY", ""))
        self._use_rainforest = bool(getattr(settings, "RAINFOREST_API_KEY", ""))
        self._use_openfoodfacts = bool(getattr(settings, "OPENFOODFACTS_ENABLED", False))
        self._use_asos = bool(getattr(settings, "ASOS_ENABLED", False)) and bool(getattr(settings, "RAPIDAPI_KEY", ""))
        self._use_homedepot = bool(getattr(settings, "HOMEDEPOT_ENABLED", False)) and bool(getattr(settings, "RAPIDAPI_KEY", ""))

        if bool(getattr(settings, "ALLOW_RAPIDAPI_FALLBACK", False)):
            log.warning(
                "ALLOW_RAPIDAPI_FALLBACK is deprecated and no longer used. "
                "RapidAPI is now enabled whenever RAPIDAPI_KEY is present."
            )

        active = [
            name for name, flag in {
                "serpapi": self._use_serpapi,
                "rapidapi": self._use_rapidapi,
                "scraperapi": self._use_scraperapi,
                "rainforest": self._use_rainforest,
                "asos": self._use_asos,
                "homedepot": self._use_homedepot,
                "openfoodfacts": self._use_openfoodfacts,
            }.items() if flag
        ]
        log.info("ProductDB active sources: %s", active if active else ["sample_data"])

        # Source availability lookup — used to filter routing table at search time
        self._source_available: Dict[str, bool] = {
            "serpapi": self._use_serpapi,
            "rapidapi": self._use_rapidapi,
            "scraperapi": self._use_scraperapi,
            "rainforest": self._use_rainforest,
            "asos": self._use_asos,
            "homedepot": self._use_homedepot,
            "openfoodfacts": self._use_openfoodfacts,
        }

        self._product_cache: Dict[str, tuple] = {}
        self._source_search_cache: Dict[str, Dict[str, tuple]] = {
            "serpapi": {},
            "rapidapi": {},
            "scraperapi": {},
            "rainforest": {},
            "asos": {},
            "homedepot": {},
            "openfoodfacts": {},
        }
        self._merged_search_cache: Dict[str, tuple] = {}

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

        if self._use_scraperapi:
            from app.services.scraperapi_client import ScraperAPIClient
            self._scraperapi = ScraperAPIClient()
        else:
            self._scraperapi = None

        if self._use_rainforest:
            from app.services.rainforest_client import RainforestClient
            self._rainforest = RainforestClient()
        else:
            self._rainforest = None

        if self._use_asos:
            from app.services.asos_client import AsosClient
            self._asos = AsosClient()
        else:
            self._asos = None

        if self._use_homedepot:
            from app.services.homedepot_client import HomeDepotClient
            self._homedepot = HomeDepotClient()
        else:
            self._homedepot = None

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
        return any(self._source_available.values())

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
        """Fetch and map products from a single source with per-source caching."""
        cache_key = f"{query}|{filters}"
        source_cache = self._source_search_cache.get(source_name, {})
        entry = source_cache.get(cache_key)
        if entry and time.time() < entry[1]:
            return entry[0]

        mapper = _MAPPERS[source_name]
        client_map = {
            "serpapi": self._serpapi,
            "rapidapi": self._rapidapi,
            "scraperapi": self._scraperapi,
            "rainforest": self._rainforest,
            "asos": self._asos,
            "homedepot": self._homedepot,
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

        if self._use_scraperapi:
            item = await self._scraperapi.get_product(product_id)
            if item:
                product = _map_scraperapi_product(item)
                self._cache_product(product)
                return product

        if self._use_rainforest:
            item = await self._rainforest.get_product(product_id)
            if item:
                product = _map_rainforest_product(item)
                self._cache_product(product)
                return product

        if self._use_asos:
            item = await self._asos.get_product(product_id)
            if item:
                product = _map_asos_product(item)
                self._cache_product(product)
                return product

        if self._use_homedepot:
            item = await self._homedepot.get_product(product_id)
            if item:
                product = _map_homedepot_product(item)
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
        category_hint: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        cache_key = f"{query}|{filters}|{category_hint}"
        entry = self._merged_search_cache.get(cache_key)
        if entry and time.time() < entry[1]:
            return entry[0]

        if not self._any_api_active():
            return self._keyword_search_sample(query, filters)

        intent = classify_search_intent(query, category_hint=category_hint)
        routed_sources: List[str] = intent["sources"]
        log.info(
            "Category routing: category=%s, routed_sources=%s",
            intent["category"], routed_sources,
        )

        # Filter to only sources that are actually configured
        active_sources: List[str] = [
            src for src in routed_sources
            if self._source_available.get(src, False)
        ]

        if not active_sources:
            return self._keyword_search_sample(query, filters)

        total_limit = getattr(settings, "PARALLEL_SEARCH_LIMIT", 10)
        per_source_limit = max(10, ceil(total_limit / max(len(active_sources), 1)))

        coroutines = [
            self._fetch_from_source(src, query, per_source_limit, filters)
            for src in active_sources
        ]
        raw_results = await asyncio.gather(*coroutines, return_exceptions=True)

        raw_lists: Dict[str, List[Product]] = {}
        for src, result in zip(active_sources, raw_results):
            if isinstance(result, BaseException):
                log.warning("[%s] gather exception for query '%s': %s", src, query, result)
            else:
                raw_lists[src] = result

        if raw_lists:
            merged_products = aggregate(raw_lists)
            results = [p.dict() for p in merged_products]
        else:
            log.warning("All API sources failed for query '%s'; falling back to sample data", query)
            return self._keyword_search_sample(query, filters)

        self._merged_search_cache[cache_key] = (results, time.time() + _SEARCH_CACHE_TTL)
        return results

    async def get_by_category(self, category: str, limit: int = 10) -> List[Product]:
        if not self._any_api_active():
            return self._sample_by_category(category, limit)

        cache_key = f"cat:{category}:{limit}"
        entry = self._merged_search_cache.get(cache_key)
        if entry and time.time() < entry[1]:
            return [Product(**d) for d in entry[0]]

        # Use category name as a hint for routing
        intent = classify_search_intent(category, category_hint=category)
        routed_sources: List[str] = intent["sources"]
        active_sources: List[str] = [
            src for src in routed_sources
            if self._source_available.get(src, False)
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
