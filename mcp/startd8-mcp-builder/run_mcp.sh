#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
  cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1
  pwd
)"
cd "$ROOT_DIR"

# -----------------------------------------------------------------------------
# Optional env loading
# -----------------------------------------------------------------------------
# Best practice: keep secrets in a local-only `.env` (gitignored).
# You can override the env file path via STARTD8_MCP_ENV_FILE.

# Preserve caller-provided env vars so `.env` files can't accidentally override them.
# This matters for observability ports (metrics) and other settings when started by Cursor.
_ORIG_STARTD8_MCP_METRICS_PORT_SET="${STARTD8_MCP_METRICS_PORT+1}"
_ORIG_STARTD8_MCP_METRICS_PORT="${STARTD8_MCP_METRICS_PORT-}"
_ORIG_STARTD8_MCP_METRICS_ADDR_SET="${STARTD8_MCP_METRICS_ADDR+1}"
_ORIG_STARTD8_MCP_METRICS_ADDR="${STARTD8_MCP_METRICS_ADDR-}"
_ORIG_STARTD8_MCP_EVENT_LOG_FILE_SET="${STARTD8_MCP_EVENT_LOG_FILE+1}"
_ORIG_STARTD8_MCP_EVENT_LOG_FILE="${STARTD8_MCP_EVENT_LOG_FILE-}"
_ORIG_STARTD8_MCP_TRACING_SET="${STARTD8_MCP_TRACING+1}"
_ORIG_STARTD8_MCP_TRACING="${STARTD8_MCP_TRACING-}"
_ORIG_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT_SET="${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT+1}"
_ORIG_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT-}"
_ORIG_STARTD8_MCP_SERVICE_SET="${STARTD8_MCP_SERVICE+1}"
_ORIG_STARTD8_MCP_SERVICE="${STARTD8_MCP_SERVICE-}"
_ORIG_STARTD8_MCP_ENV_SET="${STARTD8_MCP_ENV+1}"
_ORIG_STARTD8_MCP_ENV="${STARTD8_MCP_ENV-}"
_ORIG_STARTD8_MCP_VERSION_SET="${STARTD8_MCP_VERSION+1}"
_ORIG_STARTD8_MCP_VERSION="${STARTD8_MCP_VERSION-}"

ENV_FILE="${STARTD8_MCP_ENV_FILE:-.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi
# Optional local override file (common pattern: secrets live in .env.local).
# Only loaded when using the default env file (i.e., STARTD8_MCP_ENV_FILE is not set),
# so explicit overrides keep full control.
if [[ -z "${STARTD8_MCP_ENV_FILE:-}" && -f ".env.local" ]]; then
  set -a
  # shellcheck disable=SC1090
  source ".env.local"
  set +a
fi

# Restore preserved caller-provided env vars.
if [[ -n "${_ORIG_STARTD8_MCP_METRICS_PORT_SET:-}" ]]; then export STARTD8_MCP_METRICS_PORT="$_ORIG_STARTD8_MCP_METRICS_PORT"; fi
if [[ -n "${_ORIG_STARTD8_MCP_METRICS_ADDR_SET:-}" ]]; then export STARTD8_MCP_METRICS_ADDR="$_ORIG_STARTD8_MCP_METRICS_ADDR"; fi
if [[ -n "${_ORIG_STARTD8_MCP_EVENT_LOG_FILE_SET:-}" ]]; then export STARTD8_MCP_EVENT_LOG_FILE="$_ORIG_STARTD8_MCP_EVENT_LOG_FILE"; fi
if [[ -n "${_ORIG_STARTD8_MCP_TRACING_SET:-}" ]]; then export STARTD8_MCP_TRACING="$_ORIG_STARTD8_MCP_TRACING"; fi
if [[ -n "${_ORIG_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT_SET:-}" ]]; then export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="$_ORIG_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"; fi
if [[ -n "${_ORIG_STARTD8_MCP_SERVICE_SET:-}" ]]; then export STARTD8_MCP_SERVICE="$_ORIG_STARTD8_MCP_SERVICE"; fi
if [[ -n "${_ORIG_STARTD8_MCP_ENV_SET:-}" ]]; then export STARTD8_MCP_ENV="$_ORIG_STARTD8_MCP_ENV"; fi
if [[ -n "${_ORIG_STARTD8_MCP_VERSION_SET:-}" ]]; then export STARTD8_MCP_VERSION="$_ORIG_STARTD8_MCP_VERSION"; fi

# -----------------------------------------------------------------------------
# Python selection (prefer local venv)
# -----------------------------------------------------------------------------
PYTHON_BIN="${STARTD8_MCP_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "[startd8-mcp] ERROR: python not found (need python3)" >&2
    exit 127
  fi
fi

# -----------------------------------------------------------------------------
# Environment normalization
# -----------------------------------------------------------------------------
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

# If STARTD8_SDK_PATH is set, ensure it participates in module resolution.
if [[ -n "${STARTD8_SDK_PATH:-}" ]]; then
  export PYTHONPATH="${STARTD8_SDK_PATH}${PYTHONPATH:+:$PYTHONPATH}"
fi

# Provide a stable project root to the server (can be overridden in env).
export PROJECT_ROOT="${PROJECT_ROOT:-$ROOT_DIR}"

