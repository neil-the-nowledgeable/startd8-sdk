# Affordance-Map Consume (startd8 Generator) — Implementation Plan

**Version:** 0.4 (aligned with REQ v0.4 — CRP triaged)  
**Date:** 2026-07-28  
**Status:** Ready to implement  
**Requirements:** [`REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md`](REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md)  
**Parent Phase B:** ContextCore `REQ_O11Y_AUDIT_CATALOG_REPORT_CARD` FR-AFF-3 (`gen.*`)  
**CRP focus:** [`.crp-focus.md`](.crp-focus.md)

---

## 1. Goal

Wire optional AffordanceMap JSON into `generate_observability_artifacts` so listed **live** `gen.*` actions become **targeted repairs** with **merge-into-existing** index/quality writers — plus shrink — without `import contextcore` or full-tree thrash. Advisory/unreachable affordances skip honestly.

---

## 2. Architecture

```text
scorecard-json / affordance_map.json
        │
        ▼
  load_affordance_map()      # FR-B1 — parse, truncation stamp, exit codes
        │
        ▼
  normalize + match ladder   # FR-B6a
        │
        ▼
  plan_affordance_actions()  # FR-B2/B2b — list[ActionPlanEntry]
        │
   --dry-run? ──yes──► print plan + exit 0 (no writes)
        │ no
        ▼
  apply_affordance_actions() # live actions only
        │
        ▼
  merge_index_and_quality()  # FR-B3a — splice touched; preserve others
        │
        ▼
  affordance_actions.json    # FR-B7 — applied / applied_no_change / skipped + hashes
```

**Module home (new):** `src/startd8/observability/affordance_map_consume.py`

### Mode rule (FR-B3a) — disposition table

| Step / artifact | Map mode |
|-----------------|----------|
| Unconditional `_GENERATORS` full loop | **skip** |
| Planned `gen.*` apply | **run** (live only) |
| Declared-lane SLOs | **run** only under `gen.complete_triplet` for touched svc |
| `_convert_dashboards_to_grafana_json` | **run** for touched dashboards (needed for shrink re-measure) |
| `_write_index` / `_write_quality_report` | **merge** (never full rebuild from partial report) |
| Domain alert/dashboard, criticality, collector enrichment, capability index, portal | **skip** (preserve on disk + merged rows) |
| `_score_extended_artifacts` / orientation | **run** for touched / newly written only |
| Coverage gates / kaizen quality overwrite | **refuse or bypass** (FR-B9) |
| `--check` | **refuse** (NR-G8) |

---

## 3. Work packages

### WP-B0 — Loader, planner, join, CLI, merge skeleton (FR-B1, B2*, B6*, B8, B9, AC-G2/6–11)

| Step | Change |
|------|--------|
| B0.1 | `affordance_map_consume.py`: types, load, plan, normalize+ladder, KNOWN_GEN + advisory/unreachable annotations |
| B0.2 | Fixtures: CC scorecard + slim array + truncated/history + ENV_FORM join table |
| B0.3 | CLI `--affordance-map`; reuse `--dry-run`; refuse `--check`+map; refuse/bypass coverage gates; no confidence flag |
| B0.4 | Unit tests + CC drift-canary fixture (opt-in import only in tests) |
| B0.5 | **Merge-into-existing** helpers for manifest + quality (implement before WP-B1 writes) |
| B0.6 | HOWTO join table + exit codes |

**Exit:** dry-run plan stable; AC-G2/6–11 green.

### WP-B1 — Targeted apply + FR-B5 (FR-B3, B3a, B5, AC-G3/4/12)

| Step | Change |
|------|--------|
| B1.1 | Branch: map → apply + merge (not full loop) |
| B1.2 | `gen.emit_red_panels` → `_ensure_red_coverage`; hash; `applied_no_change` when no-op |
| B1.3 | `gen.complete_triplet` → read quality JSON legs; regenerate missing/0.0; declared lanes with SLO leg |
| B1.4 | `gen.improve_metric_coverage` / `gen.enrich_runbook` → skip with documented reasons |
| B1.5 | FR-B5: Overview/Risks/Procedures/Escalation; Risks body from coverage/criticality |
| B1.6 | Tests: single-service RED + untouched quality/manifest byte-identical; freshness → applied_no_change |

