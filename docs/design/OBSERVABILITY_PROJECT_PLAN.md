# Project Observability — Implementation Plan

**Date:** 2026-05-31
**Status:** Plan v0.1 (paired with `OBSERVABILITY_PROJECT_REQUIREMENTS.md` v0.2)
**Scope:** SDK modules — `observability/manifest.py` + `collector.py`, `otel_conventions.py`,
`contractors/artisan_phases/runner.py` + `artisan_contractor.py`, `contractors/development.py`,
`complexity/classifier.py`, doc/comments on `task_tracking_emitter.py` + `integrations/contextcore.py`.
The **category-4 artifact generator** and the **burndown/velocity dashboards** are out of scope
(generator = taxonomy REQ-OAT-041; dashboards = ceded to ContextCore + tracker skills).
**Branch:** `feat/observability-followup-run007` (or a fresh branch).

---

## Guiding principle

Planning showed category-4 is mostly **documentation + declaring existing spans** in the *one shared*
descriptor manifest — the ownership seam is already clean in code, and the heavy lifting (metrics,
live progress) is deferred or ContextCore's. Distill first; declare, don't build. The schema change
that carries `category`/`orientation` is **shared with the AI-agent doc** — land it once.

```
Phase 0  Cleanups / distillation                  C-1, C-2, C-4
Phase 1  Shared keystone: descriptor schema fields  REQ-PRO-002/005 (= AI-agent REQ-AAO-004; ONE change)
Phase 2  Declare the project spans                  REQ-PRO-002, 008
Phase 3  Document the ownership boundary            REQ-PRO-001, 004
Phase 4  Declare delivery signals + SLIs (authored)  REQ-PRO-003a, 006, 007
Phase 5  (deferred) metric-ify; live progress        REQ-PRO-003b (L); progress = ContextCore
```

---

## Phase 0 — Cleanups / distillation

| Step | Change | Files | Removes |
|------|--------|-------|---------|
| 0.1 | Disambiguate the two "task" concepts — rename codegen `task.*` span attrs to `codegen.task.*` (or keep `task.*` for work-items and namespace the chunk attrs), and document the split | otel_conventions.py, development.py, runner.py | C-1 (REQ-PRO-008) |
| 0.2 | Remove the **dead** tier histogram in `complexity/classifier.py:23–35` (created, never recorded) — or wire a `record()` if tier-rate is wanted | complexity/classifier.py | C-2 |
| 0.3 | Reconcile/document the phase-span naming (`artisan.workflow.{id}.phase.{phase}` vs `phase.{type}.attempt.{n}`) | artisan_contractor.py, runner.py | C-4 |

**Validation:** suite green; the renamed attrs are emitted under the new names; no consumer of the
old codegen `task.*` names remains (grep).

---

## Phase 1 — Shared keystone: descriptor schema fields (REQ-PRO-002/005 = AAO-004)

| Step | Change | Files |
|------|--------|-------|
| 1.1 | Add `category` + `orientation` fields to `MetricDescriptor`/`SpanDescriptor` (additive defaults). **This is the same change the AI-agent doc specifies (REQ-AAO-004)** — land it once; both categories consume it | observability/manifest.py |

**Cross-doc:** sequence so this is shared with the AI-agent plan's Phase-0.4/1.1, not done twice.
**Validation:** existing descriptors still construct; `generate_manifest()` includes the new fields.

---

## Phase 2 — Declare the project spans (REQ-PRO-002, 008)

| Step | Change | Files |
|------|--------|-------|
| 2.1 | Declare the already-emitted `phase.*` and `codegen.task.*` span attributes in `_OTEL_DESCRIPTORS` with `category=project_observability`, `orientation=system` | runner.py, artisan_contractor.py, development.py |
| 2.2 | Add those modules to `collector.py._INSTRUMENTED_MODULES`. **Do NOT** add `task_tracking_emitter` (it emits no OTel — state-file channel only) | collector.py |
| 2.3 | Add the descriptor↔emission **parity test** (shared with AI-agent REQ-AAO-012) so declared attrs ⊆ emitted attrs — closing the C-3 drift risk | tests/ |

