# Code Manifest Phase 5 Pipeline Adoption: Wiring Introspection into Consumer Surfaces

**Status:** Draft
**Date:** 2026-02-24
**Author:** Neil Yashinsky + agent:claude-code
**Parent:** [CODE_MANIFEST_PHASE5_REQUIREMENTS.md](CODE_MANIFEST_PHASE5_REQUIREMENTS.md) (Phase 5 introspection), [CODE_MANIFEST_PHASE4_REQUIREMENTS.md](CODE_MANIFEST_PHASE4_REQUIREMENTS.md) (Phase 4 pipeline integration)
**Implements:** Wiring Phase 5 runtime introspection data into 7 pipeline consumer surfaces
**Dependencies:** Phase 5 core (commit `a911b63`, schema 1.4.0), Phase 4 pipeline integration (complete), Phase 6 pipeline integration (complete)

---

## 1. Objective

Phase 5 (commit `a911b63`) added runtime introspection to the manifest system via `mode="introspect"`. New data — resolved signatures, MRO, `module_all`, `module_version`, `runtime_attributes`, `is_callable` — is now produced but **not consumed** by any pipeline surface. Phase 4 wired *structural* manifest data into 6 consumers. Phase 6 pipeline wired *call graph* data into 7 consumers. This document specifies wiring Phase 5 *introspection* data into the same 7 consumer surfaces.

The introspection layer answers questions that neither static analysis nor bytecode call graphs can:

| Question | Structural (Phase 1–3) | Call Graph (Phase 6) | Introspection (Phase 5) |
|----------|----------------------|---------------------|------------------------|
| What's the actual type of parameter `x`? | AST string (may be forward ref) | — | `resolved_signature.params[].annotation` |
| What's the real class hierarchy? | AST base classes (names only) | — | `mro` (full C3 linearization) |
| What does `__all__` contain at runtime? | Literal list only | — | `module_all` (dynamic computation) |
| Does a dataclass have generated fields? | No (absent from AST body) | — | `runtime_attributes` |
| Is this variable callable? | Heuristic (class/function defs) | — | `is_callable` (runtime truth) |
| What version is this module? | No | — | `module_version` |

Without this wiring, introspection data is available only via the CLI `startd8 manifest generate --mode introspect` command.

---

## 2. Phase 5 Capabilities Summary

Quick reference for the fields available on `Element.inspect_info` (type `InspectInfo | None`) and `FileManifest` extensions. Full specification in [CODE_MANIFEST_PHASE5_REQUIREMENTS.md](CODE_MANIFEST_PHASE5_REQUIREMENTS.md) Section 3.

### 2.1 Element-Level: `InspectInfo`

| Field | Type | Description | Consumer Value |
|-------|------|-------------|----------------|
| `resolved_signature` | `ResolvedSignature?` | Runtime-resolved callable signature with evaluated type annotations | True parameter types (not forward-ref strings) |
| `mro` | `list[str]` | Method Resolution Order (C3 linearization) as FQN strings | Full class hierarchy for inheritance-aware design |
| `resolved_annotations` | `dict[str, str]` | Evaluated `typing.get_type_hints()` results | Concrete types for generic/forward-ref annotations |
| `runtime_attributes` | `list[str]` | Members visible at runtime but absent from AST (dataclass fields, namedtuple attrs) | Complete API surface for generated types |
| `is_callable` | `bool` | Whether the object has `__call__` at runtime | Accurate callable classification beyond AST heuristics |
| `qualname` | `str?` | `__qualname__` from runtime object | Nested function/class identity confirmation |

### 2.2 File-Level: `FileManifest` Extensions

| Field | Type | Description | Consumer Value |
|-------|------|-------------|----------------|
| `module_all` | `list[str]?` | Runtime `__all__` (captures dynamic computation) | Authoritative public API surface |
| `module_version` | `str?` | Runtime `__version__` | Compatibility context for plan ingestion |

### 2.3 Availability

Introspection data is only populated when manifests are generated with `mode="introspect"`. Consumers must handle three states:

1. **No manifest** — file has no manifest entry (Phase 4 graceful degradation applies)
2. **Manifest without introspection** — `element.inspect_info is None` (generated with `mode="static"` or `mode="ast_only"`)
3. **Manifest with introspection** — `element.inspect_info` is populated (full functionality)

---

