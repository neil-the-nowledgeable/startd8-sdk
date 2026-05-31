# Project Observability — Implementation Plan

**Date:** 2026-05-31
**Status:** Plan v0.3 (paired with `OBSERVABILITY_PROJECT_REQUIREMENTS.md` v0.3; spine R2+R3 propagated into phase tables)
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
Phase 0  Cleanups / distillation                  C-1(codegen.task.* — before P2), C-2(declare histogram), C-4
Phase 1  Depend on cat-5 keystone (NOT re-add)     REQ-PRO-002/005; SHARED-005 I1 (dependency edge)
Phase 2  Declare the project spans                  REQ-PRO-002, 008; SHARED-002 (subset + name-pattern)
Phase 3  Document the ownership boundary            REQ-PRO-001, 004; SHARED-004 contextcore_owned route
Phase 4  Declare delivery signals + SLIs (authored)  REQ-PRO-003a, 006, 007 (+ CI sample-validation, R1-S5)
Phase 5  (deferred) metric-ify; live progress        REQ-PRO-003b (L); progress = ContextCore
```

---

## Phase 0 — Cleanups / distillation

| Step | Change | Files | Removes |
|------|--------|-------|---------|
| 0.1 | Disambiguate the two "task" concepts — **committed scheme** (REQ-PRO-008/R1-F2): work-item keeps `task.*` (ContextCore/SpanState-v2 canonical), codegen chunk attrs rename to **`codegen.task.*`**. **MUST land before Phase 2.1** declares descriptors (reverse-dep `REQ-OBS-SHARED-005` I3 / R2-F6 — otherwise parity encodes the `task.status` polysemy as a passing subset) | otel_conventions.py, development.py, runner.py | C-1 (REQ-PRO-008) |
| 0.2 | **Declare** (not delete) the **live** `complexity.tier_distribution` histogram — it is recorded at `classifier.py:277` (CAT45 §A-1 corrects the "dead" claim); add it to `_OTEL_DESCRIPTORS` with `category=pipeline_innate`/`orientation=system`. This is the first catch of the parity test, not a removal | complexity/classifier.py | C-2 (now *declare*, not remove) |
| 0.3 | Reconcile/document the phase-span naming (`artisan.workflow.{id}.phase.{phase}` vs `phase.{type}.attempt.{n}`) — feeds the SHARED-002(d) span **name-pattern** parity check (R3-F4) | artisan_contractor.py, runner.py | C-4 |

**Validation:** suite green; renamed codegen attrs emitted under `codegen.task.*` with no consumer of
the old names (grep); the tier histogram appears in `generate_manifest()` output (declared); Phase 0.1
lands before Phase 2.1.

---

## Phase 1 — Depend on the cat-5 keystone (NOT a second add) (REQ-PRO-002/005; `REQ-OBS-SHARED-005`)

| Step | Change | Files |
|------|--------|-------|
| 1.1 | **Dependency edge, not a change** (`REQ-OBS-SHARED-005` I1 / R1-S1): the `category`/`orientation` schema fields, collector pass-through, and parity helper are landed **once** by the cat-5 plan Phase 0.4/1. This plan **rebases on that landing** and adds only its *additive* work (Phase 2–3). It does **not** re-add the fields | — (consumes cat-5 keystone) |

**Cross-doc:** cat-5 owns the descriptor manifest most directly and lands the keystone (incl. collector
pass-through, R3-F1); cat-4 must not duplicate the diff (I1).
**Validation:** the cat-4 history shows a dependency, not a duplicate schema add (one diff total across
both plans adds the fields + helper).

---

## Phase 2 — Declare the project spans (REQ-PRO-002, 008)

| Step | Change | Files |
|------|--------|-------|
| 2.1 | Declare the already-emitted `phase.*` and `codegen.task.*` span attributes in `_OTEL_DESCRIPTORS` with `category=project_observability`, `orientation=system` | runner.py, artisan_contractor.py, development.py |
| 2.2 | Add those modules to `collector.py._INSTRUMENTED_MODULES`. **Do NOT** add `task_tracking_emitter` (it emits no OTel — state-file channel only) | collector.py |
| 2.3 | Enroll project spans in the **shared kind-aware parity helper** (`REQ-OBS-SHARED-002`, landed by cat-5) — for spans this is the **subset** relation (declared attrs ⊆ emitted) **plus** the **name-pattern** check (every `SpanDescriptor.name_pattern` matches a runtime span site or is `attributes_dynamic`, R3-F4). Reuses the helper; does not define a new relation. Requires Phase 0.1 (`codegen.task.*`) already landed | tests/ (fixtures only) |

**Validation:** the shared parity helper passes on project spans under the subset + name-pattern checks
(and fails on a mis-declared attr or a `name_pattern` with no runtime site); project spans appear in
`generate_manifest()` output with category/orientation; fixtures use the renamed `codegen.task.*` attrs.

---

## Phase 3 — Document the ownership boundary (REQ-PRO-001, 004)

| Step | Change | Files |
|------|--------|-------|
| 3.1 | Add docstrings/comments stating the boundary: startd8 writes state files + spans + Kaizen JSON; **ContextCore owns** the gauges, **live progress computation**, and burndown dashboards | task_tracking_emitter.py, integrations/contextcore.py |
| 3.2 | Specify that the generator routes declared `contextcore_*` gauges as **`route_state=contextcore_owned`** (`REQ-OBS-SHARED-004`/R2-F3/R3-F6): skip record carries `skip_reason=owned_elsewhere`, `owner=contextcore`, **no** `source_checksum`, and is **excluded from the `artifact_type_coverage` denominator** (REQ-OAT-052) — a cede is not `coverage<1.0`. Includes stale-metadata handling: classify run-007's still-declared `contextcore_task_*` as `contextcore_owned` on read (R1-F5) | (cross-ref taxonomy generator) |

**Validation:** docs/comments present; no code reaches into ContextCore beyond the optional wrapper;
no progress-delta emitter is added (REQ-PRO-004); a generator fed the cede yields
`route_state=contextcore_owned`, `owner=contextcore`, `artifact_type_coverage=1.0`; run-007 metadata
classifies `contextcore_*` as owned, not mis-attributed.

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
| 001 | 3.1, 3.2 | 005 | 1.1 (via cat-5 keystone) |
| 002 | 1.1 (dep) + 2 | 006 | 4.2 |
| 003a | 4.1 | 007 | 4.1 |
| 003b (deferred) | 5 | 008 | 0.1 (`codegen.task.*`, before P2) |
| 004 | 3.1 (document; no emitter) | — | — |

**Shared-spine traceability:** `REQ-OBS-SHARED-001` → cat-5 Phase 0.4 (consumed here Phase 1.1);
`-002` → Phase 2.3 (subset + name-pattern); `-003` → Phase 2 (layer separation); `-004` → Phase 3.2
(`contextcore_owned` route); `-005` I1 → Phase 1.1 (dependency), I3 → Phase 0.1 (rename before P2).

## CRP R1 plan amendments (cat-4/5 combined review)

These amend the phases above; applied from CRP R1 (see Appendix A). The shared spine is owned by
`OBSERVABILITY_DESCRIPTOR_SPINE_REQUIREMENTS.md`.

- **Phase 1.1 becomes a dependency edge, not a duplicate add (R1-S1/S6, `REQ-OBS-SHARED-005`).** The
  cat-5 plan Phase 1 lands the `category`/`orientation` schema fields + parity helper; **this plan
  depends on that landing and rebases** — it performs only Phase 2 (declare project spans) and Phase 3
  (ownership-boundary docs + cede). Phase 1.1 no longer re-adds the fields.
- **Phase 2.3 parity is kind-aware (R1-S2, `REQ-OBS-SHARED-002`).** Project **spans** use the
  **subset** relation (declared ⊆ emitted); cat-5 **metrics** use bijection. One shared helper,
  parameterized by signal kind — "shared with AAO-012" is now literally true.
- **Phase 0.1 commits to ONE task namespace (R1-S3, REQ-PRO-008/R1-F2).** Work-item keeps `task.*`
  (ContextCore/SpanState-v2 canonical); codegen chunk attrs rename to **`codegen.task.*`**. This lands
  **before** Phase 2.1 declares descriptors (the descriptor names depend on it).
- **Phase 0.2 CORRECTION — the tier histogram is LIVE, not dead (code-verification §A-1).** The plan's
  "remove the dead tier histogram" is **wrong**: `complexity/classifier.py:24` creates
  `complexity.tier_distribution` and it **is recorded** at `classifier.py:277`. The real defect is that
  it is **emitted-but-undeclared** (classifier.py is not in `_OTEL_DESCRIPTORS`). Flip Phase 0.2 from
  *delete* to **declare** the histogram in the manifest (category `pipeline_innate`/`project`,
  orientation `system`) — this is the first catch of the Phase-2.3 parity test, not a Phase-0 removal.
  (Adjust the "net-removes lines" claim accordingly.)
- **Phase 3.2 validates the cede fields (R1-S4, `REQ-OBS-SHARED-004`).** Assert the generator emits
  `skip_reason=owned_elsewhere`, `owner=contextcore`, no `source_checksum`, and excludes the skip from
  `artifact_type_coverage` (taxonomy REQ-OAT-052) — not merely "confirm honest-skip".
- **Phase 4.1 validates the hand-authored schema (R1-S5).** CI-validate the authored Kaizen/velocity
  JSON-schema section against a checked-in real `kaizen-metrics.json` sample, since it is not
  auto-discovered and the parity test cannot cover it.

## Before-code checklist

- [ ] Every v0.2 requirement maps to a phase; every step traces to a requirement / Appendix-C item.
- [ ] Phase-1 schema change is a **dependency** on the cat-5 keystone, not a duplicate add (R1-S1).
- [ ] Parity test (2.3) is the kind-aware shared helper (spans ⊆ emitted) (R1-S2).
- [ ] `task_tracking_emitter` stays OUT of the OTel collector (it's a state-file channel).
- [ ] No progress-delta emitter is built (REQ-PRO-004 ownership).
- [ ] Phase 0.1 lands the `codegen.task.*` rename before Phase 2.1 declares descriptors.
- [ ] Phase 0.2 **declares** the live `complexity.tier_distribution` histogram (does NOT delete it).

---

*Plan v0.1 — paired with requirements v0.2. Category-4 is mostly documentation + declaring existing
spans in the shared descriptor manifest; the schema keystone + parity test are shared with the
AI-agent doc (land once). Metrics + live progress are deferred / ContextCore-owned. Net: small,
mostly declarative + cleanup.*

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
| R1-S1 | Reframe Phase 1.1 as dependency on cat-5 keystone | claude-opus-4-8-1m | CRP R1 amendment + `REQ-OBS-SHARED-005` | 2026-05-31 |
| R1-S2 | Kind-aware parity (spans subset) | claude-opus-4-8-1m | `REQ-OBS-SHARED-002` | 2026-05-31 |
| R1-S3 | Phase 0.1 pick ONE task namespace before declaring | claude-opus-4-8-1m | Committed `codegen.task.*`; lands before Phase 2.1 | 2026-05-31 |
| R1-S4 | Phase 3.2 validate cede record fields | claude-opus-4-8-1m | `skip_reason`/`owner`/denominator-exclusion (REQ-OAT-052) | 2026-05-31 |
| R1-S5 | Phase 4.1 validate hand-authored schema vs real sample | claude-opus-4-8-1m | CI check against checked-in `kaizen-metrics.json` | 2026-05-31 |
| R1-S6 | Descriptor axes projection vs separate layer | claude-opus-4-8-1m | `REQ-OBS-SHARED-003` separate-layer resolution | 2026-05-31 |
| §A-1 | Code-verification: tier histogram is live, not dead | code-verification note | Phase 0.2 flipped delete→**declare** (`complexity.tier_distribution` recorded at classifier.py:277) | 2026-05-31 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-05-31

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-31 18:46:04 UTC
- **Scope**: Plan quality (S-prefix) for Project Observability (cat 4), weighted toward the shared descriptor-registry spine sequencing vs the AI-agent plan (cat 5) and the taxonomy cede/registry model (REQ-OAT-070a / 011 / 052).

##### Executive summary

- The shared schema keystone (Phase 1.1) and parity test (Phase 2.3) are correctly flagged as shared with cat-5, but written as steps this plan performs rather than as a dependency on the cat-5 landing — double-add hazard remains.
- The parity test relation here ("declared ⊆ emitted", Phase 2.3) differs from the cat-5 plan's bijection wording — the shared test cannot be literally identical without reconciling this.
- Phase 0.1 leaves the "task" disambiguation as an either/or; the plan should commit to one namespace before declaring descriptors (Phase 2.1 depends on the chosen names).
- Phase 3.2 ("confirm the generator reports `contextcore_*` as honest-skip") is a cross-ref but has no validation that the skip carries `skip_reason=owned_elsewhere`/`owner` per the settled taxonomy REQ-OAT-052.
- Phase 4.1 authors a hand-maintained JSON-schema section with no sync check against real Kaizen JSON — silent rot risk.
- Phase 0.2 (remove dead histogram) and Phase 0.1 (rename) net-remove lines as claimed; good distillation ordering.
- Security area untouched (acceptable — observation-only); noted for domain exhaustiveness.

##### Numbered suggestions (S-prefix → plan)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Reframe Phase 1.1 as an explicit dependency on the cat-5 keystone landing (cat-5 Phase 1 adds `category`/`orientation` + parity test; cat-4 rebases and only ADDS project-span descriptors), rather than as a step this plan also performs. | Phase 1.1 says "= AAO-004; ONE change … land it once" but is still listed as a cat-4 step; same branch reduces but does not remove the double-add hazard (focus Ask 4). A dependency edge makes the ordering enforceable. | Phase 1 header + "Cross-doc" note | Cross-plan: exactly one diff adds the schema fields; cat-4 traceability shows a dependency, not a duplicate add. |
| R1-S2 | Validation | high | Reconcile the parity-test relation: Phase 2.3 says "declared attrs ⊆ emitted attrs" (subset) but the cat-5 plan Phase 1.2 says bijection. Make the shared test **kind-aware** (⊆ for spans, chosen relation for metrics) and document the same relation in both plans. | The parity test is the shared anti-drift mechanism; "shared with AI-agent REQ-AAO-012" is false if the two plans assert different relations (focus Ask 1/4). Spans need subset (open attr sets); metrics may need bijection. | Phase 2.3 + cross-ref AAO 1.2 | Test: one parity helper enforces ⊆ for span descriptors; both plans state the relation identically. |
| R1-S3 | Interfaces | high | Phase 0.1 MUST pick ONE "task" disambiguation (commit to `workitem.*` vs `codegen.task.*`) before Phase 2.1 declares descriptors, rather than the current "(or keep `task.*` … and namespace the chunk attrs)". | Phase 2.1's descriptor names and Phase 4.1's SLI examples depend on the chosen namespace; an undecided either/or blocks deterministic descriptor declaration (focus Ask 3; REQ-PRO-008 / R1-F2). | Phase 0.1 step | Grep: post-rename, exactly one namespace is used; no consumer of the old codegen `task.*` names remains. |
| R1-S4 | Ops | medium | Phase 3.2 MUST validate the cede record fields, not just "confirm … honest-skip": assert the generator emits `skip_reason=owned_elsewhere`, `owner=contextcore`, no `source_checksum`, and excludes the skip from artifact_type_coverage (taxonomy REQ-OAT-052 / R2-F3 / R4-F2). | Phase 3.2 is a cross-reference with no concrete check; the settled taxonomy already specifies the exact skip fields and denominator-exclusion — the plan should test against them so the cede isn't a looks-like-failure (focus Ask 2). | Phase 3.2 validation | Test: declaring ContextCore-owned `contextcore_task_progress` yields a skip with the named fields and artifact_type_coverage=1.0. |
| R1-S5 | Data | medium | Phase 4.1's hand-authored JSON-schema section MUST be validated against a real `kaizen-metrics.json` / velocity-ledger sample in CI, since it is not auto-discovered and the parity test does not cover it. | The plan acknowledges these sections are hand-maintained (not collector-discovered); without a sample-validation check the authored schema silently rots when the Kaizen JSON shape changes (focus Ask 5; REQ-PRO-003a/007 / R1-F4). | Phase 4.1 validation | CI: the authored Kaizen/velocity schema validates a checked-in real sample; shape drift fails the build. |
| R1-S6 | Architecture | medium | Phase 1.1 / the shared keystone MUST state whether descriptor `category`/`orientation` are projections of the taxonomy REQ-OAT-070a registry or a separate layer, and add a reconciliation check — otherwise Phase 2.1 hand-sets axes that the taxonomy says must be derived projections. | REQ-OAT-070a forbids independently-maintained category/orientation; Phase 2.1 ("declare … with category=project_observability, orientation=system") hand-sets them per descriptor — the parallel-table accidental complexity taxonomy R2-F4 removed (focus Ask 3; R1-F9 cross-doc). | Phase 1.1 / Phase 2.1 | Test: descriptor axes equal the registry projection for overlapping signals, or the plan documents the manifest as a separate layer with a reconciliation assertion. |

##### Cross-doc note (cats 4 & 5 sequencing)

This plan and the cat-5 plan share: (1) the `MetricDescriptor`/`SpanDescriptor` `category`+`orientation` fields, (2) the descriptor↔emission parity test, (3) the same branch `feat/observability-followup-run007`. Recommended order: cat-5 Phase 1 lands the schema fields + parity test FIRST (it owns the descriptor manifest most directly and emits metrics in-process); then this cat-4 plan rebases and performs only Phase 2 (declare project spans) + Phase 3 (ownership-boundary docs + cede). This realizes the "land once, shared" intent (Ask 4) and removes the bijection-vs-subset reconciliation (R1-S2) and registry-projection (R1-S6) hazards from being decided twice.

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — Round R1 (first encounter); no prior untriaged suggestions exist.

---

## Requirements Coverage Matrix — R1

Mapping each project-obs requirement → plan phase/step → Covered / Partial / Gap (analysis only; not triage).

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| REQ-PRO-001 (ownership boundary — docs) | 3.1, 3.2 | Partial | Cede field-level contract (`skip_reason`/`owner`, denominator-exclusion) + handling of stale run-007 metadata not specified (R1-S4, R1-F1/F5). |
| REQ-PRO-002 (declare project spans; shared schema) | 1.1, 2.1, 2.2, 2.3 | Partial | Shared-keystone landing not a dependency edge (R1-S1); parity relation diverges from cat-5 (R1-S2); registry-projection question open (R1-S6/R1-F9). |
| REQ-PRO-003a (declare delivery signals — authored) | 4.1 | Partial | Hand-authored JSON-schema section has no sync/validation against real Kaizen JSON (R1-S5/R1-F4). |
| REQ-PRO-003b (metric-ify) | 5 (deferred) | Covered | Cleanly deferred (L). |
| REQ-PRO-004 (progress = ContextCore; no emitter) | 3.1 | Covered | Explicit "no delta emitter"; well-bounded. |
| REQ-PRO-005 (orientation) | 1.1 | Covered | Rides the shared schema field; same registry-projection caveat as 002. |
| REQ-PRO-006 (generate-vs-cede) | 4.2 | Partial | "MAY generate delivery-health alerts" implies an emit path deferred by 003b — mark definition-only this pass (R1-F6). |
| REQ-PRO-007 (project SLIs/SLOs — authored) | 4.1 | Partial | Hand-authored; same sync gap as 003a (R1-S5/R1-F4). |
| REQ-PRO-008 (disambiguate two "task" concepts) | 0.1 | Partial | Plan leaves an either/or; must commit to one namespace before descriptor declaration (R1-S3/R1-F2). |
