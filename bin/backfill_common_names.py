"""Fill missing common names from iNaturalist.

Usage:
    DATABASE_URL=postgresql://sound:sound@localhost:5433/sound_detection \
    uv run python bin/backfill_common_names.py
"""

from __future__ import annotations

import os
import time

from neo4j import GraphDatabase

from sound_detection.knowledge.harvesters.inaturalist import InaturalistHarvester

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")
RATE_LIMIT_SLEEP = 1.25


def is_binomial(name: str) -> bool:
    parts = name.split()
    return len(parts) == 2 and parts[0][0].isupper() and parts[1].islower()


def main() -> None:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    harvester = InaturalistHarvester()
    with driver.session() as session:
        rows = session.run(
            "MATCH (s:Species) WHERE s.common_name IS NULL OR s.common_name = '' RETURN s.scientific_name AS name"
        ).data()
        print(f"{len(rows)} species missing a common name")
        for row in rows:
            name = row["name"]
            if not is_binomial(name):
                print(f"  {name} -> skipped (not a binomial)")
                continue
            common = harvester.preferred_common_name(name)
            if not common:
                print(f"  {name} -> none")
                continue
            session.run(
                "MATCH (s:Species {scientific_name: $name}) SET s.common_name = $common",
                name=name,
                common=common,
            )
            print(f"  {name} -> {common}")
            time.sleep(RATE_LIMIT_SLEEP)
    driver.close()


if __name__ == "__main__":
    main()
