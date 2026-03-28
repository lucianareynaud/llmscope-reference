# Tasks: 002 Wire Telemetry Consumption

## Prerequisite gate

```bash
OTEL_SDK_DISABLED=true pytest -q
```

All 68 tests must pass before starting any task.

---

## Task 1 — Adapt DuckDB queries to read budget_namespace from audit_tags

- [x] 1.1 Open `policy/engine.py`
- [ ] 1.2 In `_evaluate_budget_threshold`, replace:
      ```python
      AND budget_namespace = ?
      ```
      with:
      ```python
      AND audit_tags->>'budget_namespace' = ?
      ```
- [ ] 1.3 Replace:
      ```python
      AND budget_namespace IS NULL
      ```
      with:
      ```python
      AND audit_tags->>'budget_namespace' IS NULL
      ```
- [x] 1.4 No other changes in engine.py

**Acceptance**: engine reads budget_namespace from nested audit_tags struct.

---

## Task 2 — Update budget_threshold test fixtures

- [x] 2.1 Open `tests/test_policy.py`
- [ ] 2.2 In all budget_threshold test fixtures, replace top-level
      `"budget_namespace": "demo"` with
      `"audit_tags": {"budget_namespace": "demo"}`
- [ ] 2.3 Search for any other synthetic JSONL in test files that uses
      top-level `budget_namespace` and update to nested format
- [ ] 2.4 Run:
      ```bash
      OTEL_SDK_DISABLED=true pytest tests/test_policy.py -v
      ```

**Acceptance**: all policy tests pass with updated fixtures.

---

## Checkpoint

Stop and verify tasks 1–2 before proceeding. The engine and its tests must be
green before touching api.py. Run:

```bash
OTEL_SDK_DISABLED=true pytest -q
```

All 68 tests must pass.

---

## Task 3 — Map use_case on LLMRequestContext

- [ ] 3.1 Open `app/api.py`
- [ ] 3.2 Add `use_case=request.feature_id` to the `LLMRequestContext`
      construction (keep `feature_id=request.feature_id` as well)
- [ ] 3.3 Run:
      ```bash
      OTEL_SDK_DISABLED=true pytest -q
      ```

**Acceptance**: context carries `use_case`. No test regressions.

---

## Task 4 — Add pre-dispatch cost estimation

- [ ] 4.1 In `app/api.py`, add imports:
      ```python
      from llmscope import estimate_cost, get_model_for_tier
      ```
- [ ] 4.2 Before the `policy_engine.evaluate()` call, add:
      ```python
      estimate_model = get_model_for_tier(request.route_name, request.model_tier)
      tokens_in_estimate = int(len(request.prompt.split()) * 1.3)
      tokens_out_estimate = 256
      pre_dispatch_cost = estimate_cost(
          estimate_model, tokens_in_estimate, tokens_out_estimate
      )
      ```
- [ ] 4.3 Run:
      ```bash
      OTEL_SDK_DISABLED=true pytest -q
      ```

**Acceptance**: cost estimation executes without error. No test regressions.

---

## Task 5 — Wire evaluate() arguments

- [ ] 5.1 In `app/api.py`, add `TELEMETRY_PATH` to the import from `app.settings`:
      ```python
      from app.settings import BASE_DIR, DECISIONS_PATH, TELEMETRY_PATH
      ```
- [ ] 5.2 Replace the `policy_engine.evaluate()` call with:
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
- [ ] 5.3 Remove the `# Will be wired in Task 6` comment
- [ ] 5.4 Run:
      ```bash
      OTEL_SDK_DISABLED=true pytest -q
      ```

**Acceptance**: evaluate() receives all three previously-missing arguments.
No test regressions.

---

## Task 6 — Add integration tests

- [ ] 6.1 Create `tests/test_telemetry_wiring.py`
- [ ] 6.2 Add fixture that writes synthetic telemetry JSONL to a temp file and
      patches `TELEMETRY_PATH` via `monkeypatch.setenv("TELEMETRY_PATH", ...)`

