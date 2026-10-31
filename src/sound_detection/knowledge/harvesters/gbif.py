import logging

import requests

logger = logging.getLogger(__name__)


class GbifHarvester:
    """Fetch taxonomic rank chain from GBIF for any organism."""

    BASE_URL = "https://api.gbif.org/v1/species/match"

    def fetch_ranks(self, scientific_name: str) -> list[tuple[str, str]]:
        """Return [(rank, name), ...] from kingdom down to genus/species."""
        try:
            resp = requests.get(self.BASE_URL, params={"name": scientific_name}, timeout=15)
            if resp.status_code != 200:
                return []
            data = resp.json()
            order = ["kingdom", "phylum", "class", "order", "family", "genus"]
            ranks: list[tuple[str, str]] = []
            for rank in order:
                name = data.get(rank)
                if name:
                    ranks.append((rank, name))
            return ranks
        except Exception as e:
            logger.warning(f"GBIF lookup failed for {scientific_name}: {e}")
            return []
