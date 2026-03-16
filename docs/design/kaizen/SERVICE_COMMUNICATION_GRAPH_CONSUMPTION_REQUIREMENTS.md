# Service Communication Graph Consumption — Requirements

> **Version:** 0.1.0
> **Status:** DRAFT
> **Date:** 2026-03-16
> **Scope:** Downstream consumption of ContextCore's `service_communication_graph` in plan ingestion and context resolution — the fix for cross-service import hallucination
> **Design Principle:** [Mottainai](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) — the graph is already extracted; discarding it at the consumption boundary is waste
> **Upstream:** [SERVICE_INTERCONNECTEDNESS_REQUIREMENTS.md](~/Documents/dev/ContextCore/docs/design/SERVICE_INTERCONNECTEDNESS_REQUIREMENTS.md) (REQ-SIG-100 through REQ-SIG-104) — graph extraction in ContextCore
> **Predecessor:** [CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md](CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md) — identified the proto import hallucination root cause
> **Implementation Home:** `~/Documents/dev/startd8-sdk/` (SDK) + `~/Documents/dev/cap-dev-pipe/` (pipeline)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Status Dashboard](#2-status-dashboard)
3. [Layer 1 — Seed Population from Communication Graph (REQ-SIG-2xx)](#3-layer-1--seed-population-from-communication-graph-req-sig-2xx)
4. [Layer 2 — Context Resolution Injection (REQ-SIG-2xx cont.)](#4-layer-2--context-resolution-injection-req-sig-2xx)
5. [Verification Strategy](#5-verification-strategy)
6. [Traceability Matrix](#6-traceability-matrix)
7. [Cross-References](#7-cross-references)

---

## 1. Overview

### 1.1 Problem

ContextCore now extracts a `service_communication_graph` from plan text (REQ-SIG-100–104, implemented 2026-03-16). This graph contains per-service imports, RPC dependencies, shared modules, and transport protocols. It flows through `onboarding-metadata.json` into the pipeline.

However, the downstream consumers in startd8-sdk do not yet read this graph:

1. **Plan ingestion** (`PhaseEmitter`) carries onboarding metadata into the seed but does not populate `architectural_context.shared_modules` from the graph — that field remains empty.
2. **Context resolution** (`PipelineContextStrategy`) enriches gen_context with onboarding and architectural_context but does not inject cross-service import knowledge from the graph into individual task prompts.

The result: the proto import hallucination bug persists despite the information now being present in the onboarding metadata. The data exists but is not consumed.

### 1.2 What Changed Upstream

ContextCore `da85e34` (2026-03-16) added:

| Artifact | Content |
|----------|---------|
| `onboarding-metadata.json :: service_communication_graph` | Per-service imports, RPC calls, shared modules, proto schemas |
| `onboarding-metadata.json :: service_metadata` (source profile) | Transport protocol derived from graph, not artifact manifest |
| `ServiceMetadataEntry` model | New fields: `imports`, `rpc_dependencies`, `exposes_rpcs` |

The graph structure:

```json
{
  "service_communication_graph": {
    "services": {
      "emailservice": {
        "imports": ["demo_pb2", "demo_pb2_grpc"],
        "rpc_calls": [],
        "protocol": "grpc"
      },
      "recommendationservice": {
        "imports": ["demo_pb2", "demo_pb2_grpc", "logger"],
        "rpc_calls": [{"target_service": "productcatalogservice", "method": "ListProducts"}],
        "protocol": "grpc"
      }
    },
    "shared_modules": {
      "demo_pb2": {"type": "proto_stub", "used_by": ["emailservice", "recommendationservice"]},
      "logger": {"type": "shared_lib", "used_by": ["emailservice", "recommendationservice"]}
    },
    "proto_schemas": ["protos/demo.proto"]
  }
}
```

### 1.3 Data Flow

```
ContextCore                          cap-dev-pipe                     startd8-sdk
────────────                         ────────────                     ───────────
init_from_plan_ops.py
  _extract_service_communication_graph()
  ↓ stored in .contextcore.yaml
onboarding.py
  build_onboarding_metadata()
  ↓ service_communication_graph in JSON
                                     resolve-provenance.py
                                     ↓ onboarding-metadata.json
                                     plan_ingestion_workflow.py
                                     ↓ PhaseEmitter.emit()

                        ┌── REQ-SIG-200 ──┐
                        │ Read graph from  │
                        │ onboarding,      │
                        │ populate         │
                        │ arch_context     │
                        │ .shared_modules  │
                        └────────┬────────┘
                                 ↓
                        prime-context-seed.json
                                 ↓
                        ┌── REQ-SIG-201 ──┐
                        │ resolve_context()│
                        │ inject inherited │
                        │ imports from     │
                        │ dependency tasks │
                        └────────┬────────┘
                                 ↓
                        gen_context for PI-004
                          inherited_imports: [demo_pb2, demo_pb2_grpc]
```

---

## 2. Status Dashboard

| ID | Requirement | Status | Priority | Implementation File |
|----|------------|--------|----------|-------------------|
| REQ-SIG-200 | Plan ingestion reads `service_communication_graph` | TODO | P1 | `plan_ingestion_emitter.py` |
| REQ-SIG-201 | Context resolution injects dependency imports | TODO | P1 | `context_strategy.py` |

---

## 3. Layer 1 — Seed Population from Communication Graph (REQ-SIG-200)

### REQ-SIG-200: Plan Ingestion Reads `service_communication_graph`

Plan ingestion's EMIT phase (`PhaseEmitter.emit()`) SHALL read `service_communication_graph` from onboarding metadata and use it to populate the seed.

#### 3.1 Populate `architectural_context.shared_modules`

When `onboarding_metadata.service_communication_graph.shared_modules` is present and non-empty, `PhaseEmitter._derive_shared_context()` SHALL populate `architectural_context["shared_modules"]` with the shared module entries.

Current state (from Kaizen Seed Utilization analysis):
```python
# architectural_context has 9 keys, 7 empty
architectural_context = {
    "shared_modules": [],     # ← always empty today
    "constraints": [],
    "preferences": [],
    ...
}
```

Target state:
```python
architectural_context = {
    "shared_modules": [
        {"name": "demo_pb2", "type": "proto_stub", "used_by": ["emailservice", "recommendationservice"]},
        {"name": "demo_pb2_grpc", "type": "proto_stub", "used_by": ["emailservice", "recommendationservice"]},
    ],
    ...
}
```

**Acceptance:** After plan ingestion with a ContextCore export containing a `service_communication_graph`, the seed's `architectural_context.shared_modules` is non-empty and contains at least the proto stub modules.

#### 3.2 Thread Per-Service Imports into Task Context

For each task in the seed, `PhaseEmitter` SHALL look up the task's target file directory (e.g., `src/emailservice/`) in the graph's `services` dict and attach the service's `imports` list to the task metadata.

```python
# In _derive_tasks() or _run_enrichment_pipeline():
for task in tasks:
    target_dir = _extract_service_dir(task["target_file"])  # "emailservice"
    if target_dir in comm_graph["services"]:
        task["service_imports"] = comm_graph["services"][target_dir]["imports"]
        task["service_protocol"] = comm_graph["services"][target_dir]["protocol"]
```

**Acceptance:** Tasks targeting `src/emailservice/*.py` have `service_imports: ["demo_pb2", "demo_pb2_grpc"]` in their task metadata within the seed.

#### 3.3 Forward Graph to Seed

The full `service_communication_graph` SHALL be included in the seed under a top-level `service_communication_graph` key so that downstream consumers (context resolution, post-mortem) can access it without re-parsing onboarding metadata.

**Acceptance:** `prime-context-seed.json` contains a `service_communication_graph` key matching the structure from onboarding metadata.

---

## 4. Layer 2 — Context Resolution Injection (REQ-SIG-201)

### REQ-SIG-201: Context Resolution Injects Dependency Imports

`PipelineContextStrategy.resolve_context()` SHALL, when a task has `depends_on` entries, inject `inherited_imports` from the dependency tasks' services into the gen_context.

#### 4.1 Dependency Import Extraction

When building gen_context for task T that depends on tasks [D1, D2, ...]:

1. Look up each dependency task's target file directory
2. Find matching services in `service_communication_graph`
3. Collect the `imports` lists from those services
4. Deduplicate and add as `inherited_imports` in gen_context

```python
# In resolve_context() or a helper:
def _extract_inherited_imports(
    task: Dict,
    all_tasks: Dict[str, Dict],
    comm_graph: Dict,
) -> List[str]:
    inherited = set()
    for dep_id in task.get("depends_on", []):
        dep_task = all_tasks.get(dep_id, {})
        dep_dir = _extract_service_dir(dep_task.get("target_file", ""))
        if dep_dir in comm_graph.get("services", {}):
            inherited.update(comm_graph["services"][dep_dir]["imports"])
    return sorted(inherited)
```

**Acceptance:** When generating PI-004 (`email_client.py`) which depends on PI-003 (`email_server.py`), the gen_context includes `inherited_imports: ["demo_pb2", "demo_pb2_grpc"]` derived from PI-003's service entry in the communication graph.

#### 4.2 Enrichment Field Registration

Add `"service_communication_graph"` to `PipelineContextStrategy.ENRICHMENT_FIELDS` so the graph flows through the standard enrichment pipeline:

```python
ENRICHMENT_FIELDS: typing.Tuple[str, ...] = (
    "onboarding_metadata",
    "architectural_context",
    "design_calibration",
    "service_communication_graph",  # NEW
)
```

**Acceptance:** `PipelineContextStrategy.post_generation_validate()` warns when `pipeline.service_communication_graph` is missing from resolved context.

#### 4.3 Spec Builder Integration

`spec_builder.py` SHALL include `inherited_imports` in the LLM prompt when present. The import list should appear near the top of the task specification, before the implementation instructions.

Suggested prompt section:
```
## Available Imports (from dependency services)

The following modules are available for import — these are used by services this task depends on:
- demo_pb2
- demo_pb2_grpc
```

**Acceptance:** The LLM prompt for PI-004 contains the inherited import list. The generated code uses `import demo_pb2` instead of hallucinated module paths.

---

## 5. Verification Strategy

### 5.1 Unit Tests

| Test | File | Validates |
|------|------|-----------|
| Shared modules populated from graph | `test_plan_ingestion_emitter.py` | REQ-SIG-200 §3.1 |
| Per-task service_imports attached | `test_plan_ingestion_emitter.py` | REQ-SIG-200 §3.2 |
| Graph forwarded to seed | `test_plan_ingestion_emitter.py` | REQ-SIG-200 §3.3 |
| Inherited imports extracted | `test_context_strategy.py` | REQ-SIG-201 §4.1 |
| Enrichment field registered | `test_context_strategy.py` | REQ-SIG-201 §4.2 |
| Empty graph backward compat | both | No failure when graph absent |

### 5.2 Integration Test (Kaizen Run)

Re-run the online-boutique pipeline (run-051 equivalent) with ContextCore export containing `service_communication_graph`. Verify:

1. PI-004 (`email_client.py`) generates `import demo_pb2` (not hallucinated path)
2. PI-007 (`client.py`) generates correct proto imports
3. Pass rate remains 17/17 or improves

### 5.3 Regression Safety

The graph is additive — all new fields are optional. Tasks without `service_imports` or `inherited_imports` fall back to existing behavior. `PipelineContextStrategy` only enriches when the field is present.

---

## 6. Traceability Matrix

| Requirement | Upstream Dependency | Implementation File | Estimated Lines |
|------------|-------------------|-------------------|----------------|
| REQ-SIG-200 §3.1 | REQ-SIG-104 (ContextCore) | `plan_ingestion_emitter.py` | ~15 |
| REQ-SIG-200 §3.2 | REQ-SIG-104 (ContextCore) | `plan_ingestion_emitter.py` | ~15 |
| REQ-SIG-200 §3.3 | REQ-SIG-104 (ContextCore) | `plan_ingestion_emitter.py` | ~5 |
| REQ-SIG-201 §4.1 | REQ-SIG-200 | `context_strategy.py` | ~20 |
| REQ-SIG-201 §4.2 | REQ-SIG-200 | `context_strategy.py` | ~3 |
| REQ-SIG-201 §4.3 | REQ-SIG-201 §4.1 | `spec_builder.py` | ~10 |

**Total estimated scope:** ~70 lines across 3 files.

---

## 7. Cross-References

| Document | Relationship |
|----------|-------------|
| [CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md](CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md) | Root cause analysis — Section 5 identified context_resolution.py as the fix location |
| [SERVICE_INTERCONNECTEDNESS_REQUIREMENTS.md](~/Documents/dev/ContextCore/docs/design/SERVICE_INTERCONNECTEDNESS_REQUIREMENTS.md) | Upstream — graph extraction in ContextCore (REQ-SIG-100–104, implemented) |
| [REQ_CROSS_CUTTING_CONTEXT_LOSS.md](~/Documents/dev/ContextCore/docs/design/requirements/REQ_CROSS_CUTTING_CONTEXT_LOSS.md) | ContextCore-side requirements (REQ-CCL-100–500, implemented) |
| [REQ_GENERATION_PROFILES.md](~/Documents/dev/ContextCore/docs/design/requirements/REQ_GENERATION_PROFILES.md) | REQ-GP-301 — source profile derives service_metadata from graph (implemented) |
| [KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md](KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md) | Related — seed field consumption observability (REQ-KSU-1xx) |
| [Mottainai Design Principle](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Gaps 10, 11 — onboarding metadata not injected, no architectural context |
