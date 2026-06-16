# Automation Loop Handoff Plan

## Purpose

Build a maintainable automation loop for this project so another Codex agent can continue without rediscovering context. The focus is reliability, recoverability, observability, and quality gates for the existing job application pipeline.

Out of scope for the first pass:
- Reworking product positioning or user profile content.
- Changing the live browser strategy.
- Adding new platform adapters beyond the existing BOSS Zhipin path.

## Current Baseline

Repository: `/home/igzela/Projects/job-application-os`

The project already contains a Python CLI package, `jobos`, with these relevant modules:

- `jobos/cli.py`: CLI command registration and dispatch.
- `jobos/orchestrator.py`: current full-pipeline implementation.
- `jobos/submitter.py`: single and batch submission helpers.
- `jobos/queue.py`: state-based pipeline buckets.
- `jobos/boss_import.py`: BOSS import wrapper around the Node CDP adapter.
- `jobos/config.py`: user config and `.env` loading.
- `.github/workflows/test.yml`: pytest matrix for CI.

Current local test command:

```bash
python3 -m pytest tests/ --tb=short
```

Last observed result:

```text
478 passed, 9 failed, 16 warnings
```

Known failures to fix first:

- `tests/test_e2e.py`: `pack_generator.py` assumes `languages` is a list of strings, but fixtures may provide dictionaries.
- `tests/test_llm_mock.py`: LLM provider tests are influenced by local config and return `AnthropicAdapter` instead of `MockLLMAdapter`.
- `tests/test_submit_batch.py`: submitter button mock contract broke after checking locator counts.

Environment note:

- `python` currently fails because it points to `/tmp/acp-python-build/bin/python`.
- `python3` works and was used for the test baseline.

## Desired Loop

The loop should make each stage explicit and restartable:

```text
discover/import -> score -> predict -> pack -> validate -> submit attempt -> mark/retro -> report
```

Each run should leave structured evidence:

- Planned jobs and actions.
- Per-job stage results.
- Failure category and traceback or diagnostic.
- Screenshots/debug artifacts when browser actions are involved.
- Final summary suitable for `job report` or a new run report.

## Implementation Plan

### Phase 1: Restore Baseline

Task 1: Fix pack generation for language shapes.

Acceptance criteria:
- `profile/base.yaml` languages may be strings or dictionaries.
- Resume/contact generation does not raise `TypeError`.
- E2E pack and dry-run tests pass.

Likely files:
- `jobos/pack_generator.py`
- `tests/test_pack.py` or `tests/test_e2e.py`

Task 2: Isolate LLM provider tests from local config.

Acceptance criteria:
- Tests can force mock provider without depending on `~/.jobos/config.yaml`.
- `tests/test_llm_mock.py` passes under the user's current environment.

Likely files:
- `jobos/llm/provider.py`
- `tests/test_llm_mock.py`

Task 3: Repair submitter mock compatibility.

Acceptance criteria:
- Existing submit batch tests pass.
- `_click_chat_button` handles real locator counts and mocked locators predictably.

Likely files:
- `jobos/submitter.py`
- `tests/test_submit_batch.py`

Checkpoint:

```bash
python3 -m pytest tests/ --tb=short
```

Expected: all tests pass.

### Phase 2: Add Run Planning

Task 4: Add a read-only loop planner.

Proposed command:

```bash
job loop-plan --max-jobs 10 --output pipeline_runs/<run_id>/plan.json
```

Acceptance criteria:
- Reads `.job-state.json`.
- Produces a deterministic plan from current statuses.
- Does not mutate state.
- Groups actions by stage: score, predict, pack, validate, submit, retro.

Implemented convention:
- `job loop-plan` is read-only with respect to `.job-state.json`.
- If `--output` is omitted, the plan is written to `pipeline_runs/YYYYMMDD-HHMMSS/plan.json`.
- If `--output` is provided, relative paths are resolved from the workspace root.
- `plan.json` contains stable stage keys and avoids generated timestamps so repeated planning from the same state and options is deterministic.

Likely files:
- `jobos/loop.py`
- `jobos/cli.py`
- `tests/test_loop_plan.py`

Task 5: Add run directory conventions.

Acceptance criteria:
- Run outputs live under `pipeline_runs/YYYYMMDD-HHMMSS/`.
- Each run can contain `plan.json`, `events.jsonl`, `summary.json`, and optional artifacts.
- Paths are documented and used consistently.

Run directory layout:

```text
pipeline_runs/
  YYYYMMDD-HHMMSS/
    plan.json
    events.jsonl
    summary.json
    artifacts/
```

