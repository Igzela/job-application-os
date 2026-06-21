# Job Application OS Architecture Roadmap

## 1. Purpose

This document records the target architecture direction for Job Application OS. It exists to guide incremental refactoring without changing the product scope or weakening the existing safety constraints.

The roadmap addresses these problems:

- Unify project state, artifact layout, and pipeline rules.
- Reduce repeated workflow logic across CLI, TUI, loop execution, and live BOSS paths.
- Preserve the safety posture: dry-run remains the default, and live BOSS actions must be explicit.
- Improve testability and future agent navigability by putting important rules behind deeper Modules.

## Phase Status

| Phase | Status | Evidence |
|-------|--------|----------|
| Phase 1: Documentation Baseline | Completed on 2026-06-17 | This roadmap exists; `ARCHITECTURE.md` is aligned with explicit live BOSS mode; ADR-001 through ADR-003 record the decisions. |
| Phase 2: Workspace State | Completed on 2026-06-17 | `jobos/workspace.py` owns state defaults and canonical artifact paths; status, queue, recommend, report, retro, rubric, loop, submitter, CLI, REPL, TUI, and live orchestrator paths read/write through it. |
| Phase 3: Pipeline Rules | Completed on 2026-06-17 | `jobos/pipeline.py` owns stage ordering, next-action rules, queue buckets, submit candidate statuses, and transition validation. |
| Phase 4: BOSS Submission Adapter | Completed on 2026-06-17 | `jobos/boss_adapter.py` owns public BOSS page-action helpers and submit success classification; `jobos/submission.py` owns shared submit attempt records used by batch and live BOSS paths. |
| Phase 5: CLI Thin Shell | Completed on 2026-06-17 | Primary CLI workflows delegate to deeper public functions; `job auto-submit --job` no longer imports submitter private helpers; full local pytest passed with 574 tests. |
| Phase 6: Pack Generation Deepening | Completed on 2026-06-17 | `CandidateFacts` normalizes repeated profile/evidence derivation across resume, greeting, cover letter, and form-answer rendering; full local pytest passed with 575 tests. |
| Phase 7: Lifecycle Enforcement | Completed on 2026-06-20 | Production workflows use Pipeline transition Interfaces; manual submission updates status; live workspace submission requires clean validation. |
| Phase 8: Browser Safety Alignment | Completed on 2026-06-20 | Patchright, fingerprint masking, spoofed browser identity, and simulated typing were removed; ADR-004 records the decision. |
| Phase 9: Deep BOSS Adapter | Completed on 2026-06-20 | `submit_boss_application()` owns BOSS actions, diagnostics, screenshots, success proof, and attempt persistence. |
| Phase 10: Runtime State Reliability | Completed on 2026-06-20 | Workspace and operational JSON state use schema versioning, advisory locks, and atomic replacement. |
| Phase 11: Shared Run Ledger | Completed on 2026-06-20 | Dry and live runs write `plan.json`, `events.jsonl`, and `summary.json` under `pipeline_runs/<run_id>/`. |
| Phase 12: Application Pack Manifest | Completed on 2026-06-20 | Pack manifests record file/source hashes for job, profile, evidence, and prediction inputs plus validation; live workspace submission verifies file and source integrity before browser connection. |
| Phase 13: Configuration And Architecture Guards | Completed on 2026-06-20 | Configuration sources are explicit; CI runs compile and architecture guards; generated workspace artifacts are ignored and no longer tracked. |
| Phase 14: Run Ledger Operations | Completed on 2026-06-20 | `job runs` lists recent dry/live runs, planned runs, counts, failures, in-progress runs, and corrupt run directories, including missing-plan directories, malformed event records, and malformed summary counts, through `run_ledger.list_run_ledgers()`. |
| Phase 15: Workspace Integrity Doctor | Completed on 2026-06-20 | `job doctor` isolates corrupt state, verifies Pack files and sources, and distinguishes blocking errors from legacy Pack and corrupt Run Ledger warnings. |

## 2. Current Architecture

The current codebase is functional and has broad test coverage, but several important rules are spread across shallow Modules.

- `jobos/cli.py` is the largest entry point and owns too much business logic in addition to argument parsing and user output.
- `.job-state.json` is loaded and mutated directly by multiple Modules, including CLI, loop, queue, status, report, submitter, retro, TUI screens, and rubric code.
- Dry-run loop execution, batch submit, and the live BOSS pipeline each have their own view of job status flow.
- BOSS browser interaction and submit success classification are split across `jobos/submitter.py`, `jobos/orchestrator.py`, and `jobos/live_pipeline.py`.
- Application pack generation, candidate fact derivation, markdown rendering, and evidence validation all live in `jobos/pack_generator.py`.

