# Deterministic Plan Ingestion — Implementation Plan

**Version:** 0.2 (aligned with DETERMINISTIC_INGESTION_REQUIREMENTS.md v0.2)
**Date:** 2026-06-03
**Status:** Ready for review (pre-implementation)

> Scope note from the reflective loop: the deterministic generators
> (`_heuristic_transform_content`, `_heuristic_assess_complexity`) already exist and are
> already proven as on-failure fallbacks. This plan **promotes them to default** and gates
> the LLM paths behind flags. It is wiring + config + tests + docs — not new algorithms.

---

## Step map (requirement → change)

| Step | Req | File / location | Change |
|------|-----|-----------------|--------|
| S1 | FR-2, FR-1 | `plan_ingestion_models.py` `PlanIngestionConfig` (~line 104) | Add `enable_llm_assess: bool = False` and `enable_llm_transform: bool = False`; parse both in `from_dict` via `_as_bool_cfg`. Document `complexity_threshold`/`force_route`/`low_quality_policy` as deprecated (FR-7). |
| S2 | FR-2 | `plan_ingestion_workflow.py` `_execute` ASSESS block (~4206–4241) | Branch on `cfg.enable_llm_assess`: when `False`, skip `_phase_assess`, call `_heuristic_assess_complexity(parsed_plan, threshold, force_route)` directly, build a synthetic `assess_step` with `metadata={"deterministic": True}` and `cost=0.0`. When `True`, keep current LLM call (with heuristic fallback intact). |
| S3 | FR-1 | `plan_ingestion_workflow.py` `_execute` TRANSFORM block (~4311–4346) | Branch on `cfg.enable_llm_transform`: when `False`, skip `_resolve_transformer_agent` + `_phase_transform`; write `_heuristic_transform_content(parsed_plan, route)` to `plan-ingestion-tasks.yaml` via `atomic_write`; build a synthetic `transform_step` with `metadata={"deterministic": True}`, `cost=0.0`. When `True`, keep current LLM path. |
| S4 | FR-4 | `plan_ingestion_workflow.py` (~4243–4246 comment) | **Revised:** no route reassignment exists (verified: `route` is only ever `ContractorRoute.PRIME`). Rewrite the misleading comment to describe advisory-only behavior; clarify `bias_artisan` log wording as advisory-warn. Comment/wording only — zero behavior change. |
| S5 | FR-6 | `plan_ingestion_workflow.py` (assess/transform step construction) + `plan_ingestion_diagnostics.py` if it shapes phase metadata | Ensure `metadata.deterministic` flows into `plan-ingestion-diagnostic.json` per phase. |
| S6 | FR-2/FR-1 | `_resolve_assessor_agent` / `_resolve_transformer_agent` (~1419–1455) | Make agent resolution lazy/conditional so no agent (and no API-key validation) is constructed when the LLM path is disabled. Assessor is still needed by PARSE — keep resolving it for PARSE; only gate the *assess* and *transform* usages. |
| S7 | FR-5 | `docs/PLAN_INGESTION_REQUIREMENTS.md` | Mark REQ-PI-011/012 superseded by REQ-SU-102; redraw data-flow without the Artisan branch; add pointer to this initiative. |
| S8 | FR-5 | `GOLDEN_SEED_REQUIREMENTS.md` (~line 34) | Correct the pipeline diagram: seed tasks come from PARSE features via deterministic derivation, not TRANSFORM. |
| S9 | FR-5 | `SEED_UNIFICATION_REQUIREMENTS.md` REQ-SU-102 | Mark the "heuristic override removed" acceptance criterion done (delivered by S4). |
| S10 | OQ-5 | `tests/unit/test_plan_ingestion_workflow.py`, `tests/unit/workflows/*` | Audit for tests that assert ASSESS/TRANSFORM call `agent.generate`. Update to expect deterministic default; add explicit tests for both `enable_llm_*` branches. |

---

## Detailed approach

### S1 — Config flags (foundation)
`PlanIngestionConfig` already consolidates ~30 config keys with `_as_bool_cfg`. Two new boolean fields, both defaulting `False`, parsed in `from_dict`. Zero risk; additive.

