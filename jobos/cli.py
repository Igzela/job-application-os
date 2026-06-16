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

    # job retro-freeform
    p_retro_freeform = subparsers.add_parser("retro-freeform", help="Record freeform retrospective with lessons")
    p_retro_freeform.add_argument("--job", required=True, help="Job ID")
    p_retro_freeform.add_argument("--text", required=True, help="Freeform retrospective text")
    p_retro_freeform.add_argument("--lesson", action="append", required=True, help="Lesson extracted (repeatable)")

    # job status
    subparsers.add_parser("status", help="Update STATUS.md")

    # job bump-rubric
    p_rubric = subparsers.add_parser("bump-rubric", help="Create rubric candidate")
    p_rubric.add_argument("--new-rubric", required=True, help="Path to new rubric file")

    # job doctor
    subparsers.add_parser("doctor", help="Check workspace health")

    # job demo-seed
    subparsers.add_parser("demo-seed", help="Create sample workspace with fixtures")

    # job queue
    subparsers.add_parser("queue", help="Show jobs grouped by pipeline stage")

    # job loop-plan
    p_loop_plan = subparsers.add_parser("loop-plan", help="Create a read-only automation loop plan")
    p_loop_plan.add_argument("--max-jobs", type=int, default=10, help="Maximum planned actions")
    p_loop_plan.add_argument("--output", help="Output path (default: pipeline_runs/<run_id>/plan.json)")

    # job loop-run
    p_loop_run = subparsers.add_parser("loop-run", help="Run the automation loop")
    p_loop_run.add_argument("--dry-run", action="store_true", help="Run non-browser stages only")
    p_loop_run.add_argument("--max-jobs", type=int, default=10, help="Maximum jobs to process")
    p_loop_run.add_argument("--output", help="Run directory (default: pipeline_runs/<run_id>/)")
    p_loop_run.add_argument("--resume", help="Resume an existing run directory")

    # job recommend
    p_rec = subparsers.add_parser("recommend", help="Rank scored jobs")
    p_rec.add_argument("--top", type=int, default=5, help="Number of results")
    p_rec.add_argument("--include-skipped", action="store_true", help="Include skipped jobs")

    # job paste
    subparsers.add_parser("paste", help="Import JD from stdin")

    # job validate-pack
    p_vp = subparsers.add_parser("validate-pack", help="Validate pack evidence claims")
    p_vp.add_argument("--job", required=True, help="Job ID")

    # job report
    subparsers.add_parser("report", help="Generate analytics report")

    # job scam-check
    p_scam = subparsers.add_parser("scam-check", help="Check an opportunity for scam signals")
    p_scam.add_argument("--name", required=True, help="Opportunity name")
    p_scam.add_argument("--description", required=True, help="Opportunity description")

    # job find
    p_find = subparsers.add_parser("find", help="Find income opportunities from profile")
    p_find.add_argument(
        "--direction",
        choices=["content", "freelance", "tool", "annotation", "training", "cross-border"],
        help="Filter by opportunity category",
    )

    # job plan
    p_plan = subparsers.add_parser("plan", help="Generate execution plan for an opportunity")
    p_plan.add_argument("--opportunity", required=True, help="Name of the opportunity to plan")

    # job boss-import
    p_boss = subparsers.add_parser("boss-import", help="Import jobs from BOSS Zhipin via CDP")
    p_boss.add_argument("--keyword", required=True, help="Search keyword (e.g. 'AIGC')")
    p_boss.add_argument("--city", default="100010000", help="City code (default: 100010000 = nationwide)")
    p_boss.add_argument("--port", type=int, default=9222, help="Chrome debug port (default: 9222)")

    # job submit
    p_submit_cmd = subparsers.add_parser("submit", help="Semi-automatic application submission")
    p_submit_cmd.add_argument("--job", required=True, help="Job ID")
    p_submit_cmd.add_argument("--platform", default="boss", help="Target platform (default: boss)")
    p_submit_cmd.add_argument("--confirm", action="store_true", help="Enable real submission (default is dry-run)")
    p_submit_cmd.add_argument("--port", type=int, default=9222, help="CDP port (default: 9222)")
    p_submit_cmd.add_argument("--headless", action="store_true", help="Run browser headless (standalone fallback only)")

    # job auto-submit
    p_auto = subparsers.add_parser("auto-submit", help="Auto-submit to BOSS Zhipin")
    p_auto.add_argument("--job", help="Single job ID (omit for batch)")
    p_auto.add_argument("--platform", default="boss")
    p_auto.add_argument("--confirm", action="store_true", help="Actually send messages")
    p_auto.add_argument("--port", type=int, default=9222)
    p_auto.add_argument("--headless", action="store_true")
    p_auto.add_argument("--max-jobs", type=int, default=5, help="Max jobs in batch mode")
    p_auto.add_argument("--interval-min", type=int, default=30, help="Min seconds between submissions")
    p_auto.add_argument("--interval-max", type=int, default=120, help="Max seconds between submissions")

    # job start — full automation pipeline
    p_start = subparsers.add_parser("start", help="Start full automation pipeline (LLM-guided)")
    p_start.add_argument("--keyword", help="Search keyword (e.g. 'Python开发')")
    p_start.add_argument("--max-jobs", type=int, default=10, help="Max successful submissions")
    p_start.add_argument("--dry-run", action="store_true", help="Analyze only, don't submit")
    p_start.add_argument("--port", type=int, default=9222, help="Chrome CDP port")
    p_start.add_argument("--headless", action="store_true")
    p_start.add_argument("--provider", choices=["anthropic", "openai"], help="LLM provider")
    p_start.add_argument("--api-key", help="API key (or use JOBOS_API_KEY env)")
    p_start.add_argument("--base-url", help="API base URL (or use JOBOS_BASE_URL env)")
    p_start.add_argument("--model", help="Model name override")

    # job auto-reply — monitor and auto-reply to recruiter messages
    p_reply = subparsers.add_parser("auto-reply", help="Auto-reply to recruiter messages on BOSS Zhipin")
    p_reply.add_argument("--interval", type=int, default=60, help="Seconds between checks")
    p_reply.add_argument("--max-replies", type=int, default=20, help="Max replies before stopping")
    p_reply.add_argument("--dry-run", action="store_true", help="Generate replies but don't send")
    p_reply.add_argument("--port", type=int, default=9222, help="Chrome CDP port")
    p_reply.add_argument("--headless", action="store_true")
    p_reply.add_argument("--provider", choices=["anthropic", "openai"], help="LLM provider")
    p_reply.add_argument("--api-key", help="API key")
    p_reply.add_argument("--base-url", help="API base URL")
    p_reply.add_argument("--model", help="Model name override")

    # job onboard — interactive profile setup with AI
    p_onboard = subparsers.add_parser("onboard", help="Interactive AI-guided profile setup")
    p_onboard.add_argument("--provider", choices=["anthropic", "openai"], help="LLM provider")
    p_onboard.add_argument("--api-key", help="API key")
    p_onboard.add_argument("--base-url", help="API base URL")
    p_onboard.add_argument("--model", help="Model name override")

    # job chat — standalone LLM conversation
    p_chat = subparsers.add_parser("chat", help="Chat with AI assistant")
    p_chat.add_argument("--provider", choices=["anthropic", "openai"], help="LLM provider")
    p_chat.add_argument("--api-key", help="API key")
    p_chat.add_argument("--base-url", help="API base URL")
    p_chat.add_argument("--model", help="Model name override")

    # job analyze — analyze a single job with LLM
    p_analyze = subparsers.add_parser("analyze", help="Analyze job match with LLM")
    p_analyze.add_argument("--job", required=True, help="Job ID")
    p_analyze.add_argument("--provider", choices=["anthropic", "openai"], help="LLM provider")
    p_analyze.add_argument("--api-key", help="API key")
    p_analyze.add_argument("--base-url", help="API base URL")
    p_analyze.add_argument("--model", help="Model name override")

    # job tui — launch REPL
    subparsers.add_parser("tui", help="Launch interactive REPL")

    # job start-repl
    subparsers.add_parser("start-repl", help="Launch interactive REPL (alias for tui)")

    # job config
    p_config = subparsers.add_parser("config", help="Manage configuration")
    config_sub = p_config.add_subparsers(dest="config_command")
    config_sub.add_parser("show", help="Show current config")
    config_sub.add_parser("edit", help="Open config in editor")
    config_sub.add_parser("wizard", help="Run interactive setup wizard")
    config_sub.add_parser("path", help="Print config file path")
    config_sub.add_parser("env-path", help="Print .env file path")
    p_config_set = config_sub.add_parser("set", help="Set config value")
    p_config_set.add_argument("key", help="Config key (dot notation, e.g. llm.provider)")
    p_config_set.add_argument("value", help="Value to set")
    p_config_get = config_sub.add_parser("get", help="Get config value")
    p_config_get.add_argument("key", help="Config key")

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
        "doctor": _cmd_doctor,
        "demo-seed": _cmd_demo_seed,
        "queue": _cmd_queue,
        "loop-plan": _cmd_loop_plan,
        "loop-run": _cmd_loop_run,
        "recommend": _cmd_recommend,
        "paste": _cmd_paste,
        "validate-pack": _cmd_validate_pack,
        "report": _cmd_report,
        "scam-check": _cmd_scam_check,
        "find": _cmd_find,
        "plan": _cmd_plan,
        "boss-import": _cmd_boss_import,
        "submit": _cmd_submit,
        "retro-freeform": _cmd_retro_freeform,
        "auto-submit": _cmd_auto_submit,
        "start": _cmd_start,
        "chat": _cmd_chat,
        "analyze": _cmd_analyze,
        "tui": _cmd_tui,
        "start-repl": _cmd_tui,
        "config": _cmd_config,
        "auto-reply": _cmd_auto_reply,
        "onboard": _cmd_onboard,
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
        state = {"jobs": {}, "active_rubric": "v0_student_internship", "rubric_history": [], "opportunities": [], "active_opportunity": None, "lessons": []}
        state_path.write_text(json.dumps(state, indent=2) + "\n")

    print(f"Created directory structure at {root}")
    print("Done. Edit profile/ files and rubrics/ to get started.")
    print()
    print("Tip: Run `job init --onboard` to let AI guide you through profile setup.")


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

    pack = generate_pack(job_data, pred_dict, profile, evidence)
    warnings = validate_pack(pack, evidence)

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


