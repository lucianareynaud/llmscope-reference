"""Tests for YAML policy engine."""
import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from policy.loader import load_policy
from policy.engine import YAMLPolicyEngine


@pytest.fixture
def valid_policy_file(tmp_path):
    """Create a valid policy YAML file."""
    policy_content = """
version: "0.1.0"
namespaces:
  default:
    rules:
      - id: "default-daily-cap"
        primitive: budget_threshold
        period: daily
        limit_usd: 10.00
        action: downgrade
        downgrade_to_tier: cheap
  
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
    return str(policy_path)


@pytest.fixture
def telemetry_file_with_costs(tmp_path):
    """Create telemetry JSONL with cost data."""
    telemetry_path = tmp_path / "telemetry.jsonl"
    
    now = datetime.utcnow()
    records = [
        {
            "timestamp": (now - timedelta(minutes=30)).isoformat() + "Z",
            "request_id": "req-1",
            "budget_namespace": "demo",
            "estimated_cost_usd": 0.50
        },
        {
            "timestamp": (now - timedelta(minutes=20)).isoformat() + "Z",
            "request_id": "req-2",
            "budget_namespace": "demo",
            "estimated_cost_usd": 0.40
        },
        {
            "timestamp": (now - timedelta(minutes=10)).isoformat() + "Z",
            "request_id": "req-3",
            "budget_namespace": "demo",
            "estimated_cost_usd": 0.15
        },
    ]
    
    with open(telemetry_path, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    
    return str(telemetry_path)


class TestPolicyLoader:
    """Tests for policy configuration loader."""
    
    def test_load_valid_policy(self, valid_policy_file):
        """Test loading a valid policy file."""
        config = load_policy(valid_policy_file)
        
        assert config.version == "0.1.0"
        assert "default" in config.namespaces
        assert "demo" in config.namespaces
        assert len(config.namespaces["default"].rules) == 1
        assert len(config.namespaces["demo"].rules) == 1
    
    def test_load_nonexistent_file(self, tmp_path):
        """Test that loading nonexistent file raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            load_policy(str(tmp_path / "nonexistent.yaml"))
    
    def test_load_invalid_yaml(self, tmp_path):
        """Test that invalid YAML raises ValueError."""
        invalid_path = tmp_path / "invalid.yaml"
        invalid_path.write_text("{ invalid yaml content")
        
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_policy(str(invalid_path))
    
    def test_load_missing_version(self, tmp_path):
        """Test that missing version field raises ValueError."""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text("namespaces: {}")
        
        with pytest.raises(ValueError, match="version"):
            load_policy(str(policy_path))
    
    def test_load_missing_namespaces(self, tmp_path):
        """Test that missing namespaces field raises ValueError."""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text('version: "0.1.0"')
        
        with pytest.raises(ValueError, match="namespaces"):
            load_policy(str(policy_path))


