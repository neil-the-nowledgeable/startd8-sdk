# Artisan Workflow: ContextCore Data Flow Fixes

**Created:** 2026-02-14
**Scope:** Close the data flow gaps between ContextCore export output and the artisan
workflow's consumption of that data. These are targeted enhancements — no structural
overhaul of the artisan pipeline is needed.

**Prerequisite:** ContextCore-side fixes tracked in
`ContextCore/docs/plans/EXPORT_PIPELINE_DOC_CODE_ALIGNMENT.md` (especially C1: generating
`design_calibration_hints` in `onboarding.py`).

---

## Problem Summary

The ContextCore export pipeline produces rich enrichment data in `onboarding-metadata.json`,
and plan ingestion propagates it into the artisan context seed. But the artisan workflow's
phase handlers only consume a subset of this data. Three categories of data are available
in the seed but unused:

1. **Provenance chain** — `source_checksum` is in the seed but never verified or recorded
2. **Parameter metadata** — `parameter_sources` and `semantic_conventions` are available
   but never passed to LLM prompts
3. **Output conventions** — `output_path`/`output_ext` from onboarding are available but
   SCAFFOLD doesn't use them

---

## Fix Plan

### Fix 1: Provenance Chain — `source_checksum` verification and recording

**Priority:** High
**Files:** `src/startd8/contractors/context_seed_handlers.py`
**Estimated scope:** ~30 lines across 2 handlers

#### 1a. PLAN phase: verify `source_checksum` freshness

**Where:** `PlanPhaseHandler.execute()` around line 510 (after `seed_data` is loaded)

**What:** Read `source_checksum` from the seed's `artifacts` dict. If present, store it
in the shared context so downstream phases can access it. Log a warning if absent.

```python
# After line 511 (context["design_calibration"] = ...)
source_checksum = (seed_data.get("artifacts") or {}).get("source_checksum")
context["source_checksum"] = source_checksum
if source_checksum:
    logger.info("PLAN phase: source_checksum present — provenance chain active: %s", source_checksum[:16])
else:
    logger.warning("PLAN phase: source_checksum absent in seed — provenance chain broken")
```

**Rationale:** This is the earliest point where we can detect a broken provenance chain.
If the export was re-run but the seed is stale, the checksum won't match. While we can't
verify against the original `.contextcore.yaml` from here (that's ContextCore's Gate 1),
we can at least ensure the seed carries the checksum and surface its absence.

#### 1b. FINALIZE phase: record `source_checksum` in `generation-manifest.json`

**Where:** `FinalizePhaseHandler._write_manifest()` around line 3327

**What:** Add a `provenance` key to the manifest with `source_checksum` from context:

```python
manifest = {
    "workflow_version": "0.4.0",
    "provenance": {
        "source_checksum": context.get("source_checksum"),
        "enriched_seed_path": str(context.get("enriched_seed_path", "")),
    },
    "artifacts": artifacts,
    "task_status": task_status,
    "summary": { ... },
}
```

