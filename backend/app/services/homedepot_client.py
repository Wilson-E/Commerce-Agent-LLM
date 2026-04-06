"""Home Depot Product Search client (via RapidAPI)."""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.utils.config import settings

log = logging.getLogger(__name__)

HOMEDEPOT_HOST = "home-depot2.p.rapidapi.com"
HOMEDEPOT_BASE_URL = f"https://{HOMEDEPOT_HOST}"


class HomeDepotClient:
    """Client for the Home Depot product search API via RapidAPI.

    Provides home improvement, furniture, and appliance product data.
    Uses the same RAPIDAPI_KEY as other RapidAPI-based clients.
    """

    def __init__(self):
        self._headers = {
            "X-RapidAPI-Key": settings.RAPIDAPI_KEY,
            "X-RapidAPI-Host": HOMEDEPOT_HOST,
        }

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """Search Home Depot products via /search."""
        params: Dict[str, Any] = {
            "q": query,
            "store": "6308",
            "page": str(page),
        }

        if filters:
            if "min_price" in filters:
                params["minPrice"] = str(filters["min_price"])
            if "max_price" in filters:
                params["maxPrice"] = str(filters["max_price"])

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{HOMEDEPOT_BASE_URL}/search",
                headers=self._headers,
                params=params,
            )

        if resp.status_code != 200:
            log.warning(
                "Home Depot search error %s: %s", resp.status_code, resp.text[:300]
            )
            return []

        data = resp.json()
        products = data.get("products", [])
        return products[:limit]

    async def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full product details by Home Depot item ID."""
        params = {"id": product_id}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{HOMEDEPOT_BASE_URL}/product",
                headers=self._headers,
                params=params,
            )

        if resp.status_code != 200:
            log.warning(
                "Home Depot product detail error %s for %s",
                resp.status_code,
                product_id,
            )
            return None

        return resp.json()
