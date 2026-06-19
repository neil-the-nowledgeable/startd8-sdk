# Tier 0 — OTel Demo Reference Environment (operator notes)

**Status:** S1–S8 implemented (bring-up, probe, attestation, verifier, startup capture)
**Spec:** [TIER0_REFERENCE_ENV_REQUIREMENTS.md](./TIER0_REFERENCE_ENV_REQUIREMENTS.md) · [TIER0_REFERENCE_ENV_PLAN.md](./TIER0_REFERENCE_ENV_PLAN.md)

This is the operator home for the referenced OTel Demo environment: how to bring it up, the tier
matrix, ports, footprint, and where the generated evidence lands. The demo is **referenced at a
pinned tag** (`v2.2.0`), never vendored (FR-1).

---

## Quick start

```bash
# bring up the default (observe) tier — clones the pinned demo on first run
scripts/otel_demo/bring_up.sh --tier observe

# one-shot attestation pipeline (probe → attest → verify → startup capture)
make tier0-attest
# or:
scripts/otel_demo/tier0_attest.sh

# tear down (drops volumes by default)
scripts/otel_demo/teardown.sh --tier observe
```

Individual steps:

```bash
python3 scripts/otel_demo/probe_api_shapes.py \
    --jaeger http://localhost:16686 \
    --prometheus http://localhost:9090 \
    --out docs/design/otel-demo-corpus/api-shape-decision.json

python3 scripts/otel_demo/attest_coverage.py --tier observe \
    --out docs/design/otel-demo-corpus/coverage-attestation.json

python3 scripts/otel_demo/verify_coverage.py \
    docs/design/otel-demo-corpus/coverage-attestation.json

python3 scripts/otel_demo/capture_startup.py \
    --workdir .otel-demo \
    --out docs/design/otel-demo-corpus/startup-capture.json
```

Pin overrides: `OTEL_DEMO_REF=v2.2.0`, `TIER0_WORKDIR=.otel-demo`, `OTEL_DEMO_REPO=...`.

---

## Tier matrix (FR-2)

| Tier | Compose files | Adds | Coverage |
| --- | --- | --- | --- |
| `core` | `compose.yaml` | service mesh + demo Collector | lightest |
| `observe` *(default)* | `+ compose.observability.yaml` | Jaeger, Prometheus, Grafana, OpenSearch | traces + metrics + logs |
| `profile` | `+ compose.profiling.yaml` | Pyroscope | + Profiles signal |

> **First-run confirmation (FR-2 / S2):** `bring_up.sh` filters the tier's compose list to files that
> actually exist in the pinned clone and **warns** on any missing one. If `v2.2.0`'s layout differs
> (e.g. observability is folded into `compose.yaml`), update this table to the files the script
> reports as *used*. The script never silently runs a wrong invocation.

---

## Ports (best-effort defaults — confirm on first bring-up)

| Surface | Default | Notes |
| --- | --- | --- |
| Frontend-proxy (Envoy) | `:8080` | UIs routed under here (`/grafana`, `/jaeger`, …) |
| Jaeger query API | `:16686` | `/api/services`, `/api/traces` — probe target |
| Prometheus | `:9090` | `/api/v1/...` — probe target |
| Grafana | `:8080/grafana` | shipped dashboards |
| Pyroscope | `:4040` | profile tier — `/api/apps` or `/ready` |

These feed the probe/attest flags. If your bring-up exposes different ports, pass them via
`--jaeger`/`--prometheus`/`--pyroscope` or env `JAEGER`/`PROM`/`PYRO` for `tier0_attest.sh`.

---

## Generated evidence (FR-8)

| Artifact | Producer | Tracked? |
| --- | --- | --- |
| `bringup-manifest.json` | `bring_up.sh` | gitignored — `demo_ref`, `git_sha`, tier, compose files |
| `bringup-images.txt` | `bring_up.sh` | gitignored — resolved image digests |
| `api-shape-decision.json` | `probe_api_shapes.py` | **tracked** — OQ-5 decision record for §4 + adapters |
| `coverage-attestation.json` | `attest_coverage.py` | gitignored — per-run §4 evidence (FR-5) |
| `startup-capture.json` | `capture_startup.py` | gitignored — Tier 1 seed input (FR-7) |

Optional StartD8 fan-out: see [scripts/otel_demo/fanout_patch.md](../../../scripts/otel_demo/fanout_patch.md).

---

## Footprint guardrail (FR-9)

Record measured values after first bring-up:

| Tier | Containers | Approx. memory | Notes |
| --- | --- | --- | --- |
| core | _TBD_ | _TBD_ | smallest; use on constrained hosts |
| observe | _TBD_ | _TBD_ | default |
| profile | _TBD_ | _TBD_ | heaviest (+ Pyroscope) |

**Fail-soft:** if a tier won't fit, raise Docker Desktop memory or drop to `--tier core`. `bring_up.sh`
reports the container count into `bringup-manifest.json` after each run.

---

## Attestation freshness (OQ-6)

`verify_coverage.py` checks `generated_at` against a 24h staleness window (override:
`--max-age-hours`) and rejects attestations older than `bringup-manifest.json`. Re-run
`make tier0-attest` after bring-up or demo upgrades. CI promotion is deferred (OQ-6 non-blocking).

## `coverage-attestation.json` schema (FR-5a)

`schema_version` is semver (`1.0` today). The verifier rejects unknown **major** versions before
dispatching live §4 queries.
