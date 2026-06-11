#!/usr/bin/env python3
"""
Neo4j Species Seeder for Sound Detection project.

Initial version uses a small, focused seed list.
Designed to be idempotent and easy to extend later for incremental ingestion
(single species or short lists when new detections occur).
"""

import logging
import os
from typing import Any

from dotenv import load_dotenv

from neo4j import Driver, GraphDatabase

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class Neo4jSeeder:
    def __init__(self, uri: str, user: str, password: str) -> None:
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, password))
        logger.info("Connected to Neo4j")

    def close(self) -> None:
        self.driver.close()

    def upsert_species(self, species_data: dict[str, Any]) -> None:
        """Idempotent upsert of a Species node."""
        query = """
        MERGE (s:Species {scientific_name: $scientific_name})
        ON CREATE SET
            s.common_name = $common_name,
            s.taxon = $taxon,
            s.created_at = datetime(),
            s.updated_at = datetime()
        ON MATCH SET
            s.common_name = coalesce($common_name, s.common_name),
            s.taxon = coalesce($taxon, s.taxon),
            s.updated_at = datetime()
        RETURN s
        """
        with self.driver.session() as session:
            session.run(query, species_data)
            logger.info(f"Upserted: {species_data['common_name']}")

    def seed_species(self, species_list: list[dict[str, Any]]) -> None:
        """Seed or update a list of species."""
        logger.info(f"Seeding {len(species_list)} species...")
        for species in species_list:
            self.upsert_species(species)
        logger.info("Seeding complete.")


# ============================================================
# Initial focused seed list (as requested)
# ============================================================

INITIAL_SPECIES = [
    {"scientific_name": "Turdus migratorius", "common_name": "American Robin", "taxon": "Bird"},
    {"scientific_name": "Passer domesticus", "common_name": "House Sparrow", "taxon": "Bird"},
    {"scientific_name": "Cyanocitta cristata", "common_name": "Blue Jay", "taxon": "Bird"},
    {"scientific_name": "Agelaius phoeniceus", "common_name": "Red-winged Blackbird", "taxon": "Bird"},
    {"scientific_name": "Buteo jamaicensis", "common_name": "Red-tailed Hawk", "taxon": "Bird"},
]


def main() -> None:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    seeder = Neo4jSeeder(uri, user, password)
    try:
        seeder.seed_species(INITIAL_SPECIES)
    finally:
        seeder.close()


if __name__ == "__main__":
    main()
