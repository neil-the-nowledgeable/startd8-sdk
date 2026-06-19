# Tier 0 — OTel Demo Reference Environment — Implementation Plan

**Version:** 0.3 (Post-CRP-R1 triage — aligned to requirements v0.3)
**Date:** 2026-06-18
**Status:** CRP-R1 triaged (6/6 plan suggestions applied); pre-implementation
**Requirements:** [TIER0_REFERENCE_ENV_REQUIREMENTS.md](./TIER0_REFERENCE_ENV_REQUIREMENTS.md)

---

## 1. Planning discoveries (fed the requirements §0)

These are the concrete repo facts the planning pass found; each one moved a requirement.

| # | Discovery (file evidence) | Requirement moved |
| --- | --- | --- |
| D-1 | `docker-compose.loki-stack.yml` = Loki + Promtail + Grafana only. No trace/metric/profile backend in-repo. | FR-3 (default to demo's shipped stack) |
| D-2 | `scripts/otel_smoke_test.py` and `scripts/verify_otel_trace.py` target Tempo `:3200` + OTLP `:4317`, where Tempo is an external K8s "Wayfinder" stack (`kubectl get pods -n observability`). | FR-3 / FR-4 |
| D-3 | `verify_otel_trace.py` checks V-1..V-13 are **Artisan-pipeline-specific** (`_EXPECTED_PHASES`, `gate.entry`, `design.generate`) and Tempo-only. | FR-6 (new generic verifier) + NR-6 |
| D-4 | `OTEL_DEMO_SEED_EXTRACTION_PLAN.md` OQ-OT-1 needs per-service serve/readiness for Track-2 seeds. | FR-7 (startup capture) |
| D-5 | `_PROTOCOL_METRICS`/`_OTEL_SDK_MAP` live in sibling **ContextCore** repo (per `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md`). | FR-5 emits metric names; NR-7 keeps validation out of scope |
| D-6 | OTel Demo ships `compose.observability.yaml`, `compose.profiling.yaml`, `otel-config.yml`, `telemetry-schema/`, 12 languages (uploaded repo page). | FR-2 tiers; QW-5 |

**Reflection verdict:** > 30% of v0.1 requirements changed (4 of ~6 reframed/added). Per the skill's heuristic, the v0.1 draft was premature — the loop did its job by catching it at document cost.

---

## 2. Approach overview

All Tier-0 deliverables live under `scripts/otel_demo/` (new) and `docs/design/otel-demo-corpus/`. Nothing in the OTel Demo is modified; we **reference** it by pinned tag and **observe** it.

```
scripts/otel_demo/
├── bring_up.sh          # S1/S2: pinned clone + tiered compose up
├── teardown.sh          # S8: compose down + volume prune
├── fanout_patch.md      # S4: optional additive OTLP exporter (Apache header preserved)
├── attest_coverage.py   # S5: query backends → coverage-attestation.json
├── verify_coverage.py   # S6: read attestation → run queries via adapters → exit 0/1/2
├── capture_startup.py   # S7: running compose/Dockerfiles → startup-capture.json
└── adapters/            # S6: jaeger.py, prometheus.py, tempo.py (reusable — QW-6)
docs/design/otel-demo-corpus/
├── reference-env.md     # S2/S3/S9: tiers, ports, footprint, teardown
├── coverage-attestation.json   # generated (FR-5)
└── startup-capture.json        # generated (FR-7)
```

---

## 3. Steps (traced to requirements)

### S1 — Pinned bring-up wrapper  → FR-1, FR-8
- `bring_up.sh` clones `open-telemetry/opentelemetry-demo` at tag `v2.2.0` into a gitignored work dir (NOT vendored into this repo — NR/license).
- After `compose up`, capture resolved image digests (`docker compose images --format json`) into `reference-env.md` and the attestation header.
- Accept a `--tier {core|observe|profile}` flag (default `observe`).

### S2 — Tiered profiles  → FR-2, FR-9
- Map tiers to compose file sets:
  - `core` → `-f compose.yaml`
  - `observe` → `+ -f compose.observability.yaml`
  - `profile` → `+ -f compose.profiling.yaml`
- Record container count + `docker stats` memory per tier in `reference-env.md`; add fail-soft note (raise Docker memory / use `core` tier on constrained hosts).

### S3 — Shipped-stack defaults  → FR-3
- Document the demo's shipped endpoints in `reference-env.md`: Grafana `:8080/grafana`, Jaeger UI `:8080/jaeger`, Prometheus, OpenSearch, Pyroscope (per demo's frontend-proxy routing; confirm exact ports at bring-up).
- No StartD8 stack dependency in the default path.