**Rationale:** This closes the provenance chain — Gate 3 (ContextCore's `a2a-diagnose --artisan-dir`)
can now read `generation-manifest.json` and compare `source_checksum` against the export's
onboarding metadata.

---

### Fix 2: Consume `parameter_sources` in DESIGN and IMPLEMENT

**Priority:** Medium
**Files:** `src/startd8/contractors/context_seed_handlers.py`
**Estimated scope:** ~40 lines across 2 handlers

#### 2a. Plan ingestion: propagate `parameter_sources` to seed

**Where:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py` `_phase_emit()`
around line 2097 (where onboarding fields are extracted into artifacts)

**What:** If onboarding metadata contains `parameter_sources`, include it in the seed artifacts:

```python
# After the existing example_artifacts extraction (~line 2107)
ps = onboarding.get("parameter_sources")
if ps and isinstance(ps, dict):
    artifacts["parameter_sources"] = ps
```

#### 2b. PLAN phase: store `parameter_sources` in context

**Where:** `PlanPhaseHandler.execute()` after line 514

```python
context["parameter_sources"] = (seed_data.get("artifacts") or {}).get("parameter_sources", {})
```

#### 2c. DESIGN phase: inject into design prompts

**Where:** `DesignPhaseHandler._design_single_task()` around line 700

**What:** When building the design prompt for each task, include relevant `parameter_sources`
entries that match the task's artifact types. This tells the LLM which manifest/CRD fields
each parameter comes from, improving derivation rule fidelity.

```python
# Get parameter sources relevant to this task's artifact types
task_param_sources = {}
all_param_sources = context.get("parameter_sources", {})
for atype in task.artifact_types_addressed:
    if atype in all_param_sources:
        task_param_sources[atype] = all_param_sources[atype]

if task_param_sources:
    # Append to the design prompt context
    param_context = "Parameter sources (from ContextCore manifest):\n"
    for atype, sources in task_param_sources.items():
        param_context += f"  {atype}: {json.dumps(sources, indent=2)}\n"
```

#### 2d. IMPLEMENT phase: inject into code generation context

**Where:** `ImplementPhaseHandler._tasks_to_chunks()` around line 1724

**What:** Add `parameter_sources` to chunk metadata so the `LeadContractorCodeGenerator`
has explicit mapping of which fields to read for each parameter.

```python
# In the chunk metadata dict
"parameter_sources": context.get("parameter_sources", {}).get(
    task.artifact_types_addressed[0], {}
) if task.artifact_types_addressed else {},
```

**Rationale:** `parameter_sources` is the most actionable onboarding field for code generation.
It tells the generator *exactly* which manifest field produces each template parameter.
Without it, the LLM has to infer parameter origins from the design doc text alone.

---

### Fix 3: Consume `semantic_conventions` in DESIGN and IMPLEMENT

**Priority:** Medium
**Files:** `src/startd8/contractors/context_seed_handlers.py`
**Estimated scope:** ~30 lines across 2 handlers

#### 3a. Plan ingestion: propagate `semantic_conventions` to seed

**Where:** Same location as Fix 2a in `_phase_emit()`

```python
sc = onboarding.get("semantic_conventions")
if sc and isinstance(sc, dict):
    artifacts["semantic_conventions"] = sc
```

#### 3b. PLAN phase: store in context

```python
context["semantic_conventions"] = (seed_data.get("artifacts") or {}).get("semantic_conventions", {})
```

#### 3c. DESIGN and IMPLEMENT: inject into prompts

**What:** Append semantic conventions (metric names, label key conventions, namespace
patterns) to design and implementation prompts. This is especially important for
dashboard JSON and PrometheusRule generation where metric naming must follow conventions.

```python
sem_conv = context.get("semantic_conventions", {})
if sem_conv:
    conventions_text = "Semantic conventions:\n"
    for key, val in sem_conv.items():
        conventions_text += f"  {key}: {val}\n"
    # Append to prompt context
```

**Rationale:** Without semantic conventions, generated dashboards and alert rules use
generic metric names that don't match the project's actual telemetry surface.

---

### Fix 4: FINALIZE manifest: include `source_checksum` for Gate 3

**Priority:** Medium (merged with Fix 1b)
**Note:** This is already covered by Fix 1b above. Listed separately for traceability
against the audit finding.

---

### Fix 5: SCAFFOLD — optionally use `output_conventions` from onboarding

**Priority:** Low
**Files:** `src/startd8/contractors/context_seed_handlers.py`
**Estimated scope:** ~15 lines

**Where:** `ScaffoldPhaseHandler.execute()` around line 570

**What:** If onboarding metadata includes per-artifact-type `output_path` and `output_ext`
conventions, use them to validate or supplement the directory creation logic. Currently
SCAFFOLD creates directories from `task.target_files` paths, which is correct — this
fix adds a secondary validation that the output paths match onboarding conventions.

```python
output_conventions = context.get("output_conventions", {})
if output_conventions:
    for task in tasks:
        for atype in task.artifact_types_addressed:
            expected_ext = output_conventions.get(atype, {}).get("output_ext")
            if expected_ext:
                for tf in task.target_files:
                    if not tf.endswith(expected_ext):
                        logger.warning(
                            "SCAFFOLD: task %s file %s doesn't match expected extension %s for %s",
                            task.task_id, tf, expected_ext, atype,
                        )
```

**Rationale:** This is a soft validation — it warns but doesn't block. The seed's
`target_files` are authoritative (they come from plan ingestion), but onboarding
conventions provide a second signal for catching misconfigurations.

---

## Implementation Order

1. **Fix 1** (High) — Provenance chain: source_checksum in PLAN + FINALIZE manifest
2. **Fix 2** (Medium) — parameter_sources propagation and consumption
3. **Fix 3** (Medium) — semantic_conventions propagation and consumption
4. **Fix 5** (Low) — SCAFFOLD output_conventions validation

Fixes 2 and 3 can be implemented in parallel since they follow the same pattern:
plan ingestion propagation → PLAN phase context storage → DESIGN/IMPLEMENT injection.

---

## Files Changed

| File | Fixes | Lines Added (est) |
|------|-------|-------------------|
| `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | 2a, 3a | ~10 |
| `src/startd8/contractors/context_seed_handlers.py` | 1a, 1b, 2b-d, 3b-c, 5 | ~80 |
| **Total** | | **~90** |

---

## Testing Strategy

### Unit tests

Add to `tests/unit/contractors/test_context_seed_handlers.py`:

- `test_plan_phase_extracts_source_checksum` — verify context has source_checksum after PLAN
- `test_plan_phase_warns_missing_source_checksum` — verify warning when absent
- `test_finalize_manifest_includes_provenance` — verify generation-manifest.json has provenance block
- `test_design_phase_injects_parameter_sources` — verify param sources in design prompt
- `test_implement_phase_injects_parameter_sources` — verify param sources in chunk metadata
- `test_scaffold_warns_mismatched_extension` — verify warning for output_ext mismatch

### Integration tests

- Run a full dry-run artisan workflow with a seed that includes onboarding enrichment fields
  and verify the generation-manifest.json output contains the provenance block
- Run `contextcore contract a2a-diagnose --artisan-dir` against the output and verify
  Gate 3 can read the source_checksum

---

## Success Criteria

- `source_checksum` from the ContextCore export is verifiable at every pipeline stage:
  export → onboarding → plan ingestion seed → artisan context → generation manifest
- `parameter_sources` and `semantic_conventions` appear in design/implementation prompts
  when present in onboarding metadata
- No regressions for artisan workflows that don't use ContextCore enrichment (all new
  context keys default to empty dict/None)
- Gate 3 (`a2a-diagnose --artisan-dir`) can read provenance from the generation manifest
