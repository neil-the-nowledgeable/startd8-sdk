# compare-live — Expanded Subject Coverage (multi-container + span-metrics standup)

**Version:** 0.3.2 (post-review — adds FR-8 warm-up traffic; FR-6/OQ-B flagged for CRP)
**Date:** 2026-07-24
**Status:** Draft — ready for CRP (one open decision: OQ-B, see §0.3)
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

### 0.3 Review Response (2026-07-24)

> A code-review of v0.3.1 + a 4-scope reuse hunt (`TRAFFIC_DRIVER_REUSE_MAP.md`) surfaced:

- **[High] Inc-2 would degrade to always-`unknown` — no traffic driver.** Grounded: `stand_up_subject_and_prometheus` (`live_standup.py:229-278`) boots + scrapes but drives **no** requests, and span-metrics
  emit nothing until the subject is exercised. **Resolved by FR-8** (warm-up traffic reusing an existing
  driver — `run_smoke`/`run_journey_http`/`run_journey`; no new engine).
- **[Medium — OPEN for CRP] FR-6 vs OQ-B contradiction.** FR-6 states topology = "generalized
  `generate_compose_dict`," but OQ-B leaves the approach open and *leans the other way* (a new leaner
  `observability/live_compose.py` reusing only the net/DNS/ingress patterns). The coupling is real —
  `generate_compose_dict` validates `ingress` against the **global OB `_SERVICES` registry**
  (`compose.py:94` → `services.py:88`), which an arbitrary compare-live subject fails. **CRP must decide
  OQ-B and align FR-6.** Recommendation: the new-leaner-module path (avoid coupling compare-live to
  `benchmark_matrix`; generalizing in place would fork the registry validation).
- **[Low] Multi-container × span-metrics composition underspecified** (FR-1 topology + FR-4 preset
  interaction); Prometheus-is-the-ingress joins **two** networks (fleet + edge) — state it explicitly.

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
- **FR-8 Warm-up traffic (the Inc-2 enabler).** Span-metrics (and lazily-registered RED series) emit
  **no series until the subject handles a request** — so the standup, which today only boots + scrapes
  (`live_standup.py:229-278`), must **drive bounded traffic at the subject's ingress before the readiness
  gate**, else Inc-2 degrades to always-`unknown`. **v1 adds no engine — it reuses an existing SDK
  driver, selected by subject shape:**
  - arbitrary OpenAPI app → **`run_smoke(base_url)`** (`deploy_harness/smoke.py:70`) — schema-discovered
    CRUD round-trip;
  - OB-shaped HTTP → **`run_journey_http(httpx.Client)`** (`benchmark_matrix/fleet/frontend_gate.py:49`);
  - OB-shaped gRPC → **`run_journey(addr_map)`** (`benchmark_matrix/fleet/adapter_b.py:227`).

  Loop the chosen driver until the span-metric series **settle** (reuse the existing two-phase `_await_scrape`
  gate on series-count stability) or **timeout → `unknown`** (fail-loud, per FR-5). **Realistic-load upgrade
  (optional):** a locust loadgenerator **as a sidecar in the FR-2 compose** (`FRONTEND_ADDR=<ingress>`),
  lifted from `online-boutique-*/loadgenerator` — it rides the multi-container mechanism already built,
  adding no standup code. Full grounding + options: **`TRAFFIC_DRIVER_REUSE_MAP.md`** (this dir) and the
  cross-project catalog `~/Documents/tools/load-generators/README.md`.

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
| FR-8 drivers: `run_smoke` `deploy_harness/smoke.py:70` · `run_journey_http` `fleet/frontend_gate.py:49` · `run_journey` `fleet/adapter_b.py:227` | startd8-sdk | ✓ |

---