These problems create low locality: a change to state shape, artifact paths, or submit safety behavior requires checking many files.

## 3. Architectural Principles

Future architecture work should follow these principles:

- State rules live in one Module.
- CLI is a shell, not the workflow owner.
- Browser automation happens behind platform Adapters.
- Pipeline stages are explicit, typed, and restartable.
- Evidence grounding remains mandatory before submission.
- One Adapter means a hypothetical Seam; two Adapters means a real Seam.
- Existing public Interfaces should stay stable until callers have migrated.
- Changes should be incremental and covered at the Module Interface where callers cross the Seam.

## 4. Target Module Map

### Workspace State Module

Purpose: own the project workspace layout and state persistence rules.

Responsibilities:

- Load and save `.job-state.json`.
- Provide schema defaults and future schema migrations.
- Own job status transition helpers.
- Own artifact path lookup for `jobs/`, `predictions/`, `applications/`, `retros/`, `pipeline_runs/`, and submit attempts.
- Expose read-only queries used by queue, status, report, recommendation, loop planning, and TUI screens.

Expected leverage:

- Callers stop hard-coding state paths and artifact directories.
- Status and artifact layout drift is fixed once in one place.
- Tests can assert workspace behavior through one stable Interface.

### Pipeline Module

Purpose: own the job pipeline state machine and run evidence format.

Responsibilities:

- Define stage ordering.
- Calculate the next action for each job.
- Execute dry-run stages: score, predict, pack, validate.
- Define resume semantics.
- Write and summarize `plan.json`, `events.jsonl`, and `summary.json`.
- Classify errors with stable strings.

Expected leverage:

- Queue, loop-run, report, TUI, and submit batch share the same status interpretation.
- Adding a new stage or changing a transition is local.
- Restartability remains observable and testable.

### Submission Module

Purpose: own platform-neutral submit attempt recording and diagnostics.

Responsibilities:

- Define submit attempt JSON shape.
- Record started, succeeded, failed, skipped, and unverified submit phases.
- Own screenshot naming conventions.
- Own page diagnostics aggregation.
- Own success signal representation.

Expected leverage:

- Submit attempts look the same whether they are invoked from batch submit or live pipeline.
- Diagnostics are easier to compare across runs.
- Browser failure handling can be tested without invoking a full pipeline.

### BOSS Adapter

Purpose: contain BOSS-specific browser behavior behind one Adapter.

Responsibilities:

- Connect to or select a BOSS browser page.
- Search BOSS jobs.
- Extract list and detail pages.
- Detect login, verification, access-limited, empty, and page-shape-changed states.
- Open chat, fill greeting, click send, and classify BOSS-specific success signals.
- Own BOSS duplicate/contact state.

Expected leverage:

- `orchestrator.py` no longer needs to import private functions from `submitter.py`.
- Page selector changes and BOSS-specific safety checks are local to one Adapter.
- Future platform Adapters can reuse the Submission Module without inheriting BOSS assumptions.

### Application Pack Module

Purpose: produce grounded application artifacts from normalized facts.

Responsibilities:

- Derive normalized candidate facts from profile and evidence.
- Render markdown artifacts: JD, prediction, targeted resume, greeting, cover letter, form answers, and submit checklist.
- Validate claims against the evidence bank.
- Keep `generate_pack` and `validate_pack` stable while internal structure improves.

Expected leverage:

- Education, skills, availability, and project facts are derived once.
- Pack output remains deterministic and evidence-grounded.
- Tests can target fact derivation, artifact rendering, and evidence validation separately.

## 5. Migration Plan

### Phase 1: Documentation Baseline

Goal: make the architecture direction explicit before refactoring.

Status: completed on 2026-06-17.

Tasks:

- [x] Add this architecture roadmap.
- [x] Update `ARCHITECTURE.md` where it still describes BOSS live mode as future or impossible.
- [x] Create `docs/decisions/`.
- [x] Write initial ADRs:
  - Live BOSS mode is explicit and diagnosed.
  - Workspace state owns artifact layout.
  - CLI delegates workflows to deeper Modules.

Acceptance criteria:

- Future agents can find the target architecture without re-running the audit.
- Existing docs no longer contradict the current BOSS live behavior.
- ADRs capture decisions that would otherwise be re-litigated.

Phase 1 notes:

