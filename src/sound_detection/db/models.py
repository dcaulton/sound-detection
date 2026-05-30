"""SQLModel definitions for the expanded domain model."""

import uuid
from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel


class Site(SQLModel, table=True):  # type: ignore[call-arg]
    """A physical site/parcel (yard or remote location)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True, max_length=200)
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    microphones: list["Microphone"] = Relationship(back_populates="site")


class Microphone(SQLModel, table=True):  # type: ignore[call-arg]
    """Individual outdoor microphone."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    site_id: uuid.UUID = Field(foreign_key="site.id")
    name: str = Field(index=True, max_length=100)
    latitude: float
    longitude: float
    installed_at: datetime = Field(default_factory=datetime.utcnow)

    site: Site = Relationship(back_populates="microphones")
    recordings: list["Recording"] = Relationship(back_populates="microphone")


class Recording(SQLModel, table=True):  # type: ignore[call-arg]
    """Uploaded audio file with processing status."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    microphone_id: uuid.UUID = Field(foreign_key="microphone.id")
    filename: str
    file_path: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending")
    duration_seconds: float | None = None
    error_message: str | None = None

    microphone: Microphone = Relationship(back_populates="recordings")
    detections: list["Detection"] = Relationship(back_populates="recording")


class Detection(SQLModel, table=True):  # type: ignore[call-arg]
    """Single species detection from BirdNET."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    recording_id: uuid.UUID = Field(foreign_key="recording.id")
    species: str
    common_name: str
    scientific_name: str
    confidence: float
    start_time: float
    end_time: float

    recording: Recording = Relationship(back_populates="detections")
