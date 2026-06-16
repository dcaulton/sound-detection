from unittest.mock import MagicMock, patch

import pytest
from neo4j import Driver

from sound_detection.knowledge.rag.pipeline import RAGPipeline


@pytest.fixture
def rag_pipeline(neo4j_driver: Driver) -> RAGPipeline:
    return RAGPipeline(neo4j_driver)


@patch("sound_detection.knowledge.rag.pipeline.PDFSource")
@patch("ollama.embeddings")
@patch("sound_detection.knowledge.rag.embedding.EmbeddingModel")
def test_ingest_pdf_without_species(
    mock_embedding: MagicMock,
    mock_ollama_embeddings: MagicMock,
    mock_pdf: MagicMock,
    neo4j_driver: Driver,
) -> None:
    # Mock PDF content
    mock_pdf_instance = mock_pdf.return_value
    mock_pdf_instance.fetch_species_text.return_value = (
        "This is a test PDF about midwest birds. It contains information about "
        "habitat, diet, and migration patterns of several species."
    )

    # Mock embeddings
    mock_ollama_embeddings.return_value = {"embedding": [0.1] * 768}
    mock_embedding.return_value.embed.return_value = [0.1] * 768

    # Create pipeline *inside* the test (after patches are active)
    rag_pipeline = RAGPipeline(neo4j_driver)

    success = rag_pipeline.ingest_pdf(
        file_path="/tmp/test.pdf",
        source_name="test_birds",
        scientific_name=None,
    )

    assert success is True


@patch("sound_detection.knowledge.rag.pipeline.PDFSource")
@patch("sound_detection.knowledge.rag.embedding.EmbeddingModel")
def test_link_and_unlink_chunk(
    mock_embedding: MagicMock,
    mock_pdf: MagicMock,
    rag_pipeline: RAGPipeline,
    neo4j_driver: Driver,
) -> None:
    mock_pdf_instance = mock_pdf.return_value
    mock_pdf_instance.fetch_species_text.return_value = "Test content about robins."

    mock_embed_instance = mock_embedding.return_value
    mock_embed_instance.embed.return_value = [0.1] * 768

    # Ingest with species
    rag_pipeline.ingest_pdf(file_path="/tmp/test.pdf", source_name="robin_pdf", scientific_name="Turdus migratorius")

    # Link a specific chunk
    rag_pipeline.link_chunk_to_species("Turdus migratorius", chunk_index=0, source_name="robin_pdf")

    # Unlink it
    rag_pipeline.unlink_chunks_from_species("Turdus migratorius", chunk_index=0)

    # Should not raise
    assert True
