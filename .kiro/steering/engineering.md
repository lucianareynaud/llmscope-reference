# llmscope-reference Engineering Steering

## Engineering Standard

This repository must feel like a disciplined reference workload, not an improvisational demo. Code should be small, explicit, typed, and locally understandable. The engineering goal is not maximal abstraction. The goal is a clean proof surface built on a stable dependency.

## Language, Environment, and Packaging

Use Python 3.11 or newer, consistent with `llmscope`.
Use `pyproject.toml` for packaging and dependency declaration.
Depend on `llmscope` via Git SHA until the core library is published in a stable way that justifies PyPI dependency semantics.

When iterating locally alongside the core library, use editable install in the virtual environment rather than changing project metadata to local filesystem paths.

## Dependency Rules

Imports from `llmscope` must prefer the public package surface.
Do not casually import from `llmscope` internal modules.
If a test or implementation must reach into an internal path because no public seam exists, the code must document this as temporary boundary debt.
Do not copy types, envelopes, provider behavior, or cost logic out of `llmscope`.

The reference app should be opinionated locally, but never duplicate ownership already held by the core library.

## Naming Consistency

Names that already exist in the `llmscope` public contract should be reused exactly.

If the core library uses `caller_id`, the reference app must also use `caller_id`.
If the core library uses `LLMRequestContext`, do not create a differently named wrapper for the same concept.
If the core library emits known envelope or attribution fields, do not invent competing names in the request/response layer unless translation is explicitly necessary.

Naming drift between core and reference app is architectural noise and should be treated as a bug.

## Testing Strategy

Tests are part of the artifact, not cleanup. The repository must prove that its narrow claims are true.

At minimum, tests should cover:

Request validation and context construction.
Policy decisions for allow, downgrade, and deny.
Correct calls into `llmscope` using structured context.
Decision record persistence in JSONL.
DuckDB queries returning expected answers over fixture data.
Boundary behavior when policy denies and no provider call should occur.

Tests should mock public seams whenever possible.
Mocking internals of `llmscope` is allowed only when no public seam exists and the debt is documented.
Tests must not call real provider APIs.
Tests must be deterministic and runnable locally without external services.

## Data and Artifact Conventions

Use append-only local JSONL files for operational artifacts in the first release.
Do not introduce databases or services unless a local file-based approach can no longer prove the workload.
Keep fixture data small, explicit, and easy to inspect.
If generated artifacts are used in tests, isolate them in temporary directories or fixture-controlled paths.

DuckDB is allowed as a local query engine because it helps prove the operational questions. It is not an excuse to build a generalized analytics subsystem.

## FastAPI and Request Handling

The HTTP layer must remain minimal.
Use typed request and response models.
Keep request handlers narrow and explicit.
Do not hide major policy or logging behavior in magical middleware unless that behavior clearly improves readability and testability.

For the first release, prefer straightforward orchestration inside a small service layer over framework cleverness.

## Configuration Rules

YAML policy is a concrete local mechanism, not a policy platform.
Configuration should be loaded explicitly and predictably.
Do not add hot reload, dynamic watchers, remote config, or plugin discovery in the first release.
Configuration changes should be obvious in tests and local runs.

## Query Layer Rules

The query layer exists to answer the canonical five questions and nothing more.
Keep queries named, curated, and tied to explicit fixtures or produced artifacts.
Do not build a general-purpose report builder.
Do not create a broad SQL abstraction layer unless the repository proves it is necessary.

## Documentation Rules

README and examples must begin with the operator’s questions and demonstrated outputs.
Architecture explanations come after value demonstration.
Do not write documentation that makes the repo sound broader than it is.
Do not describe unfinished future features as if they are part of the present artifact.

## Change Control

When evaluating a new task or design choice, ask:

Does this preserve the `llmscope` versus `llmscope-reference` boundary?
Does this improve the proof surface for runtime economics and operational governance?
Does this keep the repository narrow enough to finish and explain clearly?

If the answer is not clearly yes to all three, the change should be deferred or rejected.