## 3. Activation Strategy

### 3.1 HandlerConfig Extension

Add a new flag to `HandlerConfig` (`context_seed_handlers.py`, line 373):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_introspect` | `bool` | `False` | When `True`, consumers query `inspect_info` fields. When `False`, all introspect-specific logic is skipped (Phase 4 + Phase 6 behavior preserved). |

The existing `manifest_consumption_enabled` kill switch (line 441) remains the top-level gate. `enable_introspect` is checked only when `manifest_consumption_enabled` is `True`.

```
manifest_consumption_enabled = False  →  all manifest features off
manifest_consumption_enabled = True, enable_introspect = False  →  Phase 4 + Phase 6 only
manifest_consumption_enabled = True, enable_introspect = True   →  Phase 4 + Phase 5 + Phase 6
```

### 3.2 Pipeline Environment Toggle

Add to `pipeline.env` (cap-dev-pipe):

```bash
STARTD8_ENABLE_INTROSPECT=false   # Set to "true" for Phase 5 adoption
```

### 3.3 Per-Surface Kill Switches

Each integration point respects `enable_introspect`. No per-surface toggles are defined initially — the single flag controls all 7 surfaces. Per-surface toggles can be added in a follow-up if rollout reveals surfaces that need independent control.

---

## 4. Integration Point 1 — Artisan DESIGN Phase

**Current state:** `DesignPhaseHandler._task_to_feature_context()` (`context_seed_handlers.py`, lines 2091–2640) injects manifest structural context via `manifest_registry.file_element_summary()` (line 2594) into `additional_context["manifest_context"]` (line 2606). Element summaries show AST-extracted signatures — these may contain forward references (`str` instead of the actual type) and miss dataclass-generated fields.

**Failure mode addressed:** Design document specifies a method signature using forward-reference strings (e.g., `param: 'MyModel'`) instead of the resolved type, leading to implementation prompts that generate incorrect type usage.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| DS-1 | **Resolved signatures in T1 manifest context.** When `enable_introspect` is `True` and `element.inspect_info.resolved_signature` is available, render the resolved signature instead of the AST-extracted signature in the `manifest_context` field. Fall back to AST signature when `inspect_info` is `None`. | Forward references (`from __future__ import annotations`) make AST signatures unreliable. The resolved signature shows the actual types the LLM should use in generated code. |
| DS-2 | **MRO rendering for class-targeting tasks.** When a task targets a class and `element.inspect_info.mro` is available, append a `Class Hierarchy` subsection to the manifest context showing the MRO chain (excluding `builtins.object`). | Design documents for subclass features need the full inheritance context. AST base classes show only direct parents — MRO reveals the complete chain including mixin order, which affects method resolution. |
| DS-3 | **`module_all` in T3 metadata.** When `manifest.module_all` is available, include it in the design context metadata as `public_api_surface: [list]`. Assign to Tier 3 in `CONTEXT_FIELD_TIERS`. | Gives the design LLM visibility into the module's intended public API — relevant for tasks that add new exports or modify existing ones. T3 because it's metadata, not design-driving. |
| DS-4 | **Runtime attributes for dataclass/namedtuple targets.** When `element.inspect_info.runtime_attributes` is non-empty, append a `Generated Members` line to the element's summary showing the runtime-only attributes. | Dataclass fields, namedtuple attributes, and metaclass-injected methods are invisible to AST but real at runtime. The design LLM must know about them to avoid duplicating or conflicting with generated members. |
| DS-5 | **Budget sharing.** Resolved signature rendering shares the existing `manifest_context_budget` (default 4000 chars, line 442). Resolved signatures replace AST signatures (not additive) — no budget increase needed. MRO and `runtime_attributes` are additive but compact (< 200 chars typical). | Keeps prompt size stable. Resolved signatures are typically the same length as AST signatures (types replace forward-ref strings). |
| DS-6 | **Graceful degradation.** When `enable_introspect` is `False` or `inspect_info` is `None`, design prompts render identically to Phase 4 + Phase 6 behavior. | No regression for projects without introspect-mode manifests. |

---

## 5. Integration Point 2 — Artisan IMPLEMENT Phase

**Current state:** `ImplementPhaseHandler` (`context_seed_handlers.py`, lines 4116–6200+) injects manifest context into chunks via `_manifest_context` metadata (line 6170). `DevelopmentPhase._build_manifest_context()` (`development.py`, lines 1423–1452) renders this as a `## Code Structure` section. Signatures are AST-extracted.

