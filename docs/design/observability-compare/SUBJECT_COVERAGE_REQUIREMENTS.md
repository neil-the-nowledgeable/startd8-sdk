# compare-live — Expanded Subject Coverage (multi-container + span-metrics standup)

**Version:** 0.3.1 (post-planning + lessons + design-principle hardening)
**Date:** 2026-07-24
**Status:** Draft — ready for CRP
**Parent:** `REQUIREMENTS.md` (shipped v1, single-image standup) — this specs the deferred **NR-1**
(multi-container) and **NR-2** (span-metrics) as the next increments. **Backlog:** EC-2 / EC-3.

---

## 0. Planning Insights (self-reflective update)

> The planning pass against the real code reshaped this spec more than the backlog framing implied.

| Backlog / v0.1 assumption | Planning discovery (grounded) | Impact |
|---|---|---|
| "Wire `SpanMetricsCollector` as an alternative Tier-B backend." | `SpanMetricsCollector` (`runtime_fidelity.py:269`) is a **loopback `otelcol-contrib` subprocess harness** for the behavioral suite; it exposes a `/metrics` *exposition* endpoint (`:8889`), **not a Prometheus query API**. compare-live's Tier-B (`run_validation`) replays PromQL against a Prometheus `/api/v1/query`. | **Not a backend swap.** The reusable part is `collector_config` (the config *text*, `runtime_fidelity.py:82`), run as a **container** in the standup, with a Prometheus scraping its `:8889`. The Tier-B replay is **unchanged/reused**. |
| The two items are separate L builds. | Both keep the **Prometheus-fronted** Tier-B; only the *standup topology* changes. Span-metrics is a **special case** of multi-container (the collector is one container; Prometheus scrapes `collector:8889` instead of `subject/metrics`; the subject is pointed at the collector via `OTEL_EXPORTER_OTLP_ENDPOINT`). | **One doc, one core mechanism, two increments.** Inc-1 = general multi-container standup; Inc-2 = a span-metrics **preset** built on Inc-1. |
| "Relax the `internal: true` egress-deny so Prometheus can scrape." | `internal: true` blocks **outbound to the internet**, NOT intra-network service-DNS. A Prometheus on the fleet net scrapes app services by DNS fine. `compose.py` already has an **`ingress` + `host_port`** mechanism (`generate_compose_dict`, `compose.py:79`) to publish one service on a host port. | **No egress relaxation.** Prometheus joins the fleet net (to scrape) and is published as the ingress (for the host `run_validation` to query). Correction to the backlog note. |
| `generate_compose_dict` is OB-shaped → big rewrite. | It takes **any** `fleet: tuple[ServiceSpec, ...]` (`ServiceSpec` is a general dataclass: `name/image/listen_port/dial_port/addr_env/deps/is_infra`). BUT it has OB-registry couplings: `get_service(ingress)` validates the ingress against the **global** `_SERVICES` registry (`services.py:88`), and `_service_block` derives contestant images from `image_namespace="r3"`. | **Reuse the topology mechanics; generalize the couplings** (validate ingress against the *passed* fleet; allow a stock `image` per service). More wiring than rewrite — but the couplings are the real L. |
| The subject is described from scratch. | Real multi-container apps almost always **already have a `docker-compose.yml`**. | Mottainai: prefer consuming the app's existing compose over re-describing it — but arbitrary compose (volumes/healthchecks/build) is complex. v1 takes a **lean subject-topology input**; consuming a real compose is an OQ/Increment-3. |

**Resolved open questions:**
- **OQ-1 (backend swap vs topology) → topology.** Both increments reuse `run_validation` unchanged; the work is standup topology + a Prometheus.
- **OQ-2 (one doc or two) → one doc, two increments** (span-metrics is a preset of multi-container).
- **OQ-3 (egress) → no relaxation needed** — publish Prometheus as ingress; scraping is intra-net.
- **OQ-4 (reuse SpanMetricsCollector) → no; reuse `collector_config` text as a container config.**

### 0.1 Lessons-Learned Hardening (v0.3)
Applied the SDK lessons:
- **Phantom-reference audit** — every symbol named (`generate_compose_dict`, `ServiceSpec`, `get_service`, `collector_config`, `stand_up_subject_and_prometheus`, `run_live_comparison`, `render_prometheus_yml`) grep-verified at the cited path (see §Reference Audit).
- **Prune phantom scope** — dropped "consume the app's real `docker-compose.yml`" from v1 (arbitrary compose is un-tractable for a first cut) to NR-3.
- **Single-source vocabulary ownership** — the Tier-B verdict taxonomy + `FidelityReport` stay owned by `validate_promql.py`; the span-metrics collector config stays owned by `runtime_fidelity.collector_config` (cited, not restated).

### 0.2 Design-Principle Hardening (v0.3.1)
- **Mottainai** — reuse `collector_config` (config text) and the compose topology mechanics instead of a new orchestrator; reuse `run_validation` verbatim. FR-6.
- **Accidental-Complexity anti-principle** — span-metrics is a *preset* of the multi-container mechanism, not a parallel code path; one standup engine, parameterized (FR-4). Resisted a second standup module.
- **Genchi Genbutsu** — the spec binds to the real interfaces (`generate_compose_dict` signature, the `:8889` exposition endpoint), correcting the backlog's "swap the backend" / "relax egress" proxies.
- **Context-Correctness-by-Construction** — a subject that can't be described / a container that never becomes ready → `unknown` (fail-loud), never a false `pass` (FR-5), mirroring the shipped scrape-gate.

---

## 1. Problem Statement

