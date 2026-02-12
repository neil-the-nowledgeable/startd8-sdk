#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
source .venv/bin/activate

python3 scripts/emit_task_tracking.py "$@"
