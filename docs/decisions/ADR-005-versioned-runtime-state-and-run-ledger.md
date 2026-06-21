# ADR-005: Versioned Runtime State And Shared Run Ledger

## Status

Accepted

## Date

2026-06-20

## Context

Workspace state, daily limits, contact history, auto-reply history, dry-run
events, and live results used unrelated JSON formats and non-atomic writes.
Live results overwrote one root-level `pipeline_results.json`.

## Decision

Mutable JSON state uses `jobos.runtime_state` for schema versioning, advisory
locking, and atomic replacement. Dry and live Pipeline executions use
`jobos.run_ledger` and write `plan.json`, `events.jsonl`, and `summary.json`
under a unique `pipeline_runs/<run_id>/`. The Run Ledger owns event
`schema_version` and `timestamp` fields so caller payloads cannot spoof
ledger metadata. New Run Ledgers must use an explicit `dry_run` or `live`
mode; legacy plans without a mode are interpreted as `dry_run`.

## Consequences

- Corrupt state fails explicitly instead of silently resetting.
- Contact updates and daily counters use locked read-modify-write operations.
- Dry and live runs have one evidence format.
- Run event metadata is consistent across dry and live callers.
- Invalid explicit run modes are treated as corrupt Run Ledgers.
