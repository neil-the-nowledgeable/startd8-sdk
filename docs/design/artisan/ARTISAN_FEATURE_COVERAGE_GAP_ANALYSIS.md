# Artisan Feature Coverage Gap Analysis

**Date:** 2026-02-26
**Author:** agent audit
**Purpose:** Cross-reference the features specified in the code-manifest and forward-manifest design documents against what is actually wired into the Artisan pipeline.

---

## Summary

Artisan has good adoption of Phase 4 (structural manifest) and Phase 6 (call graph) features across most pipeline phases. Forward Manifest is now wired into DESIGN, IMPLEMENT (as of 2026-02-26), and REVIEW. The biggest remaining gaps are:

1. **Phase 5 (introspect) registry extension methods** — not yet implemented in `manifest_registry.py`
2. **Plan Ingestion — call graph complexity dimension** — `CG-PI-1` through `CG-PI-4` not implemented
3. **Forward Manifest missing from DESIGN prompt builder** — contracts reach `assemble_design_prompt()` but are not passed when triggered from `DesignPhaseHandler`
4. **Prime Contractor Forward Manifest flow** — `seed_forward_manifest` is stored but contracts not threaded into spec prompt
5. **Phase 5 introspect DS-1/DS-2/DS-4** — DESIGN prompt lacks MRO, resolved type, and runtime attributes sections

---

## 1. Forward Manifest — Pipeline Coverage Matrix

| Phase | Feature | Status | Notes |
|-------|---------|--------|-------|
| PLAN | Load `forward_manifest` from seed into context | ✅ Done | `PlanPhaseHandler` sets `context["forward_manifest"]` |
| DESIGN | Pass to `assemble_design_prompt()` via `ContractModule` | ✅ Done | `_task_to_feature_context()` calls `map_forward_contracts_for_task` |
| DESIGN | Pass from `DesignPhaseHandler` (context → prompt builder) | ⚠️ Partial | `forward_manifest=context.get("forward_manifest")` is threaded in `context_seed_handlers.py` line 2188 — verify the path is fully connected |
| IMPLEMENT | Inject contracts into `DevelopmentChunk` metadata | ✅ Done | **Done this session** — `_tasks_to_chunks` + `_build_forward_contracts()` |
| INTEGRATE | No contract enforcement at merge | ❌ Missing | Structural manifest diff exists but no Forward Manifest check at merge boundary |
| REVIEW | Run `validate_forward_manifest` against generated code | ✅ Done | `ReviewPhaseHandler` calls validator at line 9945; results flow into review output |
| REVIEW | Inject violated contracts into review prompt | ⚠️ Partial | Violations are collected but may not be surfaced to the lead agent's review prompt text — verify `fm_violations` are appended to review issues |
| Prime Contractor REVIEW | `validate_forward_manifest` during `_review_draft` | ✅ Done | `lead_contractor_workflow.py` line 1521 |
| Prime Contractor SPEC | Inject contracts into spec prompt | ❌ Missing | `REQ-PC-FM-006` — `forward_contracts` not yet rendered in `_build_spec_prompt` |

---

## 2. Code Manifest Phase 5 (Introspection) — Coverage Matrix

Phase 5 adds runtime introspection to manifests (`mode="introspect"`). These features require new registry methods that are **not yet implemented**.

### 2.1 Missing Registry Methods (`manifest_registry.py`)

| Method | Purpose | Required By | Status |
|--------|---------|-------------|--------|
| `file_resolved_type_summary()` | Resolved type annotations per element | DS-1, IM-1, PI-2 | ❌ Not implemented |
| `file_mro_summary()` | MRO chains for class elements | DS-2 | ❌ Not implemented |
| `file_runtime_attributes()` | Dataclass / namedtuple runtime attributes | DS-4, IM-2 | ❌ Not implemented |
| `module_all_for()` | Runtime `__all__` list | DS-3, IN-3, PF-1 | ❌ Not implemented |
| `module_version_for()` | Runtime `__version__` | PI-1 | ❌ Not implemented |
| `ManifestDiff.changed_resolved_signatures` | Resolved type changes in diff | IN-1 | ❌ Not implemented |
| `ManifestDiff.mro_changes` | MRO changes in diff | IN-2 | ❌ Not implemented |
| `ManifestDiff.module_all_diff` | `__all__` additions/removals | IN-3 | ❌ Not implemented |
| `file_element_summary(include_resolved_types=True)` | Kwarg to prefer resolved over AST types | DS-1, IM-1 | ❌ Not implemented (`include_resolved_types` kwarg missing) |
| `dead_candidates(use_runtime_callable=True)` | `is_callable` based dead code | CG-1 | ❌ Not implemented |

### 2.2 Consumer Gaps (Once Registry Methods Exist)

