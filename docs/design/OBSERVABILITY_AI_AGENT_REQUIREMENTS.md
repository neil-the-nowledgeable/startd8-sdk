# AI Agent Observability — Requirements (Taxonomy Category 5)

**Date:** 2026-05-31
**Status:** Draft v0.3 — combined cat-4/5 CRP R1 triaged (8 F-suggestions applied; shared spine extracted to `OBSERVABILITY_DESCRIPTOR_SPINE_REQUIREMENTS.md`)
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
framing was a misdiagnosis — the families serve different questions). **Guard contract (R1-F5):**
the detection key is a single `correlation_id` recorded via *both* `CostTracker.record_cost()` and
`SessionTracker.record_request()`; the action is a **single WARN log** (not drop, not raise — the
families are legitimately distinct, so the guard surfaces the likely misuse without altering either
emission path).

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

> **Schema contract owned by `REQ-OBS-SHARED-001`** (R1-F1/F7; R2-F8). The `category`/`orientation`
> field names, enum domains, and defaults are defined **once** in
> `OBSERVABILITY_DESCRIPTOR_SPINE_REQUIREMENTS.md` and referenced here **by ID only — not restated**
> (the no-restatement rule is itself REQ-OBS-SHARED-001), so the cat-4 and cat-5 implementations cannot
> diverge on spelling or default.

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
>
> **Emit-vs-cede contrast (R1-F2/F8).** Cat 5 = **SDK emits** (every metric has an in-process
> `meter.create_*` site) → produced artifacts, **no** `skip_reason`. This is the mirror image of cat 4
> = **SDK produces then cedes** to ContextCore (`contextcore_*` gauges surface as
> `skip_reason=owned_elsewhere`/`owner=contextcore`). The reason no cede vocabulary appears in *this*
> doc is precisely that cat-5 metrics have an emission site; a reviewer should not "fix" the asymmetry.
> The single-generator routing contract for both manifests is `REQ-OBS-SHARED-004`.

### 3.5 Fill the signal gaps (where instrumentation is missing)

**REQ-AAO-009 (outcome signal — ~70% done, narrowed).** session_tracking already tracks
`successful_requests`/`failed_requests` and emits a `status` label on `startd8_requests_total`; the
truncation **event** exists but is not a label. The remaining work is small: add `truncated` and
`retried` to the outcome label vocabulary (the event/data already exist) so success/error/truncated/
retry rates are queryable directly, without reconstructing them from `failed_requests` deltas.

**REQ-AAO-010 (eval hook, AAO-D4).** There MUST be a path to attach an eval/quality score to an agent
call (span attribute + optional metric), so output quality is observable, not just throughput.
**Scope (R1-F4): OUT this pass** — reserved under the `startd8.agent.eval.*` namespace; no "may".

**REQ-AAO-011 (tool use, AAO-D5).** Agentic tool calls SHOULD be instrumented — count, success/failure,
latency per tool — so tool-augmented workflows are observable.
**Scope (R1-F4): OUT this pass** — reserved under the `startd8.agent.tool.*` namespace; no "may".

### 3.6 Keep the source of truth honest