`plan.json` is created by `job loop-plan`. Later execution phases should append event records to `events.jsonl`, write the final aggregate result to `summary.json`, and place screenshots or browser diagnostics under `artifacts/`.

Likely files:
- `jobos/loop.py`
- `docs/automation-loop-handoff.md`
- `tests/test_loop_plan.py`

Checkpoint:

```bash
python3 -m pytest tests/test_loop_plan.py tests/test_queue.py --tb=short
```

Expected: loop planning and existing queue behavior are stable.

### Phase 3: Add Dry Run Execution

Task 6: Add `job loop-run --dry-run`.

Acceptance criteria:
- [Implemented] Executes non-browser stages only: score, predict, pack, validate.
- [Implemented] Continues after per-job failures.
- [Implemented] Writes `events.jsonl` and `summary.json`.
- [Implemented] Does not call submit/browser functions in dry-run mode.

Implemented command:

```bash
job loop-run --dry-run --max-jobs 10
```

`job loop-run --dry-run` creates `pipeline_runs/YYYYMMDD-HHMMSS/` by default. Use `--output <run_dir>` to choose a run dir.

Likely files:
- `jobos/loop.py`
- `jobos/cli.py`
- `tests/test_loop_run.py`

Task 7: Add per-job error classification.

Acceptance criteria:
- [Implemented] Known errors are classified with stable strings.
- [Implemented] Summary includes counts by stage and error class.
- [Implemented] A failed job can be retried in a later run.

Suggested error classes:
- `missing_state`
- `missing_job`
- `missing_pack`
- `pack_failed`
- `validation_failed`
- `browser_connect_failed`
- `no_url`
- `no_chat_button`
- `fill_failed`
- `send_failed`

Likely files:
- `jobos/loop.py`
- `jobos/submitter.py`
- `tests/test_loop_run.py`

Checkpoint:

```bash
python3 -m pytest tests/test_loop_run.py tests/test_e2e.py --tb=short
```

Expected: dry-run loop works on fixture workspaces.

### Phase 4: Improve Batch Submission Recoverability

Task 8: Persist submit attempts.

Acceptance criteria:
- [Implemented] Each submit attempt writes a structured record before and after execution.
- [Implemented] Attempts include `job_id`, URL, mode, timestamps, result, error class, screenshot paths.
- [Implemented] A process crash leaves a started attempt record under `applications/<job_id>/submit_attempts/`.

Likely files:
- `jobos/submitter.py`
- `jobos/loop.py`
- `tests/test_submit_batch.py`

Task 9: Add resume support.

Proposed command:

```bash
job loop-run --resume pipeline_runs/<run_id>
```

Acceptance criteria:
- [Implemented] Completed jobs are skipped.
- [Implemented] Failed or pending jobs can be retried.
- [Implemented] Summary clearly states skipped, retried, succeeded, and failed counts.

Implemented command:

```bash
job loop-run --resume pipeline_runs/<run_id> --dry-run
```

Likely files:
- `jobos/loop.py`
- `jobos/cli.py`
- `tests/test_loop_resume.py`

Checkpoint:

```bash
python3 -m pytest tests/test_loop_run.py tests/test_loop_resume.py tests/test_submit_batch.py --tb=short
```

Expected: interrupted runs are recoverable.

### Phase 4.5: Scrapling Extraction Diagnostics

Task 9.5: Make Scrapling a first-class optional extraction adapter.

Acceptance criteria:
- [Implemented] BOSS parsing exposes a shared extraction result with page classification, extractor name, selector attempts, fallback status, and item count.
- [Implemented] BOSS import uses Python extraction when the CDP adapter returns HTML and falls back to existing Node JSON items when no HTML is available.
- [Implemented] Imported jobs persist `extractor`, `page_state`, and `extraction_diagnostics`.
- [Implemented] Loop `events.jsonl` copies import-time extraction diagnostics onto stage events.
- [Implemented] Loop `summary.json` aggregates `by_extractor` and `by_page_state`.
- [Implemented] Submit attempts classify the current page HTML and persist page diagnostics plus recovery hints.
- [Implemented] Fixture replay covers normal, mutated DOM, login, verification, and access-limited pages.

Config:

```yaml
extraction:
  use_scrapling: true
  record_diagnostics: true
  include_html_snapshot: true
  html_snapshot_limit: 250000
```

Stable page states:
- `normal`
- `login_required`
- `verification_required`
- `access_limited`
- `empty`
- `page_shape_changed`

Focused verification:

```bash
python3 -m pytest tests/test_boss_parser.py tests/test_boss_import.py tests/test_loop_run.py tests/test_submit_batch.py --tb=short
```

