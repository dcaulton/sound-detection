"""SQLModel definitions for the expanded domain model."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import UUID as SA_UUID
from sqlalchemy import ForeignKey
from sqlmodel import JSON, Column, Field, Relationship, SQLModel


class Site(SQLModel, table=True):  # type: ignore[call-arg]
    """A physical site/parcel (yard or remote location)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True, max_length=200)
    description: str | None = None
    latitude: float
    longitude: float
    timezone: str = Field(default="UTC", description="IANA timezone name, e.g. America/Chicago")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    microphones: list["Microphone"] = Relationship(back_populates="site")


class Microphone(SQLModel, table=True):  # type: ignore[call-arg]
    """Individual outdoor microphone."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    site_id: uuid.UUID = Field(foreign_key="site.id")
    name: str = Field(index=True, max_length=100)
    latitude: float
    longitude: float
    installed_at: datetime = Field(default_factory=datetime.utcnow)
    filename_datetime_format: str | None = Field(
        default=None, description="Optional strptime format to override default filename datetime parsing"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    site: Site = Relationship(back_populates="microphones")
    recordings: list["Recording"] = Relationship(
        back_populates="microphone",
        passive_deletes=True,  # Let the database handle it
    )


class Recording(SQLModel, table=True):  # type: ignore[call-arg]
    """Uploaded audio file with processing status."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    microphone_id: uuid.UUID = Field(  # type: ignore[call-overload]
        foreign_key="microphone.id",
        sa_type=SA_UUID(as_uuid=True),
        nullable=False,
    )
    filename: str
    file_path: str
    recorded_at: datetime | None = Field(default=None, nullable=True)  # Stored as UTC
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending")
    duration_seconds: float | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    microphone: Microphone = Relationship(back_populates="recordings")
    detections: list["Detection"] = Relationship(back_populates="recording")


class Detection(SQLModel, table=True):  # type: ignore[call-arg]
    """Single species detection from BirdNET."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    recording_id: uuid.UUID = Field(
        sa_column=Column(
            SA_UUID(as_uuid=True),
            ForeignKey("recording.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    species: str
    common_name: str
    scientific_name: str
    confidence: float

    # Relative offsets (seconds from start of the audio file)
    start_offset: float
    end_offset: float

    # Absolute wall-clock times in UTC (derived from recording.recorded_at + offsets)
    start_time: datetime | None = Field(default=None, nullable=True)
    end_time: datetime | None = Field(default=None, nullable=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    recording: "Recording" = Relationship(
        back_populates="detections",
        passive_deletes=True,
    )


class BiomeSummary(SQLModel, table=True):
    __tablename__ = "biome_summaries"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    site_id: uuid.UUID = Field(foreign_key="site.id", index=True)  # ← Multi-tenant key

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    window_days: int = Field(default=30)
    status: str = Field(default="pending", index=True)  # pending | processing | completed | failed

    summary_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    narrative: str | None = None
    human_narrative: str | None = Field(default=None, nullable=True)

    notable_species_images: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )

    species_table: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )

    grok_narrative: str | None = Field(default=None, nullable=True)

    error_message: str | None = None
