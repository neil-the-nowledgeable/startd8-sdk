# Observability Artifact Taxonomy — Implementation Plan

**Date:** 2026-05-31
**Status:** Plan v0.3 — post-CRP R1–R4 (4 rounds, 3 models; all S-suggestions applied; paired with requirements v0.5)
**Scope:** SDK modules — `src/startd8/observability/artifact_generator.py`,
`src/startd8/validators/observability_artifact_checks.py`,
`scripts/generate_observability_artifacts.py`. The auto-satisfy *consumer* (REQ-OAT-031b) is
plan-ingestion (cap-dev-pipe) and is **out of scope** here.
**Branch:** `feat/observability-followup-run007` (or a fresh `feat/observability-taxonomy`).

---

## Guiding principle — complexity-first ordering

The plan is ordered so the **distillation lands before the features**. Phase 0 removes free-standing
cruft; Phase 1 makes the two axes first-class (the keystone), which *collapses* three smells for
free; Phase 2 unifies the dispatch and scoring duplication. Only then (Phases 3–5) do the
category/orientation features land — cheaply, because the structure now supports them. Per
REQ-OAT-070, every phase extends a **table**, not control flow. The pass should **net-remove** lines.

```
Phase 0  Enabling cleanups (no behavior change)         D-6, D-8, D-9, D-10
Phase 1  Keystone: two axes first-class                 REQ-OAT-023; collapses D-2, D-4
Phase 2  Unify dispatch + scoring                       REQ-OAT-042, 050-dispatcher; D-1, D-5
Phase 3  Naming / ownership                             REQ-OAT-010/011/012/013, 021; D-2-final, D-10
Phase 4  Orientation-aware validation + 3-way coverage  REQ-OAT-050/051/060/061/062; D-3
Phase 5  Metadata declare-don't-guess + routing + report REQ-OAT-020/022/024/040/041/030/031a; D-7, D-11
Phase 6  (deferred, cross-repo) auto-satisfy consumer    REQ-OAT-031b  [plan-ingestion]
```

## CRP R2–R4 plan amendments (code-grounded)

The R2–R4 rounds read the implementation and amended these phases (full dispositions in Appendix A;
requirements in OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md v0.5):

- **Phase 1 (keystone) — table is a repurpose, not a sibling (R2-S1/S2).** `_ARTIFACT_TYPE_TO_CATEGORY`
  (`:1584`) holds `observe/integration/action/reference`, a *different* axis read only by
  `generate_capability_index:1631`. Phase 1 MUST introduce a distinctly-named five-category map (or
  rename+value-migrate) and **land the Phase-3.2 capability_index revert before/with it** so no run
  leaks five-category strings into the capability schema. Phase-1 validation MUST also assert
  category-3 artifacts are **excluded from the per-service `services` dict immediately** (R4-S5) and
  extend the Phase-0.5 golden baseline to cover the table repurpose (R2-S4).
- **Phase 2 — one registry (R2-S5), `requires_declaration` (R3-S1), ordering (R3-S2).** Replace the
  two-table design (Phase 2.1 dispatch `(category,type)` + Phase 2.2 scoring `(category,orientation)`)
  with **one** `declared_type → {runtime_type, category, orientation, generator, validator_set,
  output_path, scope, requires_declaration}` registry (REQ-OAT-070a). The orchestrator MUST honour
  `requires_declaration` (triplet unconditional; extended only-if-declared) and an ordered iteration
  (spec before its JSON conversion).
- **Phase 0.4 — delete the CLI loop (R4-S4) + list return (R3-S3).** Moving persona fan-out inside the
  generator changes its return to `List[ArtifactResult]` → orchestrator (`:1980`) MUST `extend` not
  `append`; and the legacy CLI `--portal-persona=all` reload loop (`scripts:139–171`) MUST be
  **deleted**, not just bypassed (else D-10 persists).
- **Phase 3.3 — skip_reason/owner (R2-S6).** The skip record carries `skip_reason`
  (`owned_elsewhere`|`unimplemented`) + `owner`, no `source_checksum`.
- **Phase 4.3 — aggregate rollup + orientation-keyed inputs (R2-S3, R4-S3).** Replace the count-pooled
  mean (`_write_quality_report:2433`) with a mean of per-metric composites (missing axes = 0); collect
  coverage inputs **by orientation from the registry**, covering `alert_rule`↔`prometheus_rule` /
  `dashboard_spec`↔`dashboard` aliases (not type-string compares).
- **Phase 4.5 (new) — cross-artifact migration (R4-S2).** Migrate `validate_cross_artifact_consistency`
  + kaizen `cross_artifact_issues` to registry `declared_type`+`orientation`, or mark
  out-of-scope-legacy — else portal/alias renames silently kill detection while scores stay green.
- **Phase 5.6 (new) — index consolidation (R4-S1).** Name **one** canonical retrospective index
  (`generation_report`); demote `observability-manifest.yaml` to a thin summary + pointer, or retire
  it with CLI/kaizen readers migrated. Forbid duplicate per-artifact inventories.

---

## Phase 0 — Enabling cleanups (no behavior change)

Pure refactors that lower the cost of every later phase. Each is independently shippable and
test-neutral (behavior identical).

| Step | Change | Files | Removes |
|------|--------|-------|---------|
| 0.1 | Delete dead `compute_service_composite` (+ `__all__` entry); remove the no-op `repair_gridpos` call in `_repair_and_validate`; drop the dangling comment | checks.py, artifact_generator.py | D-6 |
| 0.2 | Centralize the duplicated composite weights into one constants block; reference from both validator and generator | checks.py, artifact_generator.py | D-8 |
| 0.3 | Extract a shared **check-runner** (`run_checks(list[(code, passed: bool, msg)]) -> (passed, total, issues)`) + a base result dataclass; refactor `validate_dashboard/alerts/slo` onto it (behavior identical) | checks.py | D-9 (enables Phase 4) |
| 0.4 | Move the `--portal-persona=all` fan-out **inside** the generator; CLI calls the generator once | scripts, artifact_generator.py | D-10 |
| 0.5 | **Capture a golden/characterization baseline** — run the generator on the run-007 fixture and snapshot every artifact's content + every quality score; this is the diff target for the risky Phase-2 refactors (CRP R1-S2) | (test fixture) | — |