**Failure mode addressed:** LLM generates code calling `process(data: 'DataFrame')` with a string type hint instead of the resolved `pandas.DataFrame`, causing type checker failures in downstream integration.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| IM-1 | **Resolved type context in chunk metadata.** When `enable_introspect` is `True`, replace AST-extracted signatures with resolved signatures in `chunk.metadata["_manifest_context"]` (line 6170). | Implementation prompts with resolved types produce code with correct type annotations. The LLM sees `param: pandas.DataFrame` instead of `param: 'DataFrame'`. |
| IM-2 | **Runtime attributes for dataclass/namedtuple tasks.** When a chunk targets a dataclass or namedtuple (detected via non-empty `runtime_attributes`), include generated member names in the code structure section. | Prevents the LLM from regenerating `__init__`, `__repr__`, or other dataclass-generated methods that already exist at runtime. |
| IM-3 | **`is_callable` annotation for variable targets.** When a chunk targets a module-level variable and `is_callable` is `True`, annotate the variable as callable in the code structure. | Helps the LLM understand that a variable holding a class or callable object should be invoked, not reassigned. Important for factory pattern implementations. |
| IM-4 | **Graceful degradation.** When `enable_introspect` is `False` or `inspect_info` is `None`, IMPLEMENT prompts render identically to Phase 4 + Phase 6 behavior. | No regression. |

---

## 6. Integration Point 3 — Artisan INTEGRATE Phase

**Current state:** `IntegrationEngine._manifest_pre_merge_diff()` (`integration_engine.py`, lines 96–195) computes `ManifestDiff` between existing and staged files. Compares AST-extracted signatures. Phase 6 pipeline (CG-IN-1, lines 191–205) escalates severity based on caller count.

**Failure mode addressed:** A merge changes a function's resolved parameter type (e.g., `int` → `str` after decorator evaluation) but the AST signature is unchanged — the structural diff sees no change, missing a breaking type contract violation.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| IN-1 | **Type-aware ManifestDiff.** Extend `ManifestDiff.diff()` to compare `resolved_signature` when both old and new elements have `inspect_info`. Add `changed_resolved_signatures: list[tuple[str, str, str]]` (`fqn, old_resolved, new_resolved`) to the diff result. | AST signatures can be identical while resolved types differ (forward references, decorator transformations, `TYPE_CHECKING`-guarded imports). Resolved signature comparison catches type-level breaking changes. |
| IN-2 | **MRO change detection gate.** When both old and new class elements have `inspect_info.mro`, compare MRO lists. If MRO changed, emit WARNING via `GateEmitter` with `gate_name="manifest_mro_change"`. | MRO changes indicate inheritance restructuring that may break method resolution, `super()` chains, and isinstance checks. This is a high-impact change that deserves explicit flagging. |
| IN-3 | **`module_all` change detection.** When both old and new `FileManifest` have `module_all`, compute the set difference. Log added/removed exports at INFO. | Changes to `__all__` affect downstream importers. An element removed from `__all__` becomes an undocumented internal, potentially breaking `from module import *` consumers. |
| IN-4 | **Graceful degradation.** When `enable_introspect` is `False` or `inspect_info` is `None` on either manifest, all IN requirements are skipped. Phase 4 IN-1 through IN-3 and Phase 6 CG-IN-1 through CG-IN-4 continue unchanged. | Independent degradation — introspect layer does not affect structural or call graph diff. |

---

## 7. Integration Point 4 — PREFLIGHT Workflow

**Current state:** `DomainPreflightWorkflow._run_environment_checks()` (`domain_preflight_workflow.py`, lines 386–415) passes `per_file_manifest` (line 411) and `manifest_registry` (line 412) into `RuleContext`. Existing validators access structural data only.

