import logging
from typing import Any

from neo4j import Driver

from .chunking.semantic_chunker import SemanticChunker
from .embedding import EmbeddingModel
from .ingestion.pdf import PDFSource
from .ingestion.wikipedia import WikipediaSource
from .vector_store import Neo4jVectorStore

logger = logging.getLogger(__name__)

# Link one specific chunk to a species
# pipeline.link_chunk_to_species("Turdus migratorius", chunk_index=3, source_name="robin_study")

# Unlink one chunk
# pipeline.unlink_chunks_from_species("Turdus migratorius", chunk_index=3)

# Unlink a range of chunks
# pipeline.unlink_chunks_from_species("Turdus migratorius", start_index=5, end_index=12)

# Unlink all chunks from a source
# pipeline.unlink_chunks_from_species("Turdus migratorius", source_name="robin_study")


class RAGPipeline:
    """Handles ingestion of species text into the Neo4j vector store."""

    def __init__(self, driver: Driver) -> None:
        self.driver = driver
        self.wikipedia = WikipediaSource()
        self.chunker = SemanticChunker(EmbeddingModel(), max_chunk_size=600)
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
        self.vector_store.add_chunks(chunks, scientific_name=scientific_name)
        logger.warning(f"Ingested {len(chunks)} chunks for {scientific_name}")
        return True

    def ingest_pdf(
        self, file_path: str, source_name: str = "pdf", scientific_name: str | None = None, force: bool = False
    ) -> bool:
        pdf_source = PDFSource(file_path, source_name=source_name)
        text = pdf_source.fetch_species_text()

        if not text or len(text.strip()) < 100:
            return False

        chunks = self.chunker.chunk(text, source=source_name)
        if not chunks:
            return False

        for chunk in chunks:
            chunk["embedding"] = self.chunker.embedding_model.embed(chunk["text"])

        self.vector_store.add_chunks(chunks, scientific_name=scientific_name)
        return True

    def link_chunks_to_species(self, scientific_name: str, source_name: str | None = None) -> None:
        """Link existing chunks (by source) to a Species node after ingestion."""
        query = """
        MATCH (s:Species {scientific_name: $scientific_name})
        MATCH (c:Chunk)
        WHERE ($source_name IS NULL OR c.source = $source_name)
          AND NOT (s)-[:HAS_CHUNK]->(c)
        CREATE (s)-[:HAS_CHUNK]->(c)
        """
        with self.driver.session() as session:
            session.run(query, scientific_name=scientific_name, source_name=source_name)

    def link_chunk_to_species(
        self,
        scientific_name: str,
        chunk_index: int,
        source_name: str | None = None,
    ) -> None:
        """Link one specific chunk to a species."""
        query = """
        MATCH (s:Species {scientific_name: $scientific_name})
        MATCH (c:Chunk {chunk_index: $chunk_index})
        WHERE $source_name IS NULL OR c.source = $source_name
        MERGE (s)-[:HAS_CHUNK]->(c)
        """
        with self.driver.session() as session:
            session.run(query, scientific_name=scientific_name, chunk_index=chunk_index, source_name=source_name)

    def unlink_chunks_from_species(
        self,
        scientific_name: str,
        chunk_index: int | None = None,
        source_name: str | None = None,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> None:
        """
        Disassociate chunks from a species.
        - chunk_index: unlink one specific chunk
        - start_index + end_index: unlink a range
        - source_name: unlink all chunks from that source
        """
        conditions = []
        params: dict[str, Any] = {"scientific_name": scientific_name}

        if chunk_index is not None:
            conditions.append("c.chunk_index = $chunk_index")
            params["chunk_index"] = chunk_index
        elif start_index is not None and end_index is not None:
            conditions.append("c.chunk_index >= $start_index AND c.chunk_index <= $end_index")
            params["start_index"] = start_index
            params["end_index"] = end_index
        elif source_name is not None:
            conditions.append("c.source = $source_name")
            params["source_name"] = source_name

        where_clause = " AND ".join(conditions) if conditions else "true"

        query = f"""
        MATCH (s:Species {{scientific_name: $scientific_name}})-[r:HAS_CHUNK]->(c:Chunk)
        WHERE {where_clause}
        DELETE r
        """
        with self.driver.session() as session:
            session.run(query, **params)
