import logging
import time

import wikipedia  # type: ignore[import-untyped]

from .base import DataSource

logger = logging.getLogger(__name__)


class WikipediaSource(DataSource):
    @property
    def source_name(self) -> str:
        return "wikipedia"

    def fetch_species_text(self, scientific_name: str) -> str | None:
        for attempt in range(2):  # 1 retry
            try:
                try:
                    page = wikipedia.page(scientific_name, auto_suggest=True, redirect=True)
                except wikipedia.exceptions.DisambiguationError as e:
                    try:
                        page = wikipedia.page(e.options[0], redirect=True)
                    except Exception:
                        return None
                except wikipedia.exceptions.PageError:
                    # Fallback: search for the common name
                    results = wikipedia.search(scientific_name, results=3)
                    if not results:
                        return None
                    try:
                        page = wikipedia.page(results[0], redirect=True)
                    except Exception:
                        return None

                content = page.content
                if "== See also ==" in content:
                    content = content.split("== See also ==")[0]
                if "== References ==" in content:
                    content = content.split("== References ==")[0]
                content = content[:8000]
                return str(content.strip())

            except Exception as e:
                if attempt == 0:
                    time.sleep(1)
                else:
                    logger.debug(f"Wikipedia lookup failed for {scientific_name}: {e}")
                    return None
        return None
