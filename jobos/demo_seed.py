"""Demo workspace seeding for Job Application OS."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .workspace import (
    initialize_workspace,
    jobs_raw_dir,
    load_state,
    save_state,
    state_path,
)


DEMO_RUBRIC = "v0_student_internship"


@dataclass(frozen=True)
class DemoSeedResult:
    profile_dir: Path
    rubric_path: Path
    sample_jd_path: Path


def seed_demo_workspace(state_dir: str | Path) -> DemoSeedResult:
    """Create a small idempotent demo workspace with local fixtures."""
    root = Path(state_dir)
    initialize_workspace(root)

    profile_dir = root / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "base.yaml").write_text(
        "name: Alex Chen\n"
        "school: University of California, Berkeley\n"
        "major: Computer Science\n"
        "degree: Bachelor of Science\n"
        'graduation_date: "2027-05-15"\n'
        "location: Berkeley, CA\n"
        "target_locations:\n"
        "  - San Francisco, CA\n"
        "  - Seattle, WA\n"
        "  - New York, NY\n"
        'availability_start: "2026-06-01"\n'
        'availability_end: "2026-08-15"\n'
        "days_per_week: 5\n"
        "languages:\n"
        "  - English\n"
        "  - Mandarin\n",
        encoding="utf-8",
    )
    (profile_dir / "skills.yaml").write_text(
        "skills:\n"
        "  programming_languages:\n"
        "    - name: Python\n"
        "      proficiency: advanced\n"
        "    - name: JavaScript\n"
        "      proficiency: advanced\n"
        "  frameworks:\n"
        "    - name: React\n"
        "      proficiency: advanced\n"
        "  domains:\n"
        "    - name: Data Analysis\n"
        "      proficiency: intermediate\n"
        "      tools: [pandas, NumPy, SQL]\n",
        encoding="utf-8",
    )
    (profile_dir / "education.yaml").write_text(
        "education:\n"
        "  - institution: UC Berkeley\n"
        "    degree: B.S.\n"
        "    major: Computer Science\n"
        '    graduation_date: "2027-05"\n'
        "    gpa: 3.8\n",
        encoding="utf-8",
    )
    (profile_dir / "availability.yaml").write_text(
        "internship_window:\n"
        '  start: "2026-06-01"\n'
        '  end: "2026-08-15"\n'
        "weekly_capacity:\n"
        "  days_per_week: 5\n"
        "work_arrangement:\n"
        "  open_to_remote: true\n"
        "  open_to_hybrid: true\n"
        "  preferred: hybrid\n"
        "target_locations:\n"
        "  - San Francisco, CA\n"
        "  - Seattle, WA\n",
        encoding="utf-8",
    )
    (profile_dir / "evidence_bank.md").write_text(
        "# Evidence Bank\n\n"
        "## Project 1: Chrome Extension\n\n"
        "**Type:** Full-stack\n"
        "**Tech:** Vue 3, JavaScript, Chrome Extension API\n\n"
        "- Built a Chrome extension from scratch with popup UI and content scripts\n"
        "- Integrated REST API for real-time data exchange\n\n"
        "## Project 2: Data Analysis Dashboard\n\n"
        "**Type:** Data visualization\n"
        "**Tech:** Python, pandas, matplotlib, SQL\n\n"
        "- Analyzed 100K+ record datasets using pandas\n"
        "- Created interactive visualizations with matplotlib\n",
        encoding="utf-8",
    )

    rubrics_dir = root / "rubrics"
    rubrics_dir.mkdir(exist_ok=True)
    rubric_path = rubrics_dir / f"{DEMO_RUBRIC}.md"
    rubric_path.write_text(
        "# Rubric v0: Student Internship\n\n"
        "## Scoring Formula\n\n"
        "final_score = 0.30*fit + 0.25*evidence + 0.20*opportunity + 0.15*strategic - 0.10*friction - 0.20*risk\n\n"
        "## Dimensions\n\n"
        "### 1. Skill Match (weight: 30%)\n"
        "### 2. Evidence (weight: 25%)\n"
        "### 3. Opportunity (weight: 20%)\n"
        "### 4. Strategic (weight: 15%)\n"
        "### 5. Friction (weight: 10%)\n"
        "### 6. Risk (weight: 20%)\n",
        encoding="utf-8",
    )

    raw_dir = jobs_raw_dir(root)
    raw_dir.mkdir(parents=True, exist_ok=True)
    sample_jd_path = raw_dir / "sample_swe_intern.md"
    sample_jd_path.write_text(
        "# Software Engineer Intern - Summer 2026\n\n"
        "Company: Acme Labs\n"
        "Location: San Francisco, CA (Hybrid)\n\n"
        "Requirements:\n"
        "- Python or JavaScript\n"
        "- React or similar frontend framework\n"
        "- SQL basics\n\n"
        "Nice to have:\n"
        "- Machine learning experience\n"
        "- Previous internship\n",
        encoding="utf-8",
    )

    mock_dir = root / "adapters" / "local_mock_form"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "application_form.html").write_text(
        '<!DOCTYPE html><html><body>'
        '<form action="/submit" method="POST">'
        '<input name="full_name" type="text">'
        '<input name="email" type="email">'
        '<input name="phone" type="tel">'
        '<input name="school" type="text">'
        '<input name="major" type="text">'
        '<textarea name="cover_letter"></textarea>'
        '<select name="availability"><option value="summer">Summer</option></select>'
        '<button type="submit">Submit</button>'
        '</form></body></html>',
        encoding="utf-8",
    )

    if state_path(root).exists():
        state = load_state(root)
        state["active_rubric"] = DEMO_RUBRIC
        save_state(root, state)

    return DemoSeedResult(
        profile_dir=profile_dir,
        rubric_path=rubric_path,
        sample_jd_path=sample_jd_path,
    )