- ADR-001 records the live BOSS safety posture.
- ADR-002 records that workspace state and artifact layout should move behind one Module.
- ADR-003 records that CLI should become a thin shell over deeper workflow Modules.
- Next phase: implement the Workspace State Module and migrate low-risk readers first.

### Phase 2: Workspace State

Goal: concentrate state and artifact layout knowledge.

Tasks:

- Add `jobos/workspace.py` or `jobos/state_store.py`.
- Move `.job-state.json` load/save defaults into that Module.
- Centralize artifact paths for `applications/`, `predictions/`, `pipeline_runs/`, `jobs/raw`, `jobs/normalized`, and `retros/`.
- Fix the current drift where status artifact counting refers to `packs/` while generated packs live under `applications/`.
- Migrate status, queue, recommend, report, loop, submitter, TUI, and CLI incrementally.

Acceptance criteria:

- There is one primary Module for workspace state access.
- New code does not call `json.loads(state_path.read_text())` directly for `.job-state.json`.
- Artifact directory names are not duplicated across workflow Modules.

Progress:

- 2026-06-17 slice 1:
  - Added `jobos/workspace.py` as the Workspace State Module.
  - Centralized `.job-state.json` defaults, `load_state`, `save_state`, and canonical paths for `predictions/`, `applications/`, `pipeline_runs/`, `jobs/raw`, `jobs/normalized`, `retros/`, and submit attempts.
  - Migrated `jobos/status.py`, `jobos/queue.py`, `jobos/recommend.py`, and `jobos/report.py` to use the Workspace State Module for state reads and artifact paths.
  - Fixed status artifact counting to read application packs from `applications/<job_id>/` instead of the stale `packs/` directory.
  - Updated test fixtures that still created `packs/` for the workspace layout.
  - Verification: `python3 -m pytest tests/test_workspace.py tests/test_status.py tests/test_queue.py tests/test_recommend.py tests/test_report.py tests/test_new_cli_cmds.py --tb=short` passed with 52 tests.
- 2026-06-17 slice 2:
  - Added explicit state-file helpers in `jobos/workspace.py` so callers that already receive a state file path can preserve that Interface while sharing the Workspace State implementation.
  - Migrated `jobos/retro.py` to use `load_state`, `save_state`, and `retros_dir`.
  - Migrated `jobos/rubric_manager.py` to use `load_state_file` and `save_state_file`.
  - Verification: `python3 -m pytest tests/test_workspace.py tests/test_status.py tests/test_queue.py tests/test_recommend.py tests/test_report.py tests/test_new_cli_cmds.py tests/test_retro.py tests/test_bump_rubric.py --tb=short` passed with 101 tests.
- 2026-06-17 slice 3:
  - Added canonical workspace directory constants used by path helpers.
  - Migrated `jobos/loop.py` state load/save, default run directory, normalized job lookup, prediction directory, and application pack directory usage to the Workspace State Module.
  - Verification: `python3 -m pytest tests/test_workspace.py tests/test_status.py tests/test_queue.py tests/test_recommend.py tests/test_report.py tests/test_new_cli_cmds.py tests/test_retro.py tests/test_bump_rubric.py tests/test_loop_plan.py tests/test_loop_run.py tests/test_loop_resume.py --tb=short` passed with 115 tests.
- 2026-06-17 slice 4:
  - Migrated `jobos/submitter.py` state loading/saving, application pack lookup, screenshot directory lookup, and submit attempt path generation to the Workspace State Module.
  - Preserved the existing batch error text for missing `.job-state.json`.
  - Verification: `python3 -m pytest tests/test_submitter.py tests/test_submit_batch.py --tb=short` passed with 48 tests.
- 2026-06-17 slice 5:
  - Migrated `jobos/cli.py` state loading/saving and canonical paths for init, import, score, predict, pack, dry-run, bump-rubric, doctor, demo-seed, paste, validate-pack, opportunity commands, auto-submit, BOSS import, and analyze.
  - Preserved existing user-facing path text such as `jobs/raw/`, `jobs/normalized/`, and `applications/<job_id>/`.
  - Verification: `python3 -m pytest tests/test_init.py tests/test_paste.py tests/test_new_cli_cmds.py tests/test_doctor.py tests/test_demo_seed.py tests/test_loop_plan.py tests/test_loop_run.py tests/test_boss_import.py tests/test_validate_pack_cmd.py tests/test_e2e.py --tb=short` passed with 93 tests.
