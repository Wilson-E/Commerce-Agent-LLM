"""ASOS Product Search client (via RapidAPI)."""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.utils.config import settings

log = logging.getLogger(__name__)

ASOS_HOST = "asos2.p.rapidapi.com"
ASOS_BASE_URL = f"https://{ASOS_HOST}"


class AsosClient:
    """Client for the ASOS product search API via RapidAPI.

    Provides fashion-specific product data including sizes, colors,
    and brand information.  Uses the same RAPIDAPI_KEY as other
    RapidAPI-based clients.
    """

    def __init__(self):
        self._headers = {
            "X-RapidAPI-Key": settings.RAPIDAPI_KEY,
            "X-RapidAPI-Host": ASOS_HOST,
        }

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search ASOS products via /products/v2/list."""
        params: Dict[str, Any] = {
            "q": query,
            "store": "US",
            "offset": str(page * limit),
            "limit": str(min(limit, 48)),
            "country": "US",
            "currency": "USD",
            "sizeSchema": "US",
            "lang": "en-US",
        }

        if filters:
            if "min_price" in filters:
                params["priceMin"] = str(filters["min_price"])
            if "max_price" in filters:
                params["priceMax"] = str(filters["max_price"])

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ASOS_BASE_URL}/products/v2/list",
                headers=self._headers,
                params=params,
            )

        if resp.status_code != 200:
            log.warning(
                "ASOS search error %s: %s", resp.status_code, resp.text[:300]
            )
            return []

        data = resp.json()
        return data.get("products", [])

    async def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full product details by ASOS product ID."""
        params = {
            "id": product_id,
            "store": "US",
            "currency": "USD",
            "sizeSchema": "US",
            "lang": "en-US",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ASOS_BASE_URL}/products/v3/detail",
                headers=self._headers,
                params=params,
            )

        if resp.status_code != 200:
            log.warning(
                "ASOS product detail error %s for %s",
                resp.status_code,
                product_id,
            )
            return None

        return resp.json()
