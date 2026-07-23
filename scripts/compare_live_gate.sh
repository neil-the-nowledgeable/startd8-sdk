#!/usr/bin/env bash
# Observability derived-vs-emitted CI gate (rung #3).
#
# Generates the pilot Mastodon o11y artifacts from the committed fixture, then replays the derived
# PromQL against a PINNED reference subject via `startd8 observability compare-live --baseline`, and
# fails only on a NEW dead SLI (a verdict-id not in the committed baseline). This catches the
# #274/#275 defect class — a generator/engine change that ships an SLI evaluating against nothing —
# before it merges.
#
# Two backends (auto-selected):
#   * PROMETHEUS_URL set  -> existing-backend path (`--prometheus $PROMETHEUS_URL`). Used locally
#                            against a running Prometheus (e.g. the OTel demo at :9090).
#   * PROMETHEUS_URL unset -> standup path: compare-live boots the pinned SUBJECT_IMAGE (default a
#                            self-scraping `prom/prometheus`) + a Prometheus. Used in CI (needs docker).
#
# Exit codes (mirrors compare-live / the CI contract):
#   0  clean  — every dead SLI is in the baseline (or all bind)
#   2  FAIL   — a NEW dead SLI shipped (the regression signal; fails the build)
#   3  UNKNOWN— standup/scrape/backend was inconclusive (infra, not a code regression)
#
# Env knobs:
#   BASELINE       baseline JSON path (default: the committed fixture baseline)
#   SUBJECT_IMAGE  pinned reference image for the standup path (default prom/prometheus:v2.53.0)
#   SUBJECT_PORT   subject /metrics port (default 9090 — Prometheus serves its own /metrics there)
#   WRITE_BASELINE =1 to (re)author the baseline instead of gating (explicit operator action)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$REPO_ROOT/docs/design/observability-compare/pilot-repro"
BASELINE="${BASELINE:-$FIXTURE/compare_live_baseline.json}"
SUBJECT_IMAGE="${SUBJECT_IMAGE:-prom/prometheus:v2.53.0}"
SUBJECT_PORT="${SUBJECT_PORT:-9090}"
PY="${PYTHON:-python3}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> generating pilot Mastodon o11y artifacts from the committed fixture"
PYTHONPATH="$REPO_ROOT/src" "$PY" - "$FIXTURE/onboarding-metadata.json" "$WORK/observability" <<'PY'
import sys
from pathlib import Path
from startd8.observability.artifact_generator import generate_observability_artifacts
generate_observability_artifacts(Path(sys.argv[1]), Path(sys.argv[2]))
PY

# Regression floor: the baseline-diff only catches NEW dead SLIs — it is blind to a generator
# regression that DROPS the fixture's SLIs entirely (zero fails ⇒ zero new fails ⇒ a false PASS).
# The pilot's metrics-emitting service (mastodonstreaming) must always yield >= EXPECT_MIN_SLOS SLO
# files; fewer means the generator stopped emitting known SLIs — a regression the diff can't see.
n_slos=$(find "$WORK/observability/slos" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
if [[ "${n_slos:-0}" -lt "${EXPECT_MIN_SLOS:-1}" ]]; then
  echo "GATE: FAIL — fixture generated ${n_slos:-0} SLO file(s) (< ${EXPECT_MIN_SLOS:-1}); the generator" \
       "dropped known SLIs (a regression the baseline-diff alone cannot detect)."
  exit 2
fi

CMD=(
  "$PY" -m startd8.cli observability compare-live
  -m "$WORK/observability/observability-manifest.yaml"
  --artifacts-dir "$WORK/observability"
  --onboarding-metadata "$FIXTURE/onboarding-metadata.json"
  --baseline "$BASELINE"
)
if [[ -n "${PROMETHEUS_URL:-}" ]]; then
  CMD+=(--prometheus "$PROMETHEUS_URL")
else
  CMD+=(--subject-image "$SUBJECT_IMAGE" --subject-port "$SUBJECT_PORT")
fi
if [[ "${WRITE_BASELINE:-}" == "1" ]]; then
  CMD+=(--write-baseline)
fi

echo "==> ${CMD[*]}"
set +e
PYTHONPATH="$REPO_ROOT/src" "${CMD[@]}"
code=$?
set -e

case "$code" in
  0) echo "GATE: PASS — no new dead SLI." ;;
  2) echo "GATE: FAIL — a NEW dead SLI shipped (verdict not in baseline). See output above." ;;
  3) echo "GATE: UNKNOWN — live replay inconclusive (infra/standup). Not treated as a code regression." ;;
  *) echo "GATE: unexpected exit $code" ;;
esac
exit "$code"