- 2026-06-17 slice 6:
  - Migrated `jobos/repl.py`, `jobos/tui/app.py`, and TUI screens for import, dashboard, jobs, LLM chat, and settings to use Workspace State helpers for state reads/writes and canonical paths.
  - Preserved existing command output and visible directory labels while removing direct path construction from interactive callers.
  - Verification: `python3 -m py_compile jobos/repl.py jobos/tui/app.py jobos/tui/screens/import_screen.py jobos/tui/screens/dashboard.py jobos/tui/screens/jobs.py jobos/tui/screens/llm_chat.py jobos/tui/screens/settings.py` passed; cumulative Phase 2 tests through REPL/TUI passed with 189 tests.
- 2026-06-17 slice 7:
  - Removed the unused direct `.job-state.json` read from `jobos/orchestrator.py`.
  - Migrated live BOSS screenshot directory lookup to `application_dir()`.
  - Verified that remaining direct `json.loads(...read_text())` matches are sidecar JSON state files in `anti_detect.py`, `auto_reply.py`, and `live_pipeline.py`, not `.job-state.json`.
  - Verification: `python3 -m pytest tests/test_live_pipeline_hardening.py tests/test_llm_integration.py --tb=short` passed with 32 tests.

Phase 2 completion notes:

- `jobos/workspace.py` is now the primary Module for `.job-state.json` defaults, load/save helpers, and canonical workspace artifact paths.
- Core workflow Modules no longer hard-code `applications/`, `predictions/`, `retros/`, `jobs/raw`, or `jobs/normalized` paths outside Workspace State helpers.
- The known remaining JSON sidecar files are intentionally outside Phase 2 scope: `.daily_limits.json`, `auto_reply_state.json`, and `boss_contact_state.json`.
- Full verification: `python3 -m pytest --tb=short` passed with 537 tests and 24 warnings.

### Phase 3: Pipeline Rules

Goal: make the job pipeline state machine explicit.

Tasks:

- Extract status-to-next-action rules from `jobos/loop.py` into a small public Interface.
- Define accepted statuses and transitions in one place.
- Update queue, loop planning, loop execution, submit batch, and TUI views to use the shared rules.
- Add tests for stage ordering, transition validity, skipped stages, and resume behavior.

Acceptance criteria:

- Dry-run loop and live submit paths share the same stage/status interpretation.
- Unknown statuses have an intentional fallback or validation error.
- Stage transition tests cover imported, scored, predicted, packed, validated, ready-to-submit, submitted, and retro states.

Status: completed on 2026-06-17.

Progress:

- 2026-06-17 slice 1:
  - Added `jobos/pipeline.py` as the shared pure rules Module for pipeline stages, dry-run stages, known job statuses, queue buckets, submit candidate statuses, next actions, remaining dry-run stages, and valid transitions.
  - Migrated `jobos/loop.py` planning and dry-run execution to use `action_for_job()` and `remaining_dry_run_stages()`.
  - Migrated `jobos/queue.py` to use `queue_buckets_for_job()`.
  - Migrated `jobos/submitter.py` batch candidate filtering to use `is_submit_candidate_status()` while preserving the existing compatibility behavior for `predicted` and `packed` jobs that already have packs.
  - Migrated dashboard pending-action views in `jobos/tui/app.py` and `jobos/tui/screens/dashboard.py` to use the shared next-action rule.
  - Added `tests/test_pipeline.py` for stage ordering, next-action derivation, queue bucket derivation, submit candidate status compatibility, unknown-status fallback, and transition validity.
  - Verification: `python3 -m pytest tests/test_pipeline.py tests/test_loop_plan.py tests/test_loop_run.py tests/test_loop_resume.py tests/test_queue.py tests/test_submit_batch.py --tb=short` passed with 52 tests and 3 warnings.
  - Static verification: `git diff --check` passed, and core workflow search found state branching concentrated in `jobos/pipeline.py`.
  - Full verification: `python3 -m pytest --tb=short` passed with 544 tests and 24 warnings.

### Phase 4: BOSS Submission Adapter

Goal: put BOSS browser automation behind a real Adapter Interface.

Tasks:

- Add a public BOSS submit function or class that owns chat open, greeting fill, send click, diagnostics, screenshots, and success classification.
- Move private submit helper usage out of `jobos/orchestrator.py`.
- Route batch submit and live pipeline submission through the same BOSS Adapter.
- Keep dry-run and explicit live modes visible at the Interface.
- Preserve duplicate/contact state behavior.

Acceptance criteria:

- `orchestrator.py` does not import `_click_chat_button`, `_fill_greeting`, `_click_send`, or `_take_screenshot`.
- BOSS submit attempt records have one shape across batch and live pipeline runs.
- Success signals are classified consistently before and after send.

