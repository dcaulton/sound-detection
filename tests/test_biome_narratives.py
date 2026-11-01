"""Tests for narrative generation helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sound_detection.knowledge.biome_narratives import (
    enrich_species,
    format_species_list,
    generate_narratives,
)
from sound_detection.knowledge.scoring import ScoredTaxon


def test_format_species_list_empty() -> None:
    assert format_species_list([]) == "None"


def test_format_species_list_basic() -> None:
    rows: list[ScoredTaxon] = [
        {
            "scientific_name": "Turdus migratorius",
            "common_name": "American Robin",
            "count": 12,
            "score": 8.5,
            "clade": None,
            "context": {},
        },
        {
            "scientific_name": "Sturnella magna",
            "common_name": "",
            "count": 3,
            "score": 14.0,
            "clade": None,
            "context": {},
        },
    ]
    text = format_species_list(rows, limit=8)
    assert "American Robin (*Turdus migratorius*)" in text
    assert "*Sturnella magna*" in text
    assert "12 events" in text
    assert "score 14.0" in text


@pytest.mark.asyncio
async def test_enrich_species_no_retriever() -> None:
    species = [{"scientific_name": "Turdus migratorius", "count": 5, "context": {}}]
    result = await enrich_species("sum-1", species, 7, retriever=None)
    assert result == species


@pytest.mark.asyncio
async def test_enrich_species_success() -> None:
    retriever = MagicMock()
    retriever.retrieve.return_value = [{"text": "Robin is a common thrush."}]

    chain = AsyncMock()
    chain.ainvoke.return_value = "This species is common and expected."

    species = [
        {
            "scientific_name": "Turdus migratorius",
            "count": 10,
            "context": {"common_name": "American Robin", "primary_habitat": "suburban"},
        }
    ]
    result = await enrich_species("sum-1", species, 7, retriever, chunks_per_species=5, chain=chain)

    assert len(result) == 1
    assert result[0]["llm_insight"] == "This species is common and expected."
    assert result[0]["chunks"][0]["text"].startswith("Robin")
    chain.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_enrich_species_llm_failure() -> None:
    retriever = MagicMock()
    retriever.retrieve.return_value = []

    chain = AsyncMock()
    chain.ainvoke.side_effect = RuntimeError("ollama down")

    species = [{"scientific_name": "Turdus migratorius", "count": 2, "context": {}}]
    result = await enrich_species("sum-1", species, 1, retriever, chain=chain)

    assert result[0]["llm_insight"] is None


@pytest.mark.asyncio
async def test_generate_narratives_with_mocked_chains() -> None:
    machine = AsyncMock()
    machine.ainvoke.return_value = "Machine narrative text."
    human = AsyncMock()
    human.ainvoke.return_value = "Human narrative text."

    confirmed = {"Turdus migratorius": 15, "Sturnella magna": 4}
    speculated = {"Cathartes aura": 1}
    enriched_confirmed = [
        {
            "scientific_name": "Turdus migratorius",
            "count": 15,
            "context": {"common_name": "American Robin", "interest_weight": 1.0},
        }
    ]

    machine_n, human_n, _, table = await generate_narratives(
        summary_id="sum-1",
        confirmed_counts=confirmed,
        enriched_confirmed_species=enriched_confirmed,
        speculated_counts=speculated,
        enriched_speculated_species=[],
        window_days=7,
        criteria={"clades_of_interest": {}},
        neo4j_driver=None,
        machine_chain=machine,
        human_chain=human,
    )

    assert machine_n == "Machine narrative text."
    assert human_n == "Human narrative text."
    assert isinstance(table, list)
    # singles are dropped by bucket_taxa
    names = [r["scientific_name"] for r in table]
    assert "Turdus migratorius" in names
    machine.ainvoke.assert_awaited_once()
    human.ainvoke.assert_awaited_once()
    # prompt vars should mention the window
    called_vars: dict[str, Any] = machine.ainvoke.call_args[0][0]
    assert called_vars["window_days"] == 7
    assert "Robin" in called_vars["dominant_text"] or "Turdus" in called_vars["dominant_text"]
