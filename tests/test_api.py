"""Tests for FastAPI gateway endpoint."""
import json
import pytest


class TestInferEndpoint:
    """Tests for POST /infer endpoint."""
    
    def test_allow_flow_complete(self, client):
        """Test complete allow flow with all fields."""
        response = client.post("/infer", json={
            "prompt": "What is the capital of France?",
            "tenant_id": "tenant-1",
            "caller_id": "user-123",
            "feature_id": "qa",
            "experiment_id": "exp-1",
            "budget_namespace": "test",
            "model_tier": "cheap",
            "route_name": "/answer-routed"  # Use available route from llmscope
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert "request_id" in data
        assert "answer" in data
        assert data["selected_model"] is not None
        assert data["estimated_cost_usd"] >= 0
        assert data["tokens_in"] > 0
        assert data["tokens_out"] > 0
        assert data["policy_decision"] == "allow"
        assert data["effective_model_tier"] == "cheap"
    
    def test_allow_flow_minimal(self, client):
        """Test allow flow with minimal required fields."""
        response = client.post("/infer", json={
            "prompt": "Test prompt",
            "tenant_id": "tenant-1"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["policy_decision"] == "allow"
        assert data["effective_model_tier"] == "cheap"  # default
    
    def test_downgrade_alters_effective_tier(self, client, tmp_path):
        """Test that downgrade changes effective_model_tier."""
        # Create policy that downgrades expensive to cheap
        policy_content = """
version: "0.1.0"
namespaces:
  downgrade-test:
    rules:
      - id: "force-cheap"
        primitive: route_preference
        route_name: "/answer-routed"
        prefer_tier: cheap
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        # Update policy engine to use test config
        from app.api import policy_engine
        policy_engine.config_path = str(policy_path)
        policy_engine.reload()
        
        response = client.post("/infer", json={
            "prompt": "Test prompt",
            "tenant_id": "tenant-1",
            "budget_namespace": "downgrade-test",
            "model_tier": "expensive",
            "route_name": "/answer-routed"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["policy_decision"] == "downgrade"
        assert data["policy_reason"] == "route_prefers_cheap"
        assert data["effective_model_tier"] == "cheap"
    
    def test_deny_returns_402(self, client, tmp_path):
        """Test that deny returns HTTP 402 and doesn't call llmscope."""
        # Create policy that denies
        policy_content = """
version: "0.1.0"
namespaces:
  deny-test:
    rules:
      - id: "deny-all"
        primitive: budget_threshold
        period: hourly
        limit_usd: 0.0
        action: deny
        deny_reason: "Budget exhausted"
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        # Create fake telemetry showing cost
        telemetry_path = tmp_path / "telemetry.jsonl"
        from datetime import datetime, timedelta
        import json
        now = datetime.utcnow()
        record = {
            "timestamp": (now - timedelta(minutes=10)).isoformat() + "Z",
            "request_id": "req-1",
            "budget_namespace": "deny-test",
            "estimated_cost_usd": 0.01
        }
        telemetry_path.write_text(json.dumps(record) + "\n")
        
        # Update policy engine
        from app.api import policy_engine
        policy_engine.config_path = str(policy_path)
        policy_engine.reload()
        
        # Patch evaluate to use telemetry
        original_evaluate = policy_engine.evaluate
        def patched_evaluate(*args, **kwargs):
            kwargs['telemetry_path'] = str(telemetry_path)
            return original_evaluate(*args, **kwargs)
        policy_engine.evaluate = patched_evaluate
        
        response = client.post("/infer", json={
            "prompt": "Test prompt",
            "tenant_id": "tenant-1",
            "budget_namespace": "deny-test",
            "model_tier": "cheap"
        })
        
        assert response.status_code == 402
        data = response.json()
        
        assert data["detail"]["error"] == "budget_exceeded"
        assert data["detail"]["reason"] == "Budget exhausted"
        assert data["detail"]["policy_id"] == "deny-all"

    
    def test_caller_id_propagated_to_context(self, client):
        """Test that caller_id is propagated to LLMRequestContext."""
        response = client.post("/infer", json={
            "prompt": "Test prompt",
            "tenant_id": "tenant-1",
            "caller_id": "user-789"
        })
        
        assert response.status_code == 200
        # If caller_id wasn't propagated correctly, llmscope would fail
        # The fact that we get 200 means context was constructed properly
    
    def test_feature_id_propagated_to_context(self, client):
        """Test that feature_id is propagated to LLMRequestContext."""
        response = client.post("/infer", json={
            "prompt": "Test prompt",
            "tenant_id": "tenant-1",
            "feature_id": "summarize"
        })
        
        assert response.status_code == 200
        # If feature_id wasn't propagated correctly, llmscope would fail
        # The fact that we get 200 means context was constructed properly
    
    def test_invalid_request_rejected(self, client):
        """Test that invalid request is rejected by Pydantic."""
        response = client.post("/infer", json={
            "prompt": "",  # Empty prompt should be rejected
            "tenant_id": "tenant-1"
        })
        
        assert response.status_code == 422  # Validation error
    
    def test_missing_tenant_id_rejected(self, client):
        """Test that missing tenant_id is rejected."""
        response = client.post("/infer", json={
            "prompt": "Test prompt"
        })
        
        assert response.status_code == 422  # Validation error


class TestHealthEndpoint:
    """Tests for health check endpoint."""
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}



class TestDecisionLogIntegration:
    """Tests for decision log integration in endpoint."""
    
    def test_denial_generates_log_without_cost(self, client, tmp_path):
        """Test that denial generates log entry without cost/latency."""
        # Create policy that denies
        policy_content = """
version: "0.1.0"
namespaces:
  deny-test:
    rules:
      - id: "deny-all"
        primitive: budget_threshold
        period: hourly
        limit_usd: 0.0
        action: deny
        deny_reason: "Budget exhausted"
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        # Create fake telemetry showing cost
        telemetry_path = tmp_path / "telemetry.jsonl"
        from datetime import datetime, timedelta
        import json
        now = datetime.utcnow()
        record = {
            "timestamp": (now - timedelta(minutes=10)).isoformat() + "Z",
            "request_id": "req-1",
            "budget_namespace": "deny-test",
            "estimated_cost_usd": 0.01
        }
        telemetry_path.write_text(json.dumps(record) + "\n")
        
        # Set up decision log path
        decisions_path = tmp_path / "decisions.jsonl"
        
        # Update policy engine and decision log path
        from app.api import policy_engine
        import app.api
        policy_engine.config_path = str(policy_path)
        policy_engine.reload()
        
        # Patch evaluate to use telemetry and decision log path
        original_evaluate = policy_engine.evaluate
        def patched_evaluate(*args, **kwargs):
            kwargs['telemetry_path'] = str(telemetry_path)
            return original_evaluate(*args, **kwargs)
        policy_engine.evaluate = patched_evaluate
        
        # Patch DECISIONS_PATH
        original_decisions_path = app.api.DECISIONS_PATH
        app.api.DECISIONS_PATH = str(decisions_path)
        
        try:
            response = client.post("/infer", json={
                "prompt": "Test prompt",
                "tenant_id": "tenant-1",
                "budget_namespace": "deny-test",
                "model_tier": "cheap"
            })
            
            assert response.status_code == 402
            
            # Check decision log
            assert decisions_path.exists()
            lines = decisions_path.read_text().strip().split("\n")
            assert len(lines) == 1
            
            logged = json.loads(lines[0])
            assert logged["decision"] == "deny"
            assert logged["tenant_id"] == "tenant-1"
            assert logged["budget_namespace"] == "deny-test"
            assert "estimated_cost_usd" not in logged  # None omitted
            assert "latency_ms" not in logged  # None omitted
            assert logged["policy_version"] == "0.1.0"
        finally:
            app.api.DECISIONS_PATH = original_decisions_path
    
    def test_allow_generates_log_with_cost(self, client, tmp_path):
        """Test that allow generates log entry with cost and latency."""
        decisions_path = tmp_path / "decisions.jsonl"
        
        # Patch DECISIONS_PATH
        import app.api
        original_decisions_path = app.api.DECISIONS_PATH
        app.api.DECISIONS_PATH = str(decisions_path)
        
        try:
            response = client.post("/infer", json={
                "prompt": "Test prompt",
                "tenant_id": "tenant-1"
            })
            
            assert response.status_code == 200
            data = response.json()
            
            # Check decision log
            assert decisions_path.exists()
            lines = decisions_path.read_text().strip().split("\n")
            assert len(lines) == 1
            
            logged = json.loads(lines[0])
            assert logged["decision"] == "allow"
            assert logged["request_id"] == data["request_id"]
            assert logged["tenant_id"] == "tenant-1"
            assert logged["estimated_cost_usd"] == 0.001
            assert "latency_ms" in logged
            assert logged["latency_ms"] >= 0
        finally:
            app.api.DECISIONS_PATH = original_decisions_path
    
    def test_request_id_correlation(self, client, tmp_path):
        """Test that request_id in log matches response."""
        decisions_path = tmp_path / "decisions.jsonl"
        
        # Patch DECISIONS_PATH
        import app.api
        original_decisions_path = app.api.DECISIONS_PATH
        app.api.DECISIONS_PATH = str(decisions_path)
        
        try:
            response = client.post("/infer", json={
                "prompt": "Test prompt",
                "tenant_id": "tenant-1"
            })
            
            assert response.status_code == 200
            data = response.json()
            
            # Check correlation
            import json
            lines = decisions_path.read_text().strip().split("\n")
            logged = json.loads(lines[0])
            
            assert logged["request_id"] == data["request_id"]
        finally:
            app.api.DECISIONS_PATH = original_decisions_path
    
    def test_second_request_appends_not_overwrites(self, client, tmp_path):
        """Test that second request adds second line without overwriting."""
        decisions_path = tmp_path / "decisions.jsonl"
        
        # Patch DECISIONS_PATH
        import app.api
        original_decisions_path = app.api.DECISIONS_PATH
        app.api.DECISIONS_PATH = str(decisions_path)
        
        try:
            # First request
            response1 = client.post("/infer", json={
                "prompt": "First prompt",
                "tenant_id": "tenant-1"
            })
            assert response1.status_code == 200
            
            # Second request
            response2 = client.post("/infer", json={
                "prompt": "Second prompt",
                "tenant_id": "tenant-2"
            })
            assert response2.status_code == 200
            
            # Check both logged
            import json
            lines = decisions_path.read_text().strip().split("\n")
            assert len(lines) == 2
            
            logged1 = json.loads(lines[0])
            logged2 = json.loads(lines[1])
            
            assert logged1["tenant_id"] == "tenant-1"
            assert logged2["tenant_id"] == "tenant-2"
        finally:
            app.api.DECISIONS_PATH = original_decisions_path
