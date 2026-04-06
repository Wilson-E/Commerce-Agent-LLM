"""Rainforest API client — Amazon product data."""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.utils.config import settings

log = logging.getLogger(__name__)

RAINFOREST_BASE_URL = "https://api.rainforestapi.com/request"


class RainforestClient:
    """Client for the Rainforest API (Amazon product data).

    Register and get your API key at https://www.rainforestapi.com
    """

    def __init__(self):
        self._api_key = settings.RAINFOREST_API_KEY

    async def search(
        self,
        query: str,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search Amazon products and return a list of search result dicts."""
        params: Dict[str, Any] = {
            "api_key": self._api_key,
            "type": "search",
            "amazon_domain": "amazon.com",
            "search_term": query,
            "output": "json",
        }

        if filters:
            if "min_price" in filters:
                params["min_price"] = str(int(filters["min_price"]))
            if "max_price" in filters:
                params["max_price"] = str(int(filters["max_price"]))

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(RAINFOREST_BASE_URL, params=params)

        if resp.status_code != 200:
            log.warning("Rainforest search error %s: %s", resp.status_code, resp.text[:300])
            return []

        results = resp.json().get("search_results", [])
        return results[:limit]

    async def get_product(self, asin: str) -> Optional[Dict[str, Any]]:
        """Fetch full product detail by Amazon ASIN."""
        params = {
            "api_key": self._api_key,
            "type": "product",
            "amazon_domain": "amazon.com",
            "asin": asin,
            "output": "json",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(RAINFOREST_BASE_URL, params=params)

        if resp.status_code != 200:
            log.warning("Rainforest product detail error %s for %s", resp.status_code, asin)
            return None

        return resp.json().get("product")
