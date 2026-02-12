#!/usr/bin/env bash
# Dress rehearsal for PI-001: runs real LLM calls through DESIGN to surface issues.
# Artifacts written to <output-dir>/.dress-rehearsal/
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
PROJECT_ROOT="/Users/neilyashinsky/Documents/dev/wayfinder"

STARTD8_OTEL=disabled python3 "${SCRIPT_DIR}/run_artisan_workflow.py" \
  --seed "$SEED" \
  --output-dir "$OUTPUT_DIR" \
  --project-root "$PROJECT_ROOT" \
  --task-filter PI-001 \
  --dress-rehearsal \
  --design-max-tokens 8192
