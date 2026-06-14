import logging
from typing import Any

from neo4j import Driver

from .embedding import EmbeddingModel

logger = logging.getLogger(__name__)


class Retriever:
    """Retrieves relevant text chunks for a species from the vector store."""

    def __init__(self, driver: Driver, index_name: str = "species_chunks") -> None:
        self.driver = driver
        self.index_name = index_name
        self.embedding_model = EmbeddingModel()

    def retrieve(self, scientific_name: str, query: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Retrieve the most relevant chunks for a species.
        If no query is provided, it uses the scientific name itself.
        """
        if query is None:
            query = f"Information about {scientific_name}"

        query_embedding = self.embedding_model.embed(query)

        cypher = f"""
        MATCH (s:Species {{scientific_name: $scientific_name}})-[:HAS_CHUNK]->(c:Chunk)
        CALL db.index.vector.queryNodes('{self.index_name}', $top_k, $query_embedding)
        YIELD node AS chunk, score
        RETURN chunk.text AS text,
               chunk.source AS source,
               score
        ORDER BY score DESC
        LIMIT $top_k
        """

        with self.driver.session() as session:
            result = session.run(cypher, scientific_name=scientific_name, query_embedding=query_embedding, top_k=top_k)
            chunks = [dict(record) for record in result]
            logger.info(f"Retrieved {len(chunks)} chunks for {scientific_name}")
            return chunks
