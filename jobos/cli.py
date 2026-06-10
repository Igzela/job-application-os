"""CLI entry point for the Job Application OS."""

import argparse
import json
import sys
from pathlib import Path


def _get_root() -> Path:
    """Return project root (cwd)."""
    return Path.cwd()


def main():
    parser = argparse.ArgumentParser(
        prog="job",
        description="Job Application OS - local-first job application copilot",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # job init
    subparsers.add_parser("init", help="Create directory structure and starter files")

    # job import
    p_import = subparsers.add_parser("import", help="Import raw job description")
    p_import.add_argument("--file", required=True, help="Path to job description file")

    # job score
    p_score = subparsers.add_parser("score", help="Score job against profile")
    p_score.add_argument("--job", required=True, help="Job ID")

    # job predict
    p_predict = subparsers.add_parser("predict", help="Create or update prediction")
    p_predict.add_argument("--job", required=True, help="Job ID")
    p_predict.add_argument(
        "--new-version", action="store_true", help="Create new prediction version"
    )

    # job pack
    p_pack = subparsers.add_parser("pack", help="Generate application pack")
    p_pack.add_argument("--job", required=True, help="Job ID")

    # job dry-run
    p_dry = subparsers.add_parser("dry-run", help="Run against local mock form")
    p_dry.add_argument("--job", required=True, help="Job ID")

    # job mark-submitted
    p_submit = subparsers.add_parser("mark-submitted", help="Record submission")
    p_submit.add_argument("--job", required=True, help="Job ID")
    p_submit.add_argument("--channel", required=True, help="Submission channel")

    # job retro
    p_retro = subparsers.add_parser("retro", help="Record retrospective")
    p_retro.add_argument("--job", required=True, help="Job ID")
    p_retro.add_argument("--status-3d", help="Status at 3 days")
    p_retro.add_argument("--status-14d", help="Status at 14 days")
    p_retro.add_argument("--status-30d", help="Status at 30 days")

    # job status
    subparsers.add_parser("status", help="Update STATUS.md")

    # job bump-rubric
    p_rubric = subparsers.add_parser("bump-rubric", help="Create rubric candidate")
    p_rubric.add_argument("--new-rubric", required=True, help="Path to new rubric file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    _dispatch(args)


def _dispatch(args):
    handlers = {
        "init": _cmd_init,
        "import": _cmd_import,
        "score": _cmd_score,
        "predict": _cmd_predict,
        "pack": _cmd_pack,
        "dry-run": _cmd_dry_run,
        "mark-submitted": _cmd_mark_submitted,
        "retro": _cmd_retro,
        "status": _cmd_status,
        "bump-rubric": _cmd_bump_rubric,
    }
    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _cmd_init(args):
    import shutil
    from .status import update_status

    root = _get_root()
    print("Initializing Job Application OS...")

    directories = [
        "profile",
        "jobs/raw",
        "jobs/normalized",
        "jobs/skipped",
        "jobs/saved",
        "predictions",
        "applications",
        "retros",
        "rubrics",
        "adapters/manual_paste",
        "adapters/local_mock_form",
        "adapters/boss_assist",
        "tools",
        "tests/fixtures",
    ]
    for d in directories:
        (root / d).mkdir(parents=True, exist_ok=True)

    templates = {
        "PROFILE.md": "# User Profile\n\nFill in your profile in `profile/` directory.\n",
        "RUBRIC.md": "# Job Scoring Rubric\n\nActive rubric: see `rubrics/` directory.\n",
        "WORKFLOW.md": "# Workflow\n\n1. Import JD\n2. Score\n3. Predict\n4. Pack\n5. Submit (manual)\n6. Retro\n7. Bump rubric\n",
        "STATUS.md": "# Status\n\nRun `job status` to update.\n",
    }
    for name, content in templates.items():
        path = root / name
        if not path.exists():
            path.write_text(content)

    state_path = root / ".job-state.json"
    if not state_path.exists():
        state = {"jobs": {}, "active_rubric": "v0_student_internship", "rubric_history": []}
        state_path.write_text(json.dumps(state, indent=2) + "\n")

    print(f"Created directory structure at {root}")
    print("Done. Edit profile/ files and rubrics/ to get started.")


def _cmd_import(args):
    from .importer import import_job

    root = _get_root()
    jobs_dir = root / "jobs" / "normalized"
    data = import_job(args.file, str(jobs_dir))

    # Also update state
    state_path = root / ".job-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"jobs": {}}
    state["jobs"][data["job_id"]] = {
        "title": data["title"],
        "company": data["company"],
        "location": data.get("location", ""),
        "status": "imported",
        "captured_at": data.get("imported_at", ""),
        "source_file": data.get("source_file", ""),
    }
    state_path.write_text(json.dumps(state, indent=2) + "\n")

    print(f"Imported: {data['job_id']}")
    print(f"  Title: {data['title']}")
    print(f"  Company: {data['company']}")
    print(f"  Saved to: jobs/normalized/{data['job_id']}.yaml")


def _cmd_score(args):
    from .scorer import score_job
    from .profile_loader import load_profile, load_evidence_bank

    root = _get_root()
    job_id = args.job

    # Load job data
    job_path = root / "jobs" / "normalized" / f"{job_id}.yaml"
    if not job_path.exists():
        # Try JSON
        job_path = root / "jobs" / "normalized" / f"{job_id}.json"
    if not job_path.exists():
        print(f"Error: Job {job_id} not found in jobs/normalized/", file=sys.stderr)
        sys.exit(1)

    import yaml
    if job_path.suffix == ".yaml":
        job_data = yaml.safe_load(job_path.read_text())
    else:
        job_data = json.loads(job_path.read_text())

    profile = load_profile(str(root))
    evidence = load_evidence_bank(str(root))

    # Load rubric
    rubric_path = root / "rubrics" / "v0_student_internship.md"
    rubric = {"target_roles": profile.get("target_roles", [])}
    if rubric_path.exists():
        from .rubric_manager import load_rubric
        rubric = load_rubric(str(rubric_path))

    scores = score_job(job_data, profile, evidence, rubric)

    print(f"Scores for {job_id}:")
    for dim in ["fit", "evidence", "opportunity", "strategic", "friction", "risk"]:
        print(f"  {dim}: {scores[dim]:.1f}")
    print(f"  final_score: {scores['final_score']:.2f}")
    if scores.get("skipped"):
        print(f"  SKIPPED: {scores['skip_reason']}")

    # Update state
    state_path = root / ".job-state.json"
    state = json.loads(state_path.read_text())
    if job_id in state["jobs"]:
        state["jobs"][job_id]["status"] = "scored"
        state["jobs"][job_id]["scores"] = {k: v for k, v in scores.items() if k not in ("skipped", "skip_reason")}
        state_path.write_text(json.dumps(state, indent=2) + "\n")


def _cmd_predict(args):
    from .predictor import create_prediction, save_prediction, load_prediction

    root = _get_root()
    job_id = args.job

    # Load job data from state
    state_path = root / ".job-state.json"
    state = json.loads(state_path.read_text())
    if job_id not in state["jobs"]:
        print(f"Error: Job {job_id} not found. Import and score first.", file=sys.stderr)
        sys.exit(1)

    job_entry = state["jobs"][job_id]
    scores = job_entry.get("scores", {})
    if not scores or "final_score" not in scores:
        print(f"Error: Job {job_id} not scored yet. Run `job score --job {job_id}` first.", file=sys.stderr)
        sys.exit(1)

    from .profile_loader import load_profile
    profile = load_profile(str(root))

    job_data = {"job_id": job_id, **job_entry}
    prediction = create_prediction(job_data, scores, profile)

    try:
        path = save_prediction(prediction, root / "predictions")
        print(f"Prediction saved: {path}")
        print(f"  Decision: {prediction.decision}")
        print(f"  Final score: {prediction.final_score:.2f}")
        print(f"  Confidence: {prediction.confidence:.0%}")
    except FileExistsError as e:
        if args.new_version:
            # Find next version
            import glob
            existing = glob.glob(str(root / "predictions" / f"{job_id}_v*.json"))
            next_v = len(existing) + 1
            # Create with incremented version
            prediction_v2 = create_prediction(
                {**job_data, "version": next_v}, scores, profile
            )
            path = save_prediction(prediction_v2, root / "predictions")
            print(f"New prediction version saved: {path}")
        else:
            print(f"Error: {e}", file=sys.stderr)
            print("Use --new-version to create a revised prediction.", file=sys.stderr)
            sys.exit(1)

    # Update state
    state["jobs"][job_id]["status"] = "predicted"
    state_path.write_text(json.dumps(state, indent=2) + "\n")


def _cmd_pack(args):
    from .pack_generator import generate_pack, validate_pack
    from .profile_loader import load_profile, load_evidence_bank

    root = _get_root()
    job_id = args.job

    # Load job data
    state_path = root / ".job-state.json"
    state = json.loads(state_path.read_text())
    if job_id not in state["jobs"]:
        print(f"Error: Job {job_id} not found.", file=sys.stderr)
        sys.exit(1)

    job_entry = state["jobs"][job_id]

    # Load normalized job data
    import yaml
    job_yaml = root / "jobs" / "normalized" / f"{job_id}.yaml"
    if job_yaml.exists():
        job_data = yaml.safe_load(job_yaml.read_text())
    else:
        job_data = {"job_id": job_id, **job_entry}

    # Load prediction
    from .predictor import load_prediction
    try:
        prediction = load_prediction(job_id, root / "predictions")
        pred_dict = prediction.to_dict()
    except FileNotFoundError:
        print(f"Error: No prediction for {job_id}. Run `job predict` first.", file=sys.stderr)
        sys.exit(1)

    profile = load_profile(str(root))
    evidence = load_evidence_bank(str(root))

    pack, warnings = generate_pack(job_data, pred_dict, profile, evidence)

    # Save pack files
    pack_dir = root / "applications" / job_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in pack.files.items():
        (pack_dir / filename).write_text(content)

    print(f"Application pack saved to: applications/{job_id}/")
    for f in pack.files:
        print(f"  - {f}")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")

    # Update state
    state["jobs"][job_id]["status"] = "packed"
    state_path.write_text(json.dumps(state, indent=2) + "\n")


def _cmd_dry_run(args):
    from .dry_run import run_dry_run
    from .models import ApplicationPack

    root = _get_root()
    job_id = args.job

    # Load pack files
    pack_dir = root / "applications" / job_id
    if not pack_dir.exists():
        print(f"Error: No application pack for {job_id}. Run `job pack` first.", file=sys.stderr)
        sys.exit(1)

    files = {}
    for f in pack_dir.iterdir():
        if f.is_file():
            files[f.name] = f.read_text()

    pack = ApplicationPack(job_id=job_id, files=files)

    # Find mock form
    mock_form = root / "adapters" / "local_mock_form" / "application_form.html"
    if not mock_form.exists():
        mock_form = root / "tests" / "fixtures" / "mock_form.html"

    result = run_dry_run(job_id, pack, str(mock_form))

    print(f"Dry-run for {job_id}:")
    print(f"  Fields filled: {len(result['fields_filled'])}")
    for field, value in result["fields_filled"].items():
        preview = str(value)[:60] + ("..." if len(str(value)) > 60 else "")
        print(f"    {field}: {preview}")
    print(f"  Mode: DRY RUN — nothing submitted")


def _cmd_mark_submitted(args):
    from .retro import record_submission

    root = _get_root()
    job_id = args.job
    channel = args.channel

    try:
        record_submission(job_id, channel, str(root))
        print(f"Marked {job_id} as submitted via {channel}")
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_retro(args):
    from .retro import record_retro

    root = _get_root()
    job_id = args.job

    try:
        path = record_retro(
            job_id,
            str(root),
            status_3d=args.status_3d,
            status_14d=args.status_14d,
            status_30d=args.status_30d,
        )
        print(f"Retro recorded: {path}")
        if args.status_3d:
            print(f"  3d: {args.status_3d}")
        if args.status_14d:
            print(f"  14d: {args.status_14d}")
        if args.status_30d:
            print(f"  30d: {args.status_30d}")
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_status(args):
    from .status import update_status

    root = _get_root()
    md = update_status(str(root))
    print("STATUS.md updated.")
    # Print summary
    for line in md.split("\n"):
        if line.startswith("## Pipeline"):
            break
    # Just show pipeline counts
    import re
    for line in md.split("\n"):
        if "|" in line and any(s in line.lower() for s in ["imported", "scored", "predicted", "packed", "submitted", "retro", "total"]):
            print(line)


def _cmd_bump_rubric(args):
    from .rubric_manager import bump_rubric

    root = _get_root()
    new_rubric = args.new_rubric

    if not Path(new_rubric).exists():
        print(f"Error: Rubric file not found: {new_rubric}", file=sys.stderr)
        sys.exit(1)

    report = bump_rubric(
        new_rubric_path=new_rubric,
        jobs_dir=str(root / "jobs"),
        predictions_dir=str(root / "predictions"),
        retros_dir=str(root / "retros"),
        state_path=str(root / ".job-state.json"),
    )

    print(f"Rubric bump report:")
    print(f"  Candidate: {report['candidate']['name']}")
    print(f"  Active: {report['active_rubric']}")
    print(f"  Jobs compared: {report['jobs_scored']}")
    print()
    print(report["summary"])


if __name__ == "__main__":
    main()
