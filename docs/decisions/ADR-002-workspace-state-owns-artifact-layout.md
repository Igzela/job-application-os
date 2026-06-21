# ADR-002: Workspace State Owns Artifact Layout

## Status

Accepted

## Date

2026-06-17

## Context

Project state and artifact layout are currently known by many Modules. Examples include:

- `.job-state.json` load/save logic in CLI, loop, queue, status, report, submitter, retro, TUI screens, and rubric code.
- Artifact paths such as `applications/`, `predictions/`, `pipeline_runs/`, `jobs/raw`, `jobs/normalized`, and `retros/` repeated across workflow code.
- Drift where status artifact counting refers to `packs/`, while pack generation writes to `applications/<job_id>/`.

This makes state schema and layout changes expensive because callers must know filesystem details and state defaults.

## Decision

Workspace state and artifact layout should be owned by one deep Module, tentatively named `jobos/workspace.py` or `jobos/state_store.py`.

The Workspace State Module should own:

- Loading and saving `.job-state.json`.
- Schema defaults and future migrations.
- Job status transition helpers.
- Artifact path lookup for project outputs.
- Read-only queries used by queue, status, report, recommend, loop planning, and TUI views.

Existing callers should migrate incrementally. Public behavior should remain stable during migration.

## Alternatives Considered

### Leave state helpers duplicated

- Pros: No migration work.
- Cons: Keeps layout drift and makes future schema changes risky.
- Rejected: The roadmap specifically targets state and artifact locality.

### Introduce a database

- Pros: Stronger schema and transactional behavior.
- Cons: Larger product and operational change than needed for a local-first CLI.
- Rejected: The roadmap explicitly keeps the local file-based architecture.

### Put all state behavior into `models.py`

- Pros: Reuses an existing Module.
- Cons: Mixes dataclass definitions with filesystem persistence, path layout, and workflow queries.
- Rejected: This would make `models.py` shallow and over-broad.

## Consequences

- New code should avoid direct `.job-state.json` reads once the Workspace State Module exists.
- Low-risk readers should migrate first: status, queue, recommend, and report.
- The current `packs/` versus `applications/` drift should be fixed as part of this migration.
- Tests should exercise workspace behavior at the Workspace State Module Interface.
