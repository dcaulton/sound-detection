from __future__ import annotations

import logging

from neo4j import Driver

from sound_detection.knowledge.enrichers.llm_enricher import LLMEnricher
from sound_detection.knowledge.harvesters.ebird import EbirdHarvester
from sound_detection.knowledge.species_knowledge_service import SpeciesKnowledgeService

logger = logging.getLogger(__name__)


class SeedOrUpdate:
    """
    Orchestrates harvesting + enrichment + storage for any detected species.

    Designed to be:
    - Taxon-agnostic at the top level (birds, bats, insects, etc.)
    - Extensible with additional harvesters (iNaturalist, etc.)
    - Idempotent
    """

    def __init__(self, driver: Driver) -> None:
        self.driver = driver
        self.ebird = EbirdHarvester()
        self.llm_enricher = LLMEnricher()
        self.service = SpeciesKnowledgeService(driver)

    def seed_or_update(self, scientific_name: str, extra_instructions: str | None) -> dict:
        """
        Main entry point.
        Returns the final species data after harvesting and enrichment.
        """
        # 1. Check if we already have this species
        existing = self.service.get_species_by_scientific_name(scientific_name)
        if existing:
            logger.warning(f"Species already exists: {scientific_name}")

        logger.warning(f"New species detected: {scientific_name}. Starting harvest...")

        # 2. Try to harvest from best available source
        harvested_data = self.harvest(scientific_name)

        if not harvested_data:
            logger.warning(f"No data found for {scientific_name}. Creating minimal record.")
            harvested_data = {"scientific_name": scientific_name}

        # 3. Enrich with LLM (diet, pollinator status, interesting facts, etc.)
        enriched_data = self.llm_enricher.enrich(harvested_data, extra_instructions)

        # 4. Write to Neo4j (node + basic relationships)
        self.service.upsert_species(enriched_data)
        self.service.upsert_relationships(enriched_data)

        # 5. Return final view
        return self.service.get_species_context(scientific_name) or enriched_data

    def harvest(self, scientific_name: str) -> dict | None:
        """
        Try harvesters in order of preference.
        Currently only eBird. More can be added easily.
        """
        # eBird is excellent for birds (covers ~80% of current use case)
        data = self.ebird.fetch(scientific_name)
        if data:
            return data

        # Future: Add iNaturalist or other harvesters here
        # data = self.inaturalist.fetch(scientific_name)
        # if data: return data

        return None
