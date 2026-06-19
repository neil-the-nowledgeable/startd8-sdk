# Tier 0 — OTel Demo Reference Environment — Requirements

**Version:** 0.3 (Post-CRP-R1 triage)
**Date:** 2026-06-18
**Status:** CRP-R1 triaged (10/10 applied); pre-implementation
**Derived from:** [OTEL_DEMO_COVERAGE_QUICK_WINS.md](../OTEL_DEMO_COVERAGE_QUICK_WINS.md) Tier 0
**Companion plan:** [TIER0_REFERENCE_ENV_PLAN.md](./TIER0_REFERENCE_ENV_PLAN.md)
**Coverage axes:** [OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md](../OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md)
**Gap baseline:** [OTEL_LANDSCAPE_ONLINE_BOUTIQUE_OVERLAP.md](../OTEL_LANDSCAPE_ONLINE_BOUTIQUE_OVERLAP.md)

---

## 0. Planning Insights (Self-Reflective Update)

> This section records what changed between **v0.1** (pre-planning) and **v0.2** (post-planning).
> The planning pass read the repo's actual OTel tooling and stack and falsified four v0.1
> assumptions. Six corrections resulted; four are *new* requirements that were not visible until
> planning exposed the real seams.

| v0.1 assumption | Planning discovery | Impact |
| --- | --- | --- |
| Point the demo's telemetry at StartD8's existing Tempo/LGTM stack. | `docker-compose.loki-stack.yml` ships **Loki + Promtail + Grafana only** — no Tempo/Prometheus/profiles. The Tempo that `scripts/otel_smoke_test.py` and `scripts/verify_otel_trace.py` assume is an **external K8s "Wayfinder" stack** (`kubectl get pods -n observability`), not reproducible per-developer. The OTel Demo ships its **own complete stack** (Jaeger + Prometheus + Grafana + OpenSearch + Pyroscope). | **FR-3 flips the default** to the demo's shipped stack (self-contained, includes the Profiles backend StartD8 has nowhere else). **FR-4** makes StartD8-stack fan-out *optional/additive*, not the path. |
| Reuse `scripts/verify_otel_trace.py` to assert coverage. | That script hard-codes the **Artisan 8-phase** span names (`phase.plan`, `gate.entry`, `design.generate`, …) in 13 checks and queries the **Tempo** HTTP API only. Demo traces land in **Jaeger** with arbitrary service spans. Reuse would fail every check. | **FR-6** specifies a *new* generic, backend-adapter coverage verifier; the Artisan verifier is explicitly out of scope to modify. |
| Tier 0 is "just stand it up." | The paper catalogs already *claim* landscape coverage. The un-met need is **proving** the coverage is live and detecting drift. | **FR-5 (new)** — a machine-readable `coverage-attestation.json` mapping each landscape section → a live query that returns evidence. Turns paper coverage into verified coverage. |
| Tier 0 is independent of Tier 1. | A running compose exposes each service's **serve command + port + readiness** — exactly `OQ-OT-1` in [OTEL_DEMO_SEED_EXTRACTION_PLAN](./OTEL_DEMO_SEED_EXTRACTION_PLAN.md), the blocker for Track-2 behavioral seeds. | **FR-7 (new)** — capture `startup-capture.json` as a Tier-0 by-product. Tier 0 unblocks Tier 1.4 at zero extra cost. |
| Instrumentation-derivation validation is in-repo. | `_PROTOCOL_METRICS` / `_OTEL_SDK_MAP` live in the **sibling ContextCore repo** (`ContextCore/utils/instrumentation.py`), per `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md`. | Cross-repo validation is **out of scope** here, but **FR-5 emits the live metric/attribute names** so ContextCore validation becomes a $0 downstream consumer (QW-4). |
| `docker compose up` is lightweight. | The full demo is ~20+ containers + 4 telemetry backends. | **FR-2** tiers the compose profiles; **FR-9** adds a footprint guardrail + teardown. |

**Resolved open questions:**
- **OQ-1 → Demo's shipped stack is the default.** Self-contained, reproducible, and the only place StartD8 gets a Profiles backend. StartD8 fan-out is optional (FR-4).
- **OQ-2 → Do NOT reuse the Artisan verifier.** Write a generic backend-adapter verifier (FR-6).
- **OQ-3 → Tiered profiles.** Default = core mesh + observability; profiling profile is opt-in (FR-2).
- **OQ-4 → Coverage lives in an artifact, not prose.** `coverage-attestation.json` (FR-5).

