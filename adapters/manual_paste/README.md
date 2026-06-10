# Manual Paste Adapter

Import job descriptions by pasting raw text into a file and running `job import`.

This is the simplest way to get a JD into the system when there is no API, no scraper, and no URL to fetch from. You copy the posting from a browser tab, Slack message, email, or PDF and drop it into a local file.

---

## Quick start

```bash
# 1. Paste the JD into a new file
vim /tmp/acme-senior-eng.md

# 2. Import it
job import --file /tmp/acme-senior-eng.md

# 3. Confirm it landed
ls jobs/normalized/
```

---

## Step 1: Create the file

Paste the full job description into a plain-text or markdown file. Use any filename and any directory that is convenient -- the importer reads the content, not the path.

Recommended: save to `/tmp/` so it does not clutter the workspace and gets cleaned up automatically.

```bash
# Example: quick paste from clipboard (Linux)
xclip -selection clipboard -o > /tmp/acme-senior-eng.md

# Example: quick paste from clipboard (macOS)
pbpaste > /tmp/acme-senior-eng.md
```

---

## Step 2: Format the content

The importer uses regex-based extraction. You do not need perfect formatting, but consistent structure improves field extraction accuracy.

### Required fields

| Field | How the importer finds it | Fallback |
|-------|--------------------------|----------|
| Title | First markdown heading (`# ...`) | `"Unknown Title"` |
| Company | Line containing `Company:` or `Employer:` or `Organization:` (case-insensitive) | `"Unknown Company"` |
| Location | Line containing `Location:` or `Based in:` or `Office:` (case-insensitive)` | `"Unknown"` |
| Skills | Line containing `Skills:`, `Technologies:`, `Requirements:`, or `Qualifications:` followed by a comma or semicolon separated list | Empty list |

### Minimal template

```markdown
# Senior Backend Engineer

Company: Acme Corp
Location: Remote (US)
Skills: Python, PostgreSQL, Kubernetes, AWS, gRPC

## About the role
We are looking for a senior backend engineer to ...

## Requirements
- 5+ years of backend experience
- Strong SQL skills
...
```

### Tips for reliable extraction

- Put the job title on the first line as a level-1 heading (`# Title`).
- Use `Company:`, `Location:`, and `Skills:` (or their synonyms) as simple key-value labels on their own lines.
- Separate skill items with commas or semicolons: `Skills: Python, Go, Docker`.
- Everything else (about the role, requirements, nice-to-haves, salary, benefits) is preserved in `raw_content_hash` for later reference. The importer does not parse these sections yet, so free-form text is fine.

---

## Step 3: Run the import

```bash
job import --file <path-to-your-file>
```

What happens:

1. The file is read as UTF-8.
2. Title, company, location, and skills are extracted using regex patterns.
3. A job ID is generated from the current UTC timestamp and a slug of the title (e.g. `20260610120000-senior-backend-engineer`).
4. A normalized YAML file is written to `jobs/normalized/<job_id>.yaml`.
5. The job ID is printed to stdout.

---

## Step 4: Verify

```bash
# List all imported jobs
ls jobs/normalized/

# Inspect a specific job
cat jobs/normalized/<job_id>.yaml
```

The YAML file contains:

```yaml
job_id: 20260610120000-senior-backend-engineer
title: Senior Backend Engineer
company: Acme Corp
location: Remote (US)
skills:
  - Python
  - PostgreSQL
  - Kubernetes
  - AWS
  - gRPC
source_file: acme-senior-eng.md
imported_at: '2026-06-10T12:00:00+00:00'
raw_content_hash: a1b2c3d4e5f67890
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Title shows as `Unknown Title` | No `# heading` in the file | Add a markdown heading on the first line |
| Company shows as `Unknown Company` | No `Company:` label found | Add `Company: Name` on its own line |
| Skills list is empty | No `Skills:` / `Requirements:` / `Technologies:` label found | Add `Skills: A, B, C` on its own line |
| Duplicate job IDs | Two imports in the same second with identical title slugs | Wait one second between imports, or rename the file (the ID is timestamp-based) |

---

## What this adapter does NOT do

- **No URL fetching.** If you have a URL, paste the content manually or use a future `web_fetch` adapter.
- **No structured field parsing beyond regex.** Salary, deadline, work type, and preferred/required skill distinction are not extracted. Edit the YAML manually if needed, or wait for a richer parser.
- **No deduplication.** Importing the same JD twice creates two entries. Check `raw_content_hash` if you suspect duplicates.

---

## Next steps after import

```bash
# Score the job against your profile
job score --job <job_id>

# Predict outcome
job predict --job <job_id>

# Generate application materials
job pack --job <job_id>
```
