# Architecture

## Data Flow

```
JD text/markdown
    │
    ▼
┌──────────┐   profile/*.yaml    ┌──────────┐   rubrics/*.md
│  import   │◄──────────────────►│  score   │◄──────────────────►
│ (normalize│   evidence_bank.md  │ (6 dims) │
│  to YAML) │                    └────┬─────┘
└──────────┘                         │
                                     ▼
                              ┌──────────┐
                              │ predict  │  ← immutable JSON
                              │ (probab- │    (refuses overwrite)
                              │ ilities) │
                              └────┬─────┘
                                   │
                                   ▼
                              ┌──────────┐
                              │   pack   │  ← 7 markdown files
                              │ (resume, │    generated from
                              │  greeting│    profile + evidence
                              │  etc.)   │    ONLY
                              └────┬─────┘
                                   │
                     ┌─────────────┼─────────────┐
                     ▼             ▼              ▼
               ┌──────────┐ ┌──────────┐  ┌──────────┐
               │ dry-run  │ │ mark-    │  │  retro   │
               │ (mock    │ │ submitted│  │ (3d/14d/ │
               │  form    │ │ (manual  │  │  30d     │
               │  fill)   │ │  record) │  │  status) │
               └──────────┘ └──────────┘  └────┬─────┘
                                                │
                                                ▼
                                          ┌──────────┐
                                          │  status  │  ← STATUS.md
                                          │ (dashboard│
                                          │  update) │
                                          └──────────┘
```

## Command Flow

Each CLI command maps to one or more Python modules:

| Command | Module(s) | State Mutation |
|---------|-----------|----------------|
| `job init` | `cli._cmd_init` | Creates dirs, `.job-state.json` |
| `job import` | `importer.import_job` | Writes `jobs/normalized/*.yaml`, updates state |
| `job score` | `scorer.score_job` | Updates state with scores |
| `job predict` | `predictor.create_prediction` | Writes `predictions/*.json` (immutable) |
| `job pack` | `pack_generator.generate_pack` | Writes `applications/<id>/*.md` |
| `job dry-run` | `dry_run.run_dry_run` | No state mutation (fills mock HTML in memory) |
| `job mark-submitted` | `retro.record_submission` | Updates state with submission metadata |
| `job retro` | `retro.record_retro` | Writes `retros/*.json`, updates state |
| `job status` | `status.update_status` | Writes `STATUS.md` |
| `job bump-rubric` | `rubric_manager.bump_rubric` | Writes candidate rubric, comparison report |
| `job doctor` | `doctor.run_doctor` | Read-only workspace, Pack, Run Ledger, and runtime-state integrity check |
| `job browser-check` | `browser_check.check_boss_browser` | Read-only BOSS connectivity/page-state check with screenshot, HTML, and JSON diagnostics |
| `job demo-seed` | `cli._cmd_demo_seed` | Creates sample workspace with fixtures |
| `job paste` | `importer.import_job` | Reads stdin, writes normalized YAML |
| `job queue` | `queue.get_queue` | Read-only pipeline stage view |
| `job runs` | `run_ledger.list_run_ledgers` | Read-only Run Ledger history |
| `job recommend` | `recommend.recommend_jobs` | Read-only ranked job list |
| `job validate-pack` | `evidence_markers.generate_workspace_evidence_report` | Persists validation and marks clean packs validated |
| `job report` | `report.generate_report` | Writes `reports/report.md` |
| `job scam-check` | `scam_checker.check_opportunity` | Appends to state `opportunities[]` |
| `job find` | `opportunity_finder.find_opportunities` | Appends to state `opportunities[]` |
| `job plan` | `action_planner.create_plan` | Writes `active_opportunity` in state |
| `job boss-import` | `boss_import.import_from_boss` | Writes `jobs/raw/*.json`, updates state |
| `job submit` | `submitter.submit_application` | No state mutation (dry-run default) |
| `job auto-submit` | `submitter.auto_submit_single`, `submitter.auto_submit_batch` | Writes submit attempt artifacts; updates state only after confirmed live success |
| `job start` | `orchestrator.run_full_pipeline` | Writes a live Run Ledger, submit attempts, contact/daily-limit state |
| `job auto-reply` | `auto_reply.run_auto_reply_loop` | Writes auto-reply state; dry-run unless live mode is explicit |
| `job retro-freeform` | `retro.record_freeform_retro` | Writes `retros/*.json`, appends `lessons.md` |