**Quick wins / functional low-hanging fruit surfaced by planning** (were not evident in v0.1):
- **QW-1 — Coverage attestation as a reusable contract.** Once the schema exists, every future landscape/corpus doc validates against it → $0 regression guard against coverage drift.
- **QW-2 — Startup capture unblocks behavioral seeds.** Tier 0 produces the `startup` blocks `OQ-OT-1` needs (FR-7).
- **QW-3 — One-line fan-out.** A single additive OTLP exporter in the demo collector gives a unified StartD8 Grafana view without touching any service (FR-4).
- **QW-4 — Free ContextCore validation.** Emitting live metric names lets ContextCore's `_PROTOCOL_METRICS` table be validated downstream for $0.
- **QW-5 — `telemetry-schema/` is a ready §8 artifact.** Capture it; don't author schema files.
- **QW-6 — Reusable query adapters.** Jaeger/Prometheus/Tempo adapters written once serve any future demo-based verification, not just Tier 0.

---

## 1. Problem statement

StartD8 needs broad, *demonstrable* OpenTelemetry-landscape coverage to support three downstream consumers: benchmark **corpus extraction**, **instrumentation-contract derivation** validation, and **code-observability** research fixtures. Building services to obtain that coverage is expensive (Tier 1/2). The OTel Demo already packages the coverage as toggles. **Tier 0** is the cheapest, highest-coverage move: stand up the demo as a **reproducible, pinned, verifiable reference environment** and capture the coverage as a machine-readable attestation.

| Component | Current state | Gap |
| --- | --- | --- |
| Local telemetry stack | `docker-compose.loki-stack.yml` = Loki + Promtail + Grafana | No traces / metrics / **profiles** backend locally |
| Trace backend | External K8s "Wayfinder" Tempo (not in-repo) | Not reproducible per-developer; not $0 |
| Coverage evidence | Catalog markdown (paper) | No **live** proof that landscape sections actually emit |
| Coverage verifier | `scripts/verify_otel_trace.py` (Artisan-only, Tempo-only) | No **generic** landscape-coverage verifier |
| Behavioral seed inputs | `OTEL_DEMO_SEED_EXTRACTION_PLAN` OQ-OT-1 unresolved | Needs running services' serve/readiness |

**Goal:** a one-command, pinned bring-up of the OTel Demo on its shipped stack, plus a coverage attestation and a generic verifier that *prove* which landscape-catalog sections are live — with two zero-cost by-products (startup capture for Tier 1.4, live metric names for ContextCore).

---

## 2. Requirements

### Bring-up & reproducibility

- **FR-1 — Pinned, one-command bring-up.** The reference environment MUST be brought up from the OTel Demo pinned to a fixed release (target **v2.2.0**) via a single documented command. The environment MUST NOT vendor the demo's source tree into this repo; it references the demo by pinned tag and records image digests.
- **FR-2 — Tiered compose profiles.** Define three coverage tiers and document exactly which compose files each uses:
  - **T0-core:** `compose.yaml` — the service mesh (gRPC/HTTP/Kafka/Postgres/flagd) + the demo Collector.
  - **T0-observe (default):** core + `compose.observability.yaml` — Jaeger + Prometheus + Grafana + OpenSearch.
  - **T0-profile (opt-in):** observe + `compose.profiling.yaml` — Pyroscope (Profiles signal).
- **FR-8 — Determinism & attribution.** Any demo config copied into this repo (e.g. an exporter patch) MUST retain its Apache-2.0 header. The attestation (FR-5) MUST record the demo release tag and resolved image digests so a run is reproducible and drift is detectable.
- **FR-9 — Footprint guardrail & teardown.** The docs MUST record the measured container count and memory footprint per tier, provide a single teardown command, and give fail-soft guidance when a host cannot run a tier.

### Backends

