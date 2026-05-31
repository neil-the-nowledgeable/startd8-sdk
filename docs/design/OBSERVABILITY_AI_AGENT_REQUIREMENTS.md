# AI Agent Observability — Requirements (Taxonomy Category 5)

**Date:** 2026-05-31
**Status:** Draft v0.2 — post-planning self-reflective update (requirements only; no code this pass)
**Lineage:** Instantiates **Category 5 — AI Agent Observability** of
`OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md` (the "reserved — signals emitted, no generator"
row). Evidence base: a read-only telemetry inventory of `src/startd8/` (costs/, session_tracking,
agents/tracked, orchestration, events/otel_bridge, otel, observability/manifest).
**Subject observed:** the **AI agents and LLM workflows** themselves — cost, tokens, sessions,
context usage, latency, truncation, tool use, agent/pipeline traces, output quality.

---

## 0. Planning Insights (self-reflective update, v0.1 → v0.2)

> A planning pass traced the actual emission call-chains and read the `_OTEL_DESCRIPTORS` manifest
> machinery. Headline: **most of the hard infrastructure already exists** — the descriptor manifest
> is the missing-link that closes both this doc's "descriptor→artifact loop" *and* the taxonomy's
> "declare, don't guess" producer gap, for the SDK's own metrics. Two v0.1 findings were
> over-stated and are corrected below.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| AAO-D1: cost is **double-counted** under two names | The two families are **disjoint paths with distinct semantics**: `startd8.cost.*` = global/automatic (CostTracker, fires on the standard `generate()` path); `startd8_cost_total` = **per-session** (explicit `record_request` API). They do **not** both fire in standard usage — double-counting is only a *latent* risk if a user calls both APIs for one call | **REQ-AAO-002 reframed**: clarify+document the distinct semantics and guard against double-invocation — **not** "prohibit duplicate emission" (a misdiagnosis) |
| AAO-D6: descriptor→artifact loop is unbuilt | `_OTEL_DESCRIPTORS` declared in all modules; `generate_manifest()` collects + serializes them. Missing only: (a) `category`/`orientation` fields on the descriptor schema, (b) the wire from manifest → onboarding-metadata `manifest_declared` | **REQ-AAO-008 reframed** ~70% done: *add 2 schema fields + wire the last mile*, not greenfield (M, not L) |
| REQ-AAO-001 = build a catalog | Descriptors already are a catalog (name/type/unit/labels); they just lack category/orientation + the undocumented signals | 001 narrows to *add the missing fields/signals* |
| REQ-AAO-009 = new outcome signal | session_tracking already tracks `successful/failed_requests` + a `status` label; the truncation **event** exists but isn't a metric label | 009 narrows to *add `truncated`/retry labels* (S) |
| Naming split might be intentional | Accidental divergence: session_tracking **hand-codes** underscore names; costs/ uses dotted (correct OTel); no export config maps them | **REQ-AAO-003 resolved**: standardize to **dotted** (OTel-native; Prometheus export underscores) — a consolidation task, not just docs |
| (not in v0.1) | The descriptor manifest can carry category/orientation, making the **SDK its own declare-don't-guess producer** for category-4/5 metrics | **New value/flexibility insight** (§3.4): dissolves the taxonomy's REQ-OAT-025 upstream-exporter dependency *for the SDK's own metrics*; flagged for taxonomy reconciliation |
| (not in v0.1) | No validation that **declared** descriptors match **emitted** metrics — the manifest can silently lie | **NEW REQ-AAO-012**: descriptor↔emission parity (a test), so the source of truth can't drift |

**Resolved open questions:**
- **OQ-1 → distinct semantics, documented.** Not derivation; the two cost families are global vs
  per-session views (REQ-AAO-002).
- **OQ-3 → accidental.** Standardize to dotted OTel names (REQ-AAO-003).
- **OQ-2 → keep eval in category 5**, as a reserved/phased sub-area (REQ-AAO-010).

*The essential complexity is: descriptors that carry (category, orientation) → one manifest → fed to
generation. The accidental complexity (dual cost APIs, hand-coded underscore names, a dead Prometheus
fallback, declared/emitted drift) is catalogued in Appendix C and should be removed opportunistically.*

---

## 0.1 Motivation

