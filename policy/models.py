"""Policy decision models."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PolicyVerdict:
    """Policy evaluation verdict."""

    decision: Literal["allow", "downgrade", "deny"]
    reason: str | None = None
    effective_model_tier: str | None = None
    policy_id: str | None = None
    primitive: str | None = None


@dataclass
class PolicyDecisionRecord:
    """Policy decision record for JSONL logging."""

    timestamp: str
    request_id: str
    tenant_id: str
    caller_id: str | None
    feature_id: str | None
    experiment_id: str | None
    budget_namespace: str | None
    route_name: str
    requested_model_tier: str
    effective_model_tier: str
    primitive: str
    decision: str
    reason: str | None
    policy_id: str | None
    estimated_cost_usd: float | None
    latency_ms: float | None
    window_cost_usd: float | None
    window_limit_usd: float | None
    policy_version: str

    def to_dict(self) -> dict:
        """Serialize to dict with native types, omitting None values."""
        result = {}
        for key, value in self.__dict__.items():
            if value is not None:
                result[key] = value
        return result
