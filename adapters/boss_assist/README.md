# Boss Assist — Assist-Only Mode

A human-in-the-loop adapter for the Job Application OS. It parses a user-provided job description, generates filled drafts using the local profile, and presents them for review. Nothing is submitted anywhere without explicit human confirmation.

## What It Does

1. **Ingest** a job description (pasted text, file path, or URL snapshot).
2. **Parse** structured fields from the raw description — title, company, location, skills, compensation, deadlines.
3. **Draft** application materials — tailored resume sections, cover letter, field-filled form entries — using the candidate profile stored in `PROFILE.md`.
4. **Present** every draft to the human for review, edit, and approval.
5. **Halt.** No data leaves the machine. No form is submitted. The human decides what happens next.

## What It Does Not Do

- No live submission to any ATS, portal, email endpoint, or API.
- No anti-detection, fingerprint spoofing, or bot-avoidance techniques.
- No automated follow-ups, scheduling, or outreach.
- No network requests of any kind during the draft phase.

## How It Works

```
User pastes JD
      │
      ▼
┌─────────────┐
│   Parse JD   │  Extract title, company, location, requirements, nice-to-haves
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Score Fit   │  Compare requirements against PROFILE.md; produce fit score
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Gen Drafts  │  Tailor resume bullets, draft cover letter, fill form fields
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Human Review│  Show all drafts; user edits, approves, or discards
└──────┬──────┘
       │
       ▼
   [STOP — no submission]
```

### Parsing

The JD parser extracts fields using pattern matching on the raw text. It produces a structured job record (YAML) with:

- `title` — role title
- `company` — employer name
- `location` — office / remote / hybrid
- `skills` — list of required and preferred skills
- `compensation` — salary range if stated
- `deadline` — application cutoff date if stated
- `raw_content_hash` — SHA-256 fingerprint for deduplication

This mirrors the `job import` stage from the core workflow (`jobos/importer.py`).

### Draft Generation

Drafts are generated locally from the candidate profile. The adapter produces:

- **Resume highlights** — reordered bullets emphasizing skills that match the JD.
- **Cover letter draft** — structured narrative connecting candidate experience to role requirements.
- **Form field mapping** — a flat dict of `{field_name: value}` ready for manual copy-paste or mock-form filling.

No draft is written to disk or transmitted anywhere unless the user explicitly exports it.

### Human Confirmation

Every artifact goes through a confirmation gate before it can be used:

1. The adapter prints or displays each draft.
2. The user can edit any field, rewrite any section, or reject the draft entirely.
3. Only after the user says "approved" does the draft get saved to the local workspace.

There is no auto-confirm, no batch-approve, no timeout that forces acceptance.

## Relationship to Core Workflow

Boss Assist covers stages 1 through 4 of the application workflow:

| Workflow Stage | Boss Assist Behavior |
|----------------|---------------------|
| Import         | Parses JD, creates local YAML record |
| Score          | Compares JD requirements to profile, produces fit score |
| Predict        | Optional — uses historical data if available |
| Pack           | Generates resume and cover letter drafts |
| **Submit**     | **Never performed.** Stopped here by design. |

Stage 5 (Submit) is explicitly out of scope. The user handles submission manually through whatever channel they choose.

## Usage

```bash
# From a file
job import posting.txt

# Then invoke assist mode to generate drafts
# (adapter reads the imported YAML and PROFILE.md)
```

The adapter expects:
- A parsed job YAML in the workspace `jobs/` directory (produced by `job import`).
- A populated `PROFILE.md` at the project root.

## Safety Guarantees

| Guarantee | Enforcement |
|-----------|-------------|
| No network calls during draft phase | Adapter has no HTTP client imports; all I/O is local filesystem |
| No submission without human action | No code path reaches any submit function; the workflow halts after Pack |
| No anti-detection | No browser automation, fingerprinting, or CAPTCHA solving code exists in this adapter |
| Evidence-based only | Resume drafts pull exclusively from `PROFILE.md` — no fabricated experience, no inflated claims |
| Full audit trail | Every imported JD and generated draft is saved as a local YAML/text file with timestamps |

## File Layout

```
adapters/boss_assist/
  README.md          # This file
```

Generated artifacts land in the standard workspace locations:

```
jobs/<job-id>.yaml   # Parsed JD
jobs/<job-id>/        # Drafts directory (resume, cover letter, form map)
```