- **FR-3 — Self-contained shipped stack is the default.** The environment MUST work end-to-end using the demo's **own** shipped backends (Jaeger, Prometheus, Grafana, OpenSearch, Pyroscope). It MUST NOT require StartD8's external Tempo/Wayfinder stack or the repo's Loki compose.
- **FR-4 — Optional StartD8 fan-out (additive, off by default).** The environment SHOULD support an *optional* additional OTLP exporter in the demo Collector that also ships telemetry to StartD8's Alloy/Tempo endpoint, enabling a unified StartD8 Grafana view **without modifying any demo service**. Default: disabled.
  - **FR-4a — Security (MUST).** When enabled, the exporter MUST default to a loopback/host-local target (`host.docker.internal` / `127.0.0.1`). An unauthenticated, unencrypted (`tls.insecure: true`) exporter MUST NOT point at a routable endpoint; any non-loopback target MUST use TLS. The docs MUST state that enabling fan-out **egresses all demo telemetry** (synthetic carts, user IDs, payment spans) off the demo boundary. *(R1-F1)*
  - **FR-4b — Isolation (MUST).** The fan-out exporter MUST NOT degrade the demo's own telemetry: it MUST run on dedicated pipelines (or set a bounded `sending_queue` + `retry_on_failure`) so an unreachable StartD8 endpoint cannot backpressure the demo's Jaeger/Prometheus pipelines. *(R1-S5)*

### Coverage evidence

- **FR-5 — Coverage attestation artifact.** Produce a machine-readable `coverage-attestation.json` that maps each relevant landscape-catalog section (signals §2, languages §3, OTLP §4.1, propagation §4.2, patterns §5, platform §6, collector §7) to: the live query that evidences it, the backend that answers it, and an evidence status. The artifact MUST also record the live metric/attribute names observed (for QW-4) and the demo version/digests (FR-8).
  - **FR-5a — Schema versioning (MUST).** The attestation MUST declare its own top-level `schema_version` (semver) and a compatibility policy: a consumer (the FR-6 verifier, future landscape docs, ContextCore) MUST reject an attestation whose **major** version it does not recognize. This is what makes QW-1's "reusable contract" and QW-4's downstream consumption drift-safe. *(R1-F2 / R1-S2)*
  - **FR-5b — Each acceptance row is self-describing (MUST).** Every §4 acceptance row MUST be encoded 1:1 in the attestation as an exact `query`, a numeric `threshold`, and a `window` (lookback), so re-running yields the same verdict. *(R1-F3)*
- **FR-6 — Generic landscape-coverage verifier.** Provide a *new* verifier (NOT the Artisan `verify_otel_trace.py`) that reads the attestation, runs each query against the active backend through a **backend adapter** (Jaeger / Prometheus / Tempo), and reports per-section pass/fail. Exit codes MUST follow the repo convention: `0` all evidenced, `1` one or more missing, `2` infrastructure/connection error.

### Downstream synergy

- **FR-7 — Startup/readiness capture (Tier-1.4 enabler).** From the running environment, capture each covered service's serve command, port env, and readiness signal into `startup-capture.json`, schema-aligned with the `startup` block consumed by `gen_otel_benchmark_seeds.py` (resolves `OQ-OT-1`). This is a Tier-0 by-product, not new service code.

---

## 3. Non-requirements

- **NR-1** — Does NOT modify OTel Demo source, services, or proto.
- **NR-2** — Does NOT build new services or add languages (Tier 2).
- **NR-3** — Does NOT extract benchmark seeds (Tier 1.4) — but FR-7 produces its missing input.
- **NR-4** — Does NOT generate dashboards/alerts/SLOs (separate observability-artifact pipeline).
- **NR-5** — Does NOT replace or modify the repo's Loki compose stack.
- **NR-6** — Does NOT modify `scripts/verify_otel_trace.py` (Artisan verifier stays as-is).
- **NR-7** — Does NOT validate ContextCore derivation tables here (cross-repo; only emits the inputs).

---

## 4. Coverage target (acceptance)

Tier 0 is "done" when the attestation (FR-5) evidences, on a single brought-up environment, every row below. Each row is **deterministically testable**: an exact query, a numeric threshold, and a lookback window (windows accommodate loadgenerator warm-up). These rows are the literal `query`/`threshold`/`window` entries the attestation (FR-5b) encodes. *(R1-F3)*

