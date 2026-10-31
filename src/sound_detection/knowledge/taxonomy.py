"""Taxonomy query helpers for SpeciesKnowledgeService.

Add these methods to SpeciesKnowledgeService (or keep them as free functions
that take a Driver). They rely on the Taxon / IN_TAXON / PARENT_OF structure
created by catchup_taxonomy.py.
"""

from __future__ import annotations

from typing import Any

from neo4j import Driver


def get_ancestry(driver: Driver, scientific_name: str) -> list[dict[str, Any]]:
    """Return the ancestor chain from kingdom down to the species taxon, plus the species itself.

    Each item: {"name": str, "rank": str, "inat_id": int}
    """
    query = """
    MATCH (s:Species {scientific_name: $scientific_name})-[:IN_TAXON]->(leaf:Taxon)
    OPTIONAL MATCH path = (root:Taxon)-[:PARENT_OF*0..]->(leaf)
    WHERE NOT ( ()-[:PARENT_OF]->(root) )
    WITH leaf, path
    ORDER BY length(path) DESC
    LIMIT 1
    RETURN [n IN nodes(path) | {name: n.name, rank: n.rank, inat_id: n.inat_id}] AS chain
    """
    with driver.session() as session:
        result = session.run(query, scientific_name=scientific_name)
        record = result.single()
        if not record or not record["chain"]:
            return []
        return list(record["chain"])


def is_under_clade(driver: Driver, scientific_name: str, clade_name: str) -> bool:
    """True if the species sits under (or is) the named clade."""
    query = """
    MATCH (s:Species {scientific_name: $scientific_name})-[:IN_TAXON]->(leaf:Taxon)
    MATCH (ancestor:Taxon {name: $clade_name})
    WHERE ancestor = leaf OR (ancestor)-[:PARENT_OF*]->(leaf)
    RETURN count(*) > 0 AS under
    """
    with driver.session() as session:
        result = session.run(
            query,
            scientific_name=scientific_name,
            clade_name=clade_name,
        )
        record = result.single()
        return bool(record and record["under"])


def ancestry_names(driver: Driver, scientific_name: str) -> list[str]:
    """Convenience: just the names in the chain, including the species."""
    chain = get_ancestry(driver, scientific_name)
    names = [n["name"] for n in chain if n.get("name")]
    # Always include the species name itself even if the graph link is missing
    if scientific_name not in names:
        names.append(scientific_name)
    return names