### S4 — Optional fan-out  → FR-4 / FR-4a / FR-4b (QW-3)
- `fanout_patch.md` documents adding ONE exporter to `otel-config.yml`. **Default target is loopback/host-local; `insecure: true` is valid ONLY for that loopback target.** Enabling fan-out **egresses all demo telemetry** off the boundary (FR-4a). The exporter runs on **dedicated pipelines** with a bounded queue so a dead StartD8 endpoint cannot backpressure the demo's own pipelines (FR-4b).

```yaml
# additive only — Apache-2.0 header retained. Loopback default; dev-only.
exporters:
  otlp/startd8:
    endpoint: host.docker.internal:4317   # StartD8 Alloy — LOOPBACK/HOST-LOCAL ONLY
    tls:
      insecure: true            # ⚠ unauthenticated+unencrypted — loopback target ONLY (FR-4a)
    sending_queue:
      enabled: true
      queue_size: 1000          # bounded — a dead endpoint cannot grow unboundedly (FR-4b)
    retry_on_failure:
      enabled: true
      max_elapsed_time: 30s     # give up rather than backpressure the demo (FR-4b)
# Non-loopback target MUST use TLS — remove `insecure` and supply certs (FR-4a):
#   tls: { ca_file: /certs/ca.pem }   # + cert_file/key_file/server_name as needed
service:
  pipelines:
    # dedicated pipelines: isolation so a down StartD8 endpoint cannot stall the
    # demo's own Jaeger/Prometheus exporters (FR-4b / R1-S5)
    traces/startd8:  { receivers: [otlp], exporters: [otlp/startd8] }
    metrics/startd8: { receivers: [otlp], exporters: [otlp/startd8] }
```
- Off by default; opt-in for a unified StartD8 Grafana view. No service touched.
- **Acceptance (R1-S5):** bring up with fan-out on and the StartD8 endpoint unreachable → assert Jaeger/Prometheus still receive demo telemetry (no backpressure stall).

### S5 — Coverage attestation generator  → FR-5 (QW-1, QW-4, QW-5)
- `attest_coverage.py` queries the active backends and writes `coverage-attestation.json`:

```json
{
  "schema_version": "1.0",
  "demo_version": "v2.2.0",
  "image_digests": { "...": "sha256:..." },
  "generated_at": "2026-06-18T...",
  "sections": [
    {
      "section_id": "5.4-messaging",
      "landscape_ref": "OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#54-messaging",
      "signal": "traces",
      "backend": "jaeger",
      "query": "messaging.system=kafka and span.kind in (PRODUCER,CONSUMER)",
      "threshold": 1,
      "window": "15m",
      "evidence_status": "evidenced|missing|error",
      "observed_names": ["messaging.system", "messaging.destination.name"]
    }
  ]
}
```
- **`schema_version` (FR-5a / R1-S2):** top-level semver; consumers MUST reject an unknown **major** version. Compatibility policy documented in `reference-env.md`: minor bumps add fields (back-compatible), major bumps may rename/remove (consumers must re-validate).
- **`query`/`threshold`/`window` (FR-5b / R1-F3):** each section carries the exact §4 acceptance triple, so the verifier (S6) is a pure data-driven runner and re-runs are deterministic.
- **`observed_names` (R1-S6):** a list of attribute/metric names actually seen. **QW-4 status: UNVERIFIED pending a cross-repo field contract with ContextCore.** `reference-env.md` documents the field as `observed_names: string[]`; until ContextCore agrees to consume that exact shape, QW-4 is a *candidate* integration, not a delivered one (NR-7 keeps the other side out of scope).
- Capture `telemetry-schema/` reference into the attestation (QW-5).