**Validation:** full observability + validator + dashboard_creator suites green; **byte-identical**
artifact output vs the 0.5 baseline (these are refactors). For 0.4 specifically (the one step that
changes a control path), assert `load_onboarding_metadata` is called **exactly once** for
`--portal-persona=all` and persona output is byte-identical pre/post move (CRP R1-S9).

---

## Phase 1 — Keystone: two axes first-class (REQ-OAT-023)

The single highest-leverage change.

| Step | Change | Files |
|------|--------|-------|
| 1.1 | Add `_ARTIFACT_TYPE_TO_ORIENTATION` lookup (sibling of existing `_ARTIFACT_TYPE_TO_CATEGORY`) | artifact_generator.py |
| 1.2 | Add `category: str` + `orientation: str` to `ArtifactResult` (and `GenerationReport` grouping) | artifact_generator.py |
| 1.3 | Populate both **centrally**: in `_generate_one` and the ~5 non-`_generate_one` construction sites, from the two tables — not at 40 call sites | artifact_generator.py |
| 1.4 | Emit `category`+`orientation` in `_write_index` and `_write_quality_report` per-artifact records | artifact_generator.py |

**Collapses for free:** D-2 (bucket category-3 out of the `services` dict using `category`),
D-4 (replace the `if type in (...)` role-bucketing with `group_by(orientation)`).

**Validation:** every artifact record carries both fields; the run-007 fixture's quality report
no longer shows a `project` entry in `services`; coverage bucketing keyed on orientation.

---

## Phase 2 — Unify dispatch + scoring (REQ-OAT-042, 070; D-1, D-5)

| Step | Change | Files |
|------|--------|-------|
| 2.1 | Replace the five dispatch mechanisms with **one dispatch table** keyed `(category, artifact_type) → (generator, output_prefix, scope=per-service|per-project)`; the orchestrator iterates the table | artifact_generator.py |
| 2.2 | Merge `_repair_and_validate` (triplet) and `_score_extended_artifacts` (extended) into **one** `(category, orientation)`-aware scoring dispatcher driven by a `type → validator/contract` table | artifact_generator.py, checks.py |

**Removes:** D-1, D-5. **Enforces:** REQ-OAT-070 — incl. no `(category,orientation)` branch in the
scoring dispatcher (CRP R1-F6/S-matrix). **Risk:** these are the highest-risk refactors; scope
(per-service vs per-project) must be explicit in the table (resolved: cat 1 per-service; cat 2/3
per-project). **Validation:** post-Phase-2 artifact set + per-artifact scores are **byte/score-identical
to the Phase-0.5 golden baseline** (not just "suites green") (CRP R1-S2); and after Phases 0–2,
capture `git diff --stat` and confirm a **non-positive net line delta** across the three production
modules (REQ-OAT-071; reviewed criterion, not a hard CI gate) (CRP R1-S1).

---

## Phase 3 — Naming / ownership (REQ-OAT-010/011/012/013, 021)

> **Sequencing (CRP R1-S7).** Phase 3 touches the same dispatch table + tests as Phase 2. Land
> Phase 3 **after** Phase 2 on the same line of development (not a parallel branch); 3.1/3.4
> dispatch changes MUST be **added rows** to the Phase-2 table (e.g. `onboarding_portal`,
> `role_dashboard`), never new dispatch control flow — else REQ-OAT-070 is violated via rebase.

| Step | Change | Files |
|------|--------|-------|
| 3.1 | Rename `generate_capability_index` → `generate_observability_inventory`; type `capability_index` → `observability_inventory`; output `observability-inventory.yaml`; update `_IMPLEMENTED_ARTIFACT_TYPES`, exclusion set, docstring | artifact_generator.py + tests |
| 3.2 | **Revert the Finding-2 masquerade** (REQ-OAT-013): reshape the body from the `manifest_id/version/capabilities[]` software-feature schema to a category-nested **inventory** (services + per-category artifact paths/counts) | artifact_generator.py + tests |
| 3.3 | `capability_index` becomes a category-aware honest skip owned by onboarding (REQ-OAT-011/052) | artifact_generator.py |
| 3.4 | Split `portal` → `onboarding_portal` + `role_dashboard` (REQ-OAT-021); update the dispatch table + persona handling | artifact_generator.py, portal_spec_builder.py + tests |

**Validation:** no artifact named `capability_index` produced by observability; `observability-inventory.yaml`
validates as an inventory; the run-007 Finding-2 test is replaced by an inventory-schema test; a
project declaring onboarding-owned `capability_index` shows an honest skip **and**
`artifacts_scored == artifacts_generated` still holds (skip excluded from the denominator, REQ-OAT-050)
(CRP R1-S6).

---

## Phase 4 — Orientation-aware validation + 3-way coverage (REQ-OAT-050/051/060/061/062; D-3)

Built on the Phase-0.3 check-runner, so the orientation branch is small.

| Step | Change | Files |
|------|--------|-------|
| 4.1 | Add `orientation` param to the validators; add the **bridge actionability** check (alert/loki: runbook/dashboard link + summary; notification_policy: non-null receiver/route) | checks.py |
| 4.2 | Split a `prometheus_rule`/`loki_rule` file into recording (system) vs alerting (bridge) subsets; score each; record the breakdown (REQ-OAT-062) | checks.py |
| 4.3 | Generalize coverage from 2 buckets to 3 orientations: `metric_coverage_human/system/bridge` (collect SLO/recording content as the system bucket); keep `…_dashboarded/_alerted` as aliases; **equal 1/3** 3-way composite blend (CRP R1-S5); **service/project/agent only**, not pipeline-innate (REQ-OAT-051) | artifact_generator.py |
| 4.4 | Demote `dashboard_spec` to `status="intermediate"` so it is not written/scored as an end artifact (D-3); declare only `dashboard` (JSON) | artifact_generator.py + tests |

**Validation:** a valid-but-unactionable alert scores partial; a recording+alerting `prometheus_rule`
shows a 2-part breakdown; a dashboard-only metric yields the documented **≈0.33** composite (numeric
assertion, not just field presence) (CRP R1-S5); `artifacts_scored == artifacts_generated` still
holds with `dashboard_spec` removed from **both** counts; and grep confirms **no orphaned readers**
of the `dashboard_spec` YAML path before demoting it (CRP R1-S8).

