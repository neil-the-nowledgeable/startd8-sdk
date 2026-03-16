# Implementation Plan: Service Communication Graph Consumption (REQ-SIG-200/201)

**Status:** Implemented (Phases 1-3)
**Date:** 2026-03-16
**Requirements:** [SERVICE_COMMUNICATION_GRAPH_CONSUMPTION_REQUIREMENTS.md](SERVICE_COMMUNICATION_GRAPH_CONSUMPTION_REQUIREMENTS.md)
**Estimated Scope:** ~80 lines across 5 files, 3 phases
**Prerequisite Refactor:** ArtisanContextSeed → ContextSeed unification (commit `5a79095`)

---

## Overview

Wire ContextCore's `service_communication_graph` from `onboarding-metadata.json` through plan ingestion into the context seed and LLM prompts, so that cross-service import dependencies are available to the code generation engine. This fixes the proto import hallucination root cause.

---

## Phase 1: Seed Infrastructure (~25 lines)

The graph needs a home in the seed model and builder before it can flow through the pipeline.

### Step 1.1: Add `service_communication_graph` to `ContextSeed` (REQ-SIG-200 §3.3)

**File:** `src/startd8/seeds/models.py`

**Add field** after `service_metadata` (line 52):

```python
    service_metadata: Optional[Dict[str, Any]] = None
    service_communication_graph: Optional[Dict[str, Any]] = None  # REQ-SIG-200
```

**Add serialization** in `to_dict()` after `service_metadata` block (line 82):

```python
        if self.service_communication_graph is not None:
            d["service_communication_graph"] = self.service_communication_graph
```

### Step 1.2: Add builder support

**File:** `src/startd8/seeds/builder.py`

**In `__init__()`,** add after `self._service_metadata` (line 77):

```python
        self._service_communication_graph: Optional[Dict[str, Any]] = None
```

**Add setter method** after `set_service_metadata()` (~line 288):

```python
    def set_service_communication_graph(
        self, graph: Optional[Dict[str, Any]]
    ) -> "SeedBuilder":
        """Set the service communication graph from ContextCore onboarding."""
        self._service_communication_graph = graph
        return self
```

**In `_to_dict()`,** add to `ContextSeed()` constructor after `service_metadata`:

```python
            service_communication_graph=self._service_communication_graph,
```

### Step 1.3: Tests

**File:** `tests/unit/seeds/test_models_sig.py`
- `test_seed_has_service_communication_graph` — `to_dict()` includes field
- `test_seed_graph_default_none` — Default is `None`, omitted from dict
- `test_seed_graph_round_trip` — Graph data survives to_dict()

**File:** `tests/unit/seeds/test_builder_sig.py`
- `test_builder_sets_graph` — Builder with graph → seed contains it
- `test_builder_graph_default_none` — No graph → not in seed

---

## Phase 2: Plan Ingestion Wiring (~40 lines)

Extract the graph from onboarding, merge with architectural context, and thread per-task imports.

### Step 2.1: Extract graph in `_build_seed_artifacts()` (REQ-SIG-200 §3.3)

**File:** `src/startd8/workflows/builtin/plan_ingestion_emitter.py`

**In `_build_seed_artifacts()` (~line 781),** after the existing onboarding extraction block, extract the graph:

```python
            # REQ-SIG-200: forward service communication graph to seed
            scg = onboarding_resolved.get("service_communication_graph")
            if scg and isinstance(scg, dict) and not is_omitted(scg):
                artifacts_out["service_communication_graph"] = scg
```

### Step 2.2: Merge graph modules into `architectural_context.shared_modules` (REQ-SIG-200 §3.1)

**File:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

**In `_derive_architectural_context()` (~line 3004),** after the file-counter-based `shared_modules` computation, merge graph-derived modules:

```python
        # REQ-SIG-200: merge service communication graph shared modules
        onboarding_graph = manifest_context.get("service_communication_graph", {})
        graph_shared = onboarding_graph.get("shared_modules", {})
        if graph_shared and isinstance(graph_shared, dict):
            for mod_name, mod_info in graph_shared.items():
                if isinstance(mod_info, dict):
                    ctx["shared_modules"].append({
                        "name": mod_name,
                        "type": mod_info.get("type", "unknown"),
                        "used_by": mod_info.get("used_by", []),
                    })
            if graph_shared:
                logger.info(
                    "Architectural context: merged %d shared modules from communication graph",
                    len(graph_shared),
                )
```

