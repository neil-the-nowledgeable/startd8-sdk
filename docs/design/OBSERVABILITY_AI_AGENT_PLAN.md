# AI Agent Observability — Implementation Plan

**Date:** 2026-05-31
**Status:** Plan v0.3 (paired with `OBSERVABILITY_AI_AGENT_REQUIREMENTS.md` v0.3; spine R2+R3 propagated into phase tables)
**Scope:** SDK modules — `src/startd8/observability/manifest.py`, `src/startd8/session_tracking.py`,
`src/startd8/costs/otel_metrics.py` + `tracker.py`, `src/startd8/agents/` (label helper, outcome
labels), `src/startd8/events/otel_bridge.py`. The **category-5 artifact generator** that *consumes*
the manifest is taxonomy follow-up (REQ-OAT-041), cross-referenced here, not built in this plan.
**Branch:** `feat/observability-followup-run007` (or a fresh branch).

---

## Implementation status — RECONCILED 2026-05-31 (Phases 0–3 SHIPPED on `main`)

> Phases 0–3 are **implemented and merged to `main`** via `feat/obs-cat5-impl`
> (merge `5babc995`). The two code-verification "stale claims" this plan absorbed
> (`OBSERVABILITY_CAT45_CODE_VERIFICATION.md` §A-1/§A-2) are now both *corrected and
> implemented*: the live tier histogram is declared (cat-4), and the deprecated
> opt-in Prometheus path is retired. Phase→commit map:

| Phase | Status | Commit |
|-------|--------|--------|
| 0.1 cost double-record guard | ✅ done | `bdfad35f` |
| 0.3 retire deprecated opt-in Prometheus path (§A-2) | ✅ done | `bdfad35f` |
| 0.4 `category`/`orientation` on Metric/Span + collector pass-through (R3-F1) | ✅ done | `da3a1105` |
| 0.5 `EventTypeDescriptor.category` → `event_group` (§C polysemy) | ✅ done | `da3a1105` |
| 1.1 populate axes + completeness gate (`GRANDFATHERED_SOURCES` empty) | ✅ done | `a7497351` |
| 1.2 kind-aware descriptor↔emission parity test | ✅ done | `18fbbd9d` |
| 2.1 dotted metric rename (+ exported-name collision fix) | ✅ done | `46eced3b` |
| 3.1 descriptor→`manifest_declared` bridge (`sdk_emitted` route) | ✅ done | `cbe9cca6` |
| B (follow-on): declare ALL 23 live emitters — parity bijection, exclusions empty | ✅ done | `7b78b89c` |
| Phase 4 (signal gaps), Phase 5 (cat-5 artifact definitions) | ⏳ reserved | — |

The category-5 *generator* consumption (`route_state` etc.) shipped as the taxonomy
keystone (step C, `45f0194e`) — see `OBSERVABILITY_ARTIFACT_TAXONOMY_*`. Remaining:
REQ-AAO-050/051 orientation-aware quality scoring (C2) and the `task.*` disambiguation.

---

## Guiding principle

Planning showed the hard infrastructure (per-module `_OTEL_DESCRIPTORS` + `generate_manifest()`)
**already exists** — this is mostly **wiring + cleanup**, not new machinery. Order distillation
first: Phase 0 removes accidental complexity; Phase 1 makes the descriptor manifest the **trustworthy,
routing-aware source of truth** (the keystone); the rest is wiring and small additions. Like the
taxonomy pass, expect a **net-negative** line delta in the cleanup phases.

```
Phase 0  Cleanups / distillation                 C-1, C-2, C-3, C-6; SHARED-001(collector,enum-src), 001a
Phase 1  Keystone: descriptor schema + parity     REQ-AAO-001/004/012; SHARED-001/002/005 (lands once)
Phase 2  Standardize metric names to dotted       REQ-AAO-003 (C-4); SHARED-002(b) exported-name identity
Phase 3  Close the descriptor→metadata loop        REQ-AAO-008; SHARED-004 sdk_emitted route
Phase 4  Fill signal gaps                          REQ-AAO-009 (010/011 reserved)
Phase 5  Category-5 artifact definitions           REQ-AAO-005/006/007 (generation = taxonomy follow-up)
```