Status: completed on 2026-06-17.

Progress:

- 2026-06-17 slice 1:
  - Added `jobos/boss_adapter.py` as the public BOSS browser Adapter for BOSS selectors, human delay, BOSS tab lookup, job-page navigation, chat button click, greeting fill, send click, and screenshots.
  - Migrated `jobos/submitter.py` helper implementations to delegate to `jobos/boss_adapter.py` while preserving existing private aliases for compatibility with older tests and callers.
  - Migrated `jobos/orchestrator.py` to import public BOSS Adapter helpers instead of private submitter functions.
  - Added `tests/test_boss_adapter.py` for public helper behavior, submitter compatibility aliases, and the no-private-submit-helper import rule.
  - Verification: `python3 -m pytest tests/test_boss_adapter.py tests/test_submit_batch.py tests/test_live_pipeline_hardening.py --tb=short` passed with 38 tests and 6 warnings.
  - Static verification: `python3 -m py_compile jobos/boss_adapter.py jobos/submitter.py jobos/orchestrator.py` passed; core search found BOSS selector ownership only in `jobos/boss_adapter.py`.
- 2026-06-17 slice 2:
  - Added `jobos/submission.py` as the shared submit attempt record helper Module.
  - Centralized submit error classification, attempt path generation, started attempt record shape, finished attempt update shape, and deterministic JSON writes.
  - Migrated `jobos/submitter.py` to use `jobos/submission.py` for submit attempt record construction while preserving existing private helper wrappers.
  - Added `tests/test_submission.py` for canonical started record shape, finished record update shape, attempt path generation, JSON persistence, and stable error classes.
  - Verification: `python3 -m pytest tests/test_submission.py tests/test_submit_batch.py tests/test_boss_adapter.py --tb=short` passed with 33 tests and 3 warnings.
  - Static verification: `python3 -m py_compile jobos/submission.py jobos/submitter.py` passed.
- 2026-06-17 slice 3:
  - Extended `jobos/submission.py` finished-attempt updates with optional live submit metadata: `submit_phase`, `success_signals`, and named screenshot paths.
  - Migrated live BOSS `_submit_candidate()` in `jobos/orchestrator.py` to create and finish canonical submit attempt records via `jobos/submission.py`.
  - Preserved the live pipeline return shape while adding `attempt_path` for recorded live attempts.
  - Added live coverage in `tests/test_live_pipeline_hardening.py` proving live BOSS submit failures persist the same attempt envelope as batch submit.
  - Verification: `python3 -m pytest tests/test_submission.py tests/test_live_pipeline_hardening.py::test_live_submit_candidate_persists_shared_attempt_record --tb=short` passed with 7 tests.
- 2026-06-17 slice 4:
  - Added shared BOSS submit success classification in `jobos/boss_adapter.py` via `classify_page_submit_success()`, including HTML signals and visible BOSS sent-state detection.
  - Migrated `jobos/orchestrator.py` away from its local submit success classifier.
  - Migrated `jobos/submitter.py` live confirm mode to record success signals from the shared BOSS Adapter classifier while preserving existing send-click behavior.
  - Added tests for shared success signal classification and batch attempt `success_signals`.
  - Verification: `python3 -m pytest tests/test_submission.py tests/test_boss_adapter.py tests/test_submit_batch.py tests/test_live_pipeline_hardening.py --tb=short` passed with 47 tests and 10 warnings.
  - Static verification: `git diff --check` and `python3 -m py_compile jobos/boss_adapter.py jobos/submission.py jobos/submitter.py jobos/orchestrator.py` passed; search found BOSS submit selectors only in `jobos/boss_adapter.py` and no private submitter browser-helper imports in `jobos/orchestrator.py`.
  - Full verification: `python3 -m pytest --tb=short` passed with 557 tests and 28 warnings.

### Phase 5: CLI Thin Shell

Goal: reduce CLI coupling and make workflows reusable from CLI, TUI, REPL, tests, and agents.

Status: completed on 2026-06-17.

Tasks:

- Keep argparse registration and command output in `jobos/cli.py`.
- Move command workflows into public functions on deeper Modules.
- Replace direct state manipulation inside `_cmd_*` handlers with workspace/pipeline calls.
- Migrate tests away from private CLI handlers when a deeper public Interface exists.

Acceptance criteria:

- CLI handlers mostly parse arguments, call a workflow Interface, and render output.
- Business behavior can be tested without invoking CLI private functions.
- CLI-specific tests focus on argument handling and exit behavior.

