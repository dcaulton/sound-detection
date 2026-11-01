"""Narrative generation and per-species enrichment for biome summaries.

Extracted from BiomeSummaryService. Owns the LLM chains, the RAG enrichment
loop, and the final machine/human narrative assembly.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_ollama import ChatOllama
from neo4j import Driver

from sound_detection.knowledge.biome_export import get_species_image
from sound_detection.knowledge.grading_criteria import get_interest_weight
from sound_detection.knowledge.scoring import ScoredTaxon, bucket_taxa
from sound_detection.knowledge.taxonomy import ancestry_names

log = structlog.get_logger(__name__)

llm = ChatOllama(model="qwen2.5:32b", temperature=0.3)


def build_species_enrichment_chain() -> Runnable:
    prompt = ChatPromptTemplate.from_template(
        """You are an expert ornithologist and ecologist analyzing bird observations.

    Species: {scientific_name} ({common_name})
    Detection count in the last {window_days} days: {count}

    Structured knowledge:
    - Recorded in Illinois: {recorded_in_illinois}
    - Primary habitat: {primary_habitat}
    - Diet: {diet_description}
    - Interesting facts: {interesting_facts}

    Relevant context from Wikipedia:
    {chunks_text}

    Task:
    Write a concise but insightful paragraph (3-6 sentences) that explains:
    - Why this species might be notable or unusual in this location right now
    - Any relevant seasonal, migratory, or ecological context
    - Interesting biological or behavioral details worth mentioning

    Be factual and avoid speculation. If the species is common and expected, say so briefly.
    """
    )
    return prompt | llm | StrOutputParser()


def build_narrative_chain() -> Runnable:
    prompt = ChatPromptTemplate.from_template(
        """You are an expert ornithologist and ecologist producing a concise, structured summary of 
           acoustic detections for downstream automated systems (Weathervane and similar tools).

Write a clear, information-dense report. Use short paragraphs and bullet points where helpful. Avoid fluff.

**Required content:**
- Overall activity level and the dominant (most frequently detected) species
- Any notable diversity in owls, raptors, or hummingbirds
- High-interest or indicator species that stand out
- Brief mention of rare or unexpected species
- One or two ecological observations worth tracking

**Important:**
- Treat CONFIRMED detections (BirdNET + Perch agreement) as reliable.
- Treat SPECULATED detections as possible only; do not lead with them.
- Prefer confirmed data for activity level, dominant species, and ecological claims.

Time window: last {window_days} days
Confirmed species: {total_confirmed_species}
Speculated (single-analyzer) species: {total_speculated_species}

Confirmed dominant:
{dominant_text}

Confirmed high-interest / indicator:
{high_interest_text}

Confirmed rare / unexpected:
{rare_text}

Speculated (mention cautiously):
{speculated_text}

