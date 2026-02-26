# Phase 4 Extension: Prime Contractor Forward Manifest Requirements

**Version:** 1.0.0  
**Created:** 2026-02-26  
**Status:** Draft  
**Extends:** [Phase_4_Pipeline_Threading_Requirements.md](Phase_4_Pipeline_Threading_Requirements.md)  
**Context:** Phase 4 originally targeted the Artisan pipeline. This document defines requirements for the Prime Contractor to leverage the Forward Manifest (FLCM) for interface contract enforcement during code generation.

---

## 1. Goal Description

Enable the Prime Contractor (LeadContractorWorkflow) to consume the `ForwardManifest` produced during Plan Ingestion and inject interface contract bindings into the spec prompt. This ensures that contracts discovered from `ParsedFeature` definitions, proto files, and REFINE-phase LLM suggestions are enforced when the Lead creates implementation specs and the Drafter implements code.

**Current gap:** Run-004 (python-plan, Prime route) completed 17/17 tasks but `forward_manifest` was absent from `prime-context-seed.json`. The context resolution and LeadContractor scaffolding exist but are never exercised because (a) extraction fails or returns empty, and (b) Prime does not thread the manifest through its seed loading and context assembly.

---

## 2. Requirements

### 2.1 Plan Ingestion Bridge (REQ-PC-FM-001)

**Requirement:** The Plan Ingestion EMIT phase must successfully populate `forward_manifest` in the Prime context seed.

**Current state:** `_phase_emit` calls `extract_forward_contracts(parsed_plan=..., review_output=..., working_dir=...)`, but `extract_forward_contracts` in `forward_manifest_extractor.py` accepts `features`, `yaml_text`, `proto_dir`, `tentative_contracts`. The argument mismatch causes a `TypeError` (or equivalent), which is caught and results in `forward_manifest_dict = None`.

**Implementation:**
- Add a plan-ingestion-specific bridge (e.g., `extract_forward_contracts_for_plan`) or adapt the call site to pass:
  - `features=parsed_plan.features` (from `parsed_plan`)
  - `tentative_contracts` — extract from `review_output` (e.g., `review_output.get("triage", {}).get("contracts", [])` or equivalent REFINE output)
  - `proto_dir` — resolve from `working_dir` or project root (e.g., `working_dir / "proto"` or scan for `.proto` files)
  - `yaml_text` — optional; from plan document or context files if `shared_contracts` block exists
- Ensure extraction errors are logged with sufficient detail for debugging; avoid silent degradation when possible.
- **Verification:** Run plan ingestion with a plan that has `api_signatures`, `protocol`, or `runtime_dependencies` on features; assert `prime-context-seed.json` contains a non-null `forward_manifest` with at least one contract.

---

### 2.2 Prime Contractor Seed Loading (REQ-PC-FM-002)

**Requirement:** `PrimeContractorWorkflow.load_seed_context()` must extract and preserve `forward_manifest` from the raw seed dictionary.

**Current state:** `load_seed_context` extracts only `onboarding`, `architectural_context`, `design_calibration`, `service_metadata`. It does not read or store `forward_manifest`.

**Implementation:**
- Add `forward_manifest = seed_data.get("forward_manifest")` to the extraction block.
- Store in a workflow attribute (e.g., `self.seed_forward_manifest`) for use during `develop_feature`.
- Optionally add `forward_manifest` to `SeedContext` and `_SERIALIZABLE_FIELDS` if pipeline mode state persistence is required.
- **Verification:** Unit test: `load_seed_context(seed_with_forward_manifest)` → `workflow.seed_forward_manifest` is not None and matches the seed value.

---

### 2.3 Context Assembly (REQ-PC-FM-003)

**Requirement:** When assembling `seed_data` for `_resolve_context` / `resolve_task_context`, Prime must include `forward_manifest` so the context strategy can inject contract bindings.

**Current state:** In `develop_feature`, the `seed_data` dict passed to `_context_strategy.resolve_task_context` contains `onboarding_metadata`, `architectural_context`, `design_calibration`, `plan_document_text`, `service_metadata`. It does not include `forward_manifest`.

**Implementation:**
- Add `"forward_manifest": self.seed_forward_manifest` to the `seed_data` dict in `develop_feature` (around line 1655).
- Ensure `self.seed_forward_manifest` is set from `load_seed_context` (REQ-PC-FM-002).
- **Verification:** Integration test: pipeline-mode run with a seed containing `forward_manifest`; assert `resolve_task_context` receives it and `gen_context` contains `forward_contracts` or merged constraints.

---

### 2.4 Context Resolution Hydration (REQ-PC-FM-004)

**Requirement:** When `forward_manifest` in `seed_data` is a `dict` (deserialized from JSON), the context strategy must hydrate it to a `ForwardManifest` model before calling `binding_constraints_for_task`.

**Current state:** `PipelineContextStrategy` and `StandaloneContextStrategy` check `hasattr(fm, "binding_constraints_for_task")`. A dict does not have that method, so the block is skipped and no contracts are injected.

**Implementation:**
- In `context_resolution.py`, when `fm` is a dict, call `ForwardManifest.model_validate(fm)` to obtain a typed instance.
- Use the hydrated instance for `binding_constraints_for_task(task_id)`.
- Preserve backward compatibility: if hydration fails (e.g., schema mismatch), log and skip injection.
- **Verification:** Unit test: `resolve_task_context(seed_data={"forward_manifest": {...}})` with a valid manifest dict; assert `gen_context["forward_contracts"]` or `domain_constraints` contains the expected binding strings.

