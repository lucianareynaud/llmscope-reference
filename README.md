# llmscope-reference

Reference workload demonstrating runtime economics and operational governance for LLM requests.

## Operational Questions This Answers

This reference application demonstrates how to answer five critical operational questions about LLM usage:

1. **Which tenant or feature is burning the most margin per request?**
2. **Which experiment increased cost without improving outcome?**
3. **Which fallbacks or routing choices are masking latency?**
4. **Which budget namespaces are triggering downgrades or denials?**
5. **Which routes or features are no longer margin-safe?**

These questions are answered through structured telemetry, local policy decisions, and DuckDB-backed queries over operational artifacts.

## Quick Start

### Installation

```bash
# Clone and install
git clone <repository-url>
cd llmscope-reference
pip install -e .[dev]
```

### Environment Variables

```bash
export TELEMETRY_PATH="artifacts/logs/telemetry.jsonl"
export DECISIONS_PATH="artifacts/logs/policy_decisions.jsonl"
export OTEL_SDK_DISABLED=true  # For local development
```

### Start the Server

```bash
uvicorn app.main:app --reload
```

### Example: Allow Flow

Request that passes policy and executes:

```bash
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Summarize this document",
    "tenant_id": "acme-corp",
    "feature_id": "summarize",
    "model_tier": "cheap"
  }'
```

Response:

```json
{
  "request_id": "req-20240324-abc123",
  "answer": "Here is the summary...",
  "selected_model": "gpt-4o-mini",
  "estimated_cost_usd": 0.0023,
  "tokens_in": 150,
  "tokens_out": 75,
  "policy_decision": "allow",
  "effective_model_tier": "cheap"
}
```

### Example: Deny Flow

Request that exceeds budget and is denied:

```bash
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Analyze this data",
    "tenant_id": "demo-tenant",
    "budget_namespace": "demo",
    "model_tier": "expensive"
  }'
```

Response (HTTP 402):

```json
{
  "error": "budget_exceeded",
  "reason": "Hourly budget exceeded for demo namespace",
  "policy_id": "demo-hourly-cap"
}
```

## Operational Queries

After running requests, query the operational artifacts to answer the canonical questions.

### 1. Cost by Tenant and Feature

**Question:** Which tenant or feature is burning the most margin per request?

```bash
python3 -m reporting.queries cost_by_tenant_and_feature
```

Example output:

```json
[
  {
    "tenant_id": "acme-corp",
    "feature_id": "summarize",
    "total_cost_usd": 2.45,
    "avg_cost_usd": 0.0245,
    "request_count": 100
  },
  {
    "tenant_id": "demo-tenant",
    "feature_id": "qa",
    "total_cost_usd": 1.20,
    "avg_cost_usd": 0.0400,
    "request_count": 30
  }
]
```

### 2. Experiment Cost vs Outcome

**Question:** Which experiment increased cost without improving outcome?

```bash
python3 -m reporting.queries experiment_cost_vs_outcome
```

Example output:

```json
[
  {
    "experiment_id": "exp-gpt4-turbo",
    "avg_tokens_in": 450.0,
    "avg_tokens_out": 200.0,
    "avg_cost_usd": 0.0850,
    "success_rate": 0.92,
    "request_count": 50
  },
  {
    "experiment_id": "exp-gpt4-mini",
    "avg_tokens_in": 420.0,
    "avg_tokens_out": 180.0,
    "avg_cost_usd": 0.0120,
    "success_rate": 0.94,
    "request_count": 150
  }
]
```

### 3. Budget Pressure by Namespace

**Question:** Which budget namespaces are triggering downgrades or denials?

```bash
python3 -m reporting.queries budget_pressure_by_namespace
```

Example output:

```json
[
  {
    "budget_namespace": "demo",
    "allow_count": 45,
    "downgrade_count": 12,
    "deny_count": 8,
    "total_count": 65
  },
  {
    "budget_namespace": "default",
    "allow_count": 200,
    "downgrade_count": 5,
    "deny_count": 0,
    "total_count": 205
  }
]
```

### 4. Fallback Latency Masking

**Question:** Which fallbacks or routing choices are masking latency?

```bash
python3 -m reporting.queries fallback_latency_masking
```

Example output:

```json
[
  {
    "route_name": "/answer-routed",
    "is_fallback": true,
    "p95_latency_ms": 850.0,
    "avg_latency_ms": 620.0,
    "request_count": 25
  },
  {
    "route_name": "/answer-routed",
    "is_fallback": false,
    "p95_latency_ms": 320.0,
    "avg_latency_ms": 180.0,
    "request_count": 175
  }
]
```

### 5. Unsafe Routes

**Question:** Which routes or features are no longer margin-safe?

```bash
python3 -m reporting.queries unsafe_routes --threshold 0.05
```

