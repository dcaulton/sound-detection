import logging
from typing import Any

import ollama
from neo4j import Driver

from .retriever import Retriever

logger = logging.getLogger(__name__)


class RAGEnricher:
    """
    RAG-based enrichment.
    Retrieves relevant chunks from the vector store and uses them as context for the LLM.
    """

    def __init__(self, driver: Driver, model: str | None = None) -> None:
        self.retriever = Retriever(driver)
        self.model = model or "qwen2.5:32b"

    def enrich(
        self,
        scientific_name: str,
        base_data: dict[str, Any] | None = None,
        extra_instructions: str | None = None,
        top_k: int = 6,
    ) -> dict[str, Any]:
        """
        Enrich a species using retrieved context from the knowledge base.
        """
        if base_data is None:
            base_data = {"scientific_name": scientific_name}

        # Retrieve relevant chunks
        chunks = self.retriever.retrieve(
            scientific_name=scientific_name,
            query=extra_instructions or f"Key information about {scientific_name}",
            top_k=top_k,
        )

        context_text = "\n\n".join([c["text"] for c in chunks]) if chunks else ""

        prompt = self._build_prompt(base_data, context_text, extra_instructions)

        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={"temperature": 0.3},
            )
            import json

            enriched = json.loads(response["message"]["content"])
            return {**base_data, **enriched, "retrieved_chunks": len(chunks)}

        except Exception as e:
            logger.warning(f"RAG enrichment failed for {scientific_name}: {e}")
            return base_data

    def _build_prompt(self, base_data: dict, context_text: str, extra_instructions: str | None) -> str:
        prompt = f"""You are an expert ecologist with access to detailed species information.

Base data:
{base_data}

Relevant retrieved context:
{context_text}
"""
        if extra_instructions:
            prompt += f"\nAdditional focus areas: {extra_instructions}\n"

        prompt += """
Using the retrieved context above, enrich the species data. Respond with valid JSON only:

{
  "diet_description": string or null,
  "is_pollinator": boolean,
  "primary_habitat": string or null,
  "interesting_facts": string or null,
  "dietary_specialization": string or null
}
"""
        return prompt