Progress:

- 2026-06-17 slice 1:
  - Added `workspace.initialize_workspace()` plus `WorkspaceInitResult`, workspace directory constants, workspace template constants, and `initial_state()`.
  - Migrated `jobos/cli.py` `_cmd_init()` to delegate workspace creation to `workspace.initialize_workspace()` while preserving existing command output.
  - Added direct workspace tests for required layout creation and idempotency.
  - Verification: `python3 -m pytest tests/test_workspace.py tests/test_init.py tests/test_e2e.py --tb=short` passed with 42 tests.
  - Static verification: `python3 -m py_compile jobos/workspace.py jobos/cli.py` passed.
- 2026-06-17 slice 2:
  - Added `importer.import_job_text()` for importing raw JD text without a temporary file.
  - Added `importer.import_pasted_job()` as the public workflow for pasted JD import and state update.
  - Migrated `jobos/cli.py` `_cmd_paste()` to read stdin and delegate import/state mutation to `import_pasted_job()`.
  - Added direct workflow coverage in `tests/test_paste.py`.
  - Verification: `python3 -m pytest tests/test_paste.py tests/test_import.py --tb=short` passed with 15 tests.
  - Static verification: `python3 -m py_compile jobos/importer.py jobos/cli.py` passed.
- 2026-06-17 slice 3:
  - Added `scorer.score_workspace_job()` as the public workflow for loading normalized job data, profile, evidence, rubric, scoring the job, and updating workspace state.
  - Migrated `jobos/cli.py` `_cmd_score()` to delegate scoring/state mutation to `score_workspace_job()` while keeping CLI output local.
  - Added direct scorer workflow coverage in `tests/test_score.py`.
  - Verification: `python3 -m pytest tests/test_score.py tests/test_e2e.py --tb=short` passed with 37 tests.
  - Static verification: `python3 -m py_compile jobos/scorer.py jobos/cli.py` passed.
- 2026-06-17 slice 4:
  - Added `predictor.predict_workspace_job()` plus `WorkspacePredictionResult` as the public workflow for creating immutable predictions from workspace state and marking jobs predicted.
  - Migrated `jobos/cli.py` `_cmd_predict()` to delegate prediction/state mutation to `predict_workspace_job()` while preserving CLI output and error behavior.
  - Added direct prediction workflow coverage in `tests/test_predict.py`, including new-version creation.
  - Verification: `python3 -m pytest tests/test_predict.py tests/test_e2e.py tests/test_new_cli_cmds.py --tb=short` passed with 32 tests.
- 2026-06-17 slice 5:
  - Added `pack_generator.generate_workspace_pack()` plus `WorkspacePackResult` as the public workflow for loading job data, prediction, profile, and evidence, writing application pack files, validating claims, and marking jobs packed.
  - Migrated `jobos/cli.py` `_cmd_pack()` to delegate pack generation/state mutation to `generate_workspace_pack()` while preserving CLI output and error behavior.
  - Added direct pack workflow coverage in `tests/test_pack.py`.
  - Verification: `python3 -m pytest tests/test_pack.py tests/test_e2e.py tests/test_validate_pack_cmd.py tests/test_new_cli_cmds.py --tb=short` passed with 59 tests.
- 2026-06-17 slice 6:
  - Added `dry_run.run_workspace_dry_run()` as the public workflow for loading saved application pack files and selecting the workspace mock form before executing a dry-run.
  - Migrated `jobos/cli.py` `_cmd_dry_run()` to delegate pack loading and mock-form selection to `run_workspace_dry_run()` while keeping CLI output local.
  - Added direct dry-run workflow coverage in `tests/test_dry_run.py`.
  - Verification: `python3 -m pytest tests/test_dry_run.py tests/test_e2e.py tests/test_new_cli_cmds.py --tb=short` passed with 42 tests.
- 2026-06-17 slice 7:
  - Added `evidence_markers.generate_workspace_evidence_report()` as the public workflow for loading saved pack files, evidence bank data, and normalized job data before generating an evidence report.
  - Migrated `jobos/cli.py` `_cmd_validate_pack()` to delegate evidence report assembly to `generate_workspace_evidence_report()` while keeping CLI output local.
  - Added direct validate-pack workflow coverage in `tests/test_validate_pack_cmd.py`.
  - Verification: `python3 -m pytest tests/test_validate_pack_cmd.py tests/test_pack.py tests/test_e2e.py tests/test_new_cli_cmds.py --tb=short` passed with 60 tests.