**Exit:** AC-G1, G3, G4, G12 green.

### WP-B2 — Shrink (FR-B4, AC-G5)

| Step | Change |
|------|--------|
| B2.1 | Resolve `max_lines` from expected_output_contracts |
| B2.2 | Drop panels at **spec** layer (non-RED first) |
| B2.3 | Re-render JSON; re-measure; iterate; refuse if render unavailable or RED would regress |
| B2.4 | Graph integrity (id uniqueness, targets, gridPos reflow) |
| B2.5 | Sidecar content hashes (not `--check`) |

**Exit:** AC-G5 green.

### WP-B3 — Sidecar + operator glue (FR-B7)

| Step | Change |
|------|--------|
| B3.1 | Complete `affordance_actions.json` schema |
| B3.2 | HOWTO end-to-end recipe |
| B3.3 | Optional jq extract only |

**Exit:** sidecar fields complete.

---

## 4. File touch list (expected)

| Path | Role |
|------|------|
| `src/startd8/observability/affordance_map_consume.py` | **New** |
| `src/startd8/observability/artifact_generator.py` | Map branch; merge writers |
| `src/startd8/observability/artifact_generator_generators.py` | RED / selective regen / runbook headings+Risks / shrink |
| `scripts/generate_observability_artifacts.py` | Flags + exit codes |
| `tests/…/test_affordance_map_consume.py` | Unit + join + merge + exit |
| `tests/fixtures/affordance_map/*` | Fixtures |
| `docs/design/observability-affordance-consume/*` | REQ/PLAN/HOWTO |

---

## 5. Traceability (REQ → WP)

| REQ | WP |
|-----|-----|
| FR-B0, NR-G* | All |
| FR-B1, B6, B6a, B8, B9 | B0 |
| FR-B2, B2a, B2b | B0 |
| FR-B3, B3a, B5 | B1 |
| FR-B4 | B2 |
| FR-B7 | B3 |
| AC-G1–G12 | per WP exits |

---

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Partial report truncates quality SSOT | Merge writers before apply (R1-S1) |
| Shrink deletes RED / breaks grid | OBS-200a + graph integrity + refuse |
| Join drift vs CC | Verbatim algorithm + canary fixture |
| Advisory affordances look “applied” | Skip reasons + `applied_no_change` |
| Coverage gate on partial tree | FR-B9 refuse/bypass |
| `--check` false durability | Content hashes (R2-S1) |

---

## 7. Out of scope

- SIL-REX `rex.*` / `measure.*`  
- Renaming `gen.*` / Phase A schema  
- Mandatory map  
- LLM repairs  
- Authored-panel shrink merge  
- Live dashboard repair for `improve_metric_coverage`  

---

## 8. Implementation order

1. WP-B0 (incl. merge helpers)  
2. WP-B1  
3. WP-B2  
4. WP-B3  

CRP complete — **implement from this plan**.

---

*Aligned with REQ v0.4. Do not relitigate: no import contextcore, merge writers, Hayai FR-B5, advisory coverage, unreachable enrich.*

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
| R1-S1 | Merge-into-existing for manifest + quality | CRP R1 | WP-B0.5 + FR-B3a; before WP-B1 branch | 2026-07-28 |
| R1-S2 | Post-loop run/skip/merge disposition table | CRP R1 | §2 Mode rule table | 2026-07-28 |
| R1-S3 | Split shrink into 4 steps | CRP R1 | WP-B2 rewritten | 2026-07-28 |
| R1-S4 | Refuse coverage gates + skip kaizen in map mode | CRP R1 | WP-B0.3 / FR-B9 | 2026-07-28 |
| R1-S5 | CC join drift-canary fixture | CRP R1 | WP-B0.4 | 2026-07-28 |
| R2-S1 | Shrink durability = content hash (not `--check`) | Absorbed from REQ R2 | WP-B2 / AC-G5 | 2026-07-28 |
| R2-F* | Affordance reachability / advisory / applied_no_change | REQ R2 → plan mirror | WP-B1 notes | 2026-07-28 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| — | Re-run full PLAN R2 | orchestrator | R1-S covered plan architecture; R2 unique value was F-prefix already on REQ | 2026-07-28 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-5-thinking-high — 2026-07-28