The SDK already emits a substantial body of AI-agent telemetry — but it accreted as **internal
developer instrumentation**, never formalized as a requirement and (cost aside) never surfaced in a
dashboard. The signals are *real and live*; what's missing is the spec. This document surfaces what
exists, names the gaps and the duplication, and defines the requirements that turn the implicit
instrumentation into a first-class observability category with generated artifacts.

This matters beyond startd8 itself: **any project that runs startd8 agents** inherits this
telemetry, so AI Agent Observability is a reusable category, not a startd8-only concern. startd8 is
its own reference implementation (it observes its own agents).

This is a **requirements** document. Code alignment is a separate, follow-up pass.

---

## 1. What we already collect (the evidence base)

### 1.1 Cost & token metrics — `costs/otel_metrics.py` (surfaced ✅)

OTel metrics, labels `{model, provider, project}`, emitted from `CostTracker.record_cost()`:

| Metric | Kind | Unit | Emission |
|--------|------|------|----------|
| `startd8.cost.total` | Counter | USD | `costs/otel_metrics.py:134` ← `tracker.py:266` |
| `startd8.cost.input_tokens` | Counter | tokens | `:135` |
| `startd8.cost.output_tokens` | Counter | tokens | `:136` |
| `startd8.cost.per_request` | Histogram | USD | `:137` |

Backed by a persistent `CostStore` (per-call `CostRecord`: tokens, costs, model, provider,
agent_name, project, tags, correlation_id, cache tokens). **Surfaced:** `dashboards/startd8-cost-tracking.json`
+ `startd8-mixin/dashboards/cost_tracking.libsonnet`.

### 1.2 Session & context metrics — `session_tracking.py` (undocumented ❌)

7 OTel metrics, labels include `{agent_name, model, project_id}`:

| Metric | Kind | Measures | Emission |
|--------|------|----------|----------|
| `startd8_active_sessions` | UpDownCounter | live agent sessions | `:609/:893` |
| `startd8_requests_total` | Counter (`+status`) | agent requests | `:786` |
| `startd8_tokens_total` | Counter (`+direction`) | tokens in/out | `:791` |
| `startd8_response_time_ms` | Histogram | agent call latency | `:801` |
| `startd8_context_usage_ratio` | ObservableGauge | context-window utilization (0–1) | `:428` callback |
| `startd8_truncations_total` | Counter | truncation events | `:804` |
| `startd8_cost_total` | Counter | session cost (USD) | `:807` |

Rich `SessionMetrics` state (success_rate, capacity_used%, average_response_time, ContextCore
project context). **No dashboard. No docs.** These are the `manifest_declared` metrics the run-007
onboarding metadata carried for `strtd8`.

### 1.3 Agent & pipeline spans (undocumented ❌)

- `agent.generate:{agent_name}` (`agents/tracked.py:219`) — attrs: `agent.id`, `agent.model`,
  `agent.prompt_length`, `agent.response_length`, `agent.response_time_ms`,
  `agent.tokens_{input,output,total}`, `agent.truncated`, `task.id`, `project.id`, and OTel GenAI
  conventions (`gen_ai.system`, `gen_ai.operation.name`, `gen_ai.response.finish_reasons`); event
  `truncation_detected`.
- `pipeline.{name}` + `pipeline.{name}.step.{step}` (`orchestration.py`) — `total_tokens`,
  `total_cost`, `total_time_ms`, per-step `retry_count`.
- `startd8.events.total` Counter (`events/otel_bridge.py:96`, label `event_type`); all EventBus
  events also attach as span events.
- Logs carry `trace_id`/`span_id` for correlation (`logging_otel.py`).

### 1.4 Outcome / quality / limits (partial ❌)

- Truncation: counter + span event + `TruncationResult` + pre-flight estimate.
- Usage limits (`costs/usage_limits.py`): rate/budget levels (LOW…EXCEEDED) — **events only, no metrics**.
- Quality: `improvement_tracking.py` tracks *document* quality deltas (YAML), **not per-LLM-call** —
  no eval score attached to an agent call.
- Tool use: **not instrumented** (no tool-call telemetry).

### 1.5 The self-describing manifest mechanism — `observability/manifest.py`

Each module declares `_OTEL_DESCRIPTORS` (zero runtime cost); `generate_manifest()` collects them
into a machine-readable catalog "to auto-generate dashboards, alerts, SLOs." **This is the intended
bridge** from emitted telemetry → category-5 artifacts, but the loop is not closed (the manifest is
declared, not yet driving generation).