def _cmd_retro_freeform(args):
    from .retro import record_freeform_retro

    root = _get_root()
    job_id = args.job

    try:
        path = record_freeform_retro(
            job_id=job_id,
            text=args.text,
            lessons=args.lesson,
            state_dir=str(root),
        )
        print(f"Freeform retro recorded: {path}")
        print(f"  Text: {args.text[:80]}{'...' if len(args.text) > 80 else ''}")
        print(f"  Lessons ({len(args.lesson)}):")
        for lesson in args.lesson:
            print(f"    - {lesson}")
    except Exception as e:
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


def _cmd_doctor(args):
    import sys
    root = _get_root()
    checks = []

    # 1. Required directories
    required_dirs = ["profile", "jobs", "predictions", "applications", "retros", "rubrics"]
    for d in required_dirs:
        ok = (root / d).is_dir()
        checks.append((f"Directory {d}/", ok))

    # 2. Profile files
    for name in ("base.yaml", "skills.yaml", "availability.yaml"):
        ok = (root / "profile" / name).exists()
        checks.append((f"Profile file profile/{name}", ok))

    # 3. Active rubric
    state_path = root / ".job-state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        active = state.get("active_rubric")
        rubric_ok = active and (root / "rubrics" / f"{active}.md").exists()
        checks.append((f"Active rubric ({active})", rubric_ok))
    else:
        checks.append(("Active rubric (no state file)", False))

    # 4. Test fixtures
    mock_ok = (root / "tests" / "fixtures" / "mock_form.html").exists() or \
              (root / "adapters" / "local_mock_form" / "application_form.html").exists()
    checks.append(("Mock form fixture", mock_ok))

    # 5. Python version
    py_ok = sys.version_info >= (3, 11)
    checks.append((f"Python >= 3.11 (current: {sys.version.split()[0]})", py_ok))

    # 6. No live adapter
    checks.append(("No live-platform adapter enabled", True))

    # Print results
    all_ok = True
    for label, ok in checks:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {label}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\nAll checks passed.")
    else:
        print("\nSome checks failed. Fix the issues above.")
        sys.exit(1)