---

## Phase 0 — Cleanups / distillation (mostly removals)

| Step | Change | Files | Removes |
|------|--------|-------|---------|
| 0.1 | Document the **distinct semantics** of `startd8.cost.*` (global) vs `startd8_cost_total` (per-session) in both modules' docstrings; add a guard/log warning if the same `correlation_id`'s cost is recorded via both APIs (REQ-AAO-002) | costs/tracker.py, session_tracking.py | C-1 |
| 0.2 | Extract a shared label helper for `{agent_name, model, project_id}` used by both the agent path and session_tracking | agents/, session_tracking.py | C-2 |
| 0.3 | Retire the **deprecated opt-in Prometheus path** — it is *reachable* (gated by `prometheus_port` + `not _otel_enabled`), not dead; removal spans `session_tracking.py:336–337, 438–503` **and** the recording sites `611/810/895` + `_prom_*` attrs (code-verification §A-2). Until retired, the parity test (1.2) **excludes** it via the bijection-exception list (R2-F2) | session_tracking.py | C-3 |
| 0.4 | Add `category` + `orientation` to `MetricDescriptor`/`SpanDescriptor`, typed from **one code-level enum source** imported by both manifest + taxonomy-registry validation (`REQ-OBS-SHARED-001`/R3-F7); **co-land collector pass-through** in `collect_metric_descriptors()`/`collect_span_descriptors()` so the axes (and existing `prometheus_name`/`dashboard_hints`) survive into the manifest — fields are silently dropped otherwise (R3-F1, **critical**) | observability/manifest.py, collector.py | C-6 (also `REQ-OBS-SHARED-001`) |
| 0.5 | Rename `EventTypeDescriptor.category` → `event_group` (the 8-value instrument-grouping axis) so `category` means the taxonomy uniformly; `from_dict` accepts legacy `category` as alias for one release, `to_dict` emits only `event_group` (`REQ-OBS-SHARED-001a`/R2-F4) | observability/manifest.py, collector.py:157, tests/unit/test_observability_manifest.py:82 | category polysemy (§C) |

**Validation:** full suite green; for 0.3, confirm no consumer of the opt-in Prometheus path (grep) and
that an OTLP capture still carries `startd8_*` session metrics after removal (R1-S6); for 0.4, a
`generate_manifest().to_dict()` round-trip fixture proves an annotated descriptor's axes survive
collector collection (R3-F1); for 0.5, old YAML with `event_types[].category` deserializes via the
`event_group` alias; for 0.1, a unit test that double-recording the same correlation_id triggers the
single-WARN guard.

---

## Phase 1 — Keystone: descriptor schema + parity (REQ-AAO-001/004/012; `REQ-OBS-SHARED-001/002/005`)

Makes the manifest authoritative and routing-aware before anything consumes it. This phase is the
**keystone that lands once** (`REQ-OBS-SHARED-005` I1); the cat-4 plan depends on it.

