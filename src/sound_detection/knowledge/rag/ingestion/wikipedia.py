import logging

import wikipedia  # type: ignore[import-untyped]

from .base import DataSource

logger = logging.getLogger(__name__)


class WikipediaSource(DataSource):
    @property
    def source_name(self) -> str:
        return "wikipedia"

    def fetch_species_text(self, scientific_name: str) -> str | None:
        try:
            # Try scientific name first
            try:
                page = wikipedia.page(scientific_name, auto_suggest=True, redirect=True)
            except wikipedia.exceptions.DisambiguationError as e:
                page = wikipedia.page(e.options[0], redirect=True)
            except wikipedia.exceptions.PageError:
                # Fallback: search for the common name
                results = wikipedia.search(scientific_name, results=3)
                if not results:
                    return None
                page = wikipedia.page(results[0], redirect=True)

            content = page.content

            # Clean up
            if "== See also ==" in content:
                content = content.split("== See also ==")[0]
            if "== References ==" in content:
                content = content.split("== References ==")[0]

            content = content.strip()

            return content if len(content) > 200 else None

        except Exception as e:
            logger.error(f"Wikipedia lookup failed for {scientific_name}: {e}")
            return None