def _cmd_demo_seed(args):
    import shutil
    root = _get_root()

    # Run init first
    _cmd_init(args)

    # Sample profile files
    profile_dir = root / "profile"

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
        "  - Mandarin\n"
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
        "      tools: [pandas, NumPy, SQL]\n"
    )

    (profile_dir / "education.yaml").write_text(
        "education:\n"
        "  - institution: UC Berkeley\n"
        "    degree: B.S.\n"
        "    major: Computer Science\n"
        '    graduation_date: "2027-05"\n'
        "    gpa: 3.8\n"
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
        "  - Seattle, WA\n"
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
        "- Created interactive visualizations with matplotlib\n"
    )

    # Sample rubric
    rubrics_dir = root / "rubrics"
    rubrics_dir.mkdir(exist_ok=True)
    (rubrics_dir / "v0_student_internship.md").write_text(
        "# Rubric v0: Student Internship\n\n"
        "## Scoring Formula\n\n"
        "final_score = 0.30*fit + 0.25*evidence + 0.20*opportunity + 0.15*strategic - 0.10*friction - 0.20*risk\n\n"
        "## Dimensions\n\n"
        "### 1. Skill Match (weight: 30%)\n"
        "### 2. Evidence (weight: 25%)\n"
        "### 3. Opportunity (weight: 20%)\n"
        "### 4. Strategic (weight: 15%)\n"
        "### 5. Friction (weight: 10%)\n"
        "### 6. Risk (weight: 20%)\n"
    )

    # Sample JD
    raw_dir = root / "jobs" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "sample_swe_intern.md").write_text(
        "# Software Engineer Intern — Summer 2026\n\n"
        "Company: Acme Labs\n"
        "Location: San Francisco, CA (Hybrid)\n\n"
        "Requirements:\n"
        "- Python or JavaScript\n"
        "- React or similar frontend framework\n"
        "- SQL basics\n\n"
        "Nice to have:\n"
        "- Machine learning experience\n"
        "- Previous internship\n"
    )

    # Mock form
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
        '</form></body></html>'
    )

    # Update state with rubric
    state_path = root / ".job-state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        state["active_rubric"] = "v0_student_internship"
        state_path.write_text(json.dumps(state, indent=2) + "\n")

    print("Demo workspace created!")
    print(f"  Profile: {profile_dir}")
    print(f"  Rubric: {rubrics_dir / 'v0_student_internship.md'}")
    print(f"  Sample JD: {raw_dir / 'sample_swe_intern.md'}")
    print()
    print("Next steps:")
    print(f"  job import --file jobs/raw/sample_swe_intern.md")
    print(f"  job score --job <job-id>")