| Step | Change | Files |
|------|--------|-------|
| 1.1 | Populate `category` + `orientation` on **every** `_OTEL_DESCRIPTORS` entry (cost/session = agent obs; task_* = project obs; per the requirements Appendix A orientation map). After landing, a **completeness gate** reports any descriptor with unset axes **by source file** — empty is a compat bridge, not an end state (R3-F5) | all modules declaring descriptors |
| 1.2 | Add the **kind-aware descriptor↔emission parity test** (`REQ-OBS-SHARED-002`) as a parent of named sub-checks: **(b) dual-name identity** — match canonical OTel *and* exported `prometheus_name`, reject exported-name collisions (R3-F2); **(c) repo-wide emitter universe** — scan all `meter.create_*` sites (not just `_INSTRUMENTED_MODULES`) against descriptors-or-an-owned-exclusion-registry (R3-F3); **(d) span name-pattern parity** + `attributes_dynamic` semantics (R3-F4); **metrics bijection** with documented **exceptions** (indirect emitters, observable gauges, opt-in Prom path) (R2-F2); spans **subset** with an optional **required-attr allowlist** for gate/contract attrs (R2-F7) | tests/ + a small introspection helper |
| 1.3 | Add the currently-undocumented signals to descriptors where missing (so the catalog is complete, REQ-AAO-001) | session_tracking.py, agents/tracked.py |
| 1.4 | Ship 1.2 in **bootstrap mode** — an explicit allowlisted known-gap list (seed: `complexity.tier_distribution`, `element_registry` instruments) the helper reports but does not hard-fail; removing an item requires declaring that descriptor in the same PR; list shrinks to empty → hard-fail (`REQ-OBS-SHARED-005` I4 / R2-F9) | tests/ + CI |

**Validation:** parity names each failing sub-check (a)–(e); *passes* with the indirection/
observable-gauge exceptions; *fails* on the tier histogram until declared, on an exported-name
collision, on a `name_pattern` with no runtime site, and on an allowlisted contract attr declared-but-
absent; every descriptor carries category+orientation and they survive `generate_manifest().to_dict()`
(collector pass-through from 0.4); the bootstrap allowlist is documented and shrinks via descriptor
declarations.

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
| 3.1 | Wire `generate_manifest()` output to populate onboarding-metadata `manifest_declared` (each entry carrying name/type/unit/labels/**category**/**orientation**) — the SDK becomes its own "declare, don't guess" producer. Each entry is `route_state=sdk_emitted` by virtue of having a `meter.create_*` site, so the (future) generator routes it as **produced** without inference (`REQ-OBS-SHARED-004`/R3-F6) | observability/manifest.py + a small bridge |

**Validation:** a generated onboarding metadata's `manifest_declared` for the SDK's own metrics is
produced from the manifest (not hand-authored, proven by mutating a descriptor → the entry changes,
R1-S5), carries category+orientation, and matches the descriptor catalog. **Cross-doc:** this satisfies
taxonomy REQ-OAT-024 for SDK-emitted metrics without the REQ-OAT-025 exporter change (`REQ-OBS-SHARED-004`
`sdk_emitted` route); the generator's other three `route_state`s (`contextcore_owned`,
`declared_unimplemented`, `external_convention`) are generator-side (REQ-OAT-041), cross-referenced.

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
| 006 | 5.1 | 012 (parity) | 1.2, 1.4 |

**Shared-spine traceability:** `REQ-OBS-SHARED-001` (schema + collector pass-through + enum source) →
Phase 0.4; `-001a` (event_group rename) → Phase 0.5; `-002` (kind-aware parity sub-checks) → Phase
1.2; `-002(b)` (exported-name identity) → Phase 2; `-004` (`sdk_emitted` route) → Phase 3.1; `-005`
I1/I2 (one-diff keystone + collector co-land) → Phase 0.4–1, I4 (bootstrap allowlist) → Phase 1.4.

## CRP R1 plan amendments (cat-4/5 combined review)

These amend the phases above; applied from CRP R1 (see Appendix A). The shared spine is now owned by
`OBSERVABILITY_DESCRIPTOR_SPINE_REQUIREMENTS.md`.

- **Phase 1 is the keystone landing (R1-S1, `REQ-OBS-SHARED-005`).** This plan lands the
  `category`/`orientation` schema fields **and** the parity helper **once**; the cat-4 (project) plan
  declares an explicit dependency edge on this landing and does **not** re-add them. Exactly one diff
  in history adds the fields.
