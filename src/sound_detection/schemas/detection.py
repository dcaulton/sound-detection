"""Pydantic schemas for detection endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class Detection(BaseModel):
    """Single species detection from audio."""

    species: str | None
    common_name: str | None
    scientific_name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    start_offset: float  # seconds into the recording
    end_offset: float
    model: str


class AnalyzeAudioRequest(BaseModel):
    """Metadata that can accompany an audio file."""

    mic_id: str | None = Field(None, description="Microphone identifier (e.g. 'yard-north')")
    latitude: float | None = None
    longitude: float | None = None
    recording_date: datetime | None = None


class AnalyzeAudioResponse(BaseModel):
    """Response from audio analysis."""

    detections: list[Detection]
    file_duration: float
    processing_time_seconds: float
    message: str = "Analysis complete"
