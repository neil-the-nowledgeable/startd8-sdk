# CI Fidelity Gate

Gate a build on whether generated observability artifacts actually **bind to live
data** — not just whether they're structurally well-formed. The gate replays every
generated PromQL against a real Prometheus and fails the build when coverage drops
below a floor, surfacing the exact one-line fix.

It is the CI form of `startd8 observability validate-promql` / `bind-and-verify`
(REQ_TARGET_METRIC_BINDING Group C). The static coverage gate
(`observability_artifact_checks.py`) is offline structural smoke — this is the
authoritative *fidelity* signal (FR-10).

## The exit-code contract

`validate-promql` returns three codes; `scripts/fidelity_gate.sh` maps them to CI:

| validate-promql | meaning | gate result |
|---|---|---|
| `0` pass | `binding_coverage` ≥ `--min-coverage`, ≥1 query replayed | build **passes** |
| `2` fail | `binding_coverage` below the floor | build **fails** |
| `3` unknown | backend unreachable / zero queries replayed | build **fails** (set `FAIL_ON_UNKNOWN=false` to warn instead) |

**Two coverage numbers (know which you're gating on).** The gate defaults to
`binding_coverage` — the fraction of queries that **bind** to the live metric surface
(`pass` + `bound_no_data`), i.e. *are the generated queries correct*. It's stable
regardless of whether the target has fresh traffic. `data_coverage` (the `pass`-only
fraction) answers the different question *is the backend emitting data right now* and
swings with traffic recency — don't gate CI on it unless that's genuinely what you want.

A query that binds but returned nothing in-window is `bound_no_data` (healthy service /
no errors / stale), not a failure. If you want an all-bound-but-silent backend to fail
the build (queries correct, nothing flowing), set `FAIL_ON_NO_DATA=true` — the gate then
fails a binding-pass whose `data_coverage` is 0.

Fidelity failures point at the fix: the report's `suggested_metrics_profile` names the
one-line `metricsProfile` change, and each verdict's `remediation` names the mismatched
axis.

## Run it locally

```bash
ARTIFACTS_DIR=out/observability \
ONBOARDING_METADATA=out/onboarding-metadata.json \
PROMETHEUS_URL=http://localhost:9090 \
MIN_COVERAGE=0.9 \
scripts/fidelity_gate.sh
```

Credentials come from the environment only (`PROMETHEUS_BEARER_TOKEN`,
`PROMETHEUS_ORG_ID`) and are redacted from all output — never pass them as flags.

## Wire it into GitHub Actions

`.github/workflows/observability-fidelity.yml` is a **reusable** (`workflow_call`)
workflow. From a consumer repo that generated artifacts and can reach a Prometheus
(staging/demo — CI runners rarely have a fresh one):

```yaml
jobs:
  fidelity:
    uses: <org>/startd8-sdk/.github/workflows/observability-fidelity.yml@main
    with:
      artifacts_dir: out/observability
      onboarding_metadata: out/onboarding-metadata.json
      prometheus_url: https://prometheus.staging.example.com
      min_coverage: "0.9"
      allow_prod: true          # non-localhost backend
      fail_on_unknown: false    # don't block if the backend is unreachable in CI
    secrets:
      prometheus_bearer_token: ${{ secrets.PROM_TOKEN }}
      prometheus_org_id: ${{ secrets.PROM_ORG_ID }}
```

The workflow uploads `fidelity-report.json` as a build artifact either way.

## Pre-commit

The live gate needs a reachable Prometheus, which pre-commit usually can't assume, so
it belongs in CI rather than a commit hook. If your dev loop has a local Prometheus,
add a **manual-stage** hook so it only runs on demand:

```yaml
# .pre-commit-config.yaml
  - repo: local
    hooks:
      - id: fidelity-gate
        name: observability fidelity gate
        entry: bash scripts/fidelity_gate.sh
        language: system
        stages: [manual]        # run explicitly: pre-commit run --hook-stage manual fidelity-gate
        pass_filenames: false
```

## Notes / limits

- **Demo-data freshness is handled — but visible.** An idle load generator no longer tanks
  the gate: an empty `rate(...[5m])` is re-probed at a wider `--bind-window` (default `1h`)
  and, if the series exist, scored `bound_no_data` (counts toward `binding_coverage`, not
  against it). The staleness still shows up in the low `data_coverage`, so you see it — it
  just doesn't fail a correctness gate. Set `--bind-window` to tune the tolerance.
- **Exclude non-applicable artifact types** (e.g. `service_monitor` on an OTLP-push target)
  from the artifacts dir you gate, so they don't drag coverage down.
