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


class _FakeSession:
    """Just enough AsyncSession for a dry run — no database required.

    A dry run only ever needs to load the job row and persist the report, so the
    fake records commits (that is how we assert the payload is actually saved)
    and hands the same model instance back for the lookup.
    """

    def __init__(self, summary: BiomeSummary) -> None:
        self._summary = summary
        self.commits = 0

    async def get(self, _model: object, _pk: object) -> BiomeSummary:
        return self._summary

    async def commit(self) -> None:
        self.commits += 1


def _detached_service(summary: BiomeSummary) -> BiomeSummaryService:
    service = BiomeSummaryService.__new__(BiomeSummaryService)
    service.session = _FakeSession(summary)  # type: ignore[assignment]
    service.neo4j_driver = None
    service.species_service = None
    service.retriever = None
    return service


def _filter_report() -> dict:
    return {
        "total_candidates": 2,
        "kept": {"confirmed": 1, "speculated": 0, "total": 1},
        "dropped": {"confirmed": 1, "speculated": 0, "total": 1},
        "dropped_by_reason": {"confirmed": {"non_species_label": 1}, "speculated": {}},
        "dropped_samples": {
            "confirmed": [{"scientific_name": "dog", "count": 9, "reason": "non_species_label"}],
            "speculated": [],
        },
    }


def _never(label: str) -> MagicMock:
    def _explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(f"{label} ran during a dry run")

    return MagicMock(side_effect=_explode)


@pytest.mark.asyncio
async def test_dry_run_stores_filter_report_and_skips_enrichment_and_narrative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = BiomeSummary(
        id=uuid4(),
        site_id=uuid4(),
        window_days=30,
        status="pending",
        criteria={"confirmation": {"min_signals": 2}, "_dry_run": True},
    )
    service = _detached_service(summary)

    report = _filter_report()
    gather = AsyncMock(
        return_value=(
            {"Turdus migratorius": 3},
            {},
            [{"scientific_name": "Turdus migratorius", "count": 3, "confirmation": "confirmed", "context": {}}],
            [],
            report,
        )
    )
    service._gather_and_filter_species = gather  # type: ignore[method-assign]

    # Everything downstream of Phase 1 must stay untouched in a dry run.
    service._enrich_species = AsyncMock(side_effect=AssertionError("enrichment ran in a dry run"))  # type: ignore[method-assign]
    service._build_species_enrichment_chain = _never("species enrichment chain")  # type: ignore[method-assign]
    service._build_narrative_chain = _never("narrative chain")  # type: ignore[method-assign]
    service._build_human_narrative_chain = _never("human narrative chain")  # type: ignore[method-assign]

    def _no_inaturalist(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("iNaturalist was contacted during a dry run")

    monkeypatch.setattr(
        "sound_detection.knowledge.harvesters.inaturalist.InaturalistHarvester",
        _no_inaturalist,
    )

    await service.generate_summary(summary.id)

    assert summary.status == "dry_run_complete"
    payload = summary.summary_json
    assert payload is not None
    assert payload["dry_run"] is True
    assert payload["summary_id"] == str(summary.id)
    assert payload["site_id"] == str(summary.site_id)
    assert payload["window_days"] == 30
    # Internal run keys are storage only; the payload documents them publicly.
    assert payload["criteria"]["dry_run"] is True
    assert "_dry_run" not in payload["criteria"]
    assert payload["filter_report"] == report
    assert "generated_at" in payload
    assert summary.narrative is None
    # The report has to survive the request, so it must be committed.
    assert service.session.commits >= 1  # type: ignore[attr-defined]

    gather.assert_awaited_once()
    assert gather.await_args is not None
    assert gather.await_args.kwargs["dry_run"] is True
    service._enrich_species.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_dry_run_flag_is_read_from_criteria_and_phase_one_is_told() -> None:
    summary = BiomeSummary(id=uuid4(), site_id=uuid4(), window_days=7, status="pending", criteria={"_dry_run": True})
    service = _detached_service(summary)
    service._gather_and_filter_species = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            {},
            {"Cathartes aura": 1},
            [],
            [{"scientific_name": "Cathartes aura", "count": 1, "confirmation": "speculated", "context": {}}],
            {
                "total_candidates": 1,
                "kept": {"confirmed": 0, "speculated": 1, "total": 1},
                "dropped": {"confirmed": 0, "speculated": 0, "total": 0},
                "dropped_by_reason": {"confirmed": {}, "speculated": {}},
                "dropped_samples": {"confirmed": [], "speculated": []},
            },
        )
    )

    await service.generate_summary(summary.id)

    assert summary.status == "dry_run_complete"
    payload = summary.summary_json
    assert payload is not None
    # The public payload renames the internal key; nothing else is invented.
    assert payload["criteria"] == {"dry_run": True}
    assert payload["filter_report"]["kept"]["speculated"] == 1


@pytest.mark.asyncio
async def test_full_run_does_not_take_the_dry_run_exit() -> None:
    summary = BiomeSummary(id=uuid4(), site_id=uuid4(), window_days=30, status="pending", criteria=None)
    service = _detached_service(summary)
    service._gather_and_filter_species = AsyncMock(side_effect=RuntimeError("phase 2 reached"))  # type: ignore[method-assign]

    await service.generate_summary(summary.id)

    gather = service._gather_and_filter_species
    assert isinstance(gather, AsyncMock)
    assert gather.await_args is not None
    # Phase 1 is told this is a real run, and the job did not stop at the report.
    assert gather.await_args.kwargs["dry_run"] is False
    assert summary.status != "dry_run_complete"
    assert summary.summary_json is None
