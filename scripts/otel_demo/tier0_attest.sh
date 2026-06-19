#!/usr/bin/env bash
# Tier 0 — S8 one-shot attestation pipeline (probe → attest → verify → startup capture).
#
# Requires a live OTel Demo bring-up (scripts/otel_demo/bring_up.sh).
# Exit codes follow verify_coverage.py (0 pass, 1 fail, 2 infra/schema).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="$REPO_ROOT/docs/design/otel-demo-corpus"
TIER="${TIER:-observe}"
JAEGER="${JAEGER:-http://localhost:16686}"
PROM="${PROM:-http://localhost:9090}"
PYRO="${PYRO:-http://localhost:4040}"
WORKDIR="${TIER0_WORKDIR:-$REPO_ROOT/.otel-demo}"

echo ">> Tier 0 attest  tier=$TIER  workdir=$WORKDIR"

echo ">> S5.5 API-shape probe (blocking gate)"
python3 "$REPO_ROOT/scripts/otel_demo/probe_api_shapes.py" \
  --jaeger "$JAEGER" --prometheus "$PROM" \
  --out "$OUT_DIR/api-shape-decision.json"

echo ">> S5 coverage attestation"
python3 "$REPO_ROOT/scripts/otel_demo/attest_coverage.py" \
  --tier "$TIER" --workdir "$WORKDIR" \
  --jaeger "$JAEGER" --prometheus "$PROM" --pyroscope "$PYRO" \
  --out "$OUT_DIR/coverage-attestation.json"

echo ">> S6 verify (live re-check + freshness)"
python3 "$REPO_ROOT/scripts/otel_demo/verify_coverage.py" \
  "$OUT_DIR/coverage-attestation.json" \
  --workdir "$WORKDIR"

echo ">> S7 startup capture (Tier 1 input)"
python3 "$REPO_ROOT/scripts/otel_demo/capture_startup.py" \
  --workdir "$WORKDIR" \
  --out "$OUT_DIR/startup-capture.json"

echo ">> Tier 0 attest complete — artifacts in $OUT_DIR"
