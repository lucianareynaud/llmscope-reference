"""YAML-based policy engine."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from policy.loader import load_policy
from policy.models import PolicyVerdict


class YAMLPolicyEngine:
    """Policy engine that evaluates rules from YAML configuration."""

    def __init__(self, config_path: str) -> None:
        """Initialize engine with policy configuration.

        Args:
            config_path: Path to YAML policy file
        """
        self.config_path = config_path
        self.config = load_policy(config_path)

    def reload(self) -> None:
        """Reload policy configuration from disk."""
        self.config = load_policy(self.config_path)

    def evaluate(
        self,
        budget_namespace: str | None,
        route_name: str,
        model_tier: str,
        telemetry_path: str | None = None,
        feature_id: str | None = None,
        current_estimated_cost: float | None = None,
    ) -> PolicyVerdict:
        """Evaluate policy rules for a request.

        Args:
            budget_namespace: Budget namespace for the request (None uses "default")
            route_name: Route name for the request
            model_tier: Requested model tier
            telemetry_path: Path to telemetry JSONL for budget calculations
            feature_id: Feature ID for cost anomaly detection
            current_estimated_cost: Current request estimated cost for anomaly detection

        Returns:
            PolicyVerdict with decision and metadata
        """
        namespace = budget_namespace or "default"

        if namespace not in self.config.namespaces:
            # Unknown namespace defaults to "default"
            namespace = "default"
            if namespace not in self.config.namespaces:
                # No default namespace, allow by default
                return PolicyVerdict(
                    decision="allow",
                    reason=None,
                    effective_model_tier=model_tier,
                    policy_id=None,
                    primitive=None
                )

        ns_config = self.config.namespaces[namespace]

        # Evaluate rules in order
        for rule in ns_config.rules:
            if rule.primitive == "budget_threshold":
                verdict = self._evaluate_budget_threshold(
                    rule, budget_namespace, telemetry_path
                )
                if verdict.decision != "allow":
                    # First non-allow verdict wins
                    return PolicyVerdict(
                        decision=verdict.decision,
                        reason=verdict.reason,
                        effective_model_tier=verdict.effective_model_tier or model_tier,
                        policy_id=rule.id,
                        primitive="budget_threshold"
                    )
            elif rule.primitive == "route_preference":
                verdict = self._evaluate_route_preference(
                    rule, route_name, model_tier
                )
                if verdict.decision != "allow":
                    # First non-allow verdict wins
                    return PolicyVerdict(
                        decision=verdict.decision,
                        reason=verdict.reason,
                        effective_model_tier=verdict.effective_model_tier or model_tier,
                        policy_id=rule.id,
                        primitive="route_preference"
                    )
            elif rule.primitive == "cost_anomaly":
                verdict = self._evaluate_cost_anomaly(
                    rule, feature_id, current_estimated_cost, telemetry_path
                )
                # cost_anomaly always returns allow, but may have a reason
                if verdict.reason:
                    return PolicyVerdict(
                        decision="allow",
                        reason=verdict.reason,
                        effective_model_tier=model_tier,
                        policy_id=rule.id,
                        primitive="cost_anomaly"
                    )

        # All rules passed, allow
        return PolicyVerdict(
            decision="allow",
            reason=None,
            effective_model_tier=model_tier,
            policy_id=None,
            primitive=None
        )

    def _evaluate_budget_threshold(
        self,
        rule,
        budget_namespace: str | None,
        telemetry_path: str | None
    ) -> PolicyVerdict:
        """Evaluate budget_threshold primitive.

        Args:
            rule: PolicyRule configuration
            budget_namespace: Budget namespace to check
            telemetry_path: Path to telemetry JSONL

        Returns:
            PolicyVerdict
        """
        # Safe default if no telemetry path or file doesn't exist
        if not telemetry_path:
            return PolicyVerdict(decision="allow")

        telemetry_file = Path(telemetry_path)
        if not telemetry_file.exists() or telemetry_file.stat().st_size == 0:
            return PolicyVerdict(decision="allow")

        # Calculate window start based on period
        now = datetime.now(UTC)
        if rule.period == "hourly":
            window_start = now - timedelta(hours=1)
        elif rule.period == "daily":
            window_start = now - timedelta(days=1)
        else:
            # Unknown period, allow
            return PolicyVerdict(decision="allow")

        window_start_iso = window_start.isoformat() + "Z"

        # Query accumulated cost in window
        try:
            conn = duckdb.connect(":memory:")

            # File path in FROM clause cannot be parameterized (table function arg)
            # Only WHERE clause values are parameterized for SQL injection safety
            if budget_namespace:
                query = f"""
                    SELECT COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost
                    FROM read_json_auto('{telemetry_path}')
                    WHERE timestamp >= ?
                      AND budget_namespace = ?
                """
                result = conn.execute(query, [window_start_iso, budget_namespace]).fetchone()
            else:
                query = f"""
                    SELECT COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost
                    FROM read_json_auto('{telemetry_path}')
                    WHERE timestamp >= ?
                      AND budget_namespace IS NULL
                """
                result = conn.execute(query, [window_start_iso]).fetchone()

            window_cost = float(result[0]) if result else 0.0
            conn.close()
        except Exception:
            # Query failed, safe default is allow
            return PolicyVerdict(decision="allow")

        # Check if limit exceeded
        if window_cost >= rule.limit_usd:
            if rule.action == "deny":
                return PolicyVerdict(
                    decision="deny",
                    reason=rule.deny_reason or "budget_exceeded",
                    effective_model_tier=None,
                    policy_id=rule.id,
                    primitive="budget_threshold"
                )
            elif rule.action == "downgrade":
                return PolicyVerdict(
                    decision="downgrade",
                    reason="budget_exceeded",
                    effective_model_tier=rule.downgrade_to_tier or "cheap",
                    policy_id=rule.id,
                    primitive="budget_threshold"
                )

        return PolicyVerdict(decision="allow")


    def _evaluate_route_preference(
        self,
        rule,
        route_name: str,
        model_tier: str
    ) -> PolicyVerdict:
        """Evaluate route_preference primitive.

        Args:
            rule: PolicyRule configuration
            route_name: Route name from request
            model_tier: Requested model tier

        Returns:
            PolicyVerdict
        """
        # Check if this rule applies to the current route
        if rule.route_name and rule.route_name != route_name:
            # Rule doesn't apply to this route
            return PolicyVerdict(decision="allow")

        # Check if requested tier conflicts with preferred tier
        if model_tier == "expensive" and rule.prefer_tier == "cheap":
            return PolicyVerdict(
                decision="downgrade",
                reason="route_prefers_cheap",
                effective_model_tier="cheap",
                policy_id=rule.id,
                primitive="route_preference"
            )

        # No conflict, allow
        return PolicyVerdict(decision="allow")

    def _evaluate_cost_anomaly(
        self,
        rule,
        feature_id: str | None,
        current_estimated_cost: float | None,
        telemetry_path: str | None
    ) -> PolicyVerdict:
        """Evaluate cost_anomaly primitive.

        This primitive detects cost anomalies by comparing current request cost
        against historical baseline. It always returns 'allow' but may include
        a descriptive reason when an anomaly is detected.

        Args:
            rule: PolicyRule configuration
            feature_id: Feature ID to check baseline for
            current_estimated_cost: Estimated cost for current request
            telemetry_path: Path to telemetry JSONL

        Returns:
            PolicyVerdict with decision='allow' and optional reason
        """
        # Safe defaults - always allow
        if not telemetry_path or not feature_id or current_estimated_cost is None:
            return PolicyVerdict(decision="allow")

        telemetry_file = Path(telemetry_path)
        if not telemetry_file.exists() or telemetry_file.stat().st_size == 0:
            return PolicyVerdict(decision="allow")

        # Check if rule applies to this feature
        if rule.feature_id and rule.feature_id != feature_id:
            return PolicyVerdict(decision="allow")

        # Calculate baseline window
        baseline_hours = rule.baseline_window_hours or 24
        threshold_mult = rule.threshold_multiplier or 2.0

        now = datetime.now(UTC)
        window_start = now - timedelta(hours=baseline_hours)
        window_start_iso = window_start.isoformat() + "Z"

        # Query baseline cost for this feature
        try:
            conn = duckdb.connect(":memory:")

            # File path in FROM clause cannot be parameterized (table function arg)
            # Only WHERE clause values are parameterized for SQL injection safety
            query = f"""
                SELECT AVG(estimated_cost_usd) as avg_cost
                FROM read_json_auto('{telemetry_path}')
                WHERE timestamp >= ?
                  AND use_case = ?
                  AND estimated_cost_usd IS NOT NULL
            """

            result = conn.execute(query, [window_start_iso, feature_id]).fetchone()
            baseline_cost = float(result[0]) if result and result[0] is not None else None
            conn.close()
        except Exception:
            # Query failed, safe default is allow without reason
            return PolicyVerdict(decision="allow")

        # Check for anomaly
        if baseline_cost is not None and current_estimated_cost > (baseline_cost * threshold_mult):
            reason = (
                f"cost_anomaly_detected: current={current_estimated_cost:.4f} "
                f"exceeds baseline={baseline_cost:.4f} * {threshold_mult}"
            )
            return PolicyVerdict(
                decision="allow",
                reason=reason,
                effective_model_tier=None,
                policy_id=rule.id,
                primitive="cost_anomaly"
            )

        # No anomaly detected
        return PolicyVerdict(decision="allow")