**Validation:** parity test passes (and fails on a deliberately mis-declared attr); project spans
appear in `generate_manifest()` output with category/orientation.

---

## Phase 3 — Document the ownership boundary (REQ-PRO-001, 004)

| Step | Change | Files |
|------|--------|-------|
| 3.1 | Add docstrings/comments stating the boundary: startd8 writes state files + spans + Kaizen JSON; **ContextCore owns** the gauges, **live progress computation**, and burndown dashboards | task_tracking_emitter.py, integrations/contextcore.py |
| 3.2 | Confirm the generator reports declared `contextcore_*` gauges as **ContextCore-owned honest-skip** (taxonomy REQ-OAT-011), not startd8-emitted | (cross-ref taxonomy generator) |

**Validation:** docs/comments present; no code reaches into ContextCore beyond the optional wrapper;
no progress-delta emitter is added (REQ-PRO-004 explicitly avoids it).

---

## Phase 4 — Declare delivery signals + SLIs (hand-authored) (REQ-PRO-003a, 006, 007)

The collector auto-discovers descriptors; SLO/alert/JSON-schema sections are **hand-maintained**.

| Step | Change | Files |
|------|--------|-------|
| 4.1 | Author a manifest section declaring the JSON delivery signals' schema (Kaizen `root_cause`/`pipeline_stage`/dual-score, velocity/trend, persistent-failure, improvement deltas) + sample SLI/PromQL query forms (REQ-PRO-003a/007) | observability/manifest.py (authored section) |
| 4.2 | Document generate-vs-cede: startd8 provides catalog + SLI defs + MAY emit delivery-health **alerts** (persistent-failure, quality-regression, cost-outlier) from owned signals; **dashboards are ceded** (REQ-PRO-006) | manifest.py / generator notes |

**Validation:** the manifest lists every delivery signal (no silent JSON-only project-health signal);
SLI query forms present; cede documented.

---

## Phase 5 — Deferred

- **REQ-PRO-003b (metric-ify):** emitting Kaizen/velocity as live OTel metrics — deferred (requires
  re-architecting post-run Kaizen into in-process instrumentation). L.
- **Live progress deltas:** owned by ContextCore — not built here (REQ-PRO-004).
- **C-5 (three quality scorers consolidation):** larger separate effort — flagged, not folded in.

---

## Traceability (requirement → phase)

| REQ-PRO | Phase | REQ-PRO | Phase |
|---------|-------|---------|-------|
| 001 | 3.1 | 005 | 1.1 |
| 002 | 1.1 + 2 | 006 | 4.2 |
| 003a | 4.1 | 007 | 4.1 |
| 003b (deferred) | 5 | 008 | 0.1 |
| 004 | 3.1 (document; no emitter) | — | — |

## Before-code checklist

- [ ] Every v0.2 requirement maps to a phase; every step traces to a requirement / Appendix-C item.
- [ ] Phase-1 descriptor-schema change is **shared** with the AI-agent plan (landed once).
- [ ] Parity test (2.3) is shared with AI-agent REQ-AAO-012 — one test mechanism, both categories.
- [ ] `task_tracking_emitter` stays OUT of the OTel collector (it's a state-file channel).
- [ ] No progress-delta emitter is built (REQ-PRO-004 ownership).
- [ ] Phase 0 net-removes lines (dead histogram, namespace cleanup).

---

*Plan v0.1 — paired with requirements v0.2. Category-4 is mostly documentation + declaring existing
spans in the shared descriptor manifest; the schema keystone + parity test are shared with the
AI-agent doc (land once). Metrics + live progress are deferred / ContextCore-owned. Net: small,
mostly declarative + cleanup.*