- **Reviewer**: `claude-opus-5-thinking-high`
- **Date**: 2026-07-28 18:14:37 UTC
- **Scope**: Plan review (S-prefix), grounded against the real substrate at HEAD per Design_Docs #27 — `observability/artifact_generator.py` (`generate_observability_artifacts`, `_write_index`, `_write_quality_report`, `_convert_dashboards_to_grafana_json`, `check_drift`), `artifact_generator_generators.py` (`_ensure_red_coverage`, `generate_runbook`, `_assign_gridpos`), `validators/observability_artifact_checks.py` (`validate_extended_artifact`, OBS-EXT-100/101), `scripts/generate_observability_artifacts.py` (`--dry-run`, `--check`, `_apply_coverage_gate`, `_write_quality_to_kaizen_metrics`), and ContextCore `observability/catalog.py` + `graph/compose_deps.py::normalize_service`. Requirements-side (F-prefix) items and the full answers to all six focus asks live in the REQ file's R1 block.

##### Focus-file asks — plan-side implications

Full answers to A1–A6 are in `REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md` Appendix C, Round R1. The three asks with load-bearing *plan* consequences are restated here.

**A1 — FR-B3a branch correctness: does map mode miss required post-gen steps?**

- **Summary answer:** Yes, and destructively — §2's `apply_affordance_actions` box hides two whole-tree rewriters.
- **Rationale:** `_write_index` and `_write_quality_report` rebuild `observability-manifest.yaml` and `observability-quality.json` entirely from `report.artifacts` and never read the prior files, so §2's "(+ existing quality report for touched artifacts)" is unimplementable as an append. ContextCore's `catalog.load_quality_json` reads exactly that quality file, so a one-service map run would destroy the Phase A input that produced the map. Nine further steps sit outside the `_GENERATORS` loop that WP-B1 step B1.1 proposes to branch around.
- **Assumptions / conditions:** the operator runs map mode against an `output_dir` that already holds a full-generate tree.
- **Suggested improvements:** add a merge-into-existing work package step before WP-B1 lands (R1-S1) and a run/skip/merge disposition table for every post-loop step (R1-S2); extend §6 Risks with a "map mode truncates the manifest / quality SSOT" row.

**A2 — Shrink heuristics vs `max_lines` (EXT-101) and panel-graph integrity.**

- **Summary answer:** WP-B2's signature is under-specified on all three axes — budget source, measurement layer, and graph integrity.
- **Rationale:** EXT-101 is scored by `validate_extended_artifact` on the **rendered Grafana JSON**, OBS-200a by `validate_dashboard` on the **spec**, and `max_lines` lives only in `expected_output_contracts.dashboard`. `shrink_dashboard_lines(dashboard, max_lines, preserve_red=True)` as written does not say which artifact `dashboard` is, where `max_lines` comes from, or how the budget is re-measured after a drop.
- **Assumptions / conditions:** the jsonnet render stays optional, so the JSON may be absent (`status="skipped"`).
- **Suggested improvements:** see R1-S3 — split B2.1 into contract-resolution, spec-layer drop, re-render-and-re-measure, and graph-integrity steps.

**A5 — Interaction with `--observability-yaml` domain extras / declared-lane generators.**

- **Summary answer:** The question does not typecheck as posed: those artifacts are project-scoped, not per-service.
- **Rationale:** `render_domain_alert_rules` / `render_domain_dashboard` (and the criticality dashboard, collector enrichment, capability index) emit one artifact per project; the per-service declared-lane SLO generators are reachable from no `gen.*` id. "Touched services only" has no meaning for the former, and skipping the latter silently narrows a regenerated service to the convention triplet.
- **Assumptions / conditions:** none.
- **Suggested improvements:** see R1-S2 — the disposition table must cover project-scope and declared-lane generators explicitly, not by omission.

