import logging

from neo4j import Driver

from .chunking.semantic_chunker import SemanticChunker
from .embedding import EmbeddingModel
from .ingestion.wikipedia import WikipediaSource
from .vector_store import Neo4jVectorStore

logger = logging.getLogger(__name__)


class RAGPipeline:
    """Handles ingestion of species text into the Neo4j vector store."""

    def __init__(self, driver: Driver) -> None:
        self.driver = driver
        self.wikipedia = WikipediaSource()
        self.chunker = SemanticChunker(EmbeddingModel())
        self.vector_store = Neo4jVectorStore(driver)

    def ingest_species(self, scientific_name: str, force: bool = False) -> bool:
        """
        Ingests text for a species into the vector store.

        Args:
            scientific_name: The scientific name of the species.
            force: If True, re-ingest even if data already exists.

        Returns:
            True if ingestion occurred, False if skipped.
        """
        if not force:
            # Check if chunks already exist using a normal MATCH (not vector search)
            query = """
            MATCH (s:Species {scientific_name: $scientific_name})-[:HAS_CHUNK]->(c:Chunk)
            RETURN count(c) > 0 AS has_chunks
            """
            with self.driver.session() as session:
                result = session.run(query, scientific_name=scientific_name)
                record = result.single()
                if record and record["has_chunks"]:
                    logger.warning(f"Species already ingested: {scientific_name}. Skipping.")
                    return False

        # Fetch text from Wikipedia
        text = self.wikipedia.fetch_species_text(scientific_name)
        if not text or len(text.strip()) < 50:
            logger.warning(f"No useful text found for {scientific_name}")
            return False

        # Chunk the text
        chunks = self.chunker.chunk(text, source="wikipedia")
        if not chunks:
            logger.warning(f"No chunks generated for {scientific_name}")
            return False

        # Embed chunks
        for chunk in chunks:
            chunk["embedding"] = self.chunker.embedding_model.embed(chunk["text"])

        # Store in Neo4j
        self.vector_store.add_chunks(scientific_name, chunks)
        logger.warning(f"Ingested {len(chunks)} chunks for {scientific_name}")
        return True