## Opportunity Pipeline

The opportunity pipeline extends the job application flow with income opportunity discovery, verification, and planning.

```
Profile (skills, tier)
    │
    ▼
┌──────────────┐
│  job find    │  ← discovers opportunities from profile + shared_references/
│ (opportunity │
│  finder)     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ job scam-    │  ← verifies legitimacy against red flag patterns
│ check        │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  job plan    │  ← generates 2-week execution plan with stop-loss
│ (action      │
│  planner)    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  job submit  │  ← semi-automatic submission (dry-run default)
│ (submitter)  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ job retro-   │  ← record freeform lessons
│ freeform     │
└──────────────┘
```

**State:** Opportunities are stored in `.job-state.json` under `opportunities[]`. Active plans go in `active_opportunity`. Lessons accumulate in `lessons.md`.

**Shared references:** `jobos/shared_references/` contains reference docs for the opportunity pipeline:
- `demand-signal-method.md` — primary method for finding real demand signals
- `user-tiers.md` — user tier classification (T0-T3) for filtering opportunities
- `opportunity-taxonomy.md` — categories of AI-era income opportunities

## Safety Boundaries

### Hard Constraints (enforced by code)

1. **Dry-run is the default.** `job dry-run`, `job loop-run --dry-run`, and unconfirmed submit commands do not send applications.
2. **Live BOSS mode is explicit.** `job start` and confirmed submit flows use a logged-in browser session only when the user requests live behavior. They are not part of the default offline workflow.
3. **Human-controlled browser session.** Live BOSS automation connects to an already-running browser session through CDP, or an explicitly isolated standalone browser when requested. It does not use hidden account credentials.
4. **No forbidden evasion.** The project does not implement proxy rotation, CAPTCHA bypass, credential stuffing, or security-verification circumvention.
5. **No fingerprint masking.** Standard Playwright is used without spoofed user agents, viewport, geolocation, simulated typing, or automation-flag masking.
6. **Duplicate and daily-limit guards.** Live BOSS flows persist contacted job state and daily limits to reduce repeat sends and uncontrolled volume.
7. **Diagnosed submit attempts.** Submit helpers capture screenshots, page state, extractor, recovery hints, and success signals so live behavior can be audited after the run.
8. **Validated Pack gate.** Workspace live submission requires clean persisted evidence validation and a hash-verified Pack manifest.
9. **Immutable predictions.** `predictor.save_prediction()` raises `FileExistsError` if a prediction file already exists. Only `--new-version` creates additional files.
10. **Rubric bump requires explicit approval.** `rubric_manager.bump_rubric()` creates a candidate but never activates it. The caller must explicitly call `set_active_rubric()`.
11. **Scam detection before pipeline entry.** `scam_checker.check_opportunity()` evaluates opportunities against red flag patterns. Only "feasible" or "suspect" verdicts enter the pipeline; "scam" verdicts are blocked.

### What This System Does NOT Do

- Does not default to live submission.
- Supports no live platform adapters for LinkedIn, Indeed, or other unimplemented platforms.
- Does not bypass BOSS login, verification, CAPTCHA, or access-limit states.
- Does not generate fabricated resume content.
- Does not send applications without an explicit live command and confirmation path.
- Does not require API keys for core offline functionality.

### Explicit Live BOSS Mode

Live BOSS mode exists for a logged-in browser session and is intentionally narrow:

- `job boss-import` imports BOSS search results through the CDP adapter and records extractor/page-state diagnostics.
- `job start` runs a live BOSS pipeline only when invoked explicitly. `--max-jobs` means maximum successful submissions, not maximum analyzed candidates.
- Before scoring and greeting generation, each BOSS candidate detail page is opened and classified.
- Unsafe greetings are rewritten once or skipped.
- Duplicate/contact state is persisted in `.job-contact-state.json`.
- Submit success requires strong signals such as an already-contacted state, visible sent state, greeting echo, or expected company chat context.
- Screenshots and page diagnostics are persisted under `applications/<job_id>/`.
- Live run plans, events, and summaries are persisted under `pipeline_runs/<run_id>/`.