##### Executive summary

- WP-B1 step B1.1's "branch to `apply_affordance_actions` instead of full `_GENERATORS` loop" is necessary but not sufficient: the destructive surface is the post-loop writers, not the loop.
- §2's architecture diagram stops at `affordance_actions.json` and omits nine real post-loop steps, so the plan cannot yet be implemented without inventing their map-mode semantics at the keyboard.
- The opt-in coverage gate and the kaizen-metrics writer are second-order casualties of a partial quality report — neither appears in §4 or §6.
- WP-B2 shrink needs four steps, not one, because the budget and the RED guard live at different layers.
- WP-B0.4's "normalize join cases" test cannot detect ContextCore changing `normalize_service` — the drift the plan's own §6 risk row names.
- Sequencing in §8 is sound (loader before apply before shrink before glue); the gaps are in step content, not order.
- The `--dry-run` reuse decision holds up against the substrate: `main()` already prints a per-artifact plan under `--dry-run`, so a plan print is a natural extension rather than a new surface.
- No untriaged prior items exist (Appendix C was empty in both documents), so no endorsements or disagreements are possible at R1.

##### Plan Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Ops | critical | Add an explicit **merge-into-existing** work package step: in map mode, read the prior `observability-manifest.yaml` and `observability-quality.json`, splice in only the touched services, and preserve every other service's rows byte-for-byte. Land it before WP-B1 enables the branch. | §2 shows "(+ existing quality report for touched artifacts)" and WP-B1 step B1.1 branches around the loop, but `_write_index` and `_write_quality_report` rebuild both files wholly from `report.artifacts` and never read the prior file. A one-service map run therefore truncates the manifest and the quality JSON that ContextCore's `catalog.load_quality_json` reads — destroying the Phase A input that produced the map. | New step in WP-B0 (or a WP-B0.5) plus a corrected §2 diagram note; add a §6 Risks row. | Golden test: full generate over 3 services, then a map run touching 1; assert the other 2 services' entries are byte-identical in both `observability-manifest.yaml` and `observability-quality.json`, and that a subsequent no-map `--check` reports no drift. |
| R1-S2 | Architecture | high | Add a run / skip / **merge** disposition table covering every post-loop step in `generate_observability_artifacts`: `_convert_dashboards_to_grafana_json`, `generate_business_criticality_dashboard`, `_generate_portal_artifact`, `render_domain_alert_rules` + `render_domain_dashboard`, `generate_collector_enrichment`, `generate_capability_index`, `_record_unimplemented_artifact_types`, `_score_extended_artifacts`, `_apply_orientation_scoring`, and the `report.route_states` / `fr_coverage` / `services_processed` accumulators. | §2's "Mode rule (FR-B3a)" and §4's file touch list treat the branch as loop-vs-loop, but the project-scope generators are keyed by `project_id` (not service), so "touched services only" is not expressible for them; and the per-service declared-lane generators (`generate_declared_base_slos`, `_functional_slos`, `_span_slos`, `_probe_specs`, `generate_functional_slos`) are reachable from no `gen.*` id, so a regenerated service would silently lose its declared SLO lanes. | §2 "Mode rule (FR-B3a)", expanded into a table; mirror the row set in §5 Traceability. | Test that a map run producing one dashboard leaves project-scope artifacts on disk unmodified and still represented in the merged index; test that a `gen.complete_triplet` action regenerates the declared-lane SLOs for that service, not just the convention triplet. |
| R1-S3 | Validation | high | Split WP-B2 step B2.1 into four steps: resolve `max_lines` from `metadata["expected_output_contracts"]["dashboard"]`, drop panels at the **spec** layer, re-render and re-measure the Grafana JSON against the budget (iterating), and assert graph integrity after each drop. | B2.1's `shrink_dashboard_lines(dashboard, max_lines, preserve_red=True)` does not say which artifact `dashboard` is or where the budget comes from. EXT-101 counts lines on the **rendered JSON** while OBS-200a checks the **spec**, so a single-layer implementation either cannot measure the budget or is reverted by the next generate. `_assign_gridpos` only `setdefault`s at generation time, so a JSON-layer deletion leaves a hole in the grid rather than re-flowing it. | WP-B2 step table (replace B2.1, keep B2.2 as the RED-priority rule); add a §4 note that the shrink target is the spec, not the rendered JSON. | Post-shrink assertions: rendered JSON parses, is at or under `max_lines`, panel `id`s unique, `targets[]` intact, no `gridPos` y-gaps, RED panels present, OBS-200a passing; plus an explicit refusal recorded when the render is unavailable. |
| R1-S4 | Risks | high | Refuse (or explicitly bypass with a printed notice) `--min-metric-coverage` and `--min-artifact-type-coverage` when `--affordance-map` is present, and skip the kaizen-metrics write in map mode. | `_apply_coverage_gate` reads `avg_metric_coverage_score` from `observability-quality.json` and `artifact_type_coverage` from the manifest; `_write_quality_to_kaizen_metrics` writes an `observability_artifacts` section from the scored set. In map mode those denominators cover only touched services, so a targeted repair could **pass** a gate the full tree fails — the same class of hazard NR-G8 already fences for `--check`, left open for the gates. | New WP-B0.3 sub-step alongside the `--check` refusal; new §6 Risks row ("partial quality report distorts coverage gate"). | CLI test: map plus `--min-metric-coverage 0.9` exits with the documented refusal (or prints the bypass notice and does not evaluate the gate); assert `kaizen-metrics.json` is unchanged after a map run. |
| R1-S5 | Interfaces | medium | Add a ContextCore **drift-canary** step to WP-B0.4: freeze CC's HEAD join behavior as a fixture table (`PRODUCT_CATALOG` and `PRODUCT_CATALOG_SERVICE` both to `productcatalogservice`, `store` to `store`) with a source comment naming `contextcore/graph/compose_deps.py::normalize_service` and `observability/catalog.py::catalog_service_id`, plus an opt-in test that compares against the real CC implementation only when ContextCore is importable in the test environment. | WP-B0.4's "normalize join cases" test pins the local mirror against itself, so it cannot detect the drift §6's own "Service id mismatch (CC catalog vs slug)" row is about. The canary keeps AC-G7's grep gate intact because the import lives in tests, never in the observability package. | WP-B0.4 step list; reference it from the §6 Risks mitigation cell. | Fixture-table test always runs; the CC-comparison test skips cleanly when ContextCore is absent and fails loudly when the two normalizers diverge. Confirm `grep -r "import contextcore" src/startd8/observability/` stays empty. |

