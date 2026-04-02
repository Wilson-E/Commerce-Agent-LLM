"""Best Buy Products API client."""
import logging
import urllib.parse
from typing import Any, Dict, List, Optional

import httpx

from app.utils.config import settings

log = logging.getLogger(__name__)

BESTBUY_BASE_URL = "https://api.bestbuy.com/v1"
BESTBUY_PRODUCT_FIELDS = (
    "sku,name,salePrice,regularPrice,shortDescription,description,"
    "image,url,categoryPath,manufacturer,rating,reviewCount,"
    "inStoreAvailability,onlineAvailability"
)


class BestBuyClient:
    """Client for the Best Buy Products API."""

    def __init__(self):
        self._api_key = settings.BEST_BUY_API_KEY

    def _build_search_url(self, query: str, filters: Optional[Dict[str, Any]]) -> str:
        """Build the Best Buy filter URL with conditions in parentheses."""
        conditions = [f"search={urllib.parse.quote(query, safe='')}"]
        if filters:
            if "min_price" in filters:
                conditions.append(f"salePrice%3E%3D{filters['min_price']}")
            if "max_price" in filters:
                conditions.append(f"salePrice%3C%3D{filters['max_price']}")
        return f"{BESTBUY_BASE_URL}/products({'%26'.join(conditions)})"

    async def search(
        self,
        query: str,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search Best Buy products and return a list of product dicts."""
        url = self._build_search_url(query, filters)
        params: Dict[str, Any] = {
            "apiKey": self._api_key,
            "format": "json",
            "show": BESTBUY_PRODUCT_FIELDS,
            "pageSize": str(min(limit, 100)),
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)

        if resp.status_code != 200:
            log.warning("Best Buy search error %s: %s", resp.status_code, resp.text[:300])
            return []

        return resp.json().get("products", [])

    async def get_product(self, sku: str) -> Optional[Dict[str, Any]]:
        """Fetch full product detail by SKU."""
        params = {
            "apiKey": self._api_key,
            "format": "json",
            "show": BESTBUY_PRODUCT_FIELDS,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{BESTBUY_BASE_URL}/products/{sku}.json",
                params=params,
            )

        if resp.status_code != 200:
            log.warning("Best Buy product detail error %s for %s", resp.status_code, sku)
            return None

        return resp.json()