- 2026-06-17 slice 8:
  - Added `jobos/doctor.py` with `run_doctor()` plus structured `DoctorReport` and `DoctorCheck` results for workspace health checks.
  - Migrated `jobos/cli.py` `_cmd_doctor()` to delegate all health-check logic to `run_doctor()` while preserving existing CLI output and exit behavior.
  - Added direct doctor report coverage in `tests/test_doctor.py`.
  - Verification: `python3 -m pytest tests/test_doctor.py tests/test_init.py tests/test_e2e.py tests/test_new_cli_cmds.py --tb=short` passed with 47 tests.
- 2026-06-17 slice 9:
  - Added `jobos/demo_seed.py` with `seed_demo_workspace()` plus `DemoSeedResult` for idempotent demo workspace creation.
  - Migrated `jobos/cli.py` `_cmd_demo_seed()` to delegate all fixture/profile/rubric/sample generation to `seed_demo_workspace()` while keeping output local.
  - Added direct demo seed workflow coverage in `tests/test_demo_seed.py`.
  - Verification: `python3 -m pytest tests/test_demo_seed.py tests/test_doctor.py tests/test_init.py tests/test_e2e.py tests/test_new_cli_cmds.py --tb=short` passed with 55 tests.
- 2026-06-17 slice 10:
  - Added `boss_import.import_boss_jobs_to_workspace()` plus `BossWorkspaceImportResult` for persisting BOSS raw JSON files and state entries after adapter extraction.
  - Migrated `jobos/cli.py` `_cmd_boss_import()` to delegate raw-file/state mutation to `import_boss_jobs_to_workspace()` while preserving output and adapter error handling.
  - Added direct workspace import coverage in `tests/test_boss_import.py` with the BOSS adapter mocked; no live BOSS/browser action is executed by the test.
  - Verification: `python3 -m pytest tests/test_boss_import.py tests/test_new_cli_cmds.py --tb=short` passed with 23 tests.
- 2026-06-17 slice 11:
  - Added `jobos/job_analysis.py` with `analyze_workspace_job()` plus `JobAnalysisResult` and `JobAnalysisInputError` for loading workspace job/profile data and running LLM scam, match, and explanation analysis.
  - Migrated `jobos/cli.py` `_cmd_analyze()` to delegate workspace loading and LLM workflow execution to `analyze_workspace_job()` while keeping CLI output local.
  - Added direct analysis workflow coverage in `tests/test_llm_integration.py` with the mock LLM adapter; no network LLM call is executed by the test.
  - Verification: `python3 -m pytest tests/test_llm_integration.py tests/test_new_cli_cmds.py --tb=short` passed with 31 tests.
- 2026-06-17 slice 12:
  - Added `jobos/opportunity_workflows.py` with workflows for scam-check persistence, profile-based opportunity finding, and opportunity action-plan persistence.
  - Migrated `jobos/cli.py` `_cmd_scam_check()`, `_cmd_find()`, and `_cmd_plan()` to delegate workspace state mutation to the new opportunity workflows while preserving CLI output.
  - Added direct opportunity workflow coverage in `tests/test_new_cli_cmds.py`.
  - Verification: `python3 -m pytest tests/test_new_cli_cmds.py tests/test_opportunity_finder.py --tb=short` passed with 39 tests.
- 2026-06-17 slice 13:
  - Added `submitter.auto_submit_workspace_job()` as the public single-job auto-submit workflow for loading workspace state and pack files, connecting to the browser, calling `auto_submit_single()`, and cleaning up browser resources.
  - Migrated `jobos/cli.py` `_cmd_auto_submit()` single-job mode away from private submitter helpers `_load_pack_files()` and `_connect_browser()`.
  - Added direct workspace auto-submit coverage in `tests/test_submit_batch.py` with browser and single-submit calls mocked; no real browser/live send is executed by the test.
  - Verification: `python3 -m pytest tests/test_submit_batch.py tests/test_submitter.py --tb=short` passed with 49 tests and 7 warnings.

Phase 5 completion notes:

- CLI handlers now primarily parse arguments, call public workflow Interfaces, and render output.
- Main workspace workflows are directly testable without private CLI handlers: init, paste, score, predict, pack, dry-run, validate-pack, doctor, demo-seed, BOSS import, LLM analyze, opportunity commands, and single-job auto-submit.
- Interactive/configuration commands (`chat`, `config`, `tui`, `onboard`, `auto-reply`) remain CLI shells over existing interactive Modules and are outside this phase's deeper workflow scope.
- Full verification: `python3 -m pytest --tb=short` passed with 574 tests and 28 warnings.

