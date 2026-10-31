import os

from neo4j import GraphDatabase

from sound_detection.knowledge.harvesters.gbif import GbifHarvester
from sound_detection.knowledge.species_knowledge_service import SpeciesKnowledgeService


def main() -> None:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    service = SpeciesKnowledgeService(driver)
    gbif = GbifHarvester()

    species = service.list_all_species(limit=1000)
    print(f"Found {len(species)} species")

    for s in species:
        name = s["scientific_name"]
        ranks = gbif.fetch_ranks(name)
        if not ranks:
            print(f"  no ranks for {name}")
            continue
        service.upsert_taxonomy(name, ranks)
        print(f"  wrote {len(ranks)} ranks for {name}")

    driver.close()


if __name__ == "__main__":
    main()