Structured summary:"""
    )
    return prompt | llm | StrOutputParser()


def build_human_narrative_chain() -> Runnable:
    prompt = ChatPromptTemplate.from_template(
        """You are an experienced field naturalist writing a clear, engaging summary for a 
               homeowner or land steward.

    Write a well-structured markdown report using headings and short paragraphs.

    **Structure to follow:**
    1. Overall soundscape - what was actually common and dominant
    2. High-interest and indicator species
    3. Rare or unexpected species
    4. Brief ecological observations and closing
    5. Unconfirmed / single-analyzer detections (brief, cautious)

    **Important:**
    - Balance common/dominant species with rare and high-interest ones.
    - Use both common and scientific names.
    - Keep the tone knowledgeable but accessible. Aim for 700-1000 words.
    - Treat CONFIRMED detections (BirdNET + Perch agreement) as reliable.
    - Treat SPECULATED detections as possible only; do not lead with them.
    - Prefer confirmed data for activity level, dominant species, and ecological claims.

    **Data**
    Time window: last {window_days} days
    Confirmed species: {total_confirmed_species}
    Speculated (single-analyzer) species: {total_speculated_species}

    Confirmed dominant:
    {dominant_text}

    Confirmed high-interest / indicator:
    {high_interest_text}

    Confirmed rare / unexpected:
    {rare_text}

    Speculated (mention cautiously, if at all):
    {speculated_text}

    Human-readable report:"""
    )
    return prompt | llm | StrOutputParser()


def format_species_list(rows: list[ScoredTaxon], limit: int = 8) -> str:
    """Format scored taxa as a markdown bullet list for prompts."""
    parts = []
    for r in rows[:limit]:
        common = r["common_name"] or ""
        label = f"{common} (*{r['scientific_name']}*)" if common else f"*{r['scientific_name']}*"
        parts.append(f"- {label}: {r['count']} events (score {r['score']})")
    return "\n".join(parts) if parts else "None"


async def enrich_species(
    summary_id: Any,
    filtered_species: list[dict[str, Any]],
    window_days: int,
    retriever: Any,
    chunks_per_species: int = 10,
    chain: Runnable | None = None,
) -> list[dict[str, Any]]:
    """Run RAG + LLM enrichment for each species. Returns the enriched list."""
    if not retriever:
        log.warning("no_retriever", summary_id=str(summary_id))
        return filtered_species

    log.info("enriching_species", summary_id=str(summary_id), count=len(filtered_species))

    chain = chain or build_species_enrichment_chain()
    enriched: list[dict[str, Any]] = []

    for species in filtered_species:
        name = species["scientific_name"]
        count = species["count"]
        context = species.get("context", {})

        log.info("enriching_one", summary_id=str(summary_id), species=name, count=count)

        chunks = retriever.retrieve(name, top_k=chunks_per_species)

        chunks_text = (
            "\n\n".join(f"- {chunk.get('text', '')[:800]}" for chunk in chunks[:5])
            if chunks
            else "No additional context available."
        )

        try:
            insight = await chain.ainvoke(
                {
                    "scientific_name": name,
                    "common_name": context.get("common_name", name),
                    "window_days": window_days,
                    "count": count,
                    "recorded_in_illinois": context.get("recorded_in_illinois", False),
                    "primary_habitat": context.get("primary_habitat", "Unknown"),
                    "diet_description": context.get("diet_description", "Unknown"),
                    "interesting_facts": context.get("interesting_facts", "None available"),
                    "chunks_text": chunks_text,
                }
            )

            enriched.append(
                {
                    **species,
                    "chunks": chunks,
                    "llm_insight": insight.strip(),
                }
            )

        except Exception as e:
            log.warning("enrichment_failed", summary_id=str(summary_id), species=name, error=str(e))
            enriched.append(
                {
                    **species,
                    "chunks": chunks,
                    "llm_insight": None,
                }
            )

    log.info("enrichment_complete", summary_id=str(summary_id), enriched=len(enriched))
    return enriched


async def generate_narratives(
    summary_id: Any,
    confirmed_counts: dict[str, int],
    enriched_confirmed_species: list[dict[str, Any]],
    speculated_counts: dict[str, int],
    enriched_speculated_species: list[dict[str, Any]],
    window_days: int,
    criteria: dict[str, Any],
    neo4j_driver: Driver | None = None,
    machine_chain: Runnable | None = None,
    human_chain: Runnable | None = None,
) -> tuple[str, str, list[dict[str, Any]], list[ScoredTaxon]]:
    """
    Returns:
        (machine_narrative, human_narrative, notable_species_images, species_table)
    """
    log.info("generating_narratives", summary_id=str(summary_id))

    species_contexts: dict[str, dict[str, Any]] = {}
    for sp in enriched_confirmed_species + enriched_speculated_species:
        name = sp["scientific_name"]
        species_contexts[name] = sp.get("context") or {}

    for name in set(confirmed_counts) | set(speculated_counts):
        species_contexts.setdefault(name, {})

    if neo4j_driver is not None:
        for name, ctx in species_contexts.items():
            chain = ancestry_names(neo4j_driver, name)
            ctx["interest_weight"] = get_interest_weight(chain, criteria)
            ctx["ancestry"] = chain
            interest = criteria.get("clades_of_interest") or {}
            for clade in interest:
                if clade.lower() in {n.lower() for n in chain}:
                    ctx["matched_clade"] = clade
                    break

    buckets = bucket_taxa(confirmed_counts, species_contexts)
    speculated_buckets = bucket_taxa(speculated_counts, species_contexts)

    high_interest_text = format_species_list(buckets["high_interest"])
    dominant_text = format_species_list(buckets["dominant"])
    rare_text = format_species_list(buckets["rare_vagrant"])
    speculated_text = format_species_list(
        speculated_buckets["high_interest"] or speculated_buckets["dominant"],
        limit=6,
    )

    prompt_vars = {
        "window_days": window_days,
        "total_confirmed_species": len(confirmed_counts),
        "total_speculated_species": len(speculated_counts),
        "high_interest_text": high_interest_text,
        "dominant_text": dominant_text,
        "rare_text": rare_text,
        "speculated_text": speculated_text,
    }

    machine_chain = machine_chain or build_narrative_chain()
    machine_narrative = await machine_chain.ainvoke(prompt_vars)

    human_chain = human_chain or build_human_narrative_chain()
    human_narrative = await human_chain.ainvoke(prompt_vars)

    notable_species_images: list[dict[str, Any]] = []
    image_candidates: list[Any] = buckets["high_interest"] or buckets["dominant"]
    for sp in image_candidates[:5]:
        name = sp["scientific_name"]
        image_url = get_species_image(name)
        if image_url:
            notable_species_images.append(
                {
                    "scientific_name": name,
                    "common_name": sp.get("common_name"),
                    "count": sp["count"],
                    "confirmation": "confirmed",
                    "image_url": image_url,
                }
            )

    return (
        machine_narrative.strip(),
        human_narrative.strip(),
        notable_species_images,
        buckets["table_rows"],
    )