##### Endorsements & Disagreements

Appendix C contained no prior rounds in either document at R1, so there are no untriaged items to endorse or dispute.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each REQ section / FR-ID to the plan work package that implements it, per `REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md` v0.3.2 and this plan v0.3.2.

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| §0 Planning Insights / §0.1 Lessons hardening | §1 Goal, §7 Out of scope | Covered | — |
| §0.2 Design-Principle hardening | §2 Architecture, §6 Risks | Partial | Mieruka (`affordance_actions.json`) and Anzen (RED preservation) are covered; Context-Correctness-by-Construction is not — the plan has no step for the malformed / truncated / stale-input boundary checks (R1-F3, R1-S1). |
| §0.3 Architect Validation | §2 Mode rule, WP-B0.3 | Covered | — |
| FR-B0 (placement, no CC import) | All WPs as constraints; §4 file touch list | Covered | — |
| FR-B1 (optional map input, both shapes) | WP-B0.1, B0.2, B0.3 | Partial | No step detects a history-**truncated** map (CC caps at 15 rows); malformed-map exit code is not pinned to a step (R1-F2, R1-F3). |
| FR-B2 (deterministic planner, priority order) | WP-B0.1, B2.3 | Covered | — |
| FR-B2a (dry-run reuse) | WP-B0.3, B0.4 | Covered | — |
| FR-B2b (typed `ActionPlanEntry`) | WP-B0.1 | Partial | Field list does not yet carry the per-leg decision for `gen.complete_triplet` or the resolved skip taxonomy (R1-F4). |
| FR-B3 (targeted repair default) | WP-B1.1–B1.4 | Partial | `gen.complete_triplet`'s "missing or zero-score leg" input is unnamed; no plan step loads `observability-quality.json` (R1-F4). |
| FR-B3a (map mode replaces full loop) | WP-B1.1; §2 Mode rule | **Gap** | The branch is planned, but the nine post-loop steps and the two whole-tree writers are not — the load-bearing omission (R1-S1, R1-S2). |
| FR-B4 (shrink without RED regression) | WP-B2.1–B2.4 | Partial | Shrink layer, budget source, re-measurement loop, and panel-graph integrity are unspecified; no durability check against `--check` (R1-F5, R1-S3). |
| FR-B5 (runbook marker parity, always-on) | WP-B1.5 | Covered | Substrate confirms the defect: `generate_runbook` emits `## Service summary` / `## First response`, and only `## Escalation` overlaps the scored markers. |
| FR-B6 (fail closed on ambiguity) | WP-B0.1 skip reasons, B0.4 | Partial | Skip-with-reason is planned, but "all rows skipped" has no distinct outcome, so a total join failure reads as success (R1-F2). |
| FR-B6a (service-id join rule) | WP-B0.1 `normalize_element_id`, B0.4, B0.5 | **Gap** | The mirrored algorithm omits CC's `service`-suffix injection and there is no match ladder, so ENV_FORM ids cannot join slug-shaped `ServiceHints` (R1-F1, R1-S5). |
| FR-B7 (provenance / action report) | WP-B3.1, B3.2 | Partial | Sidecar is planned; source provenance / truncation and `all_skipped` fields are not (R1-F2, R1-F3). |
| FR-B8 (`--services` intersect) | WP-B0.3 (implied) | Partial | No explicit step or test for the intersection and its empty-intersection no-op. |
| NR-G1, NR-G5, NR-G6, NR-G9 | §7 Out of scope; §4 | Covered | — |
| NR-G2, NR-G3, NR-G7 | §2 Mode rule, §6 Risks | Covered | — |
| NR-G4 | §7 Out of scope | Covered | — |
| NR-G8 (`--check` plus map refused) | WP-B0.3 | Covered | Note: the analogous coverage-gate combination is left open (R1-S4). |
| §4 Acceptance Criteria AC-G1 | WP-B1.5 (fixtures in same WP) | Covered | — |
| AC-G2 | WP-B0 exit criterion | Covered | — |
| AC-G3 | WP-B1.6 | Partial | Test asserts only that one dashboard path is touched; it does not assert the manifest / quality JSON preserve untouched services (R1-S1). |
| AC-G4 | WP-B1.5 | Covered | — |
| AC-G5 | WP-B2.4 | Partial | No durability or graph-integrity assertion; budget layer unresolved (R1-S3). |
| AC-G6 | WP-B3.2 | Partial | Conflates empty map with total-skip; no distinct exit code (R1-F2). |
| AC-G7 | WP-B0.4 | Covered | — |
| AC-G8 | WP-B0.2, B0.4 | Covered | — |
| AC-G9 | WP-B0.3 | Covered | — |
| §5 Open Questions (OQ-G5/G6/G7) | §2, WP-B0.1, B3.1 | Covered | — |
| §6 Phasing (B0 → B3) | §8 Implementation order | Covered | — |
| §7 Reference Audit | §4 File touch list | Covered | Re-verified at HEAD: `_ensure_red_coverage`, `_GENERATORS`, `generate_runbook`, `_write_quality_report`, OBS-EXT-100/101 exist; `shrink_dashboard_lines` and the map loader do not. |
