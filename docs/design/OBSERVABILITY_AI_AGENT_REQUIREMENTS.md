# AI Agent Observability — Requirements (Taxonomy Category 5)

**Date:** 2026-05-31
**Status:** Draft v0.1 — surfacing existing telemetry as formal requirements
**Lineage:** Instantiates **Category 5 — AI Agent Observability** of
`OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md` (the "reserved — signals emitted, no generator"
row). Evidence base: a read-only telemetry inventory of `src/startd8/` (costs/, session_tracking,
agents/tracked, orchestration, events/otel_bridge, otel, observability/manifest).
**Subject observed:** the **AI agents and LLM workflows** themselves — cost, tokens, sessions,
context usage, latency, truncation, tool use, agent/pipeline traces, output quality.

---

## 0. Motivation

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

**REQ-AAO-002 (reconcile duplication, AAO-D1).** The two cost/token families MUST be reconciled to a
single authoritative source. Either (a) session_tracking consumes/derives from the cost metrics, or
(b) the two are explicitly given distinct semantics (e.g. cost-metrics = global counters;
session-metrics = per-session) and that relationship is documented. Duplicate emission of the same
fact under two names without a stated relationship is prohibited.

**REQ-AAO-003 (naming, AAO-D2).** Choose one canonical naming form and document the dotted↔underscore
mapping (OTel metric names are dotted; Prometheus export underscores them — the mapping MUST be
deterministic and recorded, not divergent hand-naming).

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

**REQ-AAO-008 (manifest is source of truth, AAO-D6).** `_OTEL_DESCRIPTORS` / `generate_manifest()`
MUST be the authoritative input that populates `manifest_declared` in onboarding metadata (carrying
each signal's category + orientation per REQ-AAO-001/004), so the observability artifact generator
(taxonomy REQ-OAT-040) produces category-5 artifacts from declared facts, not heuristics. This
closes the loop: **SDK declares its telemetry → manifest → metadata → generated agent observability.**

### 3.5 Fill the signal gaps (where instrumentation is missing)

**REQ-AAO-009 (outcome signal, AAO-D4).** Each agent call MUST carry a first-class outcome
(`success | truncated | retried | error`) as a metric label and span attribute, so success/error/retry
rates are queryable without reconstructing them from `failed_requests` deltas.

**REQ-AAO-010 (eval hook, AAO-D4).** There MUST be a path to attach an eval/quality score to an agent
call (span attribute + optional metric), so output quality is observable, not just throughput. (May
be reserved/phased.)

**REQ-AAO-011 (tool use, AAO-D5).** Agentic tool calls SHOULD be instrumented — count, success/failure,
latency per tool — so tool-augmented workflows are observable. (May be reserved/phased.)

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

*Draft v0.1 — surfaces existing AI-agent telemetry (4 cost metrics surfaced; 7 session metrics +
agent/pipeline spans emitted-but-undocumented) as Category-5 requirements; names 6 findings
(duplication, naming, surfacing, weak quality, no tool-use, unclosed descriptor loop) and 11
requirements. Candidate for a reflective-requirements + CRP pass like the taxonomy doc.*