---

## Phase 5 — Metadata declare-don't-guess + routing + generation_report (REQ-OAT-020/022/024/025/030/031a/032/040/041; D-7, D-11)

> **Cross-repo dependency (CRP R1-S4 / REQ-OAT-025).** Steps 5.2–5.3 ("declare, don't guess") only
> take the *declared* branch once the **cap-dev-pipe onboarding exporter** emits `kind` +
> per-metric `category`. That exporter change is a tracked upstream dependency (out of this repo).
> Until it lands, the generator runs the heuristic **fallback** and MUST tag each classification
> `inferred` (a guard SHOULD log when fallback is used), so the dependency gap is visible, not
> silent.

| Step | Change | Files |
|------|--------|-------|
| 5.1 | `_declared_artifact_types` reads nested `artifact_categories` first, flat `artifact_types` as fallback; add `_flatten_artifact_categories` (REQ-OAT-020/022) | artifact_generator.py |
| 5.2 | Read declared **entry kind** (collapse `_is_non_service_entry` 7 heuristics → 1 check, name-pattern as recorded fallback) (REQ-OAT-024; D-7) | artifact_generator.py |
| 5.3 | Read declared **metric category/orientation**; route domain metrics to cat 4/5 surfaces (or record as "awaiting home"); heuristic fallback recorded as *inferred* (REQ-OAT-024/040/041) | artifact_generator.py |
| 5.4 | Once metric routing lands, **remove** the `_domain_alert_todo_block` stub machinery (D-11) | artifact_generator.py + tests |
| 5.5 | Emit `generation_report` (category-nested, per-artifact `{type, category, orientation, service, output_path, status, source_checksum, staleness_inputs}`) + link to `run-provenance.json`. `source_checksum` is over the **per-artifact input slice** (not whole-file) and includes a `generator_version`/template-hash; `staleness_inputs` names the fields hashed — so the deferred Phase-6 consumer's freshness test is fully determined by the report (CRP R1-S3; REQ-OAT-031a) | artifact_generator.py |
| 5.6 | Keep `generation_report` (retrospective: *what was produced*) distinct from the coverage/requirement contract (prospective: *what is needed*) — separate fields/files, never conflated (REQ-OAT-032 matrix gap) | artifact_generator.py |
| 5.7 | Ensure nested metadata accepts `project_observability` / `ai_agent_observability` category keys (reserved namespace) so cat-4/5 declarations don't error (REQ-OAT-041 matrix gap) | artifact_generator.py |

**Validation:** unrelated-service metadata edit leaves artifact X's `source_checksum` unchanged; a
`generator_version` bump changes it (CRP R1-S3). nested + flat metadata both parse; a non-service
entry with `kind` declared is
skipped without heuristics; cost/token metrics route off the service dashboard (or are recorded as
deferred); `generation_report` carries checksums; backward-compat flat view still emitted.

---

## Phase 6 — Auto-satisfy consumer (REQ-OAT-031b) — DEFERRED / cross-repo

Lives in **plan-ingestion (cap-dev-pipe)**, not these modules. Consumes the Phase-5
`generation_report` + checksums to auto-satisfy unchanged artifacts on serial / project-update runs
and emit a delta report. Tracked here only as the contract the Phase-5 producer must satisfy.

---

## Traceability (requirement → phase)

| REQ-OAT | Phase | REQ-OAT | Phase |
|---------|-------|---------|-------|
| 010/011 | 3 | 042 | 2 |
| 012/013 | 3 | 050 | 0.3 + 4 |
| 020/022 | 5 | 051 | 4 |
| 023 (keystone) | 1 | 052 | 1 + 3 |
| 024 | 5 | 060 | 1 |
| 021 | 3 | 061/062 | 4 |
| 030/031a | 5 | 070 | 2 (enforced) |
| 031b | 6 (deferred) | 040/041 | 5 |

Every REQ-OAT maps to a phase; every phase step traces to a REQ-OAT and/or an Appendix-D removal.

## Before-code checklist (per reflective-requirements Phase 6)

- [ ] Every v0.3 requirement has a plan step (above).
- [ ] Every plan step traces to a requirement or a D-item removal.
- [ ] No open questions remain (per-service/project dispatch + validator-location resolved in §0).
- [ ] Phases 0–2 net-remove lines before any feature lands (distillation-first).
- [ ] Phase-0.5 golden baseline captured; Phase-2 output diffs byte/score-identical against it (CRP R1-S2).
- [ ] `git diff --stat` after Phases 0–2 shows non-positive net delta across the 3 modules (REQ-OAT-071; reviewed, not a hard gate) (CRP R1-S1).
- [ ] Upstream cap-dev-pipe exporter dependency (REQ-OAT-025) is tracked; fallback path tags classifications `inferred` (CRP R1-S4).
- [ ] REQ-OAT-070 invariant holds after Phase 2 (new type = one table row, no new branch).

---