- **Phase 1.2 parity is kind-aware (R1-S2, `REQ-OBS-SHARED-002`).** Metrics → **bijection**; spans →
  **subset**. Replaces the ambiguous "and vice-versa" (which read as universal bijection and drifted
  against the project plan's "subset"). One helper, one documented relation, referenced by both plans.
- **Phase 1.1 registry layering (R1-S3, `REQ-OBS-SHARED-003`).** Descriptor `category`/`orientation`
  are authoritative for the **telemetry-declaration** layer — a *separate* layer from the taxonomy
  artifact-dispatch registry (REQ-OAT-070a). They share the enum vocabulary, not rows; the
  reconciliation check is vocabulary-level (no stray enum value), not row-level. Hand-populating axes
  here is therefore not the parallel-table the taxonomy forbids.
- **Phase 2 rename — captured baseline + rollback (R1-S4).** Before renaming, capture the current
  Prometheus-exported names to a golden file; assert the post-rename export equals it byte-for-byte;
  rollback = revert the rename commit. "Reproduces automatically" is not sufficient validation.
- **Phase 3 — prove generated-from-manifest (R1-S5).** Validation MUST mutate one descriptor and
  assert the corresponding `manifest_declared` entry changes (a hand-authored copy would not) — proving
  the declare-don't-guess wiring, not just catalog-match.
- **Phase 0.3 — positive OTLP proof, correctly scoped (R1-S6 + code-verification §A-2).** The
  Prometheus path is **reachable opt-in** (gated by `prometheus_port` + `not _otel_enabled`), not
  dead; retiring it spans `session_tracking.py:336, 438–503` **and** the recording sites at 611/810/895
  + `_prom_*` attrs. Gate removal on a behavioral check that an OTLP capture still carries the
  `startd8_*` session metrics after removal — a grep alone can miss late-bound usage.

## Before-code checklist — SATISFIED (Phases 0–3 shipped, see status block above)

- [x] Every v0.2 requirement maps to a phase; every step traces to a requirement / Appendix-C item.
- [x] Phase 0 net-removes lines (Prometheus opt-in path, deduped labels).
- [x] Parity test (1.2) is kind-aware and fails on a deliberately mis-declared metric (bijection) and a
  non-subset span attr before it's trusted (3.1). *(See `tests/unit/observability/test_parity.py`.)*
- [x] Phase 2 rename verified byte-for-byte against a captured golden baseline (R1-S4).
- [x] Phase 1 keystone (schema + parity) lands once; cat-4 plan depends on it, doesn't re-add (R1-S1).
- [x] Cross-doc: the Phase-3 loop's effect on taxonomy REQ-OAT-024/025 is reconciled (`REQ-OBS-SHARED-004`)
  — step C consumes `route_state` declared-first with `inferred` fallback recorded.

---

*Plan v0.1 — paired with requirements v0.2. Six phases; Phases 0–1 distill + establish the
trustworthy descriptor manifest, Phases 2–4 are wiring/small additions, Phase 5 defines artifacts
that the taxonomy category-5 generator (deferred) consumes. Net: mostly wiring + cleanup.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Name the shared keystone as a single landing; cat-4 depends on it | claude-opus-4-8-1m | CRP R1 amendment + `REQ-OBS-SHARED-005` | 2026-05-31 |
| R1-S2 | Fix parity relation (bijection vs subset) | claude-opus-4-8-1m | Kind-aware via `REQ-OBS-SHARED-002` | 2026-05-31 |
| R1-S3 | Descriptor axes authoritative vs projection | claude-opus-4-8-1m | `REQ-OBS-SHARED-003` separate-layer resolution | 2026-05-31 |
| R1-S4 | Phase 2 byte-for-byte baseline + rollback | claude-opus-4-8-1m | Golden file of pre-rename exported names | 2026-05-31 |
| R1-S5 | Phase 3 fixture proves generated-from-manifest | claude-opus-4-8-1m | Mutate-descriptor test | 2026-05-31 |
| R1-S6 | Phase 0.3 positive OTLP proof, not grep-only | claude-opus-4-8-1m | + code-verification §A-2: scope is opt-in path (336/438-503/611/810/895), not "dead" | 2026-05-31 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-05-31

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-31 18:46:04 UTC
- **Scope**: Plan quality (S-prefix) for AI Agent Observability (cat 5), weighted toward the shared descriptor-registry spine sequencing vs the project-obs plan (cat 4) and taxonomy code-alignment.

##### Executive summary

- The shared "schema keystone" (Phase 0.4 + 1.1) and parity test (Phase 1.2) are the cross-doc spine but are NOT sequenced as a single landing step — both this plan and the PRO plan list them independently against the same branch, risking a double-add.
- Phase 1.2 parity-test relation is ambiguous ("and vice-versa" = bijection) while the PRO plan Phase 2.3 states "subset"; the shared test cannot satisfy both relations.
- Phase 1.1 populates `category`/`orientation` per descriptor, which the settled taxonomy REQ-OAT-070a treats as derived projections — the plan should state whether the descriptor store is authoritative or projected.
- Phase 3's manifest→`manifest_declared` wiring is the keystone value (declare-don't-guess) but lacks a fixture-based validation that the metadata is produced from the manifest, not hand-authored.
- Phase 0.3 (remove dead Prometheus fallback) has a grep-only gate; for a deletion crossing an export boundary, add a positive proof that OTLP export still carries the affected metrics.
- Phase 2 rename relies on the Prometheus dots→underscores transform; the validation should assert byte-for-byte parity against a captured baseline, not just "reproduces … automatically".
- No ops/rollback note for the Phase 2 metric rename (a name change is observable-breaking if the transform assumption is wrong).
- Security area is untouched (acceptable — observation-only, no new surface), noted for domain exhaustiveness.

