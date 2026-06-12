from __future__ import annotations

import logging

from neo4j import Driver

from sound_detection.knowledge.harvesters.ebird import EbirdHarvester

# from sound_detection.knowledge.enrichers.llm_enricher import LLMEnricher
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
        #        self.llm_enricher = LLMEnricher()
        self.service = SpeciesKnowledgeService(driver)

    def seed_or_update(self, scientific_name: str) -> dict:
        """
        Main entry point.
        Returns the final species data after harvesting and enrichment.
        """
        # 1. Check if we already have this species
        existing = self.service.get_species_by_scientific_name(scientific_name)
        if existing:
            logger.info(f"Species already exists: {scientific_name}")
            return existing

        logger.info(f"New species detected: {scientific_name}. Starting harvest...")

        # 2. Try to harvest from best available source
        harvested_data = self._harvest(scientific_name)

        if not harvested_data:
            logger.warning(f"No data found for {scientific_name}. Creating minimal record.")
            harvested_data = {"scientific_name": scientific_name}

        # 3. Enrich with LLM (diet, pollinator status, interesting facts, etc.)
        #        enriched_data = self.llm_enricher.enrich(harvested_data)
        enriched_data = harvested_data  # TODO REMOVE

        # 4. Write to Neo4j (node + basic relationships)
        self._persist_to_neo4j(enriched_data)

        # 5. Return final view
        return self.service.get_species_context(scientific_name) or enriched_data

    def _harvest(self, scientific_name: str) -> dict | None:
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

    def _persist_to_neo4j(self, data: dict) -> None:
        """Write species node and basic relationships to Neo4j."""
        # For now we keep it simple. We can expand this significantly
        # once we have more harvester data and relationship types.
        query = """
        MERGE (s:Species {scientific_name: $scientific_name})
        SET s.common_name = $common_name,
            s.taxon = $taxon,
            s.residency_status = $residency_status,
            s.migration_notes = $migration_notes,
            s.updated_at = datetime()
        ON CREATE SET s.created_at = datetime()
        """
        with self.driver.session() as session:
            session.run(query, **data)
            logger.info(f"Persisted species to Neo4j: {data.get('scientific_name')}")
