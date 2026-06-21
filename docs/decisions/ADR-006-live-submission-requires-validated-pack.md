# ADR-006: Live Submission Requires A Validated Pack

## Status

Accepted

## Date

2026-06-20

## Context

Pipeline transition rules existed, but workflow code directly assigned status
strings. Batch submission could consider predicted or packed Jobs, and Pack
files had no integrity record.

## Decision

`jobos.pipeline` executes lifecycle transitions. Workspace live submission
requires `validated` or `ready_to_submit` status, zero unsupported claims, and
a valid Application Pack manifest. The manifest records Pack file hashes,
source hashes for job, profile, evidence, and prediction inputs, plus
validation summary, including failed validation counts. Source records avoid
global workspace-state hashes so unrelated job-state updates do not make a Pack
stale. Before browser connection, live submission independently requires zero
unsupported claims in the manifest and an exact validation-summary match
between the manifest and workspace state.

Manual submission recording may record an external fact, but it must update
the Job to `submitted`.

Regenerating a Pack is an explicit rework transition from `validated` or
`ready_to_submit` back to `packed`. It clears the prior validation result and
requires `job validate-pack` again. Terminal `submitted`, `retro`, and
`skipped` Jobs cannot be repacked.

## Consequences

- Invalid transitions fail at one Interface.
- Pack manifests reject non-flat filenames before hashing files.
- Pack generation fails if an explicit source file cannot be recorded.
- Pack or recorded source edits after validation are detected before browser
  connection.
- Source-less manifests are not valid for workspace live submission.
- Dry-run can inspect legacy Packs; live mode cannot.
- Pack generation and the automation loop use the same workspace Pack
  workflow and canonical evidence validator.
