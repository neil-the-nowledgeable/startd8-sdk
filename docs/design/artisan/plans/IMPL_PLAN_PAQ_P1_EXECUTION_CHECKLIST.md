# Priority 1 Execution Checklist: Prime-Parity Artisan Quality

**Version:** 1.0.0  
**Created:** 2026-02-26  
**Status:** Ready for execution  
**Depends on:** `docs/design/artisan/plans/IMPL_PLAN_PAQ_PRIORITIZED.md`  
**Scope:** Priority 1 only (`REQ-PAQ-100/101/200/201/300/301/400/401/500/501`)

---

## Execution Order

1. **PR-A** — Re-review correctness (`REQ-PAQ-200`, `REQ-PAQ-201`)
2. **PR-B** — Canonical path enforcement (`REQ-PAQ-300`, `REQ-PAQ-301`)
3. **PR-C** — DESIGN quality gate metrics/enforcement (`REQ-PAQ-400`, `REQ-PAQ-401`)
4. **PR-D** — Deterministic context floor (`REQ-PAQ-100`, `REQ-PAQ-101`, `REQ-PAQ-500`, `REQ-PAQ-501`)

---

## PR-A Checklist: Re-Review Correctness

**Requirements:** `REQ-PAQ-200`, `REQ-PAQ-201`  
**Primary file:** `src/startd8/contractors/artisan_phases/design_documentation.py`  
**Primary tests:** `tests/unit/contractors/test_design_quality_context.py`

### Implementation Steps

- [ ] Update `DesignDocumentationPhase.run()` so any `_revise_design(...)` result is always followed by reviewer + arbiter review on the revised design.
- [ ] Ensure all non-`RE_REVIEW` resolution branches cannot return without a post-revision review pair.
- [ ] Ensure final `DesignDocumentResult` verdicts map to the final returned `design_document` revision.
- [ ] Add structured reason code for `agreed=False` outcomes (for example `DISAGREEMENT_UNRESOLVED`, `MAX_ITERATIONS_EXCEEDED`).
- [ ] Record final accepted iteration index in result metadata.

### Exact Test Cases

| Test file | Test name | Expected result |
|---|---|---|
| `tests/unit/contractors/test_design_quality_context.py` | `test_non_rereview_resolution_triggers_post_revision_dual_review` | Reviewer and arbiter are each called again after revision before return. |
| `tests/unit/contractors/test_design_quality_context.py` | `test_returned_verdicts_match_final_revised_design` | Final verdict evidence references revised design, not pre-revision draft. |
| `tests/unit/contractors/test_design_quality_context.py` | `test_no_early_return_after_revision_without_rereview` | No branch returns revised design without second review cycle. |
| `tests/unit/contractors/test_design_quality_context.py` | `test_agreed_true_requires_latest_dual_approval` | `agreed=True` only when latest reviewer+arbiter both approve. |
| `tests/unit/contractors/test_design_quality_context.py` | `test_agreed_false_contains_reason_code` | Failed convergence includes machine-readable reason code. |

### Run Commands

```bash
pytest tests/unit/contractors/test_design_quality_context.py -k "revision or rereview or agreed" -v
pytest tests/unit/contractors/test_design_quality_context.py -v
```

### PR-A Merge Gate

- [ ] All PR-A tests pass.
- [ ] Manual branch audit confirms no revised-design return path without post-revision dual review.

---

## PR-B Checklist: Canonical Path Enforcement

**Requirements:** `REQ-PAQ-300`, `REQ-PAQ-301`  
**Primary file:** `src/startd8/contractors/context_seed_handlers.py`  
**Primary tests:** `tests/unit/contractors/test_design_phase_handler.py`

### Implementation Steps

- [ ] Keep canonical (dual-review v1) as default production path.
- [ ] Require explicit opt-in for modular/single-pass path (`use_modular_prompts=True`).
- [ ] Add review envelope for variant path so acceptance cannot bypass reviewer/arbiter quality checks.
- [ ] Remove/guard any `agreed=True` default assignment in variant path unless review evidence exists.
- [ ] Persist path tag metadata per task (`prompt_version` or explicit route ID).

### Exact Test Cases

| Test file | Test name | Expected result |
|---|---|---|
| `tests/unit/contractors/test_design_phase_handler.py` | `test_default_path_uses_v1_dual_review` | With default config, handler uses canonical v1 flow. |
| `tests/unit/contractors/test_design_phase_handler.py` | `test_modular_path_requires_explicit_opt_in` | Variant path is used only when opt-in flag is true. |
| `tests/unit/contractors/test_design_phase_handler.py` | `test_variant_path_cannot_auto_agree_without_review_envelope` | Variant output is not auto-accepted without review evidence. |
| `tests/unit/contractors/test_design_phase_handler.py` | `test_variant_path_review_failure_propagates_status` | Failed review in variant path marks task as failed/non-agreed. |
| `tests/unit/contractors/test_design_phase_handler.py` | `test_design_result_records_route_metadata` | Per-task output includes route tag for downstream analytics. |

### Run Commands

```bash
pytest tests/unit/contractors/test_design_phase_handler.py -k "modular or dual_review or prompt_version" -v
pytest tests/unit/contractors/test_design_phase_handler.py -v
```

### PR-B Merge Gate

- [ ] Default execution path confirmed canonical.
- [ ] Variant path cannot bypass review envelope.

---

## PR-C Checklist: DESIGN Gate Metrics and Enforcement

