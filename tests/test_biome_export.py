"""Tests for biome document export helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from docx import Document

from sound_detection.knowledge.biome_export import (
    add_taxon_table,
    export_to_docx,
    get_species_image,
)


def test_add_taxon_table_empty() -> None:
    doc = Document()
    add_taxon_table(doc, [])
    texts = [p.text for p in doc.paragraphs]
    assert any("No taxons" in t for t in texts)
    assert len(doc.tables) == 0


def test_add_taxon_table_rows() -> None:
    doc = Document()
    rows: list[dict[str, Any]] = [
        {"common_name": "American Robin", "scientific_name": "Turdus migratorius", "count": 12, "score": 8.5},
        {"common_name": None, "scientific_name": "Sturnella magna", "count": 4, "score": 15.0},
    ]
    add_taxon_table(doc, rows)
    assert len(doc.tables) == 1
    table = doc.tables[0]
    assert table.rows[0].cells[0].text == "Common Name"
    assert table.rows[1].cells[1].text == "Turdus migratorius"
    assert table.rows[1].cells[2].text == "12"
    assert table.rows[2].cells[0].text == "—"


def test_export_to_docx_basic() -> None:
    summary = {
        "site_id": "abc-123",
        "window_days": 7,
        "created_at": "2026-11-01T12:00:00",
        "human_narrative": "Overall the soundscape was dominated by robins.\n\n## High interest\n\nA few meadowlarks.",
        "species_table": [
            {"common_name": "American Robin", "scientific_name": "Turdus migratorius", "count": 20, "score": 6.0},
        ],
        "notable_species_images": [],
    }
    path = export_to_docx(summary)
    assert path.exists()
    assert path.suffix == ".docx"

    doc = Document(str(path))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Biome Summary Report" in full_text
    assert "abc-123" in full_text
    assert "Last 7 days" in full_text
    assert "Overall the soundscape" in full_text
    assert len(doc.tables) == 1
    path.unlink(missing_ok=True)


def test_get_species_image_success() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"thumbnail": {"source": "https://example.com/robin.jpg"}}

    with patch("sound_detection.knowledge.biome_export.requests.get", return_value=mock_resp) as mock_get:
        url = get_species_image("Turdus migratorius")

    assert url == "https://example.com/robin.jpg"
    called_url = mock_get.call_args[0][0]
    assert "Turdus_migratorius" in called_url


def test_get_species_image_failure() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("sound_detection.knowledge.biome_export.requests.get", return_value=mock_resp):
        assert get_species_image("Not a real species") is None
