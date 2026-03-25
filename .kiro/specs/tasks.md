# llmscope-reference — Tasks

## Execution Rules

- One task at a time. Do not start the next without validating the previous one.
- Each task touches only the files it declares.
- No abstractions outside the listed scope.
- Do not duplicate code from the `llmscope` core.
- Tests never call real providers or external APIs.
- Requests denied by policy do not call `llmscope.call_llm()`.
- `llmscope` enters as a dependency via Git SHA in `pyproject.toml`.
- If Kiro suggests expanding scope "because it might be useful later", reject.

## Global Stop Condition

If pressure arises to add UI, auth, sophisticated storage, multiple
policy backends, Langfuse-first, `post_evaluate`, automatic hot-reload,
`PolicyHook` in the core, or any feature that is not indispensable for
answering the five canonical questions — stop and reject.

---

## Task 1 — Repository Bootstrap

**Files:** `pyproject.toml`, `app/__init__.py`, `app/main.py`,
`app/settings.py`, `artifacts/logs/.gitkeep`, `.gitignore`,
`.github/workflows/ci.yml`, `README.md` (placeholder).

**What to do:**
- Create directory structure according to `design.md`
- `pyproject.toml` with dependencies: `llmscope @ git+https://...@<SHA>`,
  FastAPI, uvicorn, pyyaml, duckdb, pydantic
- SHA pinned to Diff 1 commit of `llmscope`, not `@main`
- `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` and
  `OTEL_SDK_DISABLED=true` as default env
- `app/main.py` with FastAPI app, empty lifespan (setup_otel/shutdown_otel
  will be added in Task 4), and `GET /healthz` responding 200
- `app/settings.py` with artifact paths configurable via env:
  `TELEMETRY_PATH`, `DECISIONS_PATH`
- CI: `pip install -e .[dev]` + `pytest -q`
- `.gitignore` covering `.venv`, `artifacts/logs/*.jsonl`, `__pycache__`

**Do not:** no inference, policy, or query logic yet.

**Acceptance:**
- `pip install -e .[dev]` in clean clone without local llmscope path
- `pytest -q` with zero tests passes without import errors
- `GET /healthz` responds 200

---

## Task 2 — HTTP Schemas

**Files:** `app/schemas.py`, `tests/test_schemas.py`.

**What to do:**
- `InferRequest` with fields: `prompt` (required, non-empty), `tenant_id`
  (required, non-empty), `caller_id` (optional), `feature_id` (optional),
  `experiment_id` (optional), `budget_namespace` (optional),
  `model_tier: Literal["cheap", "expensive"] = "cheap"`,
  `route_name: str = "/infer"`
- `InferResponse` with fields: `request_id`, `answer`, `selected_model`,
  `estimated_cost_usd`, `tokens_in`, `tokens_out`, `policy_decision`,
  `policy_reason` (optional), `effective_model_tier`
- Pydantic validation: reject empty `prompt`, reject empty `tenant_id`,
  reject `model_tier` outside `["cheap", "expensive"]`
- Tests covering: required fields, correct defaults, rejection of
  invalid values, optional `caller_id` accepted when present

**Do not:** no imports from `llmscope` in schemas.

**Acceptance:** schema tests pass. Zero imports from `llmscope` in
`app/schemas.py`.

---

## Task 3 — PolicyDecisionRecord and decision log

**Files:** `policy/__init__.py`, `policy/models.py`, `policy/log.py`,
`tests/test_decision_log.py`.

**What to do:**
- `PolicyVerdict` frozen dataclass with fields: `decision`, `reason`,
  `effective_model_tier`, `policy_id`, `primitive`
- `PolicyDecisionRecord` dataclass with all fields from `design.md`
- `to_dict()` that serializes to dict with native types, omits `None`,
  does not use enum values (all fields are already strings)
- `PolicyDecisionLog.append(record, path)` that writes one JSONL line
  atomically (open + write + flush + close on absolute path)
- Tests covering: correct serialization of all fields, omission of `None`,
  incremental append (second call does not overwrite first),
  `policy_version` present in output, file created if it doesn't exist

**Do not:** no imports from `app/` or `llmscope` in `policy/models.py`
and `policy/log.py`.

