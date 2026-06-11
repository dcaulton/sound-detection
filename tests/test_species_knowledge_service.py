from typing import Any

import pytest
from neo4j import Driver

from sound_detection.knowledge.species_knowledge_service import SpeciesKnowledgeService


@pytest.fixture(scope="module")
def neo4j_driver(neo4j_driver: Driver) -> Any:
    # Seed the test database with our initial species
    from neo4j_graph.seed_species import INITIAL_SPECIES, Neo4jSeeder

    seeder = Neo4jSeeder(neo4j_driver)
    seeder.seed_species(INITIAL_SPECIES)
    yield neo4j_driver
    neo4j_driver.close()


def test_get_species_by_scientific_name(neo4j_driver: Any) -> None:
    service = SpeciesKnowledgeService(neo4j_driver)

    result = service.get_species_by_scientific_name("Turdus migratorius")

    assert result is not None
    assert result["scientific_name"] == "Turdus migratorius"
    assert result["common_name"] == "American Robin"


def test_list_all_species(neo4j_driver: Any) -> None:
    service = SpeciesKnowledgeService(neo4j_driver)

    results = service.list_all_species(limit=10)

    assert len(results) >= 5
    scientific_names = [s["scientific_name"] for s in results]
    assert "Turdus migratorius" in scientific_names


def test_get_species_context(neo4j_driver: Any) -> None:
    service = SpeciesKnowledgeService(neo4j_driver)

    result = service.get_species_context("Cyanocitta cristata")

    assert result is not None
    assert result["scientific_name"] == "Cyanocitta cristata"
    assert "migration_peak_months" in result
    assert "breeds_in_habitats" in result
    assert "indicator_for_habitats" in result