def _cmd_queue(args):
    from .queue import get_queue

    root = _get_root()
    q = get_queue(str(root))

    stages = [
        ("Imported (unscored)", "unscored"),
        ("Scored (unpredicted)", "unpredicted"),
        ("Predicted (unpacked)", "unpacked"),
        ("Packed (unsubmitted)", "unsubmitted"),
        ("Submitted — waiting 3d retro", "waiting_3d"),
        ("Submitted — waiting 14d retro", "waiting_14d"),
        ("Submitted — waiting 30d retro", "waiting_30d"),
        ("Opportunity — candidate", "opp_candidate"),
        ("Opportunity — verifying", "opp_verifying"),
        ("Opportunity — planning", "opp_planning"),
    ]

    has_any = False
    for label, key in stages:
        jobs = q.get(key, [])
        if jobs:
            has_any = True
            print(f"\n{label} ({len(jobs)}):")
            for j in jobs:
                print(f"  {j['job_id']}  {j.get('title', '')} @ {j.get('company', '')}")

    if not has_any:
        print("No jobs in queue. Import a job with: job import --file <path>")


def _cmd_loop_plan(args):
    from .loop import write_loop_plan

    root = _get_root()
    try:
        output_path = write_loop_plan(
            state_dir=root,
            output=getattr(args, "output", None),
            max_jobs=getattr(args, "max_jobs", 10),
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Loop plan written: {output_path}")


def _cmd_loop_run(args):
    from .loop import run_loop

    root = _get_root()
    try:
        summary = run_loop(
            state_dir=root,
            dry_run=getattr(args, "dry_run", False),
            output=getattr(args, "output", None),
            max_jobs=getattr(args, "max_jobs", 10),
            resume=getattr(args, "resume", None),
        )
    except (FileNotFoundError, NotImplementedError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Loop run written: {summary['run_dir']}")
    print(f"  Started: {summary['counts']['started']}")
    print(f"  Succeeded: {summary['counts']['succeeded']}")
    print(f"  Failed: {summary['counts']['failed']}")
    print(f"  Skipped: {summary['counts']['skipped']}")
    print(f"  Retried: {summary['counts']['retried']}")


def _cmd_recommend(args):
    from .recommend import recommend_jobs

    root = _get_root()
    results = recommend_jobs(str(root), top_n=args.top, include_skipped=args.include_skipped)

    if not results:
        print("No scored jobs to recommend. Score a job first.")
        return

    print(f"Top {len(results)} recommendations:\n")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r.get('title', '?')} @ {r.get('company', '?')}")
        print(f"     Score: {r.get('final_score', 0):.1f} | Risk: {r.get('risk', 0):.1f} | Evidence: {r.get('evidence', 0):.1f}")
        if r.get("recommendation_reason"):
            print(f"     {r['recommendation_reason']}")
        print()


def _cmd_paste(args):
    from .importer import import_job

    root = _get_root()

    # Read from stdin
    jd_text = sys.stdin.read()
    if not jd_text.strip():
        print("Error: No input received on stdin.", file=sys.stderr)
        sys.exit(1)

    # Write to temp file and import
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, dir=str(root)) as f:
        f.write(jd_text)
        tmp_path = f.name

    try:
        data = import_job(tmp_path, str(root / "jobs" / "normalized"))

        # Update state
        state_path = root / ".job-state.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {"jobs": {}}
        state["jobs"][data["job_id"]] = {
            "title": data["title"],
            "company": data["company"],
            "location": data.get("location", ""),
            "status": "imported",
            "captured_at": data.get("imported_at", ""),
            "source_file": "stdin",
        }
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        print(f"Imported from stdin: {data['job_id']}")
        print(f"  Title: {data['title']}")
        print(f"  Company: {data['company']}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _cmd_validate_pack(args):
    from .evidence_markers import generate_evidence_report
    from .profile_loader import load_evidence_bank

    root = _get_root()
    job_id = args.job

    # Load pack files
    pack_dir = root / "applications" / job_id
    if not pack_dir.exists():
        print(f"Error: No application pack for {job_id}. Run `job pack` first.", file=sys.stderr)
        sys.exit(1)

    pack_files = {}
    for f in pack_dir.iterdir():
        if f.is_file():
            pack_files[f.name] = f.read_text()

    evidence = load_evidence_bank(str(root))

    # Load job data for required skills
    state_path = root / ".job-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"jobs": {}}
    job_entry = state.get("jobs", {}).get(job_id, {})

    import yaml
    job_yaml = root / "jobs" / "normalized" / f"{job_id}.yaml"
    if job_yaml.exists():
        job_data = yaml.safe_load(job_yaml.read_text())
    else:
        job_data = job_entry

    report = generate_evidence_report(pack_files, evidence, job_data)

    print(f"Evidence validation for {job_id}:\n")

    print(f"  Supported claims: {len(report['supported'])}")
    for c in report["supported"]:
        print(f"    ✓ {c['claim'][:60]}... → {c['source']}")

    print(f"\n  Unsupported claims: {len(report['unsupported'])}")
    for c in report["unsupported"]:
        print(f"    ✗ {c['claim'][:60]}... [{c['file']}]")

    print(f"\n  Weak claims: {len(report['weak'])}")
    for c in report["weak"]:
        print(f"    ? {c['claim'][:60]}... ({c['reason']})")

    print(f"\n  Missing JD skills: {report['missing_jd_skills']}")
    print(f"  Overclaim risk: {report['overclaim_risk']:.0%}")

    if report["unsupported"]:
        print("\nWarning: Some claims lack evidence support. Review before submission.")
        sys.exit(1)
    else:
        print("\nAll claims are evidence-supported.")


def _cmd_report(args):
    from .report import generate_report

    root = _get_root()
    md = generate_report(str(root))
    print("Report generated: reports/report.md")
    # Print summary
    for line in md.split("\n"):
        if line.startswith("##"):
            print(line)


def _cmd_scam_check(args):
    from .scam_checker import check_opportunity

    verdict = check_opportunity(args.name, args.description)

    print(f"Scam check: {verdict.name}")
    print(f"  Verdict: {verdict.verdict}")
    print(f"  Red flags: {verdict.red_flags}")
    print(f"  Suspect flags: {verdict.suspect_flags}")
    print(f"  Reason: {verdict.reason}")
    print(f"  Verify first step: {verdict.verify_first_step}")
    print(f"  Income expectation: {verdict.income_expectation}")

    if verdict.verdict in ("feasible", "suspect"):
        root = _get_root()
        state_path = root / ".job-state.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {"jobs": {}, "opportunities": []}
        opportunities = state.get("opportunities", [])
        opp = {
            "name": verdict.name,
            "verdict": verdict.verdict,
            "red_flags": verdict.red_flags,
            "suspect_flags": verdict.suspect_flags,
            "reason": verdict.reason,
            "verify_first_step": verdict.verify_first_step,
            "income_expectation": verdict.income_expectation,
            "checked_at": verdict.checked_at,
            "status": "candidate",
        }
        opportunities.append(opp)
        state["opportunities"] = opportunities
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        print(f"\n  Written to .job-state.json opportunities[]")


def _cmd_find(args):
    from .opportunity_finder import find_opportunities
    from .profile_loader import load_profile

    root = _get_root()
    profile = load_profile(str(root))

    direction = args.direction if args.direction else None
    opportunities = find_opportunities(profile, direction)

    if not opportunities:
        print("No opportunities found for your profile.")
        return

    print(f"Found {len(opportunities)} opportunities:\n")
    for i, opp in enumerate(opportunities, 1):
        print(f"  {i}. {opp.name}")
        print(f"     Category: {opp.category} | Tier: {opp.for_tier} | Verdict: {opp.verdict}")
        print(f"     Money source: {opp.money_source}")
        print(f"     Income: {opp.income_expectation}")
        print()

    # Write to state
    state_path = root / ".job-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"jobs": {}, "opportunities": []}
    existing = state.get("opportunities", [])
    for opp in opportunities:
        existing.append(opp.to_dict())
    state["opportunities"] = existing
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"Written {len(opportunities)} opportunities to .job-state.json")