`compare-live` self-validates derived o11y by standing up the subject + a Prometheus and replaying the
derived PromQL. Today `stand_up_subject_and_prometheus` (`live_standup.py:213`) boots **one**
`subject_image`. Two common subject shapes can't be stood up (only reachable via `--prometheus
<existing-backend>`, i.e. the operator stands them up by hand):

| Subject shape | Current state | Gap |
|---|---|---|
| **Multi-container app** (Mastodon = web+PG+Redis+Sidekiq) | single-image only | can't stand up the app itself |
| **Traces-only / OTel-collector-fronted** (#274 class) | `/metrics` scrape only | no span-metrics collector in the standup |

**Honest scope:** both are already *validated* today via `--prometheus <existing>`. This is
**self-contained-standup convenience + coverage** — removing the manual setup — **not** missing
validation. The Tier-B replay engine (`run_validation`) is reused unchanged.

## 2. Requirements

### Increment 1 — Multi-container subject standup (NR-1 → built)
- **FR-1 Subject topology input.** `compare-live` accepts a **lean subject-topology** description (v1):
  an ordered list of containers `{name, image, port, deps?}`, plus which service Prometheus scrapes
  (`metrics_service` + `metrics_port` + `metrics_path`). Passed via a `--subject-compose <file.yaml>`
  (repeatable-free, one file). Single-image (`--subject-image`) remains the trivial 1-container case.
- **FR-2 Compose standup.** Build a compose from the topology (reusing `compose.py` topology mechanics —
  internal fleet net + service-DNS + dep-edge env) plus a **Prometheus** service that scrapes
  `metrics_service:metrics_port<metrics_path>`, published on a host port (the `ingress` mechanism).
- **FR-3 Readiness + warm-up.** Boot in dependency order; gate on the **existing** two-phase warm-up
  (`_await_scrape`: samples landed + series settled) against the stood-up Prometheus. Timeout →
  `unknown`. No new gate logic.

### Increment 2 — Span-metrics (OTel-collector-fronted) subject (NR-2 → built)
- **FR-4 Span-metrics preset.** `--subject-metrics-mode span-metrics` composes a **3-node preset** on
  the Inc-1 mechanism: `subject` (env `OTEL_EXPORTER_OTLP_ENDPOINT=collector:4317`) → an
  `otel/opentelemetry-collector-contrib` container running **`collector_config`** (reused text) →
  Prometheus scrapes `collector:8889/metrics`. No `/metrics` on the subject is required.
- **FR-5 Fail-loud.** If the collector never exposes `:8889` or no span-metric series settle → `unknown`
  (never `fail`) — the subject may not be emitting traces; do not conflate with a dead SLI.

### Cross-cutting
- **FR-6 Reuse, don't rebuild.** Tier-B replay = `run_validation` unchanged; span-metrics config =
  `runtime_fidelity.collector_config`; topology = generalized `generate_compose_dict`. New code is the
  standup glue + the topology input parser, not a new engine.
- **FR-7 Teardown & safety.** Extend the existing best-effort `tear_down` to remove **all** compose
  containers + networks + temp files, on every path (the shipped `finally` + `startd8-cmp-<hex>`
  contract, generalized to N containers).

## 3. Non-Requirements
- **NR-A** Consuming the app's real `docker-compose.yml` verbatim (volumes/healthchecks/build) — a lean
  topology input only in v1; real-compose ingestion is a later increment.
- **NR-B** Kubernetes / non-docker standup.
- **NR-C** Changing the Tier-B replay, verdict taxonomy, merge, or CI-gate — all reused unchanged.
- **NR-D** Scoring/attribution across services (that is the round-3 fleet benchmark, not compare-live).

## 4. Open Questions
- **OQ-A** Topology input format: a bespoke lean YAML (FR-1) vs a **subset** of docker-compose syntax
  (`services: {image, ports, depends_on}`) so operators reuse familiar shape without full-compose
  complexity. Lean-YAML for v1; revisit.
- **OQ-B** Generalize `generate_compose_dict` in place (validate ingress against the passed fleet;
  per-service stock `image`) vs a new leaner `observability/live_compose.py` that reuses only the
  network/DNS/ingress *patterns*. Planning leans **new leaner module** to avoid coupling compare-live to
  `benchmark_matrix`.
- **OQ-C** Effort: Inc-1 ≈ **M-L** (topology parser + compose gen + N-container standup/teardown); Inc-2
  ≈ **M** on top (a preset + the collector container). Not the "L from scratch" the backlog implied.

## 5. Reference Audit
| Symbol | Path | Verified |
|---|---|---|
| `stand_up_subject_and_prometheus`, `_await_scrape`, `tear_down`, `render_prometheus_yml` | `observability/live_standup.py` | ✓ |
| `run_live_comparison`, `run_validation` (reused) | `observability/compare_live.py` / `validate_promql.py` | ✓ |
| `generate_compose_dict(fleet, *, ingress, host_port)`, `ServiceSpec` | `benchmark_matrix/fleet/compose.py` / `services.py` | ✓ |
| `get_service` (global-registry coupling), `topo_order` | `benchmark_matrix/fleet/services.py` | ✓ |
| `collector_config`, `:8889` prom exporter | `observability/runtime_fidelity.py` | ✓ |

---

*v0.3.1 — post-planning + hardening. Reframed 5 assumptions (backend-swap→topology; two-items→one-doc-two-increments; egress-non-issue; compose-reusable-but-coupled; lean-input-not-real-compose). Effort re-estimated M-L+M, not 2×L. Ready for CRP.*
