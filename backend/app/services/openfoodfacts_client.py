"""Open Food Facts API client (no API key required)."""
import logging
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

OPENFOODFACTS_BASE_URL = "https://world.openfoodfacts.org"


class OpenFoodFactsClient:
    """Client for the Open Food Facts API.

    Completely free — no registration or API key required.
    https://world.openfoodfacts.org/data
    """

    async def search(
        self,
        query: str,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search food products and return a list of product dicts."""
        params: Dict[str, Any] = {
            "search_terms": query,
            "json": "1",
            "page_size": str(min(limit, 50)),
            "action": "process",
            "fields": (
                "code,product_name,product_name_en,brands,categories,"
                "image_url,image_front_url,quantity,nutriscore_score,"
                "ecoscore_grade,ingredients_text"
            ),
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{OPENFOODFACTS_BASE_URL}/cgi/search.pl",
                params=params,
            )

        if resp.status_code != 200:
            log.warning(
                "Open Food Facts search error %s: %s", resp.status_code, resp.text[:300]
            )
            return []

        return resp.json().get("products", [])

    async def get_product(self, barcode: str) -> Optional[Dict[str, Any]]:
        """Fetch full product detail by barcode."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{OPENFOODFACTS_BASE_URL}/api/v0/product/{barcode}.json"
            )

        if resp.status_code != 200:
            log.warning(
                "Open Food Facts product detail error %s for %s", resp.status_code, barcode
            )
            return None

        data = resp.json()
        if data.get("status") != 1:
            return None

        return data.get("product")