def _cmd_plan(args):
    from .action_planner import create_plan
    from .profile_loader import load_profile

    root = _get_root()
    state_path = root / ".job-state.json"
    if not state_path.exists():
        print("Error: No .job-state.json found. Run init first.", file=sys.stderr)
        sys.exit(1)

    state = json.loads(state_path.read_text())
    opportunities = state.get("opportunities", [])

    target = None
    for opp in opportunities:
        if opp.get("name") == args.opportunity:
            target = opp
            break

    if target is None:
        print(f"Error: Opportunity '{args.opportunity}' not found in .job-state.json", file=sys.stderr)
        print("Available opportunities:", file=sys.stderr)
        for opp in opportunities:
            print(f"  - {opp.get('name', '?')}", file=sys.stderr)
        sys.exit(1)

    profile = load_profile(str(root))
    plan = create_plan(target, profile)

    print(f"Action Plan for: {plan.opportunity_name}")
    print(f"\n1. Verification First Step:")
    print(f"   {plan.verification_first_step}")
    print(f"\n2. Two-Week Checklist:")
    for item in plan.two_week_checklist:
        print(f"   - {item}")
    print(f"\n3. Income Expectation:")
    print(f"   {plan.income_expectation}")
    print(f"\n4. Stop-Loss Line:")
    print(f"   {plan.stop_loss_line}")
    print(f"\n5. AI Leverage Points:")
    for point in plan.ai_leverage_points:
        print(f"   - {point}")

    if plan.warnings:
        print(f"\nWarnings:")
        for w in plan.warnings:
            print(f"   ! {w}")

    # Write plan to state
    state["active_opportunity"] = plan.to_dict()
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"\nPlan written to .job-state.json active_opportunity")


