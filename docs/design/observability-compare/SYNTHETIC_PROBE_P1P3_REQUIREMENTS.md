# Synthetic-Probe SLI — P1–P3 (runner spec · live pending-probe verdict · link-aware) — Requirements

**Version:** 0.3.1 (post planning + lessons + design-principle hardening; ready for CRP)
**Date:** 2026-07-23
**Status:** Draft — spec only, no code
**Owner:** observability artifact generator (`src/startd8/observability/`)
**GitHub:** startd8-sdk **#308**, Phases **P1/P2/P3** (P0 shipped, PR #312)
**Refs:** `SYNTHETIC_PROBE_SLI_DESIGN.md` (the P0–P3 frame), `SYNTHETIC_PROBE_P0_REQUIREMENTS.md` (v0.4,
IMPLEMENTED), option-b2, #300 D2 / #307 (the declared-lane patterns)

---

## 0. Planning Insights (Self-Reflective Update)

> What the planning pass (reading `validate_promql`, `compare_live`, the extended-artifact + secret-
> reference emitters) corrected from the naïve "run the probe and bind the SLI" draft.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| P1 writes the freshness SLO to `slos/` (finally emitting the P0-deferred SLO). | The metric is published only when the probe **actually runs** (deploy-time, P2), not when the runner *spec* is emitted (P1). Writing the SLO at P1 reintroduces the exact R1-F1 dead-SLI leak P0 closed. | **P1 emits only the runner SPEC** (a non-PromQL artifact); the freshness SLO stays in `pending_probes` until a **live run confirms binding (P2)**, then is promoted to `slos/`. The lifecycle is declared→runner→live-confirmed→SLO. |
| The runner spec needs new exclusion plumbing so `validate_promql` skips it. | `validate_promql._EXCLUDED_ARTIFACT_DIRS` already excludes non-PromQL sibling dirs (`service-monitors`/`loki-rules`/`notifications`/`runbooks`) by subdir. | **Add one entry** (`probe-specs → probe_spec`); the runner spec rides the existing exclusion seam. No new mechanism. |
| The probe needs bespoke secret handling. | The notification-policy path already has a **reference-secrets-never-fabricate** discipline (`Receiver.target` → `# UNRESOLVED REQUIRED PARAM:` on a dangling ref). | **Reuse it:** the runner spec references credentials by name (env/secret ref), never inlines them; a missing ref is emitted as an explicit unresolved marker, not a fabricated token. |
| P2's "pending-probe" is a new verdict engine. | `compare_live`/`validate_promql` already have a closed verdict taxonomy (`pass\|fail\|bound_no_data\|error\|excluded`) + a rollup where `unknown > fail > pass`, and `fr_coverage` is already threaded into the merge. | **Add ONE verdict value** `pending_probe` (a metric that's *expected-absent until the runner runs* — NOT a `fail`/dead SLI), keyed off the `pending_probes` fr_coverage the P0 lane already emits. Reuse the taxonomy + rollup; do not restate. |
| P3 link-aware cross-trace is buildable now. | It needs **Tempo trace data with span links** (`FeedInsertWorker`→enqueue) to compute the delta; there is no trace-query client or link fixture in-repo, and the analysis is novel (most connectors don't do cross-trace link math). | **P3 = the alternative track:** specify the algorithm + a testable pure-function core (given two linked spans, compute the delta) but gate live validation on a trace fixture (OQ). Do NOT fake a live proof. |

**Resolved (from the design doc OQs):**
- **OQ-1 (runner artifact) → a portable `probe-spec.yaml`** (declarative; one concrete runner recipe
  documented) — the SDK emits the spec, an operator/runner executes it (mirrors ServiceMonitor/alert: emit,
  don't run). **OQ-2 (credentials) → secret-reference discipline** (reuse notification-policy). **OQ-5
  (compare semantics) → the `pending_probe` verdict** (FR-P2-1).

### 0.1 Lessons-Learned Hardening (v0.3)
- **Phantom-reference audit** — verified: `_EXCLUDED_ARTIFACT_DIRS` (`validate_promql.py:274`), the verdict
  taxonomy (`compare_live`/`validate_promql` `ExprVerdict.verdict`), `_EXTENDED_PER_SERVICE_GENERATORS`
  (`artifact_generator.py:214`), the notification-policy secret discipline, the P0 `pending_probes` lane
  (shipped #312). Added §9.
- **[verify-consumer-against-merged-diff]** — the P2 live-binding proof is gated on a REAL Tempo/Mastodon
  surface; it is NOT claimed complete from unit tests (the SDK harness is unit-tested, the live proof is an
  external run — §5, OQ).
- **Single-source vocabulary ownership** — the verdict taxonomy stays owned by `validate_promql`; P2 adds a
  value, never a parallel enum. The published-metric contract stays owned by the `DeclaredProbe` (P0).

### 0.2 Design-Principle Hardening (v0.3.1)
- **Genchi Genbutsu / not-fabrication** — the runner spec references real credentials (never inlines/fakes);
  the SLO is promoted to `slos/` only after a **real** live run confirms the metric exists (not on faith).
- **Mottainai** — reuse the exclusion dir, the verdict taxonomy+rollup, the secret discipline, the P0
  `pending_probes` lane; build no parallel machinery.
- **Accidental-Complexity anti-principle** — P1 adds one artifact type + one exclusion entry; P2 adds one
  verdict value. No new engines.
- **Hitsuzen** — the runner spec is deterministic from the `DeclaredProbe`; only the *measurement* is
  runtime. Emit the determinable spec; run nothing at generation time.

---

## 1. Problem Statement

P0 (shipped) records a freshness SLI as `pending_probes` — a positive finding, statically, at $0. But it is
*inert*: nothing runs the probe, so the metric is never published and the SLO never binds. P1–P3 close that:
**P1** emits a runnable probe spec (so an operator can run it); **P2** teaches `compare-live` that a
probe SLI is *pending a run* (not a dead SLI) and promotes it to a real SLO once a live run confirms binding;
**P3** offers a trace-native alternative (follow the span link, compute the delta) needing no synthetic
traffic. P1 is deterministic/$0; P2 is an SDK harness + an external live run; P3 is novel + trace-gated.

## 2. Requirements

### P1 — runner spec emission (deterministic, $0)

**FR-P1-1 — Emit a `probe-spec.yaml` runner artifact.** For each `DeclaredProbe`, emit
`probe-specs/{svc}-{name}-probe.yaml`: a declarative runner recipe carrying `{name, action, poll, assert,
measure, interval, timeout, published_metric, metric_kind}` + a `runner` block (a blackbox-style recipe:
how to run the action, poll for the assertion, and publish the measured latency as `published_metric`). One
concrete runner recipe (e.g. a Python/HTTP loop or a k8s CronJob shape) is documented as the reference.

**FR-P1-2 — Secret-reference discipline (reuse, never fabricate).** Credentials the action/poll need (API
token, base URL) are carried as **references** (`${SECRET:...}`/env names), never inlined; a required-but-
undeclared ref is emitted as `# UNRESOLVED REQUIRED PARAM:` exactly as the notification-policy path does.

**FR-P1-3 — Excluded from PromQL replay.** Add `probe-specs → probe_spec` to
`validate_promql._EXCLUDED_ARTIFACT_DIRS` — the runner spec carries no PromQL, so it is enumerated as a
deliberate exclusion, never a fidelity miss.

**FR-P1-4 — The SLO is NOT promoted to `slos/` at P1.** The freshness SLO stays in `pending_probes`
(reason_code advances to `probe_runner_emitted` — a runner exists but hasn't run). No `slos/` file yet
(promotion is P2, post-live-confirmation). Byte-identity when no probes (additive only).

### P2 — live pending-probe verdict + SLO promotion (SDK harness $0; live proof external)

**FR-P2-1 — A `pending_probe` verdict (NOT a dead SLI).** `compare-live` classifies a probe SLI whose
metric is absent from the backend as `pending_probe` — a metric *expected-absent until the runner runs* —
using the `pending_probes` fr_coverage as the key. It is **excluded from the `fail`/dead-SLI set and the CI
gate** (a pending probe must never fail the build as a #274 regression). Reuses the verdict taxonomy + rollup.

**FR-P2-2 — SLO promotion on live confirmation.** When a live run DOES return data for the probe metric,
`compare-live` reports the freshness SLI as **bound** (verdict `pass`), and the SLO is eligible for
promotion to `slos/` (the P0-deferred SLO, now grounded). Promotion is explicit (a flag/step), never
automatic on a single scrape (mirror the compare-live warm-up discipline).

**FR-P2-3 — Live proof is an external run (honesty).** The end-to-end "run against a real Mastodon, show it
binds" is an **external** live run (needs a running Mastodon + credentials + the runner). P2's SDK code
(verdict + promotion) is unit-tested with a fixture; the live proof is documented as a manual/CI-with-subject
step, NOT claimed from unit tests.

### P3 — link-aware cross-trace freshness (novel; trace-gated)

**FR-P3-1 — A pure delta-compute core.** Specify + implement a pure function: given the enqueue span and the
linked `FeedInsertWorker` span (start/end timestamps + the span link), compute the fan-out freshness delta
`t(feed-visible) − t(created)`. Unit-testable on synthetic span inputs (no network).

**FR-P3-2 — Trace-native, no synthetic traffic.** Document that this grounds freshness by following the real
`propagation_style: :link` span link — an alternative to the P1 synthetic probe (no injected statuses).

**FR-P3-3 — Live validation is trace-gated (OQ).** A real proof needs Tempo traces carrying the link; P3
ships the algorithm + pure-core tests, and gates the live binding on a trace fixture/OQ — not faked.

## 3. Non-Requirements

**NR-1 — P1/P2/P3 run nothing at generation time.** The SDK emits specs and classifies; it does not execute
probes or query Tempo during artifact generation.
**NR-2 — No fabricated credentials or metrics.** (Genchi Genbutsu.)
**NR-3 — No new verdict engine / no parallel exclusion mechanism.** Reuse the taxonomy + the exclusion dir.
**NR-4 — P3 is the alternative track, not a P1 replacement.** They coexist (synthetic vs trace-native).
**NR-5 — No auto-promotion of a pending SLO on a single scrape** (warm-up discipline).

## 4. Open Questions

- **OQ-1 — runner recipe surface.** Which ONE concrete runner does the reference recipe target — a portable
  Python/HTTP loop (zero infra) or a k8s CronJob (cluster-native)? Lean: the portable loop as the reference,
  the CronJob shape documented.
- **OQ-2 — P2 promotion trigger.** A `--promote-probes` flag on `compare-live`, or a separate `promote`
  verb? Lean: a flag, gated on ≥2 consecutive live scrapes (warm-up).
- **OQ-3 — P3 trace client.** Does the SDK gain a minimal Tempo trace-query client for P3, or does P3 consume
  an exported trace file? Lean: consume a trace file (no live Tempo dependency in the SDK) for v1.
- **OQ-4 — ContextCore carry.** `declared_probes` carry (shared with P0) — still pending cross-repo.

## 9. Reference Audit

| Symbol / fact | Location | Exists? |
|---|---|---|
| `_EXCLUDED_ARTIFACT_DIRS` (add `probe-specs`) | `validate_promql.py:274` | ✅ |
| verdict taxonomy `pass\|fail\|bound_no_data\|error\|excluded` (add `pending_probe`) | `validate_promql.py:556` | ✅ |
| rollup `unknown > fail > pass` + `fr_coverage` merge | `compare_live.py:34/101` | ✅ |
| `_EXTENDED_PER_SERVICE_GENERATORS` (add the probe-spec generator) | `artifact_generator.py:214` | ✅ |
| notification-policy secret-reference discipline | `generate_notification_policy` | ✅ |
| P0 `pending_probes` lane (the P2 key) | shipped #312 | ✅ |
| `generate_declared_probe_spec` / `pending_probe` verdict / link-delta core | — | ❌ to add |
| Live Mastodon/Tempo surface (P2 live, P3 validation) | external | ⏳ not in-repo |

---

*v0.3.1 — Post planning + lessons + design-principle hardening. 5 assumptions corrected, design-doc OQs
resolved, 10 FRs (P1 4 / P2 3 / P3 3) / 5 NRs / 4 OQs. Deterministic parts (P1, P2-harness, P3-core) are
$0/unit-testable; live proofs (P2-live, P3-validation) are external. Ready for CRP. No code yet.*
