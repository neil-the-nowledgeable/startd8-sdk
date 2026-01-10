#!/usr/bin/env bash
set -euo pipefail

# Backup runner for local testing with Anthropic.
#
# Security note:
# - This script does NOT embed ANTHROPIC_API_KEY in plain text.
# - Instead, it loads from a local-only env file (default: .env.local) OR prompts you interactively.
# - This avoids accidentally committing or sharing your API key.
#
# Usage:
#   ./run_mcp_anthropic_local.sh
#
# Optional:
#   STARTD8_MCP_ENV_FILE=.env.local ./run_mcp_anthropic_local.sh

ROOT_DIR="$(
  cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1
  pwd
)"
cd "$ROOT_DIR"

# Load environment (secrets/config) for local runs.
# - If STARTD8_MCP_ENV_FILE is set, load ONLY that file.
# - Otherwise, load `.env` then `.env.local` (local overrides win).
ENV_FILE="${STARTD8_MCP_ENV_FILE:-}"
if [[ -n "$ENV_FILE" ]]; then
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
else
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ROOT_DIR/.env"
    set +a
  fi
  if [[ -f "$ROOT_DIR/.env.local" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ROOT_DIR/.env.local"
    set +a
  fi
  # For error messages, prefer pointing users at `.env.local` if it exists.
  if [[ -f "$ROOT_DIR/.env.local" ]]; then
    ENV_FILE="$ROOT_DIR/.env.local"
  elif [[ -f "$ROOT_DIR/.env" ]]; then
    ENV_FILE="$ROOT_DIR/.env"
  else
    ENV_FILE="$ROOT_DIR/.env.local"
  fi
fi

# If still missing, prompt (hidden input).
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  # If we're non-interactive (e.g., launched by an MCP client), don't hang waiting for input.
  if [[ ! -t 0 ]]; then
    echo "[run_mcp_anthropic_local] ERROR: ANTHROPIC_API_KEY not set and stdin is not a TTY." >&2
    echo "[run_mcp_anthropic_local] Fix: put ANTHROPIC_API_KEY in $ENV_FILE (or export it) and restart." >&2
    exit 2
  fi
  echo "[run_mcp_anthropic_local] ANTHROPIC_API_KEY not set." >&2
  echo "[run_mcp_anthropic_local] Enter it now (input hidden), or create $ENV_FILE with:" >&2
  echo "  ANTHROPIC_API_KEY=your_key_here" >&2
  read -r -s -p "ANTHROPIC_API_KEY: " ANTHROPIC_API_KEY
  echo >&2
  export ANTHROPIC_API_KEY
fi

# Note: we intentionally do NOT force STARTD8_MCP_ENV_FILE here when it's unset.
# `run_mcp.sh` will load `.env` and `.env.local` automatically in that case.

# -----------------------------------------------------------------------------
# Observability defaults for local dev (safe + overrideable)
# -----------------------------------------------------------------------------
# Your common local topology:
# - MCP runs on macOS host
# - Alloy runs in Docker and scrapes via host.docker.internal
# This requires binding the metrics endpoint to 0.0.0.0 (not 127.0.0.1).

export STARTD8_MCP_SERVICE="${STARTD8_MCP_SERVICE:-startd8-mcp}"
export STARTD8_MCP_ENV="${STARTD8_MCP_ENV:-local}"
export STARTD8_MCP_VERSION="${STARTD8_MCP_VERSION:-0.1.0}"

# Enable Prometheus metrics by default for this *local dev runner*.
# Override by setting STARTD8_MCP_METRICS_PORT="" (empty) or unsetting it in your env file.
export STARTD8_MCP_METRICS_PORT="${STARTD8_MCP_METRICS_PORT:-9464}"
export STARTD8_MCP_METRICS_ADDR="${STARTD8_MCP_METRICS_ADDR:-0.0.0.0}"

# Emit JSONL events to a local file (Loki-friendly).
mkdir -p "$ROOT_DIR/logs"
export STARTD8_MCP_EVENT_LOG_FILE="${STARTD8_MCP_EVENT_LOG_FILE:-$ROOT_DIR/logs/mcp-events.jsonl}"

# Optional traces to Alloy/Tempo (publish Alloy 4318 on host).
export STARTD8_MCP_TRACING="${STARTD8_MCP_TRACING:-1}"
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT:-http://localhost:4318/v1/traces}"

exec "$ROOT_DIR/run_mcp.sh"