class TestYAMLPolicyEngine:
    """Tests for YAML policy engine."""
    
    def test_engine_initialization(self, valid_policy_file):
        """Test engine initializes with valid config."""
        engine = YAMLPolicyEngine(valid_policy_file)
        assert engine.config.version == "0.1.0"
    
    def test_reload_config(self, tmp_path):
        """Test that reload() picks up config changes."""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text("""
version: "0.1.0"
namespaces:
  default:
    rules: []
""")
        
        engine = YAMLPolicyEngine(str(policy_path))
        assert engine.config.version == "0.1.0"
        
        # Update config
        policy_path.write_text("""
version: "0.2.0"
namespaces:
  default:
    rules: []
""")
        
        engine.reload()
        assert engine.config.version == "0.2.0"

    
    def test_budget_threshold_deny(self, valid_policy_file, telemetry_file_with_costs):
        """Test budget_threshold deny when limit exceeded."""
        engine = YAMLPolicyEngine(valid_policy_file)
        
        # demo namespace has 1.05 USD in last hour, limit is 1.00
        verdict = engine.evaluate(
            budget_namespace="demo",
            route_name="/infer",
            model_tier="expensive",
            telemetry_path=telemetry_file_with_costs
        )
        
        assert verdict.decision == "deny"
        assert verdict.reason == "Hourly budget exceeded for demo namespace"
        assert verdict.policy_id == "demo-hourly-cap"
        assert verdict.primitive == "budget_threshold"
    
    def test_budget_threshold_downgrade(self, tmp_path):
        """Test budget_threshold downgrade when limit exceeded."""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text("""
version: "0.1.0"
namespaces:
  test:
    rules:
      - id: "test-cap"
        primitive: budget_threshold
        period: hourly
        limit_usd: 0.50
        action: downgrade
        downgrade_to_tier: cheap
""")
        
        telemetry_path = tmp_path / "telemetry.jsonl"
        now = datetime.utcnow()
        record = {
            "timestamp": (now - timedelta(minutes=10)).isoformat() + "Z",
            "request_id": "req-1",
            "budget_namespace": "test",
            "estimated_cost_usd": 0.60
        }
        telemetry_path.write_text(json.dumps(record) + "\n")
        
        engine = YAMLPolicyEngine(str(policy_path))
        verdict = engine.evaluate(
            budget_namespace="test",
            route_name="/infer",
            model_tier="expensive",
            telemetry_path=str(telemetry_path)
        )
        
        assert verdict.decision == "downgrade"
        assert verdict.reason == "budget_exceeded"
        assert verdict.effective_model_tier == "cheap"
        assert verdict.policy_id == "test-cap"
        assert verdict.primitive == "budget_threshold"
    
    def test_telemetry_file_absent_returns_allow(self, valid_policy_file):
        """Test that missing telemetry file returns safe allow."""
        engine = YAMLPolicyEngine(valid_policy_file)
        
        verdict = engine.evaluate(
            budget_namespace="demo",
            route_name="/infer",
            model_tier="expensive",
            telemetry_path="/nonexistent/path.jsonl"
        )
        
        assert verdict.decision == "allow"
    
    def test_telemetry_file_empty_returns_allow(self, valid_policy_file, tmp_path):
        """Test that empty telemetry file returns safe allow."""
        empty_telemetry = tmp_path / "empty.jsonl"
        empty_telemetry.write_text("")
        
        engine = YAMLPolicyEngine(valid_policy_file)
        
        verdict = engine.evaluate(
            budget_namespace="demo",
            route_name="/infer",
            model_tier="expensive",
            telemetry_path=str(empty_telemetry)
        )
        
        assert verdict.decision == "allow"
    
    def test_telemetry_path_none_returns_allow(self, valid_policy_file):
        """Test that None telemetry_path returns safe allow."""
        engine = YAMLPolicyEngine(valid_policy_file)
        
        verdict = engine.evaluate(
            budget_namespace="demo",
            route_name="/infer",
            model_tier="expensive",
            telemetry_path=None
        )
        
        assert verdict.decision == "allow"
    
    def test_budget_under_limit_returns_allow(self, valid_policy_file, tmp_path):
        """Test that budget under limit returns allow."""
        telemetry_path = tmp_path / "telemetry.jsonl"
        now = datetime.utcnow()
        record = {
            "timestamp": (now - timedelta(minutes=10)).isoformat() + "Z",
            "request_id": "req-1",
            "budget_namespace": "demo",
            "estimated_cost_usd": 0.50  # Under 1.00 limit
        }
        telemetry_path.write_text(json.dumps(record) + "\n")
        
        engine = YAMLPolicyEngine(valid_policy_file)
        verdict = engine.evaluate(
            budget_namespace="demo",
            route_name="/infer",
            model_tier="expensive",
            telemetry_path=str(telemetry_path)
        )
        
        assert verdict.decision == "allow"
        assert verdict.effective_model_tier == "expensive"



