"""Tests for policy decision logging."""
import json
from pathlib import Path
from policy.models import PolicyDecisionRecord
from policy.log import PolicyDecisionLog


def test_record_serialization_all_fields(tmp_path):
    """Test serialization with all fields populated."""
    record = PolicyDecisionRecord(
        timestamp="2024-03-24T10:00:00Z",
        request_id="req-123",
        tenant_id="tenant-1",
        caller_id="user-456",
        feature_id="summarize",
        experiment_id="exp-42",
        budget_namespace="demo",
        route_name="/infer",
        requested_model_tier="expensive",
        effective_model_tier="cheap",
        primitive="budget_threshold",
        decision="downgrade",
        reason="budget_exceeded",
        policy_id="demo-hourly-cap",
        estimated_cost_usd=0.001,
        latency_ms=150.5,
        window_cost_usd=0.95,
        window_limit_usd=1.0,
        policy_version="0.1.0"
    )
    
    result = record.to_dict()
    
    assert result["timestamp"] == "2024-03-24T10:00:00Z"
    assert result["request_id"] == "req-123"
    assert result["tenant_id"] == "tenant-1"
    assert result["caller_id"] == "user-456"
    assert result["feature_id"] == "summarize"
    assert result["experiment_id"] == "exp-42"
    assert result["budget_namespace"] == "demo"
    assert result["route_name"] == "/infer"
    assert result["requested_model_tier"] == "expensive"
    assert result["effective_model_tier"] == "cheap"
    assert result["primitive"] == "budget_threshold"
    assert result["decision"] == "downgrade"
    assert result["reason"] == "budget_exceeded"
    assert result["policy_id"] == "demo-hourly-cap"
    assert result["estimated_cost_usd"] == 0.001
    assert result["latency_ms"] == 150.5
    assert result["window_cost_usd"] == 0.95
    assert result["window_limit_usd"] == 1.0
    assert result["policy_version"] == "0.1.0"


def test_record_serialization_omits_none(tmp_path):
    """Test that None values are omitted from serialization."""
    record = PolicyDecisionRecord(
        timestamp="2024-03-24T10:00:00Z",
        request_id="req-123",
        tenant_id="tenant-1",
        caller_id=None,
        feature_id=None,
        experiment_id=None,
        budget_namespace=None,
        route_name="/infer",
        requested_model_tier="cheap",
        effective_model_tier="cheap",
        primitive="route_preference",
        decision="allow",
        reason=None,
        policy_id=None,
        estimated_cost_usd=None,
        latency_ms=None,
        window_cost_usd=None,
        window_limit_usd=None,
        policy_version="0.1.0"
    )
    
    result = record.to_dict()
    
    assert "caller_id" not in result
    assert "feature_id" not in result
    assert "experiment_id" not in result
    assert "budget_namespace" not in result
    assert "reason" not in result
    assert "policy_id" not in result
    assert "estimated_cost_usd" not in result
    assert "latency_ms" not in result
    assert "window_cost_usd" not in result
    assert "window_limit_usd" not in result
    
    # Required fields still present
    assert result["timestamp"] == "2024-03-24T10:00:00Z"
    assert result["request_id"] == "req-123"
    assert result["policy_version"] == "0.1.0"



def test_policy_version_present(tmp_path):
    """Test that policy_version is always present in output."""
    record = PolicyDecisionRecord(
        timestamp="2024-03-24T10:00:00Z",
        request_id="req-123",
        tenant_id="tenant-1",
        caller_id=None,
        feature_id=None,
        experiment_id=None,
        budget_namespace=None,
        route_name="/infer",
        requested_model_tier="cheap",
        effective_model_tier="cheap",
        primitive="budget_threshold",
        decision="allow",
        reason=None,
        policy_id=None,
        estimated_cost_usd=None,
        latency_ms=None,
        window_cost_usd=None,
        window_limit_usd=None,
        policy_version="0.1.0"
    )
    
    result = record.to_dict()
    assert "policy_version" in result
    assert result["policy_version"] == "0.1.0"


def test_append_creates_file(tmp_path):
    """Test that append creates file if it doesn't exist."""
    log_path = tmp_path / "decisions.jsonl"
    
    record = PolicyDecisionRecord(
        timestamp="2024-03-24T10:00:00Z",
        request_id="req-123",
        tenant_id="tenant-1",
        caller_id=None,
        feature_id=None,
        experiment_id=None,
        budget_namespace=None,
        route_name="/infer",
        requested_model_tier="cheap",
        effective_model_tier="cheap",
        primitive="budget_threshold",
        decision="allow",
        reason=None,
        policy_id=None,
        estimated_cost_usd=0.001,
        latency_ms=100.0,
        window_cost_usd=None,
        window_limit_usd=None,
        policy_version="0.1.0"
    )
    
    PolicyDecisionLog.append(record, str(log_path))
    
    assert log_path.exists()
    content = log_path.read_text()
    assert len(content.strip().split("\n")) == 1


def test_append_incremental(tmp_path):
    """Test that second append doesn't overwrite first."""
    log_path = tmp_path / "decisions.jsonl"
    
    record1 = PolicyDecisionRecord(
        timestamp="2024-03-24T10:00:00Z",
        request_id="req-1",
        tenant_id="tenant-1",
        caller_id=None,
        feature_id=None,
        experiment_id=None,
        budget_namespace=None,
        route_name="/infer",
        requested_model_tier="cheap",
        effective_model_tier="cheap",
        primitive="budget_threshold",
        decision="allow",
        reason=None,
        policy_id=None,
        estimated_cost_usd=0.001,
        latency_ms=100.0,
        window_cost_usd=None,
        window_limit_usd=None,
        policy_version="0.1.0"
    )
    
    record2 = PolicyDecisionRecord(
        timestamp="2024-03-24T10:01:00Z",
        request_id="req-2",
        tenant_id="tenant-2",
        caller_id=None,
        feature_id=None,
        experiment_id=None,
        budget_namespace=None,
        route_name="/infer",
        requested_model_tier="expensive",
        effective_model_tier="expensive",
        primitive="route_preference",
        decision="deny",
        reason="budget_exceeded",
        policy_id="demo-cap",
        estimated_cost_usd=None,
        latency_ms=None,
        window_cost_usd=None,
        window_limit_usd=None,
        policy_version="0.1.0"
    )
    
    PolicyDecisionLog.append(record1, str(log_path))
    PolicyDecisionLog.append(record2, str(log_path))
    
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 2
    
    # Verify both records are present
    parsed1 = json.loads(lines[0])
    parsed2 = json.loads(lines[1])
    
    assert parsed1["request_id"] == "req-1"
    assert parsed2["request_id"] == "req-2"


def test_append_creates_parent_directories(tmp_path):
    """Test that append creates parent directories if needed."""
    log_path = tmp_path / "nested" / "dir" / "decisions.jsonl"
    
    record = PolicyDecisionRecord(
        timestamp="2024-03-24T10:00:00Z",
        request_id="req-123",
        tenant_id="tenant-1",
        caller_id=None,
        feature_id=None,
        experiment_id=None,
        budget_namespace=None,
        route_name="/infer",
        requested_model_tier="cheap",
        effective_model_tier="cheap",
        primitive="budget_threshold",
        decision="allow",
        reason=None,
        policy_id=None,
        estimated_cost_usd=0.001,
        latency_ms=100.0,
        window_cost_usd=None,
        window_limit_usd=None,
        policy_version="0.1.0"
    )
    
    PolicyDecisionLog.append(record, str(log_path))
    
    assert log_path.exists()
    assert log_path.parent.exists()
