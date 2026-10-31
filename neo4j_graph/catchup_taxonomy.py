"""Backfill iNaturalist taxonomic ancestry into Neo4j.

For every Species node, look up the matching active taxon on iNaturalist,
then MERGE the full ancestor chain as Taxon nodes linked by PARENT_OF.
Also links the Species to its leaf Taxon via IN_TAXON.

A species name is treated as a clade of rank=species. The same path
queries work for "Otidimorphae", "Phoenicopteriformes", or
"Turdus migratorius".

Usage:
    python -m neo4j_graph.catchup_taxonomy
    # or
    uv run python neo4j_graph/catchup_taxonomy.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any

import requests
from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import ServiceUnavailable

load_dotenv()
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

INAT_TAXA_URL = "https://api.inaturalist.org/v1/taxa"
RATE_LIMIT_SLEEP = 1.25  # seconds between requests


def fetch_taxon(scientific_name: str) -> dict[str, Any] | None:
    """Return the best matching active taxon (with ancestors) or None."""
    params: dict[str, str] = {
        "q": scientific_name,
        "is_active": "true",
        "per_page": "5",
        "locale": "en",
    }
    try:
        resp = requests.get(INAT_TAXA_URL, params=params, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("iNat lookup failed for %s: %s", scientific_name, exc)
        return None

    results = resp.json().get("results") or []
    if not results:
        return None

    # Prefer exact scientific name match
    name_lower = scientific_name.lower()
    for t in results:
        if (t.get("name") or "").lower() == name_lower:
            return dict(t)
    return dict(results[0])


def upsert_ancestry(driver: Driver, scientific_name: str, taxon: dict[str, Any]) -> None:
    """MERGE the ancestor chain and link the Species to its leaf taxon."""
    ancestors = taxon.get("ancestors") or []
    # Include the taxon itself as the leaf
    chain = [*ancestors, taxon]

    # Filter out any entries missing id/name
    chain = [a for a in chain if a.get("id") and a.get("name")]

    if not chain:
        log.warning("No usable ancestry for %s", scientific_name)
        return

    prepared = [
        {
            "id": a["id"],
            "name": a.get("name"),
            "rank": a.get("rank"),
            "rank_level": a.get("rank_level"),
            "preferred_common_name": a.get("preferred_common_name"),
        }
        for a in chain
    ]
    leaf = prepared[-1]

    with driver.session() as session:
        # 1. Ensure all Taxon nodes exist
        session.run(
            """
            UNWIND $chain AS node_data
            MERGE (t:Taxon {inat_id: node_data.id})
            SET t.name = node_data.name,
                t.rank = node_data.rank,
                t.rank_level = node_data.rank_level,
                t.preferred_common_name = node_data.preferred_common_name
            """,
            chain=prepared,
        )

        # 2. Link consecutive taxa with PARENT_OF
        if len(prepared) >= 2:
            session.run(
                """
                UNWIND range(0, size($chain) - 2) AS i
                MATCH (parent:Taxon {inat_id: $chain[i].id})
                MATCH (child:Taxon {inat_id: $chain[i + 1].id})
                MERGE (parent)-[:PARENT_OF]->(child)
                """,
                chain=prepared,
            )

        # 3. Link the Species to its leaf taxon and store the iNat id
        session.run(
            """
            MATCH (s:Species {scientific_name: $scientific_name})
            MATCH (leaf:Taxon {inat_id: $leaf_id})
            MERGE (s)-[:IN_TAXON]->(leaf)
            SET s.inat_taxon_id = $leaf_id,
                s.inat_rank = $leaf_rank
            """,
            scientific_name=scientific_name,
            leaf_id=leaf["id"],
            leaf_rank=leaf["rank"],
        )


def main() -> None:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    print(f"Connecting to Neo4j at {uri} as {user} ...")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
    except ServiceUnavailable as exc:
        print(f"ERROR: Could not connect to Neo4j at {uri}", file=sys.stderr)
        print(f"       {exc}", file=sys.stderr)
        print("       Is the neo4j container running? Check: docker compose ps", file=sys.stderr)
        sys.exit(1)

    try:
        with driver.session() as session:
            result = session.run("MATCH (s:Species) RETURN s.scientific_name AS name ORDER BY name")
            names = [r["name"] for r in result if r["name"]]

        total = len(names)
        print(f"Found {total} species to process\n")
        if total == 0:
            print("Nothing to do.")
            return

        for i, name in enumerate(names, 1):
            # Simple progress bar: [=====>    ] 12/48 (25%)
            pct = int(100 * i / total)
            bar_len = 30
            filled = int(bar_len * i / total)
            bar = "=" * filled + ">" + " " * (bar_len - filled - 1)
            print(f"[{bar}] {i:>4}/{total} ({pct:>3}%)  {name}")

            taxon = fetch_taxon(name)
            if taxon:
                upsert_ancestry(driver, name, taxon)
                rank = taxon.get("rank", "?")
                inat_id = taxon.get("id", "?")
                print(f"         -> {rank} id={inat_id}")
            else:
                print("         -> no iNat match")
            time.sleep(RATE_LIMIT_SLEEP)
    finally:
        driver.close()
        print("\nDone.")


if __name__ == "__main__":
    main()