class TestRoutePreference:
    """Tests for route_preference primitive."""
    
    def test_route_preference_downgrade_expensive_to_cheap(self, tmp_path):
        """Test downgrade when expensive tier requested on cheap-preferred route."""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text("""
version: "0.1.0"
namespaces:
  default:
    rules:
      - id: "infer-route-preference"
        primitive: route_preference
        route_name: "/infer"
        prefer_tier: cheap
""")
        
        engine = YAMLPolicyEngine(str(policy_path))
        verdict = engine.evaluate(
            budget_namespace=None,
            route_name="/infer",
            model_tier="expensive",
            telemetry_path=None
        )
        
        assert verdict.decision == "downgrade"
        assert verdict.reason == "route_prefers_cheap"
        assert verdict.effective_model_tier == "cheap"
        assert verdict.policy_id == "infer-route-preference"
        assert verdict.primitive == "route_preference"
    
    def test_route_preference_allow_when_already_cheap(self, tmp_path):
        """Test allow when cheap tier already requested."""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text("""
version: "0.1.0"
namespaces:
  default:
    rules:
      - id: "infer-route-preference"
        primitive: route_preference
        route_name: "/infer"
        prefer_tier: cheap
""")
        
        engine = YAMLPolicyEngine(str(policy_path))
        verdict = engine.evaluate(
            budget_namespace=None,
            route_name="/infer",
            model_tier="cheap",
            telemetry_path=None
        )
        
        assert verdict.decision == "allow"
        assert verdict.effective_model_tier == "cheap"
    
    def test_route_preference_allow_when_route_not_matched(self, tmp_path):
        """Test allow when route doesn't match rule."""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text("""
version: "0.1.0"
namespaces:
  default:
    rules:
      - id: "infer-route-preference"
        primitive: route_preference
        route_name: "/infer"
        prefer_tier: cheap
""")
        
        engine = YAMLPolicyEngine(str(policy_path))
        verdict = engine.evaluate(
            budget_namespace=None,
            route_name="/other-route",
            model_tier="expensive",
            telemetry_path=None
        )
        
        assert verdict.decision == "allow"
        assert verdict.effective_model_tier == "expensive"
    
    def test_budget_threshold_and_route_preference_evaluated_in_order(self, tmp_path):
        """Test that both primitives are evaluated in order."""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text("""
version: "0.1.0"
namespaces:
  test:
    rules:
      - id: "budget-cap"
        primitive: budget_threshold
        period: hourly
        limit_usd: 0.50
        action: deny
        deny_reason: "budget_exceeded"
      
      - id: "route-pref"
        primitive: route_preference
        route_name: "/infer"
        prefer_tier: cheap
""")
        
        # Test 1: budget_threshold triggers first (deny)
        telemetry_path = tmp_path / "telemetry.jsonl"
        now = datetime.utcnow()
        record = {
            "timestamp": (now - timedelta(minutes=10)).isoformat() + "Z",
            "request_id": "req-1",
            "budget_namespace": "test",
            "estimated_cost_usd": 0.60
        }
        telemetry_path.write_text(json.dumps(record) + "\n")
        
        engine = YAMLPolicyEngine(str(policy_path))
        verdict = engine.evaluate(
            budget_namespace="test",
            route_name="/infer",
            model_tier="expensive",
            telemetry_path=str(telemetry_path)
        )
        
        # budget_threshold should trigger first
        assert verdict.decision == "deny"
        assert verdict.primitive == "budget_threshold"
        
        # Test 2: budget under limit, route_preference triggers
        telemetry_path.write_text("")  # Empty telemetry
        
        verdict = engine.evaluate(
            budget_namespace="test",
            route_name="/infer",
            model_tier="expensive",
            telemetry_path=str(telemetry_path)
        )
        
        # route_preference should trigger
        assert verdict.decision == "downgrade"
        assert verdict.primitive == "route_preference"
        assert verdict.effective_model_tier == "cheap"



