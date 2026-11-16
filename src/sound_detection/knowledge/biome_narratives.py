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
    3. Rare or unexpected species (far from known iNat range, or otherwise notable)
    4. Familiar residents - species seen often in the prior window and known from 
      Illinois. One short paragraph: they were here, they are always here. 
      Do not dwell.
    5. Brief ecological observations and closing
    6. Unconfirmed / single-analyzer detections (brief, cautious)

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

    Familiar residents (always here; mention briefly):
    {expected_text}

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


def format_species_with_insights(
    rows: list[ScoredTaxon],
    insights: dict[str, str],
    limit: int = 8,
) -> str:
    """Bullet list that includes the per-species enrichment paragraph."""
    parts = []
    for r in rows[:limit]:
        common = r["common_name"] or ""
        name = r["scientific_name"]
        label = f"{common} (*{name}*)" if common else f"*{name}*"
        parts.append(f"- {label}: {r['count']} events (score {r['score']})")
        insight = insights.get(name)
        if insight:
            parts.append(f"  Insight: {insight}")
    return "\n".join(parts) if parts else "None"


def format_count_table(rows: list[ScoredTaxon]) -> str:
    """Markdown table of name and event count. Score is internal and omitted."""
    if not rows:
        return "_None_"
    lines = [
        "| Common name | Scientific name | Events |",
        "|---|---|---|",
    ]
    for r in rows:
        common = r["common_name"] or "—"
        lines.append(f"| {common} | {r['scientific_name']} | {r['count']} |")
    return "\n".join(lines)


def criteria_note(text: str) -> str:
    """Italic criteria line placed under a section header."""
    return f"*{text}*"


def build_interest_chain() -> Runnable:
    prompt = ChatPromptTemplate.from_template(
        """You are an experienced field naturalist writing for a homeowner or land steward.

Write the body of the **High-interest and indicator species** section. No heading.

Aim for 500-700 words. Give each species room. Draw on the Insight under each
name: range, season, habitat, behavior, what its presence says about the site.
Use both common and scientific names. Do not invent facts that are not in the
insights. Do not repeat the selection criteria; they are added separately.

Species:
{interest_text}

Section body:"""
    )
    return prompt | llm | StrOutputParser()


def build_rare_chain() -> Runnable:
    prompt = ChatPromptTemplate.from_template(
        """You are an experienced field naturalist writing for a homeowner or land steward.

Write the body of the **Rare or unexpected** section. No heading.

Aim for 400-600 words. These species were heard by both models and iNaturalist
does not place them nearby. Explain why each is notable, using the insights.
If the list is empty, say so in one sentence.

Species:
{rare_text}

Section body:"""
    )
    return prompt | llm | StrOutputParser()


def build_soundscape_chain() -> Runnable:
    prompt = ChatPromptTemplate.from_template(
        """You are an experienced field naturalist writing for a homeowner or land steward.

Write the body of the **Overall soundscape** section. No heading. 350-500 words.

What was common and dominant, the character of the soundscape, and the seasonal
context. Use the insights. Do not restate counts as the whole point.

Dominant species:
{dominant_text}

Section body:"""
    )
    return prompt | llm | StrOutputParser()


