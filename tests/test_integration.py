from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_analyze_creates_recording_and_detections(client: TestClient) -> None:
    with open("data/test_bird.mp3", "rb") as f:
        with patch("sound_detection.api.v1.routers.detections.RecordingRepository") as mock_repo:
            mock_instance = AsyncMock()
            # Use a real UUID instead of a string
            mock_mic = AsyncMock()
            mock_mic.id = UUID("12345678-1234-5678-1234-567812345678")
            mock_instance.get_or_create_default_microphone.return_value = mock_mic
            mock_repo.return_value = mock_instance

            response = client.post("/detections/analyze", files={"file": ("test_bird.mp3", f, "audio/mp3")})

    assert response.status_code == 202
    data = response.json()
    assert "recording_id" in data
    assert data["status"] in ("pending", "accepted")
