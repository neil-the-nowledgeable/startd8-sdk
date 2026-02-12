#!/usr/bin/env bash
# Full run for PI-001, adopting design artifacts from a prior dress rehearsal.
# Tasks with valid prior designs skip the LLM call; others run normally.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Activate the virtual environment if not already active
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
  echo "Activating virtualenv at ${REPO_ROOT}/.venv"
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

SEED="/Users/neilyashinsky/Documents/dev/wayfinder/out/manifest-generate-ingestion/artisan-context-seed.json"
OUTPUT_DIR="/Users/neilyashinsky/Documents/dev/wayfinder/out/manifest-generate-ingestion/artisan-design"

STARTD8_OTEL=disabled python3 "${SCRIPT_DIR}/run_artisan_workflow.py" \
  --seed "$SEED" \
  --output-dir "$OUTPUT_DIR" \
  --task-filter PI-001 \
  --adopt-prior \
  --design-max-tokens 8192
