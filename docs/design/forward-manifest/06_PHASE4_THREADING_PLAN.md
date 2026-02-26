# Phase 4 Implementation Plan: Pipeline Threading

This implementation plan breaks down the exact code modifications required to satisfy the `Phase_4_Pipeline_Threading_Requirements.md` specifications.

## 1. Goal

Integrate the `ForwardManifest` effectively into the StartD8 pipeline, ensuring it transports state reliably via the `ArtisanContextSeed` and JSON handoffs, and injects actionable constraint strings into the `DESIGN` and `IMPLEMENT` LLM prompts safely without breaking backward compatibility.

*Note on Phase 3 Alignment:* The creation of the `ForwardManifest` (including `explicit` YAML contracts, `inferred` deterministic extraction, and `tentative` LLM discovery) is fully completed during the Plan Ingestion workflow (specifically ending at the `REFINE` phase). Thus, Phase 4 treats the manifest as a fully-formed, read-only payload that is simply transported and rendered during the Artisan execution phases.

## 2. Completed Scaffolding (Baseline)

The following components have been implemented and verified to provide the structural foundation for Phase 4 threading:

* **[COMPLETED] Seed Threading:** `ArtisanContextSeed` now includes an optional `forward_manifest` dictionary field (`src/startd8/workflows/builtin/plan_ingestion_models.py`).
* **[COMPLETED] Extractor Bridge:** `map_forward_contracts_for_task` is implemented in `src/startd8/contractors/artisan_phases/design_prompts/seed_mapping.py` to filter contracts securely for active tasks.
* **[COMPLETED] Prompt Module:** `ContractModule` is implemented in `src/startd8/contractors/artisan_phases/design_prompts/modules.py` to visually render constraints grouped by category and highlighted by confidence tier.
* **[COMPLETED] Prompt Hookpoints:** `SECTION_IMP_P6` ("Interface Contract Bindings") is fully registered in the `context_resolution` logic, with iterative extraction logic embedded directly in the `resolve_task_context` strategy.

## 3. Remaining Implementation Steps

### 3.0 IMPLEMENT Pipeline Integration — ✅ COMPLETED

Forward Manifest contracts are now injected into the Artisan IMPLEMENT phase. See [Phase_4_Artisan_Implement_Injection_Requirements.md](Phase_4_Artisan_Implement_Injection_Requirements.md) for full details.

**Summary of changes (2026-02-26):**
* `context_seed_handlers.py`: `_tasks_to_chunks` now reads `forward_manifest` from kwargs, calls `map_forward_contracts_for_task` per task, and stores rendered contract text in `chunk.metadata["forward_contracts"]`. `execute()` passes `forward_manifest=context.get("forward_manifest")`.
* `development.py`: `ArtisanChunkExecutor._build_forward_contracts()` helper reads `chunk.metadata["forward_contracts"]` and emits it as a prompt section. Called from `_build_task_description()`.

---

### 3.1 Handoff Serialization (`src/startd8/contractors/phase_handlers/`)

The payload must survive serialization bounds between pipeline phases (e.g., crossing process or workflow state boundaries).

* **[ACTION] Task Execution Contexts**: Locate where the `ArtisanContextSeed` is serialized into `ExecutionTask` or similar intermediate formats prior to prompt resolution.
* **[ACTION] Rehydration logic**: Ensure the nested dictionary format of `forward_manifest` inside the `ArtisanContextSeed` is passed explicitly without loss, as prompt components assume they are receiving `dict[str, Any]` at the edge.

### 3.2 DESIGN Pipeline Integration (`src/startd8/contractors/artisan_phases/design_builder.py`)

The `ContractModule` and `map_forward_contracts_for_task` scaffolding exist but must be wired into the prompt builder orchestrator.

* **[ACTION] Inject Module Data Loader**: Inside the design prompt builder loop, invoke `map_forward_contracts_for_task(task, forward_manifest=fm_model)` to hydrate data to feed the new module.
* **[ACTION] Register ContractModule**: Append `ContractModule()` to the ordered list of prompt fragments generated for the system prompt during the DESIGN phase.

### 3.3 Extractor Orchestrator Hook (`src/startd8/workflows/builtin/plan_ingestion.py`)

Though Phase 3 handles extraction, Phase 4 owns the responsibility of *capturing* that extraction before execution.

* **[ACTION] Hook the `EMIT` Phase**: Locate the emission generation logic in `PlanIngestionWorkflow`.
* **[ACTION] Call `extract_forward_contracts`**: Execute the Phase 3 method using the complete `ParsedPlan` and generated tasks, and assign the resulting `manifest.model_dump()` to `seed.forward_manifest`.

## 4. Verification Strategy

1. **Unit Tests (Design Builder):** Assert that a simulated DESIGN prompt generation correctly embeds the output text from `ContractModule`.
2. **Unit Tests (Seed Threading):** Validate that the initial seed payload retains the complete nested `forward_manifest` structure when converted back to a JSON dict.
3. **Local Pipeline Dry-Run:** Launch a mock end-to-end trace parsing a real plan document, confirming the pipeline reaches the task generation loop holding valid binding constraints in memory payload.
