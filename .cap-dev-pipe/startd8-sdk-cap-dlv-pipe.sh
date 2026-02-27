#!/usr/bin/env bash
# ============================================================================
# startd8-sdk — Capability Delivery Pipeline Entry Point
#
# Project-specific wrapper that delegates to the shared run.sh.
#
# Two modes:
#   --folder <path>  Auto-discover plan/reqs from a design folder, create a
#                    language profile with symlinks, then delegate to run.sh.
#   (no --folder)    Legacy mode — inject --lang context-bridge and delegate.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Folder discovery ────────────────────────────────────────────────────────
# Given a folder path, find exactly one *_PLAN.md and one *_REQUIREMENTS.md.
# Sets RESOLVED_PLAN and RESOLVED_REQS on success; exits on error.
resolve_folder() {
    local folder="$1"

    # Resolve to absolute path
    if [[ ! "$folder" = /* ]]; then
        folder="$(cd "$SCRIPT_DIR" && cd "$folder" && pwd)"
    fi

    if [[ ! -d "$folder" ]]; then
        echo "ERROR: --folder path does not exist: $folder" >&2
        exit 1
    fi

    # Discover plan files
    local -a plans=()
    while IFS= read -r -d '' f; do
        plans+=("$f")
    done < <(find "$folder" -maxdepth 1 -name '*_PLAN.md' -print0 2>/dev/null)

    if [[ ${#plans[@]} -eq 0 ]]; then
        echo "ERROR: No *_PLAN.md found in $folder" >&2
        exit 1
    elif [[ ${#plans[@]} -gt 1 ]]; then
        echo "ERROR: Multiple *_PLAN.md files found in $folder:" >&2
        printf '  %s\n' "${plans[@]}" >&2
        exit 1
    fi

    # Discover requirements files
    local -a reqs=()
    while IFS= read -r -d '' f; do
        reqs+=("$f")
    done < <(find "$folder" -maxdepth 1 -name '*_REQUIREMENTS.md' -print0 2>/dev/null)

    if [[ ${#reqs[@]} -eq 0 ]]; then
        echo "ERROR: No *_REQUIREMENTS.md found in $folder" >&2
        exit 1
    elif [[ ${#reqs[@]} -gt 1 ]]; then
        echo "ERROR: Multiple *_REQUIREMENTS.md files found in $folder:" >&2
        printf '  %s\n' "${reqs[@]}" >&2
        exit 1
    fi

    RESOLVED_PLAN="${plans[0]}"
    RESOLVED_REQS="${reqs[0]}"
    RESOLVED_FOLDER="$folder"
}

# ── Profile setup ───────────────────────────────────────────────────────────
# Create a language profile directory with symlinks to the discovered files.
# run.sh expects <lang>-plan.md and <lang>-requirements.md in .cap-dev-pipe/<lang>/
setup_profile() {
    local lang="$1"
    local plan="$2"
    local reqs="$3"
    local profile_dir="$SCRIPT_DIR/$lang"

    mkdir -p "$profile_dir"

    # Create/update symlinks (force to handle re-runs)
    ln -sf "$plan" "$profile_dir/${lang}-plan.md"
    ln -sf "$reqs" "$profile_dir/${lang}-requirements.md"
}

# ── Argument parsing ────────────────────────────────────────────────────────
FOLDER_PATH=""
PASSTHROUGH_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --folder)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --folder requires a path argument" >&2
                exit 1
            fi
            FOLDER_PATH="$2"
            shift 2
            ;;
        *)
            PASSTHROUGH_ARGS+=("$1")
            shift
            ;;
    esac
done

# ── List-langs short-circuit ────────────────────────────────────────────────
if [[ " ${PASSTHROUGH_ARGS[*]:-} " =~ " --list-langs " ]]; then
    exec "$SCRIPT_DIR/run.sh" "${PASSTHROUGH_ARGS[@]}"
fi

# ── Mode dispatch ───────────────────────────────────────────────────────────
if [[ -n "$FOLDER_PATH" ]]; then
    # ── Folder mode ─────────────────────────────────────────────────────
    resolve_folder "$FOLDER_PATH"

    LANG_NAME="$(basename "$RESOLVED_FOLDER")"
    setup_profile "$LANG_NAME" "$RESOLVED_PLAN" "$RESOLVED_REQS"

    # Inject --lang unless caller already specified one
    if [[ ! " ${PASSTHROUGH_ARGS[*]:-} " =~ " --lang " ]]; then
        PASSTHROUGH_ARGS=(--lang "$LANG_NAME" "${PASSTHROUGH_ARGS[@]}")
    fi

    # REQ-CDP-015: Execution chain observability — folder mode banner
    echo ""
    echo ""
    echo ""
    echo ""
    echo ""
    echo "    ┌─────────────────────────────────────────────────────────────────┐"
    echo "    │  EXECUTION DETAIL — Project Wrapper (folder mode)              │"
    echo "    ├─────────────────────────────────────────────────────────────────┤"
    echo "    │                                                                 │"
    echo "    │  Component:  startd8-sdk-cap-dlv-pipe.sh                       │"
    echo "    │  Role:       Auto-discover plan/reqs from design folder         │"
    echo "    │  Folder:     $(printf '%-40s' "$FOLDER_PATH")│"
    echo "    │  Plan:       $(printf '%-40s' "$(basename "$RESOLVED_PLAN")")│"
    echo "    │  Reqs:       $(printf '%-40s' "$(basename "$RESOLVED_REQS")")│"
    echo "    │  Profile:    .cap-dev-pipe/$LANG_NAME/                          │"
    echo "    │  Delegates:  run.sh --lang $LANG_NAME$(printf '%*s' $((29 - ${#LANG_NAME})) '')│"
    echo "    │  Chain:      [1/7] WRAPPER → run.sh → run-atomic.sh → ...      │"
    echo "    │  Reqs:       REQ-CDP-013, REQ-CDP-014                          │"
    echo "    │                                                                 │"
    echo "    └─────────────────────────────────────────────────────────────────┘"
    echo ""
    echo ""
    echo ""
    echo ""
    echo ""
else
    # ── Legacy mode ─────────────────────────────────────────────────────
    # Inject default --lang if caller didn't specify one
    if [[ ! " ${PASSTHROUGH_ARGS[*]:-} " =~ " --lang " ]]; then
        PASSTHROUGH_ARGS=(--lang "context-bridge" "${PASSTHROUGH_ARGS[@]}")
    fi

    # REQ-CDP-015: Execution chain observability
    echo ""
    echo ""
    echo ""
    echo ""
    echo ""
    echo "    ┌─────────────────────────────────────────────────────────────────┐"
    echo "    │  EXECUTION DETAIL — Project Wrapper                            │"
    echo "    ├─────────────────────────────────────────────────────────────────┤"
    echo "    │                                                                 │"
    echo "    │  Component:  startd8-sdk-cap-dlv-pipe.sh                       │"
    echo "    │  Role:       Project-specific pipeline entry point              │"
    echo "    │  Why:        Provides project identity and default language     │"
    echo "    │              profile so operators don't need to remember        │"
    echo "    │              --lang for every invocation.                       │"
    echo "    │  Default:    --lang context-bridge                              │"
    echo "    │  Delegates:  run.sh (shared language profile discovery)         │"
    echo "    │  Chain:      [1/7] WRAPPER → run.sh → run-atomic.sh → ...      │"
    echo "    │  Reqs:       REQ-CDP-013, REQ-CDP-014                          │"
    echo "    │                                                                 │"
    echo "    └─────────────────────────────────────────────────────────────────┘"
    echo ""
    echo ""
    echo ""
    echo ""
    echo ""
fi

exec "$SCRIPT_DIR/run.sh" "${PASSTHROUGH_ARGS[@]}"