Observed local result:

```text
70 passed, 21 warnings
```

Strengths observed locally:
- Scrapling and fallback extraction produce the same normalized card on the normal fixture.
- Both extractors handle the mutated fixture using data attributes and broader class selectors.
- Login, verification, and access-limited pages produce recovery-oriented page states before downstream stages continue.

Limits:
- BOSS salary digits may still be obfuscated by site fonts; placeholders are preserved when seen.
- Adaptive extraction depends on captured HTML. If the Node adapter cannot return HTML, import records `node_cdp` diagnostics and uses the adapter's JSON items.
- Submit diagnostics classify the current browser DOM only when the page object exposes HTML content.

Likely files:
- `jobos/extraction.py`
- `jobos/boss_parser.py`
- `jobos/boss_import.py`
- `jobos/loop.py`
- `jobos/submitter.py`
- `tests/test_boss_parser.py`
- `tests/test_boss_import.py`
- `tests/test_loop_run.py`
- `tests/test_submit_batch.py`

### Phase 4.6: Live BOSS Pipeline Hardening

Implemented live-mode semantics for `job start`:

- `--max-jobs` now means maximum successful submissions.
- Search rotates configured keywords and stops on successful submissions, daily limit, or candidate budget.
- Each candidate opens the detail page before scam check, match scoring, and greeting generation.
- Detail extraction records full JD, requirements, location, salary, company, recruiter/contact hints, job status, communication state, extractor, page state, and diagnostics.
- Detail extraction failures skip only the current candidate and are recorded in `pipeline_results.json`.
- Greetings are validated before send; wrong identity, recruiter/headhunter claims, unsupported claims, unrelated companies, excessive length, and spammy wording are blocked or rewritten once.
- Contacted jobs are persisted in `.job-contact-state.json` by job ID, URL, company/title, status, and timestamp.
- Already-contacted states such as `继续沟通` and `已发送` skip sending.
- Submit diagnostics include phase, strong success signals, page classification, extractor, recovery signals, and screenshot paths.
- Submit retry flow checks for pre-existing success before clicking send to avoid double-send.

Config:

```yaml
search:
  keywords:
    - Python后端
    - Python开发
    - 后端开发
    - Django
    - FastAPI
    - AI应用开发
  max_candidates_per_keyword: 20
  max_total_candidates: 100
scoring:
  min_score_to_apply: 60
```

Focused verification:

```bash
python3 -m pytest tests/test_live_pipeline_hardening.py --tb=short
```

Live smoke test remains gated by explicit human approval:

```bash
job start --keyword "Python后端" --max-jobs 1 --port 9222
```

### Phase 5: Operational Scripts

Task 10: Add idempotent scripts.

Scripts:
- `scripts/audit_env.sh`: prints Python, Node, Chrome/CDP, package, config, and pytest readiness.
- `scripts/local_ci.sh`: runs local test gates.
- `scripts/pipeline_dry_run.sh`: runs planning plus dry-run execution.

Acceptance criteria:
- [Implemented] Each script prints what it is about to do.
- [Implemented] Scripts are repeatable.
- [Implemented] Scripts avoid destructive actions.

Likely files:
- `scripts/audit_env.sh`
- `scripts/local_ci.sh`
- `scripts/pipeline_dry_run.sh`
- `tests/test_scripts.py` if shell script smoke tests are added.

Checkpoint:

```bash
bash scripts/audit_env.sh
bash scripts/local_ci.sh
```

Expected: scripts run and report actionable diagnostics.

## Suggested Agent Order

1. Fix the three current test failures before adding features.
2. Add `job loop-plan` as a read-only command.
3. Add `job loop-run --dry-run`.
4. Add structured event logging and summaries.
5. Add resume support.
6. Add operational scripts.
7. Update README and workflow docs after behavior exists.

## Commands To Explain Before Running

Agents should explain commands before running them, per project instructions.

Common commands:

```bash
git status --short
```

Shows dirty files so the agent avoids overwriting user work.

```bash
python3 -m pytest tests/ --tb=short
```

Runs the current test suite with compact tracebacks.

```bash
python3 -m pytest tests/test_loop_plan.py --tb=short
```

Runs only the new loop planner tests while developing that slice.

## Definition Of Done

- Full test suite passes with `python3 -m pytest tests/ --tb=short`.
- Loop planning is read-only and deterministic.
- Dry-run loop writes a complete run report.
- Batch attempts are structured and recoverable.
- README and workflow docs link to the loop commands and run artifacts.
- The implementation does not overwrite unrelated dirty worktree changes.