**Acceptance:** tests pass. Two consecutive `append()` calls generate two lines
in JSONL in `tmp_path`.

---

## Task 4A — YAMLPolicyEngine: loader and budget_threshold

**Files:** `policy/loader.py`, `policy/engine.py`, `config/policy.yaml`,
`tests/test_policy.py`.

**What to do:**
- `PolicyConfig` typed dataclass representing parsed YAML
- `load_policy(path: str) -> PolicyConfig` that reads and validates YAML;
  raises `ValueError` on invalid or missing YAML
- `YAMLPolicyEngine.__init__(config_path)` that calls `load_policy`
- `YAMLPolicyEngine.reload()` that re-reads YAML explicitly — no watchdog,
  no threading, no automatic callback
- `budget_threshold` primitive: calculates accumulated cost in window via DuckDB
  over `telemetry_path`; if file is missing or empty, returns safe `allow`;
  if exceeds limit, returns `deny` or `downgrade` according to YAML
- `config/policy.yaml` with `default` and `demo` namespaces according to `design.md`
- Tests covering: `budget_threshold` deny, `budget_threshold` downgrade,
  missing telemetry file returns allow, invalid YAML raises error,
  `reload()` picks up config change

**Do not:** do not implement `route_preference` or `cost_anomaly` yet.
No automatic hot-reload. No imports from `app/`.

**Acceptance:** tests pass without FastAPI and without API keys.

---

## Task 4B — YAMLPolicyEngine: route_preference

**Files:** `policy/engine.py`, `config/policy.yaml`, `tests/test_policy.py`.

**What to do:**
- `route_preference` primitive: if requested `model_tier` is `expensive` and the
  route is configured to prefer `cheap`, returns `downgrade` with
  `effective_model_tier="cheap"`
- Add `route_preference` rule to `config/policy.yaml`
- Tests covering: downgrade triggered when requested tier is expensive,
  allow when requested tier is already cheap, allow when route has no rule

**Do not:** do not implement `cost_anomaly` yet.

**Acceptance:** tests pass. `budget_threshold` and `route_preference` are
evaluated in order when both are configured.

---

## Task 5 — FastAPI gateway endpoint

**Files:** `app/api.py`, `app/main.py`, `tests/test_api.py`,
`tests/conftest.py`.

**What to do:**
- `POST /infer` with flow from `design.md`:
  validate → construct `LLMRequestContext` → `engine.evaluate()` → if deny
  return HTTP 402 → if downgrade override tier → `call_llm()` → log → response
- `LLMRequestContext` constructed with `tenant_id`, `caller_id`, `feature_id`,
  `experiment_id`, `budget_namespace` from request — exercises Diff 1 of core
- Denial returns HTTP 402 with `{"error": "budget_exceeded", "reason": "...",
  "policy_id": "..."}`
- `app/main.py` lifespan: `setup_otel()` on startup, `shutdown_otel()` on
  shutdown, `FastAPIInstrumentor.instrument_app()` after setup
- `conftest.py`: register `FakeProvider` via `register_provider()` from
  public `llmscope` — do not patch llmscope internal paths
- Tests covering: complete allow flow, downgrade alters effective tier,
  deny returns 402 and does not call `call_llm`, `caller_id` propagated in context,
  `feature_id` propagated in context

**Mock strategy:** use `register_provider(FakeProvider())` according to
`design.md`. If `register_provider` is not sufficient for some case,
document as core debt in test comment — do not use internal paths
like `llmscope.gateway.client.get_provider` as permanent contract.

**Do not:** do not implement `cost_anomaly` here. Do not create auth.

**Acceptance:** `OTEL_SDK_DISABLED=true pytest -q` passes. Endpoint responds
to local `curl`. Deny does not call provider.

---

## Task 6 — Decision log integrated into endpoint

**Files:** `app/api.py`, `tests/test_api.py`, `tests/test_decision_log.py`.

**What to do:**
- Integrate `PolicyDecisionLog.append()` into `POST /infer` handler:
  - for denial: log before returning 402, with `estimated_cost_usd=None`
    and `latency_ms=None`
  - for allow/downgrade: log after `call_llm()`, with actual cost and latency
    from `GatewayResult`
