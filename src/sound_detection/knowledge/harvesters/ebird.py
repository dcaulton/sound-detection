import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


class EbirdHarvester:
    BASE_URL = "https://api.ebird.org/v2"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("EBIRD_API_KEY")
        if not self.api_key:
            logger.warning("No EBIRD_API_KEY found — eBird calls will be skipped.")

    def fetch(self, scientific_name: str) -> dict[str, Any] | None:
        """Fetch basic presence + taxonomy info from eBird for a species."""
        if self.api_key is None:
            return None

        try:
            # Step 1: Get species code from taxonomy
            species_code = self._get_species_code(scientific_name)
            if not species_code:
                logger.warning(f"Species not found in eBird taxonomy: {scientific_name}")
                return None

            # Step 2: Check if the species has been recorded in Illinois
            url = f"{self.BASE_URL}/product/spplist/US-IL"
            headers = {"X-eBirdApiToken": self.api_key}  # type: ignore[arg-type]
            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code != 200:
                return None

            illinois_species = response.json()
            is_in_illinois = species_code in illinois_species

            return {
                "scientific_name": scientific_name,
                "taxon": "Bird",
                "ebird_species_code": species_code,
                "recorded_in_illinois": is_in_illinois,
            }

        except Exception as e:
            logger.warning(f"eBird fetch failed for {scientific_name}: {e}")
            return None

    def _get_species_code(self, scientific_name: str) -> str | None:
        """Resolve scientific name to eBird species code."""
        url = f"{self.BASE_URL}/ref/taxonomy/ebird?fmt=json"
        headers = {"X-eBirdApiToken": self.api_key}

        resp = requests.get(url, headers=headers, timeout=15)  # type: ignore[arg-type]
        if resp.status_code != 200:
            return None

        for sp in resp.json():
            if sp.get("sciName") == scientific_name:
                return str(sp.get("speciesCode"))

        return None
