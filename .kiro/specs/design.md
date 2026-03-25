# llmscope-reference — Design

## Core Principle

`llmscope` defines the runtime contract. `llmscope-reference` proves the
operational value of that contract. If something is not indispensable for
demonstrating that operational value, it stays out.

## Directory Structure

```
llmscope-reference/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, lifespan, OTEL setup/shutdown
│   ├── api.py               # POST /infer, GET /healthz, GET /readyz
│   ├── schemas.py           # InferRequest, InferResponse (Pydantic)
│   └── settings.py          # Artifact paths, env vars
├── policy/
│   ├── __init__.py
│   ├── engine.py            # YAMLPolicyEngine — standalone, no app/ dep
│   ├── loader.py            # load_policy(path) -> PolicyConfig
│   ├── models.py            # PolicyVerdict, PolicyDecisionRecord
│   └── log.py               # PolicyDecisionLog.append() — atomic JSONL
├── reporting/
│   ├── __init__.py
│   ├── queries.py           # Five canonical queries + __main__ CLI
│   └── cli.py               # Optional CLI entry point
├── config/
│   └── policy.yaml          # Default config — default and demo namespaces
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Synthetic JSONL fixtures, mock call_llm
│   ├── test_schemas.py      # InferRequest/InferResponse validation
│   ├── test_policy.py       # YAMLPolicyEngine unit tests
│   ├── test_decision_log.py # PolicyDecisionRecord serialization
│   ├── test_api.py          # Gateway endpoint integration tests
│   └── test_queries.py      # DuckDB query correctness
├── artifacts/
│   ├── logs/
│   │   ├── .gitkeep
│   │   ├── telemetry.jsonl         # written by llmscope
│   │   └── policy_decisions.jsonl  # written by policy/log.py
│   └── reports/
├── pyproject.toml
└── README.md
```

**Structure note:** `policy/` is outside `app/` deliberately. The engine
must be testable without FastAPI. Placing it in `app/policy.py` would create
implicit coupling with the application context.

## HTTP Schemas

### InferRequest

```python
class InferRequest(BaseModel):
    prompt: str                          # required, non-empty
    tenant_id: str                       # required, non-empty
    caller_id: str | None = None         # optional — propagates to LLMRequestContext
    feature_id: str | None = None
    experiment_id: str | None = None
    budget_namespace: str | None = None
    model_tier: Literal["cheap", "expensive"] = "cheap"
    route_name: str = "/infer"
```

`caller_id` is optional but must be propagated to `LLMRequestContext` when
present — this exercises the Diff 1 contract of the core.

### InferResponse

```python
class InferResponse(BaseModel):
    request_id: str
    answer: str
    selected_model: str
    estimated_cost_usd: float
    tokens_in: int
    tokens_out: int
    policy_decision: str                 # "allow" | "downgrade" | "deny"
    policy_reason: str | None = None
    effective_model_tier: str            # tier that was actually used
```

### Denial response (HTTP 402)

```json
{
  "error": "budget_exceeded",
  "reason": "<reason_code>",
  "policy_id": "<rule id from YAML>"
}
```

## Main Flow — POST /infer

```
InferRequest
  → validate payload (Pydantic)
  → construct LLMRequestContext(
        tenant_id, caller_id, feature_id,
        experiment_id, budget_namespace
    )
  → YAMLPolicyEngine.evaluate(context, route_name, model_tier)
      → if deny:
          PolicyDecisionLog.append(record)
          return HTTP 402
      → if downgrade:
          effective_model_tier = "cheap"
      → if allow:
          effective_model_tier = requested model_tier
  → llmscope.call_llm(
        prompt=prompt,
        model_tier=effective_model_tier,
        route_name=route_name,
        context=context
    )
  → PolicyDecisionLog.append(record with actual cost)
  → return InferResponse
```

**Note:** only `pre_evaluate` (before dispatch) is in V1 scope.
`post_evaluate` (post-actual-cost evaluation) is not included now — it's not
necessary to answer the five canonical questions and adds lifecycle complexity
without proportional signal gain.

## YAMLPolicyEngine

Standalone engine that loads configuration from YAML and evaluates two primitives
in V1. Third primitive (`cost_anomaly`) enters only if queries and
fixtures are already solid.

```python
@dataclass(frozen=True)
class PolicyVerdict:
    decision: Literal["allow", "downgrade", "deny"]
    reason: str | None = None
    effective_model_tier: str | None = None  # filled if downgrade
    policy_id: str | None = None
    primitive: str | None = None

class YAMLPolicyEngine:
    def __init__(self, config_path: str) -> None: ...

    def evaluate(
        self,
        context: LLMRequestContext,
        route_name: str,
        model_tier: str,
        telemetry_path: str | None = None,  # for budget_threshold via DuckDB
    ) -> PolicyVerdict: ...

    def reload(self) -> None:
        """Re-reads YAML without restart. Explicit, not automatic."""
```

**Two primitives in V1 (in evaluation order):**

1. `budget_threshold` — deny or downgrade when accumulated cost in window
   exceeds limit. Window calculated via DuckDB over `telemetry.jsonl`
   filtered by `budget_namespace` and period. If `telemetry_path` is `None`
   or file is missing, safe behavior is `allow`.