### S5.5 — OQ-5 API-shape probe (BLOCKING gate before S6)  → OQ-5 (R1-S3)
- **Resolves the circular dependency:** OQ-5 must NOT be "probed by S6" — you cannot version-gate adapters you haven't designed. This is a small spike that runs **before** any adapter code is committed.
- Against the pinned v2.2.0 environment, record the actual query shapes into `reference-env.md`:
  - Jaeger query API: `/api/services`, `/api/traces?service=…&lookback=…`, tag-filter syntax, and how `process.tags` expose `telemetry.sdk.language`.
  - Prometheus: confirm the real metric names/labels behind the §4 rows (e.g. `rpc_server_duration_milliseconds_count`, `traces_span_metrics_*`).
- Output: an "API-shape decision record" in `reference-env.md` that the §4 table and the S6 adapters are written against. If upstream names differ from §4's expected names, update the §4 table here (per its own note).

### S6 — Generic verifier + adapters  → FR-6 (QW-6); consumes S5.5
- `verify_coverage.py` reads the attestation, dispatches each `query`/`threshold`/`window` to `adapters/{jaeger,prometheus,tempo}.py`, prints a per-section report, exits `0/1/2` (mirrors `verify_otel_trace.py` exit convention without reusing its Artisan checks — NR-6).
- Adapters are written against the **S5.5 API-shape decision record** (not discovered on the fly).
- The verifier MUST validate the attestation's `schema_version` (FR-5a) before dispatch and refuse an unknown major version.
- The `tempo.py` adapter makes the verifier reusable when fan-out (S4) is on.

### S7 — Startup capture  → FR-7 (QW-2)
- `capture_startup.py` reads the cloned demo's per-service Dockerfiles/compose entries for the covered services in the seed plan (checkout, product-catalog, recommendation, product-reviews, cart, ad, payment) and emits `startup-capture.json`:

```json
{ "payment": { "cmd": ["node", "..."], "port_env": "PAYMENT_PORT", "readiness": "tcp" } }
```
- Schema matches `gen_ob_benchmark_seeds.py`'s `startup` block so it drops straight into `gen_otel_benchmark_seeds.py` (resolves OQ-OT-1). NR-3: we do not generate seeds here.

### S8 — Teardown, re-attestation target + docs  → FR-9, OQ-6 (R1-S4)
- `teardown.sh`: `docker compose ... down -v`.
- **`make tier0-attest`** (OQ-6 resolution): a single target that re-runs bring-up (if needed) + `attest_coverage.py` + `verify_coverage.py`, refreshing `generated_at`. v1 is manual; promoting to nightly CI is then a one-line wrapper. This gives drift *detection*, not just capability.
- `reference-env.md`: tiers, ports, footprint table, teardown, fail-soft guidance, the S5.5 API-shape decision record, the `schema_version` compatibility policy, and the staleness window.

### S9 — Validation
- Run S5.5 probe; confirm the §4 table names match v2.2.0 (or update the table).
- Bring up `observe` tier; run `attest_coverage.py`; assert every §4 acceptance row meets its `threshold` within its `window` (≥5 languages, gRPC, Kafka, db.system, flagd, span-metrics connector).
- Bring up `profile` tier once; assert Profiles row `evidenced`.
- Run `verify_coverage.py` → exit 0; assert it **rejects** an attestation with an unknown major `schema_version` (FR-5a).
- **Freshness gate:** assert the attestation `generated_at` is within the staleness window of bring-up (OQ-6).
- **Fan-out isolation (R1-S5):** with fan-out on and the StartD8 endpoint down, assert Jaeger/Prometheus still receive demo telemetry.
- Assert `startup-capture.json` lists all covered gRPC services with non-empty `cmd`.

---

## 4. Requirement → step traceability

