import logging
from typing import Any

from neo4j import Driver

logger = logging.getLogger(__name__)


class Neo4jVectorStore:
    """Handles vector storage and retrieval in Neo4j."""

    def __init__(self, driver: Driver, index_name: str = "species_chunks") -> None:
        self.driver = driver
        self.index_name = index_name
        self._ensure_vector_index()

    def _ensure_vector_index(self) -> None:
        """Create the vector index if it doesn't exist."""
        query = f"""
        CREATE VECTOR INDEX {self.index_name} IF NOT EXISTS
        FOR (c:Chunk)
        ON c.embedding
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: 768,
            `vector.similarity_function`: 'cosine'
        }}}}
        """
        with self.driver.session() as session:
            session.run(query)
            logger.info(f"Vector index '{self.index_name}' ensured.")

    def add_chunks(self, chunks: list[dict[str, Any]], scientific_name: str | None = None) -> None:
        if scientific_name:
            query = """
            MERGE (s:Species {scientific_name: $scientific_name})
            WITH s
            UNWIND $chunks AS chunk
            CREATE (c:Chunk {
                text: chunk.text,
                embedding: chunk.embedding,
                source: chunk.source,
                chunk_index: chunk.chunk_index
            })
            CREATE (s)-[:HAS_CHUNK]->(c)
            """
            params: dict[str, Any] = {"scientific_name": scientific_name, "chunks": chunks}
        else:
            # General knowledge chunks (not linked to a species)
            query = """
            UNWIND $chunks AS chunk
            CREATE (c:Chunk {
                text: chunk.text,
                embedding: chunk.embedding,
                source: chunk.source,
                chunk_index: chunk.chunk_index
            })
            """
            params = {"chunks": chunks}

        with self.driver.session() as session:
            session.run(query, **params)

    def search(self, scientific_name: str, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Retrieve the most relevant chunks for a species."""
        query = f"""
        MATCH (s:Species {{scientific_name: $scientific_name}})-[:HAS_CHUNK]->(c:Chunk)
        CALL db.index.vector.queryNodes('{self.index_name}', $top_k, $query_embedding)
        YIELD node AS chunk, score
        WHERE chunk.scientific_name = $scientific_name   // safety filter
        RETURN chunk.text AS text, 
               chunk.source AS source, 
               score
        ORDER BY score DESC
        """
        with self.driver.session() as session:
            result = session.run(query, scientific_name=scientific_name, query_embedding=query_embedding, top_k=top_k)
            return [dict(record) for record in result]
