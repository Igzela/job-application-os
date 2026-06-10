# Evidence Bank

Each entry links a skill or project to a concrete, verifiable outcome. Used by `job score` and `job pack` to match resume bullets to job requirements.

---

## Project 1: DeepSeek Boss Helper

**Type:** Chrome Extension (full-stack)
**Repo:** `references/deepseek-boss-helper`
**Tech:** Vue 3, Element Plus, Vite, OpenAI API, Chrome Extension API
**Role:** Sole developer

### What it does

Chrome extension for the Chinese job platform Boss Zhipin. Scrapes job descriptions in real time, runs them against a locally stored resume via DeepSeek LLM, and generates a match score with personalized greeting messages.

### Concrete outcomes

- Built a working Chrome extension from scratch covering content scripts, background service worker, popup UI, and options page.
- Integrated multi-model DeepSeek API support (10+ model variants including DeepSeek-R1, Llama distills, Qwen distills) with runtime model switching.
- Implemented local-first resume storage using `chrome.storage.local` -- no data leaves the browser.
- Shipped with a complete build pipeline (Vite bundling, `npm run build` producing a loadable `dist/` directory).

### Verifiable details

- `package.json` shows production dependencies: vue ^3.3.8, element-plus ^2.4.2, openai ^4.0.0.
- Build tooling: Vite ^5.0.0 with `@vitejs/plugin-vue`.
- Supports PDF resume upload and parsing.

### Skills demonstrated

`JavaScript` `Vue 3` `Chrome Extension APIs` `REST API integration` `async programming` `UI component design`

---

## Project 2: Cheat on Content

**Type:** Agent skill / content operations framework
**Repo:** `references/cheat-on-content`
**Tech:** Markdown-based skill system, multi-agent architecture, cross-model audit pipeline
**Role:** Author / maintainer

### What it does

A skill for AI coding agents (Claude Code, Codex) that turns content creation into a calibrated experiment. Every piece gets scored, blind-predicted, published, and retrospected at T+3 days. The scoring rubric auto-evolves based on accumulated data.

### Concrete outcomes

- Designed a 14-sub-skill architecture symlinked into agent skill directories, installable via a single `bash install.sh`.
- Built a blind prediction system that separates the scoring sub-agent from the actuals sub-agent to prevent data leakage (v1.3 to v1.4 migration broke this into `rubric_notes.md` split files).
- Implemented a cross-model audit gate: rubric upgrades require re-scoring all historical samples and passing an independent model audit before release.
- Reached #1 on Watcha (Chinese content analytics platform) hot list.
- Claimed trajectory: zero to 1M followers in one month for the originating creator channel.

### Verifiable details

- MIT licensed, version tracked via CHANGELOG.md with semantic versioning (v0.1.0 to v1.4+).
- Migration scripts exist for each version bump: `1.0-to-1.1`, `1.1-to-1.2`, `1.2-to-1.3`, `1.3-to-1.4`.
- Hook system with JSON configs: `session-start.json`, `meta-logging.json`, `prediction-immutability.json`.
- Supports both Claude Code and OpenAI Codex as target agents.

### Skills demonstrated

`Python` `system design` `data pipeline design` `multi-agent architecture` `calibration / prediction` `documentation`

---

## Project 3: Job Application Calibration OS

**Type:** CLI tool / local-first automation
**Repo:** root of this repository
**Tech:** Python, pytest
**Role:** Sole developer

### What it does

A local-first copilot for job applications. Imports job descriptions, scores a resume against them using a calibrated rubric, predicts application outcomes, and packs tailored resume variants -- all without ever submitting anything live.

### Concrete outcomes

- Designed a full CLI workflow: `job init` / `import` / `score` / `predict` / `pack` / `dry-run` / `mark-submitted` / `retro`.
- Built a scoring rubric system with versioned bumping (`job bump-rubric`) so resume-job matching improves over time.
- Implemented a local mock submission system (`job dry-run`) that validates resume packages against form schemas without network calls.
- Created a retrospective loop (`job retro`) that feeds past application outcomes back into prediction accuracy.

### Verifiable details

- Safety-first design: explicitly no live submission, no anti-detection, local mock forms only, evidence-based resume only.
- Installed via `pip install -e .` with pytest as the test runner.
- Profile data stored as structured YAML: `base.yaml`, `skills.yaml`, `availability.yaml`.

### Skills demonstrated

`Python` `CLI design` `YAML / data modeling` `test-driven development` `system architecture` `privacy-first design`

---

## Project 4: Data Analysis Coursework Projects

**Type:** Academic coursework
**Institution:** UC Berkeley, Computer Science
**Tech:** Python, pandas, NumPy, matplotlib, SQL, scikit-learn, TensorFlow

### Concrete outcomes

- Completed upper-division coursework in data structures, algorithms, and machine learning.
- Built supervised learning models (classification and regression) using scikit-learn with proper train/test splitting and cross-validation.
- Performed exploratory data analysis on datasets with 100K+ records using pandas and matplotlib, producing publication-quality visualizations.
- Wrote SQL queries for multi-table joins, aggregations, and window functions against relational databases.

### Verifiable details

- GPA and course list available on transcript (UC Berkeley, B.S. Computer Science, expected May 2027).
- Tools listed in `skills.yaml`: pandas, NumPy, matplotlib, SQL, scikit-learn, TensorFlow, PyTorch.

### Skills demonstrated

`Python` `pandas` `NumPy` `matplotlib` `SQL` `scikit-learn` `TensorFlow` `data wrangling` `statistical analysis`

---

## Cross-cutting evidence

| Skill | Projects where demonstrated |
|-------|---------------------------|
| Python | Job Application OS, Cheat on Content, Data Analysis coursework |
| JavaScript / Vue | DeepSeek Boss Helper |
| React | (coursework, personal projects -- add specific entry when available) |
| API integration | DeepSeek Boss Helper (OpenAI/DeepSeek API) |
| System design | Cheat on Content (14-sub-skill architecture), Job Application OS (CLI workflow) |
| Data analysis | Coursework projects, Cheat on Content (prediction calibration) |
| Privacy-first design | DeepSeek Boss Helper (local storage), Job Application OS (no live submission) |
| Documentation | All three projects have full READMEs with install/usage instructions |

---

## How to use this file

1. **When tailoring a resume:** Run `job score` against a job description. The tool references these entries to match bullets to requirements.
2. **When writing cover letters:** Pull specific outcomes and metrics from the entries above.
3. **When updating:** Add new entries as projects ship. Each entry must include: what it does, concrete outcomes (numbers preferred), verifiable details (file paths, versions, configs), and skills demonstrated.