### S2 — ASSESS default to heuristic
The deterministic scorer signature already matches: `_heuristic_assess_complexity(parsed_plan, threshold=..., force_route=...)` returns a complete `ComplexityScore` (all 7 dims + composite + `route=PRIME`). The default branch becomes a direct call with no agent. The existing LLM+fallback code moves under `if cfg.enable_llm_assess:`. `assess_step` for the deterministic case carries `cost=0.0`, `time_ms≈0`, `metadata={"deterministic": True}`.

### S3 — TRANSFORM default to heuristic
`_heuristic_transform_content` already returns valid YAML with the exact `tasks[]` schema the file needs, and is already invoked on transform error (`workflow.py:4331`) — so the write/validate path is proven. The default branch writes that content directly; `state.plan_document_path` is set as today so all YAML consumers keep working. The 64k-token agent and its `max_tokens` bump are only constructed under `if cfg.enable_llm_transform:`.

### S4 — Remove misleading artisan-routing drift (comment/naming only)
Implementation-time discovery: the harmful `route → artisan` reassignment does **not** exist — `route` is only ever `ContractorRoute.PRIME` (`workflow.py:1682`), and the low-quality block at 4243–4282 only builds `low_quality_reasons` and either fails (policy=`fail`) or logs an advisory warning (policy=`bias_artisan`). So S4 is reduced to: rewrite the stale comment ("Override routing to artisan…") to describe the actual advisory behavior, and clarify the `bias_artisan` wording. No behavior change. The requirements doc FR-4 and §0 were updated to record this.

### S5/S6 — Telemetry + lazy agents
Thread `metadata.deterministic` through to the diagnostic so cost savings are measurable per FR-6. Ensure the assessor agent is still resolved for PARSE (PARSE is unchanged and mandatory) but the transformer agent is only resolved when `enable_llm_transform=True`.

### S7–S9 — Doc reconciliation
Pure documentation edits; no code. Keep edits surgical and cross-referenced.

### S10 — Tests
Likely the largest effort. Expect existing tests to mock `agent.generate` for assess/transform; those become tests of the opt-in path. Add:
- `test_assess_deterministic_by_default` — no agent call, `ComplexityScore` populated, `cost==0`.
- `test_transform_deterministic_by_default` — YAML written, valid schema, `cost==0`, descriptions == feature descriptions.
- `test_enable_llm_assess_opt_in` / `test_enable_llm_transform_opt_in` — LLM path still reachable.
- `test_no_artisan_route_on_low_quality` — low-quality plan stays `prime`.

---

## Risk & validation

| Risk | Mitigation |
|------|------------|
| A consumer relies on LLM-elaborated YAML (richer than features) | Verified: prime seed ignores YAML task content; Artisan (ON HOLD) and scripts only need valid schema, which the heuristic provides. REFINE reviews structure, not LLM prose. |
| Tests assume an LLM call | S10 audits and updates; covered by OQ-5. |
| Kaizen seed-fitness expects a `composite` from the LLM | Heuristic scorer already produces `composite`; format unchanged. |
| Hidden read of the removed route override | S4 includes a grep for `complexity.route`/`state.route` writes after the override. |

**Acceptance validation:** re-run ingestion on the element-registry plan with defaults; assert `plan-ingestion-diagnostic.json` shows `assess.cost_usd==0`, `transform.cost_usd==0`, `*.deterministic==true`, `route=="prime"`, and `seed_quality_score` within noise of the 0.9667 baseline (expected: identical, since seed derivation is unchanged).

**Expected outcome:** ingestion LLM cost drops from ~$0.42 to ~$0.16/run (PARSE only) — a **62% reduction** — and ingestion LLM latency drops ~71% (removes 255s of 359s), with no seed-quality change.

---

## Sequencing

S1 → (S2, S3, S4 in parallel) → S5/S6 → S10 (tests) → S7/S8/S9 (docs). Implement behind defaults so the change is observable-by-diagnostic before any rollout decision.