**REQ-AAO-012 (descriptor↔emission parity — new, from planning).** Because the descriptor manifest
becomes the authoritative source feeding artifact generation (REQ-AAO-008), the **declared**
descriptors MUST match the **emitted** metrics/spans. There MUST be a test asserting parity so the
manifest cannot silently drift. **The relation is kind-aware and owned by `REQ-OBS-SHARED-002`**
(R1-F6/F7): **metrics → bijection** (every descriptor ⇔ a `meter.create_*` site, both directions);
**spans → subset** (declared attrs ⊆ emitted, because span attribute sets are open). The earlier
"and vice-versa" wording implied bijection for *all* kinds and drifted against the project plan's
"subset" — the shared requirement reconciles this to one kind-aware relation referenced by both
plans. Planning found no such validation today; the first thing it catches is the live-but-undeclared
`complexity.tier_distribution` histogram (see `OBSERVABILITY_CAT45_CODE_VERIFICATION.md` §A-1).

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

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Inline schema-field contract (names/enums/defaults) | claude-opus-4-8-1m | Owned by new `REQ-OBS-SHARED-001`; REQ-AAO-004 now references it by ID | 2026-05-31 |
| R1-F2 | State emit-vs-cede contrast in §3.4 | claude-opus-4-8-1m | Added emit-vs-cede note under REQ-AAO-008; cede contract = `REQ-OBS-SHARED-004` | 2026-05-31 |
| R1-F3/F9 | Authoritative vs projection of REQ-OAT-070a registry | claude-opus-4-8-1m | Resolved in `REQ-OBS-SHARED-003`: separate layers (telemetry-decl vs artifact-dispatch), shared enum vocabulary, vocabulary-level (not row-level) reconciliation | 2026-05-31 |
| R1-F4 | Commit in/out for AAO-010/011 (drop "may") | claude-opus-4-8-1m | Both marked **OUT this pass** with reserved namespaces | 2026-05-31 |
| R1-F5 | AAO-002 guard: detection key + action | claude-opus-4-8-1m | Specified: same `correlation_id` via both APIs → single WARN | 2026-05-31 |
| R1-F6 | AAO-012 parity relation (bijection vs subset) | claude-opus-4-8-1m | Kind-aware (`REQ-OBS-SHARED-002`): metrics bijection, spans subset | 2026-05-31 |
| R1-F7 | One shared requirement (REQ-OBS-SHARED-001) | claude-opus-4-8-1m | Created `OBSERVABILITY_DESCRIPTOR_SPINE_REQUIREMENTS.md`; AAO-004/008/012 reference by ID | 2026-05-31 |
| R1-F8 | Cross-ref cat-4 cede vocabulary for single generator | claude-opus-4-8-1m | `REQ-OBS-SHARED-004` (one generator, two manifests) | 2026-05-31 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-05-31

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-31 18:46:04 UTC
- **Scope**: Requirements quality (F-prefix) for AI Agent Observability (cat 5), weighted toward the 5 cross-doc focus asks on the shared `_OTEL_DESCRIPTORS` descriptor-registry spine vs the project-obs doc (cat 4) and the settled taxonomy registry (REQ-OAT-070a).

##### Focus-ask answers (sponsor cross-doc concerns 1–5)

**Ask 1 — Spine consistency (AAO-004/008/012 vs PRO-002/005: same schema change + parity test, or drift?).**
- **Summary answer:** Partial — both docs *intend* one shared change and say so in prose, but neither states the schema/parity contract in a single normative place, so two PRs can still diverge.
- **Rationale:** REQ-AAO-004 ("add category + orientation to the descriptor schema") and REQ-PRO-002 ("reuses that single shared schema change … does not duplicate it") describe the *same* `MetricDescriptor`/`SpanDescriptor` field addition, and REQ-AAO-012 / PRO plan Phase 2.3 describe the *same* parity test. But the normative text lives in two docs with only narrative cross-references ("same change the AI-agent doc specifies"); there is no shared requirement ID owning the field names, defaults, and enum values, so the two implementations can drift on, e.g., `orientation` enum spelling or default.
- **Assumptions / conditions:** Holds unless the orchestrator designates one doc (AAO) as the normative owner of the schema-field contract and PRO references it by ID rather than restating it.
- **Suggested improvements:** Promote the schema-field + parity-test contract to a single shared requirement (see R1-F1 / cross-doc R1-F8) that both AAO-004/012 and PRO-002 reference by ID; specify field names, the `orientation` enum (`system`/`human`/`bridge`), and the `category` enum values inline so both PRs cannot diverge.

