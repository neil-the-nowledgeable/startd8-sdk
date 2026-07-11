#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# run-defense-review.sh
#
# Run the architectural-review-log workflow on the defense-in-depth
# plan and feature requirements.  Every parameter can be overridden
# from the command line:
#
#   ./run-defense-review.sh --max-cost-usd 5.00 --agents "anthropic:claude-opus-4-20250514,openai:gpt-4.1"
#   ./run-defense-review.sh --no-triage --max-suggestions 30
#   ./run-defense-review.sh --help
# ─────────────────────────────────────────────────────────────

usage() {
  cat <<USAGE
Usage: $(basename "$0") [OPTIONS]

Run the architectural-review-log workflow with configurable parameters.
All options have sensible defaults for the defense-in-depth review.

Options:
  --document-path PATH            Plan document to review
  --feature-requirements PATHS    Comma-separated feature requirement file paths
  --agents SPECS                  Comma-separated agent specs (provider:model)
  --quality-tier TIER             Model tier: flagship|balanced|fast|mini (default: flagship)
  --providers LIST                Comma-separated provider allowlist
  --reviewer-count N              Number of default reviewers (default: 2)
  --max-suggestions N             Max suggestions per round (default: 20)
  --scope TEXT                    One-sentence scope statement
  --init-if-missing               Initialize appendix structure if missing (default: true)
  --no-init-if-missing            Do not initialize appendix structure
  --state-path PATH               Path for workflow state JSON
  --warn-cost-usd N               Warn if cumulative cost exceeds N USD (default: 0.50)
  --max-cost-usd N                Fail if cumulative cost exceeds N USD (default: 2.00)
  --review-template TEXT          Prompt template override
  --context-files PATHS           Comma-separated context file/dir paths
  --max-context-chars N           Max total chars of context content (default: 200000)
  --fallback-openai-model SPEC    Fallback OpenAI model (default: openai:gpt-4.1)
  --no-fallback                   Disable fallback on model-not-found
  --gemini-safety-settings JSON   Gemini safety settings as JSON array
  --enable-triage                 Enable automated triage (default: true)
  --no-triage                     Disable automated triage
  --substantially-addressed-threshold N  Min accepted per area (default: 3)
  --dry-run                       Print the JSON config without executing
  -h, --help                      Show this help message
USAGE
  exit 0
}

# ─── Defaults ────────────────────────────────────────────────
DOCUMENT_PATH="/Users/neilyashinsky/Documents/dev/ContextCore/docs/plans/implementation-plan-defense-in-depth.md"
FEATURE_REQUIREMENTS="/Users/neilyashinsky/Documents/dev/ContextCore/docs/plans/feature-enhancement-defense-in-depth.md"
AGENTS="anthropic:claude-opus-4-20250514"
QUALITY_TIER=""
PROVIDERS=""
REVIEWER_COUNT=""
MAX_SUGGESTIONS=20
SCOPE="Requirements traceability and architecture review — dual-document gap-hunting mode"
INIT_IF_MISSING=true
STATE_PATH=""
WARN_COST_USD=0.50
MAX_COST_USD=2.00
REVIEW_TEMPLATE=""
CONTEXT_FILES="/Users/neilyashinsky/Documents/dev/ContextCore/contextcore_governance_docs/SECURITY_AND_RBAC.md,/Users/neilyashinsky/Documents/dev/ContextCore/docs/reference-architecture-contextcore.md,/Users/neilyashinsky/Documents/dev/ContextCore/docs/OPERATIONAL_RESILIENCE.md,/Users/neilyashinsky/Documents/dev/ContextCore/docs/OPERATIONAL_RUNBOOK.md,/Users/neilyashinsky/Documents/dev/ContextCore/docs/OTEL_CONVENTIONS_AUDIT.md,/Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/Design_Docs_LESSONS_LEARNED.md"
MAX_CONTEXT_CHARS=200000
FALLBACK_OPENAI_MODEL=""
FALLBACK_ON_MODEL_NOT_FOUND=""
GEMINI_SAFETY_SETTINGS=""
ENABLE_TRIAGE=true
SUBSTANTIALLY_ADDRESSED_THRESHOLD=5
DRY_RUN=false

# ─── Parse arguments ─────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --document-path)          DOCUMENT_PATH="$2"; shift 2 ;;
    --feature-requirements)   FEATURE_REQUIREMENTS="$2"; shift 2 ;;
    --agents)                 AGENTS="$2"; shift 2 ;;
    --quality-tier)           QUALITY_TIER="$2"; shift 2 ;;
    --providers)              PROVIDERS="$2"; shift 2 ;;
    --reviewer-count)         REVIEWER_COUNT="$2"; shift 2 ;;
    --max-suggestions)        MAX_SUGGESTIONS="$2"; shift 2 ;;
    --scope)                  SCOPE="$2"; shift 2 ;;
    --init-if-missing)        INIT_IF_MISSING=true; shift ;;
    --no-init-if-missing)     INIT_IF_MISSING=false; shift ;;
    --state-path)             STATE_PATH="$2"; shift 2 ;;
    --warn-cost-usd)          WARN_COST_USD="$2"; shift 2 ;;
    --max-cost-usd)           MAX_COST_USD="$2"; shift 2 ;;
    --review-template)        REVIEW_TEMPLATE="$2"; shift 2 ;;
    --context-files)          CONTEXT_FILES="$2"; shift 2 ;;
    --max-context-chars)      MAX_CONTEXT_CHARS="$2"; shift 2 ;;
    --fallback-openai-model)  FALLBACK_OPENAI_MODEL="$2"; shift 2 ;;
    --no-fallback)            FALLBACK_ON_MODEL_NOT_FOUND=false; shift ;;
    --gemini-safety-settings) GEMINI_SAFETY_SETTINGS="$2"; shift 2 ;;
    --enable-triage)          ENABLE_TRIAGE=true; shift ;;
    --no-triage)              ENABLE_TRIAGE=false; shift ;;
    --substantially-addressed-threshold) SUBSTANTIALLY_ADDRESSED_THRESHOLD="$2"; shift 2 ;;
    --dry-run)                DRY_RUN=true; shift ;;
    -h|--help)                usage ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Run with --help for usage." >&2
      exit 1
      ;;
  esac