##### Numbered suggestions (S-prefix → plan)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Name the shared schema keystone as a single landing step (one PR/commit) and have the cat-4 (PRO) plan declare an explicit dependency edge on it; reference the PRO plan's Phase 1.1 by name so the two plans cannot both add the `category`/`orientation` fields. | Phase 0.4 and Phase 1.1 both add the fields, and the PRO plan Phase 1.1 also adds them "land it once" — but neither plan names the landing PR or blocks the other; same branch reduces but does not remove the double-add hazard (focus Ask 4). | "Guiding principle" / Phase 1 header | Cross-plan: exactly one diff adds the descriptor fields; the other plan's traceability shows a dependency, not a duplicate step. |
| R1-S2 | Validation | high | Fix the parity-test relation: Phase 1.2 says "every declared descriptor maps to an emission and vice-versa" (bijection) but the PRO plan Phase 2.3 says "declared attrs ⊆ emitted attrs" (subset). Pick one relation for the SHARED test and state it identically in both plans. | The parity test is the shared anti-drift mechanism; if the two plans specify different relations, the single test cannot be shared (focus Ask 1/4). Spans (open attribute sets) may justify subset while metrics justify bijection — decide and document. | Phase 1.2 + cross-ref PRO 2.3 | Test: the shared parity helper documents one relation; running it against the cat-5 manifest and cat-4 spans both pass under that one relation. |
| R1-S3 | Data | high | In Phase 1.1, state whether descriptor `category`/`orientation` are authoritative or are projections of the taxonomy REQ-OAT-070a `declared_type`-keyed registry (which forbids independently-maintained category/orientation), and add a reconciliation check if separate. | Hand-populating the axes per descriptor (Phase 1.1) reintroduces the parallel-table accidental complexity the taxonomy R2-F4 removed; the plan must pick a source of truth (focus Ask 3). | Phase 1 step 1.1 | Test: descriptor axes equal the registry projection for overlapping signals, or the plan documents the descriptor manifest as a separate layer with a reconciliation assertion. |
| R1-S4 | Ops | medium | Add a rollback/compat note and a byte-for-byte baseline assertion to Phase 2: capture the current Prometheus-exported metric names BEFORE the rename and diff the post-rename export against that captured baseline (not just "reproduces … automatically"). | A metric rename is observable-breaking if the dots→underscores transform assumption is even slightly wrong (e.g. an existing name that doesn't round-trip); the checklist item "preserve the exported names" needs a concrete captured baseline. | Phase 2 validation + before-code checklist | CI: golden file of pre-rename exported names; post-rename export equals it byte-for-byte; rollback = revert the rename commit. |
| R1-S5 | Validation | medium | Phase 3 validation should use a fixture asserting `manifest_declared` is **generated from** `generate_manifest()` (e.g. a tampered manifest entry shows up in the metadata), proving the metadata is not hand-authored. | Phase 3 is the keystone "declare-don't-guess" payoff; "produced from the manifest (not hand-authored)" is the value claim but the validation only says it "matches the descriptor catalog" — which a hand-authored copy would also satisfy. | Phase 3 validation | Test: mutate one descriptor → the corresponding `manifest_declared` entry changes; a hand-authored copy would not. |
| R1-S6 | Risks | medium | Phase 0.3 (remove dead Prometheus fallback) should add a positive proof, not just a grep: assert that after removal the OTLP export still carries the session/cost metrics, since the deletion crosses the export boundary. | A grep for consumers can miss reflection/late-bound usage; a deletion at an export boundary deserves a behavioral check that telemetry still flows. | Phase 0.3 validation | Integration: with the fallback removed, an OTLP capture still contains `startd8_*` session metrics. |

##### Cross-doc note (cats 4 & 5 sequencing)

The cat-4 (PRO) plan and this plan share three concrete artifacts: (1) the `MetricDescriptor`/`SpanDescriptor` `category`+`orientation` fields, (2) the descriptor↔emission parity test, and (3) the same target branch `feat/observability-followup-run007`. Recommend the orchestrator land the schema fields + parity test in cat-5 Phase 1 FIRST (this plan owns the descriptor manifest most directly), then have the cat-4 plan rebase and only ADD project-span descriptors + the ownership-boundary docs. This matches focus Ask 4's "land once, shared" intent and avoids the ordering hazard with the taxonomy code-alignment (REQ-OAT-070a registry) noted in R1-S3.

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — Round R1 (first encounter); no prior untriaged suggestions exist.

---

## Requirements Coverage Matrix — R1

Mapping each AI-agent requirement → plan phase/step → Covered / Partial / Gap (analysis only; not triage).

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| REQ-AAO-001 (catalog) | 1.1, 1.3 | Covered | — |
| REQ-AAO-002 (two cost families: doc + guard) | 0.1 | Partial | Guard detection-key + action (warn/drop/raise) not specified (see R1-F5). |
| REQ-AAO-003 (standardize on dotted names) | 2.1 | Partial | No captured byte-for-byte export baseline / rollback note (see R1-S4). |
| REQ-AAO-004 (orientation/schema fields) | 0.4, 1.1 | Partial | Field/enum/default contract not specified inline; shared-keystone landing not sequenced (R1-F1, R1-S1); registry-projection question open (R1-S3). |
| REQ-AAO-005 (agent dashboard — human) | 5.3 | Covered | Generation deferred to taxonomy generator (acknowledged). |
| REQ-AAO-006 (SLI/SLO — system) | 5.1 | Covered | Definitions only; generation deferred. |
| REQ-AAO-007 (alerts — bridge) | 5.2 | Covered | Definitions only; generation deferred. |
| REQ-AAO-008 (close descriptor→metadata loop) | 3.1 | Partial | Validation doesn't prove metadata is generated-from-manifest vs hand-authored (R1-S5); emit-vs-cede contrast not stated (R1-F2/F8). |
| REQ-AAO-009 (outcome labels truncated/retried) | 4.1 | Covered | — |
| REQ-AAO-010 (eval hook) | 4.2 (reserved) | Partial | "May be reserved" — in/out not committed (R1-F4). |
| REQ-AAO-011 (tool-use telemetry) | 4.3 (reserved) | Partial | "May be reserved" — in/out not committed (R1-F4). |
| REQ-AAO-012 (descriptor↔emission parity) | 1.2 | Partial | Parity relation (bijection vs PRO's subset) inconsistent across docs (R1-S2/R1-F6); registry alignment (R1-F3/F9). |
