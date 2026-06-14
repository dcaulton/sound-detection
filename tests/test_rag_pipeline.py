from typing import Any
from unittest.mock import MagicMock, patch

from neo4j import Driver

from sound_detection.knowledge.rag.pipeline import RAGPipeline
from sound_detection.knowledge.rag.retriever import Retriever


@patch("sound_detection.knowledge.rag.pipeline.WikipediaSource")
@patch("ollama.embeddings")
def test_rag_ingestion_and_retrieval(
    mock_ollama_embeddings: MagicMock,
    mock_wikipedia: MagicMock,
    neo4j_driver: Driver,
) -> None:
    scientific_name = "Turdus migratorius"

    # Mock Wikipedia
    mock_wiki_instance: MagicMock = mock_wikipedia.return_value
    mock_wiki_instance.fetch_species_text.return_value = (
        "The American Robin (Turdus migratorius) is a migratory songbird. "
        "It is known for its bright orange breast and cheerful song. "
        "Robins primarily eat earthworms and insects but also consume fruits and berries."
    )

    # Mock ollama.embeddings to return a dummy vector
    mock_ollama_embeddings.return_value = {"embedding": [0.1] * 768}

    # Create pipeline inside the test (after patches)
    rag_pipeline = RAGPipeline(neo4j_driver)

    # Force ingestion
    ingested: bool = rag_pipeline.ingest_species(scientific_name, force=True)
    assert ingested is True

    # Verify retrieval works
    retriever = Retriever(neo4j_driver)
    chunks: list[dict[str, Any]] = retriever.retrieve(scientific_name, top_k=5)

    assert len(chunks) > 0