**Requirements:** `REQ-PAQ-400`, `REQ-PAQ-401`  
**Primary files:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_contractor.py`  
**Primary tests:**  
`tests/unit/contractors/test_design_phase_handler.py`  
`tests/unit/contractors/test_quality_gate.py`

### Implementation Steps

- [ ] Add deterministic DESIGN metrics to phase output (`total_failed`, `agreement_rate`).
- [ ] Compute metrics from `design_results` deterministically.
- [ ] Extend `_check_quality_gate(...)` to evaluate DESIGN in `skip`, `warn`, and `block` modes.
- [ ] In `block` mode, DESIGN gate failures raise `QualityGateError`.
- [ ] Include failed-task details for DESIGN in gate diagnostics payload.

### Exact Test Cases

| Test file | Test name | Expected result |
|---|---|---|
| `tests/unit/contractors/test_design_phase_handler.py` | `test_design_output_includes_total_failed_and_agreement_rate` | DESIGN phase output always includes both metrics. |
| `tests/unit/contractors/test_design_phase_handler.py` | `test_agreement_rate_calculation_is_deterministic` | Agreement rate is stable for same `design_results` input. |
| `tests/unit/contractors/test_quality_gate.py` | `test_design_phase_failures_raise_in_block_mode` | `block` mode raises `QualityGateError` for DESIGN failures. |
| `tests/unit/contractors/test_quality_gate.py` | `test_design_phase_failures_warn_in_warn_mode` | `warn` mode logs warning for DESIGN failures. |
| `tests/unit/contractors/test_quality_gate.py` | `test_design_phase_failures_ignored_in_skip_mode` | `skip` mode does not raise for DESIGN failures. |
| `tests/unit/contractors/test_quality_gate.py` | `test_design_gate_details_include_failed_tasks` | Error/warn details include failed DESIGN task IDs. |

### Run Commands

```bash
pytest tests/unit/contractors/test_quality_gate.py -k "design" -v
pytest tests/unit/contractors/test_design_phase_handler.py -k "agreement_rate or total_failed" -v
pytest tests/unit/contractors/test_quality_gate.py tests/unit/contractors/test_design_phase_handler.py -v
```

### PR-C Merge Gate

- [ ] DESIGN gate behavior matches TEST/REVIEW policy behavior for `skip|warn|block`.
- [ ] Metrics are present in DESIGN output on success and failure paths.

---

## PR-D Checklist: Deterministic Context Floor

**Requirements:** `REQ-PAQ-100`, `REQ-PAQ-101`, `REQ-PAQ-500`, `REQ-PAQ-501`  
**Primary files:**  
`src/startd8/contractors/prompt_utils.py`  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_phases/design_documentation.py`  
**Primary tests:**  
`tests/unit/contractors/test_tiered_context_rendering.py`  
`tests/unit/contractors/test_design_phase_handler.py`

### Implementation Steps

- [ ] Add/confirm explicit section budget registry for design prompt assembly.
- [ ] Enforce deterministic compression order and preserve Tier-0 under all budget pressure.
- [ ] Add explicit missing markers for absent required high-signal fields (for example `MISSING_T0:<field>`).
- [ ] Enforce minimum high-signal context set before generation (block or downgrade behavior).
- [ ] Ensure single-source tier registry is used across design-adjacent renderers.

### Exact Test Cases

| Test file | Test name | Expected result |
|---|---|---|
| `tests/unit/contractors/test_tiered_context_rendering.py` | `test_compression_order_is_t3_then_t2_then_t1` | Compression follows deterministic order every run. |
| `tests/unit/contractors/test_tiered_context_rendering.py` | `test_t0_fields_never_dropped_under_extreme_budget` | Tier-0 content remains present at very low budget. |
| `tests/unit/contractors/test_tiered_context_rendering.py` | `test_missing_t0_marker_emitted_for_required_absent_fields` | Missing required Tier-0 fields produce explicit marker(s). |
| `tests/unit/contractors/test_tiered_context_rendering.py` | `test_unknown_fields_default_to_noncritical_tier` | Unknown keys render as non-critical tier by default. |
| `tests/unit/contractors/test_design_phase_handler.py` | `test_design_generation_downgrades_or_blocks_when_high_signal_floor_missing` | Missing high-signal floor triggers configured fail/downgrade behavior. |
| `tests/unit/contractors/test_design_phase_handler.py` | `test_high_signal_floor_satisfied_allows_generation` | With required context present, generation proceeds. |

### Run Commands

```bash
pytest tests/unit/contractors/test_tiered_context_rendering.py -v
pytest tests/unit/contractors/test_design_phase_handler.py -k "high_signal or floor or context" -v
pytest tests/unit/contractors/test_tiered_context_rendering.py tests/unit/contractors/test_design_phase_handler.py -v
```

### PR-D Merge Gate

- [ ] Tier-0 invariants enforced under low-budget conditions.
- [ ] High-signal floor behavior is deterministic and tested.

---

## Final Priority 1 Gate

- [ ] PR-A, PR-B, PR-C, PR-D merged in order.
- [ ] Full targeted suite passes:

```bash
pytest \
  tests/unit/contractors/test_design_quality_context.py \
  tests/unit/contractors/test_design_phase_handler.py \
  tests/unit/contractors/test_quality_gate.py \
  tests/unit/contractors/test_tiered_context_rendering.py \
  -v
```

- [ ] One end-to-end dry-run and one non-dry-run validation demonstrate:
1. revised designs are always re-reviewed,
2. canonical path is default,
3. DESIGN gate enforcement is active,
4. high-signal context floor is enforced.

