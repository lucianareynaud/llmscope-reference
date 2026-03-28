"""FastAPI gateway endpoint."""
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from policy.engine import YAMLPolicyEngine
from policy.log import PolicyDecisionLog
from policy.models import PolicyDecisionRecord

from app.schemas import InferRequest, InferResponse
from app.settings import BASE_DIR, DECISIONS_PATH, TELEMETRY_PATH
from llmscope import LLMRequestContext, call_llm, estimate_cost, get_model_for_tier

router = APIRouter()

# Initialize policy engine with default config
policy_engine = YAMLPolicyEngine(str(BASE_DIR / "config" / "policy.yaml"))


@router.post("/infer", response_model=InferResponse)
async def infer(request: InferRequest) -> InferResponse:
    """Inference endpoint with policy evaluation.

    Flow:
    1. Validate request (Pydantic)
    2. Construct LLMRequestContext
    3. Evaluate policy
    4. If deny: log decision and return HTTP 402
    5. If downgrade: override tier
    6. Call llmscope.call_llm()
    7. Log decision with actual cost/latency
    8. Return response
    """
    # Construct LLMRequestContext from request
    context = LLMRequestContext(
        tenant_id=request.tenant_id,
        caller_id=request.caller_id,
        use_case=request.feature_id,
        feature_id=request.feature_id,
        experiment_id=request.experiment_id,
        budget_namespace=request.budget_namespace
    )

    # Pre-dispatch cost estimation
    estimate_model = get_model_for_tier(request.route_name, request.model_tier)
    tokens_in_estimate = int(len(request.prompt.split()) * 1.3)
    tokens_out_estimate = 256
    pre_dispatch_cost = estimate_cost(
        estimate_model, tokens_in_estimate, tokens_out_estimate
    )

    # Evaluate policy
    verdict = policy_engine.evaluate(
        budget_namespace=request.budget_namespace,
        route_name=request.route_name,
        model_tier=request.model_tier,
        telemetry_path=TELEMETRY_PATH,
        feature_id=request.feature_id,
        current_estimated_cost=pre_dispatch_cost,
    )

    # Handle denial
    if verdict.decision == "deny":
        # Log denial before returning 402
        record = PolicyDecisionRecord(
            timestamp=datetime.now(UTC).isoformat() + "Z",
            request_id="denied-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S%f"),
            tenant_id=request.tenant_id,
            caller_id=request.caller_id,
            feature_id=request.feature_id,
            experiment_id=request.experiment_id,
            budget_namespace=request.budget_namespace,
            route_name=request.route_name,
            requested_model_tier=request.model_tier,
            effective_model_tier=request.model_tier,
            primitive=verdict.primitive or "unknown",
            decision=verdict.decision,
            reason=verdict.reason,
            policy_id=verdict.policy_id,
            estimated_cost_usd=None,
            latency_ms=None,
            window_cost_usd=None,
            window_limit_usd=None,
            policy_version=policy_engine.config.version
        )
        PolicyDecisionLog.append(record, DECISIONS_PATH)

        raise HTTPException(
            status_code=402,
            detail={
                "error": "budget_exceeded",
                "reason": verdict.reason or "policy_denied",
                "policy_id": verdict.policy_id
            }
        )

    # Determine effective tier
    if verdict.decision == "downgrade":
        effective_tier = verdict.effective_model_tier or "cheap"
    else:
        effective_tier = request.model_tier

    # Call llmscope and measure latency
    start_time = datetime.now(UTC)
    result = await call_llm(
        prompt=request.prompt,
        model_tier=effective_tier,
        route_name=request.route_name,
        context=context
    )
    end_time = datetime.now(UTC)
    latency_ms = (end_time - start_time).total_seconds() * 1000

    # Log decision with actual cost and latency
    record = PolicyDecisionRecord(
        timestamp=start_time.isoformat() + "Z",
        request_id=result.request_id,
        tenant_id=request.tenant_id,
        caller_id=request.caller_id,
        feature_id=request.feature_id,
        experiment_id=request.experiment_id,
        budget_namespace=request.budget_namespace,
        route_name=request.route_name,
        requested_model_tier=request.model_tier,
        effective_model_tier=effective_tier,
        primitive=verdict.primitive or "none",
        decision=verdict.decision,
        reason=verdict.reason,
        policy_id=verdict.policy_id,
        estimated_cost_usd=result.estimated_cost_usd,
        latency_ms=latency_ms,
        window_cost_usd=None,
        window_limit_usd=None,
        policy_version=policy_engine.config.version
    )
    PolicyDecisionLog.append(record, DECISIONS_PATH)

    # Build response
    return InferResponse(
        request_id=result.request_id,
        answer=result.text,
        selected_model=result.selected_model,
        estimated_cost_usd=result.estimated_cost_usd,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        policy_decision=verdict.decision,
        policy_reason=verdict.reason,
        effective_model_tier=effective_tier
    )
