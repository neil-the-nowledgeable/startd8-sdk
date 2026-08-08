#!/usr/bin/env bash
#
# check_contextcore_parity.sh — the homebrew of CEP CH-2 (a local runner instead of a CI lane).
#
# The cross-repo vocabulary-parity guards (tests/unit/observability/test_vocabulary_parity_*.py) check
# that startd8's hand-copied mirror sets + the committed ContextCore vocabulary snapshot have NOT drifted
# from ContextCore's normative enums. Most of those guards open with
# `pytest.importorskip("contextcore.contracts.types")`, so they SKIP in normal SDK CI (ContextCore is an
# optional dependency, absent from the SDK venv). This script is how you actually FIRE them: point it at
# a ContextCore checkout and it runs the guards + the snapshot-freshness check with ContextCore present,
# so nothing skips.
#
# Usage:
#   scripts/check_contextcore_parity.sh [path/to/ContextCore/src] [extra pytest args...]
#   CONTEXTCORE_SRC=/path/to/ContextCore/src scripts/check_contextcore_parity.sh
#
# Exit 0 = startd8 mirrors + snapshot are in sync with ContextCore.
# Exit non-0 = drift (reconcile the mirror, or refresh the snapshot per its _provenance); the failing
#              test output shows exactly what drifted.
#
set -euo pipefail

# --- resolve the SDK repo root (dir above scripts/) ---
SDK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- resolve ContextCore src: first arg (if it points at a ContextCore checkout) > env > common spots ---
CC_SRC="${CONTEXTCORE_SRC:-}"
if [ -n "${1:-}" ] && [ -f "$1/contextcore/contracts/types.py" ]; then
  CC_SRC="$1"; shift
fi
if [ -z "$CC_SRC" ]; then
  for cand in "$HOME/Documents/dev/ContextCore/src" "$SDK_ROOT/../ContextCore/src"; do
    if [ -f "$cand/contextcore/contracts/types.py" ]; then CC_SRC="$cand"; break; fi
  done
fi
if [ -z "$CC_SRC" ] || [ ! -f "$CC_SRC/contextcore/contracts/types.py" ]; then
  echo "❌ ContextCore not found (looked for contextcore/contracts/types.py)."
  echo "   Pass its src dir:  scripts/check_contextcore_parity.sh <path/to/ContextCore/src>"
  echo "   or set CONTEXTCORE_SRC=<path>."
  exit 2
fi

# --- pick the SDK venv python if present ---
PY="$SDK_ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python3"

CC_COMMIT="$(git -C "$(dirname "$CC_SRC")" rev-parse --short HEAD 2>/dev/null || echo '?')"
echo "SDK:        $SDK_ROOT"
echo "ContextCore: $CC_SRC (commit $CC_COMMIT)"
echo "Running cross-repo parity + snapshot-freshness guards (ContextCore present → nothing skips)…"
echo

set +e
PYTHONPATH="$SDK_ROOT/src:$CC_SRC" "$PY" -m pytest \
  "$SDK_ROOT/tests/unit/observability/test_vocabulary_parity_offline.py" \
  "$SDK_ROOT/tests/unit/observability/test_vocabulary_parity_contextcore.py" \
  -q -p no:cacheprovider "$@"
rc=$?
set -e

echo
if [ "$rc" -ne 0 ]; then
  echo "❌ DRIFT — startd8's mirror sets or the committed snapshot are out of sync with ContextCore ($CC_COMMIT)."
  echo "   Fix one of:"
  echo "     • reconcile the mirror in metric_descriptor.py / artifact_generator*.py, OR"
  echo "     • refresh tests/unit/observability/data/contextcore_vocab_snapshot.json (see its _provenance), then re-run."
  exit "$rc"
fi
echo "✅ In sync — startd8 mirrors + the committed vocabulary snapshot match ContextCore ($CC_COMMIT)."
