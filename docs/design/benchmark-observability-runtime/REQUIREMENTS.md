# Runtime Observability-Fidelity Benchmark Dimension — Requirements

**Version:** 0.3.1 (Post design-principle hardening — ready for CRP)
**Date:** 2026-07-10
**Status:** Draft (reflective loop; pre-CRP)
**Relates to:** `ContextCore/docs/design/FIDELITY_BENCHMARK_CONVERGENCE.md` (B1 runtime form); the shipped **static** form (`observability_fidelity_static.service_observability_coverage`, `CellResult.observability_coverage`, scorecard D6); `metric_descriptor` / `validate_promql` (Group C fidelity harness).

---

## 0. Planning Insights (Self-Reflective Update)

> Grounded by reading the behavioral harness (`benchmark_matrix/behavioral/execute.py`,
> `sandbox.py`, `contract.py`) and the OTel seeds. The exploration corrected the naive
> "just run a collector next to the service" plan on five points:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The sandbox blocks all networking, so a collector can't work | Egress is denied but **loopback (127.0.0.1) is explicitly allowed** (macOS Seatbelt `allow network-*bound local localhost`; Linux `unshare -rn` leaves only loopback) | The whole topology (service → collector → Prometheus → replay) is feasible **entirely on loopback** — FR-3 |
| The generated service emits metrics we can scrape | **Services are gRPC-only; they emit NO OTel telemetry today** (seeds specify the proto contract only; nothing injects OTel SDK or `OTEL_EXPORTER_OTLP_ENDPOINT`) | The load-bearing fork (FR-2): either the **model** instruments (measures model skill, changes the behavioral comparison) or the **harness auto-injects** instrumentation (measures deployment observability). Chosen: harness auto-inject |
| `calls_total` comes from the app's meters | The span-metrics-connector derives `calls_total`/`duration_milliseconds` from **spans (traces)**, not app metrics | The service must export **OTLP traces**; server-span auto-instrumentation produces exactly these with zero model effort — FR-2 |
| Go/Python/Node auto-instrument the same way | Auto-instrumentation is a **per-language agent**: Python (`opentelemetry-instrument`), Node (`--require @opentelemetry/auto-instrumentations-node`), Java/C# (agents) — but **Go has no runtime auto-instrument** (needs build-time SDK or eBPF); the benchmark's checkoutservice is Go and runs a pre-built binary | FR-2/NR-3: ship **Python-first**, degrade-honest for languages we can't auto-instrument. Go is out of v1 |
| Reuse `validate_promql` → needs a full Prometheus | `validate_promql` queries a Prometheus `/api/v1/query`; the collector's prometheus exporter is a `/metrics` scrape surface, not a query API | Query-surface decision (OQ-2): a minimal Prometheus scraping the collector, **or** a lighter "scrape `/metrics` and check the metric+labels exist" binding-only mode |
| The benchmark has generated observability to replay | It generates **service code only**, no observability artifacts per cell | Referenced PromQL is **synthesized from the `MetricDescriptor`** (the RED template the generator itself uses) — no per-cell observability generation needed. FR-5 |

**Resolved open questions:**
- **OQ-A → harness auto-inject, not seed-require.** Instrument the service at launch (deployment property), so the term measures "does the running service produce the RED surface under standard observability tooling" — not the model's OTel-coding skill (which would contaminate the behavioral comparison, NR-3).
- **OQ-B → reported-not-scored, like static B1 + behavioral D6.** Never folded into `quality`.
- **OQ-C → referenced = descriptor-synthesized RED**, reusing `resolve_descriptor` (Mottainai).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK/design-doc lessons before CRP:

