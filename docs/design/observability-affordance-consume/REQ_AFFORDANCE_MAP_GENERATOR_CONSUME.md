# Affordance-Map Consume (startd8 Generator) — Requirements

**Version:** 0.4 (Post CRP R1+R2 triage — implementable)  
**Date:** 2026-07-28  
**Status:** Ready to implement (CRP triaged; PLAN R2 not re-run — R1-S + R2-F sufficient)  
**Owner:** startd8 observability / ContextCore audit consumers  
**Plan:** [`PLAN_AFFORDANCE_MAP_GENERATOR_CONSUME.md`](PLAN_AFFORDANCE_MAP_GENERATOR_CONSUME.md)  
**Parent:** ContextCore [`REQ_O11Y_AUDIT_CATALOG_REPORT_CARD.md`](../../../../ContextCore/docs/design/requirements/REQ_O11Y_AUDIT_CATALOG_REPORT_CARD.md) Phase B (`gen.*` only)  
**Audience:** startd8 `artifact_generator` maintainers, SIL-REX measure operators  
**CRP focus:** [`.crp-focus.md`](.crp-focus.md) · prompt `crp-sdk-affordance-map-consume_20260728T181140Z.md`

**Related code:**
- startd8: `src/startd8/observability/artifact_generator.py`, `artifact_generator_generators.py`, `observability_artifact_checks.py`, `scripts/generate_observability_artifacts.py`
- ContextCore emit: `src/contextcore/observability/catalog.py` (`AFFORDANCE_BY_GAP`, `affordance_map`, `catalog_service_id`); join via `graph/compose_deps.normalize_service`
- Quality / contracts: `observability-quality.json`, onboarding `expected_output_contracts` (runbook markers: Overview / Risks / Escalation / Procedures)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between the Phase-B stub in the parent REQ and this grounded draft (planning pass against the generator).

| Pre-plan Assumption | Planning Discovery | Impact |
|---------------------|-------------------|--------|
| Generator needs new synthesizers for each `gen.*` | RED (`_ensure_red_coverage`), triplets (`_GENERATORS`), metric-coverage scoring, runbook generation, EXT-101 **checks** already exist | FR-B = **bias + selective regen + one new shrink pass**; do not fork scorers |
| AffordanceMap might be imported from ContextCore | startd8 observability has **zero** `import contextcore`; dependency direction must stay CC → startd8 | Consume **plain JSON** only; frozen schema in startd8 tests |
| Full regen on map is fine | Thanos multi-service trees + drift/`--check` make full regen destructive | **FR-B3 targeted repair** default; dry-run required |
| `gen.shrink_dashboard_lines` is like the others | EXT-101 is **check-only** (`max_lines`); no shrink writer | FR-B4 is the only net-new generator capability |
| `gen.enrich_runbook` = thicker prose | Generator headings ≠ contract markers (`Overview`/`Risks`/`Procedures`) | Enrich = **marker parity**; after FR-B5 the affordance is schema-fidelity only (unreachable from EXT-100) |
| `gen.complete_triplet` = regenerate all three legs | Triplets already unconditional; incompleteness = missing/zero-score leg | Selective leg regen; signal = quality JSON |
| Metric coverage needs a new emitter | Human/dashboard lane already maximal by construction | `gen.improve_metric_coverage` = **advisory / no-op** unless authored observability.yaml alert path (deferred) |
| Parent FR-AFF-3 is enough as a REQ | Too thin to implement; needs startd8-owned FRs | This sibling REQ owns Phase B `gen.*` |

**Resolved open questions (planning):**
- **OQ-G1 →** Load AffordanceMap via `--affordance-map PATH` (scorecard-json extract or `affordance_map` array); default off.
- **OQ-G2 →** Targeted per-`(service, affordance)` repair; never full-tree rewrite by default.
- **OQ-G3 →** Shrink must not drop RED below OBS-200a (≥2/3 Rate/Errors/Duration).
- **OQ-G4 →** `rex.*` / `measure.*` out of scope (ContextCore / SIL-REX sibling later).

---

### 0.1 Lessons-Learned Hardening (v0.3 → corrected v0.3.2)

> Applied `~/Documents/craft/Lessons_Learned/{sdk,observability}/` — see prior revision for full list. Key IDs: Design_Docs #12/#15/#24/#27, Obs #32.

---

### 0.2 Design-Principle Hardening (v0.3.1 → v0.3.2)

> Mottainai, Warm Up, Genchi Genbutsu, Accidental-Complexity, Context-Correctness-by-Construction, Hitsuzen, Keiyaku, Hayai-over-Sotto (FR-B5), Anzen, Mieruka — see prior revision.

---

### 0.3 Architect Validation (v0.3.2)

> Map mode replaces full loop; reuse `--dry-run`; refuse `--check`+map; FR-B6a join; FR-B8 intersect; CRP recommended. Superseded where CRP corrected (join algorithm, merge writers, affordance reachability).

---

### 0.4 CRP Insights (v0.4)

> Dual-document CRP R1 + REQ R2 (adversarial). PLAN R2 **not re-run**: R1-S already covered plan architecture; R2 unique value was F-prefix reachability. R2-S1 (content-hash durability) absorbed into R1-F5.

| Finding | Disposition |
|---------|-------------|
| Map mode truncates `_write_index` / `_write_quality_report` | **ACCEPT** → FR-B3a merge-into-existing |
| FR-B6a omitted `service` suffix + match ladder | **ACCEPT** → FR-B6a verbatim |
| All-skip exit 0 hides total join failure | **ACCEPT** → exit table |
| Truncated history map (cap 15) silent | **ACCEPT** → FR-B1 warn/stamp |
| Triplet leg signal unnamed | **ACCEPT** → quality JSON + ActionPlanEntry |
| Shrink layer / EXT-101 vs OBS-200a | **ACCEPT** → spec shrink + re-render; durability = content hash |
| `gen.improve_metric_coverage` no dashboard lever | **ACCEPT** → advisory skip |
| `gen.enrich_runbook` unreachable after FR-B5 | **ACCEPT** → annotate |
| `applied` vs no-op RED | **ACCEPT** → `applied_no_change` |
| `--min-affordance-confidence` phantom | **ACCEPT** → drop flag |

---

## 1. Problem Statement

ContextCore Observability Audit Phase A emits an **AffordanceMap** (`gen.*` + `rex.*` + `measure.*`) from quality/reconcile/live gaps. Operators still must **manually** decide which generator actions to run. The startd8 generator already implements most `gen.*` behaviors but never reads the map — so gaps like RED-missing, skeletal runbooks, empty metric-coverage, and oversized dashboards persist after regenerate.

