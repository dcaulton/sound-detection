import re
from typing import Any

from ..embedding import EmbeddingModel


class SemanticChunker:
    """
    Simple semantic chunker.
    Splits text into sentences, then merges them into chunks based on semantic similarity.
    """

    def __init__(self, embedding_model: EmbeddingModel, max_chunk_size: int = 800) -> None:
        self.embedding_model = embedding_model
        self.max_chunk_size = max_chunk_size

    def chunk(self, text: str, source: str = "wikipedia") -> list[dict[str, Any]]:
        if not text or len(text.strip()) < 50:
            return []

        # Split into sentences first
        sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: list[dict[str, Any]] = []
        current_chunk: list[str] = []
        current_length = 0
        max_size = self.max_chunk_size

        for sentence in sentences:
            if current_length + len(sentence) > max_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunks.append({"text": chunk_text, "source": source, "chunk_index": len(chunks)})
                current_chunk = []
                current_length = 0

            # If a single sentence is still too long, hard-split it
            while len(sentence) > max_size:
                chunks.append({"text": sentence[:max_size], "source": source, "chunk_index": len(chunks)})
                sentence = sentence[max_size:]

            current_chunk.append(sentence)
            current_length += len(sentence)

        if current_chunk:
            chunks.append({"text": " ".join(current_chunk), "source": source, "chunk_index": len(chunks)})

        return chunks