**Failure mode addressed:** A generated module defines `__all__` dynamically (e.g., filtering by installed optional deps) — the AST-extracted `__all__` is empty/missing, so the preflight export validator skips the file. The runtime `module_all` captures the actual public API.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| PF-1 | **Dynamic export validation via `module_all`.** When `enable_introspect` is `True` and `manifest.module_all` is available, validate that all names in `module_all` exist as elements in the manifest. Flag missing names as WARNING ("module exports name `X` but no element `X` found"). | Catches `__all__` entries that reference deleted, renamed, or never-implemented symbols. The runtime `module_all` captures dynamic `__all__` computation that AST extraction misses. |
| PF-2 | **Callable contract validation via `is_callable`.** When `enable_introspect` is `True`, add a preflight check: for each element with `inspect_info.is_callable = False` that is used as a callable in the call graph (has outbound calls or is in `callers_of()` results), emit WARNING. | Detects type errors where a non-callable variable is used in a call expression. This is a runtime `TypeError` waiting to happen. |
| PF-3 | **Graceful degradation.** When `enable_introspect` is `False`, `module_all` is `None`, or `inspect_info` is `None`, all PF requirements are skipped. Phase 4 PF-1 through PF-5 and Phase 6 CG-PF-1 through CG-PF-5 continue unchanged. | Independent degradation. |

---

## 8. Integration Point 5 — Call Graph Analysis

**Current state:** `ManifestRegistry.dead_candidates()` (`manifest_registry.py`, lines 699–720) returns public callables with zero inbound call edges. Callable classification uses `ElementKind` (line 706): `FUNCTION`, `ASYNC_FUNCTION`, `METHOD`, `ASYNC_METHOD`. This is an AST-level heuristic — it misses callable classes and callable variables.

**Failure mode addressed:** A callable class (has `__call__`) or a module-level variable holding a callable (e.g., `handler = functools.partial(...)`) is flagged as dead code because `ElementKind` doesn't classify them as callable.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| CG-1 | **Runtime-callable filtering for dead code.** When `enable_introspect` is `True`, extend `dead_candidates()` to also include elements where `inspect_info.is_callable` is `True`, regardless of `ElementKind`. Conversely, exclude elements where `is_callable` is `False` even if their `ElementKind` is in the callable set (e.g., a function replaced at runtime with a non-callable sentinel). | `is_callable` is the runtime truth about callability. AST heuristics produce false positives (non-callable objects with function-like `ElementKind`) and false negatives (callable objects with non-function `ElementKind`). |
| CG-2 | **Graceful degradation.** When `enable_introspect` is `False` or `inspect_info` is `None`, `dead_candidates()` uses the existing `ElementKind`-based heuristic (current behavior). | No regression. |

---

## 9. Integration Point 6 — Plan Ingestion

**Current state:** `extract_manifest_context()` (`seed_mapping.py`, lines 163–224) extracts `file_summaries` (line 208) and optional `dependency_context` (line 220) from the manifest registry. No module version or introspection data is extracted.

**Failure mode addressed:** A plan targets a module at version 2.x but the project depends on version 1.x — the plan ingestion pipeline has no visibility into the version mismatch, producing incorrect complexity assessments.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| PI-1 | **`module_version` in compatibility context.** When `enable_introspect` is `True` and `manifest.module_version` is available, include it in the extracted manifest context as `module_versions: {file: version}`. | Version information feeds compatibility assessment during plan ingestion. A task targeting `startd8.providers.anthropic` with `module_version="0.4.0"` gives the pipeline concrete version context for dependency ordering. |
| PI-2 | **Resolved type context in file summaries.** When `enable_introspect` is `True`, extend `file_element_summary()` rendering to prefer resolved signatures over AST signatures. | Plan ingestion complexity assessment benefits from resolved types — a function taking `DataFrame` is more complex to modify than one taking `str`, and the resolved type makes this distinction visible. |
| PI-3 | **Graceful degradation.** When `enable_introspect` is `False` or introspect data is unavailable, `extract_manifest_context()` returns identical results to current behavior. | No regression. |

---

## 10. Integration Point 7 — Prompt Rendering

**Current state:** `format_tiered_context()` (`prompt_utils.py`, lines 150–239) renders `additional_context` with tier-based progressive disclosure. `CONTEXT_FIELD_TIERS` (lines 18–64) assigns fields to tiers T0–T3. `manifest_context` is T1 (line 28), `manifest_dependencies` is T2 (line 42). No introspect-specific fields exist.