| Component | Current state | Gap |
|-----------|---------------|-----|
| CC `affordance_map` | Emitted in scorecard-json | Not consumed downstream |
| `_ensure_red_coverage` | Runs on generate for request-shaped services | No bias from `red_missing` map entries |
| Triplet generators | Unconditional per service | No selective leg repair from `triplet_incomplete` |
| Metric coverage | Scored + gated; domain panels exist | Human lane maximal; map affordance is advisory |
| Runbooks | Generated + EXT-100 scored | Heading mismatch → false “skeletal”; FR-B5 closes markers |
| Dashboard `max_lines` | EXT-101 **check only** | No `gen.shrink_dashboard_lines` writer |
| Generator CLI | `--onboarding-metadata`, coverage mins, … | No `--affordance-map` |
| Post-gen writers | Full-tree rebuild | Map mode must **merge** or it truncates quality SSOT |

**One-sentence goal:** given an AffordanceMap JSON from a ContextCore audit, the startd8 generator **optionally** performs **targeted** `gen.*` repairs for listed services — reusing existing synthesizers, merging index/quality for untouched services — without importing ContextCore or rewriting the whole tree.

---

## 2. Definitions

| Term | Meaning |
|------|---------|
| **AffordanceMap** | JSON list of `{element_id, gap_code, affordance_ids[], confidence?, provenance?, unmapped_reason?}` as emitted by CC Phase A (or equivalent `gaps[]` with `affordance_ids`). |
| **`gen.*` affordance** | Generator-owned action id from parent FR-AFF-1. |
| **Targeted repair** | Regenerate or patch only the `(service_id, artifact_type)` pairs implied by selected affordances. |
| **Action plan** | Deterministic ordered list of typed `ActionPlanEntry` derived from the map. |
| **Known gen set** | Frozen: `gen.emit_red_panels` (live), `gen.complete_triplet` (live), `gen.improve_metric_coverage` (**advisory** — no deterministic dashboard lever at HEAD), `gen.enrich_runbook` (**schema fidelity** — unreachable from EXT-100 after FR-B5), `gen.shrink_dashboard_lines` (live, net-new). |
| **Merge-into-existing** | In map mode, splice touched services into prior `observability-manifest.yaml` / `observability-quality.json`; preserve all other service rows byte-for-byte. |

---

## 3. Requirements

### Placement

**FR-B0 — Sibling of Phase A; startd8-owned.**  
This REQ implements parent FR-AFF-3 for **`gen.*` only**. It MUST NOT move AffordanceMap emit into startd8, MUST NOT import `contextcore`, and MUST NOT consume `rex.*` / `measure.*` (defer).

### Load + schema

**FR-B1 — Optional AffordanceMap input.**  
`generate_observability_artifacts` (and `scripts/generate_observability_artifacts.py`) MUST accept optional `--affordance-map PATH` (or kwarg). Accepted shapes:
1. Raw array = `affordance_map` entries, or  
2. Scorecard-json object containing `affordance_map` (and optionally `gaps`).  

Default: **absent → ordinary full generate** (plus intentional FR-B5 runbook heading alignment). Unknown keys ignored. Unknown affordance ids logged and skipped (not invented).

**Exit codes (normative):**

| Condition | Exit |
|-----------|------|
| Malformed / unreadable map | **2** |
| Non-empty map, ≥1 action `applied` or `applied_no_change` | **0** |
| Non-empty map, **all** rows skipped | **3** + `all_skipped: true` in sidecar |
| Genuinely empty map, or empty `--services` ∩ map | **0** (no-op log) |

If the scorecard carries `history.trimmed` / map length hits the known history cap while `gaps` is longer, the loader MUST warn and stamp `source_truncated: true` on the sidecar (refuse is allowed; silent success is not).

Fail-closed / join rules: **FR-B6 / FR-B6a**.

### Planner

**FR-B2 — Deterministic action planner.**  
From the map, produce an ordered **action plan** of repairs. Rules:
- Only `gen.*` ids in the known gen set.
- Index by `element_id` after **FR-B6a** normalization + match ladder.
- Deduplicate identical `(service, affordance)` pairs.
- Stable sort: by affordance priority (below) then service name.
- Advisory / unreachable affordances still appear in the plan as `skipped` with explicit reasons (do not invent repair branches).

**Default priority (tunable constants):**  
`emit_red_panels` → `complete_triplet` → `improve_metric_coverage` → `enrich_runbook` → `shrink_dashboard_lines`  
(RED/triplet before shrink so shrink cannot erase newly added RED panels in the same plan — see FR-B4 ordering.)

**FR-B2a — Dry-run (reuse existing flag).**  
When `--affordance-map` is present and `--dry-run` is set, print the action plan (including per-leg decisions and skip reasons) and write **zero** artifact files. Do **not** add a second dry-run CLI verb.

**FR-B2b — Typed plan contract (Keiyaku).**  
`ActionPlanEntry` MUST be a typed dataclass (or Pydantic model) with at least: `service_id`, `affordance_id`, `artifact_types: list[str]`, `reason`, `gap_code?`, `confidence?`, `legs?` (for triplet: which legs selected), `outcome?` (`planned` | `applied` | `applied_no_change` | `skipped`). Load/plan/apply boundaries pass these types — not ad-hoc dicts.

### Targeted execute

**FR-B3 — Targeted repair default.**  
When a map is present and dry-run is off, the generator MUST apply only planned live actions. It MUST NOT rewrite artifacts for services with no matching live `gen.*` entries. Full-tree regenerate remains available via existing entry points **without** a map (unchanged).

**FR-B3a — Map mode replaces full loop + merge writers.**  
When `--affordance-map` is present:
1. Do **not** run the unconditional per-service `_GENERATORS` full-tree pass.
2. Apply planned actions for matched services only.
3. **Merge-into-existing** for `observability-manifest.yaml` and `observability-quality.json` — untouched services’ rows MUST remain byte-identical.
4. Project-scope generators (domain alert/dashboard, criticality dashboard, collector enrichment, capability index, portal) do **not** re-run; their on-disk artifacts and merged index rows MUST survive.
5. Declared-lane per-service SLO generators run only as part of `gen.complete_triplet` for a touched service (so an SLO leg is not silently narrowed to the convention triplet).
6. Grafana JSON conversion runs for touched dashboards when the toolchain is available (required for FR-B4 re-measure).

