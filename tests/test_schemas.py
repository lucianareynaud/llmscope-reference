"""Tests for HTTP schemas."""
import pytest
from pydantic import ValidationError
from app.schemas import InferRequest, InferResponse


class TestInferRequest:
    """Tests for InferRequest schema."""
    
    def test_minimal_valid_request(self):
        """Test minimal valid request with required fields only."""
        req = InferRequest(
            prompt="test prompt",
            tenant_id="tenant-1"
        )
        assert req.prompt == "test prompt"
        assert req.tenant_id == "tenant-1"
        assert req.caller_id is None
        assert req.feature_id is None
        assert req.experiment_id is None
        assert req.budget_namespace is None
        assert req.model_tier == "cheap"
        assert req.route_name == "/answer-routed"
    
    def test_all_fields_provided(self):
        """Test request with all fields provided."""
        req = InferRequest(
            prompt="test prompt",
            tenant_id="tenant-1",
            caller_id="user-123",
            feature_id="summarize",
            experiment_id="exp-42",
            budget_namespace="demo",
            model_tier="expensive",
            route_name="/custom"
        )
        assert req.caller_id == "user-123"
        assert req.feature_id == "summarize"
        assert req.experiment_id == "exp-42"
        assert req.budget_namespace == "demo"
        assert req.model_tier == "expensive"
        assert req.route_name == "/custom"
    
    def test_empty_prompt_rejected(self):
        """Test that empty prompt is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            InferRequest(prompt="", tenant_id="tenant-1")
        
        errors = exc_info.value.errors()
        assert any("prompt" in str(e) for e in errors)
    
    def test_whitespace_only_prompt_rejected(self):
        """Test that whitespace-only prompt is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            InferRequest(prompt="   ", tenant_id="tenant-1")
        
        errors = exc_info.value.errors()
        assert any("prompt" in str(e) for e in errors)
    
    def test_empty_tenant_id_rejected(self):
        """Test that empty tenant_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            InferRequest(prompt="test", tenant_id="")
        
        errors = exc_info.value.errors()
        assert any("tenant_id" in str(e) for e in errors)

    def test_whitespace_only_tenant_id_rejected(self):
        """Test that whitespace-only tenant_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            InferRequest(prompt="test", tenant_id="   ")
        
        errors = exc_info.value.errors()
        assert any("tenant_id" in str(e) for e in errors)
    
    def test_invalid_model_tier_rejected(self):
        """Test that invalid model_tier is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            InferRequest(
                prompt="test",
                tenant_id="tenant-1",
                model_tier="invalid"
            )
        
        errors = exc_info.value.errors()
        assert any("model_tier" in str(e) for e in errors)
    
    def test_caller_id_optional_accepted(self):
        """Test that caller_id is optional and accepted when present."""
        req = InferRequest(
            prompt="test",
            tenant_id="tenant-1",
            caller_id="user-456"
        )
        assert req.caller_id == "user-456"
    
    def test_defaults_correct(self):
        """Test that default values are correct."""
        req = InferRequest(prompt="test", tenant_id="tenant-1")
        assert req.model_tier == "cheap"
        assert req.route_name == "/answer-routed"


class TestInferResponse:
    """Tests for InferResponse schema."""
    
    def test_valid_response(self):
        """Test valid response construction."""
        resp = InferResponse(
            request_id="req-123",
            answer="test answer",
            selected_model="gpt-4o-mini",
            estimated_cost_usd=0.001,
            tokens_in=10,
            tokens_out=20,
            policy_decision="allow",
            effective_model_tier="cheap"
        )
        assert resp.request_id == "req-123"
        assert resp.answer == "test answer"
        assert resp.selected_model == "gpt-4o-mini"
        assert resp.estimated_cost_usd == 0.001
        assert resp.tokens_in == 10
        assert resp.tokens_out == 20
        assert resp.policy_decision == "allow"
        assert resp.policy_reason is None
        assert resp.effective_model_tier == "cheap"
    
    def test_response_with_policy_reason(self):
        """Test response with optional policy_reason."""
        resp = InferResponse(
            request_id="req-123",
            answer="test",
            selected_model="gpt-4o-mini",
            estimated_cost_usd=0.001,
            tokens_in=10,
            tokens_out=20,
            policy_decision="downgrade",
            policy_reason="budget_exceeded",
            effective_model_tier="cheap"
        )
        assert resp.policy_reason == "budget_exceeded"