**Note:** `_derive_architectural_context` currently takes `(parsed_plan, manifest_context)`. The graph needs to flow through `manifest_context`. This is handled in Step 2.3.

### Step 2.3: Thread graph through emitter to architectural context derivation

**File:** `src/startd8/workflows/builtin/plan_ingestion_emitter.py`

**In `emit()` (~line 172),** pass the graph via `manifest_context` before `_derive_shared_context()`:

```python
        # REQ-SIG-200: forward graph to architectural context derivation
        if onboarding_resolved:
            _scg = onboarding_resolved.get("service_communication_graph")
            if _scg and isinstance(_scg, dict):
                manifest_context = dict(manifest_context) if manifest_context else {}
                manifest_context["service_communication_graph"] = _scg
```

### Step 2.4: Thread per-task service imports (REQ-SIG-200 §3.2)

**File:** `src/startd8/workflows/builtin/plan_ingestion_emitter.py`

**In `_derive_tasks()` or `_run_enrichment_pipeline()`,** after tasks are constructed, attach per-service imports:

```python
        # REQ-SIG-200 §3.2: attach per-service imports to task metadata
        if onboarding_resolved:
            _scg = onboarding_resolved.get("service_communication_graph", {})
            _services = _scg.get("services", {})
            if _services:
                for task in tasks:
                    _tf = task.get("config", {}).get("context", {}).get("target_files", [])
                    for tf in _tf:
                        _svc_dir = Path(tf).parts[1] if len(Path(tf).parts) > 1 else ""
                        if _svc_dir in _services:
                            svc = _services[_svc_dir]
                            task.setdefault("config", {}).setdefault("context", {})
                            task["config"]["context"]["service_imports"] = svc.get("imports", [])
                            task["config"]["context"]["service_protocol"] = svc.get("protocol", "")
                            break  # first match wins
```

**Note:** The service directory extraction heuristic (`parts[1]`) matches the plan's `src/<service>/` structure. This is project-specific; a more general approach would normalize against the graph's service keys.

### Step 2.5: Tests

**File:** `tests/unit/workflows/test_sig_consumption.py`
- `test_graph_extracted_to_seed_artifacts` — Graph in onboarding → in seed artifacts
- `test_graph_omitted_marker_excluded` — Marker dict → not in seed
- `test_shared_modules_merged_from_graph` — Graph modules appear in arch context
- `test_per_task_service_imports` — Task targeting `src/emailservice/` gets imports
- `test_no_graph_backward_compat` — No graph in onboarding → no failure

---

## Phase 3: Context Resolution — Strategy 3 (~20 lines)

### Key Design Decision: Enhance Existing Mechanism

The gap analysis revealed that `PrimeContractorWorkflow._collect_dependency_imports()` already implements a 2-strategy dependency import extraction pipeline (Strategy 1: description parsing, Strategy 2: forward manifest). Rather than creating a parallel `inherited_imports` path through `PipelineContextStrategy.ENRICHMENT_FIELDS` → `context_resolution.py` → `spec_builder.py`, the graph is injected as **Strategy 3** into the existing mechanism.

This means:
- **No changes to `context_strategy.py`** — enrichment fields are the wrong mechanism
- **No changes to `context_resolution.py`** — the graph doesn't need a new IMP-P6 block
- **No changes to `spec_builder.py`** — `_build_dependency_imports_section()` already renders the output
- **No new helper function** — the matching logic is inline in `_collect_dependency_imports`

### Step 3.1: Add graph to `SeedContext` (REQ-SIG-201)

**File:** `src/startd8/contractors/prime_contractor.py`

Add `service_communication_graph` field to the `SeedContext` dataclass and populate it in `_init_seed_context()` from `seed_data.get("service_communication_graph")`.

### Step 3.2: Strategy 3 in `_collect_dependency_imports` (REQ-SIG-201)

**File:** `src/startd8/contractors/prime_contractor.py`

After Strategy 2 (forward manifest), add:

