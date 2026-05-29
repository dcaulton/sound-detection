"""Basic smoke tests for the FastAPI app."""

from fastapi.testclient import TestClient

from sound_detection.api.main import app

client = TestClient(app)


def test_health_check() -> None:
    """Health endpoint returns 200 and correct status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "sound-detection"


def test_biome_summary() -> None:
    """Biome summary endpoint returns expected shape."""
    response = client.get("/biome/summary")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert isinstance(data["short"], bool)
