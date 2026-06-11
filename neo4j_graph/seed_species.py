#!/usr/bin/env python3
"""
Neo4j Species Seeder with relationships.
Idempotent. Safe to re-run.
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
    def __init__(
        self,
        driver_or_uri: str | Driver,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        if isinstance(driver_or_uri, Driver):
            self.driver: Driver = driver_or_uri
        else:
            if user is None or password is None:
                raise ValueError("user and password are required when passing a URI string")
            self.driver = GraphDatabase.driver(driver_or_uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    def upsert_species(self, species_data: dict[str, Any]) -> None:
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
        """
        with self.driver.session() as session:
            session.run(query, species_data)

    def create_relationships(self) -> None:
        """Create relationships between species, regions, and habitats."""
        queries = [
            # American Robin
            """
            MATCH (s:Species {scientific_name: 'Turdus migratorius'})
            MERGE (r:Region {name: 'Illinois'})
            MERGE (s)-[:RESIDENT_IN {status: 'year_round'}]->(r)
            MERGE (h:Habitat {name: 'OakSavanna'})
            MERGE (s)-[:BREEDS_IN]->(h)
            """,
            # House Sparrow (invasive resident)
            """
            MATCH (s:Species {scientific_name: 'Passer domesticus'})
            MERGE (r:Region {name: 'Illinois'})
            MERGE (s)-[:RESIDENT_IN {status: 'year_round'}]->(r)
            """,
            # Blue Jay
            """
            MATCH (s:Species {scientific_name: 'Cyanocitta cristata'})
            MERGE (r:Region {name: 'Illinois'})
            MERGE (s)-[:RESIDENT_IN {status: 'year_round'}]->(r)
            MERGE (h:Habitat {name: 'OakSavanna'})
            MERGE (s)-[:BREEDS_IN]->(h)
            """,
            # Red-winged Blackbird (strong prairie/wetland association)
            """
            MATCH (s:Species {scientific_name: 'Agelaius phoeniceus'})
            MERGE (r:Region {name: 'Illinois'})
            MERGE (s)-[:RESIDENT_IN {status: 'breeding'}]->(r)
            MERGE (h:Habitat {name: 'TallgrassPrairie'})
            MERGE (s)-[:BREEDS_IN]->(h)
            MERGE (s)-[:INDICATOR_OF]->(h)
            """,
            # Red-tailed Hawk
            """
            MATCH (s:Species {scientific_name: 'Buteo jamaicensis'})
            MERGE (r:Region {name: 'Illinois'})
            MERGE (s)-[:RESIDENT_IN {status: 'year_round'}]->(r)
            MERGE (h:Habitat {name: 'OakSavanna'})
            MERGE (s)-[:BREEDS_IN]->(h)
            """,
        ]

        with self.driver.session() as session:
            for query in queries:
                session.run(query)
        logger.info("Relationships created/updated.")

    def seed_species(self, species_list: list[dict[str, Any]]) -> None:
        logger.info(f"Seeding {len(species_list)} species...")
        for species in species_list:
            self.upsert_species(species)
        self.create_relationships()
        logger.info("Seeding + relationships complete.")


# Initial species list
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
