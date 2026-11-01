"""Document assembly and image helpers for biome summaries.

Extracted from BiomeSummaryService so the service can stay focused on
orchestration. These functions take plain data (summary dicts, table rows)
and produce files or image URLs.
"""

from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
import structlog
from docx import Document
from docx.document import Document as DocumentObject
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from PIL import Image as PILImage
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.db.models import BiomeSummary
from sound_detection.knowledge.scoring import ScoredTaxon

log = structlog.get_logger(__name__)

USER_AGENT = "sound-detection/0.2 (https://github.com/dcaulton/sound-detection; bioacoustics research)"


def get_species_image(scientific_name: str) -> str | None:
    """Return a Wikipedia thumbnail URL for the species, or None."""
    try:
        title = scientific_name.replace(" ", "_")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
        headers = {"User-Agent": USER_AGENT}

        log.info("fetching_species_image", species=scientific_name, url=url)
        resp = requests.get(url, headers=headers, timeout=8)
        log.info("species_image_response", species=scientific_name, status=resp.status_code)

        if resp.status_code == 200:
            data = resp.json()
            thumb = str(data.get("thumbnail", {}).get("source"))
            log.info("species_image_found", species=scientific_name, thumbnail=thumb)
            return thumb
        log.warning("species_image_non_200", species=scientific_name, status=resp.status_code)
    except Exception as e:
        log.exception("species_image_failed", species=scientific_name, error=str(e))
    return None


def add_taxon_table(doc: DocumentObject, table_rows: list[ScoredTaxon] | list[dict[str, Any]]) -> None:
    """Add a formatted Word table of scored taxa."""
    if not table_rows:
        doc.add_paragraph("No taxons with more than one detection.")
        return

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"

    headers = ["Common Name", "Scientific Name", "Detections", "Score"]
    header_cells = table.rows[0].cells
    for i, text in enumerate(headers):
        header_cells[i].text = text
        for paragraph in header_cells[i].paragraphs:
            for run in paragraph.runs:
                run.bold = True

    for row in table_rows:
        cells = table.add_row().cells
        cells[0].text = row.get("common_name") or "—"
        cells[1].text = row.get("scientific_name") or ""
        cells[2].text = str(row.get("count", ""))
        cells[3].text = str(row.get("score", ""))

    doc.add_paragraph()  # spacer


def export_to_docx(summary: dict[str, Any]) -> Path:
    """
    Generate a formatted Word document from a completed summary.
    Returns the path to a temporary .docx file.
    """
    doc = Document()

    # ---------- Title ----------
    title = doc.add_heading("Biome Summary Report", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ---------- Metadata ----------
    meta = doc.add_paragraph()
    meta.add_run("Site ID: ").bold = True
    meta.add_run(str(summary.get("site_id", "Unknown")))
    meta.add_run("\n")
    meta.add_run("Window: ").bold = True
    meta.add_run(f"Last {summary.get('window_days', '?')} days")
    meta.add_run("\n")
    meta.add_run("Generated: ").bold = True
    created = summary.get("created_at", "")
    meta.add_run(created[:19].replace("T", " ") if created else "Unknown")

    doc.add_paragraph()  # spacer

    # ---------- Human Narrative ----------
    doc.add_heading("Summary", level=1)

    human_narrative = summary.get("human_narrative") or summary.get("narrative") or "No narrative available."

    for block in human_narrative.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            level = min(block.count("#"), 3)
            text = block.lstrip("# ").strip()
            doc.add_heading(text, level=level)
        else:
            doc.add_paragraph(block)

    # ----- Species Table -----
    doc.add_heading("Species Detected (more than one detection)", level=1)

    table_rows = summary.get("species_table") or []
    add_taxon_table(doc, table_rows)

    # ----- Notable Species with Images -----
    images = summary.get("notable_species_images") or []
    if images:
        doc.add_heading("Notable Species", level=1)

        headers = {"User-Agent": USER_AGENT}

        for item in images:
            name = item.get("scientific_name", "Unknown")
            common = item.get("common_name") or ""
            count = item.get("count", "?")
            image_url = item.get("image_url")

            caption = f"{common} ({name})" if common else name
            caption += f"  —  {count} detections"
            doc.add_heading(caption, level=2)

            if image_url:
                try:
                    resp = requests.get(image_url, headers=headers, timeout=10)
                    if resp.status_code != 200:
                        doc.add_paragraph(f"[Image unavailable - HTTP {resp.status_code}]")
                        continue

                    image_stream = BytesIO(resp.content)
                    with PILImage.open(image_stream) as img:
                        if img.mode in ("RGBA", "P", "LA"):
                            img = img.convert("RGB")  # type: ignore[assignment]
                        elif img.mode != "RGB":
                            img = img.convert("RGB")  # type: ignore[assignment]

                        output = BytesIO()
                        img.save(output, format="JPEG", quality=85)
                        output.seek(0)

                        doc.add_picture(output, width=Inches(3.5))
                        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

                except Exception as e:
                    doc.add_paragraph(f"[Could not load image: {type(e).__name__}: {e}]")
                    log.exception("embed_image_failed", image_url=image_url)

            doc.add_paragraph()

    # ---------- Footer ----------
    doc.add_paragraph()
    footer = doc.add_paragraph("Generated by sound-detection")
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.runs[0].font.size = Pt(9)
    footer.runs[0].font.color.rgb = RGBColor(120, 120, 120)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    doc.save(tmp.name)
    tmp.close()

    return Path(tmp.name)


async def backfill_images(session: AsyncSession, summary_id: Any) -> dict[str, Any] | None:
    """Fetch Wikipedia thumbnails for the top scored species and persist them."""
    summary = await session.get(BiomeSummary, summary_id)
    if not summary:
        return None

    candidates = summary.species_table or []
    candidates = sorted(
        candidates,
        key=lambda x: x.get("score", 0),
        reverse=True,
    )[:8]

    images = []
    for sp in candidates:
        name = sp.get("scientific_name")
        if not name:
            continue
        image_url = get_species_image(name)
        if image_url:
            images.append(
                {
                    "scientific_name": name,
                    "common_name": sp.get("common_name"),
                    "count": sp.get("count"),
                    "image_url": image_url,
                }
            )

    summary.notable_species_images = images
    session.add(summary)
    await session.commit()
    await session.refresh(summary)

    return {
        "summary_id": str(summary.id),
        "images_found": len(images),
        "notable_species_images": images,
    }
