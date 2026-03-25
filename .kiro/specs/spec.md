# llmscope-reference — Spec

## TL;DR

`llmscope-reference` is a narrow satellite application that consumes the
runtime contract emitted by `llmscope` and proves operational value with concrete
policy, decision log, and reproducible queries. The goal is not to become a
product or platform; it's to demonstrate, with real execution data, that a thin
runtime economics gateway enables cost attribution, budget enforcement, and
operational investigation without inflating the core.

## Problem

The `llmscope` core now emits a better runtime contract: structured context via
`LLMRequestContext`, compatible envelope, economic attributes in spans, and
preserved backward compatibility. This improves the library, but doesn't show
the market what this contract buys in operation.

Without a demonstrative application, external reading stops at "instrumented
middleware". A piece is missing that answers valuable questions.

## The Five Operational Questions This App Must Answer

1. Which tenant or feature burns the most margin per request?
2. Which experiment increased cost without improving outcome?
3. Which budget namespace is triggering downgrade or deny?
4. Which fallbacks are masking latency?
5. Which routes are no longer economically safe?

The app is ready when these five questions can be answered with real data
via CLI or simple endpoint. Dashboard is not a requirement.

## What This App Is

- A minimal FastAPI API that receives requests with structured attribution
  context and routes them through `llmscope`
- A concrete policy engine (`YAMLPolicyEngine`) that loads rules from YAML
  and produces `allow`, `downgrade`, or `deny` decisions — living in the app, not in the core
- A decision log persisted in JSONL for each request, including denials
- A query layer in DuckDB with the five canonical queries as named functions
- A README that opens with the five questions, not with architecture

## What This App Is Not

- Copy or fork of `llmscope` core code
- SaaS platform with auth, billing, or user management
- Semantic eval suite or prompt testing harness
- UI product or BI dashboard
- Agent orchestration framework
- Langfuse replacement (may appear as future demonstrative integration,
  never as central dependency)
- `PolicyHook` implementation to pressure the core for new abstraction —
  concrete policy lives here and doesn't require interface in `llmscope`

## Target User

The target user is not an end user. It's a technical buyer or platform manager
who wants to answer operational questions about LLM systems in production, or a
hiring manager who needs to see architecture judgment applicable to cost,
observability, and governance.

## Dependency Contract

```toml
[project]
dependencies = [
    "llmscope @ git+https://github.com/<org>/llmscope.git@<SHA>",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "pyyaml>=6.0",
    "duckdb>=0.10",
    "pydantic>=2.0",
]
```

`llmscope` is a library dependency, never a copy. SHA pinned to Diff 1 commit,
not `@main`. Local development uses `pip install -e ../llmscope` inside venv
without altering `pyproject.toml`.

## Visible Artifacts of V1

1. Minimal inference endpoint consuming `LLMRequestContext` from `llmscope`
2. Concrete policy in YAML with three possible decisions and reason code
3. Decision log in JSONL per request, including denials
4. DuckDB query layer with the five named canonical queries

## Quality Criteria

V1 is only valid if:

- the app uses `LLMRequestContext` from core with optional `caller_id` propagated
- policy decision is visible and persisted, including for denials
- queries run over real artifacts emitted by the application
- README opens with the five operational questions, not with stack
- the piece remains narrow and finishable

## Done Criteria

V1 is ready when it's possible to:

1. start the app locally
2. send requests with distinct `tenant_id`, `feature_id`, `budget_namespace`
3. observe `allow`, `downgrade`, and `deny` decisions with reason code
4. inspect decision JSONL and telemetry emitted by core
5. run the five canonical queries in DuckDB over real data
6. demonstrate the flow in README without elaborate UI

## Risks

The main risk is scope inflation: dashboard, auth, Langfuse-first,
sophisticated storage, premature `post_evaluate`, hot-reload with watchdog,
extra abstractions, or early productization. The second risk is duplicating
logic that already exists in `llmscope`, weakening the lib/app separation.

## Boundary Rule

`llmscope` defines the runtime contract.
`llmscope-reference` proves the operational value of that contract.
If something is not indispensable for proving that operational value, it stays out.
