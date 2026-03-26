"""HTTP request and response schemas."""
from typing import Literal

from pydantic import BaseModel, field_validator


class InferRequest(BaseModel):
    """Inference request schema aligned with llmscope structured context."""

    prompt: str
    tenant_id: str
    caller_id: str | None = None
    feature_id: str | None = None
    experiment_id: str | None = None
    budget_namespace: str | None = None
    model_tier: Literal["cheap", "expensive"] = "cheap"
    route_name: str = "/answer-routed"

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("prompt must not be empty")
        return v

    @field_validator("tenant_id")
    @classmethod
    def tenant_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("tenant_id must not be empty")
        return v


class InferResponse(BaseModel):
    """Inference response schema."""

    request_id: str
    answer: str
    selected_model: str
    estimated_cost_usd: float
    tokens_in: int
    tokens_out: int
    policy_decision: str
    policy_reason: str | None = None
    effective_model_tier: str
