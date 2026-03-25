# llmscope-reference Scope Steering

## What This Repository Is

`llmscope-reference` is a reference workload for runtime economics and operational governance of LLM requests. It demonstrates how a thin runtime contract emitted by `llmscope` can be consumed by a realistic application layer to produce local policy decisions, decision artifacts, and operator-grade queries.

The repository is not trying to win by feature count. It wins by sharpness. A buyer, reviewer, or recruiter should be able to understand in a few minutes that this application can answer operational questions that many LLM systems cannot answer cleanly.

## What Success Looks Like

The first release is successful when a reviewer can run the reference app, submit structured requests, see local policy decisions take effect, inspect emitted artifacts, and query the resulting data to answer the canonical operational questions.

Success is not defined by UI polish, broad integration coverage, or platform breadth. Success is defined by demonstrable operational clarity.

## Fixed Scope for the First Release

The first release includes only the following scope:

A minimal HTTP inference endpoint.
Structured request input carrying the attribution fields needed by `llmscope`.
Construction of `LLMRequestContext` from request data.
A concrete `YAMLPolicyEngine` evaluated before dispatch.
Three decision outcomes: `allow`, `downgrade`, `deny`.
Append-only JSONL decision logging.
DuckDB-backed queries answering the canonical five questions.
Tests covering the policy path, denied path, downgraded path, artifact generation, and query correctness.
A README that opens with the five operational questions rather than architecture.

This is enough. Anything beyond this must justify itself against the non-goals below.

## Canonical Questions This Repo Must Answer

The query layer, fixture data, and example outputs must remain aligned to the following exact questions:

Which tenant or feature is burning the most margin per request?
Which experiment increased cost without improving outcome?
Which fallbacks or routing choices are masking latency?
Which budget namespaces are triggering downgrades or denials?
Which routes or features are no longer margin-safe?

Do not let the spec, implementation, tests, and README drift into different sets of promised questions. A question promised publicly must be answered concretely by the repository.

## Hard Non-Goals

The following are explicitly out of scope for the first release:

A web dashboard.
Authentication or RBAC.
Organization management.
Multi-user settings.
Background workers unless absolutely required for local artifact handling.
Streaming UX.
Hot reload for YAML policy.
Generic policy composition engines.
Plugin systems.
Provider orchestration duplicated outside `llmscope`.
Agent orchestration frameworks.
General-purpose analytics platform behavior.
A hosted SaaS control plane.

If an implementation idea sounds like product surface rather than workload proof, it is probably a non-goal.

## Scope Control Rules

Every proposed addition must pass all of the following tests:

It must make at least one canonical question easier to answer.
It must not weaken the boundary between `llmscope` and `llmscope-reference`.
It must not create a new reusable framework inside the reference app.
It must not require a UI to prove value.
It must be possible to explain why it exists in one sentence.

Anything that fails one of these tests should be cut or deferred.

## Positioning Rules

Describe this repository in buyer language first, implementation language second.

Open with questions, evidence, and operational outcomes.
Only then explain FastAPI, YAML policy, JSONL artifacts, or DuckDB.
Do not market this repo as a generic LLM platform.
Do not market it as a full control plane product.
Do not market it as “another observability tool.”

The correct positioning is a narrow reference application that proves the value of runtime economics instrumentation.

## Release Discipline

The first release should favor completeness of the narrow story over breadth.

A complete release with one endpoint, one policy file, one decision log, one query module, and strong tests is better than a broader release with optional integrations, half-finished abstractions, or ornamental features.

No feature should enter the first release merely because it might be useful later.
