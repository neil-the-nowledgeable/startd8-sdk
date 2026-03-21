# Observability Pipeline — Fix List

**Date**: 2026-03-21
**Context**: Validated against run-091 (online-boutique, csharp, 15/15 PASS, $1.91). Stage 4.5 artifacts generate correctly but downstream threading has gaps. This document catalogs every fix needed to get full value from the capability.

---

## Fix 0: `self._cfg` Never Set in Plan Ingestion Workflow (ROOT CAUSE)

**Severity**: Critical — blocks ALL config-driven features from reaching the emitter (observability, security contract, and anything else added to `PlanIngestionConfig`)

**File**: `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

**Problem**: Line 3602 creates `cfg = PlanIngestionConfig.from_dict(config)` as a local variable. The emitter wrapper at line 3554 does `_base_cfg = getattr(self, "_cfg", None) or PlanIngestionConfig()` — but `self._cfg` is never assigned, so it always falls back to a default `PlanIngestionConfig()` with all optional fields as `None`.

This means `observability_hints`, `security_contract`, `generation_profile`, and every other config field parsed from `resolve-provenance.py` output is silently dropped before reaching the emitter.

**Fix**: Add `self._cfg = cfg` after line 3602:
```python
cfg = PlanIngestionConfig.from_dict(config)
self._cfg = cfg  # Store for _phase_emit compat wrapper
```

**Impact**: Unblocks observability contract threading (REQ-OPI-200), security contract threading (REQ-ICD-106), and any future config-driven emitter features. This single fix is the reason both `observability_contract: MISSING` and `security_contract: MISSING` appear in run-090 and run-091 seeds despite the extraction and emitter code being fully implemented.

**Test**: After fix, re-run plan ingestion against run-091 export → verify `observability_contract` and `security_contract` are present in seed.

---

## Fix 1: `--generation-profile` Crash in TODO Completion (FIXED)

**Severity**: High — crashes the instrumentation stage, preventing all TODO completion

**File**: `cap-dev-pipe/run-prime-contractor.sh` line 347

**Problem**: Line 347 passes `--generation-profile full` to `run_todo_completion.py`, which does not accept that argument. Causes `error: unrecognized arguments: --generation-profile full` (exit 2).

**Fix**: Already applied — replaced with a comment explaining why the profile is not forwarded. Generation profile controls ContextCore export scoping, not instrumentation.

**Status**: DONE

---

## Fix 2: Non-Service Entry Filtering in Artifact Generator

**Severity**: Medium — inflates artifact count but doesn't break functionality

**File**: `src/startd8/observability/artifact_generator.py`

**Problem**: `instrumentation_hints` from ContextCore includes entries for requirement IDs (`reqcdpobs001...`), project names (`online-boutique-demo`), and run IDs (`online-boutique/run-090-...`). All get `transport: http` and produce meaningless alert rules, dashboard specs, and SLO definitions.

**Current state**: Filtering IS implemented in `_is_non_service_entry()` and `extract_service_hints()`. Run-091 shows 4 services instead of run-090's 13 — but `multiserviceprojectguidance` and `protos` still leak through (they have `transport` set).

**Remaining fix**: Tighten filter — `protos` is a shared module directory (not a service). `multiserviceprojectguidance` is a cross-cutting concern document. Consider: skip entries where `service_id` doesn't appear in any task's `target_files` path component (requires service_communication_graph cross-check or post-generation validation).

---

## Fix 3: Per-Task Observability Enrichment Not Reaching Tasks

**Severity**: High — blocked by Fix 0

**File**: `src/startd8/workflows/builtin/plan_ingestion_emitter.py` (lines 323-339)

**Problem**: The per-task enrichment code at lines 323-339 IS correct — it matches `service_name` against `_obs_lookup` and injects `convention_metrics`, `transport`, `language`, `sdk_packages` into task context. But it never fires because `cfg.observability_hints` is always `None` (due to Fix 0).

**Fix**: Fix 0 resolves this. The enrichment code is already implemented and correct.

**Verify after Fix 0**: Re-run plan ingestion → check that tasks for `cartservice` have `convention_metrics`, `transport`, `language` in `config.context`.

---

## Fix 4: Contractor Does Not Inject Per-Task Observability Context

**Severity**: Medium — blocks metric-aware prompt generation

**File**: `src/startd8/contractors/prime_contractor.py` (line 1595-1603)

**Problem**: The contractor loads `self._observability_contract` from the seed (line 1597-1599) but never injects it into per-task `gen_context`. Compare with `security_contract` (lines 3465-3466) and `instrumentation_contract` (lines 3470-3471) which ARE injected.

**Fix**: After line 3471, add:
```python
# REQ-OPI-300: Thread observability contract per-task context
# Per-task fields (convention_metrics, transport, etc.) are already in
# gen_context from seed enrichment (REQ-OPI-200). The top-level contract
# is injected here for prompt builders that need the full service map.
if self._observability_contract and "observability_contract" not in gen_context:
    gen_context["observability_contract"] = self._observability_contract