**Ask 2 — Emit-vs-cede asymmetry coherent and implementable?**
- **Summary answer:** Yes, coherent — cat 5 (SDK emits its own metrics → is its own declare-don't-guess producer) and cat 4 (SDK produces raw signals, ContextCore owns gauges) are genuinely different ownership shapes, and this doc states its side precisely.
- **Rationale:** §3.4 / REQ-AAO-008 are explicit that the SDK's descriptors carry category+orientation so "the SDK is its own declare, don't guess producer," dissolving the REQ-OAT-025 exporter dependency *for SDK-emitted metrics only* (boundary stated). The asymmetry is real because cat-5 metrics have an in-process `meter.create_*` emission site, whereas cat-4 gauges (`contextcore_task_*`) have none in startd8. The one imprecision is that this doc does not name the *cede* vocabulary (`skip_reason=owned_elsewhere`/`owner`) that the cat-4 doc must use — but that is a cat-4 obligation, not a cat-5 gap.
- **Assumptions / conditions:** None for the cat-5 side; the cede precision is the project doc's responsibility (see PRO R1-F cross-doc).
- **Suggested improvements:** Add one sentence to §3.4 explicitly contrasting "cat 5 = emit (no cede)" against "cat 4 = produce-then-cede" so a reader of this doc alone understands why no `skip_reason` appears here (see R1-F2).

**Ask 3 — Do these descriptors fit the taxonomy's single type-keyed registry (REQ-OAT-070a), or introduce a parallel metric-side registry?**
- **Summary answer:** Depends — as written, `category`/`orientation` are stored as *independent fields per descriptor*, which conflicts with REQ-OAT-070a's rule that they are **derived projections, never independently maintained**.
- **Rationale:** REQ-OAT-070a (taxonomy, settled) mandates a single `declared_type`-keyed registry where `category`/`orientation` are projections of the registry row, "never independently authored on each artifact." REQ-AAO-004/008 instead add `category`+`orientation` as *fields on each `_OTEL_DESCRIPTORS` entry*, hand-populated per descriptor (plan step 1.1: "populate category + orientation on every entry"). That is a metric-side parallel store of the same axes the taxonomy says must be derived — a drift surface the taxonomy explicitly designed away. The dotted-vs-underscore naming (REQ-AAO-003) is orthogonal and does not interact with the registry collision.
- **Assumptions / conditions:** Holds if the metric descriptor is treated as an artifact-type-keyed entry that the taxonomy registry could project from; if the descriptor manifest is a strictly separate concern (telemetry-declaration vs artifact-type-dispatch), the two registries are legitimately different layers and there is no conflict.
- **Suggested improvements:** Add a requirement (R1-F3) stating whether the descriptor `category`/`orientation` are authoritative or are projections sourced from the taxonomy REQ-OAT-070a registry, and a parity assertion that the two never disagree for a given signal.

**Ask 4 — Shared "descriptor schema keystone" + parity test concretely sequenced, or two PRs each add it?**
- **Summary answer:** Partial — both plans name a shared keystone but the sequencing instruction is soft ("sequence so this is shared"); nothing makes one PR land it and the other depend on it.
- **Rationale:** AAO plan Phase 0.4/1.1–1.2 and PRO plan Phase 1.1/2.3 each independently list "add category+orientation fields" and "add the parity test." Both before-code checklists say it is shared, but neither names the landing PR/branch or makes the second category's work *blocked on* the first. Both target the same branch (`feat/observability-followup-run007`), which reduces but does not eliminate the double-add hazard.
- **Assumptions / conditions:** Holds unless the orchestrator records an explicit ordering (one keystone PR, both categories rebase on it).
- **Suggested improvements:** S-side plan suggestion (see PLAN R1-S) to name the keystone landing step once and have cat-4 declare an explicit dependency edge on it.

**Ask 5 — Deferred-vs-in-scope boundary: is the in-scope work genuinely small and the deferred work clearly elsewhere/later?**
- **Summary answer:** Yes for cat 5 — this doc defers no metric-emission (it already emits), reserves only eval/tool-use (REQ-AAO-010/011 marked "may be reserved/phased"), and scopes the generator out (§4) to taxonomy REQ-OAT-041.
- **Rationale:** §4 cleanly excludes the generator; REQ-AAO-010/011 are explicitly phased; the in-scope set (catalog + 2 schema fields + parity test + name standardization + label additions) is small and wiring-shaped. The one soft edge: REQ-AAO-010/011 say "may be reserved" — "may" leaves the in-scope boundary to implementer discretion rather than a committed line.
- **Assumptions / conditions:** None material.
- **Suggested improvements:** Replace "may be reserved/phased" with a committed in/out marker for REQ-AAO-010/011 (see R1-F4).

##### Numbered suggestions (F-prefix → requirements)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | Specify the descriptor schema-field contract inline in REQ-AAO-004: exact field names (`category`, `orientation`), the `orientation` enum (`system`\|`human`\|`bridge`), the `category` enum (incl. `ai_agent_observability`, `project_observability`), and default values — rather than the prose "add 2 schema fields". | REQ-AAO-004 is the normative owner of the schema change that PRO-002 reuses; without an inline contract the two categories' PRs can diverge on enum spelling/defaults (focus Ask 1). | REQ-AAO-004 (§3.2) | Schema unit test asserts the two fields exist with the named enum domains and defaults; PRO-002 references REQ-AAO-004 by ID. |
| R1-F2 | Architecture | medium | Add one sentence to §3.4 / REQ-AAO-008 contrasting "cat 5 = SDK emits (no cede)" vs "cat 4 = SDK produces then cedes to ContextCore", and state explicitly that no `skip_reason`/`owner` appears in cat-5 because every cat-5 metric has an in-process emission site. | A reader of this doc alone cannot tell why the cede vocabulary present in the cat-4 doc is absent here; making the emit-vs-cede boundary explicit prevents a future reviewer from "fixing" the asymmetry (focus Ask 2). | §3.4 after the cross-doc convergence note | Doc review: the sentence names both ownership shapes and ties the absence of `skip_reason` to the in-process emission site. |
| R1-F3 | Data | high | State whether the descriptor `category`/`orientation` fields are **authoritative** or are **projections** of the taxonomy single type-keyed registry (REQ-OAT-070a, which forbids independently-maintained category/orientation), and require a parity assertion that descriptor-declared axes never disagree with the registry for the same signal. | REQ-OAT-070a (settled) makes category/orientation derived projections; REQ-AAO-004/008 hand-populate them per descriptor — a parallel metric-side store the taxonomy designed away (focus Ask 3). The doc must declare which is source-of-truth. | New REQ-AAO-013 under §3.4, or a clause in REQ-AAO-008 | Test: for each signal, descriptor `(category,orientation)` equals the value projected from the REQ-OAT-070a registry (or the doc explicitly declares the descriptor manifest a separate layer). |
| R1-F4 | Validation | low | Replace "(May be reserved/phased.)" on REQ-AAO-010 and REQ-AAO-011 with a committed in-scope / out-of-scope marker and, if out, a reserved namespace note (mirroring §4's generator exclusion). | "May" leaves the in/out boundary to implementer discretion, weakening the "in-scope work is genuinely small" claim (focus Ask 5); a committed marker makes the deferral testable in the before-code checklist. | REQ-AAO-010, REQ-AAO-011 (§3.5) | Checklist item: each of 010/011 carries an explicit in/out marker; no "may" remains on scope lines. |
| R1-F5 | Risks | medium | REQ-AAO-002's double-invocation guard MUST specify the **detection key and action**: detect when the same `correlation_id` is recorded via both `CostTracker.record_cost()` and `SessionTracker.record_request()`, and define whether the guard warns, drops the duplicate, or raises. | REQ-AAO-002 says "guard against double-invocation" and Appendix C C-1 says "warns on double-invocation" but the requirement itself does not commit to key or action — an implementer cannot build/test the guard from the requirement alone. | REQ-AAO-002 (§3.1) | Unit test: recording the same `correlation_id` cost via both APIs triggers the specified action (e.g. one WARN log) deterministically. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F6 | Validation | medium | REQ-AAO-012 (descriptor↔emission parity) MUST state its **enforcement boundary**: does parity require *exact* bijection (every descriptor ⇔ every `meter.create_*`/span), or descriptor ⊆ emitted? The PRO plan Phase 2.3 asserts "declared attrs ⊆ emitted attrs" (subset), while AAO-012 reads as bijection ("and vice-versa"). | The two docs share one parity test (focus Ask 1/4) but specify different relations (bijection here vs subset in PRO 2.3) — the shared test cannot satisfy both; this is a latent cross-doc contradiction in the very mechanism meant to prevent drift. | REQ-AAO-012 (§3.6) | Test: the parity helper's relation (bijection vs subset) is documented identically in both docs and the single shared test enforces exactly that relation. |

##### Cross-doc consistency (cats 4 & 5)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F7 | Architecture | high | Create ONE shared requirement (proposed `REQ-OBS-SHARED-001`) owning the descriptor schema change (`category`/`orientation` fields + enums + defaults) AND the descriptor↔emission parity test, and have AAO-004/008/012 and PRO-002/005 reference it by ID instead of each restating it. | Today the schema change and parity test are described in both docs with only narrative cross-links ("same change the AI-agent doc specifies"); one normative owner eliminates the drift risk the shared spine was meant to remove (Ask 1). Note: PRO plan 2.3 says "subset" while AAO-012 says "bijection" — proof the duplication is already drifting (see R1-F6). | New top-level shared requirement referenced from §3.2/§3.4/§3.6 here and §3.2 in PRO | Both docs cite the same requirement ID; a single schema/parity test module is referenced by both plans; no field/enum/relation is defined in two places. |
| R1-F8 | Interfaces | medium | Make the emit-vs-cede asymmetry implementable by cross-referencing the cat-4 cede mechanism: state here that the cat-4 cede uses the taxonomy `skip_reason=owned_elsewhere`/`owner` honest-skip (REQ-OAT-011/052), and that cat-5 metrics never use it because they emit in-process — so a generator reading the manifest routes cat-5 as produced and cat-4 gauges as owned_elsewhere. | Ask 2 asks whether the asymmetry is "precise enough to implement." It is coherent but the cat-5 doc never names the cede vocabulary the generator must apply to the *other* side; naming it here closes the loop so the single generator handles both manifests uniformly. | §3.4 cross-doc convergence note | Test: a generator fed both manifests emits cat-5 metrics as produced artifacts and cat-4 `contextcore_*` as skips with `skip_reason=owned_elsewhere`. |
| R1-F9 | Data | high | Resolve the registry-model question (Ask 3) at the cross-doc level: declare in BOTH docs whether the `_OTEL_DESCRIPTORS` metric-side `category`/`orientation` are projections of the taxonomy REQ-OAT-070a `declared_type`-keyed registry or a deliberately separate telemetry-declaration layer — and if separate, add a reconciliation assertion that the two registries never disagree for an overlapping signal. | REQ-OAT-070a (settled) forbids independently-maintained category/orientation; both cat-4/5 docs hand-populate them on descriptors. Either they are projections (then say from-where) or a second registry exists (then bound it). Leaving it implicit reintroduces exactly the parallel-table accidental complexity the taxonomy R2-F4 removed. | New shared clause referenced from REQ-AAO-008 and REQ-PRO-002 | Cross-doc test: for any signal present in both the descriptor manifest and the taxonomy registry, `(category,orientation)` agree; doc states which side is authoritative. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — this is Round R1 (first encounter); no prior untriaged suggestions exist.
