# Job Application Calibration OS

> **Default safe mode.** Dry-run and loop commands do not submit applications.
> Live BOSS submission exists only through explicit live commands against a logged-in
> browser session, with duplicate checks, greeting validation, and submit diagnostics.

A local-first job application OS: discover opportunities, verify legitimacy, prepare applications, track submissions, and learn from outcomes.

## Quickstart

```bash
# Install
pip install -e .

# Create demo workspace with sample profile, rubric, and JD
job demo-seed

# Import the sample job description
job import --file jobs/raw/sample_swe_intern.md

# Score against your profile
job score --job <job-id>

# Create immutable prediction
job predict --job <job-id>

# Generate application pack
job pack --job <job-id>

# Validate evidence grounding
job validate-pack --job <job-id>

# Test against local mock form (no submission)
job dry-run --job <job-id>

# Run non-browser pipeline stages for pending jobs
job loop-run --dry-run --max-jobs 10
```

## Full Demo (copy-paste)

```bash
pip install -e . && \
job init && \
job demo-seed && \
job import --file jobs/raw/sample_swe_intern.md && \
job doctor && \
job queue
```

Then score, predict, pack, validate, and dry-run using the job ID printed by import.

## Daily Workflow

```bash
# Check workspace health
job doctor

# See what needs attention
job queue

# Get recommendations for next application
job recommend --top 3

# Paste a JD from clipboard
cat jd.txt | job paste

# After packing, validate evidence
job validate-pack --job <id>

# Generate weekly report
job report
```

## Automation Loop Plan

Use `job loop-plan` to write a read-only plan, or `job loop-run --dry-run` to execute non-browser stages (`score`, `predict`, `pack`, `validate`) for pending jobs. Dry and live runs write `plan.json`, `events.jsonl`, and `summary.json` under `pipeline_runs/<run_id>/`.

Interrupted dry-runs can be resumed:

```bash
job loop-run --resume pipeline_runs/<run_id> --dry-run
```

Inspect recent dry and live runs:

```bash
job runs
job runs --mode live --limit 5
```

Corrupt run directories, including directories missing `plan.json`, malformed
event records, or malformed summary counts, are reported individually and do not
hide healthy runs. Plan-only run directories are shown as `planned`; runs with
events but no summary are shown as `running`.

See [docs/automation-loop-handoff.md](docs/automation-loop-handoff.md) for implementation notes and run artifact conventions.

### Scrapling Extraction Diagnostics

BOSS imports use a Python extraction layer with Scrapling when available and a BeautifulSoup fallback when it is disabled or unavailable. Configure it in `~/.jobos/config.yaml`:

```yaml
extraction:
  use_scrapling: true
  adaptive: true
  adaptive_store: ~/.jobos/scrapling.db
  adaptive_percentage: 40
  record_diagnostics: true
  include_html_snapshot: true
  html_snapshot_limit: 250000
```

`job boss-import --keyword <kw>` records `extractor`, `page_state`, and `extraction_diagnostics` on imported jobs. Loop events copy those fields into `events.jsonl`; `summary.json` aggregates `by_extractor` and `by_page_state`. Submit attempts also classify the current page and persist recovery hints under `applications/<job_id>/submit_attempts/`.

Stable page states are `normal`, `login_required`, `verification_required`, `access_limited`, `empty`, and `page_shape_changed`. When Scrapling cannot extract cards, the fallback parser still runs and records `fallback_used`.

Install the complete Scrapling integration in an isolated environment:

```bash
pip install -e ".[scrapling]"
scrapling install
```

Fetch a replayable page artifact with the HTTP or standard browser engine:

```bash
job scrapling-fetch --url https://example.com --engine http
job scrapling-fetch --url https://example.com --engine dynamic
```

Run a same-domain crawl with robots.txt enforcement, concurrency limits,
download delay, JSONL output, and a resumable checkpoint directory:

```bash
job scrapling-crawl --url https://example.com --max-pages 50 --concurrency 3 --delay 1
```

Outputs are written under ignored `scrapling_runs/`. Login, verification, and
access-limited BOSS pages remain hard stops.

### Live BOSS Pipeline Hardening

`job start --max-jobs N` treats `N` as maximum successful submissions, not maximum analyzed candidates. The live pipeline rotates search keywords and continues analyzing candidates until successful submissions reach `--max-jobs`, the daily limit is reached, or the candidate budget is exhausted.

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

For each BOSS candidate, the pipeline opens the detail page before scam checks, match scoring, and greeting generation. Detail extraction merges full JD text, requirements, location, salary, company, recruiter/contact hints, job status, communication state, `detail_extractor`, `page_state`, and diagnostics into the candidate record. If detail extraction fails, the candidate is skipped with structured diagnostics and the run continues.

Generated greetings pass a pre-send safety validator. The validator blocks wrong identity/name, HR/recruiter/headhunter/招聘顾问 claims, unsupported project or experience claims, unrelated company mentions, excessive length, and spammy wording. One constrained LLM rewrite is attempted; if it still fails, the job is skipped with `greeting_invalid`.

Duplicate/contacted state is persisted in `.job-contact-state.json` by job ID, URL, company/title, status, and timestamp. Jobs already seen by URL/job ID or company/title are skipped before applying. Detail pages showing BOSS states such as `继续沟通` or `已发送` are recorded as already contacted and are not messaged again.

Submit results include `submit_phase`, `success_signals`, `page_state`, `extractor`, `recovery_signals`, `page_diagnostics`, and screenshot paths. Success requires a strong signal such as visible `已发送`, greeting text appearing in the chat, expected company chat context, or an already-contacted BOSS state. The submit helper checks for pre-existing success before clicking send to avoid double-send during retries.

