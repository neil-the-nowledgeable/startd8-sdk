#!/usr/bin/env bash
# Role 3 M5 — cross-repo seam pytest entry ($0, offline except loopback remote test).
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src pytest tests/unit/backend_codegen/test_openapi_role3_m5_cross_repo.py -q "$@"
