#!/usr/bin/env bash
# Convenience wrapper: dress rehearsal for PI-002 (wayfinder manifest-generate plan).
# Delegates to dress-rehearsal.sh with wayfinder paths.
# Override via ARTISAN_SEED, ARTISAN_OUTPUT_DIR, ARTISAN_PROJECT_ROOT.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Wayfinder defaults (override with env vars)
export ARTISAN_SEED="${ARTISAN_SEED:-/Users/neilyashinsky/Documents/dev/wayfinder/out/manifest-generate-ingestion/artisan-context-seed.json}"
export ARTISAN_OUTPUT_DIR="${ARTISAN_OUTPUT_DIR:-/Users/neilyashinsky/Documents/dev/wayfinder/out/manifest-generate-ingestion/artisan-design}"
export ARTISAN_PROJECT_ROOT="${ARTISAN_PROJECT_ROOT:-/Users/neilyashinsky/Documents/dev/wayfinder}"

exec "${SCRIPT_DIR}/dress-rehearsal.sh" PI-002 "$@"
