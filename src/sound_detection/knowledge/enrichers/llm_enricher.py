import logging
import os
from typing import Any

import ollama

logger = logging.getLogger(__name__)


class LLMEnricher:
    """
    Handles LLM enrichment with support for Primary/Fallback models + hosts.
    Also supports Spotlight mode with additional instructions.
    """

    def __init__(self) -> None:
        self.primary_host = os.getenv("OLLAMA_PRIMARY_HOST", "http://localhost:11434")
        self.primary_model = os.getenv("OLLAMA_PRIMARY_MODEL", "qwen2.5:32b")

        self.fallback_host = os.getenv("OLLAMA_FALLBACK_HOST", "http://localhost:11434")
        self.fallback_model = os.getenv("OLLAMA_FALLBACK_MODEL", "qwen2.5:14b")

    def enrich(self, base_data: dict[str, Any], extra_instructions: str | None = None) -> dict[str, Any]:
        """
        Main enrichment method.
        - Tries primary model/host first.
        - Falls back to fallback model/host if primary fails.
        - Supports extra instructions (used by Spotlight mode).
        """
        scientific_name = base_data.get("scientific_name", "unknown")

        # Try primary
        result = self._call_ollama(
            base_data=base_data, host=self.primary_host, model=self.primary_model, extra_instructions=extra_instructions
        )
        if result:
            return result

        # Fallback
        logger.warning(f"Primary model failed. Falling back to {self.fallback_model} on {self.fallback_host}")
        result = self._call_ollama(
            base_data=base_data,
            host=self.fallback_host,
            model=self.fallback_model,
            extra_instructions=extra_instructions,
        )
        if result:
            return result

        logger.error(f"LLM enrichment failed for {scientific_name}")
        return base_data

    def _call_ollama(
        self, base_data: dict[str, Any], host: str, model: str, extra_instructions: str | None = None
    ) -> dict[str, Any] | None:
        os.environ["OLLAMA_HOST"] = host

        prompt = self._build_prompt(base_data, extra_instructions)
        logger.warning(f"calling ollama with this prompt: {prompt}")

        try:
            response = ollama.chat(
                model=model, messages=[{"role": "user", "content": prompt}], format="json", options={"temperature": 0.3}
            )
            import json

            enriched = json.loads(response["message"]["content"])
            logger.warning(f"ollama response: {enriched}")
            return {**base_data, **enriched}

        except Exception as e:
            logger.error(f"Ollama call failed on {host} with {model}: {e}")
            return None

    def _build_prompt(self, base_data: dict[str, Any], extra_instructions: str | None) -> str:
        scientific_name = base_data.get("scientific_name", "unknown species")

        prompt = f"""You are an expert ecologist. Enrich the following species information.

Species: {scientific_name}
Base data: {base_data}
"""
        if extra_instructions and extra_instructions != "string":
            prompt += f"\nAdditional focus: {extra_instructions}\n"

        prompt += """
Respond with valid JSON containing at these fields:
{
  "diet_description": string or null,
  "is_pollinator": boolean,
  "primary_habitat": string or null,
  "interesting_facts": string or null,
  "dietary_specialization": string or null
}
"""
        return prompt
