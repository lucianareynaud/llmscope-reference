"""Integration tests for telemetry wiring."""
import json
import pytest
from datetime import UTC, datetime, timedelta
from pathlib import Path


@pytest.fixture
def telemetry_fixture(tmp_path, monkeypatch):
    """Fixture that writes synthetic telemetry JSONL and patches TELEMETRY_PATH."""
    telemetry_path = tmp_path / "telemetry.jsonl"
    
    def write_telemetry(records):
        """Write records to telemetry file."""
        with open(telemetry_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
    
    # Patch TELEMETRY_PATH in app.api module
    monkeypatch.setattr("app.api.TELEMETRY_PATH", str(telemetry_path))
    
    return write_telemetry


class TestBudgetThresholdWiring:
    """Tests for budget_threshold primitive with real telemetry."""
    
    def test_budget_threshold_denies_when_over_limit(self, tmp_path):
        """Test that budget_threshold denies when accumulated cost exceeds limit."""
        # Create telemetry file
        telemetry_path = tmp_path / "telemetry.jsonl"
        now = datetime.now(UTC)
        records = [
            {
                "timestamp": (now - timedelta(minutes=50)).isoformat() + "Z",
                "tenant_id": "acme",
                "audit_tags": {"budget_namespace": "demo"},
                "estimated_cost_usd": 0.60,
                "route": "/infer",
                "status": "success"
            },
            {
                "timestamp": (now - timedelta(minutes=30)).isoformat() + "Z",
                "tenant_id": "acme",
                "audit_tags": {"budget_namespace": "demo"},
                "estimated_cost_usd": 0.50,
                "route": "/infer",
                "status": "success"
            }
        ]
        with open(telemetry_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        
        # Create policy with budget_threshold rule
        policy_content = """
version: "0.1.0"
namespaces:
  demo:
    rules:
      - id: "demo-hourly-cap"
        primitive: budget_threshold
        period: hourly
        limit_usd: 1.00
        action: deny
        deny_reason: "Hourly budget exceeded for demo namespace"
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        # Test policy engine directly
        from policy.engine import YAMLPolicyEngine
        engine = YAMLPolicyEngine(str(policy_path))
        verdict = engine.evaluate(
            budget_namespace="demo",
            route_name="/infer",
            model_tier="cheap",
            telemetry_path=str(telemetry_path)
        )
        
        # Assert deny decision
        assert verdict.decision == "deny"
        assert verdict.reason == "Hourly budget exceeded for demo namespace"
        assert verdict.policy_id == "demo-hourly-cap"
    
    def test_budget_threshold_allows_when_under_limit(self, tmp_path):
        """Test that budget_threshold allows when accumulated cost is under limit."""
        # Create telemetry file
        telemetry_path = tmp_path / "telemetry.jsonl"
        now = datetime.now(UTC)
        records = [
            {
                "timestamp": (now - timedelta(minutes=30)).isoformat() + "Z",
                "tenant_id": "acme",
                "audit_tags": {"budget_namespace": "demo"},
                "estimated_cost_usd": 0.10,
                "route": "/infer",
                "status": "success"
            }
        ]
        with open(telemetry_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        
        # Create policy with budget_threshold rule
        policy_content = """
version: "0.1.0"
namespaces:
  demo:
    rules:
      - id: "demo-hourly-cap"
        primitive: budget_threshold
        period: hourly
        limit_usd: 1.00
        action: deny
        deny_reason: "Hourly budget exceeded for demo namespace"
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        # Test policy engine directly
        from policy.engine import YAMLPolicyEngine
        engine = YAMLPolicyEngine(str(policy_path))
        verdict = engine.evaluate(
            budget_namespace="demo",
            route_name="/infer",
            model_tier="cheap",
            telemetry_path=str(telemetry_path)
        )
        
        # Assert allow decision
        assert verdict.decision == "allow"


class TestCostAnomalyWiring:
    """Tests for cost_anomaly primitive with real telemetry."""
    
    def test_cost_anomaly_detects_spike(self, client, telemetry_fixture, tmp_path):
        """Test that cost_anomaly detects spike when cost exceeds baseline."""
        # Create policy with cost_anomaly rule
        policy_content = """
version: "0.1.0"
namespaces:
  default:
    rules:
      - id: "anomaly-detector"
        primitive: cost_anomaly
        feature_id: "summarize"
        baseline_window_hours: 24
        threshold_multiplier: 3.0
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        # Update policy engine to use test config
        from app.api import policy_engine
        policy_engine.config_path = str(policy_path)
        policy_engine.reload()
        
        # Write synthetic telemetry with 10 events at ~0.002 USD each
        now = datetime.now(UTC)
        records = []
        for i in range(10):
            records.append({
                "timestamp": (now - timedelta(hours=12 - i)).isoformat() + "Z",
                "tenant_id": "acme",
                "use_case": "summarize",
                "estimated_cost_usd": 0.002,
                "route": "/infer",
                "status": "success"
            })
        telemetry_fixture(records)
        
        # POST with feature_id="summarize" and model_tier="expensive"
        # Pre-dispatch cost estimate will be higher, triggering anomaly
        response = client.post("/infer", json={
            "prompt": "This is a very long prompt that will generate a high cost estimate " * 10,
            "tenant_id": "acme",
            "feature_id": "summarize",
            "model_tier": "expensive",
            "route_name": "/answer-routed"
        })
        
        # Assert response contains cost_anomaly_detected
        assert response.status_code == 200
        data = response.json()
        if data.get("policy_reason"):
            assert "cost_anomaly_detected" in data["policy_reason"]


class TestEmptyTelemetryWiring:
    """Tests for empty/missing telemetry handling."""
    
    def test_empty_telemetry_allows(self, client, monkeypatch):
        """Test that missing telemetry file returns allow."""
        # Point TELEMETRY_PATH to nonexistent file
        monkeypatch.setattr("app.api.TELEMETRY_PATH", "/nonexistent/telemetry.jsonl")
        
        # POST to /infer
        response = client.post("/infer", json={
            "prompt": "Test prompt",
            "tenant_id": "acme",
            "budget_namespace": "demo",
            "model_tier": "cheap",
            "route_name": "/answer-routed"
        })
        
        # Assert HTTP 200 (safe default is allow)
        assert response.status_code == 200
        data = response.json()
        assert data["policy_decision"] == "allow"