| Requirement | Step(s) |
| --- | --- |
| FR-1 pinned bring-up | S1 |
| FR-2 tiered profiles | S2 |
| FR-3 shipped-stack default | S3 |
| FR-4 optional fan-out | S4 |
| FR-4a fan-out security | S4 |
| FR-4b fan-out isolation | S4, S9 |
| FR-5 attestation | S5 |
| FR-5a schema versioning | S5, S6 |
| FR-5b self-describing acceptance | S5, S9 |
| FR-6 generic verifier | S6 |
| FR-7 startup capture | S7 |
| FR-8 determinism/attribution | S1, S5 |
| FR-9 footprint/teardown | S2, S8 |
| OQ-5 (BLOCKING) | S5.5 |
| OQ-6 (non-blocking) | S8 (`make tier0-attest`) |
| Acceptance §4 | S5.5, S9 |

Every step traces to a requirement; every requirement has ≥1 step. No orphans.

---

## 5. Sequencing & effort

| Order | Step | Effort | Blocks |
| --- | --- | --- | --- |
| 1 | S1 bring_up + S2 tiers + S3 docs | ~½ day | everything |
| 2 | S7 startup capture | ~2 hr | Tier 1.4 |
| 3 | **S5.5 OQ-5 API-shape probe** | ~2 hr | S6 (BLOCKING) |
| 4 | S5 attestation + S6 verifier + adapters | ~1 day | acceptance |
| 5 | S4 fan-out (optional) | ~1 hr | — |
| 6 | S8 teardown/`make tier0-attest`/docs + S9 validation | ~1 hr | sign-off |

Critical path ≈ **2 days**, almost all glue/observation code — no service code, matching the Tier-0 "config-not-build" thesis. The S5.5 probe is sequenced **before** the adapters it informs (R1-S3).

---

## 6. Risks

| Risk | Mitigation |
| --- | --- |
| Demo too heavy for dev laptop | FR-2 `core` tier; FR-9 fail-soft guidance |
| Jaeger/Prometheus query API drift across versions | **S5.5 probe resolves API shapes before adapters are built** (R1-S3); adapter isolation; pin v2.2.0 (FR-8) |
| Demo upstream changes service layout | Pinned tag + recorded digests (FR-8); re-capture on bump |
| Attestation rots vs catalog | QW-1 reusable contract + **`make tier0-attest` re-run target + freshness gate** (R1-S4); CI promotion deferred (OQ-6 non-blocking) |
| Incompatible attestation consumed silently | `schema_version` + verifier rejects unknown major (FR-5a / R1-S2) |
| Fan-out leaks telemetry / backpressures demo | Loopback default + TLS-for-routable (FR-4a); dedicated pipelines + bounded queue (FR-4b / R1-S5) |
| QW-4 cross-repo integration assumed delivered | Marked UNVERIFIED pending ContextCore field contract (R1-S6); `observed_names: string[]` documented |

---

## 7. Phase 5 — Convergent Review (R1 complete)

A dual-document CRP review (R1, `claude-opus-4-8`) ran on v0.2 and is now **triaged into v0.3**. All 6 plan-side suggestions (R1-S1…S6) and 4 requirements-side (R1-F1…F4) were **accepted and applied** — see Appendix A in both files. The review confirmed the reflective loop's blind spots were *missing concerns* (fan-out security, schema versioning, OQ sequencing, cross-repo coupling, acceptance testability), all now addressed. A future R2 (different model/focus) would append under Appendix C without re-proposing settled items.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Secure the fan-out exporter (loopback default, insecure-warning, TLS variant) | claude-opus-4-8 R1 | Applied in **S4** (rewritten YAML + FR-4a). | 2026-06-18 |
| R1-S2 | Add `schema_version` + compat policy to attestation | claude-opus-4-8 R1 | Applied in **S5** JSON example + FR-5a; S6 verifier rejects unknown major. | 2026-06-18 |
| R1-S3 | OQ-5 probe/spike before S6 (break circular dep) | claude-opus-4-8 R1 | Applied as new step **S5.5** (BLOCKING gate); sequencing + risks updated; OQ-5 disposition in reqs §5. | 2026-06-18 |
| R1-S4 | Minimal scheduled/CI re-attestation hook | claude-opus-4-8 R1 | Applied in **S8** (`make tier0-attest`) + §4 freshness gate; CI promotion deferred (OQ-6 non-blocking). | 2026-06-18 |
| R1-S5 | Route fan-out via separate pipeline / bounded queue | claude-opus-4-8 R1 | Applied in **S4** (dedicated `*/startd8` pipelines + `sending_queue`/`retry_on_failure`) + FR-4b; S9 isolation check. | 2026-06-18 |
| R1-S6 | Specify `observed_names` shape; mark QW-4 unverified | claude-opus-4-8 R1 | Applied in **S5**: `observed_names: string[]` documented; QW-4 flagged UNVERIFIED pending ContextCore field contract. | 2026-06-18 |

