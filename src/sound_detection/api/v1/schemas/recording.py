from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RecordingUpdate(BaseModel):
    microphone_id: UUID | None = None
    recorded_at: datetime | None = None
