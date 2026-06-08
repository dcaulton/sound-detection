from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.mark.asyncio
async def test_analyze_creates_recording_and_detections(client: TestClient, db: Session) -> None:
    with open("data/test_bird.mp3", "rb") as f:
        with patch("sound_detection.api.v1.routers.detections.RecordingRepository") as mock_repo:
            mock_instance = AsyncMock()
            mock_instance.get_or_create_default_microphone.return_value.id = "some-uuid"
            mock_repo.return_value = mock_instance

            response = client.post("/detections/analyze", files={"file": ("test_bird.mp3", f, "audio/mp3")})

    assert response.status_code == 202
