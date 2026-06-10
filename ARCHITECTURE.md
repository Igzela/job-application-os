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
| `job doctor` | `cli._cmd_doctor` | Read-only health check |
| `job demo-seed` | `cli._cmd_demo_seed` | Creates sample workspace with fixtures |
| `job paste` | `importer.import_job` | Reads stdin, writes normalized YAML |
| `job queue` | `queue.get_queue` | Read-only pipeline stage view |
| `job recommend` | `recommend.recommend_jobs` | Read-only ranked job list |
| `job validate-pack` | `evidence_markers.generate_evidence_report` | Read-only evidence audit |
| `job report` | `report.generate_report` | Writes `reports/report.md` |

## Safety Boundaries

### Hard Constraints (enforced by code)

1. **No live submission.** The `dry_run` module only fills local HTML forms. No HTTP client is imported or called.
2. **No anti-detection.** No proxy rotation, CAPTCHA bypass, undetected-chromedriver, or scraping evasion code exists anywhere in this project.
3. **Evidence-only resume.** `pack_generator.validate_pack()` checks every claim in generated resumes against the evidence bank. Unsupported claims are flagged as warnings.
4. **Immutable predictions.** `predictor.save_prediction()` raises `FileExistsError` if a prediction file already exists. Only `--new-version` creates additional files.
5. **Rubric bump requires explicit approval.** `rubric_manager.bump_rubric()` creates a candidate but never activates it. The caller must explicitly call `set_active_rubric()`.

### What This System Does NOT Do

- Does not connect to LinkedIn, Indeed, BOSS Zhipin, or any live job platform
- Does not automate browser actions against real websites
- Does not generate fabricated resume content
- Does not submit applications on the user's behalf
- Does not require API keys for core functionality

### Assist-Only Mode (Future)

When a `boss_assist` or similar adapter is added, it will:
- Parse user-provided page content / JD text
- Fill draft forms locally
- **Require human confirmation** before any submission
- Never bypass platform terms of service

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

**Future provider:** A real provider (e.g., OpenAI) would be added as `jobos/llm/openai.py` and selected via `get_llm_adapter({"provider": "openai", "api_key": "..."})`. It would still respect the "no live submission" boundary.

## File Structure

```
job-application-os/
├── jobos/                    # Python package
│   ├── cli.py               # CLI entry point (argparse, 18 commands)
│   ├── models.py            # Dataclasses: Job, Prediction, Retro, ApplicationPack
│   ├── scorer.py            # 6-dimension scoring engine with hard gates
│   ├── predictor.py         # Immutable prediction creation
│   ├── pack_generator.py    # Application pack generation + evidence validation
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
│   ├── llm/                 # LLM adapter (mock by default)
│   │   ├── base.py          # Protocol interface
│   │   ├── mock.py          # Deterministic mock
│   │   └── provider.py      # Factory
│   └── adapters/            # Form templates
├── profile/                  # User profile (YAML + evidence bank)
├── rubrics/                  # Scoring rubric definitions
├── tests/                    # Test suite (249 tests)
├── .github/workflows/test.yml  # CI configuration
├── pyproject.toml           # Package metadata (primary)
├── setup.py                 # Package installation (legacy compat)
└── README.md                # User documentation
```
