# Observability Artifact Taxonomy — Implementation Plan

**Date:** 2026-05-31
**Status:** Plan v0.1 (paired with `OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md` v0.3)
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

**Validation:** full observability + validator + dashboard_creator suites green, byte-identical
artifact output on a fixture run (these are refactors).

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

**Removes:** D-1, D-5. **Enforces:** REQ-OAT-070 (new type = one table row).
**Risk:** per-service vs per-project scope must be explicit in the table (resolved: cat 1
per-service; cat 2/3 per-project). **Validation:** same artifacts produced as before; suites green.

---

## Phase 3 — Naming / ownership (REQ-OAT-010/011/012/013, 021)

| Step | Change | Files |
|------|--------|-------|
| 3.1 | Rename `generate_capability_index` → `generate_observability_inventory`; type `capability_index` → `observability_inventory`; output `observability-inventory.yaml`; update `_IMPLEMENTED_ARTIFACT_TYPES`, exclusion set, docstring | artifact_generator.py + tests |
| 3.2 | **Revert the Finding-2 masquerade** (REQ-OAT-013): reshape the body from the `manifest_id/version/capabilities[]` software-feature schema to a category-nested **inventory** (services + per-category artifact paths/counts) | artifact_generator.py + tests |
| 3.3 | `capability_index` becomes a category-aware honest skip owned by onboarding (REQ-OAT-011/052) | artifact_generator.py |
| 3.4 | Split `portal` → `onboarding_portal` + `role_dashboard` (REQ-OAT-021); update the dispatch table + persona handling | artifact_generator.py, portal_spec_builder.py + tests |

**Validation:** no artifact named `capability_index` produced by observability; `observability-inventory.yaml`
validates as an inventory; the run-007 Finding-2 test is replaced by an inventory-schema test.

---

## Phase 4 — Orientation-aware validation + 3-way coverage (REQ-OAT-050/051/060/061/062; D-3)

Built on the Phase-0.3 check-runner, so the orientation branch is small.

| Step | Change | Files |
|------|--------|-------|
| 4.1 | Add `orientation` param to the validators; add the **bridge actionability** check (alert/loki: runbook/dashboard link + summary; notification_policy: non-null receiver/route) | checks.py |
| 4.2 | Split a `prometheus_rule`/`loki_rule` file into recording (system) vs alerting (bridge) subsets; score each; record the breakdown (REQ-OAT-062) | checks.py |
| 4.3 | Generalize coverage from 2 buckets to 3 orientations: `metric_coverage_human/system/bridge` (collect SLO/recording content as the system bucket); keep `…_dashboarded/_alerted` as aliases; 3-way composite blend; **service/project/agent only**, not pipeline-innate (REQ-OAT-051) | artifact_generator.py |
| 4.4 | Demote `dashboard_spec` to `status="intermediate"` so it is not written/scored as an end artifact (D-3); declare only `dashboard` (JSON) | artifact_generator.py + tests |

**Validation:** a valid-but-unactionable alert scores partial; a recording+alerting `prometheus_rule`
shows a 2-part breakdown; `metric_coverage_{human,system,bridge}` present; `artifacts_scored ==
artifacts_generated` still holds (Finding-1 invariant) with `dashboard_spec` no longer counted.

---

## Phase 5 — Metadata declare-don't-guess + routing + generation_report (REQ-OAT-020/022/024/040/041/030/031a; D-7, D-11)

| Step | Change | Files |
|------|--------|-------|
| 5.1 | `_declared_artifact_types` reads nested `artifact_categories` first, flat `artifact_types` as fallback; add `_flatten_artifact_categories` (REQ-OAT-020/022) | artifact_generator.py |
| 5.2 | Read declared **entry kind** (collapse `_is_non_service_entry` 7 heuristics → 1 check, name-pattern as recorded fallback) (REQ-OAT-024; D-7) | artifact_generator.py |
| 5.3 | Read declared **metric category/orientation**; route domain metrics to cat 4/5 surfaces (or record as "awaiting home"); heuristic fallback recorded as *inferred* (REQ-OAT-024/040/041) | artifact_generator.py |
| 5.4 | Once metric routing lands, **remove** the `_domain_alert_todo_block` stub machinery (D-11) | artifact_generator.py + tests |
| 5.5 | Emit `generation_report` (category-nested, per-artifact `{type, category, orientation, service, output_path, status, source_checksum}`) + link to `run-provenance.json` (REQ-OAT-030/031a) | artifact_generator.py |

**Validation:** nested + flat metadata both parse; a non-service entry with `kind` declared is
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
- [ ] REQ-OAT-070 invariant holds after Phase 2 (new type = one table row, no new branch).

---

*Plan v0.1 — paired with requirements v0.3. Six phases; Phases 0–2 are distillation (remove
accidental complexity), 3–5 are the category/orientation features, 6 is the deferred cross-repo
consumer. Net line delta expected negative.*
