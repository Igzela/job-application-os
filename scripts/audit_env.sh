#!/usr/bin/env bash
set -u

echo "audit_env: read-only environment audit"
echo "audit_env: checking Python, Node, Chrome/CDP hints, package metadata, config, pytest readiness"

echo
echo "## Python"
command -v python3 || true
python3 --version || true

echo
echo "## Node"
command -v node || true
node --version || true
command -v npm || true
npm --version || true

echo
echo "## Chrome / CDP"
command -v google-chrome || true
command -v chromium || true
command -v chromium-browser || true
if command -v curl >/dev/null 2>&1; then
  echo "audit_env: probing http://127.0.0.1:9222/json/version without changing browser state"
  curl --max-time 2 --silent --show-error http://127.0.0.1:9222/json/version || true
  echo
fi

echo
echo "## Package"
python3 -m pip show job-application-os || true
python3 -m pip show pytest || true

echo
echo "## Config"
test -f .job-state.json && echo ".job-state.json: present" || echo ".job-state.json: missing"
test -f pyproject.toml && echo "pyproject.toml: present" || echo "pyproject.toml: missing"
test -d profile && echo "profile/: present" || echo "profile/: missing"
test -d jobs && echo "jobs/: present" || echo "jobs/: missing"
test -d applications && echo "applications/: present" || echo "applications/: missing"

echo
echo "## Pytest readiness"
python3 -m pytest --version || true