- **[Phantom-reference audit]** — the harness seams this leans on exist: `run_behavioral_cell` /
  `run_service_sandboxed` (`behavioral/execute.py`), `sandbox.py` isolation, `resolve_serve_command`
  (`contract.py`), `resolve_descriptor` (`metric_descriptor.py`), `validate_promql` binding logic,
  `CellResult`. **To verify at build:** `extract_service_hints` lives in `observability/` — confirm
  it's importable from the behavioral harness or move it to shared code (§Reference-Audit). The
  `otelcol-contrib` span-metrics connector is external and must be vendored (OQ-4).
- **[Prune phantom scope]** — Go/eBPF instrumentation → NR-5; a full Prometheus/Grafana stack → NR-2;
  per-cell observability generation → dropped (descriptor is the template, FR-5).
- **[Single-source vocabulary]** — the fidelity verdict/coverage vocabulary is owned by the shared
  `verification` core + `validate_promql`; this doc **cites** them (FR-4/FR-6), never restates the
  binding rule, so runtime and static/BPI fidelity can't diverge.
- **[CRP steering]** — brand-new doc (least-reviewed). Settled: auto-inject (not seed-require),
  reported-not-scored, loopback-only, descriptor-referenced.

**§Reference-Audit (to verify / create):**

| Symbol | Where | Status |
|--------|-------|--------|
| `extract_service_hints` reachable from behavioral | `observability/` → behavioral | verify / hoist to shared |
| collector binary + span-metrics config | provisioned at prepare time | to create (OQ-4) |
| auto-instrument wrappers (Python/Node) | new launch-wrap in `behavioral/` | to create (FR-2) |
| `runtime_observability_coverage` / `observability_runtime` | `CellResult` | to create (FR-6) |

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked the draft against the design principles. Each changed the draft:

- **[Genchi Genbutsu]** — the entire thesis: don't infer from source, **run the service and observe
  its actual emitted telemetry**. Ground truth = the service's own live-derived metrics (FR-2/FR-5).
- **[Context-Correctness — no silent green]** — the load-bearing risk: a collector that fails to
  start, a language that can't be auto-instrumented, or a connector that never converges must **not**
  read as a clean pass or a model failure. FR-7's three-way split (degraded / no-telemetry / bound)
  + FR-8's convergence gate are the guard. Strengthened FR-7 to be explicit that `degraded` ⇒
  `coverage=None` (excluded), never 0.0 (which would read as "the model failed").
- **[Accidental-Complexity]** — the runtime stack (auto-instrument agent + collector + query surface)
  is itself a fleet of failure modes. **Resolved OQ-2 toward the lighter path for v1**: the binding
  question needs only *metric + label presence*, so v1 **scrapes the collector's `/metrics` and
  checks presence** — **no Prometheus binary** (one fewer moving part). Full-Prometheus
  `validate_promql` replay (histogram_quantile evaluation) is a later fidelity upgrade, not v1.
