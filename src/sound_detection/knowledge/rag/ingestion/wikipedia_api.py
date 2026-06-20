import logging
import time
from typing import Any

import requests

from .base import DataSource

logger = logging.getLogger(__name__)

USER_AGENT = "sound-detection/0.2[](https://github.com/dcaulton/sound-detection)"


class WikipediaSource(DataSource):
    """Wikipedia text fetcher using the MediaWiki API directly (more robust than the wikipedia library)."""

    BASE_URL = "https://en.wikipedia.org/w/api.php"

    @property
    def source_name(self) -> str:
        return "wikipedia"

    def fetch_species_text(self, scientific_name: str) -> str | None:
        for attempt in range(3):
            try:
                # 1. Try direct page
                text = self._get_page_extract(scientific_name)
                if text:
                    return text

                # 2. Try searching with the scientific name
                results = self._search(scientific_name)
                for title in results:
                    text = self._get_page_extract(title)
                    if text:
                        return text

                # 3. Last resort: try searching with just the genus
                genus = scientific_name.split()[0]
                results = self._search(genus)
                for title in results:
                    text = self._get_page_extract(title)
                    if text and scientific_name.lower() in text.lower():
                        return text

                return None

            except Exception as e:
                if attempt < 2:
                    time.sleep((attempt + 1) * 1.5)
                else:
                    logger.debug(f"Wikipedia lookup failed for {scientific_name}: {e}")
                    return None

        return None

    def _get_page_extract(self, title: str) -> str | None:
        params: dict[str, Any] = {
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "explaintext": 1,
            "exsectionformat": "plain",
            "redirects": 1,
            "format": "json",
        }
        headers = {"User-Agent": USER_AGENT}

        resp = requests.get(self.BASE_URL, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            extract: str | None = page.get("extract")
            if extract:
                # Basic cleanup
                if "== See also ==" in extract:
                    extract = extract.split("== See also ==")[0]
                if "== References ==" in extract:
                    extract = extract.split("== References ==")[0]
                extract = extract.strip()[:8000]
                return extract
        return None

    def _search(self, query: str, limit: int = 5) -> list[str]:
        params: dict[str, Any] = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "srwhat": "text",
            "format": "json",
        }
        headers = {"User-Agent": USER_AGENT}

        resp = requests.get(self.BASE_URL, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Search HTTP error: {resp.status_code}")
            return []

        data = resp.json()
        results = [item["title"] for item in data.get("query", {}).get("search", [])]

        return results
