# llmscope-reference

Reference implementation demonstrating operational governance, cost attribution, and policy control for LLM inference requests in production conditions.

## Purpose

This repository proves that the `llmscope` runtime contract is sufficient for building accountable AI systems. It demonstrates how to consume structured telemetry, apply pre-dispatch policy decisions, persist operational artifacts, and answer critical cost and performance questions without coupling to specific observability platforms or policy engines.

This is infrastructure for production LLM operations, not a demo app or generic AI platform.

## What This Repository Demonstrates

**Implemented and Verified:**

1. **Pre-dispatch policy evaluation** - Three policy primitives (budget_threshold, route_preference, cost_anomaly) that can allow, downgrade, or deny requests before calling LLM providers
2. **Structured cost attribution** - Request context with tenant_id, caller_id, feature_id, experiment_id, budget_namespace flows through llmscope and into decision artifacts
3. **Append-only operational artifacts** - JSONL decision log with fcntl advisory locking for concurrent write safety
4. **DuckDB-backed operational queries** - Five queries answering canonical questions about margin burn, experiment outcomes, budget pressure, latency masking, and cost safety
5. **YAML policy configuration** - Declarative policy rules with namespace isolation and three concrete primitives
6. **OpenTelemetry instrumentation** - FastAPI app instrumented via llmscope's OTEL lifecycle
7. **Test coverage** - 68 tests with no external API dependencies

**Current Limitations:**

- Budget enforcement (`budget_threshold`) and cost anomaly detection (`cost_anomaly`) require telemetry consumption, which is **not yet wired** in the policy evaluation path (hardcoded `telemetry_path=None` in app/api.py)
- Policy decisions are logged, but budget calculations cannot access historical telemetry to enforce limits
- Queries work if llmscope emits telemetry, but policy engine cannot consume it yet
- Provider configuration and routing are handled by llmscope core; this repository does not demonstrate provider setup

## Five Canonical Questions

This reference application is designed to answer:

1. **Which tenant or feature is burning the most margin per request?**
2. **Which experiment increased cost without improving outcome?**
3. **Which fallbacks or routing choices are masking latency?**
4. **Which budget namespaces are triggering downgrades or denials?**
5. **Which routes or features are no longer margin-safe?**

These questions are answered through DuckDB queries over JSONL artifacts emitted by llmscope (telemetry) and this reference app (policy decisions).

## Architecture

```
┌─────────────────┐
│  FastAPI App    │  Validates requests, constructs LLMRequestContext
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ YAMLPolicyEngine│  Pre-dispatch evaluation: allow / downgrade / deny
└────────┬────────┘  (budget_threshold, route_preference, cost_anomaly)
         │
         ▼
┌─────────────────┐
│    llmscope     │  Provider routing, cost tracking, OTEL emission
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ JSONL Artifacts │  policy_decisions.jsonl (this repo)
└─────────────────┘  telemetry.jsonl (llmscope core)
         │
         ▼
┌─────────────────┐
│ DuckDB Queries  │  Five canonical operational queries
└─────────────────┘
```

### Request Lifecycle

1. HTTP POST to `/infer` with prompt, tenant_id, and attribution fields
2. FastAPI validates request, constructs `LLMRequestContext`
3. Policy engine evaluates rules (currently only route_preference is functional)
4. If `deny`: return HTTP 402, log decision, stop
5. If `downgrade`: override model_tier to "cheap"
6. If `allow`: proceed unchanged
7. Call `llmscope.call_llm()` with context
8. Log decision with actual cost and latency
9. Return response to client

## Policy Primitives

### 1. budget_threshold

Enforces spending limits per namespace over time windows.

```yaml
- id: "demo-hourly-cap"
  primitive: budget_threshold
  period: hourly
  limit_usd: 1.00
  action: deny
  deny_reason: "Hourly budget exceeded"
```

**Status:** Implemented but not functional (requires telemetry wiring).

Actions: `deny` (reject request) or `downgrade` (switch to cheap tier).

### 2. route_preference

Downgrades expensive requests on routes configured for cheap tiers.

```yaml
- id: "demo-route-preference"
  primitive: route_preference
  route_name: "/answer-routed"
  prefer_tier: cheap
```

**Status:** Fully functional.

### 3. cost_anomaly

Alerts when request cost exceeds historical baseline. Always allows, never blocks.

```yaml
- id: "demo-cost-anomaly"
  primitive: cost_anomaly
  feature_id: "summarize"
  baseline_window_hours: 24
  threshold_multiplier: 3.0
  action: alert
```

**Status:** Implemented but not functional (requires telemetry wiring).

## Local Setup

### Installation

```bash
git clone <repository-url>
cd llmscope-reference
pip install -e .[dev]
```

### Environment Variables

```bash
export TELEMETRY_PATH="artifacts/logs/telemetry.jsonl"
export DECISIONS_PATH="artifacts/logs/policy_decisions.jsonl"
export OTEL_SDK_DISABLED=true  # For local development without OTEL backend
```

### Start Server

```bash
uvicorn app.main:app --reload
```

