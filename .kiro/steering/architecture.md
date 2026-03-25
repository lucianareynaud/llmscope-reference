# llmscope-reference Architecture Steering

## Purpose

`llmscope-reference` is a narrow reference application that demonstrates the operational value of the `llmscope` runtime contract. It is not a product, not a platform, and not an alternative implementation of the `llmscope` core library. Its job is to consume the runtime contract emitted by `llmscope`, apply concrete local policy, persist local operational artifacts, and answer a fixed set of operational questions with real data.

The architectural thesis is simple: `llmscope` defines the runtime contract; `llmscope-reference` proves what an operator can do with that contract. If a capability is required to define or emit the runtime contract itself, it belongs in `llmscope`. If a capability demonstrates how to consume, evaluate, persist, or query that contract in a realistic workload, it belongs in `llmscope-reference`.

## Dependency Direction

Dependency flow is one-way.

`llmscope-reference` depends on `llmscope`.
`llmscope` must never depend on `llmscope-reference`.
`llmscope-reference` must never copy, fork, or reimplement `llmscope` internals.

All inference requests in this repository must pass through the public `llmscope` surface. The integration point is the public API of `llmscope`, including `call_llm(..., context=...)` and the structured `LLMRequestContext`. Direct imports from `llmscope` internals are prohibited unless there is no public seam that can satisfy the need. If such an exception is unavoidable, it must be treated as explicit technical debt and documented in code comments and task notes.

## Core Components Allowed in This Repository

This repository may contain only the following first-class architectural components in its initial scope:

A minimal FastAPI application surface that accepts structured inference requests and passes them into `llmscope`.

A concrete local `YAMLPolicyEngine` that evaluates requests before dispatch and returns one of three decisions: `allow`, `downgrade`, or `deny`.

A local operational artifact store based on append-only JSONL files for policy decisions and any reference-app-specific records.

A local query layer based on DuckDB for answering a fixed set of canonical operational questions over emitted artifacts.

Fixtures, tests, and small operational utilities required to exercise the above.

These components are permitted because they demonstrate consumption of the runtime contract. They do not redefine the runtime contract.

## Explicit Boundary with llmscope Core

The following concerns belong to `llmscope`, not to this repository:

Provider abstraction.
Provider selection and routing mechanics implemented in the core library.
Envelope definition and serialization semantics.
OpenTelemetry emission logic owned by the core runtime.
Cost estimation and normalization logic already implemented by the library.
Public runtime types such as `LLMRequestContext`.

The following concerns belong to `llmscope-reference`, not to the core library:

Concrete YAML policy files and parsing.
Concrete policy rules and thresholds specific to this workload.
Decision records as local operational artifacts.
DuckDB-backed operational queries.
Reference-app request and response schemas.
Demonstration-oriented repository structure and fixtures.

Any proposal that pushes YAML config loading, concrete policy engines, DuckDB query logic, dashboards, or operational artifact persistence down into `llmscope` is architecturally wrong for this phase.

## Initial Request Lifecycle

The first release must keep the request lifecycle narrow.

An HTTP request enters the FastAPI app.
The app validates the request and constructs `LLMRequestContext`.
The concrete local policy engine performs a pre-dispatch evaluation.
If the decision is `deny`, the app returns a denied response and records the decision locally.
If the decision is `downgrade`, the app mutates the request parameters according to local policy and then calls `llmscope`.
If the decision is `allow`, the app calls `llmscope` unchanged.
The app records the resulting operational artifacts and exposes them to the query layer.

The first release does not require a post-dispatch policy phase. Pre-dispatch evaluation is sufficient to prove value.

## Canonical Operational Questions

The application exists to answer a small fixed set of questions. Architecture should be optimized for these questions, not for generic analytics.

Which tenant or feature is burning the most margin per request?
Which experiment increased cost without improving outcome?
Which fallbacks or routing choices are masking latency?
Which budget namespaces are triggering downgrades or denials?
Which routes or features are no longer margin-safe?

If a proposed component does not materially improve the system’s ability to answer one of these questions, it is probably out of scope.

## Non-Goals

This repository must not grow into a product surface during the first release.

There is no UI dashboard requirement.
There is no auth or RBAC requirement.
There is no multi-tenant console requirement.
There is no plugin system requirement.
There is no generic policy framework requirement.
There is no policy DSL beyond the concrete YAML schema needed now.
There is no hot reload requirement.
There is no Langfuse-first architecture requirement.
There is no distributed system requirement.

These may become future explorations, but they are not part of the architectural baseline.

## Design Discipline

Favor concrete local components over abstract extensibility.
Favor explicit request-path data flow over magical background behavior.
Favor append-only artifacts over mutable stateful stores.
Favor deterministic helpers and narrow contracts over callback systems.
Favor demonstration of operational truth over completeness theater.

Every architectural change should be judged by three criteria: does it preserve the boundary with `llmscope`, does it improve the proof surface of the runtime economics thesis, and does it keep the repository narrow enough to finish cleanly.
