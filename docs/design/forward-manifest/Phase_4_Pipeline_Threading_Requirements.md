# Phase 4 Requirements: Pipeline Threading

This document outlines the requirements and implementation plan for Phase 4 of the Forward-Looking Code Manifest (FLCM) integration: Pipeline threading (seed, handoff, and prompt modules).

## 1. Goal Description

The goal of Phase 4 is to seamlessly thread the `ForwardManifest` through the existing StartD8 pipeline. This ensures contracts discovered in earlier phases (like Plan Ingestion) survive the pipeline boundaries—such as the design/implementation handoff—and are accurately injected as structured bindings into subsequent LLM prompts.

## 2. Core Threading Requirements

### 2.1 Seed Threading (`ArtisanContextSeed`)

* **Requirement:** The `ArtisanContextSeed` must be updated to carry the state of the FLCM.
* **Implementation:**
  * Add a new field `forward_manifest: Optional[Dict[str, Any]] = None` to the `ArtisanContextSeed` dataclass.
  * This field must be populated during the EMIT phase of plan ingestion.
  * Ensure the existing `to_dict()` and `from_dict()` serialization methods correctly handle this new field.

### 2.2 Handoff Threading (JSON Contract)

* **Requirement:** The handoff JSON payload that ferries context between the Design half and Implementation half of the pipeline must safely transport the FLCM.
* **Implementation:**
  * Introduce a new `"forward_manifest"` key in the handoff JSON payload.
  * Use `.model_dump()` to serialize the `ForwardManifest` effectively when building the handoff.
  * On the receiving end (e.g., `PlanPhaseHandler`), deserialize the JSON payload back into a strongly-typed `ForwardManifest` instance (e.g., via `ForwardManifest.model_validate()`).

### 2.3 Shared Context Dictionary Threading

* **Requirement:** The `ForwardManifest` must be immediately accessible to any phase handler during an active pipeline run.
* **Implementation:**
  * Inject the active manifest into the shared pipeline dict: `context["forward_manifest"]`.
  * All handlers (Design, Implement, Review, etc.) should check this key (`context.get("forward_manifest")`) before attempting to enforce contracts.

### 2.4 Prompt Injection (Path 1: `prompt_constraints`)

* **Requirement:** A zero-change pathway for the `IMPLEMENT` phase to enforce bindings.
* **Implementation:**
  * The `PlanPhaseHandler` or `ImplementPhaseHandler` must load contracts from the `forward_manifest` bound to the current task.
  * Append these contracts to the task's `prompt_constraints` list using the precomputed `.binding_text`.
  * This leverages the existing `ConstraintsModule.render()` logic seamlessly.

### 2.5 Prompt Injection (Path 2: Dedicated `ContractModule`)

* **Requirement:** `DESIGN` prompts require detailed context—not just the constraints, but *why* they exist and their categorization.
* **Implementation:**
  * Create a dedicated `ContractModule` within `design_prompts/modules.py`.
  * This module implements the `PromptFragment` rendering logic.
  * It should group contracts by `ContractCategory` and cleanly format the `[BINDING]` vs `[ADVISORY]` prefixes alongside source references.
  * This module is classified as Tier 0 (non-droppable) to guarantee contract enforcement.

### 2.6 Pipeline Context Resolution (IMP-P6)

* **Requirement:** The `IMPLEMENT` module must explicitly structure the contract bindings into a labeled section for clarity to the LLM.
* **Implementation:**
  * Update `context_resolution.py` to include a new section hook:`IMP-P6` ("Interface Contract Bindings").
  * Map `IMP-P6` to the `"forward_contracts"` field to ensure the constraints are rendered at the exact intended spot within the prompt structure.

## 3. Backward Compatibility & Defensive Design

### 3.1 Optionality & Degradation

* **Requirement:** If FLCM is missing (e.g., older project states or disabled features), the pipeline *must not crash*.
* **Implementation:** The `forward_manifest` field on the seed, the JSON handoff, and pipeline dictionary must all accept and handle `None`. The `ContractModule` should simply return an empty string or omit its section if no contracts are found.

### 3.2 YAML Contract Integration (Optional Enhancement)

* Update `artisan-pipeline.contract.yaml` (if applicable) to declare `forward_manifest` as an optional input/output parameter across the `plan`, `design`, and `implement` boundaries. This enhances traceability for the State Engine.

## 4. Proposed Changes Summary

* [MODIFY] `src/startd8/pipeline_models.py` (or equivalent file housing `ArtisanContextSeed`)
* [MODIFY] `src/startd8/design_prompts/modules.py` -> Add `ContractModule`
* [MODIFY] `src/startd8/context_resolution.py` -> Add `IMP-P6` hookpoint
* [MODIFY] `src/startd8/seed_mapping.py` -> Add `extract_forward_contracts`
* [MODIFY] Phase Handler boundary logic (export to JSON / import from JSON serialization scripts)

## 5. Verification Plan

1. **Seed Serialization Test:** Ensure `ArtisanContextSeed` serializes and deserializes the `forward_manifest` dict reliably.
2. **Handoff Simulation Test:** Assert that simulated task states successfully emit and parse `"forward_manifest"` during a mock DESIGN -> IMPLEMENT transition.
3. **Prompt Module Unit Test:** Validate that `ContractModule.render()` successfully aggregates multiple contracts by category and returns the exact predicted markdown text.
4. **Graceful Fallback Test:** Execute a full pipeline run with a manifest-less project and guarantee it runs cleanly without throwing `KeyError` or `AttributeError`.
