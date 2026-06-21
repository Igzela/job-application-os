#!/usr/bin/env bash
set -euo pipefail

echo "check_architecture: will verify architecture constraints without modifying files"
echo "check_architecture: command: python3 scripts/check_architecture.py"
python3 scripts/check_architecture.py
