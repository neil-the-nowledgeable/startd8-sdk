# AI Agent Observability — Implementation Plan

**Date:** 2026-05-31
**Status:** Plan v0.1 (paired with `OBSERVABILITY_AI_AGENT_REQUIREMENTS.md` v0.2)
**Scope:** SDK modules — `src/startd8/observability/manifest.py`, `src/startd8/session_tracking.py`,
`src/startd8/costs/otel_metrics.py` + `tracker.py`, `src/startd8/agents/` (label helper, outcome
labels), `src/startd8/events/otel_bridge.py`. The **category-5 artifact generator** that *consumes*
the manifest is taxonomy follow-up (REQ-OAT-041), cross-referenced here, not built in this plan.
**Branch:** `feat/observability-followup-run007` (or a fresh branch).

---

## Guiding principle

Planning showed the hard infrastructure (per-module `_OTEL_DESCRIPTORS` + `generate_manifest()`)
**already exists** — this is mostly **wiring + cleanup**, not new machinery. Order distillation
first: Phase 0 removes accidental complexity; Phase 1 makes the descriptor manifest the **trustworthy,
routing-aware source of truth** (the keystone); the rest is wiring and small additions. Like the
taxonomy pass, expect a **net-negative** line delta in the cleanup phases.

```
Phase 0  Cleanups / distillation                 C-1, C-2, C-3, C-6
Phase 1  Keystone: descriptor schema + parity     REQ-AAO-001/004/012 (+ C-5/C-6)
Phase 2  Standardize metric names to dotted       REQ-AAO-003 (C-4)
Phase 3  Close the descriptor→metadata loop        REQ-AAO-008
Phase 4  Fill signal gaps                          REQ-AAO-009 (010/011 reserved)
Phase 5  Category-5 artifact definitions           REQ-AAO-005/006/007 (generation = taxonomy follow-up)
```

---

## Phase 0 — Cleanups / distillation (mostly removals)

| Step | Change | Files | Removes |
|------|--------|-------|---------|
| 0.1 | Document the **distinct semantics** of `startd8.cost.*` (global) vs `startd8_cost_total` (per-session) in both modules' docstrings; add a guard/log warning if the same `correlation_id`'s cost is recorded via both APIs (REQ-AAO-002) | costs/tracker.py, session_tracking.py | C-1 |
| 0.2 | Extract a shared label helper for `{agent_name, model, project_id}` used by both the agent path and session_tracking | agents/, session_tracking.py | C-2 |
| 0.3 | Remove (or gate behind explicit opt-in) the **dead Prometheus fallback** `session_tracking.py:438–503` once OTel-only is confirmed | session_tracking.py | C-3 |
| 0.4 | Add `category` + `orientation` fields to `MetricDescriptor`/`SpanDescriptor` (defaults so existing descriptors still construct) | observability/manifest.py | C-6 (also REQ-AAO-004) |

**Validation:** full suite green; for 0.3, confirm no consumer of the Prometheus path (grep); for
0.1, a unit test that double-recording the same correlation_id triggers the guard.

---

## Phase 1 — Keystone: descriptor schema + parity (REQ-AAO-001/004/012)

Makes the manifest authoritative and routing-aware before anything consumes it.

| Step | Change | Files |
|------|--------|-------|
| 1.1 | Populate `category` + `orientation` on **every** `_OTEL_DESCRIPTORS` entry (cost/session = agent obs; task_* = project obs; per the requirements Appendix A orientation map) | all modules declaring descriptors |
| 1.2 | Add the **descriptor↔emission parity test** (REQ-AAO-012): assert every declared descriptor maps to an actual `meter.create_*`/span emission and vice-versa — fail on declared-but-not-emitted or emitted-but-not-declared | tests/ + a small introspection helper |
| 1.3 | Add the currently-undocumented signals to descriptors where missing (so the catalog is complete, REQ-AAO-001) | session_tracking.py, agents/tracked.py |

**Validation:** parity test passes (and *fails* on a deliberately mis-declared descriptor); every
descriptor carries category+orientation; `generate_manifest()` output includes the new fields.

---

## Phase 2 — Standardize metric names to dotted (REQ-AAO-003; C-4)

| Step | Change | Files |
|------|--------|-------|
| 2.1 | Rename hand-coded underscore metric names (`startd8_cost_total`, `startd8_tokens_total`, `startd8_active_sessions`, …) to dotted OTel form (`startd8.session.cost.total`, etc.); the Prometheus exporter reproduces the underscore names automatically | session_tracking.py + descriptors + tests |

