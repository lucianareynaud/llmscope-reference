# Spec: 002 Wire Telemetry Consumption

## Goal

Connect the policy engine to llmscope's telemetry JSONL so that `budget_threshold`
and `cost_anomaly` primitives evaluate against real operational data at runtime.

Zero changes to llmscope core. The reference adapts to the core's envelope contract.

## Prerequisite gate

```bash
OTEL_SDK_DISABLED=true pytest -q
```

All 68 tests must pass before starting.

## Problem

`app/api.py` passes `telemetry_path=None` to `policy_engine.evaluate()`, which
disables two of three policy primitives at runtime:

- `budget_threshold`: returns `allow` immediately (no telemetry to query)
- `cost_anomaly`: returns `allow` immediately (no baseline to compare)

Additionally, `feature_id` and `current_estimated_cost` are not passed to
`evaluate()`, so `cost_anomaly` cannot match features or detect anomalies even
if telemetry were available.

There are also two field mapping gaps between the core's JSONL and the engine's
DuckDB queries:

1. **budget_namespace**: The core envelope carries `budget_namespace` inside
   `audit_tags` (a nested dict), not as a top-level field. The engine queries
   `WHERE budget_namespace = ?` — top-level. Query silently returns zero rows.
   Fix: adapt the DuckDB queries to read from nested struct.

2. **use_case**: The core envelope has `use_case` as a top-level field, populated
   from `LLMRequestContext.use_case`. The reference constructs the context without
   setting `use_case`, only `feature_id`. The engine queries `WHERE use_case = ?`.
   Fix: set `use_case=request.feature_id` on the context.

## What this spec changes

### `app/api.py`

1. Pass `telemetry_path=TELEMETRY_PATH` to `evaluate()`
2. Pass `feature_id=request.feature_id` to `evaluate()`
3. Add pre-dispatch cost estimation via `llmscope.estimate_cost()` and pass
   `current_estimated_cost` to `evaluate()`
4. Set `use_case=request.feature_id` on the `LLMRequestContext`

### `policy/engine.py`

5. In `_evaluate_budget_threshold`: change DuckDB queries from
   `WHERE budget_namespace = ?` to `WHERE audit_tags->>'budget_namespace' = ?`
   and from `WHERE budget_namespace IS NULL` to
   `WHERE audit_tags->>'budget_namespace' IS NULL`

### Test fixtures

6. Update synthetic JSONL in `tests/test_policy.py` budget_threshold tests to
   use `audit_tags: {"budget_namespace": "demo"}` instead of top-level
   `budget_namespace`, matching the real envelope format.

### `README.md`

7. Update status of `budget_threshold` and `cost_anomaly` from "not functional"
   to "functional". Remove "Wire telemetry consumption" from roadmap.

## What this spec does NOT change

- No changes to llmscope core (no spec 011, no envelope modification)
- No new policy primitives
- No post-dispatch policy evaluation
- No new API endpoints
- No changes to the query layer in `reporting/queries.py`
- No changes to pyproject.toml llmscope pin

## Acceptance criteria

1. `evaluate()` receives `telemetry_path`, `feature_id`, and `current_estimated_cost`
2. `LLMRequestContext` is constructed with `use_case=request.feature_id`
3. Engine queries read `budget_namespace` from `audit_tags` (nested), not top-level
4. When telemetry JSONL exists with cost exceeding budget limits,
   `budget_threshold` produces `deny` or `downgrade`
5. When telemetry exists with baseline data and the current request cost exceeds
   threshold multiplier, `cost_anomaly` returns a reason string
6. All existing tests pass (updated fixtures match real envelope format)
7. New integration tests verify the wired path with synthetic telemetry

## Pre-dispatch cost estimation

`cost_anomaly` needs `current_estimated_cost` before dispatch. Approach:

1. Resolve model for tier: `get_model_for_tier(route_name, model_tier)`
2. Estimate input tokens: `int(len(prompt.split()) * 1.3)` (conservative)
3. Use 256 as default output token estimate
4. Call `estimate_cost(model, tokens_in_est, tokens_out_est)`

Precision is not critical — `cost_anomaly` uses a multiplier threshold (default
3x). The estimate only needs the right order of magnitude.

## DuckDB nested access rationale

The llmscope core's `LLMRequestContext.to_audit_tags()` includes `budget_namespace`
in the returned dict. The envelope stores this in `audit_tags: dict[str, str]`.
The JSONL serialization produces:

```json
{"tenant_id": "acme", "audit_tags": {"budget_namespace": "demo", "feature_id": "summarize"}, ...}
```

DuckDB's `read_json_auto` infers `audit_tags` as a STRUCT. The `->>'key'`
operator extracts string values from JSON/STRUCT fields reliably across row
schemas. This avoids changing the core's envelope contract to serve a downstream
consumer's query convenience.

## Risks

- **Telemetry file doesn't exist on first request**: Engine already handles this
  (returns `allow` when file is missing or empty).
- **audit_tags struct variance**: Different rows may have different keys in
  `audit_tags`. DuckDB's `->>'key'` returns NULL for missing keys, which is
  correct behavior for the IS NULL branch.
- **Pre-dispatch cost estimate inaccuracy**: Acceptable given 3x default
  multiplier.