**Failure mode addressed:** Resolved type strings (potentially longer than AST annotations due to fully-qualified names like `pandas.core.frame.DataFrame`) are not accounted for in the token budget, causing unexpected budget overruns.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| PR-1 | **Resolved types rendering in tiered context.** Register `manifest_resolved_types` as a new T1 field in `CONTEXT_FIELD_TIERS`. When present, render resolved type annotations alongside or replacing AST types. | Resolved types are T1 (high value, scope-framing) — they directly influence implementation decisions. Same tier as `manifest_context` for co-rendering. |
| PR-2 | **Budget accounting for resolved type strings.** Resolved type strings may be longer than AST annotations (fully-qualified names vs short names). The progressive compression cascade (TC-201 through TC-203) must account for this. Under budget pressure, prefer dropping `manifest_resolved_types` before dropping `manifest_context` (resolved types are supplementary to structural context). | Prevents introspect data from crowding out more fundamental structural context during compression. |
| PR-3 | **New T3 field: `public_api_surface`.** Register `public_api_surface` (from DS-3) as T3 in `CONTEXT_FIELD_TIERS`. | Module `__all__` is metadata, not design-driving — T3 is appropriate (droppable under budget pressure). |
| PR-4 | **Graceful degradation.** When introspect fields are absent from `additional_context`, rendering is identical to current behavior. | No regression. |

---

## 11. ManifestRegistry API Extensions

### 11.1 Modified Methods

| Method | Current Location | Change | Requirement |
|--------|-----------------|--------|-------------|
| `file_element_summary()` | `manifest_registry.py`, line 499 | Add `include_resolved_types: bool = False` kwarg. When `True` and `element.inspect_info.resolved_signature` is available, render resolved parameter types instead of AST-extracted types in tiers 1–4. | DS-1, IM-1, PI-2 |
| `dead_candidates()` | `manifest_registry.py`, line 699 | Add `use_runtime_callable: bool = False` kwarg. When `True`, use `inspect_info.is_callable` as the callable classifier instead of `ElementKind`-based heuristic. | CG-1 |

### 11.2 New Methods

| Method | Signature | Description | Requirement |
|--------|-----------|-------------|-------------|
| `file_resolved_type_summary()` | `(relative_path: str, budget_chars: int = 2000) -> str` | Compact summary of resolved types for a file's elements. Format: `"element_name: (param: Type, ...) -> ReturnType"` per callable. Progressive truncation: full → public-only → count-only. | PR-1, DS-1 |
| `file_mro_summary()` | `(relative_path: str) -> dict[str, list[str]]` | Returns `{class_fqn: mro_list}` for all classes in the file that have `inspect_info.mro`. | DS-2 |
| `file_runtime_attributes()` | `(relative_path: str) -> dict[str, list[str]]` | Returns `{element_fqn: runtime_attributes}` for elements with non-empty `runtime_attributes`. | DS-4, IM-2 |
| `module_all_for()` | `(relative_path: str) -> list[str] | None` | Returns `FileManifest.module_all` for the given file, or `None`. | DS-3, IN-3, PF-1 |
| `module_version_for()` | `(relative_path: str) -> str | None` | Returns `FileManifest.module_version` for the given file, or `None`. | PI-1 |

### 11.3 ManifestDiff Extensions

| Property/Method | Type | Description | Requirement |
|----------------|------|-------------|-------------|
| `changed_resolved_signatures` | `list[tuple[str, str, str]]` | `(fqn, old_resolved, new_resolved)` triples for elements whose resolved signature changed. Only populated when both manifests have `inspect_info`. | IN-1 |
| `mro_changes` | `list[tuple[str, list[str], list[str]]]` | `(fqn, old_mro, new_mro)` triples for classes whose MRO changed. | IN-2 |
| `module_all_diff` | `tuple[list[str], list[str]] | None` | `(added, removed)` exports. `None` if either manifest lacks `module_all`. | IN-3 |

---

## 12. Performance Budget

