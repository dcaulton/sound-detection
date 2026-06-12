import logging
from typing import Any

import ollama

logger = logging.getLogger(__name__)


class LLMEnricher:
    """
    Uses a local LLM (via Ollama) to enrich species data with ecological context.
    Runs at seed time when a new species is first detected.
    """

    def __init__(self, model: str = "llama3.1") -> None:
        self.model = model

    def enrich(self, base_data: dict[str, Any]) -> dict[str, Any]:
        """
        Takes harvested data and adds LLM-generated fields such as:
        - Diet and foraging behavior
        - Pollinator status
        - Interesting ecological facts
        - Habitat preferences
        """
        scientific_name = base_data.get("scientific_name", "unknown species")

        prompt = f"""You are an expert ecologist. Given the following information about {scientific_name}, 
provide structured enrichment data. Respond ONLY with valid JSON.

Base data:
{base_data}

Please add the following fields if relevant:
- diet_description (string)
- is_pollinator (boolean)
- primary_habitat (string)
- interesting_facts (string, 1-2 sentences)
- dietary_specialization (string or null)

Return only the JSON object."""

        try:
            response = ollama.chat(model=self.model, messages=[{"role": "user", "content": prompt}], format="json")
            enriched = response["message"]["content"]
            # Merge LLM output with original data
            import json

            llm_data = json.loads(enriched)
            return {**base_data, **llm_data}

        except Exception as e:
            logger.warning(f"LLM enrichment failed for {scientific_name}: {e}")
            return base_data
