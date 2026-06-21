# Domain Context

## Workspace

The local project root containing profile data, normalized Jobs, predictions,
Application Packs, retrospectives, Run Ledgers, and `.job-state.json`.

## Job

A normalized employment opportunity identified by `job_id`. A Job owns its
scores, prediction references, validation result, submission metadata, and
retrospective windows.

## Pipeline

The ordered Job lifecycle: imported, scored, predicted, packed, validated,
ready to submit, submitted, and retro. `jobos.pipeline` owns valid transitions
and live-submission readiness.

## Application Pack

The candidate-facing files generated for one Job. A Pack includes a manifest
with file hashes, source hashes, and evidence-validation summary.

## Evidence Validation

The claim audit comparing candidate-authored Pack content with the evidence
bank. Clean persisted validation is required before workspace live submission.

## Submit Attempt

One diagnosed BOSS submission transaction. It records mode, phase, result,
success signals, screenshots, page classification, and recovery hints.

## Run Ledger

The `plan.json`, `events.jsonl`, and `summary.json` evidence for one dry or live
Pipeline execution under `pipeline_runs/<run_id>/`.

## Runtime State

Mutable operational sidecar state such as daily limits, contacted BOSS Jobs,
and auto-reply history. Runtime State is versioned and atomically persisted.

## Live BOSS Mode

An explicit browser workflow against a user-controlled logged-in session. It
does not bypass login or verification and does not mask browser automation.
