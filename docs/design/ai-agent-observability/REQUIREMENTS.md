# AI-Agent / LLM-Integration `signal_kind` Family for the Observability Generator — Requirements

**Version:** 0.1 (draft — reflective-requirements loop; series live-grounded, values deferred)
**Date:** 2026-07-22
**Status:** Draft — ready for CRP
**Extends:** the #226 "de-overfit" family (`docs/design/observability-requirement-shaped/REQUIREMENTS.md`),
which made the observability generator **requirement-shaped** (per-`signal_kind` templates) and added
service **KINDS** (`metric_descriptor.py`).
**Companion-of-record:** `docs/design/OBSERVABILITY_AI_AGENT_REQUIREMENTS.md` (the *emission/descriptor*
side — how the SDK declares its own cat-4/5 telemetry). This doc is the **generator** side: turning that
already-emitted telemetry into SLOs.
**Subject observed:** the **hosted-LLM consumption** of the SDK's own agents — cost/call, token
throughput, context-window fullness — as distinct from GPU model-inference (see §5, #231).

---

## 0. Planning Insights (Self-Reflective Update)

> A planning pass mapped each proposed FR onto the live de-overfit mechanism
> (`artifact_generator_generators.py`), the emission layer (`costs/otel_metrics.py`,
> `session_tracking.py`), and a live Mimir instance (localhost:9009, 2026-07-22). The pass produced
> material corrections; the biggest is that **this family is uniquely un-blocked**, because — unlike
> batch/cron/ml_inference — its metric series already exist and are queryable *today*.

| v0.0 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| "AI-agent SLOs need a new generator mechanism" | The de-overfit family already built the seam: `_FUNCTIONAL_SLI_TEMPLATES` (`artifact_generator_generators.py:1008`) maps `signal_kind → (candidate series, shape, unit)`, `_select_functional_metric` (`:1025`) binds to the series the service declares, `generate_functional_slos` (`:1057`) emits the SLO. | This is a **table-extension**, not a new subsystem — add AI rows to `_FUNCTIONAL_SLI_TEMPLATES` + register the AI `signal_kind`s. Same shape as `queue_depth`/`lag`/`freshness`. |
| "The series need grounding, like batch/cron" | The AI series are **already emitted and live-queryable**: `startd8_cost_per_request_USD` (histogram, `otel_metrics.py:49`), `startd8_cost_output_tokens_total` (counter, `:40`), `startd8_context_usage_ratio` (observable gauge, `session_tracking.py:83`). Verified returning real data in Mimir 2026-07-22. | The **series** are grounded (done); only the threshold **VALUES** stay deferred (OQ-1, the honest scope). This inverts the batch/cron posture (which lacks even the subjects). |
| "cat-4/5 metrics have a generator" | They do **not**: `artifact_generator.py:1178` (REQ-OAT-041) only *counts* them as `metrics_awaiting_category_home` — `Category.PROJECT` / `Category.AI_AGENT` (`taxonomy_enums.py:30-31`) have **no generator yet**. | This is the KNOWN GAP this spec fills. FR-2 gives cat-5 (`ai_agent_observability`) its first home. |
| "AI signal_kinds are all novel shapes" | Two of three reuse **existing** SLI shapes verbatim: cost/call is a **latency-analog** (histogram-quantile, exactly `_functional_sli_query`'s `histogram_quantile` path); token-throughput is a `rate`; context-saturation is a `gauge_max`. | No new PromQL shape is required for the first three kinds (FR-1). A new shape (`quantile`) is only a naming refinement of the existing histogram path (OQ-3). |
| "This is the same as #231 (ml_inference)" | #231 is **GPU model-inference** (saturation/lag on a served model); this is **hosted-LLM consumption** (dollars/tokens/context on an API we call). Different subject, different series, different units. | Named the distinction explicitly (§5) so they are not conflated under a shared "AI" label. This family does **not** touch `UNGROUNDED_KINDS` (`metric_descriptor.py:205`). |

**Resolved open questions:**
- **OQ (series existence) → RESOLVED.** All three primary series exist, are declared with
  `category: ai_agent_observability` (`otel_metrics.py:21`, `session_tracking.py:47`), and return
  live data in Mimir (2026-07-22). See §6.
- **OQ (which shape) → RESOLVED for 3 kinds.** cost/call = histogram-quantile, token-throughput =
  rate, context-saturation = gauge_max — all already implemented in `_functional_sli_query`
  (`:1044`).

*The essential complexity is: the SDK's own AI telemetry is emitted and categorized `ai_agent_observability`,
but the generator has no per-`signal_kind` template to turn it into SLOs. The accidental complexity to
avoid is inventing a parallel AI-SLO mechanism when the de-overfit `_FUNCTIONAL_SLI_TEMPLATES` seam already
fits — this doc extends that seam and nothing else.*

---

## 1. Problem Statement

The SDK **emits and categorizes** a first-class body of AI-agent/LLM telemetry, but the observability
artifact generator has **no profile to turn it into SLOs**.

**Emission side (source-grounded, already shipped):**
- `costs/otel_metrics.py:20` declares `_OTEL_DESCRIPTORS` with `"category": "ai_agent_observability"`,
  `"orientation": "system"`, exporting `startd8.cost.total` (counter, USD), `startd8.cost.input_tokens` /
  `startd8.cost.output_tokens` (counters, tokens), and `startd8.cost.per_request` (histogram, USD) — all
  labeled `model` / `provider` / `project` (`:30`, `:38`, `:46`, `:54`).
- `session_tracking.py:46` declares a sibling `_OTEL_DESCRIPTORS` (same `ai_agent_observability` category,
  `:47`) exporting `startd8.context.usage_ratio` (observable gauge, unit `ratio`, `:83-89`), plus
  `startd8.requests.total`, `startd8.tokens.total`, `startd8.response.time_ms`, `startd8.truncations.total`.

**Generator side (the gap):**
- `artifact_generator.py:1178` (REQ-OAT-041) explicitly states cat-4/5 (`Category.PROJECT` /
  `Category.AI_AGENT`, `taxonomy_enums.py:30-31`) metrics "have no generator yet"; they are only
  **counted** as `summary["metrics_awaiting_category_home"]` (`:1181-1184`) so the gap is *visible*, not
  *closed*. No SLO, alert, or dashboard panel is derived from an `ai_agent_observability` metric.

**Consequence:** every `startd8.cost.*` / `startd8.context.usage_ratio` series is real, live, and
labeled — yet a project that runs startd8 agents gets **zero** cost/token/context SLOs from the
generator, even though the de-overfit seam that would produce them already exists for
queue/worker/stream services. This spec closes REQ-OAT-041 for **category 5** using the de-overfit
mechanism, with the honest note that only the threshold **values** (not the series) remain to be
grounded.

---

## 2. The AI-Agent `signal_kind`s (proposed)

Each row extends `_FUNCTIONAL_SLI_TEMPLATES` (`artifact_generator_generators.py:1008`) exactly as the
#226 rows (`queue_depth`, `lag`, `retry_rate`, `saturation`, `freshness`, `run_success`) do:
`signal_kind → (candidate series (grounded), SLI shape, unit)`. The candidate series is bound to the
declared metric by `_select_functional_metric` (`:1025`); the shape is realized by `_functional_sli_query`
(`:1044`). **All series named below are Prometheus-exported names (dots → underscores) verified live in
Mimir 2026-07-22.**

| `signal_kind` | Candidate series (grounded, Prom name) | SLI shape | Unit | Notes |
|---------------|----------------------------------------|-----------|------|-------|
| **`llm_cost_per_request`** | `startd8_cost_per_request_USD` (histogram; from `startd8.cost.per_request`, `otel_metrics.py:49`) | `quantile` (histogram-quantile; the **latency-analog** — same PromQL as the existing histogram path) | `USD` | Budget = "p99 $/call ≤ target". Measured: opus $0.0225, sonnet $0.0060, haiku $0.0011 per call. |
| **`token_throughput`** | `startd8_cost_output_tokens_total` (counter; from `startd8.cost.output_tokens`, `otel_metrics.py:40`) | `rate` (reuses `_functional_sli_query` `rate` branch, `:1049`) | `short` (tokens/s) | `sum(rate(startd8_cost_output_tokens_total[5m]))`. Input-token analog available from `startd8_cost_input_tokens_total`. |
| **`context_saturation`** | `startd8_context_usage_ratio` (observable gauge, 0–1; `session_tracking.py:83`) | `gauge_max` (reuses `_functional_sli_query` `gauge_max` branch, `:1046`) | `percentunit` | A genuine **saturation** SLI — context-window fullness. Emitter already has an `is_near_capacity` 80% notion (`session_tracking.py:181`). |
| **`llm_error_rate`** *(optional / partial)* | `startd8_requests_total{status="error"}` ÷ `startd8_requests_total` (counter has a `status` label, `session_tracking.py:64`) | `ratio` (reuses `_functional_sli_query` `ratio` branch, `:1052`) | `ratio` | The `status` label exists; a dedicated error/refusal series does **not** — see the GAP note below. |

**GAP note (honesty):** there is **no dedicated `refusal_rate` series** today. A refusal is an
application-level classification the SDK does not currently label. `llm_error_rate` can be *derived* from
the existing `status` label on `startd8_requests_total`, but a distinct **refusal** signal would require a
new instrument on the emission side — **out of scope here** (this doc reuses emitted metrics only; see §7
and the companion `OBSERVABILITY_AI_AGENT_REQUIREMENTS.md` REQ-AAO-009 for label additions). `llm_error_rate`
is therefore proposed as OPTIONAL, gated on confirming the `status` label's value vocabulary.

**Shape reuse summary:** three of four kinds require **no new shape** — `quantile` is the existing
histogram-quantile path (`_INSTRUMENT_TO_QUERY["histogram"]`, `:90`, and the `custom`/histogram branch of
`_functional_sli_query`), `rate`/`gauge_max`/`ratio` are literal existing branches. The only refinement is
naming a `quantile` shape distinctly from `gauge_max` so the cost histogram gets a `histogram_quantile`
query rather than a bare `max()` (OQ-3).

---

## 3. Requirements (SDK — this repo)

### Back-compat gate

- **FR-0 — Byte-parity / opt-in gate (mirrors #226 FR-11).** Absent any AI-agent `functional[]` FR **and**
  absent any `ai_agent_observability`-category metric on a service, generator output MUST be
  **byte-identical** to today's. The AI rows in `_FUNCTIONAL_SLI_TEMPLATES` are inert until a service
  declares an AI `signal_kind` FR or carries a cat-5 metric.
  **Acceptance:** a full-YAML golden of the existing Online-Boutique / http fixtures is unchanged with the
  AI rows added (extend the #226 FR-0 fixture matrix; add one **cat-5 fixture** — a service carrying
  `startd8_cost_per_request_USD` + an `llm_cost_per_request` FR — that DOES emit).

### The signal_kind rows

- **FR-1 — Register the AI `signal_kind`s in `_FUNCTIONAL_SLI_TEMPLATES`.** Add the §2 rows
  (`llm_cost_per_request`, `token_throughput`, `context_saturation`, optional `llm_error_rate`) to the
  table at `artifact_generator_generators.py:1008`, each `(candidate series, shape, unit)`. They are NOT in
  `_TRIPLET_SIGNAL_KINDS` (`:1022`), so `generate_functional_slos` (`:1057`) treats them as non-request
  functional SLIs and binds via `_select_functional_metric`.
  **Acceptance:** an FR with `signal_kind: llm_cost_per_request` + a `target` produces an OpenSLO doc whose
  `thresholdMetric.spec.query` is `histogram_quantile(0.99, ...startd8_cost_per_request_USD_bucket...)`;
  `token_throughput` produces a `rate(...)` query; `context_saturation` produces `max(startd8_context_usage_ratio{...})`.

- **FR-1a — `quantile` shape for the cost histogram.** Extend `_functional_sli_query` (`:1044`) with a
  `quantile` branch emitting `histogram_quantile(<q>, sum by (le,...)(rate({metric}_bucket{selector}[5m])))`,
  so `llm_cost_per_request` reads as a latency-analog rather than a raw gauge. Default `q=0.99` (reuse the
  descriptor `quantile` field, `metric_descriptor.py:78`).
  **Acceptance:** the generated cost query matches the live-verified expression in §6.

### The cat-4/5 generator (REQ-OAT-041 home)

- **FR-2 — Emit SLOs for `ai_agent_observability`-category metrics.** Give cat-5 its first generator: a
  service (or the project scope) that carries `Category.AI_AGENT` metrics (`taxonomy_enums.py:31`) SHALL
  have those metrics bound to the FR-1 templates and emitted as SLOs, instead of only being counted at
  `artifact_generator.py:1181` (`metrics_awaiting_category_home`). The generator reuses
  `generate_functional_slos` (`:1057`); no new emit path.
  **Acceptance:** a run whose route-states include a cat-5 metric with a matching AI `signal_kind` FR
  emits an SLO artifact and **decrements** `metrics_awaiting_category_home` by that metric; the
  `artifact_type_coverage_by_category` (`artifact_generator.py:1165`) shows cat-5 coverage > 0.

- **FR-2a — Cost/context are `orientation: system`, project-scoped.** The AI series are labeled
  `model`/`provider`/`project` (not per-service `service`), and both descriptor blocks declare
  `"orientation": "system"` (`otel_metrics.py:21`, `session_tracking.py:48`). The generator MUST bind the
  AI SLI selectors on `model`/`project` (not the service-identity label), so a cost SLO reads
  "p99 $/call for `model=opus` under `project=X`", not a per-service RED selector.
  **Acceptance:** generated AI SLO queries carry a `{model=...}` / `{project=...}` selector, never a
  `{service=...}` selector inherited from `MetricDescriptor.selector` (`metric_descriptor.py:99`).

### The threshold table (compose onto the shared seam)

- **FR-3 — Per-`signal_kind` thresholds under the shared 3-axis table (SHAPE now, VALUES deferred).** Per
  `DE_OVERFIT_FAMILY_THRESHOLD_SEAM.md`, the live table is
  `<criticality>.<deployment_mode>.<field>` (`config/importance_thresholds.yaml`), resolved by
  `_resolve_threshold` / `_select_importance_default` (`artifact_generator_generators.py:52,134`), which are
  **already generic over `field_name`**. Add the AI `signal_kind`s (`llm_cost_per_request`,
  `token_throughput`, `context_saturation`) as `field_name`s **inside each existing
  `<criticality>.<deployment_mode>` cell**, and a criticality-agnostic baseline in `_DEFAULT_THRESHOLDS`
  (`:45`). **No new resolution code** — the manifest → importance → flat tiers apply unchanged.
  **Acceptance:** the table *shape* lands with placeholder/documented values; `_resolve_threshold` returns
  an AI threshold at the `default:importance` tier when the field is present and falls through to the flat
  default otherwise (byte-parity for services with no AI FR).

### Coverage integration

- **FR-4 — AI coverage in the generation report (mirrors #226 FR-9).** The report SHALL surface AI-SLI
  coverage using the existing `fr_coverage` channel: an AI `signal_kind` FR whose source series is present
  → emitted; whose series is absent → the **`resolved≠∅, produced=0`** (unfulfilled) class, not a silent
  drop. Because the AI series *do* exist, the common case is "emitted"; `llm_error_rate` (no dedicated
  series) is the expected `unfulfilled` case until §7's emission gap is closed.
  **Acceptance:** a run with an `llm_cost_per_request` FR and the live cost histogram reports it emitted; a
  run with a `refusal_rate` FR (no series) reports it `unfulfilled` with the actionable reason "no emitting
  series; requires an emission-side label (see OBSERVABILITY_AI_AGENT_REQUIREMENTS REQ-AAO-009)".

### Non-request suppression parity

- **FR-5 — AI kinds never inherit a request RED triple.** AI SLIs are additive functional signals
  (`generate_functional_slos`), never the convention triplet. A project-scoped cost/context metric MUST NOT
  cause `_ensure_red_coverage` (`:867`) to synthesize a "Request Rate" panel. This is automatic given FR-2a
  (project selector, not service RED) but is asserted as a guard.
  **Acceptance:** a fixture carrying only cat-5 metrics + AI FRs produces AI SLOs and **no** fabricated
  Request-Rate/Availability panels.

---

## 4. Non-Requirements / Honest Gaps

- **NR-1 — No cost-per-token PRICING logic.** This doc consumes the *emitted* `startd8.cost.*` USD
  histograms; it does **not** compute or model pricing (that lives in `costs/pricing.py`). A cost SLO is
  "p99 $/call ≤ budget", derived from what CostTracker already recorded.
- **NR-2 — No new metric instruments.** This doc reuses only what `otel_metrics.py` / `session_tracking.py`
  already emit. Any *new* label (a distinct `refusal` outcome, a per-tool-call series) is an **emission-side**
  change owned by `OBSERVABILITY_AI_AGENT_REQUIREMENTS.md` (REQ-AAO-009), not here.
- **NR-3 — Threshold VALUES deferred (see OQ-1).** The SHAPE of the criticality × deployment_mode ×
  signal_kind table lands now; the magnitudes (breaching p99 $/call, paging context-saturation) are gated
  on real agent-run data. Ship the table structure, fill values from a grounded pilot — never by invention
  (the #226 §0.4 / ADR-004 discipline).
- **NR-4 — `refusal_rate` out of scope.** No dedicated refusal series exists; deriving it needs an
  emission-side classification. Listed as a candidate (§2) and an `unfulfilled` coverage case (FR-4), not a
  deliverable.

---

## 5. Relationship to #231 (`ml_inference`) — DISTINCT, not the same "AI"

These are two different subjects that both carry the word "AI"; conflating them re-introduces exactly the
overfit #226 fights.

| Axis | **#231 `ml_inference`** | **This family (LLM-integration)** |
|------|-------------------------|-----------------------------------|
| Subject | A **GPU-served model** we host/run | A **hosted LLM API** we *consume* (Anthropic/OpenAI/…) |
| Grounding status | `ml_inference ∈ UNGROUNDED_KINDS` (`metric_descriptor.py:205`) — series NOT yet grounded | Series **grounded + live** (`startd8_cost_*`, `startd8_context_usage_ratio`) 2026-07-22 |
| Shape | saturation / lag on the GPU (`_KIND_SUGGESTED_SIGNALS["ml_inference"] = ("saturation","lag")`, `:216`) | cost/call (quantile), tokens (rate), context (gauge_max) |
| Units | GPU utilization %, inference-queue lag | **USD**, tokens/s, context-window ratio |
| Registry touched | `UNGROUNDED_KINDS` (a **service KIND**) | `_FUNCTIONAL_SLI_TEMPLATES` (a **signal_kind**) — no KIND added |
| Silent-danger | an ML service exposing an http port getting a phantom 500ms HTTP SLO (#231) | none analogous — cost/context are project-scoped, never request-shaped |

**Naming decision:** #231 is a **service-KIND** (what a service *is*); this family is a set of
**signal_kinds** (what SLIs a consumer of LLMs *has*). They live in different tables
(`metric_descriptor.py` KIND maps vs `artifact_generator_generators.py` `_FUNCTIONAL_SLI_TEMPLATES`) and do
not overlap. This doc adds **no** entry to `CANONICAL_SERVICE_KINDS` / `UNGROUNDED_KINDS` /
`_KIND_DEFAULTS`.

---

## 6. Grounding Evidence (verified live, 2026-07-22, Mimir @ localhost:9009)

**Series grounded (DONE) — the honest distinction vs the batch/cron/ml_inference OQ-5:**

| SLI | Live PromQL (verified returning data) | Emission source |
|-----|----------------------------------------|-----------------|
| cost / request (p99) | `histogram_quantile(0.99, sum by (le,model)(rate(startd8_cost_per_request_USD_bucket[5m])))` under a USD budget | `startd8.cost.per_request` histogram (`otel_metrics.py:49`) |
| token throughput | `sum(rate(startd8_cost_output_tokens_total[5m]))` | `startd8.cost.output_tokens` counter (`otel_metrics.py:40`) |
| context saturation | `max(startd8_context_usage_ratio{...})` (0–1) | `startd8.context.usage_ratio` observable gauge (`session_tracking.py:83`) |

Measured cost/call (avg, live): **opus $0.0225, sonnet $0.0060, haiku $0.0011** — real, model-labeled,
queryable. This is why this family is **not** blocked on subject-location the way #226 OQ-5 was: the
subjects exist and run continuously (the SDK observing its own agents).

**Values NOT grounded (OQ-1) — deferred, honestly:** the *magnitude* of each threshold — what p99 $/call
should *breach* for a given criticality, at what context-saturation the SLO should *page* — needs real
agent-run distributions across models/workloads, not the 3-sample averages above. This is the same
"series grounded ≠ values grounded" split the de-overfit family draws (its OQ-5): there, *neither* was
grounded; here, series are grounded and only values remain. Ship the table SHAPE (FR-3), fill values from a
grounded pilot.

---

## 7. Reference Audit

Every code symbol this spec names was read and grep-verified to exist:

| Symbol / anchor | file:line | Used by |
|-----------------|-----------|---------|
| `_OTEL_DESCRIPTORS` (`category: ai_agent_observability`), `startd8.cost.*` | `costs/otel_metrics.py:20-57` | §1, §2, §6 |
| `startd8.context.usage_ratio` observable gauge, `_OTEL_DESCRIPTORS` | `session_tracking.py:46-89` | §2, §6 |
| `is_near_capacity` (80% context notion) | `session_tracking.py:181` | §2 |
| REQ-OAT-041 `metrics_awaiting_category_home`; `Category.PROJECT`/`AI_AGENT` | `artifact_generator.py:1178-1184` | §1, FR-2 |
| `Category.PROJECT="project_observability"`, `AI_AGENT="ai_agent_observability"` | `taxonomy_enums.py:30-31` | §1, FR-2 |
| `_FUNCTIONAL_SLI_TEMPLATES`, `_TRIPLET_SIGNAL_KINDS` | `artifact_generator_generators.py:1008,1022` | FR-1 |
| `_select_functional_metric`, `_functional_sli_query`, `generate_functional_slos` | `artifact_generator_generators.py:1025,1044,1057` | FR-1/1a/2 |
| `_INSTRUMENT_TO_QUERY["histogram"]` (histogram-quantile) | `artifact_generator_generators.py:90` | FR-1a |
| `_resolve_threshold`, `_select_importance_default`, `_DEFAULT_THRESHOLDS` | `artifact_generator_generators.py:134,52,45` | FR-3 |
| `importance_thresholds.yaml` (`<criticality>.<mode>.<field>`) | `config/importance_thresholds.yaml` | FR-3 |
| `_ensure_red_coverage` (unconditional synthesis, now gated) | `artifact_generator_generators.py:867` | FR-5 |
| `UNGROUNDED_KINDS`, `_KIND_SUGGESTED_SIGNALS`, `CANONICAL_SERVICE_KINDS` | `metric_descriptor.py:205,213,239` | §5 |
| `MetricDescriptor.selector`, `.quantile` | `metric_descriptor.py:99,78` | FR-1a, FR-2a |
| `artifact_type_coverage_by_category` | `artifact_generator.py:1165` | FR-2 |

---

## 8. Open Questions

- **OQ-1 (the grounding gate — VALUES, not series).** What are the real criticality × deployment_mode ×
  signal_kind threshold magnitudes for `llm_cost_per_request` (breaching $/call), `token_throughput`
  (floor tokens/s), and `context_saturation` (paging fullness)? The **series** are grounded (§6); the
  **values** need a grounded pilot across models/workloads. Ship the table SHAPE (FR-3) now; fill values
  later — never invent them. *(Directly parallels the de-overfit OQ-5, but one level less blocked: series
  done, values pending.)*
- **OQ-2 — project-scope vs per-service binding.** Cost/context are `orientation: system`, labeled
  `model`/`project`, not `service`. Does the generator emit these as **project-level** SLOs (one per
  model/project) or attach them to a nominal "agent" service? FR-2a assumes project/model selectors;
  confirm the report/manifest schema has a home for a non-service-scoped SLO (or introduce a synthetic
  `project`-scoped service id).
- **OQ-3 — `quantile` shape naming.** Is a distinct `quantile` branch in `_functional_sli_query` (FR-1a)
  warranted, or should `llm_cost_per_request` route through the existing histogram path in
  `_INSTRUMENT_TO_QUERY`? (Leaning: add the explicit branch so the functional-SLI path is self-contained,
  matching how `gauge_max`/`rate`/`age`/`ratio` are all explicit.)
- **OQ-4 — `llm_error_rate` / `refusal_rate`.** `status` on `startd8_requests_total` can derive an
  error-rate; a true *refusal* rate needs an emission-side label. Include `llm_error_rate` as OPTIONAL now
  (from `status`), and defer `refusal_rate` to the emission side (NR-4 / REQ-AAO-009)?
- **OQ-5 — cross-check with the companion emission spec.** `OBSERVABILITY_AI_AGENT_REQUIREMENTS.md`
  flagged a dual cost-metric naming split (dotted vs underscore, per-session vs global). Confirm the
  generator binds to the **dotted `startd8.cost.*`** family (the one carrying the
  `ai_agent_observability` descriptor), not the session-tracker's per-session names, so it observes the
  global cost surface — reconcile before implementation.

---

## Changelog

*v0.1 — Initial draft (reflective-requirements loop). Grounded on `costs/otel_metrics.py`,
`session_tracking.py`, `artifact_generator.py` (REQ-OAT-041), `artifact_generator_generators.py`
(`_FUNCTIONAL_SLI_TEMPLATES` / `generate_functional_slos`), `metric_descriptor.py`,
`config/importance_thresholds.yaml`, and the #226 de-overfit spec + threshold-seam note. Series
live-verified in Mimir (localhost:9009, 2026-07-22); threshold VALUES deferred (OQ-1). Distinguished from
#231 ml_inference (§5). Extends `_FUNCTIONAL_SLI_TEMPLATES` (not a new mechanism); fills REQ-OAT-041 for
category 5.*
