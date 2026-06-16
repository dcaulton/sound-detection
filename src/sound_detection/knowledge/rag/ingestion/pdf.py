from __future__ import annotations

from pypdf import PdfReader

from .base import DataSource


class PDFSource(DataSource):
    """Ingests text from a PDF file."""

    def __init__(self, file_path: str, source_name: str = "pdf") -> None:
        self.file_path = file_path
        self._source_name = source_name

    @property
    def source_name(self) -> str:
        return self._source_name

    def fetch_species_text(self, scientific_name: str | None = None) -> str | None:
        try:
            reader = PdfReader(self.file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text.strip() if text.strip() else None
        except Exception:
            return None