Example output:

```json
[
  {
    "route_name": "/answer-routed",
    "avg_cost_usd": 0.0720,
    "max_cost_usd": 0.1500,
    "request_count": 45
  }
]
```

## Policy Configuration

Policy is defined in `config/policy.yaml` using three primitives:

### 1. Budget Threshold

Enforces spending limits per namespace over time windows:

```yaml
- id: "demo-hourly-cap"
  primitive: budget_threshold
  period: hourly
  limit_usd: 1.00
  action: deny
  deny_reason: "Hourly budget exceeded for demo namespace"
```

Actions: `deny` (reject request) or `downgrade` (switch to cheaper tier)

### 2. Route Preference

Downgrades expensive requests on routes configured for cheap tiers:

```yaml
- id: "demo-route-preference"
  primitive: route_preference
  route_name: "/answer-routed"
  prefer_tier: cheap
```

### 3. Cost Anomaly

Alerts when request cost exceeds historical baseline (always allows, never blocks):

```yaml
- id: "demo-cost-anomaly"
  primitive: cost_anomaly
  feature_id: "summarize"
  baseline_window_hours: 24
  threshold_multiplier: 3.0
  action: alert
```

## Architecture

```
┌─────────────────┐
│  FastAPI App    │  Validates requests, constructs LLMRequestContext
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ YAMLPolicyEngine│  Evaluates: allow / downgrade / deny
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    llmscope     │  Core library handles provider routing, cost tracking
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ JSONL Artifacts │  telemetry.jsonl, policy_decisions.jsonl
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ DuckDB Queries  │  Answers the five operational questions
└─────────────────┘
```

### Request Lifecycle

1. HTTP request enters FastAPI app
2. App validates and constructs `LLMRequestContext`
3. Policy engine evaluates pre-dispatch
4. If `deny`: return HTTP 402, log decision
5. If `downgrade`: override tier, call llmscope
6. If `allow`: call llmscope unchanged
7. Log decision with cost and latency
8. Return response to client

## Boundary with llmscope

This repository is a **reference application** that demonstrates consumption of the `llmscope` runtime contract. It is not a product, not a platform, and not an alternative implementation.

**llmscope (core library) owns:**
- Provider abstraction and routing
- Cost estimation and normalization
- OpenTelemetry emission
- Runtime types (`LLMRequestContext`, `GatewayResult`)

**llmscope-reference (this repo) owns:**
- Concrete YAML policy engine
- Local decision artifacts (JSONL)
- DuckDB operational queries
- Reference HTTP API surface

This separation proves that the `llmscope` runtime contract is sufficient for building operational governance without coupling to specific policy engines or artifact stores.

## Dependencies

This repository depends on `llmscope` via Git SHA:

```
llmscope @ git+https://github.com/lucianareynaud/llmscope.git@5d3fdfbc8558a297b95491c5f332c43a1588b627
```

The pinned SHA corresponds to the commit that introduced `LLMRequestContext` with attribution fields (`tenant_id`, `caller_id`, `feature_id`, `experiment_id`, `budget_namespace`).

## Testing

```bash
# Run all tests
OTEL_SDK_DISABLED=true pytest -q

# Run specific test modules
pytest tests/test_policy.py -v
pytest tests/test_queries.py -v
pytest tests/test_api.py -v
```

All tests use fixtures and mocks - no external API calls or real providers.

## Development

### Project Structure

```
llmscope-reference/
├── app/              # FastAPI application
│   ├── api.py        # POST /infer endpoint
│   ├── main.py       # App initialization, OTEL lifecycle
│   ├── schemas.py    # Request/response models
│   └── settings.py   # Configuration
├── policy/           # Policy engine
│   ├── engine.py     # YAMLPolicyEngine with three primitives
│   ├── loader.py     # YAML config parsing
│   ├── models.py     # PolicyVerdict, PolicyDecisionRecord
│   └── log.py        # JSONL decision logging
├── reporting/        # Query layer
│   └── queries.py    # Five canonical queries
├── config/
│   └── policy.yaml   # Policy configuration
├── artifacts/logs/   # Operational artifacts (gitignored)
└── tests/            # Test suite
```

### Adding a New Policy Rule

1. Add rule to `config/policy.yaml` under appropriate namespace
2. If using existing primitive (`budget_threshold`, `route_preference`, `cost_anomaly`), no code changes needed
3. Reload policy: engine automatically picks up changes on next request
4. Test with curl or pytest

### Adding a New Query

1. Add function to `reporting/queries.py`
2. Use DuckDB `read_json_auto()` over telemetry or decisions JSONL
3. Return `list[dict]` with native Python types
4. Add CLI case in `__main__` block
5. Add tests in `tests/test_queries.py`

## License

This is a reference implementation for demonstration purposes.
