import logging
import os
from typing import Any, cast

import ollama

logger = logging.getLogger(__name__)


class EmbeddingModel:
    """Handles embedding generation using Ollama."""

    def __init__(self, model: str | None = None) -> None:
        model_name: str = model or os.getenv("OLLAMA_EMBEDDING_MODEL") or "nomic-embed-text"
        self.model: str = model_name

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text chunk."""
        try:
            response: Any = ollama.embeddings(model=self.model, prompt=text)
            return cast(list[float], response["embedding"])
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return [self.embed(text) for text in texts]
