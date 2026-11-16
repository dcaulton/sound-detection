from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.db.models import BiomeSummary, Site
from sound_detection.knowledge.biome_summary_service import BiomeSummaryService


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_generate_summary_happy_path(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    site = Site(id=uuid4(), name="Test Site")
    async_session.add(site)
    await async_session.commit()
    await async_session.refresh(site)

    summary = BiomeSummary(site_id=site.id, window_days=30, status="pending")
    async_session.add(summary)
    await async_session.commit()
    await async_session.refresh(summary)

    service = BiomeSummaryService(async_session, neo4j_driver=None)

    service.retriever = MagicMock()
    service.retriever.retrieve.return_value = [{"text": "Some context"}]

    mock_enrichment_chain = AsyncMock()
    mock_enrichment_chain.ainvoke.return_value = "This species is notable because of seasonal patterns."

    mock_narrative_chain = AsyncMock()
    mock_narrative_chain.ainvoke.return_value = (
        "This is a long, detailed generated narrative for the biome summary report."
    )

    mock_human_chain = AsyncMock()
    mock_human_chain.ainvoke.return_value = (
        "This is a human-readable markdown report with headings and a species table."
    )

    def _fake_chain(text: str) -> MagicMock:
        chain = AsyncMock()
        chain.ainvoke.return_value = text
        return MagicMock(return_value=chain)

    service._build_species_enrichment_chain = MagicMock(return_value=mock_enrichment_chain)  # type: ignore[method-assign]
    service._build_narrative_chain = MagicMock(return_value=mock_narrative_chain)  # type: ignore[method-assign]
    service._build_human_narrative_chain = MagicMock(return_value=mock_human_chain)  # type: ignore[method-assign]

    monkeypatch.setattr(
        "sound_detection.knowledge.biome_narratives.build_soundscape_chain",
        _fake_chain("Soundscape body."),
    )
    monkeypatch.setattr(
        "sound_detection.knowledge.biome_narratives.build_interest_chain",
        _fake_chain("Interest body."),
    )
    monkeypatch.setattr(
        "sound_detection.knowledge.biome_narratives.build_rare_chain",
        _fake_chain("Rare body."),
    )
    monkeypatch.setattr(
        "sound_detection.knowledge.biome_narratives.build_familiar_chain",
        _fake_chain("Familiar body."),
    )

    await service.generate_summary(summary.id)

    await async_session.refresh(summary)

    assert summary.status == "completed"
    assert summary.narrative is not None
    assert len(summary.narrative) > 50
    assert summary.summary_json is not None
    assert "total_species" in summary.summary_json
    # Create a real Site first (FK requirement)
    site = Site(id=uuid4(), name="Test Site")
    async_session.add(site)
    await async_session.commit()
    await async_session.refresh(site)

    # Create BiomeSummary
    summary = BiomeSummary(site_id=site.id, window_days=30, status="pending")
    async_session.add(summary)
    await async_session.commit()
    await async_session.refresh(summary)

    service = BiomeSummaryService(async_session, neo4j_driver=None)

    # Mock retriever
    service.retriever = MagicMock()
    service.retriever.retrieve.return_value = [{"text": "Some context"}]

    mock_enrichment_chain = AsyncMock()
    mock_enrichment_chain.ainvoke.return_value = "This species is notable because of seasonal patterns."

    mock_narrative_chain = AsyncMock()
    mock_narrative_chain.ainvoke.return_value = (
        "This is a long, detailed generated narrative for the biome summary report."
    )

    service._build_species_enrichment_chain = MagicMock(return_value=mock_enrichment_chain)  # type: ignore[method-assign]
    service._build_narrative_chain = MagicMock(return_value=mock_narrative_chain)  # type: ignore[method-assign]

    # Section chains live in biome_narratives and call the real model unless patched.
    monkeypatch.setattr(
        "sound_detection.knowledge.biome_narratives.build_soundscape_chain",
        _fake_chain("Soundscape body."),
    )
    monkeypatch.setattr(
        "sound_detection.knowledge.biome_narratives.build_interest_chain",
        _fake_chain("Interest body."),
    )
    monkeypatch.setattr(
        "sound_detection.knowledge.biome_narratives.build_rare_chain",
        _fake_chain("Rare body."),
    )
    monkeypatch.setattr(
        "sound_detection.knowledge.biome_narratives.build_familiar_chain",
        _fake_chain("Familiar body."),
    )

    service._build_species_enrichment_chain = MagicMock(return_value=mock_enrichment_chain)  # type: ignore[method-assign]
    service._build_narrative_chain = MagicMock(return_value=mock_narrative_chain)  # type: ignore[method-assign]
    service._build_human_narrative_chain = MagicMock(return_value=mock_human_chain)  # type: ignore[method-assign]

    # Run
    await service.generate_summary(summary.id)

    # Assert
    await async_session.refresh(summary)

    assert summary.status == "completed"
    assert summary.narrative is not None
    assert len(summary.narrative) > 50
    assert summary.summary_json is not None
    assert "total_species" in summary.summary_json
