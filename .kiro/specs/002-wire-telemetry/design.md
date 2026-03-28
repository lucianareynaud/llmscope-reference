# Design: 002 Wire Telemetry Consumption

## Changes in app/api.py

### Import additions

```python
from app.settings import BASE_DIR, DECISIONS_PATH, TELEMETRY_PATH
from llmscope import (
    LLMRequestContext,
    call_llm,
    estimate_cost,
    get_model_for_tier,
)
```

### Change 1 — Map use_case on context

Current:
```python
context = LLMRequestContext(
    tenant_id=request.tenant_id,
    caller_id=request.caller_id,
    feature_id=request.feature_id,
    experiment_id=request.experiment_id,
    budget_namespace=request.budget_namespace
)
```

Target:
```python
context = LLMRequestContext(
    tenant_id=request.tenant_id,
    caller_id=request.caller_id,
    use_case=request.feature_id,
    feature_id=request.feature_id,
    experiment_id=request.experiment_id,
    budget_namespace=request.budget_namespace
)
```

Setting `use_case=request.feature_id` ensures the core envelope emits `use_case`
top-level in JSONL. The engine's `WHERE use_case = ?` then matches correctly.

### Change 2 — Pre-dispatch cost estimation

Before the `evaluate()` call:

```python
estimate_model = get_model_for_tier(request.route_name, request.model_tier)
tokens_in_estimate = int(len(request.prompt.split()) * 1.3)
tokens_out_estimate = 256
pre_dispatch_cost = estimate_cost(
    estimate_model, tokens_in_estimate, tokens_out_estimate
)
```

### Change 3 — Wire evaluate()

Current:
```python
verdict = policy_engine.evaluate(
    budget_namespace=request.budget_namespace,
    route_name=request.route_name,
    model_tier=request.model_tier,
    telemetry_path=None  # Will be wired in Task 6
)
```

Target:
```python
verdict = policy_engine.evaluate(
    budget_namespace=request.budget_namespace,
    route_name=request.route_name,
    model_tier=request.model_tier,
    telemetry_path=TELEMETRY_PATH,
    feature_id=request.feature_id,
    current_estimated_cost=pre_dispatch_cost,
)
```

---

## Changes in policy/engine.py

### _evaluate_budget_threshold — DuckDB query adaptation

Current (lines 159–174):
```python
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
```

Target:
```python
if budget_namespace:
    query = f"""
        SELECT COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost
        FROM read_json_auto('{telemetry_path}')
        WHERE timestamp >= ?
          AND audit_tags->>'budget_namespace' = ?
    """
    result = conn.execute(query, [window_start_iso, budget_namespace]).fetchone()
else:
    query = f"""
        SELECT COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost
        FROM read_json_auto('{telemetry_path}')
        WHERE timestamp >= ?
          AND audit_tags->>'budget_namespace' IS NULL
    """
    result = conn.execute(query, [window_start_iso]).fetchone()
```

The `->>'key'` operator extracts a string value from a JSON/STRUCT field.
Returns NULL when the key is absent, which satisfies the IS NULL branch.

---

## Changes in test fixtures

### tests/test_policy.py — budget_threshold fixtures

Current synthetic JSONL format:
```json
{"timestamp": "...", "request_id": "req-1", "budget_namespace": "demo", "estimated_cost_usd": 0.50}
```

Target (matching real envelope format):
```json
{"timestamp": "...", "request_id": "req-1", "audit_tags": {"budget_namespace": "demo"}, "estimated_cost_usd": 0.50}
```

All budget_threshold test fixtures must be updated. The cost_anomaly fixtures
already use `use_case` top-level, which matches the real envelope — no changes.

---

## Test strategy

### Existing tests

Update budget_threshold test fixtures to match real JSONL format. All 68 tests
must continue passing.

### New integration tests — tests/test_telemetry_wiring.py

1. **test_budget_threshold_denies_when_over_limit**: Write synthetic telemetry
   with accumulated cost > 1.00 USD in `audit_tags.budget_namespace="demo"`.
   POST to `/infer`. Assert HTTP 402.

2. **test_budget_threshold_allows_when_under_limit**: Write synthetic telemetry
   under limit. POST. Assert HTTP 200.

3. **test_cost_anomaly_detects_spike**: Write synthetic telemetry with low
   baseline for `use_case="summarize"`. POST with expensive tier. Assert
   `policy_reason` contains `cost_anomaly_detected`.

4. **test_empty_telemetry_allows**: Point `TELEMETRY_PATH` to nonexistent file.
   POST. Assert HTTP 200.

Fixtures write temporary JSONL and patch `TELEMETRY_PATH` via monkeypatch.
