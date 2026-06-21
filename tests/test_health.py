"""Basic smoke tests for the FastAPI app."""

from fastapi.testclient import TestClient

from sound_detection.main import app

client = TestClient(app)


def test_health_check() -> None:
    """Health endpoint returns 200 and correct status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "sound-detection"