---

## 2. Findings (what's wrong / missing)

| # | Finding | Evidence |
|---|---------|----------|
| AAO-D1 | **Duplicate cost/token instrumentation.** `startd8.cost.*` (costs/) and `startd8_cost_total`/`startd8_tokens_total` (session_tracking) measure overlapping things in two modules with two naming styles | §1.1 vs §1.2 |
| AAO-D2 | **Naming inconsistency.** Dotted (`startd8.cost.total`, OTel-native) vs underscore (`startd8_cost_total`, Prometheus-export style) for the same family; no documented mapping | §1.1/1.2 |
| AAO-D3 | **Surfacing gap.** Only cost has a dashboard; the 7 session/context metrics + all spans are emitted but invisible | §1.2/1.3 |
| AAO-D4 | **Weak outcome/quality signals.** Per-call success/truncated/retried/error not a coherent first-class signal; no eval-score-per-call; quality tracking is document-level only | §1.4 |
| AAO-D5 | **No tool-use telemetry** for agentic workflows | §1.4 |
| AAO-D6 | **Descriptor→artifact loop not closed.** `_OTEL_DESCRIPTORS`/`generate_manifest()` exists but doesn't drive category-5 dashboard/alert/SLO generation | §1.5 |

---

## 3. Requirements

### 3.1 Canonicalize & document the signal catalog

**REQ-AAO-001 (catalog).** Every AI-agent signal MUST have a documented entry — canonical name,
kind, unit, labels, semantics, emission site, and `(category=ai_agent_observability, orientation)` —
in a single source of truth (the `_OTEL_DESCRIPTORS` manifest, §3.4). Undocumented-but-emitted
signals (§1.2/1.3) MUST be added.

**REQ-AAO-002 (clarify the two cost/token families — corrected).** Planning showed these are **not**
redundant duplicates but **disjoint paths with distinct semantics**: `startd8.cost.*` is the
**global/automatic** cost (emitted by `CostTracker.record_cost()` on the standard `generate()`
path); `startd8_cost_total`/`startd8_tokens_total` are **per-session** (emitted by the explicit
`SessionTracker.record_request()` API). The requirement is therefore to **document the distinct
semantics** (global vs per-session, which to use when) and to **guard against double-invocation** —
a caller feeding the same call's cost to *both* APIs double-counts. This is a documentation +
guard-rail requirement, **not** a deduplication of redundant emission (the v0.1 "double-counting"
framing was a misdiagnosis — the families serve different questions).

**REQ-AAO-003 (naming — resolved to standardize on dotted).** Planning confirmed the split is
**accidental**: `session_tracking.py` hand-codes underscore names (`startd8_cost_total`) while
`costs/` uses correct dotted OTel names (`startd8.cost.total`), with no export config mapping them.
The metric names MUST be standardized to **dotted OTel-native** form; the Prometheus exporter
performs the dots→underscores transformation deterministically (so `startd8.cost.total` is exported
as `startd8_cost_total`). This is a consolidation (rename the hand-coded names + tests), not merely
documentation. **Compatibility:** because the Prometheus export of the new dotted names reproduces
the existing underscore names, downstream Prometheus/Grafana consumers are unaffected.

### 3.2 Orientation classification (feeds the taxonomy)

**REQ-AAO-004.** Each signal and each generated artifact MUST declare its **orientation** per the
two-axis taxonomy so it routes correctly: the raw metrics/SLI definitions are **system**-oriented;
agent dashboards are **human**-oriented; agent alerts & budget/notification policies are **bridge**.
This is the data that satisfies the taxonomy's REQ-OAT-024 (declare, don't guess) for agent metrics.

### 3.3 Category-5 artifacts to generate