---

### 2.5 Task ID Alignment (REQ-PC-FM-005)

**Requirement:** Contract applicability must align with Prime's feature IDs (e.g., `PI-001`, `PI-002`).

**Current state:** `ForwardManifest.contracts_for_task(task_id)` filters by `applicable_task_ids`. The DeterministicExtractor sets `applicable_task_ids=[feature.feature_id]` (e.g., `F-001a`). Plan Ingestion derives tasks with IDs like `PI-001` from `_derive_tasks_from_features` (format: `PI-{idx:03d}`). Prime's `feature_data["id"]` is `PI-001`. Mismatch causes contracts to be omitted.

**Implementation:**
- Add a post-extraction step in the plan ingestion bridge: given the `feature_id → task_id` mapping from `_derive_tasks_from_features`, rewrite `applicable_task_ids` in each contract from `feature_id` to `task_id` before serializing to the seed.
- Alternatively, extend `contracts_for_task` to accept an optional `feature_id_to_task_id` mapping and match on both.
- **Verification:** With a contract originally scoped to `F-001a` and task `PI-001` derived from that feature, assert that `contracts_for_task("PI-001")` returns the contract.

---

### 2.6 LeadContractor Prompt Injection (REQ-PC-FM-006)

**Requirement:** The LeadContractor spec prompt must surface interface contract bindings to the Lead agent.

**Current state:** `PipelineContextStrategy` sets `gen_context["forward_contracts"]` when contracts exist. `LeadContractorWorkflow._build_spec_prompt` does not pop or render `forward_contracts`; it only consumes `domain_constraints`, `requirements_text`, `critical_parameters`, etc. The `forward_contracts` key may remain in the general context dump or be ignored.

**Implementation (choose one):**
- **Option A — Dedicated section:** Add an `## Interface Contract Bindings` section to the spec prompt template. Pop `forward_contracts` in `_build_spec_prompt` and render it explicitly. Ensures contracts are prominent and not buried in context.
- **Option B — Merge into domain_constraints:** Append `forward_contracts` content to `domain_constraints` before formatting. Simpler but less structured.
- **Recommendation:** Option A for clarity and alignment with Phase 4 IMP-P6 ("Interface Contract Bindings").
- **Verification:** With a seed containing `forward_manifest` and a task with applicable contracts, assert the spec prompt includes the binding text (e.g., `[BINDING] function=getJSONLogger | ...`).

---

### 2.7 Backward Compatibility (REQ-PC-FM-007)

**Requirement:** When `forward_manifest` is absent or empty, Prime must run without error.

**Implementation:**
- All new code paths must handle `forward_manifest is None` or `forward_manifest == {}`.
- `load_seed_context`: default `self.seed_forward_manifest = None` when key missing.
- `seed_data`: omit `forward_manifest` or pass `None`; context strategy already guards with `if fm:`.
- **Verification:** Run Prime with a seed that has no `forward_manifest`; assert no `KeyError`, `AttributeError`, or crash.

---

## 3. Proposed Changes Summary

| Component | Change |
|-----------|--------|
| `plan_ingestion_workflow.py` | Fix `extract_forward_contracts` call: pass `features`, `tentative_contracts`, `proto_dir`, `yaml_text` derived from `parsed_plan`, `review_output`, `working_dir` |
| `prime_contractor.py` | `load_seed_context`: extract `forward_manifest`; `develop_feature`: add to `seed_data` |
| `context_resolution.py` | Hydrate `dict` → `ForwardManifest.model_validate()` when `fm` is dict |
| `lead_contractor_workflow.py` | Pop `forward_contracts` and render in spec prompt (new section or merge) |
| `lead_contractor.yaml` (prompts) | Add `forward_contracts_section` placeholder if Option A |

---

## 4. Verification Plan

1. **Unit: Plan Ingestion Bridge** — Mock `parsed_plan` with features having `api_signatures`; assert `forward_manifest` in emitted seed has contracts.
2. **Unit: Seed Loading** — `load_seed_context(seed_with_forward_manifest)` → `seed_forward_manifest` populated.
3. **Unit: Context Hydration** — `resolve_task_context(seed_data={"forward_manifest": valid_dict})` → `gen_context` contains contract bindings.
4. **Unit: LeadContractor Rendering** — `_build_spec_prompt` with `forward_contracts` in context → spec string includes binding text.
5. **Integration: Full Pipeline** — Run `run-atomic.sh --plan python-plan.md --requirements python-requirements.md --route prime`; assert `prime-context-seed.json` has `forward_manifest` and generated code respects at least one contract (e.g., `getJSONLogger` in logger.py).
6. **Regression: Manifest Absent** — Run with seed lacking `forward_manifest`; assert no crash, generation proceeds.

---

## 5. Dependencies

- Phase 3 extractor (`extract_forward_contracts`) — must accept inputs derivable from plan ingestion.
- `ForwardManifest` model and `binding_constraints_for_task` — already implemented.
- `context_resolution` Phase 4 scaffolding — exists but requires hydration fix.

---

## 6. Out of Scope

- Artisan pipeline changes (handoff, ContractModule) — covered by Phase 4 base doc.
- Post-generation contract validation (detecting violations in generated code) — Phase 5 validator.
- Changes to the Forward Manifest schema or extractor internals.
