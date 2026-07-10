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
| `0` pass | coverage ≥ `--min-coverage`, ≥1 query replayed | build **passes** |
| `2` fail | coverage below the floor | build **fails** |
| `3` unknown | backend unreachable / zero queries replayed | build **fails** (set `FAIL_ON_UNKNOWN=false` to warn instead) |

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

- **Demo-data freshness matters.** Replay uses the emitted `rate(...[5m])` windows, so a
  target whose load generator has been idle for >5 minutes will show low coverage even
  though the metrics bind — the queries are correct, the recent data is just absent.
  Widen the load window or point at a live-traffic backend for a representative gate.
  (Widening the replay rate-window to tolerate stale-but-present data is a tracked harness
  refinement.)
- **Exclude non-applicable artifact types** (e.g. `service_monitor` on an OTLP-push target)
  from the artifacts dir you gate, so they don't drag coverage down.
