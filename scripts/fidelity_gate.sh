#!/usr/bin/env bash
# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# CI fidelity gate: replay generated observability PromQL against a live Prometheus
# and gate the build on the result. A thin, portable wrapper over
# `startd8 observability validate-promql` that turns its three exit codes into a
# CI-friendly pass/fail with a configurable policy for "unknown".
#
# Runs identically in CI and locally. Credentials come from the environment only
# (PROMETHEUS_BEARER_TOKEN / PROMETHEUS_ORG_ID) — never flags — and are redacted by
# the underlying command.
#
# Exit-code policy (validate-promql → this gate):
#   0 pass    → 0 (build passes)
#   2 fail    → 1 (build fails: coverage below --min-coverage)
#   3 unknown → 1 by default (backend unreachable / zero queries replayed);
#               set FAIL_ON_UNKNOWN=false to treat unknown as a non-blocking warning.
#
# Usage (env-driven so it drops cleanly into any CI):
#   ARTIFACTS_DIR=out/observability \
#   ONBOARDING_METADATA=out/onboarding-metadata.json \
#   PROMETHEUS_URL=http://prometheus:9090 \
#   MIN_COVERAGE=0.9 \
#   scripts/fidelity_gate.sh
#
# Optional env:
#   ALLOW_PROD=true        # opt in to a non-demo/non-localhost backend
#   FAIL_ON_UNKNOWN=false  # let exit-3 (unknown) pass with a warning
#   REPORT=fidelity-report.json  # where to write the JSON report (default)

set -uo pipefail

ARTIFACTS_DIR="${ARTIFACTS_DIR:?set ARTIFACTS_DIR to the generated observability dir}"
ONBOARDING_METADATA="${ONBOARDING_METADATA:?set ONBOARDING_METADATA to onboarding-metadata.json}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
MIN_COVERAGE="${MIN_COVERAGE:-1.0}"
ALLOW_PROD="${ALLOW_PROD:-false}"
FAIL_ON_UNKNOWN="${FAIL_ON_UNKNOWN:-true}"
# FR-5a: fail a binding-pass run where the backend returned NO live data at all
# (every query binds but data_coverage is 0) — "correct queries, silent backend".
FAIL_ON_NO_DATA="${FAIL_ON_NO_DATA:-false}"
REPORT="${REPORT:-fidelity-report.json}"

args=(
  observability validate-promql
  --artifacts-dir "$ARTIFACTS_DIR"
  --onboarding-metadata "$ONBOARDING_METADATA"
  --prometheus "$PROMETHEUS_URL"
  --min-coverage "$MIN_COVERAGE"
  --report "$REPORT"
)
if [ "$ALLOW_PROD" = "true" ]; then
  args+=(--allow-prod)
fi

echo "▶ fidelity gate: replaying $ARTIFACTS_DIR against $PROMETHEUS_URL (min-coverage=$MIN_COVERAGE)"
startd8 "${args[@]}"
code=$?

case "$code" in
  0)
    # FR-5a no-silent-green: a binding pass with zero live data is not truly healthy.
    if [ "$FAIL_ON_NO_DATA" = "true" ] && [ -f "$REPORT" ]; then
      data_cov=$(python3 -c "import json;print(json.load(open('$REPORT')).get('data_coverage',1))" 2>/dev/null || echo 1)
      if [ "$data_cov" = "0.0" ] || [ "$data_cov" = "0" ]; then
        echo "✗ fidelity gate: queries BIND but data_coverage is 0 — backend emitted no live"
        echo "  data in-window (idle load / stale). Failing (FAIL_ON_NO_DATA=true)."
        exit 1
      fi
    fi
    echo "✓ fidelity gate PASS (binding_coverage ≥ $MIN_COVERAGE)"
    exit 0
    ;;
  2)
    echo "✗ fidelity gate FAIL: generated PromQL does not bind to live data below the coverage floor."
    echo "  See $REPORT — 'suggested_metrics_profile' names the one-line fix, per-verdict 'remediation' the rest."
    exit 1
    ;;
  3)
    if [ "$FAIL_ON_UNKNOWN" = "true" ]; then
      echo "✗ fidelity gate UNKNOWN (backend unreachable or zero queries replayed) — failing (FAIL_ON_UNKNOWN=true)."
      echo "  Set FAIL_ON_UNKNOWN=false to treat this as a non-blocking warning."
      exit 1
    fi
    echo "⚠ fidelity gate UNKNOWN (backend unreachable or zero queries replayed) — not blocking (FAIL_ON_UNKNOWN=false)."
    exit 0
    ;;
  *)
    echo "✗ fidelity gate: unexpected exit code $code from validate-promql."
    exit 1
    ;;
esac