def build_familiar_chain() -> Runnable:
    prompt = ChatPromptTemplate.from_template(
        """You are an experienced field naturalist writing for a homeowner or land steward.

Write a short body for the **Familiar residents** section. No heading. 150-250 words.

These species had many detections in the prior window and a nearby iNaturalist
record. Mention a few by name and say they are the regulars. A complete table
is appended separately; do not try to list every species.

Residents:
{expected_text}

Section body:"""
    )
    return prompt | llm | StrOutputParser()


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

    insights: dict[str, str] = {}
    for sp in enriched_confirmed_species + enriched_speculated_species:
        if sp.get("llm_insight"):
            insights[sp["scientific_name"]] = sp["llm_insight"]

    unexpected_names = {
        sp["scientific_name"] for sp in enriched_confirmed_species + enriched_speculated_species if sp.get("unexpected")
    }
    expected_names = {
        sp["scientific_name"]
        for sp in enriched_confirmed_species + enriched_speculated_species
        if sp.get("expected_here") and float((sp.get("context") or {}).get("interest_weight") or 1.0) <= 1.0
    }

    all_scored = {s["scientific_name"]: s for s in buckets["table_rows"]}
    unexpected_rows = [all_scored[n] for n in unexpected_names if n in all_scored]
    expected_rows = [all_scored[n] for n in expected_names if n in all_scored]
    expected_rows.sort(key=lambda s: s["count"], reverse=True)

    high_interest_rows = [s for s in buckets["high_interest"] if s["scientific_name"] not in expected_names]
    # Full set for the table: every non-familiar species at the score cap, by count.
    # The [:12] bucket is only what the prose sees; the table is the whole cut.
    interest_table_rows = [
        s for s in buckets["table_rows"] if s["score"] >= 12 and s["scientific_name"] not in expected_names
    ]
    interest_table_rows.sort(key=lambda s: s["count"], reverse=True)
    rare_rows = unexpected_rows or [s for s in buckets["rare_vagrant"] if s["scientific_name"] not in expected_names]

    high_interest_text = format_species_with_insights(high_interest_rows, insights, limit=10)
    dominant_text = format_species_with_insights(buckets["dominant"], insights)
    rare_text = format_species_with_insights(rare_rows, insights, limit=10)
    expected_text = format_species_list(expected_rows, limit=12)
    expected_table = format_count_table(expected_rows)
    interest_table = format_count_table(interest_table_rows)
    rare_table = format_count_table(sorted(rare_rows, key=lambda s: s["count"], reverse=True))
    speculated_text = format_species_list(
        speculated_buckets["high_interest"] or speculated_buckets["dominant"],
        limit=6,
    )

    prox = criteria.get("proximity") or {}
    exp = criteria.get("expected") or {}
    near_mi = prox.get("radius_miles", 100)
    far_mi = prox.get("far_miles", 500)
    prior_days = exp.get("prior_days", 60)
    prior_min = exp.get("min_count", 50)

    prompt_vars = {
        "window_days": window_days,
        "total_confirmed_species": len(confirmed_counts),
        "total_speculated_species": len(speculated_counts),
        "high_interest_text": high_interest_text,
        "interest_text": high_interest_text,
        "dominant_text": dominant_text,
        "rare_text": rare_text,
        "expected_text": expected_text,
        "speculated_text": speculated_text,
    }

    machine_chain = machine_chain or build_narrative_chain()
    machine_narrative = await machine_chain.ainvoke(prompt_vars)

    if human_chain is not None:
        human_narrative = await human_chain.ainvoke(prompt_vars)
    else:
        soundscape = await build_soundscape_chain().ainvoke(prompt_vars)
        interest = await build_interest_chain().ainvoke(prompt_vars)
        rare = await build_rare_chain().ainvoke(prompt_vars)
        familiar = await build_familiar_chain().ainvoke(prompt_vars)
        human_narrative = "\n\n".join(
            [
                "## Overall soundscape\n\n"
                + criteria_note(
                    f"Most frequently detected species in the last {window_days} days. Counts are BirdNET plus Perch."
                )
                + "\n\n"
                + soundscape.strip(),
                "## High-interest and indicator species\n\n"
                + criteria_note(
                    "Highest interest score, or a clade given an interest weight above 1.0 "
                    "in the request. Familiar residents are excluded unless elevated."
                )
                + "\n\n"
                + interest.strip()
                + "\n\n"
                + interest_table,
                "## Rare or unexpected\n\n"
                + criteria_note(
                    f"Both BirdNET and Perch detected the species, and iNaturalist has no "
                    f"observation within {near_mi} miles (or the nearest is {far_mi}+ miles). "
                    "A missing iNat record is treated as not local."
                )
                + "\n\n"
                + rare.strip()
                + "\n\n"
                + rare_table,
                "## Familiar residents\n\n"
                + criteria_note(
                    f"At least {prior_min} detections in the {prior_days} days before this window "
                    f"at this site, and a nearest iNaturalist observation within {near_mi} miles."
                )
                + "\n\n"
                + familiar.strip()
                + "\n\n"
                + expected_table,
            ]
        )

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
