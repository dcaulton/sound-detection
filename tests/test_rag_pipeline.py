from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from neo4j import Driver

from sound_detection.knowledge.rag.pipeline import RAGPipeline
from sound_detection.knowledge.rag.retriever import Retriever


@pytest.fixture
def rag_pipeline(neo4j_driver: Driver) -> RAGPipeline:
    return RAGPipeline(neo4j_driver)


@patch("sound_detection.knowledge.rag.pipeline.WikipediaSource")
def test_rag_ingestion_and_retrieval(
    mock_wikipedia: MagicMock, rag_pipeline: RAGPipeline, neo4j_driver: Driver
) -> None:
    scientific_name = "Turdus migratorius"

    # Mock Wikipedia to return fixed content
    mock_instance: MagicMock = mock_wikipedia.return_value
    mock_instance.fetch_species_text.return_value = (
        "The American Robin (Turdus migratorius) is a migratory songbird. "
        "It is known for its bright orange breast and cheerful song. "
        "Robins primarily eat earthworms and insects but also consume fruits and berries."
    )

    # Force re-ingestion
    ingested: bool = rag_pipeline.ingest_species(scientific_name, force=True)
    assert ingested is True

    # Verify retrieval works
    retriever = Retriever(neo4j_driver)
    chunks: list[dict[str, Any]] = retriever.retrieve(scientific_name, top_k=5)

    assert len(chunks) > 0
    assert any("robin" in chunk["text"].lower() for chunk in chunks)