Synthetic JSONL format for budget_threshold tests (matches real envelope):
```json
{"timestamp": "2026-03-27T10:00:00Z", "tenant_id": "acme", "audit_tags": {"budget_namespace": "demo"}, "estimated_cost_usd": 0.50, "route": "/infer", "status": "success"}
```

Synthetic JSONL format for cost_anomaly tests (matches real envelope):
```json
{"timestamp": "2026-03-27T10:00:00Z", "tenant_id": "acme", "use_case": "summarize", "estimated_cost_usd": 0.002, "route": "/infer", "status": "success"}
```

- [ ] 6.3 Add `test_budget_threshold_denies_when_over_limit`:
      - Write JSONL with accumulated cost > 1.00 USD in
        `audit_tags.budget_namespace="demo"` in the last hour
      - POST `/infer` with `budget_namespace="demo"`
      - Assert HTTP 402 with `budget_exceeded` in response detail
- [ ] 6.4 Add `test_budget_threshold_allows_when_under_limit`:
      - Write JSONL with accumulated cost = 0.10 USD
      - POST `/infer` with `budget_namespace="demo"`
      - Assert HTTP 200
- [ ] 6.5 Add `test_cost_anomaly_detects_spike`:
      - Write JSONL with 10 events for `use_case="summarize"` at ~0.002 USD each
      - POST `/infer` with `feature_id="summarize"` and `model_tier="expensive"`
      - Assert response `policy_reason` contains `cost_anomaly_detected`
- [ ] 6.6 Add `test_empty_telemetry_allows`:
      - Point `TELEMETRY_PATH` to nonexistent file
      - POST `/infer`
      - Assert HTTP 200
- [ ] 6.7 Run:
      ```bash
      OTEL_SDK_DISABLED=true pytest tests/test_telemetry_wiring.py -v
      ```

**Acceptance**: all new integration tests pass.

---

## Task 7 — Update README

- [ ] 7.1 Under "Current Limitations", replace the telemetry wiring limitation
      text with: "Budget enforcement and cost anomaly detection evaluate against
      local telemetry JSONL. Pre-dispatch cost estimation uses a rough token
      count approximation."
- [ ] 7.2 Under "Request Lifecycle", remove "(currently only route_preference is
      functional)" from step 3
- [ ] 7.3 Update `budget_threshold` status from "Implemented but not functional"
      to "Functional — evaluates against local telemetry JSONL"
- [ ] 7.4 Update `cost_anomaly` status from "Implemented but not functional"
      to "Functional — evaluates against local telemetry JSONL"
- [ ] 7.5 Remove "Wire telemetry consumption" from "Near-Term Roadmap"

**Acceptance**: README reflects functional state accurately.

---

## Task 8 — Full verification

- [ ] 8.1 Run:
      ```bash
      OTEL_SDK_DISABLED=true pytest -q
      ```
      Expect: 68 + N new tests pass (N = number of new integration tests)
- [ ] 8.2 Verify `app/api.py` no longer contains `telemetry_path=None`
- [ ] 8.3 Verify `policy/engine.py` queries reference `audit_tags->>'budget_namespace'`
- [ ] 8.4 Verify no changes were made to llmscope core

**Acceptance**: spec 002 is complete.

---

## Completion criteria

- `evaluate()` receives `telemetry_path`, `feature_id`, and `current_estimated_cost`
- `LLMRequestContext` carries `use_case=request.feature_id`
- Engine reads `budget_namespace` from `audit_tags` nested struct
- `budget_threshold` produces deny/downgrade at runtime when telemetry exceeds limits
- `cost_anomaly` detects spikes when cost exceeds baseline * multiplier
- Test fixtures match real envelope JSONL format
- Integration tests prove the wired path
- README documents the functional state
- All tests pass
- Zero changes to llmscope core
