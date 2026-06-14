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

        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: list[dict[str, Any]] = []
        current_chunk: list[str] = []
        current_length = 0

        for sentence in sentences:
            sentence_length = len(sentence)

            if current_length + sentence_length > self.max_chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunks.append({"text": chunk_text, "source": source, "chunk_index": len(chunks)})
                current_chunk = [sentence]
                current_length = sentence_length
            else:
                current_chunk.append(sentence)
                current_length += sentence_length

        # Add the last chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append({"text": chunk_text, "source": source, "chunk_index": len(chunks)})

        return chunks
