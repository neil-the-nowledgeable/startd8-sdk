#!/usr/bin/env bash
# Tier 0 — OTel Demo reference environment teardown (S8 / FR-9).
# Companion to bring_up.sh. Stops + removes the demo stack and its volumes.
#
# Usage:
#   scripts/otel_demo/teardown.sh [--tier core|observe|profile] [--keep-volumes]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKDIR="${TIER0_WORKDIR:-$REPO_ROOT/.otel-demo}"
TIER="observe"
DOWN_ARGS=(--remove-orphans -v)   # -v drops volumes by default (clean slate)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier)         TIER="${2:?}"; shift 2 ;;
    --keep-volumes) DOWN_ARGS=(--remove-orphans); shift ;;
    -h|--help)      grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERROR: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$WORKDIR/compose.yaml" ]]; then
  echo "Nothing to tear down: $WORKDIR/compose.yaml not found." >&2; exit 0
fi

declare -a WANT
case "$TIER" in
  core)    WANT=(compose.yaml) ;;
  observe) WANT=(compose.yaml compose.observability.yaml) ;;
  profile) WANT=(compose.yaml compose.observability.yaml compose.profiling.yaml) ;;
  *) echo "ERROR: --tier must be core|observe|profile" >&2; exit 2 ;;
esac

declare -a CF_ARGS=()
for f in "${WANT[@]}"; do [[ -f "$WORKDIR/$f" ]] && CF_ARGS+=(-f "$f"); done
[[ ${#CF_ARGS[@]} -gt 0 ]] || CF_ARGS=(-f compose.yaml)

echo ">> tearing down tier=$TIER (${DOWN_ARGS[*]})"
( cd "$WORKDIR" && docker compose "${CF_ARGS[@]}" down "${DOWN_ARGS[@]}" )
echo ">> done. (clone left at $WORKDIR; remove it manually to reclaim disk)"
