#!/usr/bin/env bash
set -euo pipefail

echo "local_ci: will run local Python test suite with compact tracebacks"
echo "local_ci: command: python3 -m pytest tests/ --tb=short"
python3 -m pytest tests/ --tb=short
