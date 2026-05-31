# Observability cat-4/5 Implementation — Session Handoff

**Date:** 2026-05-31
**Branch:** `feat/obs-cat5-impl` (pushed to `origin`, 8 commits ahead of `main`)
**Worktree:** `/Users/neilyashinsky/Documents/dev/startd8-obs-gap`
**Principle:** Written per [MUJŌ](../design-princples/MUJO_DESIGN_PRINCIPLE.md) — the Five
Continuity Signals. **Negative knowledge (Signal 5) is the priority — read it first.**

> The previous agent does not exist. This file is the only synthesis of *why* the code
> is the way it is, what was rejected, and what traps await. Start at Signal 3, not 0.

---

## Signal 1 — STATE (where are we?)

**The descriptor spine (REQ-OBS-SHARED-001..005) is implemented for cat-5 (AI-agent) and
cat-4 (project), with the pipeline-innate catalog half-done.** The observability manifest
now carries `category`/`orientation` taxonomy axes, a kind-aware parity test, a
descriptor→`manifest_declared` bridge, and `route_state` provenance — all *consumed by
nothing yet* (the generator wiring is the next big piece).

- **Tests:** the full observability + session + complexity suites are **green**. The
  manifest drift check passes. Run with `PYTHONPATH="$(pwd)/src"` (see Signal 5 #1).
- **Manifest:** `docs/capability-index/startd8.observability.manifest.yaml` — 18 metrics,
  10 spans, regenerated; hand-authored SLO/alert templates preserved.
- **Completeness gate:** `GRANDFATHERED_SOURCES` is **empty** — every collector-
  instrumented module declares its axes (0 violations on a real check, not masking).
- **Parity bootstrap:** ~~22 emitters tolerated~~ → **B COMPLETE.** `parity.EMITTER_EXCLUSIONS`
  is now **empty**; `run_parity()` is a clean bijection (`ok=True`, `bootstrap_undeclared=[]`,
  no hard violations). 23 emitters declared (the 22 prefix-cluster ones + `complexity.tier_distribution`,
  whose declaration `e48e8f71` claimed but the stash incident dropped — never recovered until now).
  Manifest YAML regenerated 17→40 metrics (additive; SLO/alert preserved). **B done; C (REQ-OAT-023
  keystone + route_state) also DONE — see Signal 4 step 2. Resume point is now C2 (REQ-OAT-050/051
  orientation-aware quality scoring) or step 3 (`task.*` disambiguation).**

---

## Signal 2 — ACCOMPLISHMENTS (what changed?)

8 commits on the branch (oldest → newest):

| Commit | What |
|--------|------|
| `da3a1105` | cat-5 Phase 0.4/0.5 keystone: `taxonomy_enums.py`, axes on Metric/Span descriptors, **collector pass-through** (the R3-F1 fix), `EventTypeDescriptor.category→event_group` |
| `bdfad35f` | cat-5 Phase 0.1-0.3: cost double-record guard, `_metric_labels` helper, **retired the Prometheus opt-in path** |
| `a7497351` | cat-5 Phase 1.1/1.3: annotate agent descriptors, completeness gate (`manifest_validation.py`) |
| `18fbbd9d` | cat-5 Phase 1.2/1.4: **kind-aware parity helper** (`parity.py`) + bootstrap mode |
| `46eced3b` | cat-5 Phase 2: dotted metric rename + **resolved the exported-name collision** |
| `cbe9cca6` | cat-5 Phase 3 + 4.1: descriptor→`manifest_declared` bridge (`onboarding_bridge.py`) + outcome labels |
| `e48e8f71` | cat-4 (A) scoped: project spans + tier histogram + ownership docstrings |
| `b294d046` | **Recovery** of stash-lost cat-4 edits + B grandfathered-module annotations |

New modules: `observability/taxonomy_enums.py`, `manifest_validation.py`, `parity.py`,
`onboarding_bridge.py`, `costs/double_record_guard.py`.

---

## Signal 3 — DISCOVERIES (what was learned?)

**Positive:**
- The parity scanner (`parity.scan_emitted_metric_names`) is the load-bearing tool — it
  found gaps a `len(metrics)==N` test never could.
- The **R3-F2 exported-name collision was REAL**: `startd8.cost.total` and
  `startd8_cost_total` both exported to `startd8_cost_total`. Resolved by renaming the
  per-session metric to `startd8.session.cost.total` (Phase 2).
- The **R3-F1 collector-drop bug was REAL**: `collector.py` silently dropped
  `prometheus_name`/`dashboard_hints` (and would have dropped the new axes). Fixed.
- Module-level `category`/`orientation` defaults in `_OTEL_DESCRIPTORS` (collector reads
  them as fallbacks) keep annotation DRY — one line per module, not per-descriptor.

**Negative / scope-correcting (the expensive lessons):**
- **The `task.*` rename is 13× bigger than the plan claimed.** Planned as a 3-file rename;
  reality is **39 distinct attrs / 98 occurrences / 9 files**, and `task.*` *already mixes*
  codegen-chunk (`complexity_tier`, `blast_radius`) with work-item (`story_points`,
  `assignee`, `labels`, `depends_on`) concepts. A blind sweep would mislabel work-item
  attrs as codegen. **Deferred** to a per-site classification follow-up — see
  `OBSERVABILITY_CODEGEN_TASK_DISAMBIGUATION_FOLLOWUP.md`.
- The 22 undeclared emitters are spread across ~6 modules (`element_registry.py`,
  `micro_prime/engine.py`, `micro_prime/repair.py`, `security_prime/otel.py`,
  `utils/artifact_inventory.py`, `plan_ingestion_mottainai.py`), not co-located.

---

## Signal 4 — NEXT ACTIONS (what should I do?)

**In dependency order. Task IDs reference the session's TodoWrite list (#10–12).**

1. **~~Finish B — declare the 22 emitters (#10)~~ ✅ DONE.** All 23 emitters declared
   (`pipeline_innate/system`; `complexity.tier_distribution` was the dropped 23rd), 7 carrier
   modules registered in `collector._INSTRUMENTED_MODULES`, `parity.EMITTER_EXCLUSIONS` emptied.
   `run_parity().bootstrap_undeclared == []`, obs+manifest suites green (230). YAML regenerated.
2. **~~Then C — generator route_state consumption (#11)~~ ✅ DONE (keystone scope).**
   Implemented the REQ-OAT-023 keystone in `artifact_generator.py`: single type-keyed
   registry (`_ARTIFACT_TYPE_REGISTRY`, REQ-OAT-070a) distinct from the legacy 4-value
   `_ARTIFACT_TYPE_TO_CATEGORY`; `category`/`orientation`/`declared_type`/`runtime_type`/
   `route_state`/`skip_reason`/`owner` on `ArtifactResult`, stamped centrally in `_generate_one`;
   `classify_route_state`/`classify_route_states` (REQ-OBS-SHARED-004, incl. the stale
   `contextcore_task_*`→`contextcore_owned` clause); honest skips + `owned_elsewhere`
   coverage-denominator exclusion + per-category coverage (REQ-OAT-052); declared-first metric
   classification w/ `inferred` recording (REQ-OAT-024) + REQ-OAT-041 "awaiting cat-4/5 home" count.
   Human onboarding dashboards reuse the existing `portal_spec_builder` (NOT rebuilt).
   **Deferred to C2:** REQ-OAT-050/051 orientation-aware quality scoring + the D-9 validator-runner
   refactor. New tests: `test_route_state.py` (28). Obs+manifest suites green (258 total).

   ~~2-orig. Then C — generator route_state consumption (#11).~~ Teach
   `observability/artifact_generator.py` (which ALREADY generates 8 artifact types) to:
   (a) read `route_state` from `manifest_declared` (via `onboarding_bridge`) — route
   `sdk_emitted`→produced, `contextcore_owned`→`skip_reason=owned_elsewhere`/`owner`
   excluded from the coverage denominator (REQ-OAT-052), `declared_unimplemented` +
   `external_convention` per the 4-state table; (b) consume the taxonomy
   `category`/`orientation` for orientation-aware output. NOTE: it currently has 0
   `route_state` refs and only the OLD `_ARTIFACT_TYPE_TO_CATEGORY` (4-value capability
   grouping — DIFFERENT from the 5-cat taxonomy; do not conflate).
3. **Deferred follow-up — `task.*` disambiguation (#12).** Per-site audit; see its doc.
4. **Housekeeping:** open the PR for `feat/obs-cat5-impl`; decide whether cat-4/B/C live on
   this branch or split. Phase 5 (cat-5 artifact *definitions*) and 4.2/4.3 (eval/tool-use
   telemetry) remain reserved per plan.

---

## Signal 5 — WARNINGS (what should I NOT do?) ⚠️ HIGHEST PRIORITY

1. **NEVER `git stash` mid-work in this worktree.** A `git stash -u`/`pop` cycle this
   session **silently dropped 5 files' edits** right before a commit; the completeness gate
   masked it via a stale grandfather list. To compare against a baseline, use
   `git diff HEAD` or `git show HEAD:<file>`, or a throwaway worktree — never stash.
2. **Tests need `PYTHONPATH="$(pwd)/src"`.** The venv's editable install resolves
   `import startd8` to the **primary repo** (`startd8-sdk/src`), NOT this worktree. Running
   plain `pytest` here tests the WRONG source and yields phantom pass/fail. Always prefix.
3. **Regenerating the manifest YAML MUST preserve hand-authored sections.** `generate_
   manifest()` does NOT emit `slo_templates`/`alert_templates`. Do not `--show > yaml` —
   load the committed YAML, replace only `metrics/spans/event_types/dashboards`, keep
   `slo_templates`/`alert_templates` verbatim (see the python snippet in commits 46eced3b /
   e48e8f71). Overwriting wipes 3 SLOs + 3 alerts.
4. **Do NOT blind-rename `task.*`.** See Signal 3 — it would mislabel work-item attributes.
   Per-site classification only.
5. **The 22 bootstrap exclusions + the empty grandfather list are an INVARIANT, not
   decoration.** Removing an `EMITTER_EXCLUSIONS` entry without declaring its descriptor, or
   adding an unannotated collector module without grandfathering, will (correctly) fail the
   parity / completeness tests. That is the gate working.
6. **Cost-dashboard semantic shift (already shipped, verify before prod):** dashboards/SLO/
   alert templates querying `startd8_cost_total` now resolve to the **global** cost (costs
   module), not per-session (which moved to `startd8_session_cost_total`). Judged correct
   for cost/budget panels; a human should eyeball before this reaches live dashboards.
7. **`route_state` is the routing key, NOT `category` (R3-F6).** When wiring the generator,
   route by `route_state`; `category` answers "what domain," not "who emits / why skipped."

---

## Pre-existing failures (NOT yours — do not chase)

Confirmed failing on `main`/clean HEAD, unrelated to this work: `test_link_count`
(dashboard_creator), ~14 contractor tests (`test_kaizen_metadata_agent_specs`,
`test_copy_detection::test_strip_docstrings`, `test_pca_p0::test_track_new_field`),
`test_stub_counting_parity`, and `F821 RepairRoute` lint in `repair/orchestrator.py`.

---

*Handoff v1.0 — emitted during the session, not after (MUJŌ design rule #1). The branch is
clean, green, and pushed. Resume at Signal 4 step 1.*