| Landscape § | Backend | Query (exact) | Threshold | Window |
| --- | --- | --- | --- | --- |
| §2 Traces | Jaeger | `GET /api/services` → `GET /api/traces?service=<svc>` | ≥1 trace for ≥1 service | 5m |
| §2 Metrics | Prometheus | `count(rpc_server_duration_milliseconds_count) + count(http_server_request_duration_seconds_count)` | ≥1 series | instant |
| §2 Profiles *(T0-profile only)* | Pyroscope | profile series query for any service label | ≥1 profile | 5m |
| §3.1 Languages | Jaeger | distinct `process.tags["telemetry.sdk.language"]` across `/api/services` | ≥5 distinct values | 15m |
| §4.1 OTLP gRPC + HTTP | collector (static) | parse `otel-config.yml`: `receivers.otlp.protocols` has `grpc` **and** `http` | both present | n/a |
| §5.3 gRPC | Jaeger | spans where tag `rpc.system="grpc"` | ≥1 span | 5m |
| §5.4 Messaging | Jaeger | spans with `messaging.system="kafka"` and kind ∈ {PRODUCER,CONSUMER} | ≥1 span | 15m |
| §5.5 Database | Jaeger | spans where tag `db.system` ∈ {`postgresql`,`valkey`,`redis`} | ≥1 span | 15m |
| §5.6 Feature flags | Jaeger | spans/events with tag `feature_flag.key` (flagd) | ≥1 | 15m |
| §7.1 Connector | Prometheus | `count({__name__=~"traces_span_metrics_.*"})` (span-metrics connector output) | ≥1 series | instant |

> Metric/series names above are the expected v2.2.0 names; the OQ-5 API-shape probe (plan S5.5) confirms exact names/labels before the verifier is committed and updates this table if upstream differs.

`startup-capture.json` (FR-7) MUST list every covered gRPC service from the seed plan with a non-empty serve command.

**Freshness gate (FR-5/OQ-6):** acceptance also asserts the attestation's `generated_at` is within a defined staleness window of the bring-up, so a stale artifact cannot satisfy the gate. *(R1-S4 / R1-F4)*

---

## 5. Open questions (remaining)

Each open question now carries an explicit **blocking disposition** for declaring Tier 0 "done." *(R1-F4)*

- **OQ-5 — Backend query stability.** Do Jaeger/Prometheus query APIs differ enough across the demo's pinned versions to need version-gated adapters? **Disposition: BLOCKING for S6.** Must be resolved by a dedicated API-shape probe/spike (plan **S5.5**) that records the v2.2.0 Jaeger/Prometheus query shapes **before** the FR-6 adapters are committed — the probe cannot live inside the step it gates. *(R1-S3)*
- **OQ-6 — Attestation as CI vs local/manual.** **Disposition: NON-BLOCKING for v1 "done."** v1 ships a manual re-attestation target (`make tier0-attest`) plus the freshness gate in §4; a scheduled/nightly CI job is deferred but the make target makes promotion to CI a one-line follow-up. Drift *detection* (not just capability) is therefore satisfied for v1 via the freshness gate. *(R1-S4)*

---

*v0.3 — Post-CRP-R1 triage. Applied R1-F1 (FR-4a security), R1-F2 (FR-5a schema versioning), R1-F3 (FR-5b + §4 deterministic acceptance), R1-F4 (OQ dispositions), and the requirements-side reflection of R1-S5 (FR-4b isolation). 10/10 R1 suggestions accepted (see Appendix A). No requirements deferred or rejected.*
*v0.2 — Post-planning self-reflective update. 2 requirements reframed (FR-3, FR-6), 4 added (FR-5, FR-7, plus FR-2/FR-9 hardened), 0 deferred, 4 open questions resolved, 6 quick wins surfaced.*

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
| R1-F1 | Security MUST clause on FR-4 (loopback default, TLS for non-loopback, egress note) | claude-opus-4-8 R1 | Applied as **FR-4a (Security, MUST)**. | 2026-06-18 |
| R1-F2 | Attestation declares own `schema_version` + compatibility policy | claude-opus-4-8 R1 | Applied as **FR-5a (Schema versioning, MUST)**; consumers reject unknown major. | 2026-06-18 |
| R1-F3 | §4 acceptance rows deterministically testable (query + threshold + window) | claude-opus-4-8 R1 | Applied: §4 table rewritten with exact query/threshold/window columns; encoded via **FR-5b**. | 2026-06-18 |
| R1-F4 | State OQ-5/OQ-6 blocking disposition | claude-opus-4-8 R1 | Applied in §5: OQ-5 **BLOCKING for S6** (probe S5.5); OQ-6 **NON-BLOCKING for v1** (manual `make tier0-attest` + freshness gate). | 2026-06-18 |

