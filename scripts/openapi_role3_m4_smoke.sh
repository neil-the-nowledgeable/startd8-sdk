#!/usr/bin/env bash
# Role 3 M4 — two-app seam fixture smoke ($0, offline).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}${ROOT}/src"
PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi
exec "$PY" -m pytest tests/unit/backend_codegen/test_openapi_role3_m4_fixture.py -q "$@"
