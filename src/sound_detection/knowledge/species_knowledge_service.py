from typing import Any

from neo4j import Driver
from neo4j.time import DateTime as Neo4jDateTime


class SpeciesKnowledgeService:
    """
    Service layer for querying species ecological context from Neo4j.
    Focused on residency, migration, and habitat relationships.
    """

    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def upsert_species(self, data: dict) -> None:
        # Separate scalar properties from relationship data
        props = {
            k: v for k, v in data.items() if not isinstance(v, list | dict) and v is not None and k != "scientific_name"
        }

        """Create or update the Species node and its properties."""
        query = """
        MERGE (s:Species {scientific_name: $scientific_name})
        ON MATCH SET
            s += $props,
            s.updated_at = datetime()
        ON CREATE SET 
            s += $props,
            s.created_at = datetime()
        """

        with self.driver.session() as session:
            session.run(query, scientific_name=data["scientific_name"], props=props)

    def upsert_relationships(self, data: dict) -> None:
        """
        Create/update relationships from the data dict.
        Related nodes are created if they don't exist.
        """
        scientific_name = data.get("scientific_name")
        if not scientific_name:
            return

        with self.driver.session() as session:
            # Example: Handle residency
            if "residency_status" in data and data.get("region"):
                session.run(
                    """
                    MERGE (s:Species {scientific_name: $scientific_name})
                    MERGE (r:Region {name: $region})
                    MERGE (s)-[:RESIDENT_IN {status: $status}]->(r)
                """,
                    scientific_name=scientific_name,
                    region=data.get("region", "Illinois"),
                    status=data.get("residency_status"),
                )

            # Example: Handle habitat
            if data.get("breeds_in_habitat"):
                session.run(
                    """
                    MERGE (s:Species {scientific_name: $scientific_name})
                    MERGE (h:Habitat {name: $habitat})
                    MERGE (s)-[:BREEDS_IN]->(h)
                """,
                    scientific_name=scientific_name,
                    habitat=data["breeds_in_habitat"],
                )

    def get_species_by_scientific_name(self, scientific_name: str) -> dict[str, Any] | None:
        """Basic species lookup by scientific name."""
        query = """
        MATCH (s:Species {scientific_name: $scientific_name})
        RETURN s.scientific_name AS scientific_name,
               s.common_name AS common_name,
               s.taxon AS taxon
        """
        with self.driver.session() as session:
            result = session.run(query, scientific_name=scientific_name)
            record = result.single()
            return dict(record) if record else None

    def _convert_neo4j_types(self, value: Any) -> Any:
        if isinstance(value, Neo4jDateTime):
            return value.to_native()  # converts to standard datetime.datetime
        if isinstance(value, dict):
            return {k: self._convert_neo4j_types(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._convert_neo4j_types(item) for item in value]
        return value

    def get_species_residency(self, scientific_name: str) -> dict[str, Any] | None:
        """
        Returns residency and migration information for a species in Illinois.
        This is the core method for our highest-priority feature.
        """
        query = """
        MATCH (s:Species {scientific_name: $scientific_name})
        OPTIONAL MATCH (s)-[r:RESIDENT_IN]->(reg:Region {name: 'Illinois'})
        OPTIONAL MATCH (s)-[m:MIGRATES_THROUGH]->(reg)
        RETURN s.scientific_name AS scientific_name,
               s.common_name AS common_name,
               r.status AS residency_status,
               m.peak_months AS migration_peak_months
        """
        with self.driver.session() as session:
            result = session.run(query, scientific_name=scientific_name)
            record = result.single()
            if not record:
                return None
            return {
                "scientific_name": record["scientific_name"],
                "common_name": record["common_name"],
                "residency_status": record["residency_status"],
                "migration_peak_months": record["migration_peak_months"],
            }

    def get_species_habitat_context(self, scientific_name: str) -> dict[str, Any] | None:
        """Returns habitat relationships (breeding + indicator status)."""
        query = """
        MATCH (s:Species {scientific_name: $scientific_name})
        OPTIONAL MATCH (s)-[:BREEDS_IN]->(h:Habitat)
        OPTIONAL MATCH (s)-[:INDICATOR_OF]->(h2:Habitat)
        RETURN s.scientific_name AS scientific_name,
               s.common_name AS common_name,
               collect(DISTINCT h.name) AS breeds_in_habitats,
               collect(DISTINCT h2.name) AS indicator_for_habitats
        """
        with self.driver.session() as session:
            result = session.run(query, scientific_name=scientific_name)
            record = result.single()
            if not record:
                return None
            return {
                "scientific_name": record["scientific_name"],
                "common_name": record["common_name"],
                "breeds_in_habitats": record["breeds_in_habitats"],
                "indicator_for_habitats": record["indicator_for_habitats"],
            }

    def get_species_context(self, scientific_name: str) -> dict[str, Any] | None:
        query = """
        MATCH (s:Species {scientific_name: $scientific_name})
        OPTIONAL MATCH (s)-[r_out]->(target_out)
        OPTIONAL MATCH (source_in)-[r_in]->(s)
        RETURN 
            properties(s) AS props,
            collect(DISTINCT {
                type: type(r_out),
                target_labels: labels(target_out),
                target_props: properties(target_out)
            }) AS outgoing,
            collect(DISTINCT {
                type: type(r_in),
                source_labels: labels(source_in),
                source_props: properties(source_in)
            }) AS incoming
        """
        with self.driver.session() as session:
            result = session.run(query, scientific_name=scientific_name)
            record = result.single()
            if not record:
                return None

            outgoing = self._convert_neo4j_types(record["outgoing"])
            outgoing = [x for x in outgoing if x.get("type") is not None]
            for x in outgoing:
                target_props = x.get("target_props") or {}
                if "embedding" in target_props:
                    target_props.pop("embedding")

            incoming = self._convert_neo4j_types(record["incoming"])
            incoming = [x for x in incoming if x.get("type") is not None]
            for x in incoming:
                source_props = x.get("source_props") or {}
                if "embedding" in source_props:
                    source_props.pop("embedding")

            return {
                "props": self._convert_neo4j_types(record["props"]),
                "outgoing": outgoing,
                "incoming": incoming,
            }

    def list_all_species(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return a list of species (useful for debugging and basic UI)."""
        query = """
        MATCH (s:Species)
        RETURN s.scientific_name AS scientific_name,
               s.common_name AS common_name,
               s.taxon AS taxon
        ORDER BY s.scientific_name
        LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(query, limit=limit)
            return [dict(record) for record in result]

    def update_species(self, scientific_name: str, **fields: dict[str, Any]) -> None:
        """Update properties on an existing Species node."""
        if not fields:
            return

        set_clauses = ", ".join(f"s.{k} = ${k}" for k in fields)
        query = f"""
        MATCH (s:Species {{scientific_name: $scientific_name}})
        SET {set_clauses}
        """
        with self.driver.session() as session:
            session.run(query, scientific_name=scientific_name, **fields)

    def delete_species(self, scientific_name: str, delete_chunks: bool = True) -> None:
        """Delete a Species node and optionally its associated chunks."""
        if delete_chunks:
            query = """
            MATCH (s:Species {scientific_name: $scientific_name})
            OPTIONAL MATCH (s)-[:HAS_CHUNK]->(c:Chunk)
            DETACH DELETE s, c
            """
        else:
            query = """
            MATCH (s:Species {scientific_name: $scientific_name})
            DETACH DELETE s
            """
        with self.driver.session() as session:
            session.run(query, scientific_name=scientific_name)
