# Job Application Calibration OS

> **Dry-run / assist-only.** This system never submits applications to live platforms.
> It imports job descriptions, scores fit, predicts outcomes, and generates application
> packs — all locally. Submission is always manual.

A local-first copilot that turns job applications into calibrated experiments.

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

## Commands

| Command | Description |
|---------|-------------|
| `job init` | Create directory structure and starter files |
| `job demo-seed` | Create sample workspace with profile, rubric, and JD |
| `job doctor` | Check workspace health |
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
| `job recommend --top N` | Rank scored jobs by composite quality |
| `job status` | Update STATUS.md with pipeline counts |
| `job report` | Generate analytics report |
| `job bump-rubric --new-rubric <path>` | Create rubric candidate + comparison |

## Running Tests

```bash
# Run all tests (249 tests, no API keys needed)
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_e2e.py -v

# Run with short traceback
python -m pytest tests/ --tb=short
```

## Safety Boundaries

This system is explicitly **not** an auto-apply bot:

- **No live submission.** `dry_run.py` fills local HTML forms only. No HTTP client is imported.
- **No anti-detection.** No proxy rotation, CAPTCHA bypass, or scraping evasion.
- **Evidence-only resume.** `validate-pack` flags any resume claim not traceable to the evidence bank.
- **Immutable predictions.** Predictions cannot be overwritten — only versioned.
- **Human confirmation required.** The `submit_checklist.md` requires manual review before any real submission.
- **LLM is optional.** The LLM adapter defaults to a deterministic mock. No API keys required. No network calls in tests.

## CI

Tests run automatically on push/PR via GitHub Actions (`.github/workflows/test.yml`).

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for data flow, command flow, safety boundaries, and the LLM adapter interface.

## License

MIT