2. `route_preference` — downgrade when requested `model_tier` is `expensive`
   and the route is configured to prefer `cheap`.

**Third primitive — conditional:**

3. `cost_anomaly` — alert (does not block, decision always `allow`) when
   average cost per feature deviates from 24h baseline by configured
   multiplier. Only implement if test_queries.py fixtures already cover
   baseline correctly.

**No automatic hot-reload:** `reload()` is explicit and called only when
necessary. Watchdog does not enter V1 — it doesn't prove value, multiplies
threading and config state edge cases in tests.

## PolicyDecisionRecord

```python
@dataclass
class PolicyDecisionRecord:
    timestamp: str              # ISO 8601
    request_id: str
    tenant_id: str
    caller_id: str | None
    feature_id: str | None
    experiment_id: str | None
    budget_namespace: str | None
    route_name: str
    requested_model_tier: str
    effective_model_tier: str
    primitive: str              # "budget_threshold" | "route_preference" | "cost_anomaly"
    decision: str               # "allow" | "downgrade" | "deny"
    reason: str | None
    policy_id: str | None
    estimated_cost_usd: float | None   # None if pre-dispatch denial
    latency_ms: float | None           # None if pre-dispatch denial
    window_cost_usd: float | None      # accumulated cost in window (budget_threshold)
    window_limit_usd: float | None
    policy_version: str         # semver of loaded config

    def to_dict(self) -> dict:
        """Serializes to JSONL. Omits None. Preserves native types."""
```

Additive-only schema. New fields in minor versions. Consumers tolerate
unknown keys.

## config/policy.yaml

```yaml
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

      - id: "demo-route-preference"
        primitive: route_preference
        route_name: "/infer"
        prefer_tier: cheap

      - id: "demo-cost-anomaly"
        primitive: cost_anomaly
        feature_id: "summarize"
        baseline_window_hours: 24
        threshold_multiplier: 3.0
        action: alert
```

## Five Canonical Queries — Canonical Names and Question Mapping

| Function                      | Question                                              |
|-------------------------------|-------------------------------------------------------|
| `cost_by_tenant_and_feature`  | Which tenant or feature burns the most margin?        |
| `experiment_cost_vs_outcome`  | Which experiment increased cost without improving outcome? |
| `budget_pressure_by_namespace`| Which namespace triggers downgrade or deny?           |
| `fallback_latency_masking`    | Which fallbacks are masking latency?                  |
| `unsafe_routes`               | Which routes are no longer economically safe?         |

**Implementation in `reporting/queries.py`:**

```python
def cost_by_tenant_and_feature(telemetry_path: str) -> list[dict]:
    """Total and average cost per tenant_id and use_case (feature)."""

def experiment_cost_vs_outcome(telemetry_path: str) -> list[dict]:
    """Per experiment_id: average tokens, average cost, finish_reason=stop rate."""

def budget_pressure_by_namespace(decisions_path: str) -> list[dict]:
    """Per budget_namespace: count of allow/downgrade/deny."""

def fallback_latency_masking(telemetry_path: str) -> list[dict]:
    """p95 latency per route and is_fallback."""

def unsafe_routes(
    telemetry_path: str,
    cost_threshold_usd: float = 0.05
) -> list[dict]:
    """Routes where average cost per request exceeds threshold."""
```

Each function returns `list[dict]` with native Python types. DuckDB reads JSONL
directly via `read_json_auto(path)`. No persistent tables. No ETL.
Missing or empty file returns `[]` without error.

CLI exposed via `python3 -m reporting.queries <query_name>`.

## Boundary Invariants

- Only public `llmscope` API is imported:
  `from llmscope import call_llm, LLMRequestContext, setup_otel, shutdown_otel`
- No internal `llmscope` paths in production code
- `policy/` without dependency on `app/` — testable standalone
- `reporting/` without dependency on `app/` or `policy/` — reads only artifacts
- Tests do not call real provider; mock via public surface when possible

## Mock Strategy in Tests

`llmscope` exposes `register_provider()` as public API. Tests should
prefer registering a `FakeProvider` via `register_provider()` in `conftest.py`
instead of patching internal paths. If the public seam is not sufficient for
a specific case, document as core technical debt — do not embed internal path
as permanent test contract.

```python
# conftest.py — preferred
from llmscope import register_provider, ProviderBase, ProviderResponse

class FakeProvider(ProviderBase):
    @property
    def provider_name(self) -> str:
        return "fake"

    async def complete(self, prompt, model, max_tokens):
        return ProviderResponse(text="ok", tokens_in=10, tokens_out=5)

register_provider(FakeProvider())
```

## Artifact Paths

```
artifacts/logs/telemetry.jsonl          # written by llmscope
artifacts/logs/policy_decisions.jsonl   # written by policy/log.py
artifacts/reports/                      # optional CLI output
```

Configurable via `settings.py` / env vars. Missing file never breaks
the main flow — each component treats missing file as empty state.

## OTEL

`app/main.py` lifespan calls `llmscope.setup_otel()` on startup and
`llmscope.shutdown_otel()` on shutdown. `OTEL_SDK_DISABLED=true` in CI and
tests. No Langfuse integration in V1.