```

Note: With Fix 0 + Fix 3, per-task fields (`convention_metrics`, `transport`, `language`, `sdk_packages`) will already be in `gen_context` from seed enrichment. The top-level contract injection is for the prompt builder to access the full service map if needed.

---

## Fix 5: Spec Builder Observability Section Not Tested End-to-End

**Severity**: Low — code exists but hasn't been exercised in a real run

**File**: `src/startd8/implementation_engine/spec_builder.py` (lines 269-307, 1099-1101)

**Problem**: `_build_observability_guidance_section()` IS implemented and registered at P2 priority. But because Fix 0 blocks observability data from reaching tasks, the section has never been generated in a real run. It reads `context.get("convention_metrics")` which will be populated once Fix 0 is applied.

**Fix**: No code change needed. Verify after Fix 0 that the "Observability Contract" section appears in generated spec prompts for services with convention metrics.

---

## Fix 6: `_normalize_service_name` Matching Gap

**Severity**: Low — could cause silent match failures

**File**: `src/startd8/workflows/builtin/plan_ingestion_emitter.py`

**Problem**: The normalization function strips hyphens and lowercases. But the `instrumentation_hints` keys from ContextCore use different conventions per project:
- online-boutique run-091: `cartservice`, `emailservice` (no hyphens)
- Other projects may use: `cart-service`, `cart_service`, `CartService`

The inferred `service_name` from target_files is the raw directory name (e.g., `cartservice`). If the hint key is `cart-service`, normalization must handle both sides.

**Current state**: `_normalize_service_name()` exists and is applied to both sides. Verify it handles the actual conventions seen across projects.

**Fix**: Audit the function — ensure it strips ALL of `-`, `_`, and lowercases. Test with mixed-convention inputs.

---

## Fix 7: TODO Completion Merge Not Tested with Real Data

**Severity**: Low — code exists but hasn't been exercised

**File**: `src/startd8/workflows/builtin/todo_completion_workflow.py` (lines 37-86, 180-184)

**Problem**: `_merge_observability_into_contract()` IS implemented. It merges convention metrics from the observability manifest into the instrumentation contract. But `--observability-manifest` has never successfully been passed (blocked by Fix 1 crashing the instrumentation stage).

**Fix**: Fix 1 is done. On next run, TODO completion will receive `--observability-manifest` and the merge function will execute. Verify convention metrics appear in Category B task contracts.

---

## Summary: Fix Priority Order

| # | Fix | Severity | Status | Blocks |
|---|-----|----------|--------|--------|
| 0 | `self._cfg = cfg` in plan_ingestion_workflow.py | **Critical** | TODO | Fixes 3, 4, 5 |
| 1 | Remove `--generation-profile` from run-prime-contractor.sh | High | **DONE** | Fix 7 |
| 2 | Tighten non-service filtering | Medium | Partially done | Standalone |
| 3 | Per-task observability enrichment | High | Code done, blocked by Fix 0 | Fix 5 |
| 4 | Contractor per-task injection | Medium | TODO (~3 lines) | Fix 5 |
| 5 | Spec builder observability section | Low | Code done, needs verification | Standalone |
| 6 | Normalization matching audit | Low | Needs audit | Standalone |
| 7 | TODO completion merge verification | Low | Code done, blocked by Fix 1 (now resolved) | Standalone |

**Critical path**: Fix 0 → {Fix 3, Fix 4} → Fix 5 (verify)

**After Fix 0 alone**, the following chain unblocks automatically:
- `resolve-provenance.py` produces `observability_hints` ✓ (already working)
- `PlanIngestionConfig.from_dict()` parses them ✓ (already working)
- `self._cfg` carries them to emitter → **Fix 0 enables this**
- Emitter builds `observability_contract` at seed level ✓ (code exists)
- Emitter enriches per-task context with `convention_metrics` ✓ (code exists)
- Seed serializes `observability_contract` ✓ (model field exists)
- Contractor loads `observability_contract` from seed ✓ (code exists)
- **Fix 4**: Contractor injects into gen_context → needs 3 lines
- Spec builder renders "Observability Contract" section ✓ (code exists)

**One line + three lines = full pipeline value.**

---

## Verification Plan

After applying Fix 0 + Fix 4:

```bash
# Re-run plan ingestion against existing run-091 export
cd /Users/neilyashinsky/Documents/dev/online-boutique-demo
.cap-dev-pipe/run-plan-ingestion.sh \
    --provenance .cap-dev-pipe/pipeline-output/online-boutique/run-091-20260321T1525/run-provenance.json \
    --force-prime --force-regenerate

# Verify seed has observability_contract
python3 -c "
import json
seed = json.load(open('.cap-dev-pipe/pipeline-output/online-boutique/latest/plan-ingestion/prime-context-seed.json'))
oc = seed.get('observability_contract')
print(f'observability_contract: {len(oc[\"services\"])} services' if oc else 'MISSING')
sc = seed.get('security_contract')
print(f'security_contract: PRESENT' if sc else 'MISSING')
for t in seed['tasks'][:3]:
    ctx = t['config']['context']
    print(f'  {t[\"task_id\"]}: convention_metrics={\"YES\" if ctx.get(\"convention_metrics\") else \"no\"}, transport={ctx.get(\"transport\", \"-\")}')
"
```