| Affordance | Required behavior |
|------------|-------------------|
| `gen.emit_red_panels` | Ensure `_ensure_red_coverage` for that service’s dashboard; regenerate dashboard only if needed. If kinds imply neither throughput nor availability, record **`applied_no_change`** (not `applied`). |
| `gen.complete_triplet` | Authoritative leg signal = `{output_dir}/observability/observability-quality.json` → `services.{svc}.{artifact_type}.score` for `alert_rule` / `dashboard_spec` / `slo_definition` (absent key = missing; `0.0` = zero-score). Regenerate those legs only. If quality JSON absent/stale → regenerate **all three** with `reason="leg_signal_unavailable"`. Surface per-leg selection on `ActionPlanEntry`. Declared-lane SLOs regenerate with the SLO leg. |
| `gen.improve_metric_coverage` | **Advisory.** At HEAD, dashboard regen is byte-identical for the human coverage lane. Record `skipped` with `reason="no_deterministic_lever"` (or `applied_no_change` if a no-op regen is attempted). Do **not** claim dashboard repair. Bridging via authored `observability.yaml` alerts is out of map-mode scope (project-scope; see FR-B3a). |
| `gen.enrich_runbook` | **Schema fidelity.** After FR-B5, EXT-100 cannot emit `runbook_skeletal`; if the id appears, `skipped` with `reason="unreachable_after_fr_b5"`. No dedicated repair branch required. |
| `gen.shrink_dashboard_lines` | Apply FR-B4 shrink to that service’s **dashboard spec**, then re-render/re-measure Grafana JSON. |