**Areas substantially addressed (post-R1):** FR-4 security/isolation; FR-5 schema versioning + self-describing acceptance; §4 deterministic acceptance; open-question blocking dispositions. Remaining R1 items are plan-side (see plan Appendix A: R1-S1…S6).

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-06-19

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-19 01:45:00 UTC
- **Scope**: Requirements-side concerns (Feature Requirements) the reflective loop could not self-catch — security gaps in FR-4, attestation versioning in FR-5, §4 acceptance testability, and OQ-5/OQ-6 blocking disposition.

**Executive summary**

- FR-4 authorizes an optional OTLP exporter but states *no* security requirements (TLS, auth, endpoint scoping, data egress) — "off by default" is not a substitute for a security clause.
- FR-5/FR-8 require recording the demo version + digests but never require the attestation to version *itself*; QW-1's reusable-contract promise depends on a declared schema version.
- §4 acceptance evidence is qualitative ("a `*_duration` / RPC metric series present", "non-empty service trace list") without exact queries, thresholds, or a time window — not deterministically verifiable.
- OQ-5/OQ-6 are listed as "remaining" but FR-5/FR-6/§4 acceptance depend on their answers; the requirements never state whether they are blocking for "done."

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | high | Add a security MUST clause to FR-4: the optional exporter MUST default to a loopback/host-only endpoint, MUST document that `insecure: true` is unauthenticated/unencrypted, MUST require TLS for any non-loopback target, and MUST note the data-egress scope (all demo telemetry leaves the boundary when enabled). | FR-4 currently reads "additive, off by default" with zero security constraints; an implementer copying the plan's `tls: insecure: true` to a routable endpoint leaks telemetry in cleartext. | §2 Backends — FR-4 ("Optional StartD8 fan-out (additive, off by default)") | Acceptance check: FR-4 enumerates TLS/auth/egress constraints; a test asserts the default exporter endpoint is loopback and a non-loopback target without TLS is rejected. |
| R1-F2 | Data | high | Extend FR-5 to require the attestation declare its own `schema_version` plus a stability/compatibility policy (what consumers must do on a major bump). | FR-5/FR-8 version the *demo* and digests but not the *artifact schema*; QW-1 ("reusable contract") and QW-4 (ContextCore consumer) cannot detect incompatible attestations without it. | §2 Coverage evidence — FR-5 ("a machine-readable `coverage-attestation.json`") | Schema includes a required `schema_version`; a consumer-side test rejects an unknown major version. |
| R1-F3 | Validation | high | Make §4 acceptance rows deterministically testable: for each row, specify the exact query string, the numeric threshold, and the lookback/time window (e.g., "≥1 `rpc.server.duration` series in the last 5m" instead of "a `*_duration` / RPC metric series present"). | The table mixes specific ("≥5 distinct `telemetry.sdk.language`") and vague ("a `*_duration` / RPC metric series present") criteria; vague rows can pass or fail nondeterministically depending on timing and metric naming. | §4 Coverage target — acceptance table (row "§2 Metrics \| a `*_duration` / RPC metric series present") | Each acceptance row maps 1:1 to a concrete query + threshold + window encoded in `coverage-attestation.json`; re-running yields the same verdict. |
| R1-F4 | Risks | medium | State explicitly whether OQ-5 and OQ-6 are **blocking** or **non-blocking** for declaring Tier 0 "done," and record the disposition in §4 or §5. | §4/S9 acceptance depend on adapter stability (OQ-5) and the attestation's freshness/drift story (OQ-6); leaving "done" silent on these lets Tier 0 be signed off while the drift-detection value (the doc's stated purpose) is unproven. | §5 Open questions — OQ-5 and OQ-6 | Requirements record a blocking/non-blocking decision per OQ with rationale; acceptance gate reflects it. |

**Endorsements / Disagreements**: None — Appendix C had no prior rounds at R1.
