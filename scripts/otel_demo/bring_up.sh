#!/usr/bin/env bash
# Tier 0 — OTel Demo reference environment bring-up (S1/S2).
#
# Implements FR-1 (pinned, one-command bring-up), FR-2 (tiered profiles), FR-3 (shipped-stack
# default), FR-8 (determinism/attribution: record ref + image digests), FR-9 (footprint/teardown).
# See docs/design/otel-demo-corpus/TIER0_REFERENCE_ENV_REQUIREMENTS.md.
#
# The OTel Demo is *referenced* (cloned at a pinned tag), never vendored into this repo.
# Default backend is the demo's OWN shipped stack (Jaeger/Prometheus/Grafana/OpenSearch/Pyroscope) —
# no StartD8 Tempo/Wayfinder/Loki dependency (FR-3).
#
# Usage:
#   scripts/otel_demo/bring_up.sh [--tier core|observe|profile] [--ref vX.Y.Z] [--no-clone]
#   OTEL_DEMO_REF=v2.2.0 TIER0_WORKDIR=.otel-demo scripts/otel_demo/bring_up.sh --tier observe
#
# Tiers (FR-2):
#   core     compose.yaml                          — service mesh + demo Collector (lightest)
#   observe  + compose.observability.yaml          — Jaeger + Prometheus + Grafana + OpenSearch (default)
#   profile  + compose.profiling.yaml              — Pyroscope (Profiles signal)
set -euo pipefail

# --- locate repo root (script lives in scripts/otel_demo/) ---
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# --- config (overridable via env) ---
DEMO_REPO="${OTEL_DEMO_REPO:-https://github.com/open-telemetry/opentelemetry-demo.git}"
DEMO_REF="${OTEL_DEMO_REF:-v2.2.0}"                       # pinned release (FR-1/FR-8) — user-facing
GIT_REF="${DEMO_REF#v}"                                    # upstream tag is 2.2.0 (no v prefix)
WORKDIR="${TIER0_WORKDIR:-$REPO_ROOT/.otel-demo}"          # gitignored referenced clone
OUT_DIR="$REPO_ROOT/docs/design/otel-demo-corpus"
TIER="observe"
DO_CLONE=1

# --- args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier)     TIER="${2:?--tier needs a value}"; shift 2 ;;
    --ref)      DEMO_REF="${2:?--ref needs a value}"; shift 2 ;;
    --no-clone) DO_CLONE=0; shift ;;
    -h|--help)  grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERROR: unknown arg: $1" >&2; exit 2 ;;
  esac
done

case "$TIER" in core|observe|profile) ;; *)
  echo "ERROR: --tier must be core|observe|profile (got '$TIER')" >&2; exit 2 ;;
esac

# --- preflight: docker + compose v2 ---
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found on PATH." >&2; exit 2
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: 'docker compose' (v2) not available." >&2; exit 2
fi

# --- clone/checkout the pinned demo (FR-1: referenced, not vendored) ---
if [[ "$DO_CLONE" -eq 1 ]]; then
  if [[ -d "$WORKDIR/.git" ]]; then
    echo ">> reusing existing clone at $WORKDIR (fetching $GIT_REF)"
    git -C "$WORKDIR" fetch --depth 1 origin "refs/tags/$GIT_REF:refs/tags/$GIT_REF" 2>/dev/null \
      || git -C "$WORKDIR" fetch --depth 1 origin "$GIT_REF"
    git -C "$WORKDIR" checkout -q "$GIT_REF"
  else
    echo ">> cloning $DEMO_REPO @ $DEMO_REF ($GIT_REF) -> $WORKDIR"
    git clone --depth 1 --branch "$GIT_REF" "$DEMO_REPO" "$WORKDIR"
  fi
else
  echo ">> --no-clone: using existing $WORKDIR as-is"
fi

if [[ ! -f "$WORKDIR/compose.yaml" ]]; then
  echo "ERROR: $WORKDIR/compose.yaml not found — is the clone valid for $DEMO_REF?" >&2; exit 2
fi

# --- map tier -> compose files, then filter to those that actually exist (FR-2, robust to layout) ---
declare -a WANT
case "$TIER" in
  core)    WANT=(compose.yaml) ;;
  observe) WANT=(compose.yaml compose.observability.yaml) ;;
  profile) WANT=(compose.yaml compose.observability.yaml compose.profiling.yaml) ;;
esac

declare -a CF_ARGS=()
declare -a CF_USED=()
for f in "${WANT[@]}"; do
  if [[ -f "$WORKDIR/$f" ]]; then
    CF_ARGS+=(-f "$f"); CF_USED+=("$f")
  else
    echo "WARN: expected compose file '$f' not present in $DEMO_REF — skipping." \
         "(First-run layout differs from the plan; update reference-env.md.)" >&2
  fi
done
[[ ${#CF_ARGS[@]} -gt 0 ]] || { echo "ERROR: no compose files resolved for tier '$TIER'." >&2; exit 2; }

echo ">> tier=$TIER  compose files: ${CF_USED[*]}"

# --- bring up (FR-3: shipped stack) ---
( cd "$WORKDIR" && docker compose "${CF_ARGS[@]}" up -d )

# --- record bring-up manifest + image digests (FR-8 determinism/attribution) ---
mkdir -p "$OUT_DIR"
IMAGES_TXT="$OUT_DIR/bringup-images.txt"
( cd "$WORKDIR" && docker compose "${CF_ARGS[@]}" images ) >"$IMAGES_TXT" 2>/dev/null \
  || ( cd "$WORKDIR" && docker compose "${CF_ARGS[@]}" ps ) >"$IMAGES_TXT" 2>/dev/null || true

CONTAINER_COUNT="$( ( cd "$WORKDIR" && docker compose "${CF_ARGS[@]}" ps -q ) 2>/dev/null | grep -c . || echo 0 )"
GIT_SHA="$(git -C "$WORKDIR" rev-parse HEAD 2>/dev/null || echo unknown)"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# JSON via heredoc (compose-files as a JSON array)
CF_JSON="$(printf '%s\n' "${CF_USED[@]}" | sed 's/.*/"&"/' | paste -sd, -)"
cat >"$OUT_DIR/bringup-manifest.json" <<JSON
{
  "demo_ref": "$DEMO_REF",
  "git_sha": "$GIT_SHA",
  "tier": "$TIER",
  "compose_files": [$CF_JSON],
  "container_count": $CONTAINER_COUNT,
  "images_file": "bringup-images.txt",
  "generated_at": "$NOW",
  "note": "Image digests are in images_file. demo_ref+git_sha pin the environment (FR-8)."
}
JSON

echo ">> wrote $OUT_DIR/bringup-manifest.json  (containers: $CONTAINER_COUNT, ref: $DEMO_REF)"
echo ">> images recorded in $IMAGES_TXT"
cat <<EOF

Next:
  1. Confirm access (frontend-proxy default :8080; Jaeger/Prometheus per reference-env.md).
  2. Run the full attestation pipeline (or probe-only gate first):
       make tier0-attest
     Probe-only (S5.5 blocking gate):
       python3 scripts/otel_demo/probe_api_shapes.py --out "$OUT_DIR/api-shape-decision.json"
  3. Tear down when done:
       scripts/otel_demo/teardown.sh --tier $TIER
EOF
