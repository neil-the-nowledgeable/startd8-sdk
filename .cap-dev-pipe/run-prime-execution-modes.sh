#!/usr/bin/env bash
# ============================================================================
# Run Capability Delivery Pipeline for Prime Execution Modes
#
# Plan:      docs/design/prime/PRIME_EXECUTION_MODES_PLAN.md
# Reqs:      docs/design/prime/PRIME_EXECUTION_MODES_REQUIREMENTS.md
# Output:   pipeline-output/prime-execution-modes/
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SDK_ROOT="${SDK_ROOT:-$HOME/Documents/dev/startd8-sdk}"

PLAN="$SDK_ROOT/docs/design/prime/PRIME_EXECUTION_MODES_PLAN.md"
REQS="$SDK_ROOT/docs/design/prime/PRIME_EXECUTION_MODES_REQUIREMENTS.md"
OUTPUT_DIR="$SCRIPT_DIR/pipeline-output/prime-execution-modes"

# Optional: run from scratch (clear existing output first)
FROM_SCRATCH="${FROM_SCRATCH:-false}"
if [ "$FROM_SCRATCH" = "true" ] || [ "${1:-}" = "--from-scratch" ]; then
    echo "Clearing output directory for fresh run..."
    rm -rf "$OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR"
fi

cd "$SCRIPT_DIR"
./run-cap-delivery.sh \
  --plan "$PLAN" \
  --requirements "$REQS" \
  --project startd8 \
  --name prime-execution-modes \
  --project-root "$SDK_ROOT"