- **[Mottainai]** — reuse `resolve_descriptor` (the generator's own resolution) for the referenced
  side and the shared binding logic for the verdict; the collector's `/metrics` is the same
  Prometheus series `validate_promql` would query, so the check is the same, minus the query engine.

*(No Hitsuzen action — deterministic replay, nothing LLM-generated.)*

---

## 0.3 Spike Validation (2026-07-10)

> The collector-in-sandbox spike (throwaway prototype + report on its worktree branch)
> confirmed the load-bearing feasibility and corrected one requirement:

- **Feasible, no `sandbox.py` change.** `otelcol-contrib` runs under the repo's own
  `run_service_sandboxed` seatbelt loopback-only profile; OTLP receive (4317) + prometheus
  export (8889) on 127.0.0.1 work while **egress stays denied** (proven with a negative
  control: in-sandbox connect to `1.1.1.1:443` → `PermissionError`; loopback succeeds).
- **RED surface binds 4/4** against the real `span-metrics-connector` profile:
  `calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}` +
  `...OK}` + `duration_milliseconds_bucket`. Scrape-and-match (FR-4) viable with a ~20-line
  text parser; `extract_service_hints` confirmed importable.
- **FR-8 corrected** → poll for **non-zero** throughput (see FR-8).
- **Config is load-bearing:** 4 non-obvious knobs separate "binds" from "silently unbound"
  (`namespace: ""`, no explicit `span.kind` dimension, `resource_to_telemetry_conversion`,
  `telemetry.metrics.level: none`). Ship the spike's config verbatim (Step 0).

## 1. Problem Statement

The shipped **static** observability-readiness term (B1) reads the generated *source* and is
deliberately **optimistic**: it assumes a service with a server transport is auto-instrumented, so
it catches the *floor* (no observable surface) but not "the instrumentation is subtly broken." The
only way to know for sure is to **run the service and see what it actually emits** — genchi
genbutsu. The benchmark is uniquely positioned for this because the **behavioral cell already
starts the service**. The runtime form closes the loop: instrument the running service, let it emit
telemetry, derive the RED metrics, and replay the RED PromQL against the service's **own live
metrics** with the exact BPI fidelity harness.

| Component | Static form (shipped) | Runtime gap |
|-----------|----------------------|-------------|
| Ground truth | source-declared/implied metrics | the service's **actual emitted** telemetry |
| Confidence | optimistic (wiring present ≠ working) | proven (metrics observed live) |
| Signal | observability-readiness | observability-**fidelity** (binding against real series) |

**Goal:** for a behavioral cell, produce a **runtime** `observability_coverage` = the fraction of the
RED PromQL that binds against the service's own live-derived metrics — reported-not-scored, opt-in,
degrade-honest, on loopback inside the existing sandbox.

---

## 2. Requirements

### Group A — Orchestration

- **FR-1 — Opt-in, gated on behavioral.** A `runtime_observability` flag (default **off**), valid
  only when `behavioral` is on (it needs the running service). Off ⇒ byte-identical to today.

- **FR-2 — Harness-injected auto-instrumentation (deployment property, not model skill).** At
  launch the harness wraps the service in its language's OTel **auto-instrumentation agent** and
  injects `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:{otlp_port}` +
  `OTEL_TRACES_EXPORTER=otlp`. Server-span auto-instrumentation yields the traces the span-metrics
  connector needs. **Python-first** (`opentelemetry-instrument`); Node next; **languages with no
  runtime auto-instrument (Go) are out of scope for v1** and degrade-honest (FR-7).

- **FR-3 — Collector sidecar on loopback.** A provisioned OTel Collector (OTLP receiver →
  span-metrics connector → prometheus exporter) runs as a sidecar subprocess in the same sandbox,
  bound to `127.0.0.1` only (egress stays denied; loopback is allowed). Lifecycle: start collector →
  await ready → start service → run the behavioral suite (traffic = the spans) → **settle** →
  replay → tear **both** down unconditionally.

- **FR-4 — Query surface (v1 = scrape-and-match; Accidental-Complexity §0.2).** v1 scrapes the
  collector's prometheus-exporter `/metrics` and checks that each descriptor RED series (metric name
  + service-identity label + error selector) is **present** — the binding question, with **no
  Prometheus binary**. The presence check uses the **same descriptor-driven binding logic** as
  `validate_promql` (via the shared `verification` core), so runtime and BPI fidelity agree. A
  later upgrade adds a minimal Prometheus + full `validate_promql` replay (`histogram_quantile`
  evaluation) for services that warrant it.

### Group B — Signal

