from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.db.models import BiomeSummary, Site
from sound_detection.knowledge.biome_summary_service import BiomeSummaryService


@pytest.mark.asyncio
async def test_generate_summary_happy_path(async_session: AsyncSession) -> None:
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

    # Correct way to mock LangChain-style chains
    mock_enrichment_chain = AsyncMock()
    mock_enrichment_chain.ainvoke.return_value = "This species is notable because of seasonal patterns."

    mock_narrative_chain = AsyncMock()
    mock_narrative_chain.ainvoke.return_value = (
        "This is a long, detailed generated narrative for the biome summary report."
    )

    service._build_species_enrichment_chain = MagicMock(return_value=mock_enrichment_chain)  # type: ignore[method-assign]
    service._build_narrative_chain = MagicMock(return_value=mock_narrative_chain)  # type: ignore[method-assign]

    # Run
    await service.generate_summary(summary.id)

    # Assert
    await async_session.refresh(summary)

    assert summary.status == "completed"
    assert summary.narrative is not None
    assert len(summary.narrative) > 50
    assert summary.summary_json is not None
    assert "total_species" in summary.summary_json
