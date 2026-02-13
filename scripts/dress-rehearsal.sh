#!/usr/bin/env bash
# Dress rehearsal: runs real LLM calls through DESIGN to surface issues.
# Artifacts written to <output-dir>/.dress-rehearsal/
#
# Usage: dress-rehearsal.sh TASK_ID [PROJECT_ROOT]
#   TASK_ID      — e.g. PI-001, PI-002
#   PROJECT_ROOT — (optional) target project root; overrides ARTISAN_PROJECT_ROOT
#
# Env vars (all optional):
#   ARTISAN_SEED          — Path to enriched context seed JSON (required if not set)
#   ARTISAN_OUTPUT_DIR    — Output directory for artifacts
#   ARTISAN_PROJECT_ROOT  — Target project root (inferred from seed if unset)
#   ARTISAN_RESUME        — Set to 1 to resume from last checkpoint
#
# Example (env vars):
#   export ARTISAN_SEED=/path/to/artisan-context-seed.json
#   ./scripts/dress-rehearsal.sh PI-001
#
# Example (wayfinder):
#   ARTISAN_SEED=~/Documents/dev/wayfinder/out/manifest-generate-ingestion/artisan-context-seed.json \
#     ./scripts/dress-rehearsal.sh PI-002
set -euo pipefail

TASK_ID="${1:-}"
if [ -z "$TASK_ID" ]; then
  echo "Usage: $0 TASK_ID [PROJECT_ROOT]"
  echo ""
  echo "  TASK_ID      — e.g. PI-001, PI-002"
  echo "  PROJECT_ROOT — (optional) target project root for generated code"
  echo ""
  echo "Env vars: ARTISAN_SEED (required), ARTISAN_OUTPUT_DIR, ARTISAN_PROJECT_ROOT"
  echo ""
  echo "Example:"
  echo "  ARTISAN_SEED=/path/to/artisan-context-seed.json $0 PI-001"
  exit 1
fi

# Optional override from second arg
[[ -n "${2:-}" ]] && export ARTISAN_PROJECT_ROOT="$2"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Activate the virtual environment if not already active
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
  echo "Activating virtualenv at ${REPO_ROOT}/.venv"
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

# shellcheck source=artisan_common.sh
source "${SCRIPT_DIR}/artisan_common.sh"
resolve_artisan_config

RESUME_ARG=""
[[ "${ARTISAN_RESUME:-0}" == "1" ]] && RESUME_ARG="--resume"

STARTD8_OTEL=disabled python3 "${SCRIPT_DIR}/run_artisan_workflow.py" \
  --seed "$SEED" \
  --output-dir "$OUTPUT_DIR" \
  --project-root "$PROJECT_ROOT" \
  --task-filter "$TASK_ID" \
  --dress-rehearsal \
  --design-max-tokens 8192 \
  $RESUME_ARG