- **FR-5 — Referenced PromQL = descriptor-synthesized RED.** Reconstruct the service's
  `MetricDescriptor` (via the generator's own `resolve_descriptor`/`extract_service_hints`) and
  synthesize the canonical RED queries (throughput, latency p99, error ratio). No per-cell
  observability-artifact generation — the descriptor is the template (Mottainai).

- **FR-6 — Runtime coverage, reported-not-scored.** Store `runtime_observability_coverage` (float)
  + provenance (`observability_runtime`: profile, traces_received, metrics_seen, per-query binding)
  on `CellResult`; surface a scorecard sub-dimension. It **never** folds into `quality`/composite
  (parallels static B1 + behavioral D6).

### Group C — Honesty

- **FR-7 — Degrade-honest, three-way (never a silent green, never model-blamed unfairly).**
  Distinguish: **degraded** (collector didn't start / language not auto-instrumentable / connector
  didn't converge → harness gap, `runtime_observability_coverage=None`, NOT a fail); **no-telemetry**
  (service ran but emitted **zero** traces → an instrumentation/service gap, a real *low* signal, not
  a crash); **bound/unbound** (traces flowed, metrics derived, PromQL replayed → the real coverage).
  Mirrors the benchmark's `degraded` vs `model_fault` split (FR-32) and the fidelity harness's
  `unknown` vs `fail`.

- **FR-8 — Convergence gate (poll for NON-ZERO throughput).** After the suite generates traffic,
  **poll** the query surface until the throughput metric is **present AND non-zero** (spike finding:
  the first scrape can read `calls_total 0` for a beat — the counter delta hasn't accumulated — while
  the histogram is already correct; a present-only check would false-early) or a bounded timeout.
  Timeout with zero throughput ⇒ `no-telemetry` (FR-7), never a false pass. **Settle default 8s /
  cap 15s** (convergence measured at median 2.7s, max 3.8s cold).

- **FR-9 — Bounded added cost.** Collector boot + settle + replay must stay within the cell budget
  (`per_run_timeout_s`); target ≤ +30s/cell. The whole dimension is opt-in (FR-1), so the default
  fleet cost is unchanged.

---

## 3. Non-Requirements

- **NR-1 — Not scored.** Never folded into composite quality / the Scoreboard ranking.
- **NR-2 — Not a full observability stack.** Minimal collector (+ optional minimal Prometheus) on
  loopback; no Grafana, no Tempo, no persistence beyond the cell.
- **NR-3 — Not measuring the model's OTel-coding skill.** Instrumentation is harness-injected so the
  term is a *deployment* property; requiring the model to write OTel would change the behavioral
  comparison and is out of scope (a separate, legitimate future dimension).
- **NR-4 — Not replacing the static form.** Static B1 runs on every cell ($0); runtime is the deeper
  opt-in that confirms it. A static-vs-runtime disagreement is itself a useful signal (future).
- **NR-5 — Not Go/eBPF instrumentation in v1.** Languages without a runtime auto-instrument agent
  degrade-honest; build-time/eBPF instrumentation is a later phase.
- **NR-6 — Not external network.** Egress stays denied; everything is loopback.

---

## 4. Open Questions

- **OQ-2 → resolved (FR-4, §0.2):** v1 = **scrape-and-match** (no Prometheus binary); full-Prometheus
  `validate_promql` replay is a later upgrade.
- **OQ-3 — Language coverage:** confirm which auto-instrument agents run under the sandbox's
  resource caps (Python `opentelemetry-instrument`, Node `--require`). Java/C# agents are heavier.
  Go is deferred (NR-5). What fraction of the OB suite is thereby covered in v1? (Python services
  only — quantify.)
- **OQ-4 → resolved (spike):** vendor `otelcol-contrib` **v0.156.0** per platform at prepare time.
  Boot median 0.32s (max 1.5s cold), RSS ~136 MB — within the sandbox's 2 GB / timeouts.
- **OQ-5 → resolved (spike):** settle default **8s / cap 15s** (convergence median 2.7s).

---

*v0.3.1 — Post-planning self-reflective update (6 assumptions corrected, OQs resolved: auto-inject /
reported-not-scored / descriptor-referenced / scrape-and-match), lessons hardening (§0.1: reference
audit + single-source citation), design-principle hardening (§0.2: Genchi Genbutsu run-and-observe;
Context-Correctness no-silent-green ×2 → FR-7/FR-8; Accidental-Complexity → v1 drops the Prometheus
binary; Mottainai reuse descriptor + binding logic). Ready for CRP review.*