Server runs on `http://localhost:8000`.

### Example Request

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

## Operational Queries

Queries read JSONL artifacts and return structured data.

### 1. Cost by Tenant and Feature

```bash
python3 -m reporting.queries cost_by_tenant_and_feature
```

Returns: tenant_id, feature_id, total_cost_usd, avg_cost_usd, request_count

### 2. Experiment Cost vs Outcome

```bash
python3 -m reporting.queries experiment_cost_vs_outcome
```

Returns: experiment_id, avg_tokens_in, avg_tokens_out, avg_cost_usd, success_rate, request_count

### 3. Budget Pressure by Namespace

```bash
python3 -m reporting.queries budget_pressure_by_namespace
```

Returns: budget_namespace, allow_count, downgrade_count, deny_count, total_count

### 4. Fallback Latency Masking

```bash
python3 -m reporting.queries fallback_latency_masking
```

Returns: route_name, is_fallback, p95_latency_ms, avg_latency_ms, request_count

### 5. Unsafe Routes

```bash
python3 -m reporting.queries unsafe_routes --threshold 0.05
```

Returns: route_name, avg_cost_usd, max_cost_usd, request_count

## Testing

```bash
# Run all tests
OTEL_SDK_DISABLED=true pytest -q

# Run specific modules
pytest tests/test_policy.py -v
pytest tests/test_queries.py -v
pytest tests/test_api.py -v
```

68 tests across 7 modules. All tests use fixtures and mocks - no external API calls.

## Repository Structure

```
llmscope-reference/
├── app/              # FastAPI application
│   ├── api.py        # POST /infer endpoint with policy integration
│   ├── main.py       # App initialization, OTEL lifecycle
│   ├── schemas.py    # Request/response Pydantic models
│   └── settings.py   # Configuration (paths, env vars)
├── policy/           # Policy engine
│   ├── engine.py     # YAMLPolicyEngine with three primitives
│   ├── loader.py     # YAML config parsing and validation
│   ├── models.py     # PolicyVerdict, PolicyDecisionRecord
│   └── log.py        # JSONL decision logging with fcntl locking
├── reporting/        # Query layer
│   └── queries.py    # Five DuckDB-backed canonical queries
├── config/
│   └── policy.yaml   # Policy configuration (default, demo namespaces)
├── artifacts/logs/   # Operational artifacts (gitignored)
│   ├── telemetry.jsonl        # Emitted by llmscope core
│   └── policy_decisions.jsonl # Emitted by this app
└── tests/            # 68 tests, no external dependencies
```

## Boundary with llmscope Core

This repository is a **reference application**, not a product or platform.

**llmscope (core library) owns:**
- Provider abstraction and routing
- Cost estimation and normalization
- OpenTelemetry emission
- Telemetry artifact generation
- Runtime types (`LLMRequestContext`, `GatewayResult`)

**llmscope-reference (this repo) owns:**
- Concrete YAML policy engine
- Pre-dispatch policy evaluation
- Local decision artifacts (JSONL)
- DuckDB operational queries
- Reference HTTP API surface

This separation proves that the llmscope runtime contract is sufficient for building operational governance without coupling to specific policy engines, artifact stores, or observability platforms.

## Dependencies

```toml
llmscope @ git+https://github.com/lucianareynaud/llmscope.git@5d3fdfbc8558a297b95491c5f332c43a1588b627
fastapi>=0.110
uvicorn[standard]>=0.29
pyyaml>=6.0
duckdb>=0.10
pydantic>=2.0
```

Pinned llmscope SHA corresponds to the commit introducing `LLMRequestContext` with attribution fields.

## Current Limitations

1. **Telemetry consumption not wired** - Policy engine cannot access telemetry for budget enforcement or cost anomaly detection (hardcoded `telemetry_path=None`)
2. **No provider configuration examples** - llmscope core handles providers, but setup is not demonstrated here
3. **No post-dispatch policy** - Only pre-dispatch evaluation is implemented
4. **No hot reload** - Policy changes require engine reload or restart
5. **POSIX-only file locking** - fcntl advisory locking is not portable to Windows
6. **No authentication or RBAC** - This is a reference implementation, not a production service
7. **No UI or dashboard** - Queries are CLI-only

## Non-Goals

This repository intentionally does not include:

- Web dashboard or UI
- Authentication or authorization
- Multi-tenant console
- Plugin system or policy DSL
- Generic analytics platform
- Distributed system architecture
- Streaming inference
- Agent orchestration
- Evaluation pipelines or LLM-as-judge workflows

These may be explored in future work, but are not part of the current scope.

## Near-Term Roadmap

1. **Wire telemetry consumption** - Connect policy engine to llmscope telemetry for budget enforcement
2. **Provider setup documentation** - Document how to configure llmscope providers
3. **Post-dispatch policy** - Add policy evaluation after LLM response (e.g., output validation)
4. **Policy reload endpoint** - Add HTTP endpoint to reload policy without restart
5. **Query API** - Expose queries via HTTP endpoints, not just CLI

## License

Reference implementation for demonstration purposes.
