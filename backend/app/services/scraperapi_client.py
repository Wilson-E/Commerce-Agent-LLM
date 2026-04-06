"""ScraperAPI structured data client — Amazon product search."""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.utils.config import settings

log = logging.getLogger(__name__)

SCRAPERAPI_BASE_URL = "https://api.scraperapi.com/structured/amazon/search"
SCRAPERAPI_PRODUCT_URL = "https://api.scraperapi.com/structured/amazon/product"


class ScraperAPIClient:
    """Client for ScraperAPI's structured Amazon data endpoints.

    Register and get your API key at https://www.scraperapi.com
    """

    def __init__(self):
        self._api_key = settings.SCRAPERAPI_KEY

    async def search(
        self,
        query: str,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search Amazon products via ScraperAPI structured data."""
        params: Dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "country": "us",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(SCRAPERAPI_BASE_URL, params=params)

        if resp.status_code != 200:
            log.warning("ScraperAPI search error %s: %s", resp.status_code, resp.text[:300])
            return []

        results = resp.json().get("results", [])
        return results[:limit]

    async def get_product(self, asin: str) -> Optional[Dict[str, Any]]:
        """Fetch full Amazon product detail by ASIN."""
        params = {
            "api_key": self._api_key,
            "asin": asin,
            "country": "us",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(SCRAPERAPI_PRODUCT_URL, params=params)

        if resp.status_code != 200:
            log.warning("ScraperAPI product detail error %s for %s", resp.status_code, asin)
            return None

        return resp.json()