def _cmd_submit(args):
    from .submitter import submit_application

    root = _get_root()
    job_id = args.job
    platform = args.platform
    dry_run = not args.confirm

    try:
        result = submit_application(
            job_id=job_id,
            platform=platform,
            state_dir=str(root),
            dry_run=dry_run,
            confirm=args.confirm,
            cdp_port=args.port,
            headless=args.headless,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except NotImplementedError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    mode = "DRY RUN" if result.dry_run else "LIVE"
    print(f"Submit [{mode}] for {job_id} on {platform}:")
    print(f"  Fields: {len(result.fields_filled)}")
    for field_name, value in result.fields_filled.items():
        preview = value[:60] + ("..." if len(value) > 60 else "")
        print(f"    {field_name}: {preview}")
    if result.page_title:
        print(f"  Page title: {result.page_title}")
    if result.screenshot_path:
        print(f"  Screenshot: {result.screenshot_path}")
    if result.error:
        print(f"  Error: {result.error}", file=sys.stderr)


def _cmd_auto_submit(args):
    from .submitter import auto_submit_single, auto_submit_batch, _load_pack_files, _connect_browser

    root = _get_root()
    dry_run = not args.confirm
    mode = "DRY RUN" if dry_run else "LIVE"

    if args.job:
        # Single job mode
        job_id = args.job
        state_path = root / ".job-state.json"
        if not state_path.exists():
            print("Error: No .job-state.json found. Run `job init` first.", file=sys.stderr)
            sys.exit(1)

        state = json.loads(state_path.read_text())
        job_info = state.get("jobs", {}).get(job_id)
        if not job_info:
            print(f"Error: Job {job_id} not found in state.", file=sys.stderr)
            sys.exit(1)

        job_info["job_id"] = job_id
        pack_files = _load_pack_files(root / "applications" / job_id)
        if not pack_files:
            print(f"Error: No application pack for {job_id}. Run `job pack` first.", file=sys.stderr)
            sys.exit(1)

        pw, browser, context, page = _connect_browser(args.port, args.headless)
        try:
            result = auto_submit_single(
                page=page,
                job_data=job_info,
                pack_files=pack_files,
                state_dir=str(root),
                dry_run=dry_run,
                confirm=args.confirm,
            )
        finally:
            try:
                browser.close()
            except Exception:
                pass
            try:
                pw.stop()
            except Exception:
                pass

        print(f"Auto-submit [{mode}] for {job_id}:")
        print(f"  Submitted: {result.submitted}")
        if result.screenshot_path:
            print(f"  Screenshot: {result.screenshot_path}")
        if result.error:
            print(f"  Error: {result.error}", file=sys.stderr)
            sys.exit(1)

    else:
        # Batch mode
        print(f"Auto-submit batch [{mode}]:")
        print(f"  Max jobs: {args.max_jobs}")
        print(f"  Interval: {args.interval_min}-{args.interval_max}s")

        summary = auto_submit_batch(
            state_dir=str(root),
            cdp_port=args.port,
            max_jobs=args.max_jobs,
            interval_min=args.interval_min,
            interval_max=args.interval_max,
            dry_run=dry_run,
            confirm=args.confirm,
        )

        print(f"\nBatch summary:")
        print(f"  Attempted: {summary.total_attempted}")
        print(f"  Succeeded: {summary.total_succeeded}")
        print(f"  Failed: {summary.total_failed}")

        for result in summary.results:
            status = "OK" if not result.error else "FAIL"
            print(f"  [{status}] {result.job_id}: {result.page_url or 'no url'}")

        if summary.errors:
            print(f"\nErrors:", file=sys.stderr)
            for err in summary.errors:
                print(f"  - {err}", file=sys.stderr)


def _cmd_boss_import(args):
    from .boss_import import import_from_boss
    from .config import load_config
    from datetime import datetime, timezone
    import re as _re

    root = _get_root()
    keyword = args.keyword
    city_code = args.city
    port = args.port
    extraction_config = load_config().get("extraction", {})

    try:
        jobs = import_from_boss(
            keyword,
            city_code,
            port,
            use_scrapling=extraction_config.get("use_scrapling", True),
            record_diagnostics=extraction_config.get("record_diagnostics", True),
            include_html_snapshot=extraction_config.get("include_html_snapshot", True),
            html_snapshot_limit=extraction_config.get("html_snapshot_limit", 250000),
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ConnectionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not jobs:
        print(f"No jobs found for keyword '{keyword}' (city={city_code}).")
        return

    raw_dir = root / "jobs" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    state_path = root / ".job-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"jobs": {}}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    imported = 0

    for i, job in enumerate(jobs):
        slug = _re.sub(r"[^a-z0-9]+", "-", job["title"].lower()).strip("-")[:40]
        job_id = f"{ts}-boss-{i:03d}-{slug}"

        # Write raw job data as JSON
        raw_path = raw_dir / f"{job_id}.json"
        raw_path.write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n")

        # Register in state
        state["jobs"][job_id] = {
            "title": job["title"],
            "company": job["company"],
            "location": job.get("city_code", city_code),
            "status": "imported",
            "captured_at": job.get("imported_at", ""),
            "source": "boss_zhipin",
            "keyword": keyword,
            "link": job.get("link", ""),
        }
        if job.get("extractor"):
            state["jobs"][job_id]["extractor"] = job["extractor"]
        if job.get("page_state"):
            state["jobs"][job_id]["page_state"] = job["page_state"]
        if job.get("extraction_diagnostics"):
            state["jobs"][job_id]["extraction_diagnostics"] = job["extraction_diagnostics"]
        imported += 1

    state_path.write_text(json.dumps(state, indent=2) + "\n")

    print(f"Imported {imported} jobs for keyword '{keyword}':")
    for job in jobs:
        print(f"  - {job['title']} @ {job['company']}  {job['salary']}")
    print(f"\nRaw files saved to: jobs/raw/")
    print(f"State updated: .job-state.json")


def _build_llm_config(args) -> dict:
    """从CLI参数构建LLM配置"""
    config = {}
    if hasattr(args, "provider") and args.provider:
        config["provider"] = args.provider
    if hasattr(args, "api_key") and args.api_key:
        config["api_key"] = args.api_key
    if hasattr(args, "base_url") and args.base_url:
        config["base_url"] = args.base_url
    if hasattr(args, "model") and args.model:
        config["model"] = args.model
    return config if config else None


def _cmd_start(args):
    from .orchestrator import run_full_pipeline

    root = _get_root()
    config = _build_llm_config(args)

    result = run_full_pipeline(
        state_dir=str(root),
        cdp_port=args.port,
        max_jobs=args.max_jobs,
        dry_run=args.dry_run,
        config=config,
        search_keyword=args.keyword or "",
        headless=args.headless,
    )

    if result.get("error"):
        sys.exit(1)


def _cmd_chat(args):
    from .llm.provider import get_llm_adapter
    from .llm.conversation import Conversation
    from .llm.prompts import INTRO_SYSTEM

    config = _build_llm_config(args)
    llm = get_llm_adapter(config)

    print("\n🤖 AI助手已就绪。输入 'quit' 退出。\n")

    conv = Conversation(llm)

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break

        if not user_input:
            continue

        reply = conv.chat(user_input, system=INTRO_SYSTEM)
        print(f"\nAI: {reply}\n")


def _cmd_analyze(args):
    from .llm.provider import get_llm_adapter
    from .llm.job_analyzer import analyze_match, explain_scores, check_scam
    from .profile_loader import load_profile
    import yaml

    root = _get_root()
    job_id = args.job
    config = _build_llm_config(args)

    # Load job data
    state_path = root / ".job-state.json"
    if not state_path.exists():
        print("Error: No .job-state.json found. Run `job init` first.", file=sys.stderr)
        sys.exit(1)

    state = json.loads(state_path.read_text())
    job_entry = state.get("jobs", {}).get(job_id)
    if not job_entry:
        print(f"Error: Job {job_id} not found.", file=sys.stderr)
        sys.exit(1)

    # Try loading normalized job data
    job_yaml = root / "jobs" / "normalized" / f"{job_id}.yaml"
    job_json = root / "jobs" / "raw" / f"{job_id}.json"
    if job_yaml.exists():
        job_data = yaml.safe_load(job_yaml.read_text())
    elif job_json.exists():
        job_data = json.loads(job_json.read_text())
    else:
        job_data = {"job_id": job_id, **job_entry}

    profile = load_profile(str(root))
    llm = get_llm_adapter(config)

    print(f"\n📊 分析职位: {job_data.get('title', job_id)}")
    print(f"   公司: {job_data.get('company', '未知')}\n")

    # Scam check
    print("🔒 反诈检查...")
    scam = check_scam(llm, json.dumps(job_data, ensure_ascii=False))
    risk = scam.get("risk_level", "unknown")
    emoji = {"low": "✅", "medium": "⚠️", "high": "❌", "critical": "🚫"}.get(risk, "❓")
    print(f"   {emoji} 风险等级: {risk}")
    if scam.get("red_flags"):
        print(f"   红线: {scam['red_flags']}")
    if scam.get("suspect_signals"):
        print(f"   可疑: {scam['suspect_signals']}")
    print()

    # Match analysis
    print("📊 匹配度分析...")
    match = analyze_match(llm, job_data, profile)
    print(f"   总分: {match.get('total_score', '?')}/100")
    print(f"   结论: {match.get('verdict', '未知')}")
    if match.get("breakdown"):
        print("   维度:")
        for dim, score in match["breakdown"].items():
            print(f"     {dim}: {score}")
    if match.get("strengths"):
        print(f"   优势: {', '.join(match['strengths'])}")
    if match.get("weaknesses"):
        print(f"   劣势: {', '.join(match['weaknesses'])}")
    print()

    # Explanation
    print("💡 分析解读...")
    explanation = explain_scores(llm, match, job_data, profile)
    print(f"   {explanation}")


def _cmd_tui(args):
    from .repl import run_repl

    root = _get_root()
    run_repl(str(root))


def _cmd_config(args):
    from .config import print_config, set_config_value, get_config_value, config_wizard, CONFIG_FILE, ENV_FILE
    import subprocess

    cmd = getattr(args, "config_command", None)

    if cmd == "show" or cmd is None:
        if not CONFIG_FILE.exists():
            print(f"配置文件不存在: {CONFIG_FILE}")
            print("运行 `job config wizard` 进行初始配置。")
            return
        print_config()

    elif cmd == "edit":
        subprocess.run(["xdg-open", str(CONFIG_FILE)])

    elif cmd == "wizard":
        config_wizard()

    elif cmd == "path":
        print(CONFIG_FILE)

    elif cmd == "env-path":
        print(ENV_FILE)

    elif cmd == "set":
        key = args.key
        value = args.value
        set_config_value(key, value)
        print(f"✅ {key} = {value}")

    elif cmd == "get":
        val = get_config_value(args.key)
        print(f"{args.key} = {val}")


def _cmd_auto_reply(args):
    """启动自动回复"""
    from .auto_reply import run_auto_reply_loop
    config = _build_llm_config(args)
    root = Path.cwd()
    result = run_auto_reply_loop(
        state_dir=str(root),
        config=config,
        interval=args.interval,
        max_replies=args.max_replies,
        dry_run=args.dry_run,
        cdp_port=args.port,
        headless=args.headless,
    )
    if result.get("error"):
        print(f"❌ 错误: {result['error']}")


def _cmd_onboard(args):
    """启动AI引导的信息收集"""
    from .onboarding import run_onboarding
    config = _build_llm_config(args)
    root = Path.cwd()
    run_onboarding(state_dir=str(root), config=config)