| ID | Metric | Budget | Rationale |
|----|--------|--------|-----------|
| PB-1 | `file_resolved_type_summary()` per file | < 10ms | String formatting of pre-parsed `inspect_info` data. No I/O. Same complexity as `file_element_summary()`. |
| PB-2 | `file_mro_summary()` per file | < 5ms | Dict comprehension over elements. O(elements). |
| PB-3 | `file_runtime_attributes()` per file | < 5ms | Dict comprehension over elements. O(elements). |
| PB-4 | `ManifestDiff` resolved signature comparison | < 15ms | String comparison of resolved signatures on top of existing diff. O(shared elements). |
| PB-5 | `ManifestDiff` MRO comparison | < 5ms | List comparison for class elements only. O(classes). |
| PB-6 | Per-task DESIGN prompt overhead (DS-1 through DS-6) | < 20ms | Resolved type substitution + MRO rendering. Replaces existing string, not additive I/O. |
| PB-7 | Per-task IMPLEMENT prompt overhead (IM-1 through IM-4) | < 15ms | Resolved type substitution in chunk metadata. Same code path as structural rendering. |
| PB-8 | Pipeline startup overhead (introspect data loading) | < 100ms | Introspect data is already in the cached manifest — no additional I/O. Only adds field access during rendering. |
| PB-9 | Per-file INTEGRATE overhead (IN-1 through IN-4) | < 20ms | Resolved sig comparison + MRO comparison + `module_all` set diff. All in-memory. |

---

## 13. Acceptance Criteria

### 13.1 Functional Criteria

| ID | Criterion | Integration Point | Validation |
|----|-----------|-------------------|------------|
| AC-5P1 | DESIGN prompt renders resolved signatures (not forward-ref strings) when `enable_introspect` is `True` and `inspect_info` is available. | DS-1 | Unit test: manifest with `inspect_info.resolved_signature` containing resolved type. Assert design context uses resolved type, not AST string. |
| AC-5P2 | DESIGN prompt includes MRO chain for class-targeting tasks. | DS-2 | Unit test: class element with `inspect_info.mro = ["Child", "Parent", "object"]`. Assert `Class Hierarchy` subsection in design context. |
| AC-5P3 | DESIGN context includes `public_api_surface` from `module_all`. | DS-3 | Unit test: manifest with `module_all = ["foo", "bar"]`. Assert metadata field in additional context. |
| AC-5P4 | DESIGN context includes runtime attributes for dataclass elements. | DS-4 | Unit test: element with `runtime_attributes = ["__init__", "__repr__"]`. Assert `Generated Members` in element summary. |
| AC-5P5 | IMPLEMENT chunk metadata uses resolved signatures when available. | IM-1 | Unit test: chunk with manifest containing `inspect_info`. Assert `_manifest_context` contains resolved types. |
| AC-5P6 | IMPLEMENT code structure section includes runtime attributes for dataclass targets. | IM-2 | Unit test: chunk targeting a dataclass. Assert runtime attributes listed in code structure. |
| AC-5P7 | INTEGRATE phase detects resolved signature changes between old and new manifests. | IN-1 | Unit test: `ManifestDiff.diff()` with matching AST signatures but differing resolved signatures. Assert `changed_resolved_signatures` is non-empty. |
| AC-5P8 | INTEGRATE phase emits WARNING on MRO changes. | IN-2 | Unit test: class with changed MRO. Assert WARNING log and `GateEmitter` event with `gate_name="manifest_mro_change"`. |
| AC-5P9 | INTEGRATE phase logs `module_all` changes. | IN-3 | Unit test: `FileManifest` with changed `module_all`. Assert INFO log with added/removed exports. |
| AC-5P10 | Preflight validates `module_all` entries against manifest elements. | PF-1 | Unit test: `module_all` containing a name with no corresponding element. Assert WARNING. |
| AC-5P11 | `dead_candidates()` uses `is_callable` when `use_runtime_callable=True`. | CG-1 | Unit test: callable class (`is_callable=True`, `ElementKind.CLASS`) with zero callers. Assert it appears in dead candidates. Non-callable variable (`is_callable=False`) excluded. |
| AC-5P12 | Plan ingestion includes `module_version` in extracted context. | PI-1 | Unit test: manifest with `module_version="0.4.0"`. Assert `module_versions` key in extracted context dict. |
| AC-5P13 | `format_tiered_context()` renders `manifest_resolved_types` as T1. | PR-1 | Unit test: additional context with `manifest_resolved_types` field. Assert rendered at T1 (before T2 fields). |
| AC-5P14 | `format_tiered_context()` drops `manifest_resolved_types` before `manifest_context` under budget pressure. | PR-2 | Unit test: context exceeding budget. Assert `manifest_context` retained, `manifest_resolved_types` dropped. |
| AC-5P15 | **Full pipeline completes with `enable_introspect=False`.** All Phase 4 + Phase 6 behavior is identical. | All DS-6, IM-4, IN-4, PF-3, CG-2, PI-3, PR-4 | Integration test: pipeline run with `enable_introspect=False` produces identical outputs to pre-Phase-5-pipeline run. |

