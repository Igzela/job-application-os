#!/usr/bin/env bash
set -euo pipefail

MAX_JOBS="${MAX_JOBS:-10}"
RUN_DIR="${RUN_DIR:-}"

echo "pipeline_dry_run: will create loop plan and execute non-browser dry-run stages"
echo "pipeline_dry_run: stages: score, predict, pack, validate"
echo "pipeline_dry_run: MAX_JOBS=${MAX_JOBS}"

if [[ -n "${RUN_DIR}" ]]; then
  echo "pipeline_dry_run: command: job loop-run --dry-run --max-jobs ${MAX_JOBS} --output ${RUN_DIR}"
  job loop-run --dry-run --max-jobs "${MAX_JOBS}" --output "${RUN_DIR}"
else
  echo "pipeline_dry_run: command: job loop-run --dry-run --max-jobs ${MAX_JOBS}"
  job loop-run --dry-run --max-jobs "${MAX_JOBS}"
fi