| Consumer | Feature IDs | Status |
|----------|------------|--------|
| DESIGN prompt — resolved type context | DS-1 | ❌ `enable_introspect` flag exists but `file_resolved_type_summary()` not available |
| DESIGN prompt — MRO chain | DS-2 | ❌ `file_mro_summary()` not available |
| DESIGN prompt — `module_all` | DS-3 | ❌ `module_all_for()` not available |
| DESIGN prompt — runtime attributes | DS-4 | ❌ `file_runtime_attributes()` not available |
| IMPLEMENT — resolved types in manifest context | IM-1 | ❌ `include_resolved_types` kwarg missing |
| IMPLEMENT — runtime attributes for dataclass tasks | IM-2 | ❌ `file_runtime_attributes()` not available |
| IMPLEMENT — `is_callable` annotation | IM-3 | ❌ Not implemented |
| INTEGRATE — resolved signature diff | IN-1 | ❌ `ManifestDiff.changed_resolved_signatures` missing |
| INTEGRATE — MRO change detection | IN-2 | ❌ `ManifestDiff.mro_changes` missing |
| PREFLIGHT — `module_all` validation | PF-1 | ❌ `module_all_for()` missing |
| PREFLIGHT — `is_callable` cross-check | PF-2 | ❌ Not implemented |
| Plan Ingestion — `module_version` | PI-1 | ⚠️ Partial — `extract_manifest_context()` calls `enable_introspect` path but `module_version_for()` not available |
| Prompt rendering — T1 `manifest_resolved_types` | PR-1 | ❌ `CONTEXT_FIELD_TIERS` missing this field |

---

## 3. Code Manifest Phase 6 (Call Graph) — Coverage Matrix

Phase 6 call graph is well-adopted. Remaining gaps:

| Feature | IDs | Status | Notes |
|---------|-----|--------|-------|
| IMPLEMENT caller context | CG-IM-1,2,4,6 | ✅ Done | `_build_call_graph_context()` in `development.py` |
| IMPLEMENT post-gen caller compatibility check | CG-IM-5 | ✅ Done | `_manifest_post_generate_diff()` includes caller check |
| REVIEW blast radius + dead code | CG-RV-1,2,3 | ✅ Done | `_build_call_graph_section()` in `ReviewPhaseHandler` |
| DESIGN call graph context | CG-DS-1,2,3 | ✅ Done | Lines 2722+ in `context_seed_handlers.py` |
| INTEGRATE severity escalation | CG-IN-1 | ✅ Done | `_manifest_pre_merge_diff()` |
| INTEGRATE cross-file notification | CG-IN-3 | ✅ Done | Logged in `IntegrationEngine` |
| PREFLIGHT `CallGraphValidator` | CG-PF-1,2,3,4 | ✅ Done | Registered in `_registry.py` |
| Plan Ingestion — call graph complexity | CG-PI-1,2,3,4 | ❌ Missing | No `call_graph_impact` dimension in `_heuristic_assess_complexity()` |
| Code Review skill — call graph context | CG-CR-1,2,3,4,5 | ❌ Missing | `/code-review` skill has no manifest registry integration |

---

## 4. Priority Recommendations

### Priority 1 — High Impact, Low Risk

| Gap | Effort | Why Now |
|-----|--------|---------|
| **Prime Contractor spec prompt — Forward Manifest injection (REQ-PC-FM-006)** | Small | Contracts are already loaded into context but never rendered in `_build_spec_prompt`. One section addition. |
| **Review phase — ensure `fm_violations` surface in review prompt text** | Small | Violations are validated but need to confirm they reach the LLM review prompt, not just the output metadata. |
| **Plan Ingestion — call graph complexity dimension (CG-PI-1,2,3)** | Medium | Call graph is available; `_heuristic_assess_complexity()` just needs a 6th dimension. High value for task ordering and risk detection. |

### Priority 2 — Phase 5 Introspect Foundation

| Gap | Effort | Why |
|-----|--------|-----|
| **`file_mro_summary()` + DESIGN MRO rendering (DS-2)** | Medium | Highest value Phase 5 feature — inheritance-aware design prevents LLM from producing wrong base classes. |
| **`file_resolved_type_summary()` + `include_resolved_types` kwarg (DS-1, IM-1)** | Medium | Forward-reference resolution is a real LLM failure mode (produces type annotations as string literals). |
| **`module_all_for()` + PREFLIGHT PF-1 validation** | Small | Once the registry method is added, the preflight consumer is simply adding a new `ValidationResult` condition. |

### Priority 3 — Completeness

| Gap | Effort | Why |
|-----|--------|-----|
| **`ManifestDiff.changed_resolved_signatures` + INTEGRATE IN-1** | Medium | Catches type-level breaking changes invisible to AST diff |
| **Code Review skill — call graph context (CG-CR-1,2,3)** | Medium | Transforms code review from syntax-level to architecture-level |
| **Phase 5 `CONTEXT_FIELD_TIERS` — `manifest_resolved_types` as T1 (PR-1)** | Small | Only needed once consumers produce resolved type fields |

---

## 5. Reference Documents

| Document | Coverage |
|----------|---------|
| [CODE_MANIFEST_PHASE5_PIPELINE_REQUIREMENTS.md](../CODE_MANIFEST_PHASE5_PIPELINE_REQUIREMENTS.md) | Phase 5 introspect — 7 consumer surfaces |
| [CODE_MANIFEST_PHASE6_PIPELINE_REQUIREMENTS.md](../CODE_MANIFEST_PHASE6_PIPELINE_REQUIREMENTS.md) | Phase 6 call graph — 7 consumer surfaces |
| [Phase_4_Prime_Contractor_Forward_Manifest_Requirements.md](../forward-manifest/Phase_4_Prime_Contractor_Forward_Manifest_Requirements.md) | Prime Contractor FM flow |
| [Phase_4_Artisan_Implement_Injection_Requirements.md](../forward-manifest/Phase_4_Artisan_Implement_Injection_Requirements.md) | IMPLEMENT injection (completed 2026-02-26) |
| [Phase_5_Prime_Contractor_Validator_Requirements.md](../forward-manifest/Phase_5_Prime_Contractor_Validator_Requirements.md) | Prime Contractor FM validation |
