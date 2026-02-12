#!/usr/bin/env bash
# Shared configuration and helpers for artisan workflow scripts.
# Source this from dress-rehearsal.sh, adopt-prior.sh, etc.
#
# Env vars (all optional):
#   ARTISAN_SEED          — Path to enriched context seed JSON
#   ARTISAN_OUTPUT_DIR    — Output directory for artifacts
#   ARTISAN_PROJECT_ROOT  — Target project root (where generated code is written)
#
# When ARTISAN_PROJECT_ROOT is unset, it is inferred by walking up from the
# seed path until we find pyproject.toml or .contextcore.yaml. If inference
# fails, defaults to "." with a warning (multi-repo setups should set it explicitly).
set -euo pipefail

_infer_project_root_from_seed() {
  local seed="$1"
  [[ -z "$seed" || ! -f "$seed" ]] && return 1
  local dir
  dir="$(cd "$(dirname "$seed")" && pwd)"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/pyproject.toml" || -f "$dir/.contextcore.yaml" ]]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

# Resolve SEED, OUTPUT_DIR, PROJECT_ROOT from env vars and args.
# Usage: set from env, or pass as arguments after sourcing:
#   SEED, OUTPUT_DIR, PROJECT_ROOT can be set by caller before sourcing,
#   or ARTISAN_* env vars are used. PROJECT_ROOT is inferred from SEED if unset.
resolve_artisan_config() {
  # SEED: required — from ARTISAN_SEED or first non-empty of existing vars
  SEED="${ARTISAN_SEED:-${SEED:-}}"
  if [[ -z "$SEED" || ! -f "$SEED" ]]; then
    echo "Error: ARTISAN_SEED must point to a valid context seed JSON file." >&2
    echo "  Example: export ARTISAN_SEED=/path/to/artisan-context-seed.json" >&2
    exit 1
  fi
  SEED="$(cd "$(dirname "$SEED")" && pwd)/$(basename "$SEED")"

  # OUTPUT_DIR: default to seed_dir/artisan-design (common convention)
  local seed_dir
  seed_dir="$(dirname "$SEED")"
  OUTPUT_DIR="${ARTISAN_OUTPUT_DIR:-${OUTPUT_DIR:-${seed_dir}/artisan-design}}"
  # Resolve to absolute path
  if [[ -d "$(dirname "$OUTPUT_DIR")" ]]; then
    OUTPUT_DIR="$(cd "$(dirname "$OUTPUT_DIR")" && pwd)/$(basename "$OUTPUT_DIR")"
  elif [[ "$OUTPUT_DIR" != /* ]]; then
    OUTPUT_DIR="$(pwd)/$OUTPUT_DIR"
  fi

  # PROJECT_ROOT: from ARTISAN_PROJECT_ROOT, or infer from seed, or default "."
  if [[ -n "${ARTISAN_PROJECT_ROOT:-}${PROJECT_ROOT:-}" ]]; then
    PROJECT_ROOT="$(cd "${ARTISAN_PROJECT_ROOT:-$PROJECT_ROOT}" && pwd)"
  else
    local inferred
    if inferred="$(_infer_project_root_from_seed "$SEED")"; then
      PROJECT_ROOT="$inferred"
    else
      PROJECT_ROOT="$(pwd)"
      echo "Warning: Could not infer project root from seed. Using current directory (.)." >&2
      echo "  For multi-repo setups (e.g. SDK generating into wayfinder), set ARTISAN_PROJECT_ROOT." >&2
    fi
  fi
}
