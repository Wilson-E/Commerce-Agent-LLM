"""Walmart Affiliate API client."""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.utils.config import settings

log = logging.getLogger(__name__)

WALMART_BASE_URL = "https://api.walmartlabs.com/v1"


class WalmartClient:
    """Client for the Walmart Affiliate (Open) API.

    Register for a free API key at https://walmart.io
    """

    def __init__(self):
        self._api_key = settings.WALMART_API_KEY

    async def search(
        self,
        query: str,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search Walmart products and return a list of item dicts."""
        params: Dict[str, Any] = {
            "apiKey": self._api_key,
            "query": query,
            "numItems": str(min(limit, 25)),
            "format": "json",
        }

        if filters:
            if "min_price" in filters:
                params["minPrice"] = str(filters["min_price"])
            if "max_price" in filters:
                params["maxPrice"] = str(filters["max_price"])

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{WALMART_BASE_URL}/search", params=params)

        if resp.status_code != 200:
            log.warning("Walmart search error %s: %s", resp.status_code, resp.text[:300])
            return []

        return resp.json().get("items", [])

    async def get_product(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full product detail by Walmart item ID."""
        params = {
            "apiKey": self._api_key,
            "format": "json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{WALMART_BASE_URL}/items/{item_id}",
                params=params,
            )

        if resp.status_code != 200:
            log.warning("Walmart item detail error %s for %s", resp.status_code, item_id)
            return None

        return resp.json()
