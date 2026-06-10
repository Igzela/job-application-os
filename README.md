# Job Application Calibration OS

Local-first copilot for job applications.

## Safety

- No live submission
- No anti-detection
- Local mock forms only
- Evidence-based resume only

## Setup

```bash
pip install -e .
pytest
```

## Commands

| Command | Description |
|---------|-------------|
| `job init` | Initialize workspace |
| `job import <file>` | Import job description |
| `job score` | Score resume against job |
| `job predict` | Predict application outcome |
| `job pack` | Pack resume for submission |
| `job dry-run` | Test submission locally |
| `job mark-submitted` | Mark application as submitted |
| `job retro` | Review past applications |
| `job status` | Show current status |
| `job bump-rubric` | Update scoring rubric |

## Examples

```bash
# Initialize workspace
job init

# Import a job description
job import job_posting.txt

# Score your resume
job score

# Run local mock submission
job dry-run
```