### 13.2 Performance Criteria

| ID | Criterion | Budget | Validation |
|----|-----------|--------|------------|
| AP-5P1 | `file_resolved_type_summary()` per file | < 10ms | Benchmark test with largest project file. |
| AP-5P2 | Per-task DESIGN prompt overhead (introspect additions) | < 20ms | Benchmark DESIGN prompt build time with and without introspect data. |
| AP-5P3 | Per-file INTEGRATE resolved sig comparison | < 15ms | Benchmark `ManifestDiff.diff()` with introspect data vs without. |

### 13.3 Cache Criteria

| ID | Criterion | Validation |
|----|-----------|------------|
| AC-5PC1 | Introspect data in cached manifests is consumed without re-generation. Consumers read `inspect_info` from the loaded `ManifestRegistry` (populated via `from_cache()`), not by re-running `mode="introspect"`. | Unit test: load cached manifest, verify `inspect_info` fields accessible on elements. |

---

## 14. Rollout Plan

### Priority 1: Highest Impact (INTEGRATE + DESIGN)

| Component | Description | Deps | Rationale |
|-----------|-------------|------|-----------|
| IN-1: Type-aware ManifestDiff | Resolved signature comparison in INTEGRATE | Phase 5 core + Phase 4 ManifestDiff | Catches type-level breaking changes invisible to AST diff. Highest fidelity integration gate. |
| IN-2: MRO change detection | Inheritance restructuring gate | Phase 5 core | MRO changes are high-impact, low-frequency — worth flagging every time. |
| DS-1: Resolved signatures in DESIGN | True types in design context | Phase 5 core + `file_element_summary()` extension | Design decisions based on actual types (not forward-ref strings) improve downstream implementation quality. |
| DS-2: MRO in DESIGN | Class hierarchy context | Phase 5 core + `file_mro_summary()` | Inheritance-aware design for subclass features. |
| Registry: `file_resolved_type_summary()`, `file_mro_summary()`, `module_all_for()` | New query methods | Phase 5 core | Foundation for P1 consumers. |
| ManifestDiff: `changed_resolved_signatures`, `mro_changes`, `module_all_diff` | Diff extensions | Phase 5 core + Phase 4 ManifestDiff | Foundation for P1 INTEGRATE consumers. |

### Priority 2: Medium Impact (IMPLEMENT + PREFLIGHT)

| Component | Description | Deps |
|-----------|-------------|------|
| IM-1, IM-2, IM-3: Resolved types + runtime attrs + callable annotations in IMPLEMENT | Accurate implementation prompts | P1 (registry extensions) |
| PF-1: Dynamic export validation | `module_all` validation | P1 (`module_all_for()`) |
| PF-2: Callable contract validation | `is_callable` cross-check | Phase 5 core + Phase 6 call graph |
| DS-3, DS-4: `module_all` + runtime attrs in DESIGN | Complete design context | P1 (registry extensions) |

### Priority 3: Lower Impact (CALL GRAPH + PLAN INGESTION + PROMPT)

| Component | Description | Deps |
|-----------|-------------|------|
| CG-1: Runtime-callable dead code filtering | Improved dead code accuracy | Phase 5 core + Phase 6 `dead_candidates()` |
| PI-1, PI-2: `module_version` + resolved types in plan ingestion | Version-aware complexity assessment | P1 (registry extensions) |
| PR-1, PR-2, PR-3, PR-4: Tiered rendering extensions + graceful degradation | Budget-aware introspect rendering | P1 (registry extensions) |
| IN-3: `module_all` change detection | Export change visibility | P1 (`module_all_for()`) |

---

## 15. Configuration

New artisan config YAML fields:

```yaml
artisan:
  # Existing fields...

  # Phase 5 introspect pipeline integration
  enable_introspect: false              # Master toggle for introspect data consumption
  resolved_type_budget: 2000            # PR-2: max chars for resolved type context
```

Both fields are optional with the defaults shown above. `manifest_consumption_enabled: false` (Phase 4 kill switch) also disables all introspect consumers.

---

