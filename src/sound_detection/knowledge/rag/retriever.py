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

    def _vector_search(self, query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        cypher = f"""
        CALL db.index.vector.queryNodes('{self.index_name}', $top_k, $query_embedding)
        YIELD node AS chunk, score
        RETURN chunk.text AS text, chunk.source AS source, score
        ORDER BY score DESC
        LIMIT $top_k
        """
        with self.driver.session() as session:
            result = session.run(cypher, query_embedding=query_embedding, top_k=top_k)
            return [dict(record) for record in result]

    def _keyword_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        cypher = """
        CALL db.index.fulltext.queryNodes('chunk_text', $search_query)
        YIELD node AS chunk, score
        RETURN chunk.text AS text, chunk.source AS source, score
        ORDER BY score DESC
        LIMIT $top_k
        """
        with self.driver.session() as session:
            result = session.run(
                cypher,
                search_query=query,  # ← changed from query=query
                top_k=top_k,
            )
            return [{"text": r["text"], "source": r["source"], "keyword_score": r["score"]} for r in result]

    def hybrid_search(self, query: str, top_k: int = 10, keyword_weight: float = 0.4) -> list[dict[str, Any]]:
        """
        Hybrid search: vector similarity + keyword matching.
        Merging and scoring is done in Python.
        """
        query_embedding = self.embedding_model.embed(query)

        # 1. Vector search
        vector_results = self._vector_search(query_embedding, top_k * 2)

        # 2. Keyword search (fulltext)
        keyword_results = self._keyword_search(query, top_k * 2)

        # 3. Merge + deduplicate
        combined = {}

        # Process vector results
        for item in vector_results:
            key = item["text"]
            if key not in combined:
                combined[key] = {**item, "vector_score": item["score"], "keyword_score": 0.0}
            else:
                combined[key]["vector_score"] = item["score"]

        # Process keyword results
        for item in keyword_results:
            key = item["text"]
            if key not in combined:
                combined[key] = {**item, "vector_score": 0.0, "keyword_score": item["keyword_score"]}
            else:
                combined[key]["keyword_score"] = item["keyword_score"]

        # 4. Calculate hybrid score and sort
        results = []
        for item in combined.values():
            hybrid_score = item["vector_score"] * (1 - keyword_weight) + item["keyword_score"] * keyword_weight
            item["score"] = hybrid_score
            results.append(item)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
