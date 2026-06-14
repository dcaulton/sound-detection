from abc import ABC, abstractmethod


class DataSource(ABC):
    """Abstract base class for all data sources used in RAG ingestion."""

    @abstractmethod
    def fetch_species_text(self, scientific_name: str) -> str | None:
        """
        Fetch and clean textual information about a species.
        Returns None if no useful data is found.
        """
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name of the data source (e.g. 'wikipedia', 'all_about_birds')."""
        pass