**REQ-AAO-005 (dashboards — human).** A category-5 **agent dashboard** MUST be generatable, covering
the now-surfaced signals: cost & token burn (by model/provider), active sessions, request rate &
success rate, response-time distribution, context-usage saturation, truncation rate, cache-hit
efficiency. (Cost already has one — extend, don't fork.)

**REQ-AAO-006 (SLO/SLI — system).** Agent-workflow SLIs/SLOs MUST be definable:
- **success rate** = `successful_requests / requests_total`;
- **truncation rate** = `truncations_total / requests_total` (objective: below a threshold);
- **context-saturation** = fraction of sessions exceeding the 80% capacity warning;
- **cost budget** = spend per run/day vs a budget target (ties to usage_limits).

**REQ-AAO-007 (alerts — bridge).** Agent alerts MUST be generatable and **actionable** (per the
taxonomy bridge rule): cost-spike, budget-exceeded (from usage_limits levels), truncation-rate-high,
context-saturation, error/failure-rate-high — each with severity, summary, and a runbook/dashboard
link.

### 3.4 Close the descriptor→artifact loop

**REQ-AAO-008 (close the descriptor→artifact loop — ~70% built).** Planning found the loop's
infrastructure already exists: every module declares `_OTEL_DESCRIPTORS`, and `generate_manifest()`
collects + serializes them. Only the **last mile** is missing, so this requirement is *wiring*, not
greenfield:
1. add `category` + `orientation` to the descriptor schema (REQ-AAO-004 — a small schema change);
2. wire `generate_manifest()` output to populate `manifest_declared` in onboarding metadata.

This closes the loop: **SDK declares its telemetry → manifest → metadata → generated agent
observability** — so the artifact generator (taxonomy REQ-OAT-040) produces category-5 artifacts
from **declared facts**, not heuristics.

> **Cross-doc convergence (value/flexibility insight).** Because the SDK's own descriptors carry
> category+orientation, **the SDK is its own "declare, don't guess" producer** for its category-4/5
> metrics — it does **not** need the cap-dev-pipe onboarding-exporter change the taxonomy worried
> about (REQ-OAT-024/025) *for these SDK-emitted metrics*. The exporter dependency remains only for
> non-SDK / service-level metrics. This is flagged for reconciliation into the taxonomy doc once its
> CRP settles (not edited here to avoid the active review).

### 3.5 Fill the signal gaps (where instrumentation is missing)

**REQ-AAO-009 (outcome signal — ~70% done, narrowed).** session_tracking already tracks
`successful_requests`/`failed_requests` and emits a `status` label on `startd8_requests_total`; the
truncation **event** exists but is not a label. The remaining work is small: add `truncated` and
`retried` to the outcome label vocabulary (the event/data already exist) so success/error/truncated/
retry rates are queryable directly, without reconstructing them from `failed_requests` deltas.

**REQ-AAO-010 (eval hook, AAO-D4).** There MUST be a path to attach an eval/quality score to an agent
call (span attribute + optional metric), so output quality is observable, not just throughput. (May
be reserved/phased.)

**REQ-AAO-011 (tool use, AAO-D5).** Agentic tool calls SHOULD be instrumented — count, success/failure,
latency per tool — so tool-augmented workflows are observable. (May be reserved/phased.)

### 3.6 Keep the source of truth honest

**REQ-AAO-012 (descriptor↔emission parity — new, from planning).** Because the descriptor manifest
becomes the authoritative source feeding artifact generation (REQ-AAO-008), the **declared**
descriptors MUST match the **emitted** metrics/spans. There MUST be a test asserting parity — every
`_OTEL_DESCRIPTORS` entry corresponds to an actual `meter.create_*`/span emission and vice-versa — so
the manifest cannot silently drift (declared-but-not-emitted, or emitted-but-not-declared). Planning
found no such validation today; without it, a generator driven by the manifest would produce
dashboards/alerts for metrics that don't exist (or miss ones that do).

---

## 4. Non-requirements / out of scope

- Implementing the category-5 **generator** itself — this doc specifies the *requirements* and the
  signal catalog; the generator is taxonomy follow-up code (REQ-OAT-041 reserves the namespace).
- Project Observability (category 4 — `contextcore_task_*`): adjacent, separately specified.
- Changing the agent runtime behavior; this is observation-only.

## 5. Open questions

- **OQ-1.** Reconcile REQ-AAO-002 via derivation (session reads cost) or distinct-semantics? (Needs
  a read of how often both are emitted for the same call — possible double-counting of cost today.)
- **OQ-2.** Should eval scores (REQ-AAO-010) live in this category or a separate "eval observability"?
- **OQ-3.** Is the dotted vs underscore split intentional (OTel-native vs Prom-export) or accidental?
  If the former, REQ-AAO-003 is a documentation task; if the latter, a consolidation task.

---

## Appendix A — signal → (orientation, surfaced?) catalog

| Signal | Kind | Orientation (of its artifacts) | Surfaced today? |
|--------|------|-------------------------------|-----------------|
| `startd8.cost.*` (total/tokens/per_request) | metric | system (raw) → human (dashboard) / bridge (budget alert) | ✅ cost dashboard |
| `startd8_active_sessions` | metric (UpDownCounter) | human (dashboard) | ❌ |
| `startd8_requests_total` (+status) | metric | system (SLI: success rate) / human | ❌ |
| `startd8_tokens_total` (+direction) | metric | human (dashboard) | ❌ |
| `startd8_response_time_ms` | metric (Histogram) | human / system (latency SLO) | ❌ |
| `startd8_context_usage_ratio` | metric (Gauge) | bridge (saturation alert) / human | ❌ |
| `startd8_truncations_total` | metric | bridge (truncation alert) / system (SLI) | ❌ |
| `startd8_cost_total` (session) | metric | bridge (budget) / human | ❌ (dup of cost.total — AAO-D1) |
| `agent.generate:{name}` | span | system (trace) | ❌ |
| `pipeline.{name}[.step]` | span | system (trace) | ❌ |
| `startd8.events.total` | metric | system | ❌ |
| usage-limit level | event | bridge (budget alert) | ❌ (events only) |
| per-call outcome | (gap) | system (SLI) | ❌ REQ-AAO-009 |
| tool-call telemetry | (gap) | system / human | ❌ REQ-AAO-011 |

## Appendix B — requirement index

`REQ-AAO-001..003` catalog/canonicalization · `REQ-AAO-004` orientation · `REQ-AAO-005..007`
category-5 artifacts (human/system/bridge) · `REQ-AAO-008` descriptor→artifact loop ·
`REQ-AAO-009..011` signal gaps (outcome/eval/tool-use).

---

*(v0.1 footer superseded by the v0.2 summary below.)*

## Appendix C — pre-existing accidental complexity to eliminate (opportunistic)

Catalogued by the planning pass; the code-alignment follow-up SHOULD remove these. Effort S/M/L.

| # | Smell | Location | Why accidental | Distillation | Effort |
|---|-------|----------|----------------|--------------|--------|
| C-1 | **Dual cost APIs, latent double-count** | `costs/tracker.py:266` (`record_cost`) + `session_tracking.py:807` (`record_request`) | two user-facing APIs can both record one call's cost under two names | document distinct semantics + a guard that warns on double-invocation (REQ-AAO-002) | S |
| C-2 | **Duplicated label-building** | base agent + `session_tracking.py` rebuild `{agent_name, model, project_id}` independently | copy-paste; can drift | one shared label helper | S |
| C-3 | **Dead Prometheus fallback** | `session_tracking.py:438–503` | full legacy Prometheus path kept though OTel is the chosen export | remove (or gate behind an explicit opt-in) once OTel-only confirmed | M |
| C-4 | **Hand-coded underscore metric names** | `session_tracking.py` (`startd8_*`) | diverges from the dotted OTel convention used in `costs/` | rename to dotted; Prom export underscores (REQ-AAO-003) | M |
| C-5 | **No descriptor↔emission validation** | `observability/manifest.py` `_OTEL_DESCRIPTORS` vs `meter.create_*` | the manifest can declare metrics that aren't emitted (or miss emitted ones) | add a parity test (REQ-AAO-012) | M |
| C-6 | **Descriptor schema lacks category/orientation** | `observability/manifest.py` MetricDescriptor/SpanDescriptor | the routing fields the taxonomy needs aren't in the schema | add two fields (REQ-AAO-004) — also unblocks REQ-AAO-008 | S |

**Net:** C-1/C-2/C-6 are S quick wins; C-5 (parity test) is a high-value robustness win that makes
the descriptor manifest trustworthy as the generation source of truth; C-3 (dead Prometheus path) is
a standalone deletion; C-4 rides on REQ-AAO-003. Most are *removals*, consistent with the taxonomy's
distillation-first principle.

---

*v0.2 — Post-planning self-reflective update. Corrected 2 over-stated findings (cost double-count is
latent not actual; descriptor loop ~70% built), narrowed 2 requirements (001, 009), resolved the
naming split to "standardize on dotted" (003), added 1 requirement (012 descriptor↔emission parity),
surfaced the cross-doc convergence (the SDK is its own declare-don't-guess producer), and catalogued
6 accidental-complexity items (Appendix C). Net finding: the infrastructure largely exists — this is
mostly wiring + cleanup, not new machinery.*
