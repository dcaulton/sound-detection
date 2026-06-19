from __future__ import annotations

import logging

from neo4j import Driver

from sound_detection.knowledge.harvesters.ebird import EbirdHarvester
from sound_detection.knowledge.rag.pipeline import RAGPipeline
from sound_detection.knowledge.rag.rag_enricher import RAGEnricher
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
        self.rag_pipeline = RAGPipeline(driver)
        self.rag_enricher = RAGEnricher(driver)  # type: ignore[call-arg]
        self.service = SpeciesKnowledgeService(driver)

    def seed_or_update(self, scientific_name: str, extra_instructions: str | None = None) -> dict:
        # Skip if species already has Wikipedia chunks (deeper enrichment already done)
        try:
            chunks = self.rag_enricher.retriever.retrieve(scientific_name, top_k=1)
            if chunks and any(c.get("source") == "wikipedia" for c in chunks):
                logger.info(f"Species {scientific_name} already enriched with Wikipedia chunks. Skipping.")
                return {}
        except Exception:
            pass  # proceed if retrieval check fails

        existing = self.service.get_species_by_scientific_name(scientific_name)

        if existing:
            logger.warning(f"Species exists, enriching with RAG: {scientific_name}")
            self.rag_pipeline.ingest_species(scientific_name)
            enriched = self.rag_enricher.enrich(scientific_name, existing)
        else:
            logger.warning(f"New species detected: {scientific_name}")

            # Call eBird harvester
            harvested = self.ebird.fetch(scientific_name) or {"scientific_name": scientific_name}

            # Ingest Wikipedia text into vector store
            self.rag_pipeline.ingest_species(scientific_name)

            # Enrich using RAG
            enriched = self.rag_enricher.enrich(scientific_name, harvested)

        self.service.upsert_species(enriched)
        self.service.upsert_relationships(enriched)

        return self.service.get_species_context(scientific_name) or enriched
