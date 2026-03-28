"""Test fixtures and configuration."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def client():
    """FastAPI test client fixture."""
    # Import here to ensure OTEL is disabled before app initialization
    from app.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_llmscope(monkeypatch):
    """Mock llmscope.call_llm for testing without real API calls.
    
    NOTE: This uses monkeypatching as a temporary solution. The llmscope public
    API (register_provider) requires provider name and instance, but the test
    environment needs additional setup that isn't fully documented yet.
    
    This is documented as technical debt - ideally we would use register_provider
    with a FakeProvider as shown in design.md, but the current llmscope version
    requires route policies to be configured which isn't part of the public seam.
    """
    from llmscope.gateway.client import GatewayResult
    
    async def fake_call_llm(*args, **kwargs):
        """Return fake GatewayResult."""
        return GatewayResult(
            request_id="test-req-123",
            text="Fake response",
            selected_model="gpt-4o-mini",
            estimated_cost_usd=0.001,
            tokens_in=10,
            tokens_out=20,
            cache_hit=False
        )
    
    monkeypatch.setattr("app.api.call_llm", fake_call_llm)
    yield


@pytest.fixture(autouse=True)
def restore_default_policy():
    """Restore policy engine to default config after each test."""
    yield
    # Restore default policy after test completes
    try:
        from app.api import policy_engine
        from app.settings import BASE_DIR
        policy_engine.config_path = str(BASE_DIR / "config" / "policy.yaml")
        policy_engine.reload()
    except Exception:
        # If policy engine doesn't exist yet, that's fine
        pass