done

# ─── Build JSON config ───────────────────────────────────────
# Helper: convert comma-separated string to JSON array of strings
csv_to_json_array() {
  local input="$1"
  if [[ -z "$input" ]]; then
    echo "[]"
    return
  fi
  local first=true
  echo -n "["
  IFS=',' read -ra items <<< "$input"
  for item in "${items[@]}"; do
    item="$(echo "$item" | xargs)"  # trim whitespace
    if $first; then
      first=false
    else
      echo -n ", "
    fi
    echo -n "\"$item\""
  done
  echo -n "]"
}

AGENTS_JSON=$(csv_to_json_array "$AGENTS")
FEATURE_REQ_JSON=$(csv_to_json_array "$FEATURE_REQUIREMENTS")
CONTEXT_FILES_JSON=$(csv_to_json_array "$CONTEXT_FILES")

# Start building the config object
CONFIG="{"
CONFIG+="\"document_path\": \"$DOCUMENT_PATH\""
CONFIG+=", \"agents\": $AGENTS_JSON"
CONFIG+=", \"max_suggestions\": $MAX_SUGGESTIONS"
CONFIG+=", \"scope\": \"$SCOPE\""
CONFIG+=", \"init_if_missing\": $INIT_IF_MISSING"
CONFIG+=", \"enable_triage\": $ENABLE_TRIAGE"
CONFIG+=", \"substantially_addressed_threshold\": $SUBSTANTIALLY_ADDRESSED_THRESHOLD"
CONFIG+=", \"max_context_chars\": $MAX_CONTEXT_CHARS"

# Feature requirements (only if non-empty)
if [[ -n "$FEATURE_REQUIREMENTS" ]]; then
  CONFIG+=", \"feature_requirements\": $FEATURE_REQ_JSON"
fi

# Context files (only if non-empty)
if [[ -n "$CONTEXT_FILES" ]]; then
  CONFIG+=", \"context_files\": $CONTEXT_FILES_JSON"
fi

# Cost guardrails
if [[ -n "$WARN_COST_USD" ]]; then
  CONFIG+=", \"warn_cost_usd\": $WARN_COST_USD"
fi
if [[ -n "$MAX_COST_USD" ]]; then
  CONFIG+=", \"max_cost_usd\": $MAX_COST_USD"
fi

# Optional fields — only include when explicitly set
if [[ -n "$QUALITY_TIER" ]]; then
  CONFIG+=", \"quality_tier\": \"$QUALITY_TIER\""
fi
if [[ -n "$PROVIDERS" ]]; then
  PROVIDERS_JSON=$(csv_to_json_array "$PROVIDERS")
  CONFIG+=", \"providers\": $PROVIDERS_JSON"
fi
if [[ -n "$REVIEWER_COUNT" ]]; then
  CONFIG+=", \"reviewer_count\": $REVIEWER_COUNT"
fi
if [[ -n "$STATE_PATH" ]]; then
  CONFIG+=", \"state_path\": \"$STATE_PATH\""
fi
if [[ -n "$REVIEW_TEMPLATE" ]]; then
  # Escape double quotes in template
  ESCAPED_TEMPLATE="${REVIEW_TEMPLATE//\"/\\\"}"
  CONFIG+=", \"review_template\": \"$ESCAPED_TEMPLATE\""
fi
if [[ -n "$FALLBACK_OPENAI_MODEL" ]]; then
  CONFIG+=", \"fallback_openai_model\": \"$FALLBACK_OPENAI_MODEL\""
fi
if [[ -n "$FALLBACK_ON_MODEL_NOT_FOUND" ]]; then
  CONFIG+=", \"fallback_on_model_not_found\": $FALLBACK_ON_MODEL_NOT_FOUND"
fi
if [[ -n "$GEMINI_SAFETY_SETTINGS" ]]; then
  CONFIG+=", \"gemini_safety_settings\": $GEMINI_SAFETY_SETTINGS"
fi

CONFIG+="}"

# ─── Execute ─────────────────────────────────────────────────
cd /Users/neilyashinsky/Documents/dev/startd8-sdk
source .venv/bin/activate

if $DRY_RUN; then
  echo "Config JSON (dry run):"
  echo "$CONFIG" | python3 -m json.tool
  exit 0
fi

echo "$CONFIG" | startd8 workflow run architectural-review-log -c /dev/stdin
