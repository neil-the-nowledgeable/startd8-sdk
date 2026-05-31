#!/usr/bin/env bash
# Validate post-generation TODO completion (Categories A, B, C) using the REAL
# production scanner path against a generated/ output tree.
#
# Usage:
#   ./validate.sh <generated-dir>                      # a plan-ingestion/generated dir
#   ./validate.sh <run-dir>                            # …/run-NNN-…  (adds /plan-ingestion/generated)
#   ./validate.sh <pipeline-output/<project>>          # auto-picks the newest run with generated/
#
# Exercises: A (uncomment $0), B (implement -> would route to LLM), C (left alone).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_VENV="$HERE/../../.venv/bin/activate"

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
    echo "usage: $0 <generated-dir | run-dir | pipeline-output/<project>-dir>" >&2
    exit 2
fi

# Resolve the generated/ dir from whatever flavor of path was given.
if [ -d "$TARGET" ] && [ "$(basename "$TARGET")" = "generated" ]; then
    GEN="$TARGET"
elif [ -d "$TARGET/plan-ingestion/generated" ]; then
    GEN="$TARGET/plan-ingestion/generated"
else
    GEN=""
    for r in $(ls -1dt "$TARGET"/run-* 2>/dev/null); do
        if [ -d "$r/plan-ingestion/generated" ]; then
            GEN="$r/plan-ingestion/generated"
            break
        fi
    done
fi

if [ -z "${GEN:-}" ] || [ ! -d "$GEN" ]; then
    echo "No plan-ingestion/generated/ dir resolved from: $TARGET" >&2
    exit 1
fi

echo "Validating TODO completion (A/B/C) against: $GEN"
echo

# shellcheck disable=SC1090
source "$REPO_VENV" 2>/dev/null || true
set +e
python3 "$HERE/run_probe.py" "$GEN"
rc=$?
set -e

# Leave the run pristine — remove the probe we dropped in.
rm -f "$GEN/probe_module.py"
echo
echo "(probe_module.py removed from the target dir)"
exit $rc
