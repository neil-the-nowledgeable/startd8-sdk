#!/usr/bin/env bash
# clear_artisan_cache.sh — Delete artisan workflow cache (checkpoints, resume state, staging, task errors)
#
# Usage:
#   ./scripts/clear_artisan_cache.sh          # interactive (prompts before delete)
#   ./scripts/clear_artisan_cache.sh --force   # no prompts
#   ./scripts/clear_artisan_cache.sh --dry-run  # show what would be deleted

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FORCE=false
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --force|-f) FORCE=true ;;
    --dry-run|-n) DRY_RUN=true ;;
    --help|-h)
      echo "Usage: $0 [--force|-f] [--dry-run|-n]"
      echo ""
      echo "Clears artisan workflow cache so the next run starts fresh."
      echo ""
      echo "Locations cleared:"
      echo "  .startd8/checkpoints/          Per-workflow checkpoint files"
      echo "  .startd8/state/                Resume cache (generation/test/review results)"
      echo "  .startd8/staging/              Staged files from IMPLEMENT phase"
      echo "  .startd8/task_errors/          Per-task error snapshots"
      echo "  .cap-dev-pipe/**/checkpoints/  Pipeline checkpoint files"
      echo ""
      echo "Options:"
      echo "  --force, -f    Skip confirmation prompt"
      echo "  --dry-run, -n  Show what would be deleted without deleting"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (use --help for usage)"
      exit 1
      ;;
  esac
done

# ── Gather cache locations ──────────────────────────────────────────

declare -a TARGETS=()
declare -a DESCRIPTIONS=()
total_files=0
total_bytes=0

count_dir() {
  local dir="$1"
  local desc="$2"
  if [[ -d "$dir" ]]; then
    local count
    count=$(find "$dir" -type f 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$count" -gt 0 ]]; then
      local bytes
      bytes=$(find "$dir" -type f -exec stat -f%z {} + 2>/dev/null | awk '{s+=$1} END {print s+0}')
      TARGETS+=("$dir")
      DESCRIPTIONS+=("$desc: $count files ($(numfmt_bytes "$bytes"))")
      total_files=$((total_files + count))
      total_bytes=$((total_bytes + bytes))
    fi
  fi
}

numfmt_bytes() {
  local bytes=$1
  if [[ $bytes -ge 1048576 ]]; then
    echo "$(( bytes / 1048576 )) MB"
  elif [[ $bytes -ge 1024 ]]; then
    echo "$(( bytes / 1024 )) KB"
  else
    echo "${bytes} B"
  fi
}

# Pipeline checkpoints (may have multiple pipeline-output subdirs)
count_pipeline_checkpoints() {
  local cap_dev="$PROJECT_ROOT/.cap-dev-pipe/pipeline-output"
  if [[ -d "$cap_dev" ]]; then
    while IFS= read -r -d '' cpdir; do
      local relpath="${cpdir#"$PROJECT_ROOT"/}"
      count_dir "$cpdir" "$relpath"
    done < <(find "$cap_dev" -type d -name checkpoints -print0 2>/dev/null)
  fi
}

count_dir "$PROJECT_ROOT/.startd8/checkpoints"    "Workflow checkpoints"
count_dir "$PROJECT_ROOT/.startd8/state"           "Resume cache (generation/test/review)"
count_dir "$PROJECT_ROOT/.startd8/staging"         "Staged implementation files"
count_dir "$PROJECT_ROOT/.startd8/task_errors"     "Task error snapshots"
count_pipeline_checkpoints

# ── Report ──────────────────────────────────────────────────────────

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "Nothing to clear — artisan cache is already empty."
  exit 0
fi

echo "Artisan workflow cache:"
echo ""
for i in "${!DESCRIPTIONS[@]}"; do
  echo "  ${DESCRIPTIONS[$i]}"
done
echo ""
echo "Total: $total_files files ($(numfmt_bytes "$total_bytes"))"
echo ""

if $DRY_RUN; then
  echo "(dry run — nothing deleted)"
  exit 0
fi

# ── Confirm ─────────────────────────────────────────────────────────

if ! $FORCE; then
  read -rp "Delete all artisan cache? [y/N] " confirm
  if [[ ! "$confirm" =~ ^[yY]$ ]]; then
    echo "Aborted."
    exit 0
  fi
fi

# ── Delete ──────────────────────────────────────────────────────────

for dir in "${TARGETS[@]}"; do
  find "$dir" -type f -delete 2>/dev/null
  # Remove empty subdirectories but keep the parent
  find "$dir" -mindepth 1 -type d -empty -delete 2>/dev/null
done

echo "Cleared $total_files cached files."
