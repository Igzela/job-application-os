#!/usr/bin/env bash
set -euo pipefail

echo "local_ci: will compile Python, run architecture guards, then run tests"
echo "local_ci: command: python3 -m compileall -q jobos"
python3 -m compileall -q jobos
echo "local_ci: command: bash scripts/check_architecture.sh"
bash scripts/check_architecture.sh
echo "local_ci: command: python3 -m pytest tests/ --tb=short"
python3 -m pytest tests/ --tb=short
