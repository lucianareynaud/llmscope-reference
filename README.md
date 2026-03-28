# llmscope-reference

Reference workload demonstrating runtime economics and operational governance for LLM inference requests.

## What This Is

A narrow reference application that consumes the `llmscope` runtime contract to apply local policy decisions, persist operational artifacts, and answer a fixed set of cost and performance questions.

This repository demonstrates pre-dispatch policy evaluation, structured cost attribution, append-only JSONL artifacts, and DuckDB-backed queries. It is not a product, platform, or observability tool.

## Five Operational Questions

This application answers:

1. Which tenant or feature is burning the most margin per request?
2. Which experiment increased cost without improving outcome?
3. Which fallbacks or routing choices are masking latency?
4. Which budget namespaces are triggering downgrades or denials?
5. Which routes or features are no longer margin-safe?

Query results are derived from JSONL artifacts: `telemetry.jsonl` (emitted by llmscope) and `policy_decisions.jsonl` (emitted by this app).

## What Is Implemented

**Policy Engine** (`policy/engine.py`)
- Three primitives: `budget_threshold`, `route_preference`, `cost_anomaly`
- Pre-dispatch evaluation returns allow, downgrade, or deny
- DuckDB queries against local telemetry JSONL for budget and anomaly checks
- YAML configuration with namespace isolation

**Request Lifecycle** (`app/api.py`)
- FastAPI endpoint validates requests, constructs `LLMRequestContext`
- Pre-dispatch cost estimation using llmscope public API
- Policy evaluation before provider call
- Deny path returns HTTP 402 without calling provider
- Downgrade path mutates model_tier to "cheap"
- Decision logging to JSONL with fcntl advisory locking

**Query Layer** (`reporting/queries.py`)
- Five DuckDB-backed queries answering canonical questions
- CLI interface: `python -m reporting.queries <query_name>`
- Handles missing or empty JSONL files gracefully

**Testing** (`tests/`)
- 72 tests across 8 modules
- No external API calls (mocked llmscope, fixture-based)
- CI runs on Python 3.11 and 3.12

## What Is Not Implemented

- Provider configuration examples (llmscope core handles providers, not demonstrated here)
- Post-dispatch policy evaluation (only pre-dispatch exists)
- HTTP query API (queries are CLI-only)
- Policy hot reload (requires engine reload or restart)
- Authentication or RBAC
- Web dashboard or UI
- Windows support (fcntl locking is POSIX-only)

## Request Lifecycle

1. HTTP POST to `/infer` with prompt, tenant_id, and attribution fields
2. FastAPI validates request, constructs `LLMRequestContext`
3. Pre-dispatch cost estimation using `llmscope.get_model_for_tier()` and `estimate_cost()`
4. Policy engine evaluates rules against local telemetry JSONL
5. If `deny`: return HTTP 402, log decision, stop
6. If `downgrade`: override model_tier to "cheap"
7. If `allow`: proceed unchanged
8. Call `llmscope.call_llm()` with context
9. Log decision to `policy_decisions.jsonl`
10. Return response to client

```
HTTP Request → FastAPI → Policy Engine → llmscope → Provider
                  ↓            ↓            ↓
            LLMRequestContext  ↓       telemetry.jsonl
                          policy_decisions.jsonl
                               ↓
                          DuckDB Queries
```

## Policy Primitives

Three primitives are implemented in `policy/engine.py`:

### 1. budget_threshold

Enforces spending limits per namespace over time windows (hourly or daily).

```yaml
- id: "demo-hourly-cap"
  primitive: budget_threshold
  period: hourly
  limit_usd: 1.00
  action: deny
  deny_reason: "Hourly budget exceeded"
```

Actions: `deny` (reject request) or `downgrade` (switch to cheap tier).

Evaluates against local `telemetry.jsonl` using DuckDB query.

### 2. route_preference

Downgrades requests on routes configured for cheap tiers.

```yaml
- id: "demo-route-preference"
  primitive: route_preference
  route_name: "/answer-routed"
  prefer_tier: cheap
```

Always downgrades if route matches and current tier is not cheap.

### 3. cost_anomaly

Alerts when estimated request cost exceeds historical baseline.

```yaml
- id: "demo-cost-anomaly"
  primitive: cost_anomaly
  feature_id: "summarize"
  baseline_window_hours: 24
  threshold_multiplier: 3.0
  action: alert
```

Always allows request (alert-only, never blocks).

Evaluates against local `telemetry.jsonl` using DuckDB query.

## Installation and Setup

### Requirements

- Python 3.11 or 3.12
- POSIX-compatible OS (macOS, Linux) for fcntl file locking

### Install

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

## Example Request

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

If policy denies the request:

```json
{
  "detail": "Request denied by policy: Hourly budget exceeded"
}
```

HTTP status: 402 Payment Required

## Running Queries

All queries are CLI-based and read from JSONL artifacts.

### 1. Cost by Tenant and Feature

Which tenant or feature burns the most margin per request?

```bash
python -m reporting.queries cost_by_tenant_and_feature
```

Output: `tenant_id`, `feature_id`, `total_cost_usd`, `avg_cost_usd`, `request_count`

### 2. Experiment Cost vs Outcome

Which experiment increased cost without improving outcome?

```bash
python -m reporting.queries experiment_cost_vs_outcome
```

Output: `experiment_id`, `avg_tokens_in`, `avg_tokens_out`, `avg_cost_usd`, `success_rate`, `request_count`