This mode is documented by ADR-001 and should remain explicit, diagnosed, and conservative.

## LLM Adapter (Milestone 3)

The LLM adapter is implemented but defaults to a deterministic mock:

```
jobos/llm/
├── __init__.py
├── base.py       # Protocol interface (summarize_jd, improve_greeting, etc.)
├── mock.py       # Deterministic mock — passthrough, no randomness
└── provider.py   # Factory: get_llm_adapter(config) returns MockLLMAdapter by default
```

**Interface:**
```python
class LLMAdapter(Protocol):
    def summarize_jd(self, jd_text: str) -> dict: ...
    def improve_greeting(self, greeting: str, context: dict) -> str: ...
    def improve_cover_letter(self, cover_letter: str, context: dict) -> str: ...
    def rewrite_resume_bullet(self, bullet: str, context: dict) -> str: ...
    def explain_score(self, scores: dict, job_data: dict) -> str: ...
```

**Default behavior:** `get_llm_adapter()` returns `MockLLMAdapter` which passes text through unchanged. No API keys. No network calls. All tests use mock mode.

**Real providers:** Anthropic and OpenAI adapters can be selected through explicit config, process environment, `~/.jobos/.env`, or `~/.jobos/config.yaml`, in that order. Claude Code configuration is opt-in. LLM provider choice does not relax dry-run defaults, evidence grounding, or live BOSS confirmation requirements.

## File Structure

```
job-application-os/
├── jobos/                    # Python package
│   ├── cli.py               # CLI entry point (argparse, 24 commands)
│   ├── models.py            # Dataclasses: Job, Prediction, Retro, ApplicationPack
│   ├── scorer.py            # 6-dimension scoring engine with hard gates
│   ├── predictor.py         # Immutable prediction creation
│   ├── pack_generator.py    # Application pack generation + evidence validation
│   ├── application_pack.py  # Pack manifest, hashes, loading, integrity checks
│   ├── runtime_state.py     # Versioned, locked, atomic JSON persistence
│   ├── run_ledger.py        # Shared dry/live plan, event, summary artifacts
│   ├── automation_policy.py # Operating hours and daily live-action limits
│   ├── dry_run.py           # Local mock form filling
│   ├── importer.py          # JD text → normalized YAML
│   ├── profile_loader.py    # Profile + evidence bank loading
│   ├── retro.py             # Submission tracking + retro recording
│   ├── rubric_manager.py    # Rubric versioning + bump comparison
│   ├── status.py            # STATUS.md generator
│   ├── queue.py             # Pipeline stage grouping
│   ├── recommend.py         # Job ranking by composite quality
│   ├── evidence_markers.py  # Claim-level evidence mapping
│   ├── report.py            # Analytics report generation
│   ├── scam_checker.py      # Opportunity legitimacy verification
│   ├── opportunity_finder.py # Income opportunity discovery from profile
│   ├── action_planner.py    # Execution plan generation for opportunities
│   ├── boss_import.py       # BOSS Zhipin job import via CDP
│   ├── submitter.py         # Semi-automatic application submission
│   ├── shared_references/   # Reference docs (demand signals, tiers, taxonomy)
│   ├── llm/                 # LLM adapter (mock by default)
│   │   ├── base.py          # Protocol interface
│   │   ├── mock.py          # Deterministic mock
│   │   └── provider.py      # Factory
│   └── adapters/            # Form templates
├── profile/                  # User profile (YAML + evidence bank)
├── rubrics/                  # Scoring rubric definitions
├── tests/                    # Test suite (376+ tests)
├── .github/workflows/test.yml  # CI configuration
├── pyproject.toml           # Package metadata (primary)
├── setup.py                 # Package installation (legacy compat)
└── README.md                # User documentation
```
