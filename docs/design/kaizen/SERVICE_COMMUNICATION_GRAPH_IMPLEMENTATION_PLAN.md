# Implementation Plan: Service Communication Graph Consumption (REQ-SIG-200/201)

**Status:** Draft
**Date:** 2026-03-16
**Requirements:** [SERVICE_COMMUNICATION_GRAPH_CONSUMPTION_REQUIREMENTS.md](SERVICE_COMMUNICATION_GRAPH_CONSUMPTION_REQUIREMENTS.md)
**Estimated Scope:** ~85 lines across 5 files, 3 phases

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

## Phase 3: Context Resolution + Prompt Injection (~20 lines)

### Step 3.1: Add graph to enrichment fields (REQ-SIG-201 §4.2)

**File:** `src/startd8/contractors/context_strategy.py`

**In `PipelineContextStrategy.ENRICHMENT_FIELDS` (line 144):**

```python
    ENRICHMENT_FIELDS: typing.Tuple[str, ...] = (
        "onboarding_metadata",
        "architectural_context",
        "design_calibration",
        "service_communication_graph",  # REQ-SIG-201
    )
```

### Step 3.2: Extract and render `inherited_imports` in spec builder (REQ-SIG-201 §4.3)

**File:** `src/startd8/implementation_engine/spec_builder.py`

**In `build_spec_prompt()` (~line 631),** after the requirements section, add:

```python
    # --- REQ-SIG-201: inherited imports from dependency services ---
    inherited_imports = context.pop("inherited_imports", None) or context.pop(
        "service_imports", None
    )
    inherited_imports_section = ""
    if inherited_imports and isinstance(inherited_imports, list):
        import_items = "\n".join(f"- `{m}`" for m in inherited_imports)
        inherited_imports_section = (
            "\n## Available Imports (from dependency services)\n"
            "The following modules are used by services this task depends on — "
            "import them directly instead of inventing alternative paths:\n"
            f"{import_items}\n"
        )
```

Then include `inherited_imports_section` in the final prompt assembly.

### Step 3.3: Dependency import extraction helper (REQ-SIG-201 §4.1)

**File:** `src/startd8/contractors/context_seed/shared.py` or a new `sig_utils.py`

```python
def extract_inherited_imports(
    task_id: str,
    task_index: Dict[str, Any],
    comm_graph: Dict[str, Any],
) -> List[str]:
    """Extract imports from dependency tasks' services in the communication graph."""
    task = task_index.get(task_id)
    if not task:
        return []
    services = comm_graph.get("services", {})
    inherited: set[str] = set()
    for dep_id in getattr(task, "depends_on", []):
        dep = task_index.get(dep_id)
        if not dep:
            continue
        for tf in getattr(dep, "target_files", []):
            svc_dir = Path(tf).parts[1] if len(Path(tf).parts) > 1 else ""
            if svc_dir in services:
                inherited.update(services[svc_dir].get("imports", []))
    return sorted(inherited)
```

### Step 3.4: Tests

**File:** `tests/unit/contractors/test_sig_resolution.py`
- `test_inherited_imports_from_dependency` — Dep has imports → inherited
- `test_no_deps_empty_imports` — No depends_on → empty list
- `test_dep_not_in_graph` — Dep target not in graph → empty

**File:** `tests/unit/test_spec_builder_sig.py`
- `test_inherited_imports_rendered_in_prompt` — Imports appear in spec
- `test_no_imports_no_section` — Empty imports → no section in prompt

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
| `src/startd8/workflows/builtin/plan_ingestion_emitter.py` | 2 | Extract graph from onboarding, thread to manifest_context, per-task imports |
| `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | 2 | Merge graph modules into architectural context |
| `src/startd8/contractors/context_strategy.py` | 3 | Add enrichment field |
| `src/startd8/implementation_engine/spec_builder.py` | 3 | Render inherited imports section |
| `src/startd8/contractors/context_seed/shared.py` | 3 | `extract_inherited_imports()` helper |

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Service directory heuristic (`parts[1]`) is project-specific | Graph keys match plan headings; fallback to no-op if no match |
| Large graphs inflate seed size | Graph is typically <5KB; negligible vs existing 50KB+ seeds |
| Backward compat for seeds without graph | All fields are `Optional`, default `None`; existing seeds unaffected |
| `_derive_architectural_context` signature change | No signature change — graph flows through existing `manifest_context` dict |