**Validation:** Prometheus export of the new dotted names reproduces the **existing** underscore
metric names byte-for-byte (so Grafana/Prom consumers are unaffected); descriptor names updated to match.

---

## Phase 3 — Close the descriptor→metadata loop (REQ-AAO-008)

| Step | Change | Files |
|------|--------|-------|
| 3.1 | Wire `generate_manifest()` output to populate onboarding-metadata `manifest_declared` (each entry carrying name/type/unit/labels/**category**/**orientation**) — the SDK becomes its own "declare, don't guess" producer | observability/manifest.py + a small bridge |

**Validation:** a generated onboarding metadata's `manifest_declared` for the SDK's own metrics is
produced from the manifest (not hand-authored), carries category+orientation, and matches the
descriptor catalog. **Cross-doc:** this satisfies taxonomy REQ-OAT-024 for SDK-emitted metrics
without the REQ-OAT-025 exporter change (reconcile into the taxonomy doc post-CRP).

---

## Phase 4 — Fill signal gaps (REQ-AAO-009; 010/011 reserved)

| Step | Change | Files |
|------|--------|-------|
| 4.1 | Add `truncated`/`retried` to the outcome label vocabulary on `startd8_requests_total` (event/data already exist) (REQ-AAO-009) | session_tracking.py, agents/tracked.py |
| 4.2 | (reserved) eval-score hook on agent calls (span attr + optional metric) (REQ-AAO-010) | agents/tracked.py |
| 4.3 | (reserved) tool-call telemetry (count/success/latency) (REQ-AAO-011) | agents/base.py |

**Validation:** success/error/truncated/retry rates are directly queryable from the `status`/outcome
label, without reconstructing from `failed_requests` deltas.

---

## Phase 5 — Category-5 artifact definitions (REQ-AAO-005/006/007)

The **definitions** (SLI formulas, alert specs, dashboard panel set) are in scope as descriptor/
template metadata; the **generation** of dashboards/alerts/SLOs is the taxonomy category-5 generator
(reserved, REQ-OAT-041) — cross-referenced, not built here.

| Step | Change | Files |
|------|--------|-------|
| 5.1 | Define agent SLIs/SLOs (success rate, truncation rate, context-saturation, cost budget) as manifest template metadata (REQ-AAO-006) | observability/manifest.py |
| 5.2 | Define agent alert specs (cost-spike, budget-exceeded, truncation-rate-high, context-saturation, error-rate) — bridge-actionable (severity/summary/links) (REQ-AAO-007) | observability/manifest.py |
| 5.3 | Extend the existing cost dashboard into a full agent dashboard (sessions, latency, saturation, truncation, cache efficiency) (REQ-AAO-005) — **extend, don't fork** | dashboards/ + mixin |

**Validation:** the SLI/alert/dashboard definitions are present in the manifest and consumed by the
(future) category-5 generator to produce deployable artifacts.

---

## Traceability (requirement → phase)

| REQ-AAO | Phase | REQ-AAO | Phase |
|---------|-------|---------|-------|
| 001 | 1 | 007 | 5.2 |
| 002 | 0.1 | 008 (keystone loop) | 3 |
| 003 | 2 | 009 | 4.1 |
| 004 | 0.4 + 1.1 | 010 (reserved) | 4.2 |
| 005 | 5.3 | 011 (reserved) | 4.3 |
| 006 | 5.1 | 012 (parity) | 1.2 |

## Before-code checklist

- [ ] Every v0.2 requirement maps to a phase; every step traces to a requirement / Appendix-C item.
- [ ] Phase 0 net-removes lines (dead Prometheus path, deduped labels).
- [ ] Parity test (1.2) fails on a deliberately mis-declared descriptor before it's trusted (3.1).
- [ ] Phase 2 rename verified to preserve the exported Prometheus metric names (no consumer break).
- [ ] Cross-doc: the Phase-3 loop's effect on taxonomy REQ-OAT-024/025 is reconciled post-CRP.

---

*Plan v0.1 — paired with requirements v0.2. Six phases; Phases 0–1 distill + establish the
trustworthy descriptor manifest, Phases 2–4 are wiring/small additions, Phase 5 defines artifacts
that the taxonomy category-5 generator (deferred) consumes. Net: mostly wiring + cleanup.*
