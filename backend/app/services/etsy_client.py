"""Etsy Open API v3 client."""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.utils.config import settings

log = logging.getLogger(__name__)

ETSY_BASE_URL = "https://openapi.etsy.com/v3/application"


class EtsyClient:
    """Client for the Etsy Open API v3.

    Register for a free API key at https://www.etsy.com/developers
    """

    def __init__(self):
        self._headers = {"x-api-key": settings.ETSY_API_KEY}

    async def search(
        self,
        query: str,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search active Etsy listings and return a list of listing dicts."""
        params: Dict[str, Any] = {
            "keywords": query,
            "limit": str(min(limit, 100)),
            "includes": ["Images", "Shop"],
        }

        if filters:
            if "min_price" in filters:
                params["min_price"] = str(filters["min_price"])
            if "max_price" in filters:
                params["max_price"] = str(filters["max_price"])

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ETSY_BASE_URL}/listings/active",
                headers=self._headers,
                params=params,
            )

        if resp.status_code != 200:
            log.warning("Etsy search error %s: %s", resp.status_code, resp.text[:300])
            return []

        return resp.json().get("results", [])

    async def get_product(self, listing_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full listing detail by listing ID."""
        params = {"includes": ["Images", "Shop"]}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ETSY_BASE_URL}/listings/{listing_id}",
                headers=self._headers,
                params=params,
            )

        if resp.status_code != 200:
            log.warning("Etsy listing detail error %s for %s", resp.status_code, listing_id)
            return None

        return resp.json()