- `request_id` from `GatewayResult` must appear in `PolicyDecisionRecord`
  for correlation with `telemetry.jsonl`
- Tests covering: denial generates log without cost, allow generates log with cost,
  `request_id` in record matches `request_id` in response, second request
  adds second line without overwriting

**Acceptance:** after two requests (one allow, one deny), `policy_decisions.jsonl`
has two lines with correct fields.

---

## Task 7 — DuckDB query layer

**Files:** `reporting/__init__.py`, `reporting/queries.py`, `reporting/cli.py`,
`tests/test_queries.py`.

**What to do:**
- Five functions according to table in `design.md`:
  - `cost_by_tenant_and_feature(telemetry_path)`
  - `experiment_cost_vs_outcome(telemetry_path)`
  - `budget_pressure_by_namespace(decisions_path)`
  - `fallback_latency_masking(telemetry_path)`
  - `unsafe_routes(telemetry_path, cost_threshold_usd=0.05)`
- Each function returns `list[dict]` with native Python types
- DuckDB reads via `duckdb.read_json_auto(path)` directly — no persistent tables,
  no ETL, no `views.sql`
- Missing or empty file returns `[]` without exception
- CLI via `python3 -m reporting.queries <name> [--telemetry path]
  [--decisions path]` printing formatted JSON
- Tests with synthetic JSONL fixtures in `tmp_path` covering: correct result
  for each query, empty result when file is missing, empty result when JSONL is empty,
  correct return types (str, float, int — not DuckDB types)

**Do not:** no `views.sql`, no persistent database, no imports from `app/`
or `policy/`.

**Acceptance:** tests pass with fixtures. CLI returns valid JSON. No
query raises exception with missing file.

---

## Task 8 — cost_anomaly (conditional)

**Files:** `policy/engine.py`, `config/policy.yaml`, `tests/test_policy.py`.

**Precondition:** only execute this task if `tests/test_queries.py` already covers
cost baseline per feature with real fixtures. If not covered, skip.

**What to do:**
- `cost_anomaly` primitive: calculates average cost baseline per `feature_id`
  in the last `baseline_window_hours` via DuckDB over `telemetry_path`;
  if current cost exceeds `baseline * threshold_multiplier`, returns `allow`
  with descriptive `reason` (does not block)
- Tests covering: anomaly detected returns allow with reason, no anomaly
  returns allow without reason, missing file returns allow

**Do not:** `cost_anomaly` never returns `deny` or `downgrade`. It's an alert.

**Acceptance:** tests pass. `decision` is always `"allow"` for this primitive.

---

## Task 9 — README oriented to operational questions

**Files:** `README.md`.

**What to do:**
- Open with the five operational questions — not with stack, not with architecture
- "Quick start" section: pip install, env vars, two `curl` examples
  (allow flow and deny flow with real or synthetic outputs)
- "Operational queries" section: example output for each of the five
  queries (can be synthetic as long as it's realistic)
- "Policy configuration" section: the three primitives with YAML example
- Short "Architecture" section, after questions and quick start
- "Boundary" section: explain that `llmscope` is the core and this is the demonstrative shell
- Pinned `llmscope` SHA confirmed in `pyproject.toml`

**Acceptance:** README read in 30 seconds communicates what the project answers
and how to run it. The five questions are on the first screen.

---

## Task 10 — Final Hardening

**Files:** all tests, `pyproject.toml`, CI.

**What to do:**
- Ensure complete suite passes with `OTEL_SDK_DISABLED=true pytest -q`
  in clean clone without local llmscope path
- Verify that no internal `llmscope` module was imported in production code
  (only `from llmscope import ...`)
- Verify that `policy/` does not import from `app/`
- Verify that `reporting/` does not import from `app/` or `policy/`
- Confirm that no out-of-scope items entered: no UI, no auth, no
  watchdog, no `post_evaluate`, no `PolicyHook` in core, no Langfuse
- Green CI in clean clone

**Acceptance:** Green CI. Zero imports from llmscope internals. Boundaries
respected. App demonstrable in less than five commands from README.

---

## Mandatory Order

```
1 → 2 → 3 → 4A → 4B → 5 → 6 → 7 → 8 (if precondition OK) → 9 → 10
```