**Areas substantially addressed (post-R1):** fan-out security + isolation (S4); attestation schema versioning + self-describing rows (S5); OQ-5 de-circularized via S5.5; OQ-6 drift detection via `make tier0-attest` + freshness gate; QW-4 honestly scoped as unverified. The R1 Requirements Coverage Matrix's Partial/Gap rows are all now closed in v0.3.

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-19 01:45:00 UTC
- **Scope**: Concerns the reflective loop could not self-catch — fan-out exporter security (S4/FR-4), attestation schema versioning & drift (S5/FR-5), OQ-5/OQ-6 sequencing-vs-acceptance coupling, cross-repo ContextCore coupling (QW-4/NR-7), and §4 testability gaps.

**Executive summary**

- S4's fan-out patch ships `tls: insecure: true` with no auth and an unscoped endpoint — a documented opt-in that, as written, normalizes an insecure cross-process telemetry channel.
- Enabling fan-out exports *all* demo spans/metrics (synthetic carts, user IDs, payment spans) off the demo boundary; no data-egress classification note exists.
- `coverage-attestation.json` (S5) has no `schema_version`; QW-1's "reusable contract" and the S6 verifier / ContextCore consumer (QW-4) all parse it, so an unversioned schema is a silent-drift hazard.
- OQ-5 (query-API drift) is "probed" *by* S6 itself (§5 order-3) — a circular dependency: adapter shape can't be known until the adapter is built. Needs a probe/spike preceding S6.
- OQ-6 defers CI-vs-manual, but FR-8/QW-1's drift-detection value is contingent on re-running; a purely manual artifact detects drift only when someone remembers.
- §4 acceptance rows use unquantified evidence ("a `*_duration` / RPC metric series present") with no exact query string or lookback window — not deterministically testable.
- `observed_names` → ContextCore `_PROTOCOL_METRICS` (QW-4) has no agreed field contract; the "free downstream consumer" claim is unverified across repos.
- Adversarial: an additive exporter on the demo's *shared* trace/metrics pipelines can backpressure the demo's own telemetry if the StartD8 endpoint is down.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | high | In S4, replace the bare `tls: insecure: true` with (a) a default loopback-only/`host.docker.internal` scoping note, (b) an explicit warning that the exporter is unauthenticated and unencrypted, and (c) a TLS-enabled variant snippet for any non-loopback target. | The patch as shown normalizes an insecure exporter; copied verbatim to a routable endpoint it leaks telemetry in cleartext with no auth. | S4 — the `otlp/startd8` exporter YAML block | Lint/grep the patch doc for an `insecure: true` accompanied by a loopback-scope warning + a secure alternative; reject a routable endpoint with `insecure: true`. |
| R1-S2 | Data | high | Add a top-level `schema_version` (and a brief compatibility policy: what a major bump means for consumers) to the `coverage-attestation.json` example in S5. | S6, QW-1's reusable contract, and ContextCore (QW-4) all parse this artifact; without a version field they cannot detect or refuse incompatible attestations — silent drift. | S5 — the `coverage-attestation.json` example (alongside `demo_version`/`generated_at`) | Assert generated attestation contains `schema_version`; add a consumer test that rejects an unknown major version. |
| R1-S3 | Risks | high | Insert an explicit OQ-5 probe/spike task that runs *before* S6 (or at S6's first sub-step), recording the Jaeger/Prometheus API shapes for the pinned v2.2.0 before adapters are committed. | §5 order-3 builds S5+S6 together while OQ-5 is "probed by S6" — circular: you cannot version-gate adapters you haven't designed. Resolving the API contract first de-risks the adapter layer. | §5 Sequencing table (row "3 \| S5 attestation + S6 verifier") and §3 S6 | Sequencing table shows an OQ-5 resolution step preceding adapter implementation with the API-shape decision recorded in `reference-env.md`. |
| R1-S4 | Ops | medium | Resolve OQ-6 toward at least a minimal scheduled/CI re-attestation hook (documented `make`/cron target or nightly job), even if v1 stays local. | §6 risk "Attestation rots vs catalog" is mitigated only if re-attestation actually runs; a manual-only artifact provides drift *capability* but no drift *detection*. | §6 Risks table (row "Attestation rots vs catalog") and §5 | Plan specifies a re-run cadence or CI trigger; acceptance includes a check that the attestation's `generated_at` is fresher than a defined staleness window. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S5 | Security | medium | In S4, route the `otlp/startd8` exporter through a *separate* pipeline (or set `sending_queue`/`retry_on_failure` conservatively) rather than appending to the demo's existing `traces`/`metrics` exporter lists. | Appending to `exporters: [..., otlp/startd8]` puts the additive exporter on the demo's primary pipelines; if the StartD8 endpoint is down, queue saturation/retries can degrade the demo's own (Jaeger/Prometheus) telemetry — violating "no service touched" in spirit. | S4 — the `service.pipelines` block | Bring up with fan-out on and the StartD8 endpoint unreachable; assert Jaeger/Prometheus still receive demo telemetry (no backpressure stall). |
| R1-S6 | Interfaces | medium | Specify the exact shape/field names of `observed_names` and cite where ContextCore's `_PROTOCOL_METRICS` consumes it (or mark the QW-4 integration explicitly "unverified pending cross-repo contract"). | QW-4 claims a "$0 downstream consumer," but with no shared field contract the claim is untestable and NR-7 leaves the other side unowned — coupling without a boundary. | S5 — the `observed_names` line and §QW-4 reference | Either a documented field contract referenced by both repos, or a plan note flagging the integration as speculative until a cross-repo schema is agreed. |

**Endorsements / Disagreements**: None — Appendix C had no prior rounds at R1.

---

## Requirements Coverage Matrix — R1

Analysis only (per dual-document mode). Maps each requirement/section to its plan step(s) and a coverage verdict. `Partial`/`Gap` rows reference the R1 suggestion that proposes the fix.

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Pinned bring-up | S1 | Full | — |
| FR-2 Tiered profiles | S2 | Full | — |
| FR-3 Shipped-stack default | S3 | Full | — |
| FR-4 Optional fan-out | S4 | Partial | No security constraints on the optional exporter (TLS/auth/egress, shared-pipeline backpressure) — see R1-S1, R1-S5, R1-F1. |
| FR-5 Coverage attestation | S5 | Partial | Attestation carries no `schema_version`/compatibility policy — see R1-S2, R1-F2. |
| FR-6 Generic verifier | S6 | Partial | OQ-5 adapter-drift resolved only by S6 itself (circular); no attestation schema-validation gate before dispatch — see R1-S3. |
| FR-7 Startup capture | S7 | Full | Minor: consumer `startup` block schema not version-pinned (not blocking). |
| FR-8 Determinism & attribution | S1, S5 | Full | — |
| FR-9 Footprint & teardown | S2, S8 | Full | — |
| §4 Coverage target (acceptance) | S9 | Partial | Acceptance rows lack exact query strings/thresholds and a lookback window — see R1-F3. |
| OQ-5 Query-API stability | S6 (probe) | Partial | Probe is internal to the step it gates — see R1-S3. |
| OQ-6 CI vs manual attestation | §6 Risks | Gap | No re-attestation cadence/CI decision; drift detection currently manual-only — see R1-S4, R1-F4. |