**FR-B5 — Runbook marker parity (always-on).**  
Align `generate_runbook` headings with scored markers (`Overview`, `Risks`, `Procedures`, `Escalation`). Map `Service summary`→`Overview`, `First response`→`Procedures`; keep `Escalation`. For **`## Risks`**, emit at least one non-heading line derived deterministically from available coverage/criticality signals (`fr_coverage` gaps, criticality, availability) — not a bare heading (Obs #32 / R2-F3). Marker presence clears EXT-100; it does **not** by itself assert runbook operational quality.

**FR-B4 — Shrink without RED regression.**  
- Resolve `max_lines` from `expected_output_contracts.dashboard`.
- Drop/condense panels at the **dashboard_spec** layer (prefer non-RED / duplicates / verbose options).
- Re-render Grafana JSON and re-measure line count iteratively until ≤ `max_lines` or refuse.
- After shrink, OBS-200a MUST still pass for request-shaped services that had RED completeness before the shrink (or refuse with reason).
- Panel-graph integrity: unique panel `id`, intact `targets[]`, `gridPos` re-flowed (no holes).
- If Grafana render is unavailable → **refuse** the shrink action with reason (not silent pass).
- Durability: record pre/post **content hashes** of the spec (and rendered JSON when present) in the sidecar — do **not** rely on `--check` (it does not compare dashboard content).
- Shrink runs **after** RED/triplet actions in the same plan (FR-B2 priority).
- Generator-owned dashboards only (NR-G9).

**FR-B6 — Fail closed on ambiguity.**  
If `element_id` does not match a known service after FR-B6a, skip with explicit reason (do not invent services). Forward upstream `unmapped_reason` into skip records when present. Do **not** expose `--min-affordance-confidence` (phantom knob; confidence is 0.0/1.0 with empty ids).

**FR-B6a — Service-id join rule (verbatim).**  
Local helper (no `import contextcore`). For ENV_FORM ids (`^[A-Z][A-Z0-9_]*(?:_SERVICE)?$`):
1. Strip trailing `_SERVICE`
2. Delete underscores
3. Lowercase
4. If the slug does **not** already end with `service`, append `service`  
   (`PRODUCT_CATALOG` → `productcatalogservice`; `PRODUCT_CATALOG_SERVICE` → same.)

Otherwise: lowercase the id.

**Match ladder** before declaring unknown: (1) exact match to `ServiceHints.service_id`, (2) normalized form equals a hint id, (3) `(?:service)?$`-insensitive equivalence between normalized id and each hint id. Document with a worked join table in HOWTO.

**FR-B7 — Provenance / report.**  
Emit `{output_dir}/affordance_actions.json` with planned / applied / **`applied_no_change`** / skipped (reasons), pre/post content hashes for touched artifacts, `all_skipped`, `source_truncated?`, and echoed `unmapped_reason` when present. Mottainai: do not re-emit a second quality scorer — existing `_write_quality_report` remains the quality SSOT (after merge).

**FR-B8 — Optional `--services` intersect.**  
If a service filter and a map are both present, effective targets = **intersection**. Empty → no-op + log; exit 0.

**FR-B9 — Coverage gates in map mode.**  
Refuse (or bypass with printed notice and **do not evaluate**) `--min-metric-coverage` / `--min-artifact-type-coverage` when a map is present. Skip kaizen-metrics overwrite from a partial quality report in map mode.

### Non-Requirements

- **NR-G1** — Does NOT `import contextcore` or call the Observability Audit from the generator.
- **NR-G2** — Does NOT re-derive AffordanceMap from `observability-quality.json` when a map file is provided (map is the worklist). Quality JSON MAY be read as the **triplet leg signal** only (FR-B3).
- **NR-G3** — Does NOT use an LLM to choose or author repairs.
- **NR-G4** — Does NOT consume `rex.*` or `measure.*` affordances.
- **NR-G5** — Does NOT change Phase A emit schema or rename `gen.*` ids (unreachable ids remain in the frozen set).
- **NR-G6** — Does NOT make AffordanceMap mandatory for ordinary generate.
- **NR-G7** — Does NOT silently full-regenerate the tree because a map was passed.
- **NR-G8** — Does NOT combine `--check` with `--affordance-map` (refuse with clear error).
- **NR-G9** — Does NOT build an authored-panel merge layer for shrink; generator-owned dashboards only.
- **NR-G10** — Does NOT treat `gen.improve_metric_coverage` as a live dashboard repair at HEAD.

---

## 4. Acceptance Criteria

| ID | Criterion |
|----|-----------|
| **AC-G1** | Without map: ordinary full generate + FR-B5 runbook alignment only (fixtures updated). |
| **AC-G2** | `--dry-run` + map prints plan (incl. legs/skips) and creates no artifact diffs. |
| **AC-G3** | Map with only `store` + `gen.emit_red_panels` touches store dashboard; other services’ manifest + quality rows byte-identical. |
| **AC-G4** | FR-B5 runbook contains Overview/Risks/Procedures/Escalation; Risks has ≥1 non-heading line; EXT-100 marker issues clear. Not a claim of operational runbook quality. |
| **AC-G5** | Shrink: rendered JSON ≤ `max_lines` **or** refuse (incl. no-render); OBS-200a preserved when applied; sidecar hashes show change; panel graph intact. |
| **AC-G6** | Exit table in FR-B1 honored (malformed→2, all-skip→3, empty→0). |
| **AC-G7** | No `contextcore` import in startd8 observability package (grep gate). |
| **AC-G8** | Frozen CC-shaped `affordance_map` fixture parses; known gen set asserted (incl. advisory/unreachable annotations in tests). |
| **AC-G9** | `--check` + map exits non-zero (NR-G8). |
| **AC-G10** | ENV_FORM map ids produce a non-empty plan against slug-shaped `ServiceHints` via FR-B6a ladder. |
| **AC-G11** | Truncated/history-capped map stamps `source_truncated` (warn or refuse). |
| **AC-G12** | Freshness-only service + `gen.emit_red_panels` → `applied_no_change`, byte-identical dashboard. |

---

## 5. Open Questions

_(None remaining for Phase 6.)_

---

## 6. Phasing

| Phase | Scope | Exit |
|-------|-------|------|
| **B0** | Loader, planner, join ladder, exit codes, CLI, `--check`/coverage-gate refuse, dry-run | AC-G2, G6–G11 |
| **B1** | Merge writers + targeted RED/triplet; FR-B5 headings+Risks; advisory skips | AC-G1, G3, G4, G12 |
| **B2** | Shrink (spec → re-render → hash) | AC-G5 |
| **B3** | Sidecar completeness; HOWTO | AC-G6 fields |

SIL-REX `rex.*` consume = separate REQ.

---

## 7. Reference Audit

| Symbol / check | Exists? | Notes |
|----------------|---------|-------|
| `_ensure_red_coverage` | Yes | Early-return when kinds lack throughput/availability |
| OBS-200a / OBS-EXT-100 / OBS-EXT-101 | Yes | Spec vs rendered-JSON layers differ |
| `_write_index` / `_write_quality_report` | Yes | Full rebuild — must merge in map mode |
| `check_drift` | Yes | Key/transform only; excludes rendered `dashboard` |
| `generate_runbook` | Yes | Heading mismatch vs markers |
| `normalize_service` (CC) | Yes | Suffix rule; mirror locally |
| `HISTORY_AFFORDANCE_CAP` | Yes (CC) | 15 |
| `shrink_dashboard_lines` / AffordanceMap loader | **No** | to-be-created |

---

## Appendix A: Settled Questions (design)

| ID | Resolution |
|----|------------|
| OQ-G1–G7 | As in v0.3.2 + CRP: merge writers, exit table, advisory coverage, unreachable enrich |

## Appendix B: Rejected Suggestions (design)

| Idea | Why rejected |
|------|----------------|
| Import CC catalog module | Reverses dependency direction |
| Full regen when any map entry present | Thanos-scale thrash; NR-G7 |
| LLM enrich runbooks | Violates Hitsuzen |
| Re-derive AffordanceMap from quality when map present | Mottainai; quality may be read for triplet legs only |
| Second dry-run flag | Accidental complexity |
| Hybrid `--check`+map | Refuse (NR-G8) |
| Map-only FR-B5 | Violates Hayai |
| Live dashboard repair for `improve_metric_coverage` | No deterministic lever (R2-F1) |
| `--min-affordance-confidence` | Phantom knob (R2-F5) |
| Durability via `--check` alone | `check_drift` ignores dashboard content (R2-S1) |

## Appendix C: Incoming Suggestions (Untriaged)

_(CRP rounds live under Iterative Review Log Appendix C below — do not duplicate.)_

---

*v0.4 — CRP R1+R2 triaged into normative FRs. PLAN R2 skipped (R1-S sufficient). Ready to implement.*

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
| R1-F1 | Verbatim ENV normalize + match ladder | CRP R1 | Merged into FR-B6a; AC-G10 | 2026-07-28 |
| R1-F2 | Exit-code table; all-skip ≠ success | CRP R1 | Merged into FR-B1 / AC-G6 | 2026-07-28 |
| R1-F3 | Truncated AffordanceMap detect | CRP R1 | Merged into FR-B1; AC-G11 | 2026-07-28 |
| R1-F4 | Triplet leg signal + ActionPlanEntry fields | CRP R1 | Merged into FR-B3 / FR-B2b | 2026-07-28 |
| R1-F5 | Shrink layer + refuse if no render | CRP R1 | Merged into FR-B4 / AC-G5; durability = content hash (R2-S1), not `--check` | 2026-07-28 |
| R2-F1 | `gen.improve_metric_coverage` advisory / no dashboard lever | CRP R2 | Merged into FR-B3 table | 2026-07-28 |
| R2-F2 | `applied_no_change` + pre/post hash | CRP R2 | Merged into FR-B7 / FR-B2b | 2026-07-28 |
| R2-F3 | `## Risks` stub-or-fill from fr_coverage | CRP R2 | Merged into FR-B5 (fill from coverage gaps) | 2026-07-28 |
| R2-F4 | `gen.enrich_runbook` unreachable after FR-B5 | CRP R2 | Annotated in §2 + FR-B5 | 2026-07-28 |
| R2-F5 | Drop `--min-affordance-confidence` | CRP R2 | Removed; echo `unmapped_reason` in FR-B7 | 2026-07-28 |
| R2-S1 | Durability via content hash (not `--check`) | CRP R2 (absorbed; PLAN R2 not re-run) | Applied as R1-F5 validation refinement | 2026-07-28 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| — | Relitigate Hayai FR-B5 always-on | focus | Settled pre-CRP; R2-F3 is residual content risk only | 2026-07-28 |
| — | Import contextcore for join | — | NR-G1; local mirror + canary in tests | 2026-07-28 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-5-thinking-high — 2026-07-28

- **Reviewer**: `claude-opus-5-thinking-high`
- **Date**: 2026-07-28 18:14:37 UTC
- **Scope**: Requirements review (F-prefix), grounded against the real substrate at HEAD per Design_Docs #27 — `observability/artifact_generator.py` (`generate_observability_artifacts`, `_write_index`, `_write_quality_report`, `check_drift`), `artifact_generator_generators.py` (`_ensure_red_coverage`, `generate_runbook`), `validators/observability_artifact_checks.py` (`validate_extended_artifact`, OBS-EXT-100/101), `scripts/generate_observability_artifacts.py`, and ContextCore `observability/catalog.py` + `graph/compose_deps.py::normalize_service`. Plan-side (S-prefix) items live in the PLAN file's R1 block.

##### Focus-file asks (`.crp-focus.md` → "Ask CRP to pressure-test"), answered first

**A1 — FR-B3a branch correctness: does map mode miss required post-gen steps (index write, quality report, portal) that must still run for touched artifacts?**

- **Summary answer:** Yes — materially, and in a *destructive* rather than merely incomplete way.
- **Rationale:** `_write_index` rebuilds `observability-manifest.yaml` and `_write_quality_report` rebuilds `observability-quality.json` **entirely from `report.artifacts`**; neither reads the prior file. A map-mode run whose report holds one service therefore emits an index and quality JSON containing only that service — and ContextCore's `catalog.load_quality_json` reads exactly that file, so map mode would destroy the Phase A input that produced the map. FR-B3a's "Quality report / sidecar still run for what was touched" is only satisfiable if those two writers become merge-into-existing. Beyond them, everything outside the `_GENERATORS` loop is unaddressed: `_convert_dashboards_to_grafana_json`, `generate_business_criticality_dashboard`, `generate_collector_enrichment`, `generate_capability_index`, `_record_unimplemented_artifact_types`, `_score_extended_artifacts`, `_apply_orientation_scoring`, and the `report.route_states` / `report.fr_coverage` / `services_processed` accumulators.
- **Assumptions / conditions:** `output_dir` already holds a prior full-generate tree (the operator flow the HOWTO implies). On a virgin directory the truncation is harmless, but then the index is legitimately partial and should say so.
- **Suggested improvements:** Give FR-B3a a normative "post-gen steps under map mode" table with three dispositions — run / skip / **merge**. Add an AC: a map run touching 1 of 3 services leaves the other 2 services' rows byte-identical in **both** `observability-manifest.yaml` and `observability-quality.json`. See R1-S1 / R1-S2 in the PLAN.

**A2 — Shrink heuristics vs contract `max_lines` (EXT-101) and Grafana panel-graph integrity after drops.**

- **Summary answer:** Under-specified, and as written non-durable: the line budget and the RED guard are measured at **different layers**.
- **Rationale:** `validate_extended_artifact` counts `content.count("\n") + 1` against `contract["max_lines"]`, and `_score_extended_artifacts` only scores artifacts whose `quality is None` — so EXT-101 lands on the **rendered Grafana JSON** (`artifact_type="dashboard"`), never on `dashboard_spec` (already scored by `validate_dashboard`). OBS-200a RED, conversely, is a `validate_dashboard` check on the **spec**. FR-B3's "Apply FR-B4 shrink to that service's Grafana JSON" therefore mutates an artifact the next ordinary generate re-renders from the spec — silently reverting the repair, re-arming EXT-101, and showing up as drift under `--check`. Shrinking the spec instead cannot verify the JSON budget without re-rendering, and that render is recorded `status="skipped"` whenever the jsonnet toolchain / startd8-mixin is unavailable.
- **Assumptions / conditions:** `max_lines` continues to be declared only under `expected_output_contracts.dashboard`; the jsonnet render stays optional.
- **Suggested improvements:** FR-B4 must name the shrink **layer** (recommend spec, then re-render and re-measure iteratively), state the refuse-with-reason path when the render is unavailable (not a silent pass), and require panel-graph integrity: unique panel `id`, intact `targets[]`, and `gridPos` re-flow — `_assign_gridpos` only `setdefault`s at generation time, so a JSON-layer deletion leaves a hole in the grid. Add a durability AC: after a shrink action, a subsequent no-map `--check` reports no drift.

**A3 — Local `normalize_element_id` fidelity vs CC `catalog_service_id` (ENV_FORM + `normalize_service`) without importing CC — drift risk.**

- **Summary answer:** No — the FR-B6a prose is not faithful, and the join failure is already realized at HEAD.
- **Rationale:** `catalog_service_id` delegates ENV_FORM ids to `contextcore.graph.compose_deps.normalize_service`, which strips a trailing `_SERVICE`, deletes underscores, lowercases, **and appends `service` when the slug does not already end in it** — `PRODUCT_CATALOG` → `productcatalogservice`. FR-B6a's "apply the same slug normalization CC uses" never states that suffix injection, so a good-faith implementer produces `productcatalog` and the FR-B6 join fails. Worse: startd8's `ServiceHints.service_id` is the raw `instrumentation_hints` key (`store`, `query-frontend`), so even a *faithful* mirror yields a spelling startd8 never uses — every ENV_FORM row skips as "unknown service", and AC-G6 blesses that as exit 0.
- **Assumptions / conditions:** None — verified against HEAD in both repos.
- **Suggested improvements:** Inline the four-step algorithm verbatim in FR-B6a (including the suffix rule); add a **match ladder** — exact, then normalized, then `(?:service)?$`-insensitive equivalence — before declaring an element unknown; add an AC that a map of ENV_FORM ids against slug-shaped `ServiceHints` produces a non-empty plan. See R1-F1 and R1-S5.

**A4 — Whether zero-score leg detection for `complete_triplet` has a clear on-disk signal today.**

- **Summary answer:** Partial — a signal exists, but no requirement names it and nothing in the generator reads it back today.
- **Rationale:** The only on-disk signals are `observability-quality.json` → `services.{svc}.{dashboard_spec|alert_rule|slo_definition}.score`, and `observability-manifest.yaml` → `artifacts[].status` / `quality_score`. A *missing* leg is an absent key, not a `0.0`, so "missing" and "zero-score" are two distinct reads, not one predicate. `_write_quality_report` returns early when nothing is scored, and `--dry-run` writes neither file — so a dry-run plan cannot honestly show which legs it would touch.
- **Assumptions / conditions:** The map run's `output_dir` is the same tree a prior quality report was written into; nothing guarantees freshness.
- **Suggested improvements:** FR-B3 declares the authoritative leg-completeness input, the absent/stale-input behavior (recommend regenerating all three legs with an explicit `reason="leg_signal_unavailable"` rather than a silent no-op), and surfaces the resolved per-leg decision on `ActionPlanEntry` so the dry-run plan is honest. See R1-F4.

**A5 — Interaction of map mode with `--observability-yaml` domain extras / declared-lane generators.**

- **Summary answer:** Neither "touched services only" nor "never" is expressible as the question assumes — those artifacts are **project-scoped**, not per-service.
- **Rationale:** `render_domain_alert_rules(_spec, project_id=...)` and `render_domain_dashboard(...)` emit one artifact per **project**, as do `generate_business_criticality_dashboard`, `generate_collector_enrichment`, and `generate_capability_index`. The declared-lane generators (`generate_declared_base_slos`, `generate_declared_functional_slos`, `generate_declared_span_slos`, `generate_declared_probe_specs`, `generate_functional_slos`) *are* per-service but are reachable from no `gen.*` id in the frozen set. Skipping all of these in map mode leaves their files intact on disk (writes are per-artifact) yet drops them from the regenerated index — the A1 truncation again, via a second path.
- **Assumptions / conditions:** None.
- **Suggested improvements:** State in FR-B3a that project-scope generators do **not** run in map mode (no `gen.*` id owns them) and that their existing index/quality rows MUST survive via merge; and that declared-lane per-service generators run only as part of a `gen.complete_triplet` regeneration for a touched service, so an SLO leg is not silently narrowed to the convention triplet.

**A6 — Exit policy when the map is malformed vs when all rows skip.**

- **Summary answer:** Malformed is under-specified (an "or", not a criterion); all-skip is specified but wrong.
- **Rationale:** FR-B1 says malformed JSON → "non-zero exit (or structured error)" — untestable as written, and `main()` today returns non-zero only when `errored > 0 or gate_failed`, so a loader returning a structured error without raising would exit **0**. AC-G6 then blesses "all-skip after valid empty/filtered map = exit 0", which collapses "you gave me nothing to do" and "I could not act on any of the N repairs you asked for" into one success signal — precisely the marker-vs-reality confusion Obs #32 warns about.
- **Assumptions / conditions:** None.
- **Suggested improvements:** Replace the prose with a small exit-code table: malformed/unreadable map → 2; non-empty map with ≥1 applied action → 0; non-empty map with **all** rows skipped → non-zero (recommend 3) plus `all_skipped: true` in `affordance_actions.json`; genuinely empty map or empty `--services` intersection → 0. See R1-F2 and R1-S4.

##### Executive summary

- The highest-severity finding is not in the planner: map mode routes through two **whole-tree rewriters** (`_write_index`, `_write_quality_report`) that would truncate the manifest and the quality SSOT ContextCore reads back (A1 → R1-S1).
- The FR-B6a join is broken at HEAD — CC appends a `service` suffix FR-B6a never mentions, and startd8 service ids are raw onboarding hint keys (A3 → R1-F1).
- Two "success" signals hide failure: all-rows-skipped exits 0, and a history-trimmed scorecard silently caps the map at 15 rows (R1-F2, R1-F3).
- FR-B4 shrink straddles layers — EXT-101 scores the rendered JSON, OBS-200a the spec — so the specified repair is either unmeasurable or reverted by the next generate (A2 → R1-F5).
- `gen.complete_triplet`'s "zero-score leg" predicate has no declared input, and nothing in the generator reads the quality JSON today (A4 → R1-F4).
- Project-scope generators (domain alert/dashboard, criticality dashboard, collector enrichment, capability index) have no `gen.*` owner and no stated map-mode disposition (A5).
- The opt-in coverage gate and the kaizen-metrics writer both read the (now partial) quality report, so a map run could pass a gate the full tree fails (R1-S4).
- Worth preserving as-is: the Mottainai reuse framing, NR-G1..G9 as a real fence, the typed `ActionPlanEntry` (FR-B2b), and §7 Reference Audit — the audit is accurate against HEAD, which is why the gaps above are locatable at all.
- No untriaged prior items exist (Appendix C was empty in both documents), so no endorsements or disagreements are possible at R1.

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | critical | Replace FR-B6a's descriptive prose with the verbatim four-step algorithm (strip trailing `_SERVICE`, delete underscores, lowercase, **append `service` when the slug does not already end in it**) and add a match ladder — exact, then normalized, then `(?:service)?$`-insensitive equivalence — before an element is declared unknown. | Anchor: "*if the id matches ENV_FORM ... apply the same slug normalization CC uses; otherwise lowercase*". CC `normalize_service` turns `PRODUCT_CATALOG` into `productcatalogservice`; `ServiceHints.service_id` is the raw `instrumentation_hints` key (`store`, `query-frontend`). A faithful mirror still fails to join, and FR-B6 then skips every ENV_FORM row while AC-G6 reports exit 0. | FR-B6a, replacing the "apply the same slug normalization CC uses" sentence; add a worked join table. | Table-driven test over `PRODUCT_CATALOG`, `PRODUCT_CATALOG_SERVICE`, `productcatalogservice`, `store` against `ServiceHints` ids `productcatalog`, `productcatalogservice`, `store`; assert a non-empty plan for every row that names a real service. |
| R1-F2 | Validation | critical | Split the exit contract into an explicit table and stop treating "every row skipped" as success: malformed/unreadable map → 2; non-empty map with at least one applied action → 0; non-empty map with all rows skipped → non-zero (recommend 3) with `all_skipped: true` recorded in `affordance_actions.json`; genuinely empty map or empty `--services` intersection → 0. | Anchor: "*exit 0 if remaining actions succeed (all-skip after valid empty/filtered map = exit 0)*". Today `main()` returns non-zero only for `errored > 0 or gate_failed`, so a loader that returns a structured error without raising exits 0; and an operator who asked for N repairs and received none currently reads the same exit code as an operator with nothing to do. | AC-G6, plus the "Malformed JSON → non-zero exit (or structured error)" sentence in FR-B1. | Three CLI tests asserting distinct exit codes for malformed map, all-rows-skip on a non-empty map, and empty map; assert `all_skipped` appears in the sidecar for the middle case. |
| R1-F3 | Data | high | Require the loader to detect and refuse-or-warn on a **truncated** AffordanceMap, and to record `source_truncated` plus the source `provenance` in `affordance_actions.json`. | Anchor: "*Scorecard-json object containing `affordance_map` (and optionally `gaps`)*". CC caps the map at `HISTORY_AFFORDANCE_CAP = 15` when trimming a report for history and stamps `history.trimmed: True`. An operator extracting the map from a trimmed scorecard silently repairs at most 15 gaps and gets a success exit — a looks-like-success failure the REQ has no guard for. | FR-B1 accepted-shapes list, plus a new AC beside AC-G8. | Fixture pair: an untrimmed scorecard and a trimmed one (15 map rows, longer `gaps`, `history.trimmed` set); assert the trimmed input warns or refuses and stamps `source_truncated` in the sidecar. |
| R1-F4 | Interfaces | high | Name the authoritative on-disk input for `gen.complete_triplet` leg completeness, define the absent/stale-input behavior, and surface the per-leg decision on `ActionPlanEntry`. | Anchor: "*Regenerate **missing or zero-score** legs only (alert / dashboard_spec / SLO) for that service*". The only signals are `observability-quality.json` `services.{svc}.{artifact_type}.score` and the manifest's `artifacts[]` rows; a missing leg is an absent key rather than a `0.0`, nothing in the generator reads either file back today, and `--dry-run` writes neither — so the dry-run plan cannot show which legs it would touch. | FR-B3 affordance table row for `gen.complete_triplet`; extend the FR-B2b field list with the resolved per-leg selection. | Unit test: quality JSON with one absent leg and one `score: 0.0` leg yields exactly those two legs in the plan; a run with no quality JSON yields all three legs plus `reason="leg_signal_unavailable"`. |
| R1-F5 | Ops | high | Declare the shrink **layer** in FR-B4 (recommend the dashboard spec, with a mandatory re-render-and-re-measure loop), require refuse-with-reason when the Grafana render is unavailable, and add a durability criterion. | Anchors: "*Apply FR-B4 shrink to that service's Grafana JSON*" and "*After shrink, OBS-200a MUST still pass*". EXT-101's `max_lines` is scored on the rendered `dashboard` artifact while OBS-200a is scored on `dashboard_spec`, so a JSON-layer shrink is reverted by the next generate (and reads as drift), while a spec-layer shrink cannot measure the budget without re-rendering — and that render is `status="skipped"` when the jsonnet toolchain is missing. | FR-B4 bullet list; add a durability clause to AC-G5. | After a shrink action, assert the rendered JSON is at or under `max_lines`, OBS-200a still passes on the spec, and a subsequent no-map `--check` reports no drift; assert an explicit refusal (not a silent pass) when the render is unavailable. |

##### Stress-test note (no additional suggestions)

Attempting to break the above: (1) if the intended operator flow always targets a **fresh** `output_dir`, the A1 truncation is not destructive — but then map mode is not a "targeted repair" of an existing tree, which contradicts FR-B3's premise, so the requirement should say which it is. (2) R1-F1 would be moot if ContextCore only ever emitted already-slug element ids — but `catalog_service_id` exists precisely because ENV_FORM ids occur, and `affordance_map` element ids flow from `report.gaps`, so the ENV_FORM path is reachable by construction. (3) R1-F3 is arguably out of scope as "a ContextCore emit concern", but the truncation is invisible on the startd8 side and the REQ owns the loader, so the guard belongs here rather than in Phase A (which is settled).

##### Endorsements & Disagreements

Appendix C contained no prior rounds in either document at R1, so there are no untriaged items to endorse or dispute.

#### Review Round R2 — claude-opus-5-thinking-high — 2026-07-28

- **Reviewer**: `claude-opus-5-thinking-high`
- **Date**: 2026-07-28 18:22:03 UTC
- **Scope**: **Adversarial / stress-test pass** (F-prefix). R1 established that map mode's post-gen surface is destructive and that the service-id join is broken. R2 attacks a different question: *assume both are fixed — do the five frozen `gen.*` affordances actually have deterministic levers, and can their outcomes be told apart from doing nothing?* Re-grounded at HEAD against `generate_dashboard_spec` / `_add_domain_panels` / `_ensure_red_coverage` / `generate_runbook` (`artifact_generator_generators.py`), `_write_quality_report` expected-metric assembly and `check_drift` (`artifact_generator.py`), `validate_extended_artifact` + `_EXTENDED_CONTRACTS` runbook markers (`tests/unit/observability/test_artifact_generator.py`), and CC `attach_catalog` / `_GAP_FROM_CHECK` (`observability/catalog.py`). Focus asks A1–A6 were answered in R1; R2 re-opens **A2** and **A5** adversarially and adds a new axis R1 did not consider (affordance reachability). Plan-side R2 items are in the PLAN file.

##### Executive summary

- **Two of the five frozen `gen.*` ids have no deterministic lever at HEAD.** `gen.improve_metric_coverage` cannot move coverage because dashboard generation is a pure function of the service hints and already panels every declared metric; `gen.enrich_runbook` becomes unreachable the moment FR-B5 lands, because its gap code is derived solely from the OBS-EXT-100 marker check FR-B5 satisfies.
- That collapses the map's practical action set to three (RED, triplet, shrink) — worth stating in the REQ so implementers do not build two untestable branches (R2-F1, R2-F4).
- **The only real lever for `metric_coverage_empty` is the authored `observability.yaml` alert path** — and that is exactly the project-scope generator R1-S2 proposes to skip in map mode. The two accepted directions collide (R2-F1).
- **`applied` is not a truthful outcome label.** `_ensure_red_coverage` legitimately no-ops for a service whose resolved SLI kinds imply neither throughput nor availability, so a `red_missing` row on a cron/queue service would report success while changing nothing (R2-F2).
- **FR-B5 has no content source for `## Risks`.** `Service summary`→`Overview` and `First response`→`Procedures` are honest renames; `Risks` is not, and the marker check is a bare substring test — so an empty heading scores. Residual risk only, per the focus file (R2-F3).
- **`--min-affordance-confidence` is a phantom knob:** the emitter produces exactly `1.0` or `0.0`, and a `0.0` row already carries no affordance ids (R2-F5).
- **Refinement to R1-F5:** its proposed durability check via `--check` cannot work — `check_drift` compares `(type, service)` key sets and derivation transformations only, never content, and excludes the rendered `dashboard` outright. See R2-S1 in the PLAN.
- R1's five F-items all still stand; R2 adds no overlap with them and endorses four below.

##### Feature Requirements Suggestions (adversarial pass)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Architecture | high | Declare `gen.improve_metric_coverage` **advisory / no deterministic lever** with an honest skip reason, or re-scope it to the alert lane and state its dependency on an authored `observability.yaml` — but do not specify it as a dashboard regeneration. | Anchor: "*Regenerate dashboard (± alerts) emphasizing uncovered expected metrics for that service*". `generate_dashboard_spec(service, business, descriptor)` is a pure function of its inputs and `_add_domain_panels` already appends one panel per `manifest_declared` metric with expr-dedup, while the expected set in `_write_quality_report` is exactly `convention ∪ declared` — so the human/dashboard coverage lane is already maximal by construction and regeneration is byte-identical. The real deficits are the system (SLO) and bridge (alert) lanes, and the bridge deficit comes from `_domain_alert_todo_block` comment stubs that `extract_referenced_metrics` strips; the only way to turn those into live references is authored `observability.yaml` thresholds — a project-scope generator map mode is otherwise told to skip. | FR-B3 affordance table row for `gen.improve_metric_coverage`; note the collision with FR-B3a's project-scope skip. | Regenerate a dashboard twice with identical inputs and assert byte-identity plus unchanged `metric_coverage_human` in the quality JSON; assert the sidecar records the affordance as no-change (or skipped with `no_deterministic_lever`), never as an applied repair. |
| R2-F2 | Validation | high | Add a fourth outcome to FR-B7 — `applied_no_change` — and require a pre/post content hash per touched artifact, so "the action ran" and "the artifact changed" are separable. | Anchor: "*listing planned vs applied vs skipped (with reasons)*". `_ensure_red_coverage` returns early both when RED is already complete and when the resolved SLI-kind set implies neither `throughput` nor `availability` — the deliberate #226 FR-13 deletion of the unconditional path. A `red_missing` row for a freshness-only cron therefore produces a legitimate no-op that the current three-outcome vocabulary must report as `applied`, which is the looks-like-success shape AC-G6 already risks elsewhere. | FR-B7, extending the planned/applied/skipped vocabulary; mirror the new outcome in FR-B2b's typed entry. | Map with `gen.emit_red_panels` against a service whose kinds resolve to freshness only: assert outcome `applied_no_change`, byte-identical dashboard, and a reason naming the resolved SLI kinds. |
| R2-F3 | Risks | medium | Name the deterministic content source for the `## Risks` section FR-B5 introduces, or state explicitly that it ships as a stub whose EXT-100 credit is knowingly hollow. | Anchor: "*Align `generate_runbook` headings with the scored contract markers (`Overview`, `Risks`, `Procedures`, `Escalation` …)*". `generate_runbook` emits `## Service summary`, `## Dashboards`, `## Alerts`, `## First response`, `## Escalation`; the first and fourth rename honestly to `Overview` and `Procedures`, but **nothing** in the generator maps to `Risks`, and `validate_extended_artifact` is a case-sensitive substring test — a bare `## Risks` line scores full marks. Material already in hand would fill it deterministically: the service's `fr_coverage` entries (`empty_services`, `ungrounded_kinds`, `suppressed_base_metrics`, `unverified_base_metrics`) plus criticality and availability targets. Filed as residual risk only; the Hayai always-on decision is not relitigated. | FR-B5, after the marker list; cross-reference the Obs #32 caveat already present in AC-G4. | Golden runbook test asserting `## Risks` contains at least one non-heading line derived from the service's coverage gaps, not just the heading. |
| R2-F4 | Interfaces | medium | State in the known-gen set (or FR-B5) that `gen.enrich_runbook` becomes **unreachable** once FR-B5 lands, and that consuming it is schema fidelity rather than a live branch. | Anchor: "*Map-driven `enrich_runbook` then primarily fills remaining skeletal gaps beyond headings*". ContextCore derives `runbook_skeletal` only from OBS-EXT-100 via `_GAP_FROM_CHECK`, and OBS-EXT-100 fires only on a missing `completeness_markers` substring (`Overview`, `Risks`, `Escalation`, `Procedures` — `_EXTENDED_CONTRACTS` in the generator tests). Once FR-B5 emits all four headings, no marker issue is raised, no `runbook_skeletal` gap is emitted, and the affordance can never appear in a real map — so "remaining skeletal gaps beyond headings" names a category EXT-100 cannot detect. Keeping the id satisfies NR-G5; pretending it has a behavior produces an untestable branch. | §2 Definitions "Known gen set" row, plus the FR-B5 sentence; keep the id, annotate reachability. | Assert the frozen known-gen set still contains the id (AC-G8 unchanged) while the apply layer records it as `skipped` with `reason="unreachable_after_fr_b5"` if it ever appears; no dedicated repair branch required. |
| R2-F5 | Data | medium | Either drop `--min-affordance-confidence` (Accidental-Complexity, consistent with the already-rejected second dry-run flag) or document its binary semantics and require the skip reason to echo the upstream `unmapped_reason` verbatim. | Anchor: "*Confidence MAY be used as a filter (`--min-affordance-confidence`, default 0.0)*". `attach_catalog` sets `confidence` to exactly `1.0` when affordance ids resolved and `0.0` otherwise, and a `0.0` row additionally carries empty `affordance_ids` plus `unmapped_reason: "no registry entry"`. So the flag has two meaningful values, its default admits everything, and the rows it would filter are already no-ops — while the genuinely useful upstream signal (`unmapped_reason`) is discarded in favour of a locally invented "unknown affordance" reason. | FR-B6, replacing the confidence sentence; add the `unmapped_reason` echo to FR-B7's skip records. | Fixture row with `confidence: 0.0` and `unmapped_reason` set: assert the sidecar skip reason contains the upstream string verbatim; if the flag is retained, assert `--min-affordance-confidence 0.5` changes nothing on a real CC-shaped map. |

##### Endorsements & Disagreements

**Endorsements** (untriaged R1 items this round agrees with):

- **R1-F1** — the `service`-suffix join failure is the single defect most likely to make the whole feature silently do nothing; R2's reachability findings are moot if the join never lands.
- **R1-F2** — the exit-code table is the only thing that would have surfaced R2-F1/R2-F4 at runtime rather than at review time.
- **R1-F4** — with `gen.improve_metric_coverage` and `gen.enrich_runbook` reduced to no-ops (R2-F1, R2-F4), `gen.complete_triplet`'s undefined leg signal becomes load-bearing for two of the three surviving affordances.
- **R1-S1** (plan) — the merge requirement is a precondition for every R2 finding being observable at all, since the sidecar and quality JSON are how outcomes are read.

**Disagreements / refinements:**

- **R1-F5 — partially wrong in its Validation column.** Its "a subsequent no-map `--check` reports no drift" test cannot detect a reverted shrink: `check_drift` builds `existing_keys` / `fresh_keys` from `(type, service)` pairs and compares derivation-rule transformations only — it never compares artifact **content** — and it explicitly excludes the rendered Grafana JSON via `_DERIVED_TYPES = {"dashboard"}`. The suggestion's substance (name the shrink layer, refuse when the render is unavailable) stands; its verification mechanism must be replaced by content hashing. Concrete replacement filed as R2-S1 in the PLAN.