### Phase 6: Pack Generation Deepening

Goal: make pack generation easier to change without weakening evidence constraints.

Status: completed on 2026-06-17.

Tasks:

- Introduce normalized candidate facts derived from profile and evidence.
- Move repeated education, skills, availability, and work-arrangement derivation behind fact helpers.
- Keep markdown rendering deterministic.
- Keep claim validation mandatory and close to generated artifacts.
- Preserve `generate_pack` and `validate_pack` as stable external Interfaces during migration.

Acceptance criteria:

- Repeated fact derivation logic is removed from individual artifact renderers.
- Evidence validation still flags unsupported generated claims.
- Existing pack, hallucination, truthfulness, and e2e tests continue to pass.

Progress:

- 2026-06-17 slice 1:
  - Added `CandidateFacts` and `derive_candidate_facts()` to normalize repeated candidate facts from profile and evidence bank data.
  - Migrated greeting, cover letter, and form-answer rendering to use normalized candidate facts for education, skills, availability, work arrangement, location, constraints, and project names.
  - Added direct facts-derivation coverage in `tests/test_pack.py`.
  - Verification: `python3 -m pytest tests/test_pack.py tests/test_m4b_defaults.py tests/test_truthfulness.py tests/test_hallucination.py --tb=short` passed with 69 tests.
- 2026-06-17 slice 2:
  - Extended `CandidateFacts` with contact, education, and formatted skill labels needed by resume rendering.
  - Migrated resume contact, education, skills, availability, and work-arrangement rendering to use normalized candidate facts instead of repeating profile traversal.
  - Verification: `python3 -m pytest tests/test_pack.py tests/test_m4b_defaults.py tests/test_truthfulness.py tests/test_hallucination.py --tb=short` passed with 69 tests.

Phase 6 completion notes:

- Pack renderers now receive repeated candidate facts through one normalized derivation point.
- `profile.get(...)` traversal for candidate facts is concentrated in `derive_candidate_facts()`.
- Evidence grounding remains enforced by `validate_pack()` and evidence marker tests.
- Full verification: `python3 -m pytest --tb=short` passed with 575 tests and 28 warnings.

## 6. Non-Goals

This roadmap does not propose:

- Replacing the Python CLI stack.
- Introducing a database.
- Expanding default live submission permissions.
- Rewriting the BOSS parser from scratch.
- Reworking product positioning or profile content.
- Performing one large refactor across the whole codebase.

## 7. Acceptance Criteria

The roadmap is complete when the target architecture is implemented and verified by current-state evidence:

- `.job-state.json` has one primary read/write Module.
- Artifact path rules are not duplicated across workflow Modules.
- CLI is visibly thinner and delegates workflows to deeper Modules.
- `orchestrator.py` does not depend on submitter private functions.
- Dry-run loop and live submit share stage/status rules.
- BOSS submit attempts use a consistent diagnostics and artifact format.
- Application pack generation still requires evidence grounding.
- `python3 -m pytest tests/ --tb=short` passes.

## 8. Suggested Implementation Order

1. Land this roadmap and the first ADRs.
2. Add the Workspace State Module and migrate low-risk readers first: status, queue, recommend, report.
3. Migrate loop planning and loop execution to the Workspace State Module.
4. Extract shared pipeline status rules.
5. Consolidate submit attempt recording and BOSS submission behavior.
6. Thin CLI handlers after deeper Interfaces are stable.
7. Deepen pack generation internals while keeping external pack Interfaces stable.

This order keeps each migration reversible and limits the number of files touched in each step.

## 9. Post-Roadmap Hardening

Phases 7 through 15 implement the incremental audit performed after the
original roadmap completed:

- Lifecycle transitions execute through the Pipeline Module.
- Live workspace submission requires evidence validation and Pack integrity.
- Standard Playwright replaces browser fingerprint masking.
- The BOSS Adapter exposes one deep submission Interface.
- Mutable JSON state is versioned and atomically written.
- Dry and live runs share one Run Ledger format.
- Application Packs carry hashes and validation state.
- Configuration does not mutate process environment or silently consume
  Claude Code credentials.
- `scripts/check_architecture.sh` protects these constraints in local CI and
  GitHub Actions.
- `job runs` exposes Run Ledger history without requiring filesystem inspection;
  one corrupt run does not block healthy run discovery.
- `job doctor` reports blocking workspace, Pack, and runtime-state integrity
  errors separately from legacy Pack and corrupt Run Ledger warnings.