# -----------------------------------------------------------------------------
# MCP stdio safety defaults / checks
# -----------------------------------------------------------------------------
# MCP stdio uses stdout for JSON-RPC. If stderr is merged into stdout (e.g. `2>&1`)
# the JSON stream is corrupted and clients like Cursor/Inspector will fail.
#
# Heuristic: when running under an MCP client, stdin is a pipe (not a TTY).
if [[ ! -t 0 ]]; then
  # Quiet by default when driven by an MCP client (can be overridden).
  export STARTD8_MCP_QUIET="${STARTD8_MCP_QUIET:-1}"
  # Persist structured JSONL events for debugging outside the client UI (optional).
  export STARTD8_MCP_EVENT_LOG_FILE="${STARTD8_MCP_EVENT_LOG_FILE:-$PROJECT_ROOT/logs/mcp-events.jsonl}"
fi

# Explicit defaults (used by the Python server)
export STARTD8_MCP_DEBUG="${STARTD8_MCP_DEBUG:-0}"
export STARTD8_MCP_REGISTER_SKILL_TOOLS="${STARTD8_MCP_REGISTER_SKILL_TOOLS:-1}"
export STARTD8_MCP_MAX_SKILL_TOOLS="${STARTD8_MCP_MAX_SKILL_TOOLS:-100}"
export STARTD8_MCP_STARTUP_MAX_SKILLS="${STARTD8_MCP_STARTUP_MAX_SKILLS:-$STARTD8_MCP_MAX_SKILL_TOOLS}"
export STARTD8_MCP_SKILL_CACHE_TTL_SECONDS="${STARTD8_MCP_SKILL_CACHE_TTL_SECONDS:-10}"

# Enforce clean stdout whenever stdin is not a TTY (i.e. MCP client mode).
# Disable by setting STARTD8_MCP_ENFORCE_CLEAN_STDOUT=0.
if [[ "${STARTD8_MCP_ENFORCE_CLEAN_STDOUT:-1}" == "1" && ! -t 0 ]]; then
  if ! "$PYTHON_BIN" -c 'import os,sys; a=os.fstat(1); b=os.fstat(2); sys.exit(0 if (a.st_dev,a.st_ino)!=(b.st_dev,b.st_ino) else 1)'; then
    echo "[startd8-mcp] ERROR: stdout and stderr are merged. MCP requires clean stdout for JSON-RPC." >&2
    echo "[startd8-mcp] Fix: remove 2>&1 / avoid piping. For logs, use STARTD8_MCP_LOG_FILE." >&2
    exit 2
  fi
fi

# -----------------------------------------------------------------------------
# Skill path defaults
# -----------------------------------------------------------------------------
# Ensure your local Claude Skills directory is discoverable by the MCP server.
# (Does not override existing STARTD8_SKILL_PATH; it appends if missing.)
DEFAULT_CLAUDE_SKILLS_DIR="/Users/neilyashinsky/Documents/tools/Anthropic/context/Claude/Skills"
if [[ -d "$DEFAULT_CLAUDE_SKILLS_DIR" ]]; then
  if [[ -z "${STARTD8_SKILL_PATH:-}" ]]; then
    export STARTD8_SKILL_PATH="$DEFAULT_CLAUDE_SKILLS_DIR"
  else
    case ":${STARTD8_SKILL_PATH}:" in
      *":${DEFAULT_CLAUDE_SKILLS_DIR}:"*)
        # already present
        ;;
      *)
        export STARTD8_SKILL_PATH="${STARTD8_SKILL_PATH}:$DEFAULT_CLAUDE_SKILLS_DIR"
        ;;
    esac
  fi
fi

# -----------------------------------------------------------------------------
# Diagnostics (stderr only; safe for MCP stdio)
# -----------------------------------------------------------------------------
if [[ "${STARTD8_MCP_QUIET:-0}" != "1" ]]; then
  {
    echo "[startd8-mcp] cwd=$ROOT_DIR"
    echo "[startd8-mcp] python=$PYTHON_BIN"
    echo "[startd8-mcp] PROJECT_ROOT=${PROJECT_ROOT}"
    echo "[startd8-mcp] STARTD8_SDK_PATH=${STARTD8_SDK_PATH:-}"
    echo "[startd8-mcp] STARTD8_SKILL_PATH=${STARTD8_SKILL_PATH:-}"
    echo "[startd8-mcp] DEFAULT_AGENT=${DEFAULT_AGENT:-}"
    echo "[startd8-mcp] ALLOWED_AGENTS=${ALLOWED_AGENTS:-}"
  } >&2
fi

# -----------------------------------------------------------------------------
# Optional log capture (stderr only; MCP-safe)
# -----------------------------------------------------------------------------
# If you want persistent logs without breaking MCP stdio, set:
#   STARTD8_MCP_LOG_FILE=/path/to/logfile.log
if [[ -n "${STARTD8_MCP_LOG_FILE:-}" ]]; then
  mkdir -p "$(dirname "$STARTD8_MCP_LOG_FILE")"
  # Tee stderr to file while keeping stderr visible.
  exec 2> >(tee -a "$STARTD8_MCP_LOG_FILE" >&2)
fi

exec "$PYTHON_BIN" -u startd8_mcp.py