Success rate = proportion of requests with `finish_reason='stop'`

### 3. Budget Pressure by Namespace

Which budget namespaces trigger downgrades or denials?

```bash
python -m reporting.queries budget_pressure_by_namespace
```

Output: `budget_namespace`, `allow_count`, `downgrade_count`, `deny_count`, `total_count`

### 4. Fallback Latency Masking

Which fallbacks or routing choices mask latency?

```bash
python -m reporting.queries fallback_latency_masking
```

Output: `route_name`, `is_fallback`, `p95_latency_ms`, `avg_latency_ms`, `request_count`

### 5. Unsafe Routes

Which routes are no longer economically safe?

```bash
python -m reporting.queries unsafe_routes --threshold 0.05
```

Output: `route_name`, `avg_cost_usd`, `max_cost_usd`, `request_count`

Default threshold: $0.05 per request

## Testing

```bash
# Run all tests
OTEL_SDK_DISABLED=true pytest -q

# Run specific test modules
pytest tests/test_policy.py -v
pytest tests/test_queries.py -v
pytest tests/test_api.py -v
pytest tests/test_telemetry_wiring.py -v
```

72 tests across 8 modules. All tests use fixtures and mocks - no external API calls.

Test coverage:
- Policy engine evaluation (budget_threshold, route_preference, cost_anomaly)
- Request validation and context construction
- Decision logging with concurrent write safety
- DuckDB queries over fixture data
- API integration with mocked llmscope
- Telemetry wiring and pre-dispatch cost estimation

## Repository Structure

```
llmscope-reference/
├── app/                    # FastAPI application
│   ├── api.py              # POST /infer endpoint with policy integration
│   ├── main.py             # App initialization, OTEL lifecycle
│   ├── schemas.py          # Request/response Pydantic models
│   └── settings.py         # Configuration (paths, env vars)
├── policy/                 # Policy engine
│   ├── engine.py           # YAMLPolicyEngine with three primitives
│   ├── loader.py           # YAML config parsing and validation
│   ├── models.py           # PolicyVerdict, PolicyDecisionRecord
│   └── log.py              # JSONL decision logging with fcntl locking
├── reporting/              # Query layer
│   └── queries.py          # Five DuckDB-backed canonical queries
├── config/
│   └── policy.yaml         # Policy configuration (default, demo namespaces)
├── artifacts/logs/         # Operational artifacts (gitignored)
│   ├── telemetry.jsonl     # Emitted by llmscope core
│   └── policy_decisions.jsonl  # Emitted by this app
├── tests/                  # 72 tests, no external dependencies
└── .github/workflows/
    └── ci.yml              # Python 3.11 and 3.12 test matrix
```

## Boundary with llmscope Core

This repository consumes the `llmscope` runtime contract. It does not redefine or reimplement it.

**llmscope (core library) owns:**
- Provider abstraction and routing
- Cost estimation and normalization
- OpenTelemetry emission
- Telemetry artifact generation (`telemetry.jsonl`)
- Runtime types (`LLMRequestContext`, `GatewayResult`)

**llmscope-reference (this repo) owns:**
- Concrete YAML policy engine
- Pre-dispatch policy evaluation
- Local decision artifacts (`policy_decisions.jsonl`)
- DuckDB operational queries
- Reference HTTP API surface

Integration point: `llmscope.call_llm(..., context=LLMRequestContext(...))`

All inference requests pass through the public `llmscope` API. No internal imports from llmscope are used except where documented as technical debt in code comments.

## Dependencies

```toml
llmscope @ git+https://github.com/lucianareynaud/llmscope.git@5d3fdfbc
fastapi>=0.110
uvicorn[standard]>=0.29
pyyaml>=6.0
duckdb>=0.10
pydantic>=2.0
opentelemetry-instrumentation-fastapi>=0.45b0
```

llmscope is pinned to SHA `5d3fdfbc` (introduces `LLMRequestContext` with attribution fields).

Dev dependencies: `pytest>=8.0`, `pytest-asyncio>=0.23`, `httpx>=0.27`

## Known Limitations

1. **Pre-dispatch cost estimation**: Uses rough token count approximation (word count * 1.3) for budget and anomaly checks
2. **No provider configuration examples**: llmscope core handles providers, but setup is not demonstrated in this repo
3. **No post-dispatch policy**: Only pre-dispatch evaluation is implemented
4. **No policy hot reload**: Policy changes require engine reload or restart
5. **POSIX-only file locking**: fcntl advisory locking is not portable to Windows
6. **No authentication or RBAC**: This is a reference implementation, not a production service
7. **CLI-only queries**: No HTTP query API (queries run via `python -m reporting.queries`)
8. **Local JSONL artifacts only**: No database or distributed artifact store

## What This Repository Does Not Include

- Web dashboard or UI
- Authentication or authorization
- Multi-tenant console
- Plugin system or policy DSL
- Generic analytics platform
- Distributed system architecture
- Streaming inference
- Agent orchestration
- Evaluation pipelines or LLM-as-judge workflows

These are not planned for the first release.

## Future Work

Potential extensions (not committed):

1. Provider setup documentation
2. Post-dispatch policy evaluation (e.g., output validation)
3. Policy reload HTTP endpoint
4. HTTP query API (expose queries via REST endpoints)
5. Windows compatibility (replace fcntl with cross-platform locking)

## License

Reference implementation for demonstration purposes.