class TestCostAnomaly:
    """Tests for cost_anomaly primitive."""
    
    def test_anomaly_detected_returns_allow_with_reason(self, tmp_path):
        """Test that cost anomaly is detected and returns allow with descriptive reason."""
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
        threshold_multiplier: 2.0
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        # Create telemetry with baseline costs
        telemetry_path = tmp_path / "telemetry.jsonl"
        now = datetime.utcnow()
        
        # Historical baseline: 3 requests at ~0.01 each
        records = [
            {
                "timestamp": (now - timedelta(hours=12)).isoformat() + "Z",
                "request_id": "req-1",
                "use_case": "summarize",
                "estimated_cost_usd": 0.01
            },
            {
                "timestamp": (now - timedelta(hours=6)).isoformat() + "Z",
                "request_id": "req-2",
                "use_case": "summarize",
                "estimated_cost_usd": 0.01
            },
            {
                "timestamp": (now - timedelta(hours=1)).isoformat() + "Z",
                "request_id": "req-3",
                "use_case": "summarize",
                "estimated_cost_usd": 0.01
            }
        ]
        
        with open(telemetry_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        
        engine = YAMLPolicyEngine(str(policy_path))
        
        # Current request cost is 0.03, which exceeds baseline (0.01) * 2.0
        verdict = engine.evaluate(
            budget_namespace="default",
            route_name="/answer-routed",
            model_tier="cheap",
            telemetry_path=str(telemetry_path),
            feature_id="summarize",
            current_estimated_cost=0.03
        )
        
        # Should return allow with reason
        assert verdict.decision == "allow"
        assert verdict.reason is not None
        assert "cost_anomaly_detected" in verdict.reason
        assert "current=0.03" in verdict.reason or "current=0.0300" in verdict.reason
        assert verdict.policy_id == "anomaly-detector"
        assert verdict.primitive == "cost_anomaly"
    
    def test_no_anomaly_returns_allow_without_reason(self, tmp_path):
        """Test that no anomaly returns allow without reason."""
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
        threshold_multiplier: 2.0
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        # Create telemetry with baseline costs
        telemetry_path = tmp_path / "telemetry.jsonl"
        now = datetime.utcnow()
        
        records = [
            {
                "timestamp": (now - timedelta(hours=12)).isoformat() + "Z",
                "request_id": "req-1",
                "use_case": "summarize",
                "estimated_cost_usd": 0.01
            },
            {
                "timestamp": (now - timedelta(hours=6)).isoformat() + "Z",
                "request_id": "req-2",
                "use_case": "summarize",
                "estimated_cost_usd": 0.01
            }
        ]
        
        with open(telemetry_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        
        engine = YAMLPolicyEngine(str(policy_path))
        
        # Current request cost is 0.015, which does NOT exceed baseline (0.01) * 2.0
        verdict = engine.evaluate(
            budget_namespace="default",
            route_name="/answer-routed",
            model_tier="cheap",
            telemetry_path=str(telemetry_path),
            feature_id="summarize",
            current_estimated_cost=0.015
        )
        
        # Should return allow without reason
        assert verdict.decision == "allow"
        assert verdict.reason is None
        assert verdict.policy_id is None
        assert verdict.primitive is None
    
    def test_missing_telemetry_returns_allow(self, tmp_path):
        """Test that missing telemetry file returns allow."""
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
        threshold_multiplier: 2.0
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        engine = YAMLPolicyEngine(str(policy_path))
        
        # Telemetry file doesn't exist
        verdict = engine.evaluate(
            budget_namespace="default",
            route_name="/answer-routed",
            model_tier="cheap",
            telemetry_path=str(tmp_path / "nonexistent.jsonl"),
            feature_id="summarize",
            current_estimated_cost=0.05
        )
        
        # Should return allow without reason (safe default)
        assert verdict.decision == "allow"
        assert verdict.reason is None
    
    def test_empty_telemetry_returns_allow(self, tmp_path):
        """Test that empty telemetry file returns allow."""
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
        threshold_multiplier: 2.0
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        # Create empty telemetry file
        telemetry_path = tmp_path / "telemetry.jsonl"
        telemetry_path.write_text("")
        
        engine = YAMLPolicyEngine(str(policy_path))
        
        verdict = engine.evaluate(
            budget_namespace="default",
            route_name="/answer-routed",
            model_tier="cheap",
            telemetry_path=str(telemetry_path),
            feature_id="summarize",
            current_estimated_cost=0.05
        )
        
        # Should return allow without reason (safe default)
        assert verdict.decision == "allow"
        assert verdict.reason is None
    
    def test_different_feature_id_returns_allow(self, tmp_path):
        """Test that rule only applies to specified feature_id."""
        # Create policy with cost_anomaly rule for "summarize"
        policy_content = """
version: "0.1.0"
namespaces:
  default:
    rules:
      - id: "anomaly-detector"
        primitive: cost_anomaly
        feature_id: "summarize"
        baseline_window_hours: 24
        threshold_multiplier: 2.0
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        # Create telemetry with baseline costs for "summarize"
        telemetry_path = tmp_path / "telemetry.jsonl"
        now = datetime.utcnow()
        
        records = [
            {
                "timestamp": (now - timedelta(hours=12)).isoformat() + "Z",
                "request_id": "req-1",
                "use_case": "summarize",
                "estimated_cost_usd": 0.01
            }
        ]
        
        with open(telemetry_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        
        engine = YAMLPolicyEngine(str(policy_path))
        
        # Request is for "qa" feature, not "summarize"
        verdict = engine.evaluate(
            budget_namespace="default",
            route_name="/answer-routed",
            model_tier="cheap",
            telemetry_path=str(telemetry_path),
            feature_id="qa",
            current_estimated_cost=0.10
        )
        
        # Should return allow without reason (rule doesn't apply)
        assert verdict.decision == "allow"
        assert verdict.reason is None
    
    def test_missing_parameters_returns_allow(self, tmp_path):
        """Test that missing required parameters returns safe allow."""
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
        threshold_multiplier: 2.0
"""
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(policy_content)
        
        telemetry_path = tmp_path / "telemetry.jsonl"
        telemetry_path.write_text("")
        
        engine = YAMLPolicyEngine(str(policy_path))
        
        # Missing feature_id
        verdict = engine.evaluate(
            budget_namespace="default",
            route_name="/answer-routed",
            model_tier="cheap",
            telemetry_path=str(telemetry_path),
            feature_id=None,
            current_estimated_cost=0.05
        )
        assert verdict.decision == "allow"
        
        # Missing current_estimated_cost
        verdict = engine.evaluate(
            budget_namespace="default",
            route_name="/answer-routed",
            model_tier="cheap",
            telemetry_path=str(telemetry_path),
            feature_id="summarize",
            current_estimated_cost=None
        )
        assert verdict.decision == "allow"
