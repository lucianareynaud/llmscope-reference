"""Smoke test for application startup and health endpoint."""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


def test_app_starts(client):
    """Verify the app starts without import errors."""
    assert app is not None
    assert app.title == "llmscope-reference"


def test_health_endpoint(client):
    """Verify health endpoint responds with 200."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