## 16. Open Questions / Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | **Import side effects during manifest generation.** Introspect mode requires importing modules, which may trigger side effects. If manifests are regenerated during the pipeline (e.g., IN-4 post-merge refresh), the import may interfere with pipeline state. | Medium | High | Post-merge refresh should use `mode="static"` (not `mode="introspect"`). Introspect manifests are generated pre-pipeline as a separate step. Document this constraint. |
| R2 | **Resolved type string length variance.** Fully-qualified type names (`pandas.core.frame.DataFrame`) are much longer than short names (`DataFrame`). In pathological cases, resolved signatures could blow the prompt budget. | Medium | Medium | PR-2 budget accounting + progressive compression drops `manifest_resolved_types` before `manifest_context`. `file_resolved_type_summary()` has its own budget parameter. |
| R3 | **MRO noise for simple classes.** Most classes have trivial MRO (`[MyClass, object]`). Rendering MRO for every class wastes tokens on uninformative data. | Low | Low | DS-2 only renders MRO when the chain is > 2 entries (i.e., has actual inheritance beyond `object`). |
| R4 | **`module_all` discrepancy with AST `__all__`.** Runtime and AST `__all__` may disagree (dynamic computation). Consumers must decide which source of truth to use. | Medium | Low | Runtime `module_all` is authoritative when available. AST-extracted `__all__` is the fallback. Document the precedence in `ManifestRegistry.module_all_for()`. |
| R5 | **Stale introspect data after code changes.** If code is modified but manifests aren't regenerated with `mode="introspect"`, the `inspect_info` data is stale. Phase 4's GD-3 digest-based staleness detection invalidates the entire manifest (including `inspect_info`), but this means losing structural data too. | Medium | Medium | Accept manifest-level staleness (GD-3). Introspect data is advisory — stale data is better than no data, but the staleness detection already handles the worst case. |
| R6 | **Adoption friction.** `enable_introspect` defaults to `False`, requiring explicit opt-in at two levels (HandlerConfig + pipeline.env). Teams may not discover the feature. | Low | Low | Default is intentionally conservative for a feature that requires module imports. Documentation + capability index entry will drive adoption. |

---

## 17. File Changes

| File | Change | Priority |
|------|--------|----------|
| `src/startd8/contractors/context_seed_handlers.py` | Add `enable_introspect` to `HandlerConfig` (line 443). Extend `_task_to_feature_context()` for DS-1, DS-2, DS-4. Extend `ImplementPhaseHandler` chunk enrichment for IM-1, IM-2, IM-3. | P1/P2 |
| `src/startd8/utils/manifest_registry.py` | Add `include_resolved_types` kwarg to `file_element_summary()` (line 499). Add `use_runtime_callable` kwarg to `dead_candidates()` (line 699). Add new methods: `file_resolved_type_summary()`, `file_mro_summary()`, `file_runtime_attributes()`, `module_all_for()`, `module_version_for()`. Extend `ManifestDiff` with `changed_resolved_signatures`, `mro_changes`, `module_all_diff`. | P1 |
| `src/startd8/contractors/integration_engine.py` | Extend `_manifest_pre_merge_diff()` (line 96) for IN-1, IN-2, IN-3. | P1 |
| `src/startd8/contractors/artisan_phases/development.py` | Extend `_build_manifest_context()` (line 1423) to render resolved types when available. | P2 |
| `src/startd8/contractors/prompt_utils.py` | Add `manifest_resolved_types` (T1) and `public_api_surface` (T3) to `CONTEXT_FIELD_TIERS` (line 18). Budget accounting for resolved type strings. | P3 |
| `src/startd8/workflows/builtin/domain_preflight_workflow.py` | Extend `_run_environment_checks()` (line 386) for PF-1, PF-2. | P2 |
| `src/startd8/contractors/artisan_phases/design_prompts/seed_mapping.py` | Extend `extract_manifest_context()` (line 163) for PI-1, PI-2. | P3 |
| `tests/unit/test_manifest_introspect_pipeline.py` | **New file**: Unit tests for all 7 consumer surfaces (AC-5P1 through AC-5P15). | P1 |
| `tests/unit/test_manifest_diff_introspect.py` | **New file**: `ManifestDiff` resolved signature + MRO comparison tests. | P1 |

---

## Appendix: Iterative Review Log

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

*(Pending first review round)*

### Areas Needing Further Review

*(Pending first review round)*

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

*(Awaiting first review round)*
