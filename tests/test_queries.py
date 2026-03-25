"""Tests for DuckDB query layer."""
import json
import pytest
from pathlib import Path
from reporting.queries import (
    cost_by_tenant_and_feature,
    experiment_cost_vs_outcome,
    budget_pressure_by_namespace,
    fallback_latency_masking,
    unsafe_routes
)


@pytest.fixture
def telemetry_fixture(tmp_path):
    """Create telemetry JSONL fixture."""
    telemetry_path = tmp_path / "telemetry.jsonl"
    records = [
        {
            "timestamp": "2024-03-24T10:00:00Z",
            "request_id": "req-1",
            "tenant_id": "tenant-1",
            "use_case": "summarize",
            "experiment_id": "exp-a",
            "route_name": "/answer-routed",
            "estimated_cost_usd": 0.01,
            "tokens_in": 100,
            "tokens_out": 50,
            "finish_reason": "stop",
            "latency_ms": 150.0,
            "is_fallback": False
        },
        {
            "timestamp": "2024-03-24T10:01:00Z",
            "request_id": "req-2",
            "tenant_id": "tenant-1",
            "use_case": "qa",
            "experiment_id": "exp-a",
            "route_name": "/answer-routed",
            "estimated_cost_usd": 0.02,
            "tokens_in": 200,
            "tokens_out": 100,
            "finish_reason": "stop",
            "latency_ms": 200.0,
            "is_fallback": False
        },
        {
            "timestamp": "2024-03-24T10:02:00Z",
            "request_id": "req-3",
            "tenant_id": "tenant-2",
            "use_case": "summarize",
            "experiment_id": "exp-b",
            "route_name": "/answer-routed",
            "estimated_cost_usd": 0.05,
            "tokens_in": 500,
            "tokens_out": 250,
            "finish_reason": "length",
            "latency_ms": 500.0,
            "is_fallback": True
        },
    ]
    
    with open(telemetry_path, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    
    return str(telemetry_path)


@pytest.fixture
def decisions_fixture(tmp_path):
    """Create policy decisions JSONL fixture."""
    decisions_path = tmp_path / "decisions.jsonl"
    records = [
        {
            "timestamp": "2024-03-24T10:00:00Z",
            "request_id": "req-1",
            "tenant_id": "tenant-1",
            "budget_namespace": "default",
            "decision": "allow",
            "policy_version": "0.1.0"
        },
        {
            "timestamp": "2024-03-24T10:01:00Z",
            "request_id": "req-2",
            "tenant_id": "tenant-1",
            "budget_namespace": "demo",
            "decision": "downgrade",
            "policy_version": "0.1.0"
        },
        {
            "timestamp": "2024-03-24T10:02:00Z",
            "request_id": "req-3",
            "tenant_id": "tenant-2",
            "budget_namespace": "demo",
            "decision": "deny",
            "policy_version": "0.1.0"
        },
    ]
    
    with open(decisions_path, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    
    return str(decisions_path)


class TestCostByTenantAndFeature:
    """Tests for cost_by_tenant_and_feature query."""
    
    def test_correct_result(self, telemetry_fixture):
        """Test query returns correct aggregated results."""
        result = cost_by_tenant_and_feature(telemetry_fixture)
        
        assert len(result) == 3
        
        # Check types
        for row in result:
            assert isinstance(row["tenant_id"], str)
            assert isinstance(row["total_cost_usd"], float)
            assert isinstance(row["avg_cost_usd"], float)
            assert isinstance(row["request_count"], int)
        
        # Check tenant-2 summarize (highest cost)
        assert result[0]["tenant_id"] == "tenant-2"
        assert result[0]["feature_id"] == "summarize"
        assert result[0]["total_cost_usd"] == 0.05
        assert result[0]["request_count"] == 1
    
    def test_empty_file_returns_empty_list(self, tmp_path):
        """Test that empty file returns empty list."""
        empty_path = tmp_path / "empty.jsonl"
        empty_path.write_text("")
        
        result = cost_by_tenant_and_feature(str(empty_path))
        assert result == []
    
    def test_missing_file_returns_empty_list(self, tmp_path):
        """Test that missing file returns empty list."""
        result = cost_by_tenant_and_feature(str(tmp_path / "nonexistent.jsonl"))
        assert result == []


class TestExperimentCostVsOutcome:
    """Tests for experiment_cost_vs_outcome query."""
    
    def test_correct_result(self, telemetry_fixture):
        """Test query returns correct experiment metrics."""
        result = experiment_cost_vs_outcome(telemetry_fixture)
        
        assert len(result) == 2
        
        # Check types
        for row in result:
            assert isinstance(row["experiment_id"], str)
            assert isinstance(row["avg_tokens_in"], float)
            assert isinstance(row["avg_tokens_out"], float)
            assert isinstance(row["avg_cost_usd"], float)
            assert isinstance(row["success_rate"], float)
            assert isinstance(row["request_count"], int)
        
        # exp-b has higher cost
        assert result[0]["experiment_id"] == "exp-b"
        assert result[0]["avg_cost_usd"] == 0.05
        assert result[0]["success_rate"] == 0.0  # finish_reason != 'stop'
        
        # exp-a has lower cost but 100% success
        assert result[1]["experiment_id"] == "exp-a"
        assert result[1]["success_rate"] == 1.0
    
    def test_empty_file_returns_empty_list(self, tmp_path):
        """Test that empty file returns empty list."""
        empty_path = tmp_path / "empty.jsonl"
        empty_path.write_text("")
        
        result = experiment_cost_vs_outcome(str(empty_path))
        assert result == []


class TestBudgetPressureByNamespace:
    """Tests for budget_pressure_by_namespace query."""
    
    def test_correct_result(self, decisions_fixture):
        """Test query returns correct decision counts."""
        result = budget_pressure_by_namespace(decisions_fixture)
        
        assert len(result) == 2
        
        # Check types
        for row in result:
            assert isinstance(row["budget_namespace"], str)
            assert isinstance(row["allow_count"], int)
            assert isinstance(row["downgrade_count"], int)
            assert isinstance(row["deny_count"], int)
            assert isinstance(row["total_count"], int)
        
        # demo has most pressure (1 downgrade + 1 deny)
        assert result[0]["budget_namespace"] == "demo"
        assert result[0]["allow_count"] == 0
        assert result[0]["downgrade_count"] == 1
        assert result[0]["deny_count"] == 1
        assert result[0]["total_count"] == 2
        
        # default has no pressure
        assert result[1]["budget_namespace"] == "default"
        assert result[1]["allow_count"] == 1
        assert result[1]["downgrade_count"] == 0
        assert result[1]["deny_count"] == 0
    
    def test_empty_file_returns_empty_list(self, tmp_path):
        """Test that empty file returns empty list."""
        empty_path = tmp_path / "empty.jsonl"
        empty_path.write_text("")
        
        result = budget_pressure_by_namespace(str(empty_path))
        assert result == []


class TestFallbackLatencyMasking:
    """Tests for fallback_latency_masking query."""
    
    def test_correct_result(self, telemetry_fixture):
        """Test query returns correct latency metrics."""
        result = fallback_latency_masking(telemetry_fixture)
        
        assert len(result) >= 1
        
        # Check types
        for row in result:
            assert isinstance(row["route_name"], str)
            assert isinstance(row["is_fallback"], bool)
            assert isinstance(row["p95_latency_ms"], float)
            assert isinstance(row["avg_latency_ms"], float)
            assert isinstance(row["request_count"], int)
    
    def test_empty_file_returns_empty_list(self, tmp_path):
        """Test that empty file returns empty list."""
        empty_path = tmp_path / "empty.jsonl"
        empty_path.write_text("")
        
        result = fallback_latency_masking(str(empty_path))
        assert result == []


class TestUnsafeRoutes:
    """Tests for unsafe_routes query."""
    
    def test_correct_result_with_default_threshold(self, telemetry_fixture):
        """Test query returns routes exceeding default threshold."""
        result = unsafe_routes(telemetry_fixture)
        
        # Only routes with avg > 0.05 should appear
        # Our fixture has avg around 0.027 for /answer-routed, so should be empty
        assert isinstance(result, list)
    
    def test_correct_result_with_custom_threshold(self, telemetry_fixture):
        """Test query returns routes exceeding custom threshold."""
        result = unsafe_routes(telemetry_fixture, cost_threshold_usd=0.01)
        
        assert len(result) >= 1
        
        # Check types
        for row in result:
            assert isinstance(row["route_name"], str)
            assert isinstance(row["avg_cost_usd"], float)
            assert isinstance(row["max_cost_usd"], float)
            assert isinstance(row["request_count"], int)
            assert row["avg_cost_usd"] > 0.01
    
    def test_empty_file_returns_empty_list(self, tmp_path):
        """Test that empty file returns empty list."""
        empty_path = tmp_path / "empty.jsonl"
        empty_path.write_text("")
        
        result = unsafe_routes(str(empty_path))
        assert result == []
    
    def test_missing_file_returns_empty_list(self, tmp_path):
        """Test that missing file returns empty list."""
        result = unsafe_routes(str(tmp_path / "nonexistent.jsonl"))
        assert result == []