*Plan v0.1 — paired with requirements v0.3. Six phases; Phases 0–2 are distillation (remove
accidental complexity), 3–5 are the category/orientation features, 6 is the deferred cross-repo
consumer. Net line delta expected negative.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}` for this plan doc).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Net-removal gate | R1 (opus-4-8) | Before-code checklist + Phase-2 validation; reviewed criterion, not hard CI gate (REQ-OAT-071) | 2026-05-31 |
| R1-S2 | Golden/characterization baseline before Phase 2 | R1 | Added Phase 0.5 (capture) + Phase 2 validation diffs against it | 2026-05-31 |
| R1-S3 | source_checksum granularity + generator_version + staleness_inputs | R1 | Applied to Phase 5.5 + validation | 2026-05-31 |
| R1-S4 | Schedule upstream exporter cross-repo dependency | R1 | Phase 5 preamble cross-repo note + checklist (REQ-OAT-025) | 2026-05-31 |
| R1-S5 | Specify 3-way blend weights | R1 | Phase 4.3 equal-1/3 + numeric validation | 2026-05-31 |
| R1-S6 | Skip vs scored denominator | R1 | Phase 3 validation (skip excluded from denominator) | 2026-05-31 |
| R1-S7 | Sequence-harden Phase 3 vs Phase 2 | R1 | Phase 3 sequencing preamble | 2026-05-31 |
| R1-S8 | dashboard_spec demotion: orphaned-readers + counts | R1 | Phase 4.4 validation | 2026-05-31 |
| R1-S9 | Persona move single-load assertion | R1 | Phase 0.4 validation | 2026-05-31 |
| R2-S1 | Table repurpose/retire, not sibling | R2 (opus-4-8) | Phase-1 amendment: distinctly-named five-cat map + update generate_capability_index reader | 2026-05-31 |
| R2-S2 | Phase 1↔3 capability_index window | R2 | Phase-1 amendment: land Phase-3.2 revert before/with the repurpose | 2026-05-31 |
| R2-S3 | Aggregate rollup not pooled mean | R2 | Phase-4.3 amendment (missing axes=0) | 2026-05-31 |
| R2-S4 | Golden baseline covers Phase 1 | R2 | Phase-0.5/Phase-1 validation amendment | 2026-05-31 |
| R2-S5 | Single type-keyed registry | R2 | Phase-2 amendment (one registry; projections) | 2026-05-31 |
| R2-S6 | skip_reason/owner on skip record | R2 | Phase-3.3 amendment | 2026-05-31 |
| R3-S1 | requires_declaration flag | R3 (opus-4-8-1m) | Phase-2 amendment (registry column; orchestrator honours it) | 2026-05-31 |
| R3-S2 | dispatch ordering (spec before JSON) | R3 | Phase-2 amendment (ordered registry) | 2026-05-31 |
| R3-S3 | portal list return type | R3 | Phase-0.4 amendment (extend not append) | 2026-05-31 |
| R4-S1 | index consolidation | R4 (composer-2.5-fast) | NEW Phase-5.6 (one canonical index; demote/retire manifest) | 2026-05-31 |
| R4-S2 | cross-artifact migration | R4 | NEW Phase-4.5 (registry-keyed, or out-of-scope-legacy) | 2026-05-31 |
| R4-S3 | orientation-keyed coverage (aliases) | R4 | Phase-4.3 amendment | 2026-05-31 |
| R4-S4 | delete CLI persona loop | R4 | Phase-0.4 amendment (delete, not bypass) | 2026-05-31 |
| R4-S5 | exclude pseudo-service in Phase 1 | R4 | Phase-1 validation amendment | 2026-05-31 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-05-31

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-31 00:00:00 UTC
- **Scope**: Plan review (S-prefix) for the 6-phase observability-taxonomy implementation. Focus: distillation-first sequencing, dispatch/scoring unification risk, producer/consumer seam, validation gating.

**Executive summary (top risks / gaps / opportunities):**
- The plan's net-removal thesis (Guiding principle) has no measurable gate — Phases 0–2 are asserted to net-remove but nothing in the plan verifies it.
- Phase 2's two unifications (dispatch table + scoring dispatcher) are the highest-risk steps yet carry only "suites green" validation; no characterization/golden test is mandated before the refactor.
- The producer/consumer seam (Phase 5.5 → Phase 6) emits `source_checksum` but the plan never states checksum granularity or what makes an artifact stale — Phase 6 (cross-repo) inherits an under-specified contract.
- REQ-OAT-024 "declare, don't guess" (Phases 5.1–5.3) depends on an upstream cap-dev-pipe onboarding-exporter change that the plan does not schedule or flag as a dependency.
- Phase 4.3's 3-way coverage blend has no specified weighting in the plan; validation only checks presence, not the headline value.
- Phase ordering puts the keystone (Phase 1) before unification (Phase 2) correctly, but Phase 3's rename/revert touches tests that Phase 2's dispatch-table change also touches — rebase/sequencing friction risk.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | Add a measurable net-removal gate to the Before-code checklist and Phase-2 validation: capture `git diff --stat` after Phases 0–2 and assert non-positive net line delta across the three modules | The "Guiding principle" and closing note both promise the pass net-removes lines, but no plan step verifies it; an unmeasured claim can silently regress to addition (mirrors requirements R1-F1) | "Before-code checklist" + Phase 2 Validation row | CI/diff-stat check on the Phase 0–2 PR shows net deletions |
| R1-S2 | Risks | high | Before Phase 2's dispatch/scoring unification, add a Phase-0 step to capture a golden/characterization snapshot of all artifacts + scores on the run-007 fixture; Phase 2 validation MUST diff against it, not just assert "suites green" | Step 2.1 (one dispatch table replacing five mechanisms) and 2.2 (merging `_repair_and_validate` + `_score_extended_artifacts`) are the riskiest refactors; "same artifacts produced as before; suites green" is asserted but no byte/score-level baseline is mandated to catch silent scoring drift | Phase 0 (new step 0.5) + Phase 2 Validation | Golden test: post-Phase-2 artifact set + per-artifact scores are byte/score-identical to the captured baseline |
| R1-S3 | Interfaces | high | In Phase 5.5, specify the `source_checksum` granularity (per-artifact input-slice of metadata+manifest) and include a `generator_version`/template-hash component + a per-record `staleness_inputs` field, so the deferred Phase-6 consumer has a complete freshness contract | Phase 5.5 emits `source_checksum` but the plan (like REQ-OAT-031a) never pins granularity or template-version inclusion; Phase 6 is cross-repo and can only consume what Phase 5.5 emits — an under-specified seam causes over-invalidation or stale reuse (requirements R1-F2) | Phase 5, Step 5.5 | Unit test: unrelated-service metadata edit leaves artifact X's checksum unchanged; `generator_version` bump changes it |
| R1-S4 | Architecture | high | Add an explicit upstream-dependency step/flag: Phases 5.1–5.3 (REQ-OAT-024 declare-don't-guess) require the cap-dev-pipe onboarding exporter to emit `kind` + per-metric `category`; schedule or flag this cross-repo dependency, else the heuristic "fallback" becomes the primary path | The plan treats "read declared kind/category" as in-module work, but the declarations originate upstream; without the exporter change, Phases 5.1–5.3 ship a fallback-only path that defeats REQ-OAT-024 (requirements R1-F7) | Phase 5 preamble or a new "Cross-repo dependencies" note beside Phase 6 | Integration: generator on updated-exporter fixture takes the declared branch; a guard logs when fallback (inferred) is used |
| R1-S5 | Validation | medium | Phase 4.3 must specify the 3-way composite blend weights (e.g. equal 1/3) and add a validation row asserting the headline value for a single-axis-covered metric, not just presence of the three fields | Phase 4.3 validation only checks `metric_coverage_{human,system,bridge}` are "present"; the composite value that folds them is unspecified, so a visualized-only metric's headline score is undefined and could mislead (requirements R1-F4) | Phase 4, Step 4.3 + Validation | Test: dashboard-only metric yields the documented composite (e.g. 0.33), asserted numerically |
| R1-S6 | Validation | medium | Make the Finding-1 invariant (`artifacts_scored == artifacts_generated`) explicit about honest-skips (Phase 3.3 / REQ-OAT-052): state that skipped declared-but-unproduced types are excluded from the scored denominator, not counted as 0-score | Phase 3.3 introduces category-aware honest skips while Phase 4 preserves the scored==generated invariant; the plan does not say how skips interact with the denominator — a silent off-by-skip in coverage math | Phase 3 Step 3.3 + Phase 4 Validation | Test: project declaring onboarding-owned `capability_index` shows an honest skip while scored==generated still holds |
| R1-S7 | Ops | medium | Sequence-harden Phase 3 vs Phase 2: both touch the same test files (dispatch table in 2.1; rename/persona/dispatch updates in 3.1/3.4). Note the shared-file ordering in the plan and land Phase 3's dispatch-table edits as extensions of the Phase-2 table, not parallel edits | Phase 2.1 builds the dispatch table and Phase 3.4 adds rows (`onboarding_portal`/`role_dashboard`) to it; if developed in parallel branches they collide on `artifact_generator.py` dispatch + tests, creating rebase friction and risking REQ-OAT-070 violation via a parallel branch | Phase 3 preamble | Review: Phase 3 dispatch changes are diffs that only add table rows, no new dispatch control flow |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Risks | medium | Phase 4.4 demotes `dashboard_spec` to `status="intermediate"` (not written/scored), but Phase 1.4 and the index writers emit per-artifact records; confirm the demotion does not break the `artifacts_scored == artifacts_generated` count and that no downstream reader expects the spec file on disk | Removing `dashboard_spec` from the scored set changes both numerator and denominator and removes a file some consumer (e.g. a debug/inspection step) may read; the plan asserts the invariant "still holds" but does not check for orphaned readers of the spec file | Phase 4 Step 4.4 Validation | Test: grep for readers of the `dashboard_spec` YAML path; invariant holds with spec excluded from both counts |
| R1-S9 | Ops | low | Phase 0.4 / D-10 moves the `--portal-persona=all` fan-out inside the generator; add a validation that the CLI's persona output is byte-identical pre/post move and that metadata is loaded exactly once (the bug D-10 calls out) | Phase 0 claims "byte-identical artifact output," but the persona fan-out move is the one Phase-0 step that changes a control path (CLI→generator); a single-load assertion directly verifies the D-10 fix rather than assuming it | Phase 0 Step 0.4 / Validation | Test/trace: `load_onboarding_metadata` called once for `--portal-persona=all`; persona artifacts byte-identical to pre-move |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round.

**Disagreements** (prior untriaged items this reviewer would reject): none — first round.

#### Review Round R2 — claude-opus-4-8 — 2026-05-31

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-05-31 17:10:00 UTC
- **Scope**: Plan review (S-prefix), **code-grounded**. R1 caught the obvious sequencing/validation gaps; this round read the target modules and focuses on interactions the plan's phase ordering creates with the *existing* implementation (the keystone's collision with `_ARTIFACT_TYPE_TO_CATEGORY`, the coverage rollup, and the capability_index migration window).

**Executive summary (top risks / gaps / opportunities):**
- Phase 1.1 calls `_ARTIFACT_TYPE_TO_ORIENTATION` a "sibling of existing `_ARTIFACT_TYPE_TO_CATEGORY`," but the existing table holds a *different axis* (`observe/integration/action/reference`, `artifact_generator.py:1584`), not the five-category enum — the keystone repurposes a live field, not just adds a sibling.
- Phase ordering (1 repurposes the category table; 3 removes its only reader `generate_capability_index`) creates a **window** where the masquerade emits new-taxonomy category strings into the capability schema.
- Phase 4.3's "equal 1/3" fixes the per-metric value but inherits the existing **count-pooled** aggregate (`_write_quality_report:2433`) which is not equal-weight across services missing an axis.
- The Phase-0.5 golden baseline guards Phase 2, but the riskiest *semantic* change is Phase 1's table repurpose; the baseline should cover it too.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | Phase 1.1 MUST treat `_ARTIFACT_TYPE_TO_CATEGORY` as a **repurpose/retire**, not an additive sibling: the existing table maps to `observe/integration/action/reference` (`artifact_generator.py:1584`), a different axis than the five-category enum. Add a Phase-1 step to introduce a distinctly-named five-category table (or rename + value-migrate) and update its sole reader `generate_capability_index` (line 1631). | The plan's "sibling of existing `_ARTIFACT_TYPE_TO_CATEGORY`" framing under-counts the work and risks silently overloading a field that an existing artifact reads (requirements R2-F1). | Phase 1, new step 1.0 or 1.1 note | Grep: only the new five-category map feeds `category` on `ArtifactResult`; legacy 4-value set retired or explicitly mapped |
| R2-S2 | Ops | medium | Sequence-harden Phase 1 vs Phase 3: Phase 1 repurposes the category table while `generate_capability_index` (still emitted, `:1985`) reads it at line 1631 until Phase 3.2 reverts the masquerade. Land the **revert (3.2) or the table-reader update before/with** the Phase-1 repurpose, so no run emits new-taxonomy category strings into the capability schema. | Cross-phase interaction the per-phase validation misses: Phase 1 changes table semantics, Phase 3 removes the consumer; between them the masquerade leaks `service_observability` etc. into a capability manifest (requirements R2-F1). | Phase 1 / Phase 3 sequencing note | Test: at the Phase-1 PR boundary, capability_index output (if still produced) carries no five-category enum value |
| R2-S3 | Validation | medium | Phase 4.3 MUST specify the **aggregate** coverage rollup, not just the per-metric 1/3: replace the existing count-pooled mean (`_write_quality_report:2433`, `(sum(dash)+sum(alert))/(len(dash)+len(alert))`) with a mean of per-metric/per-service composites where missing axes score 0. Add a validation row. | R1-S5 pinned the per-metric ≈0.33 but not the rollup; the inherited pooled mean is availability-weighted, so the headline `avg_metric_coverage_score` is not equal-1/3 when a service has no bridge artifacts (requirements R2-F2). | Phase 4, Step 4.3 + Validation | Test: two services, one with no alerts, yield the documented equal-weight aggregate, not the pooled value |
| R2-S4 | Risks | medium | Extend the Phase-0.5 golden baseline + diff guard to cover **Phase 1's table repurpose** (capability_index / quality-report `category` strings), not only Phase 2's dispatch/scoring refactor. | The plan treats Phase 1 as behavior-collapsing-for-free, but repurposing `_ARTIFACT_TYPE_TO_CATEGORY` changes the `category` value emitted by `generate_capability_index` (line 1631) and the quality report — an observable output change that the byte/score baseline should catch (extends CRP R1-S2). | Phase 0 Step 0.5 / Phase 1 Validation | Golden diff: Phase-1 output changes are limited to intended new `category`/`orientation` fields; no unintended capability-schema drift |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S5 | Architecture | medium | Phase 2.1 (`(category, artifact_type)` dispatch table) and Phase 2.2 (`(category, orientation)` scoring dispatcher) SHOULD derive from a **single type-keyed registry** rather than two independently-keyed tables, so the two-axis model does not become a new D-1/D-5-style smell. | Two composite keys for one artifact must be kept consistent by hand; a single `type → {category, orientation, generator, validator_set, scope}` row makes both projections derived (requirements R2-F4). | Phase 2 preamble / Steps 2.1–2.2 | Code review: one registry; dispatch and scoring both index it; adding a type is one row |
| R2-S6 | Ops | low | Phase 3.3 honest-skip needs a **`skip_reason`/`owner`** on the skip record: the existing `_record_unimplemented_artifact_types` (line 2056) emits a single "not implemented" reason, but REQ-OAT-011/052 want "owned by onboarding" distinguished from "unimplemented." | Without the reason field the honest-skip cannot say *why* (owned elsewhere vs not built), and REQ-OAT-052's "with owner" is unmet (requirements R2-F3). | Phase 3, Step 3.3 | Test: onboarding-owned `capability_index` skip carries `skip_reason=owned_elsewhere`/`owner=onboarding` |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): R1-S2 (golden baseline) — R2-S4 extends it to Phase 1. R1-S5 (3-way blend weights) — R2-S3 extends it to the aggregate rollup. R1-S7 (Phase 3 vs 2 sequencing) — R2-S2 adds the Phase-1↔3 capability_index window.

**Disagreements** (prior untriaged items this reviewer would reject): none.

#### Review Round R3 — claude-opus-4-8-1m — 2026-05-31

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-31 17:50:00 UTC
- **Scope**: Plan review (S-prefix), **code-grounded**. Focused on hidden complexity traps in the implementation details of Phases 0 and 2.

**Executive summary (top risks / gaps / opportunities):**
- Phase 2.1 unifies the dispatch loop but misses that the triplet is currently generated *unconditionally* while extended artifacts are generated *conditionally* (only if declared). Unifying them naively will break behavior.
- Phase 2.1 unification also risks breaking ordering dependencies. `_convert_dashboards_to_grafana_json` runs after `dashboard_spec` is generated.
- Phase 0.4 moves the persona fan-out inside the generator, changing its return type from a single `ArtifactResult` to a `List`, which breaks the orchestrator's `append` logic.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Architecture | high | Phase 2.1 MUST add a `requires_declaration: bool` (or `always_generate: bool`) column to the unified dispatch table. The orchestrator must check this flag: generate the legacy triplet unconditionally (as it does today), but generate extended artifacts only if they exist in `declared_artifact_types`. | The current code uses two separate loops with different generation conditions (`_GENERATORS` vs `_EXTENDED_PER_SERVICE_GENERATORS`). A single loop without this flag will either skip required triplet artifacts or generate unrequested extended ones (requirements R3-F1). | Phase 2, Step 2.1 | Code review: The dispatch table explicitly encodes the condition, and the orchestrator loop respects it |
| R3-S2 | Architecture | medium | Phase 2.1 MUST explicitly document that the dispatch table's iteration order is topologically sorted, ensuring `dashboard_spec` is generated before the `dashboard` JSON converter runs. | `_convert_dashboards_to_grafana_json` requires `dashboard_spec` to already be in `report.artifacts`. Moving it into a unified dispatch loop introduces a hard ordering dependency that the plan overlooks (requirements R3-F2). | Phase 2, Step 2.1 | Test: The JSON conversion runs successfully and finds the spec in the report when triggered from the unified dispatch loop |
| R3-S3 | Ops | medium | Phase 0.4 MUST note that moving `--portal-persona=all` inside `_generate_portal_artifact` changes its return type from `Optional[ArtifactResult]` to `List[ArtifactResult]`, requiring the orchestrator (`artifact_generator.py:1980`) to `extend` rather than `append` to `report.artifacts`. | The plan treats this as a pure move, but `ArtifactResult` is a single object. Fanning out personas means returning multiple artifacts. A simple move without updating the signature and caller will cause type errors or nested lists. | Phase 0, Step 0.4 | Code review: The orchestrator handles a list return from the portal generator correctly |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S1: Retiring the old category table is required.
- R2-S5: Single type-keyed registry is the correct architectural end-state.

**Disagreements** (prior untriaged items this reviewer would reject): none.

#### Review Round R4 — composer-2.5-fast — 2026-05-31

- **Reviewer**: composer-2.5-fast
- **Date**: 2026-05-31 18:15:00 UTC
- **Scope**: Plan review (S-prefix), **code-grounded**. R1–R3 covered dispatch/scoring unification; this round targets **index consolidation**, **type-alias migration**, and **CLI end-user gates** visible in the three target modules today.

**Executive summary (top risks / gaps / opportunities):**
- Phase 5 adds `generation_report` but leaves `_write_index` (`observability-manifest.yaml`) producing a parallel artifact inventory — triple-index accidental complexity unless Phase 5.6 specifies retirement.
- Internal `alert_rule` vs declared `prometheus_rule` breaks bridge metric coverage in `_write_quality_report:2351` today; Phase 4.3 orientation refactor must not repeat this via string compares.
- `--min-artifact-type-coverage` reads manifest `artifact_type_coverage` which penalizes honest onboarding-owned skips — operators see false FAIL.
- Phase 0.4 must delete the CLI `--portal-persona=all` re-load loop (`scripts/generate_observability_artifacts.py:139–171`), not only move fan-out into the generator.
- Cross-artifact validation (`validate_cross_artifact_consistency`) is absent from plan phases but still feeds kaizen postmortem — type renames will silently degrade it.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Architecture | high | Phase 5.6 MUST specify **index consolidation**: either repurpose `_write_index` to emit `generation_report` (renaming the file) and drop duplicate artifact lists from `observability-manifest.yaml`, or mark manifest deprecated in the same PR that adds `generation_report`. Add a validation row asserting **one** canonical per-artifact inventory file. | REQ-OAT-030 names `_write_index` as the producer seam; Phase 5.5 adds a second inventory without a removal step — permanent dual-writer complexity (requirements R4-F1). End users and CLI gates already read manifest (`generate_observability_artifacts.py:283`). | Phase 5, Step 5.6 + Validation | Test: grep shows one file holds full per-artifact `{type,category,orientation,checksum}` inventory; manifest lacks duplicate list or carries `deprecated: true` |
| R4-S2 | Validation | medium | Phase 4 MUST add a step (e.g. 4.5) to migrate **`validate_cross_artifact_consistency`** and kaizen cross-artifact emission to use **declared_type + orientation** from the unified registry instead of hard-coded type names (`dashboard`, `alert_rule`, `portal`). | Cross-artifact checks predate the taxonomy but still run from the CLI (`generate_observability_artifacts.py:395–427`); Phase 3.4 portal split and prometheus/alert alias normalization will silently stop detection while per-artifact scores stay green — parallel validation path smell (requirements R4-F5). | Phase 4 (new step 4.5) | Test: fixture with alert referencing unvisualized metric still populates `cross_artifact_issues` after portal split |
| R4-S3 | Validation | medium | Phase 4.3 MUST replace `_write_quality_report`'s type-string content pools (`:2349–2352`, `alert_rule` only) with **orientation-keyed collection** from the registry, including `prometheus_rule`/`dashboard` declared aliases (requirements R4-F3). | Bridge metric coverage ignores `prometheus_rule` artifacts today; Phase 4's 3-way blend inherits this bug if not explicitly fixed — headline `avg_metric_coverage_score` misleads operators (Ask 4). | Phase 4, Step 4.3 + Validation | Test: declared `prometheus_rule` with live rules yields non-zero bridge coverage component |
| R4-S4 | Ops | medium | Phase 0.4 MUST **delete** the CLI `--portal-persona=all` branch that reloads metadata per persona (`scripts/generate_observability_artifacts.py:139–171`) once fan-out moves into the generator; keeping both paths preserves D-10 (triple metadata load). | Plan Step 0.4 says "CLI calls the generator once" but does not require removing the legacy CLI loop; partial migration leaves accidental complexity and violates the single-load assertion in Phase 0 Validation (extends R1-S9). | Phase 0, Step 0.4 + Validation | Test: `--portal-persona=all` invokes generator once; no `load_onboarding_metadata` in CLI for persona fan-out |
| R4-S5 | Validation | low | Phase 1 Validation MUST assert category-3 artifacts (`capability_index`/future inventory, portal) are **excluded from the per-service `services` dict** in `observability-quality.json` immediately — not deferred to Phase 4 — so D-2 spurious composites do not pollute `--min-metric-coverage` gates during the migration window. | D-2 documents fake project-level service entries in quality JSON today (`generate_capability_index:1653`, `_write_quality_report:2334`); Phase 1 adds `category` but plan validation only checks field presence, not exclusion from per-service composites. | Phase 1 Validation row | Test: quality JSON `services` keys are runtime service IDs only; no `project_id` pseudo-service composite |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): R2-S1/S2 (Phase 1↔3 sequencing). R2-S3 (aggregate rollup). R3-S1/S2 (dispatch flags + ordering). R3-S3 (portal list return type). Plan Phase 5.6 existence for REQ-OAT-032 — R4-S1 strengthens it with concrete retirement criteria.

**Disagreements** (prior untriaged items this reviewer would reject): none.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to the plan phase/step that addresses it. Coverage: **Covered** / **Partial** / **Gap**.

| Requirement | Plan Phase / Step | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| REQ-OAT-010 (no `capability_index` from obs generator) | Phase 3.1, 3.3 | Covered | — |
| REQ-OAT-011 (honest-skip for onboarding-owned `capability_index`) | Phase 3.3 | Covered | — |
| REQ-OAT-012 (`observability_inventory.yaml`, category 3) | Phase 3.1, 3.2 | Covered | — |
| REQ-OAT-013 (revert the Finding-2 masquerade) | Phase 3.2 | Covered | — |
| REQ-OAT-020 (nested `artifact_categories`) | Phase 5.1 | Covered | — |
| REQ-OAT-021 (`onboarding_portal` + `role_dashboard` split) | Phase 3.4 | Covered | — |
| REQ-OAT-022 (derived flat `artifact_types` backward-compat) | Phase 5.1 | Partial | Plan implements `_flatten_artifact_categories` but does not address duplicate-key/ordering precedence (R1-F3 / R1-S-N/A) |
| REQ-OAT-023 (keystone: category+orientation on every record) | Phase 1.1–1.4 | Covered | — |
| REQ-OAT-024 (declare, don't guess) | Phase 5.2, 5.3 | Partial | Reads declared `kind`/metric-category but no plan step schedules the upstream cap-dev-pipe exporter change that must emit them (R1-S4 / R1-F7) |
| REQ-OAT-030 (`generation_report`) | Phase 5.5 | Covered | — |
| REQ-OAT-031a (producer: `source_checksum`) | Phase 5.5 | Partial | Checksum granularity + `generator_version`/template-hash + `staleness_inputs` unspecified (R1-S3 / R1-F2) |
| REQ-OAT-031b (consumer: auto-satisfy) | Phase 6 (deferred, cross-repo) | Covered | Correctly out of scope; tracked as the contract Phase 5.5 must satisfy |
| REQ-OAT-032 (intent direction: needed vs produced) | — | Gap | No plan step asserts the prospective (coverage contract) vs retrospective (`generation_report`) distinction is preserved / non-conflated |
| REQ-OAT-040 (metric routing by declared category) | Phase 5.3 | Covered | — |
| REQ-OAT-041 (reserved categories 4 & 5 namespaced) | Phase 4.3 (system-bucket), 5.3 (route/record) | Partial | Reserved categories defined via routing/recording but no explicit plan step namespaces `project_observability`/`ai_agent_observability` in metadata |
| REQ-OAT-042 (orchestration dispatch by category) | Phase 2.1 | Covered | — |
| REQ-OAT-050 (category- & orientation-aware validation; scored==generated) | Phase 0.3 (check-runner), Phase 4.1 | Covered | — |
| REQ-OAT-051 (orientation-based metric coverage, 3-way) | Phase 4.3 | Partial | 3-way blend weights / headline composite value unspecified (R1-S5 / R1-F4) |
| REQ-OAT-052 (category-aware honest skip; per-category coverage) | Phase 1 + 3.3 | Partial | Skip vs scored-denominator interaction unstated (R1-S6 / R1-F8) |
| REQ-OAT-060 (every type declares orientation) | Phase 1.1 | Covered | — |
| REQ-OAT-061 (bridge: both sub-dimensions) | Phase 4.1 | Partial | Runbook/dashboard-link failure mode + runbook production ownership unspecified (R1-F5) |
| REQ-OAT-062 (mixed-orientation files: score off-orientation subset) | Phase 4.2 | Covered | — |
| REQ-OAT-070 (extension by table, not control flow) | Phase 2.1, 2.2 (enforced) | Partial | Guards per-`type` branches but not `(category,orientation)`-keyed branches in scoring dispatcher (R1-F6) |

## Requirements Coverage Matrix — R2 (code-grounded deltas only)

Analysis only (not triage). Lists requirements whose coverage changes once the existing implementation is inspected; rows not listed are unchanged from R1.

| Requirement | Plan Phase / Step | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| REQ-OAT-023 (keystone: category+orientation; assigned from lookup tables) | Phase 1.1–1.4 | Partial | Plan assumes `_ARTIFACT_TYPE_TO_CATEGORY` is the 5-cat table; in code (`:1584`) it holds `observe/integration/action/reference`. No step repurposes/retires it or updates its reader `generate_capability_index:1631` (R2-S1 / R2-F1) |
| REQ-OAT-051 (orientation metric coverage, 3-way) | Phase 4.3 | Partial | Per-metric 1/3 fixed (R1) but **aggregate** rollup unspecified; inherits count-pooled mean (`:2433`), not equal-weight across axis-missing services (R2-S3 / R2-F2) |
| REQ-OAT-052 (honest skip with owner) | Phase 3.3 | Partial | Existing skip path (`:2056`) emits one reason; no `skip_reason`/`owner` to distinguish onboarding-owned (011) from unimplemented (R2-S6 / R2-F3) |
| REQ-OAT-070 (extension by table) | Phase 2.1, 2.2 | Partial | Two differently-keyed tables — `(category,artifact_type)` dispatch vs `(category,orientation)` scoring — not one type-keyed registry; a new consistency burden (R2-S5 / R2-F4) |
| REQ-OAT-062 (mixed-orientation files) | Phase 4.2 | Partial | Denominator rule for a dual-scored file (1 artifact vs 2 toward scored==generated) unstated (R2-F5) |

## Requirements Coverage Matrix — R3 (code-grounded deltas only)

Analysis only (not triage). Lists requirements whose coverage changes once the complexity of unified dispatch is inspected; rows not listed are unchanged from R2.

| Requirement | Plan Phase / Step | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| REQ-OAT-042 (orchestration dispatch by category) | Phase 2.1 | Partial | Unifying dispatch naively breaks the existing conditional vs unconditional generation behavior (`_GENERATORS` vs `_EXTENDED_PER_SERVICE_GENERATORS`). Missing a `requires_declaration` flag (R3-S1 / R3-F1). |
| REQ-OAT-042 (orchestration dispatch by category) | Phase 2.1 | Partial | Unifying dispatch ignores hard ordering dependencies (`dashboard` JSON conversion depends on `dashboard_spec`). Topologically sorted iteration order is unstated (R3-S2 / R3-F2). |
| REQ-OAT-051 / 052 (coverage vs skips) | Phase 3.3 | Partial | Skips exempt the artifact from the scored denominator, but the interaction with *metric* coverage is unstated. A skipped artifact shouldn't grant a free pass to uncovered metrics (R3-F3). |

## Requirements Coverage Matrix — R4 (code-grounded deltas only)

Analysis only (not triage). Lists requirements whose coverage changes once type-alias drift and index overlap are inspected; rows not listed are unchanged from R3.

| Requirement | Plan Phase / Step | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| REQ-OAT-032 (prospective vs retrospective; single authoritative index) | Phase 5.6 | Partial | Step 5.6 says "keep distinct" but does not retire `_write_index` / `observability-manifest.yaml` duplicate inventory — three overlapping indexes remain (R4-S1 / R4-F1) |
| REQ-OAT-030 (`generation_report` producer) | Phase 5.5 | Partial | Producer seam still documented as `_write_index` in requirements §4.5 while plan adds a separate file — dual-writer unless consolidated (R4-F1) |
| REQ-OAT-051 (orientation metric coverage) | Phase 4.3 | Partial | Coverage collection still type-string-based in code (`alert_rule` only); declared `prometheus_rule` alias not covered (R4-S3 / R4-F3) |
| REQ-OAT-052 (honest skip + coverage gates) | Phase 3.3 | Partial | `artifact_type_coverage` in manifest penalizes `owned_elsewhere` skips — CLI gate false FAIL (R4-F2) |
| REQ-OAT-023 (keystone fields on every record) | Phase 1.1–1.4 | Partial | No `declared_type` vs runtime alias on `ArtifactResult`; registry cannot unify reporting (R4-F4) |
| REQ-OAT-050 (validation) | Phase 4 | Partial | Cross-artifact consistency validators not in plan; will silently break on type renames (R4-S2 / R4-F5) |
