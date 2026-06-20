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
            species_info = self._get_species_info(scientific_name)
            if not species_info:
                logger.warning(f"Species not found in eBird taxonomy: {scientific_name}")
                return None

            species_code = species_info["speciesCode"]

            # Check Illinois presence (unchanged)
            url = f"{self.BASE_URL}/product/spplist/US-IL"
            headers = {"X-eBirdApiToken": self.api_key}
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                return None

            illinois_species = response.json()
            is_in_illinois = species_code in illinois_species

            return {
                "scientific_name": scientific_name,
                "common_name": species_info.get("comName"),
                "taxon": "Bird",
                "ebird_species_code": species_code,
                "recorded_in_illinois": is_in_illinois,
            }
        except Exception as e:
            logger.warning(f"eBird fetch failed for {scientific_name}: {e}")
            return None

    def _get_species_info(self, scientific_name: str) -> dict | None:
        """Resolve scientific name to eBird species info (code + common name)."""
        url = f"{self.BASE_URL}/ref/taxonomy/ebird?fmt=json"
        headers: dict[str, str] = {}
        if self.api_key:
            headers = {"X-eBirdApiToken": self.api_key}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        for sp in resp.json():
            if sp.get("sciName") == scientific_name:
                return {
                    "speciesCode": sp.get("speciesCode"),
                    "comName": sp.get("comName"),
                }
        return None