```python
# Strategy 3: Service communication graph (REQ-SIG-201)
comm_graph = self._seed_context.service_communication_graph if self._seed_context else None
if comm_graph and dep.target_files:
    graph_services = comm_graph.get("services", {})
    for tf in dep.target_files:
        # Match target file path components against graph service keys (case-insensitive)
        for part in Path(tf).parts:
            part_lower = part.lower()
            for svc_key in graph_services:
                if svc_key.lower() == part_lower:
                    modules.update(graph_services[svc_key].get("imports", []))
                    break
```

The matching uses case-insensitive comparison of each path component against all graph service keys, solving Gap 4 (fragile heuristic).

### Step 3.3: Tests

**File:** `tests/unit/test_sig_consumption.py`
- `test_graph_provides_imports` — Strategy 3 finds imports from graph
- `test_no_graph_no_crash` — Without graph, Strategy 3 is silently skipped
- `test_case_insensitive_match` — Graph key "EmailService" matches path "emailservice/"

---

## Dependency Graph

```
Phase 1 (seed infrastructure)
├─ 1.1 ContextSeed field
├─ 1.2 SeedBuilder setter
└─ 1.3 Tests

Phase 2 (plan ingestion) ← depends on Phase 1
├─ 2.1 Extract graph in artifacts
├─ 2.2 Merge into arch context ← depends on 2.3
├─ 2.3 Thread graph through manifest_context
├─ 2.4 Per-task service imports
└─ 2.5 Tests

Phase 3 (context resolution) ← depends on Phase 2
├─ 3.1 Enrichment field registration
├─ 3.2 Spec builder rendering
├─ 3.3 Dependency import helper
└─ 3.4 Tests
```

---

## Files Modified Summary

| File | Phase | Changes |
|------|-------|---------|
| `src/startd8/seeds/models.py` | 1 | Add `service_communication_graph` field + serialization |
| `src/startd8/seeds/builder.py` | 1 | Add `_service_communication_graph` + setter + build wiring |
| `src/startd8/workflows/builtin/plan_ingestion_emitter.py` | 2 | Extract graph from onboarding, thread to manifest_context, pass to ContextSeed |
| `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | 2 | Merge graph modules into architectural context |
| `src/startd8/contractors/prime_contractor.py` | 3 | `SeedContext.service_communication_graph` field + Strategy 3 in `_collect_dependency_imports` |

**Not modified (gap analysis corrections):**
- `context_strategy.py` — enrichment fields are the wrong mechanism for this data flow
- `context_resolution.py` — graph reaches prompts via existing `_collect_dependency_imports` → `_build_dependency_imports_section`
- `spec_builder.py` — `_build_dependency_imports_section()` already renders dependency imports

---

## Gap Analysis Findings (2026-03-16)

| Gap | Severity | Finding | Resolution |
|-----|----------|---------|-----------|
| 1 | Critical | Two parallel seed models (`ArtisanContextSeed` vs `ContextSeed`) — emitter used the wrong one | Unified in commit `5a79095`; `ArtisanContextSeed` is now an alias |
| 2 | Medium | Plan targeted `ENRICHMENT_FIELDS` but actual LLM context flows through `_collect_dependency_imports` | Strategy 3 added to existing mechanism; no new parallel path |
| 3 | Low | `PIPELINE_SIGNAL_KEYS` not updated | Intentionally deferred — graph is optional, absent in existing seeds |
| 4 | Low | `Path(tf).parts[1]` heuristic is project-specific | Case-insensitive full-component matching against graph keys |
| 5 | Low | Helper location (shared.py vs seeds/utils.py) | No separate helper needed — logic is inline in Strategy 3 |
| 6 | Detail | Missing prompt insertion point | N/A — existing `_build_dependency_imports_section` handles rendering |
| AC-1 | Tech debt | `_derive_shared_context` 5-tuple | Documented; `manifest_context` piggybacking works for now |
| AC-2 | Tech debt | Duplicate emit methods (15 params each) | Easier to consolidate now that both construct `ContextSeed` |
| AC-3 | Resolved | Duplicate `to_dict()` in two models | Eliminated by ArtisanContextSeed → ContextSeed unification |

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Service key matching is case-insensitive only | Covers the common case (plan headings vs path components); false matches unlikely since service names are distinctive |
| Large graphs inflate seed size | Graph is typically <5KB; negligible vs existing 50KB+ seeds |
| Backward compat for seeds without graph | All fields are `Optional`, default `None`; existing seeds unaffected |
| `_derive_architectural_context` signature change | No signature change — graph flows through existing `manifest_context` dict |