*v0.3.2 — post-review. Added FR-8 (warm-up traffic, reuses existing drivers — resolves the [High]
always-`unknown` gap); flagged the FR-6/OQ-B contradiction for CRP (§0.3). Reuse grounding in
`TRAFFIC_DRIVER_REUSE_MAP.md`.*
*v0.3.1 — post-planning + hardening. Reframed 5 assumptions (backend-swap→topology; two-items→one-doc-two-increments; egress-non-issue; compose-reusable-but-coupled; lean-input-not-real-compose). Effort re-estimated M-L+M, not 2×L.*

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
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-24

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-24 18:40:00 UTC
- **Scope**: Requirements-quality review (unambiguity / completeness / testability / traceability), grounded in `compose.py`, `services.py`, `live_standup.py`, and the FR-8 driver signatures. Focus-file asks 1–4 answered first.

##### Focus-file asks (answered before standard suggestions)

**Ask 1 — OQ-B: generalize `generate_compose_dict` in place vs new `observability/live_compose.py`.**
- **Summary answer:** New leaner module — but the coupling is *deeper* than the doc states, which strengthens the case.
- **Rationale:** The doc names two OB couplings (ingress validation `compose.py:94→services.py:88`; `image_namespace="r3"`). Grounding surfaced a **third, more pervasive** one the doc misses: `_service_block` (`compose.py:57`) resolves **every** dependency edge through the global registry — `dep = get_service(dep_name)` — to derive `{addr_env}: {peer}:{dial_port}`. An arbitrary compare-live subject whose deps aren't in `_SERVICES` `KeyError`s on *dep fan-out*, not just ingress. Conversely the image coupling is *already soft*: `_service_block:42` uses `spec.image` when set and only falls back to the `r3` namespace when `image is None`, so a per-service stock image needs no change. Net: generalizing-in-place must fork **two** `get_service` call-sites (ingress + dep fan-out) plus thread `addr_env`/`dial_port` off the passed fleet — that is a behavior fork of `benchmark_matrix`'s hot path, risking Round-3 regressions. A new module reusing only the net/DNS/ingress *patterns* isolates that risk.
- **Assumptions / conditions:** The new module must still carry the §0 faithfulness traps generically (dep-edge env injection, listen≠dial remap) — i.e. it reuses the *mechanism* (`_service_block`'s env/network logic) but sources dep addresses from the passed topology, not `_BY_NAME`.
- **Suggested improvements:** See R1-F1 (correct the OQ-B coupling inventory) and R1-F2 (align FR-6).

**Ask 2 — FR-6 vs OQ-B contradiction.**
- **Summary answer:** Yes, real contradiction; FR-6 must be reworded to state the *pattern-reuse* outcome, not "generalized `generate_compose_dict`."
- **Rationale:** FR-6 (`§2 Cross-cutting`) asserts "topology = generalized `generate_compose_dict`" as settled, but OQ-B (`§4`) and §0.3 both lean new-module. A reader implementing FR-6 verbatim would generalize in place, contradicting the recommendation. See R1-F2.

**Ask 3 — FR-8 soundness (host-side loop vs in-compose locust; span-metrics convergence signal).**
- **Summary answer:** Host-side loop for v1 is correct; but the convergence signal is under-specified — `_await_scrape`/`job_series_count` count *series presence*, which is the wrong settle signal for histograms.
- **Rationale:** FR-8 says "re-gate on the two-phase `_await_scrape` (series-count stability)." Grounding (`live_standup.py:143 job_series_count`, `:156 _await_scrape`) confirms the gate keys on **series count settling**. For span-metrics the risk is that the histogram *series* (`_bucket`/`_count`/`_sum`) register on first scrape while their **counts are still 0** until traffic lands — so series-count can "settle" at a stable-but-empty state and gate green with no data, re-introducing the always-`unknown`/false-ready failure FR-8 exists to kill. See R1-F3 (require a non-zero-sample convergence signal, e.g. `sum(increase(<hist>_count[…]))>0`).
- **Assumptions / conditions:** none.
- **Suggested improvements:** R1-F3; and R1-F5 on `run_smoke`'s skip-return semantics as a warm-up input.

**Ask 4 — Multi-container × span-metrics composition; Prometheus-two-networks clarity.**
- **Summary answer:** Under-defined in two concrete ways beyond the doc's own [Low] note.
- **Rationale:** (a) The *current* single-image standup uses a **plain bridge** `docker network create` (`live_standup.py:258`), NOT the `internal:true` fleet + `edge` split FR-2 introduces — so FR-2 is a *new* network topology for compare-live, not a reuse of the shipped standup's networking; the doc frames it as reuse. (b) `render_prometheus_yml` (`live_standup.py:58`) emits a **single scrape job** (one `target_host:target_port`); FR-4 (scrape `collector:8889`) fits, but any FR-1 subject where the ingress service ≠ the metrics service, or where >1 service must be scraped, needs multi-job Prometheus config that does not exist yet. See R1-F4 and R1-F6.
- **Suggested improvements:** R1-F4, R1-F6.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | Correct the OQ-B / §0.3 coupling inventory: `generate_compose_dict` couples to the global registry at **three** sites, not two — add the dep-edge fan-out `get_service(dep_name)` at `compose.py:57` (every `depends_on` peer is resolved via `_BY_NAME` to build `{addr_env}: peer:dial_port`). Also note the image coupling is *already soft* (`compose.py:42` prefers `spec.image`; the `r3` namespace is only the `image is None` fallback), so it is NOT a blocker. | The doc's stated couplings (ingress validation + image_namespace) understate the in-place-generalization cost and overstate the image issue; the dep fan-out is the coupling that actually breaks an arbitrary subject and forks `benchmark_matrix`'s hot path. Getting the inventory right is what justifies OQ-B's new-module lean. | §0.3 (FR-6/OQ-B bullet) and §4 OQ-B | Grep-verify `get_service(` occurrences in `compose.py` return exactly two call-sites (`:94` ingress, `:57` dep); confirm `_service_block` image branch at `:42`. |
| R1-F2 | Interfaces | high | Reword FR-6's third clause from "topology = generalized `generate_compose_dict`" to the OQ-B-resolved outcome, e.g. "topology = a new `observability/live_compose.py` that **reuses the `compose.py` net/DNS/ingress/dep-env patterns** without importing `benchmark_matrix`'s OB registry." Make FR-6 defer to OQ-B rather than pre-deciding it. | FR-6 currently states as a *requirement* the exact approach OQ-B/§0.3 leans *against* — an implementer following FR-6 verbatim contradicts the recommendation. A requirement must not assert an open decision as settled. | §2 Cross-cutting, FR-6 (verbatim: "topology = generalized `generate_compose_dict`") | Post-CRP, verify FR-6 wording and OQ-B resolution agree (no reviewer can read them as contradictory). |
| R1-F3 | Validation | high | FR-8 must specify a **non-zero-sample** span-metric convergence signal, not just `_await_scrape` series-count stability. State the gate as: histogram `_count` series exist **AND** `sum(increase(<span_metric>_count[<window>])) > 0` before releasing; series-count-only stability may settle at a registered-but-empty state and gate green with no data. | `_await_scrape`/`job_series_count` (`live_standup.py:143,156`) key on series *presence/count settling*; span-metric histograms can register series on first scrape with zero observations until traffic lands — re-introducing the false-ready path FR-8 exists to eliminate (see §0.3 [High]). | §2 FR-8, after "reuse the existing two-phase `_await_scrape` gate on series-count stability" | Stand up a span-metrics subject, drive zero traffic, assert the gate does NOT release (stays until timeout→`unknown`); drive traffic, assert release only after `_count` increase is observed. |
| R1-F4 | Ops | medium | State explicitly that FR-2 introduces a **new** two-network topology (`internal:true` `fleet` + `edge` bridge) that the *current* single-image standup does not use (it uses a plain `docker network create` bridge, `live_standup.py:258`). Frame FR-2 networking as **new code adapted from `compose.py`'s pattern**, not reuse of the shipped standup. | The doc's [Low] note says "Prometheus joins two networks — state it explicitly," but the deeper gap is that the shipped standup has no fleet/edge concept at all; readers estimating effort/teardown from the existing standup will under-scope. Accurate provenance prevents a false "just reuse live_standup" read. | §0.3 [Low] bullet and §1/FR-2 | Confirm `live_standup.py` uses a single plain bridge (grep `network create`); confirm no `internal:true`/`edge` today. |
| R1-F5 | Risks | medium | FR-8 should define behavior when the selected driver **cannot exercise** the subject: `run_smoke` returns a `SmokeOutcome(status="skipped", …)` (no OpenAPI / no CRUD resource / body-synth-fail) and **never raises**; the OB journey drivers can score all-fail on a non-OB subject. Specify that a driver that produces **no successful request** ⇒ warm-up fails ⇒ `unknown` (fail-loud), never a silent proceed-to-gate. | Without this, a mis-matched driver (generic `run_smoke` against an app with no `/openapi.json`) silently drives zero real traffic, span-metrics never materialize, and the run degrades to `unknown` with no distinguishable cause from "subject emits no traces." Making the skip an explicit fail-loud branch preserves diagnosability. | §2 FR-8, driver-selection list | Point `run_smoke` at a subject with no `/openapi.json`; assert warm-up reports a `skipped`/`unknown` reason naming the driver, not a false-ready. |
| R1-F6 | Interfaces | medium | FR-1/FR-2 must state whether Prometheus scrapes **one** service (`metrics_service`) or potentially several, and reconcile with `render_prometheus_yml` being **single-job today** (`live_standup.py:58`). If v1 is single-scrape-target, say so as an explicit boundary; if multi-service metrics are in scope, FR-2 must call out generalizing `render_prometheus_yml` to N scrape jobs. | FR-1 introduces `metrics_service`/`metrics_port`/`metrics_path` (singular), implying one scrape target, but a "multi-container app" reader may expect per-service scraping. The single-job renderer is a concrete constraint that should be surfaced as either a boundary or a required change. | §2 FR-1 (metrics_service fields) and FR-2 | Confirm `render_prometheus_yml` emits exactly one `job_name`/target; assert FR text names the single-target boundary or the N-job change. |
| R1-F7 | Validation | low | FR-3/FR-7 reuse `_await_scrape` and `tear_down`, but neither states the **N-container** teardown ordering/failure contract: FR-7 says "generalized to N containers" — specify that teardown is **best-effort per-container** (one container's removal failure must not abort the rest) and that the `startd8-cmp-<hex>` prefix is the sole ownership key for the sweep. | "Generalized to N containers" is directionally clear but not testable as written; a partial-teardown that aborts on the first error would leak containers/networks across runs. The shipped single-image `tear_down` is best-effort (`live_standup.py:325`); the N-container contract should say so. | §2 FR-7 | Simulate one container removal failing; assert remaining containers + the network + temp files are still removed and the run reports leaked-resource count. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F8 | Risks | medium | Adversarial to my own Ask-3/R1-F3: even a non-zero `_count` signal can gate green on **partial** warm-up (only the browse step's spans materialized, checkout never ran). Add that FR-8's warm-up must assert the driver reached a **terminal success** (e.g. `JourneyOutcome.completed` / `run_smoke` status `passed`), not merely "some series appeared," before the gate is trusted. | A bounded loop that only ever succeeds at `GET /` produces non-zero span-metrics yet leaves the checkout SLI's series empty — the PromQL replay then validates a subset and may false-`pass`/`unknown` inconsistently. Tying warm-up release to driver terminal success closes the partial-coverage hole R1-F3 alone leaves open. | §2 FR-8 (convergence criteria) | Force checkout to fail; assert warm-up does not report ready (driver `completed=False`), run resolves `unknown`, not a partial green. |
| R1-F9 | Data | low | FR-1's `--subject-compose <file.yaml>` lean schema is described in prose (`{name, image, port, deps?}` + `metrics_service`/`metrics_port`/`metrics_path`) but has no formal schema or example. Add a minimal YAML example and state required-vs-optional fields + the validation error surface (malformed topology ⇒ `unknown`, never a partial standup), consistent with FR-5 fail-loud. | An implementer/QA cannot write a conformance test against prose; a worked example + field table makes FR-1 testable and prevents divergent parsers. Cross-refs OQ-A (lean-YAML vs compose-subset) — pin the v1 shape concretely. | §2 FR-1 | Provide the example as a golden fixture; assert the parser round-trips it and rejects a missing-`metrics_service` file with an `unknown`-class error. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — Appendix C had no prior rounds at R1.