Generated Application Packs include `manifest.json` with file hashes, source
hashes for job, profile, evidence, prediction inputs, and evidence-validation
summary, including failed validation counts. Pack sources are job-specific
files plus profile/prediction inputs; unrelated workspace-state edits do not
invalidate Pack integrity. Pack files must be flat filenames, and Pack
generation fails if an explicit source file is missing. Workspace live
submission rejects a missing, source-less, modified, source-stale, or
unvalidated Pack before connecting to the browser. Live submission also
requires the Pack manifest validation summary to match workspace state and to
contain zero unsupported claims. `job doctor` reports blocking workspace,
Pack, and runtime-state integrity errors separately from non-blocking legacy
Pack and Run Ledger warnings.

`job validate-pack` also writes the full claim-level report to
`applications/<job_id>/validation_report.json`, including supported, weak, and
unsupported claims, missing JD skills, and overclaim risk.

## Commands

| Command | Description |
|---------|-------------|
| `job init` | Create directory structure and starter files |
| `job demo-seed` | Create sample workspace with profile, rubric, and JD |
| `job doctor` | Check workspace and artifact integrity |
| `job browser-check [--standalone-browser] [--headless]` | Check BOSS browser connectivity, login/page state, and save diagnostics |
| `job import --file <path>` | Import raw JD text or markdown |
| `job paste` | Import JD from stdin |
| `job score --job <id>` | Score job against profile (6 dimensions) |
| `job predict --job <id>` | Create immutable prediction |
| `job pack --job <id>` | Generate application pack (7 files) |
| `job validate-pack --job <id>` | Validate pack evidence claims |
| `job dry-run --job <id>` | Fill local mock form (no submission) |
| `job mark-submitted --job <id> --channel <ch>` | Record manual submission |
| `job retro --job <id>` | Record 3d/14d/30d outcome status |
| `job queue` | Show jobs grouped by pipeline stage |
| `job loop-plan --max-jobs N` | Create a read-only loop plan |
| `job loop-run --dry-run --max-jobs N` | Run score, predict, pack, validate with structured events |
| `job loop-run --resume <run_dir> --dry-run` | Resume a prior dry-run, skipping completed stages |
| `job runs [--mode live|dry_run] [--limit N]` | List recent Run Ledgers and result counts |
| `job recommend --top N` | Rank scored jobs by composite quality |
| `job status` | Update STATUS.md with pipeline counts |
| `job report` | Generate analytics report |
| `job bump-rubric --new-rubric <path>` | Create rubric candidate + comparison |
| `job scam-check --name <name> --description <desc>` | Check an opportunity for scam signals |
| `job find [--direction <dir>]` | Find income opportunities from profile |
| `job plan --opportunity <name>` | Generate execution plan for an opportunity |
| `job boss-import --keyword <kw>` | Import jobs from BOSS Zhipin via CDP |
| `job submit --job <id> --platform <plat>` | Semi-automatic application submission |
| `job submit --job <id> --standalone-browser --headless` | Browser dry-run in an isolated Chromium profile |
| `job start --keyword <kw> --max-jobs N --port 9222` | Live BOSS pipeline; `--max-jobs` means successful submissions |
| `job retro-freeform --job <id> --text <text> --lesson <l>` | Record freeform retro with extracted lessons |

## Running Tests

```bash
# Run all tests (no API keys needed)
python3 -m pytest tests/ --tb=short

# Run focused Scrapling/diagnostics tests
python3 -m pytest tests/test_boss_parser.py tests/test_boss_import.py tests/test_loop_run.py tests/test_submit_batch.py --tb=short
```

Operational scripts:

```bash
bash scripts/audit_env.sh
bash scripts/check_architecture.sh
bash scripts/local_ci.sh
MAX_JOBS=5 bash scripts/pipeline_dry_run.sh
```

## Safety Boundaries

This system defaults to dry-run/manual workflows, with explicit live BOSS mode:

- **Dry-run remains non-submitting.** `dry_run.py` fills local HTML forms only. `job loop-run --dry-run` skips browser submission stages.
- **Loop dry-run skips browser stages.** `job loop-run --dry-run` runs only `score`, `predict`, `pack`, and `validate`.
- **No anti-detection.** No proxy rotation, CAPTCHA bypass, or scraping evasion.
- **No fingerprint masking.** Standard Playwright does not spoof user agents, viewport, geolocation, or automation flags.
- **Evidence-only resume.** `validate-pack` flags any resume claim not traceable to the evidence bank.
- **Immutable predictions.** Predictions cannot be overwritten — only versioned.
- **Live BOSS mode is explicit.** `job start` uses a logged-in browser session and writes a unique Run Ledger under `pipeline_runs/`; run it only after reviewing config and daily limits.
- **Greeting preflight required.** Unsafe greetings are rewritten once or skipped.
- **Duplicate guard required.** `.job-contact-state.json` prevents repeat messages by job ID, URL, and company/title.
- **Submit attempts are diagnosed.** Browser submit helpers persist screenshots, DOM classification, recovery hints, and success signals.
- **Browser dry-run must prove page readiness.** Submit dry-runs fail when BOSS shows login, verification, access-limit, or blank-page states; CLI exits non-zero so scripts do not treat browser blockers as success.
- **LLM is optional.** The LLM adapter defaults to a deterministic mock. No API keys required. No network calls in tests.
- **Scam detection.** `scam-check` evaluates opportunities against red flag patterns before they enter the pipeline.

## CI

Tests run automatically on push/PR via GitHub Actions (`.github/workflows/test.yml`).

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for data flow, command flow, safety boundaries, and the LLM adapter interface.

## License

MIT
