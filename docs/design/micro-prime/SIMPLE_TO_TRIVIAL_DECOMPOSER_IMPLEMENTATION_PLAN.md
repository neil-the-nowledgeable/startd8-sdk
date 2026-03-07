# Simple → Trivial Decomposer — Implementation Plan

**Date:** 2026-03-07
**Status:** DRAFT
**Source:** [SIMPLE_TO_TRIVIAL_DECOMPOSER_FEASIBILITY.md](./SIMPLE_TO_TRIVIAL_DECOMPOSER_FEASIBILITY.md)
**Related:** [MODERATE_DECOMPOSER_IMPLEMENTATION_PLAN.md](./MODERATE_DECOMPOSER_IMPLEMENTATION_PLAN.md), [REQ-MP-910_RECURSIVE_DECOMPOSITION_CORE.md](./REQ-MP-910_RECURSIVE_DECOMPOSITION_CORE.md), [DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md](../scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md), [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)

---

## Overview

This plan follows the feasibility document's recommended phasing (Phase 0 → 1 → 2 → 3) and maps each to concrete code changes. Phases 0 and 1 are independent and can be developed in parallel. Phase 2 is incremental. Phase 3 is gated on data from 0–2.

---

## Phase 0: Identical-Copy File Duplication (Highest Value, Zero Risk)

**Goal:** Detect tasks that are exact copies of a predecessor's output; skip all LLM phases and copy the file.

### Changes

1. **Plan ingestion / task schema** — Add `copy_source_task_id: Optional[str]` and `copy_source_file: Optional[str]` fields to `FeatureSpec` in `contractors/queue.py` (existing dataclass fields: `id`, `name`, `description`, `dependencies`, `target_files`, `status`, `metadata`). Populate during plan ingestion by scanning `task_description` for duplication signals (`"identical copy"`, `"duplicated identically"`, etc.) combined with `feature.dependencies` (not `depends_on` — plan ingestion maps seed `depends_on` to `FeatureSpec.dependencies: List[str]`). Copy detection requires `len(feature.dependencies) == 1` for unambiguous copy source. **Fallback inference** (R4-S5): if `copy_source_file` is not explicitly set during plan ingestion but the predecessor task has exactly one entry in `target_files`, infer `copy_source_file` from it; if the predecessor has zero or multiple `target_files`, reject the copy detection (do not guess).

2. **Copy detection utility** — New module `src/startd8/contractors/copy_detection.py`:
   - Must start with `from startd8.logging_config import get_logger; logger = get_logger(__name__)` (Leg 13 #15). Log at DEBUG for detection entry/exit, INFO for strategy selection (`file_copy` / `copy_and_modify` / rejected), WARNING for fallback triggers.
   - `detect_copy_task(feature: FeatureSpec) -> Optional[CopySource]` — NLP signal scan + `feature.dependencies` validation
   - `CopySource` dataclass:
     ```python
     @dataclass
     class CopySource:
         predecessor_id: str      # FeatureSpec.id of the source task
         source_file: str         # Relative path to copy from predecessor's output
         workspace_root: str = "" # For path validation; set by caller
     ```
   - Path normalization guard (R6-S7, R4-S4): use `resolved = Path(workspace_root, source_file).resolve(strict=False)` and verify via `resolved.is_relative_to(Path(workspace_root).resolve())` to block traversal. Use `Path.resolve()` instead of `os.path.abspath()` for correct symlink handling on macOS (Leg 9 #20). The `is_relative_to()` check (Python 3.9+) is preferred over string `startswith()` to avoid prefix collisions (e.g., `/workspace2` falsely matching `/workspace`).
   - **Exception discipline** (Leg 13 #14): `detect_copy_task` must use narrow exception types — `except ValueError` for signal parsing failures, `except (KeyError, AttributeError)` for missing fields. No bare `except Exception` in this module.

3. **Prime contractor integration** — In `PrimeContractorWorkflow.develop_feature()`, add an early exit **as the first conditional** before any code generation logic (Leg 13 #20 — detection without action is dead code; the copy detection signal must flow all the way to the skip logic):
   - If `feature.copy_source_task_id is not None`:
     1. Look up predecessor task by ID. If predecessor `status != FeatureStatus.COMPLETE`, raise `ValueError(f"Copy source task {id} not complete (status={status})")` — do not attempt file read. (Note: the enum value is `COMPLETE`, not `COMPLETED` — see `queue.py` line 34.)
     2. Read predecessor's output file with a **30-second timeout** using `concurrent.futures.ThreadPoolExecutor(max_workers=1)` and `future.result(timeout=30)`. Wrap in `try/finally` to call `executor.shutdown(wait=False)` for I/O lock release. This provides a deterministic, stdlib-only timeout mechanism that works on all platforms (R4-S1).
     3. **Overwrite policy**: controlled by config `copy_overwrite: bool = True`. When `False`, use **TOCTOU-safe** exclusive creation: `open(target_path, "xb")` which atomically fails with `FileExistsError` if the file already exists — no separate `exists()` + `open()` race window (R4-S2). When `True` (default), use `open(target_path, "wb")` to overwrite.
     4. Write to `feature.target_files[0]`.
     5. **SHA-256 verify** — compute `hashlib.sha256(source).hexdigest() == hashlib.sha256(target).hexdigest()`. Predecessor file must remain accessible until verification completes (do not clean up predecessor artifacts before this step).
     6. Return `GenerationResult(success=True, generated_files=[target_path], cost_usd=0.0, input_tokens=0, output_tokens=0, iterations=0, model="", metadata={"strategy": "file_copy", "copy_source_task_id": predecessor_id, "sha256": digest})`.
   - If predecessor failed → raise `ValueError` with predecessor task ID and status
   - If predecessor file missing on disk → raise `FileNotFoundError` referencing predecessor task ID
   - **Exception discipline** (Leg 13 #14): Use `except (OSError, FileNotFoundError, TimeoutError)` for file operations, `except ValueError` for status/validation checks. Reserve `except Exception` only for the top-level per-task error guard in `develop_feature()`, not in copy helpers.

4. **`copy_and_modify` edge case** — If duplication signal + modification signal detected → set `strategy="copy_and_modify"`, inject predecessor output as `{reference_implementation}` in the spec prompt. Still uses LLM but with better context. **Dependency:** Prompt templates used in the spec/draft phase must accept an optional `{reference_implementation}` slot. If the slot is absent from the template, the predecessor output is silently omitted (no crash). Render test required to verify injection. **Prompt-budget guard** (R4-S6, Leg 10 #37): before injecting `{reference_implementation}`, measure its token count against a configurable budget (default: 2000 tokens). If the predecessor output exceeds the budget, apply tiered compression: (1) strip comments and docstrings, (2) truncate to budget with a `# [TRUNCATED — full source: {path}]` marker. This prevents `copy_and_modify` prompts from blowing token limits on large predecessor files.

5. **Metrics** — `prime.file_copy_tasks`, `prime.file_copy_cost_saved_usd` OTel counters.

6. **Tests:**
   - Positive: byte-identical copy (SHA-256 match)
   - Negative: "adapted copy" / "modified to" language → NOT routed to file-copy
   - Path traversal: `../../etc/passwd` in `source_file` → blocked by normalization guard
   - Predecessor not completed: `status=PENDING` → `ValueError` with task ID and status
   - Predecessor file missing: `FileNotFoundError` referencing predecessor task ID
   - Overwrite policy: target exists + `copy_overwrite=False` → `FileExistsError`; `copy_overwrite=True` → overwrite succeeds
   - Multi-dependency rejection: `len(feature.dependencies) != 1` → not routed to file-copy
   - Read timeout: mock filesystem read that blocks via `ThreadPoolExecutor` → assert `TimeoutError` within 30s and executor shutdown (R4-S1)
   - TOCTOU overwrite: concurrent test — target deleted between hypothetical check and open → `open(..., "xb")` still behaves correctly (R4-S2)
   - Fallback inference: predecessor with exactly one `target_file` → `copy_source_file` inferred; predecessor with multiple `target_files` → detection rejected (R4-S5)
   - Path symlink: use `Path.resolve()` in both prod and test; verify macOS `/var` → `/private/var` doesn't break assertions (Leg 9 #20)
   - Path prefix collision: `/workspace2/file.py` must NOT pass guard when `workspace_root=/workspace` (R4-S4)

7. **Test fixture update checklist** (Leg 9 #29): After adding `copy_source_task_id` and `copy_source_file` to `FeatureSpec`, run `grep -r "FeatureSpec\|FakeSeedTask" tests/` and update all fixture constructors with new fields defaulting to `None`. Existing tests must continue to pass without modification (new fields are optional).

**Estimated scope:** ~300 lines new code + ~150 lines tests.

---

## Phase 1: Class-Boilerplate Decomposer (via Moderate Decomposer Extension)

**Goal:** When the Moderate Decomposer's `ClassDecomposeStrategy` finds that **all** sub-elements are TRIVIAL (template-matched), mark them all as `deterministic=True` and skip `_handle_simple` entirely.

**Approach:** Extend existing code rather than building a separate Simple Decomposer (answers Open Question #1: **unify**).

### Changes

1. **`ClassDecomposeStrategy` enhancement** — In the existing Moderate Decomposer (`micro_prime/decomposer.py`), after `ClassDecomposeStrategy.plan()` produces sub-elements, check if every sub-element passes `template_registry.is_trivial()`. **Dependency:** `ClassDecomposeStrategy.__init__` must accept an optional `template_registry: Optional[TemplateRegistry] = None` parameter. The engine (`micro_prime/engine.py`) passes its `self._templates` to the strategy at construction.
   - If **all** sub-elements are TRIVIAL: set `sub_element.deterministic = True` for each. Template render output is stored in the `sub_results: dict[str, str]` dict (keyed by `sub_element.name`) that is passed to `assemble()`. The `SubElement` dataclass itself is unchanged — rendered content flows through `sub_results`, not a new field.
   - The TRIVIAL check must use `getattr(self, "_templates", None)` to access the template registry, not bare `self._templates`, in case test fixtures use `__new__` to bypass `__init__` (Leg 9 #26).
   - Assembly uses `ClassDecomposeStrategy.assemble(plan, sub_results, skeleton)` unchanged.
   - The resulting `GenerationResult` for an all-TRIVIAL decomposition: `GenerationResult(success=True, generated_files=[...], cost_usd=0.0, input_tokens=0, output_tokens=0, iterations=0, model="", metadata={"strategy": "simple_decompose", "llm_calls": 0})`.
   - **Mock discipline** (Leg 9 #23): All `mock.patch` calls for `ClassDecomposeStrategy` must use `autospec=True` to catch signature drift when adding the `template_registry` parameter. Grep test files for hand-written mock constructors and update them.

2. **Strategy enum and routing contract** — Add `AssemblyStrategy(str, Enum)` to `complexity/models.py`:
   ```python
   class AssemblyStrategy(str, Enum):
       FILE_COPY = "file_copy"             # Phase 0: byte-identical copy
       COPY_AND_MODIFY = "copy_and_modify"  # Phase 0: LLM with predecessor context
       TEMPLATE = "template"                # TRIVIAL: direct template render
       SIMPLE_DECOMPOSE = "simple_decompose" # All sub-elements TRIVIAL
       LLM_SIMPLE = "llm_simple"            # Ollama/local model
       LLM_MODERATE = "llm_moderate"        # Cloud model (Sonnet)
       ESCALATE = "escalate"                # COMPLEX: premium model (Opus)
   ```
   **Routing contract** — each strategy maps to exactly one handler, no overlap:
   | Strategy | Handler | LLM? |
   |----------|---------|------|
   | `FILE_COPY` | `_handle_file_copy()` in prime contractor | No |
   | `COPY_AND_MODIFY` | `_handle_simple()` with predecessor injection | Yes |
   | `TEMPLATE` | `template_registry.render()` | No |
   | `SIMPLE_DECOMPOSE` | `ClassDecomposeStrategy.assemble()` with template sub-results | No |
   | `LLM_SIMPLE` | `_handle_simple()` via Ollama | Yes |
   | `LLM_MODERATE` | `_handle_moderate()` via cloud model | Yes |
   | `ESCALATE` | `_handle_complex()` / escalation path | Yes |

   Record as OTel span attribute `assembly.strategy`.

   **Post-change requirement** (Leg 10 #1): After adding `AssemblyStrategy` to `complexity/models.py`, run `pip install -e .` before testing. Entry-point-based discovery and enum imports require reinstall.

3. **Template-first short-circuit in `_handle_simple`** (R5-S1) — Before invoking Ollama, try `template_registry.is_trivial()`. If it matches, render and return immediately (zero LLM). This catches cases where template expansion (Phase 2) makes previously-SIMPLE elements directly TRIVIAL. **Test:** Mock Ollama; process a SIMPLE element that matches a template; assert Ollama call count is 0 and output matches template render exactly. **Fixture warning** (Leg 9 #31): Test fixtures that expect SIMPLE classification must override ALL conjunctive fields: `manifest_coverage="full"`, `edit_mode="create"`, `blast_radius=0`, `caller_count=0`, `target_file_count=1`, `estimated_loc < 150`. Default `TaskComplexitySignals` values are designed to produce MODERATE, not SIMPLE.

4. **All-or-nothing assembly** (R4-S1) — Assemble in memory; splice only if all sub-elements succeed. On any failure, fall back to `_handle_simple` with the **rejection reason** passed as context. Rejection reasons use a typed enum (`RejectionReason`):
   ```python
   class RejectionReason(str, Enum):
       NO_TEMPLATE_MATCH = "no_template_match"
       SKELETON_MISMATCH = "skeleton_mismatch"
       UNSAFE_DECORATOR = "unsafe_decorator"
       RENDER_CONTRACT_VIOLATION = "render_contract_violation"
       SYNTAX_ERROR = "syntax_error"
       EMPTY_OUTPUT = "empty_output"
   ```
   The fallback path receives the reason as a `metadata["rejection_reason"]` key on the internal result, which the telemetry hook captures before invoking `_handle_simple`. This surfaces in OTel spans and the JSON report.

5. **`ast.parse` syntax gate** (R6-S1) — Run `ast.parse()` on assembled output before writing to disk. Catch `SyntaxError` only (Leg 13 #14 — narrow exception types; do not catch `Exception`): set `deterministic=False` on the plan, record `RejectionReason.SYNTAX_ERROR`, and fall back to `_handle_simple`. The fallback receives the original element spec unchanged. The gate must use static analysis only (`ast.parse`), never `import` or `exec`, to prevent cross-file import poisoning (Leg 9 #27).

6. **Config gating** — `micro_prime.enable_simple_decomposer: bool = False` in config, with `simple_decomposer.confidence_threshold: float`.

7. **Recursion policy** (REQ-MP-910) — Default behavior remains non-recursive (leaf-only). Sub-elements are only eligible for re-decomposition when recursion is enabled and the policy permits it. **Negative test:** with recursion disabled, construct a decomposed sub-element whose `element_spec` would itself qualify for decomposition (e.g., a class-like synthetic spec); assert the engine blocks re-entry with a bounded rejection reason (e.g., `recursion_blocked`).

8. **`decomposition_source` tracking** (R2-S3) — Add `decomposition_source: Optional[str] = None` field to `ForwardElementSpec` (values: `"simple"`, `"moderate"`, `"copy"`). **Fixture update checklist** (Leg 9 #29): Run `grep -r "ForwardElementSpec\|FakeElement\|MockElement" tests/` and update all fixture constructors. The new field defaults to `None` so existing tests pass, but any test asserting on serialized output must account for the new key.

9. **Post-assembly file-level validation gate** (feasibility R3-S4) — After splice, run a file-level gate using **static analysis only** (`ast.parse` + string search — never `import` or `exec` to prevent cross-file import poisoning, Leg 9 #27):
   - No `[STARTD8-SKELETON]` markers remain in the assembled file → **FAIL** (always wrong)
   - No nested duplicate function/class definitions (AST walk for duplicate `def`/`class` names at the same scope) → **FAIL** (always wrong)
   - Required functions/classes from `ForwardFileSpec.elements` are present → **WARN** (may be filled by a later element's assembly in multi-element files; Leg 13 #18 — advisory-by-default for greenfield generation). Configurable severity per check.
   - On FAIL: rollback splice (restore original file content), record `RejectionReason.RENDER_CONTRACT_VIOLATION`, and escalate.
   - **Validator addition audit** (Leg 9 #25): After adding this gate, run the full existing test suite to verify existing "clean code" test fixtures still pass. New validators can introduce false positives on existing fixtures.
   - **Test:** inject a skeleton marker into an assembled file → gate rejects, splice is rolled back.

**Estimated scope:** ~250 lines modified/new in decomposer + ~250 lines tests.

---

## Phase 2: Template Registry Expansion

**Goal:** Convert more SIMPLE elements to TRIVIAL directly by adding templates.

### New Templates (in `templates.py` or template registry)

1. `__init__` with optional params (params with defaults)
2. `__init__` with `*args`/`**kwargs` (store in `self._extra` or `pass`)
3. Simple validation pattern (`if not x: raise ValueError(...)`)
4. Pydantic model / `@dataclass` boilerplate (R6-S3) — typed fields → class body
5. Render contract definition (R4-S2) — body-only vs full `def`, indentation policy, trailing newline

### Safety

- Safe literal serialization via `repr()` for string defaults (R4-S7)
- Name sanitization — reject non-identifier characters (R5-S7, R2-S7)
- Relaxed templates require explicit allowlist, disabled by default (R1-S7)
- No-regression guard — if template output equals DFA stub, reject and fall back to LLM (R5-S4)

**Estimated scope:** ~150 lines new templates + ~100 lines tests.

---

## Phase 3: Function-Body Decomposition (Conditional)

**Gate:** Only proceed if run data shows >15% of SIMPLE functions have docstring clauses that map to existing templates. Check via `--dry-run-deterministic` report: `template_coverage` map and `rejection_reasons["no_template_match"]` count for SIMPLE functions.

**Goal:** Decompose SIMPLE functions/methods into a sequence of template-renderable clauses. When all clauses map to templates, assemble deterministically — zero LLM cost. When any clause fails to map, fall back to `_handle_simple` (Ollama).

**Key difference from Phase 1:** Phase 1 extends the Moderate Decomposer's `ClassDecomposeStrategy` to mark all-TRIVIAL sub-elements as deterministic. Phase 3 operates at the SIMPLE tier on **functions**, not classes. It does not use `ModerateDecomposer` — it is a pre-check in `_handle_simple` (after the template-first short-circuit, before Ollama).

**Key difference from `FunctionChainStrategy`:** `FunctionChainStrategy` (REQ-MP-902) decomposes MODERATE functions into helper sub-functions + dispatch body, each generated via LLM. Phase 3 maps clauses to **existing templates** — no LLM, no helper functions. It reuses `_parse_responsibilities()` for clause extraction but maps clauses to template types rather than creating synthetic helper specs.

### Prerequisites

- Phase 2 template registry must include sufficient templates (at minimum: `simple_validation`, `dunder_method`, `config_constant`, `property_getter`, `typed_constant_default`, `dataclass_boilerplate`)
- `_parse_responsibilities()` in `decomposer.py` is stable and reusable (already used by `FunctionChainStrategy`)
- `AssemblyStrategy.SIMPLE_DECOMPOSE` enum value exists (Phase 1)
- `RejectionReason` enum exists (Phase 1)
- Template-first short-circuit in `_handle_simple` exists (Phase 1) — Phase 3 runs **after** it (if the whole element doesn't match a single template, try decomposing into clauses)

### Changes

1. **Clause-to-template mapper** — New module `src/startd8/micro_prime/clause_mapper.py`:
   - Must start with `from startd8.logging_config import get_logger; logger = get_logger(__name__)` (Leg 13 #15).
   - `ClauseMapping` dataclass:
     ```python
     @dataclass
     class ClauseMapping:
         clause_text: str           # Original responsibility clause
         template_name: str         # Matched template name (e.g. "simple_validation")
         synthetic_spec: ForwardElementSpec  # Synthetic element spec for template rendering
         confidence: float          # 0.0–1.0 match confidence
     ```
   - `map_clause_to_template(clause: str, element: ForwardElementSpec, file_spec: ForwardFileSpec, template_registry: TemplateRegistry) -> Optional[ClauseMapping]`:
     - Matches clause text against known patterns using keyword signals (not NLP/LLM):
       | Clause Signal | Template | Synthetic Spec Construction |
       |---|---|---|
       | `"validate"`, `"check"`, `"verify"`, `"ensure"` + single param ref | `simple_validation` | `kind=FUNCTION, name=validate_{param}`, 1-param signature |
       | `"initialize"`, `"set up"`, `"store"`, `"assign"` + param list | `dunder_method` (__init__) | `kind=METHOD, name=__init__`, params from element signature |
       | `"return string"`, `"represent"`, `"display"`, `"format"` | `dunder_method` (__repr__/__str__) | `kind=METHOD, name=__repr__`, parent_class from element |
       | `"compare"`, `"equal"`, `"match"` | `dunder_method` (__eq__) | `kind=METHOD, name=__eq__` |
       | `"hash"` | `dunder_method` (__hash__) | `kind=METHOD, name=__hash__` |
       | `"constant"`, `"default"`, `"config"` + assignment pattern | `config_constant` / `typed_constant_default` | `kind=CONSTANT, name` extracted from clause |
     - Each synthetic spec is validated via `template_registry.is_trivial(synthetic_spec)` before returning
     - If no pattern matches → return `None`
     - **Name sanitization** (R5-S7): all synthetic spec names validated via `_is_safe_identifier()` before construction
     - **Exception discipline** (Leg 13 #14): use `except (KeyError, ValueError)` for parsing failures, not bare `except Exception`

   - `map_all_clauses(clauses: list[str], element: ForwardElementSpec, file_spec: ForwardFileSpec, template_registry: TemplateRegistry) -> Optional[list[ClauseMapping]]`:
     - Maps each clause via `map_clause_to_template()`
     - Returns `None` if **any** clause fails to map (all-or-nothing, R4-S1)
     - Returns the full list only when all clauses succeed
     - Logs at DEBUG for each clause match/miss, INFO for all-match or first-miss

2. **`FunctionBodyDecomposer`** — New class in `clause_mapper.py` (not in `decomposer.py` — this is a SIMPLE-tier pre-check, not a ModerateDecomposer strategy):
   ```python
   class FunctionBodyDecomposer:
       """Decomposes SIMPLE functions into template-renderable clauses (Phase 3).

       Sits between the template-first short-circuit and Ollama in _handle_simple.
       Unlike FunctionChainStrategy (MODERATE tier, LLM-generated helpers), this
       maps clauses to existing templates for zero-LLM assembly.
       """

       def __init__(
           self,
           template_registry: TemplateRegistry,
           confidence_threshold: float = 0.7,
       ) -> None: ...

       def try_decompose(
           self,
           element: ForwardElementSpec,
           file_spec: ForwardFileSpec,
           contracts: list[InterfaceContract],
       ) -> Optional[str]:
           """Attempt to decompose a SIMPLE function into template-rendered clauses.

           Returns assembled code string on success, None on failure.
           Caller (engine._handle_simple) falls back to Ollama on None.
           """
   ```
   - **Applicability check** (inline, not a separate `can_handle`):
     1. `element.kind` in `(FUNCTION, METHOD, ASYNC_FUNCTION, ASYNC_METHOD)` — not CLASS
     2. `element.docstring_hint` is not None and not empty
     3. `_parse_responsibilities(element.docstring_hint)` returns 2+ clauses
     4. Clause count ≤ `max_helpers_per_function` (reuse existing config bound)
     5. **Decorator guard** (R2-S4): reject if `element.decorators` contains any entry not in a safe allowlist (`["staticmethod", "classmethod", "property", "abstractmethod", "overload", "override"]`)
   - **Decomposition flow:**
     1. Parse clauses via `_parse_responsibilities(element.docstring_hint)`
     2. Map all clauses via `map_all_clauses()` — if any fail, return `None`
     3. For each `ClauseMapping`, render via `template_registry.match(mapping.synthetic_spec, file_spec, contracts)`
     4. If any render returns `None` → return `None` (all-or-nothing)
     5. **No-regression guard** (R5-S4): if any rendered body equals DFA stub (`_is_dfa_stub()`), return `None`
     6. Assemble: concatenate rendered bodies with `\n` separator
     7. **`ast.parse` syntax gate** (R6-S1): validate assembled code; on `SyntaxError`, return `None`
     8. Return assembled code
   - **Confidence threshold**: default 0.7 (higher than class decomposition's 0.6 per feasibility §6 Phase 3)
   - **Recursion policy** (REQ-MP-910): `FunctionBodyDecomposer` produces final code, not sub-elements for re-processing. No recursive decomposition applies by construction — `try_decompose` returns a string, not a `DecompositionPlan`.
   - **`decomposition_source` tracking** (R2-S3): set `element.decomposition_source = "simple"` before returning success (via `model_copy(update=...)` — do not mutate the original spec)

3. **Engine integration** — In `MicroPrimeEngine._handle_simple()` (engine.py), add a second pre-check **after** the template-first short-circuit (line ~1161) and **before** Ollama generation (line ~1171):
   ```python
   # Phase 3: Function-body decomposition — try to decompose SIMPLE function
   # into template-renderable clauses before falling back to Ollama.
   if self._config.enable_simple_decomposer and self._function_body_decomposer is not None:
       decomposed_code = self._function_body_decomposer.try_decompose(
           element, file_spec, contracts,
       )
       if decomposed_code is not None:
           logger.info(
               "Function-body decomposition succeeded for %s (0 LLM calls)",
               element.name,
           )
           # Record metrics
           _record_simple_decompose_succeeded(file_path)
           self._completed.append({
               "element": {
                   "name": element.name,
                   "parent_class": element.parent_class,
                   "kind": element.kind,
               },
               "file_path": file_path,
               "code": decomposed_code,
               "syntax_valid": True,
           })
           result = ElementResult(
               element_name=element.name,
               file_path=file_path,
               tier=TierClassification.SIMPLE,
               classification_reason=reasoning,
               success=True,
               code=decomposed_code,
               template_used=True,
               template_name="function_body_decompose",
               model="template",
               verification_verdict="skipped",
               decomposition_metadata={
                   "strategy": "function_body_decompose",
                   "clause_count": len(clauses),
                   "llm_calls": 0,
               },
           )
           self._metrics.record(result)
           return result
       else:
           _record_simple_decompose_rejected(file_path)
   ```
   - **Dependency**: `MicroPrimeEngine.__init__()` must instantiate `FunctionBodyDecomposer` when `enable_simple_decomposer` is True:
     ```python
     self._function_body_decomposer: Optional[FunctionBodyDecomposer] = None
     if self._config.enable_simple_decomposer:
         from startd8.micro_prime.clause_mapper import FunctionBodyDecomposer
         self._function_body_decomposer = FunctionBodyDecomposer(
             template_registry=self._templates,
             confidence_threshold=self._config.simple_decomposer_confidence_threshold,
         )
     ```
   - **Lazy import** (Leg 11 #55): Use conditional import inside `__init__` to avoid import cost when feature is disabled.

4. **OTel counters** — Add to the existing OTel meter in `engine.py`:
   ```python
   _simple_decompose_attempted = _meter.create_counter(
       "micro_prime.simple_decompose_attempted",
       description="SIMPLE function body decomposition attempts",
   )
   _simple_decompose_succeeded = _meter.create_counter(
       "micro_prime.simple_decompose_succeeded",
       description="SIMPLE function body decompositions that produced code",
   )
   _simple_decompose_rejected = _meter.create_counter(
       "micro_prime.simple_decompose_rejected",
       description="SIMPLE function body decompositions that fell back to LLM",
   )
   ```
   Use `patch.object(module, "attr", create=True)` in tests for optional OTel imports (Leg 9 #28).

5. **Report integration** — Update `SimpleDecomposerReport` (Cross-Cutting) to include Phase 3 metrics:
   - `function_decompose_attempted: int = 0`
   - `function_decompose_succeeded: int = 0`
   - `function_decompose_rejected: int = 0`
   - `clause_template_hits: Dict[str, int] = field(default_factory=dict)` — per-template-type counts from clause mapping

6. **Tests** (`tests/unit/micro_prime/test_clause_mapper.py`):

   **Clause mapper tests:**
   - `test_validate_clause_maps_to_simple_validation`: clause "validate the input parameter" → `simple_validation` template match
   - `test_init_clause_maps_to_dunder_init`: clause "initialize and store parameters" → `dunder_method` (__init__) match
   - `test_repr_clause_maps_to_dunder_repr`: clause "return string representation" → `dunder_method` (__repr__) match
   - `test_unknown_clause_returns_none`: clause "do something complex with external API" → `None`
   - `test_map_all_clauses_all_or_nothing`: one unmappable clause → entire mapping returns `None`
   - `test_unsafe_synthetic_name_rejected`: clause producing non-identifier name → `None`

   **FunctionBodyDecomposer tests:**
   - `test_decompose_two_clause_function`: function with "validate input; return formatted result" → assembled code from 2 templates
   - `test_decompose_non_function_rejected`: CLASS element → `None`
   - `test_decompose_no_docstring_rejected`: element with `docstring_hint=None` → `None`
   - `test_decompose_single_clause_rejected`: only 1 clause → `None` (need 2+)
   - `test_decompose_decorated_function_rejected`: element with `@app.route` decorator → `None`
   - `test_decompose_safe_decorator_allowed`: `@staticmethod` decorator → proceeds
   - `test_decompose_syntax_error_fallback`: assembled code fails `ast.parse` → `None`
   - `test_decompose_stub_output_fallback`: template renders DFA stub → `None`
   - `test_decompose_sets_decomposition_source`: returned code triggers `decomposition_source="simple"` in metadata

   **Engine integration tests:**
   - `test_simple_function_body_decompose_zero_llm`: Mock Ollama; process SIMPLE function with 2 template-mappable clauses; assert Ollama call count is 0 and output matches template assembly
   - `test_simple_function_body_decompose_disabled`: `enable_simple_decomposer=False` → decomposer not invoked, Ollama called
   - `test_simple_function_body_decompose_fallback_to_ollama`: function with unmappable clause → decomposer returns None, Ollama invoked

   **Fixture warning** (Leg 9 #31): Test fixtures that expect SIMPLE classification must override ALL conjunctive `TaskComplexitySignals` fields.
   **Mock discipline** (Leg 9 #23): All `mock.patch` calls must use `autospec=True`.
   **`getattr` resilience** (Leg 9 #26): Access `self._function_body_decomposer` via `getattr(self, "_function_body_decomposer", None)` in engine code that test fixtures using `__new__` might reach.

### Safety

- **All-or-nothing** (R4-S1): assembled in memory; returned only if all clauses render and `ast.parse` passes
- **Decorator guard** (R2-S4): reject functions with complex decorators (only safe allowlist proceeds)
- **Name sanitization** (R5-S7, R2-S7): synthetic spec names validated via `_is_safe_identifier()`
- **Safe literal serialization** (R4-S7): template rendering already uses `repr()` for defaults (Phase 2)
- **No-regression guard** (R5-S4): reject if any rendered body equals DFA stub
- **`ast.parse` gate** (R6-S1): syntax validation on assembled output; `SyntaxError` → fall back, never crash
- **Recursion policy** (REQ-MP-910): `try_decompose` returns a string, not a plan — recursion does not apply by construction
- **Rejection reason injection** (R6-S4): when falling back to `_handle_simple` after Phase 3 rejection, the rejection reason (e.g., `"clause_3_no_template_match"`) is passed as `metadata["rejection_reason"]` so the LLM prompt can include focused context about what the deterministic path could not handle

### Decision: Separate module vs extending decomposer.py

Phase 3 lives in a **new module** (`clause_mapper.py`) rather than extending `decomposer.py` because:
1. `decomposer.py` implements the `DecompositionStrategy` protocol which produces `DecompositionPlan` + `SubElement` objects for the MODERATE tier. Phase 3 does not produce plans or sub-elements — it returns assembled code directly.
2. `FunctionBodyDecomposer.try_decompose()` is called from `_handle_simple()`, not from `_handle_moderate()`. Mixing tiers in one module violates the routing contract (R1-S1).
3. `clause_mapper.py` can import from `decomposer.py` (for `_parse_responsibilities`) without circular dependency.

**Estimated scope:** ~200 lines new code (`clause_mapper.py`) + ~300 lines tests (`test_clause_mapper.py`).

---

## Cross-Cutting Concerns (All Phases)

| Concern | Approach |
|---------|----------|
| **Observability** | OTel counters on meter `startd8.micro_prime` (same as existing `micro_prime.decomposition_*`): `micro_prime.simple_decompose_attempted`, `micro_prime.simple_decompose_succeeded`, `micro_prime.simple_decompose_rejected`. Rejection reason taxonomy via `RejectionReason` enum (see Phase 1, Step 4). `assembly.strategy` span attribute (R6-S6). |
| **CLI dry-run** | `--dry-run-deterministic` flag combining copy detection + simple decomposition audit (R2-S6, R3-S7, R5-S2) |
| **Reporting** | `.startd8/reports/simple-decomposer.json`. Implement as a typed `@dataclass` (Leg 13 #16 — typed structures over raw dicts; IDE autocomplete catches stale keys, missing fields caught at construction). Serialize via `dataclasses.asdict()`. **Advisory persistence** (R4-S7, Leg 11 #70): wrap report file I/O in `try/except OSError` with `logger.warning("Report write failed: %s", err)`; never fail a successful generation run due to a non-critical report write error: |

```python
@dataclass
class CostSavings:
    llm_calls_avoided: int = 0
    usd_saved_estimate: float = 0.0
    per_call_rate_usd: float = 0.005

@dataclass
class ReportMeta:
    schema_version: str = "1.0.0"  # SemVer; bump on field additions/removals (R4-S3, Leg 10 #39)
    sdk_version: str = ""           # startd8.__version__
    python_version: str = ""        # platform.python_version()

@dataclass
class SimpleDecomposerReport:
    run_id: str = ""
    timestamp: str = ""  # ISO-8601
    _meta: ReportMeta = field(default_factory=ReportMeta)
    attempted: int = 0
    succeeded: int = 0
    rejected: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)   # RejectionReason.value → count
    template_coverage: Dict[str, int] = field(default_factory=dict)   # template_name → count
    cost_savings: CostSavings = field(default_factory=CostSavings)
    deterministic_ratio: float = 0.0
```

| Concern (continued) | Approach |
|---------|----------|
| **Idempotence** | Two-pass test: running twice produces identical output (R4-S5) |
| **Skeleton-signature mismatch gate** | Reject decomposition if DFA stub signature differs from `ForwardElementSpec` (R4-S4) |
| **Decorator guard** | Reject decomposition for elements with complex decorators (R2-S4) |
| **Success metrics** | Track `deterministic_elements / total_elements` per run; target 40% after Phase 0+1, 60% after Phase 0+1+2 (R3-S5) |

---

## Implementation Order

```
Phase 0 (file copy)         <- standalone, no dependencies, immediate value      ✅ DONE
Phase 1 (class boilerplate) <- extends existing Moderate Decomposer              ✅ DONE
  +-- Strategy enum + template short-circuit (shipped with Phase 1)              ✅ DONE
Phase 2 (template expansion) <- incremental, each template is independent        ✅ DONE
Phase 3 (function body)      <- gated on Phase 0–2 metrics
  +-- clause_mapper.py (new module, ~200 lines)
  +-- engine.py integration (insert after template short-circuit, before Ollama)
  +-- test_clause_mapper.py (~300 lines)
  +-- OTel counters + report integration
```

Phases 0, 1, and 2 are complete. Phase 3 depends on:
- Phase 2 templates (clause mapping targets)
- Phase 1 `enable_simple_decomposer` config gate
- Phase 1 `RejectionReason` enum
- `_parse_responsibilities()` from `decomposer.py` (stable, used by FunctionChainStrategy)

---

## Implementation Guardrails (from SDK Lessons Learned)

Checklist for implementers — each item references a validated lesson from the SDK knowledge base.

### Before Coding

- [ ] Verify all referenced classes/methods exist in current codebase (`develop_feature()`, `ClassDecomposeStrategy`, `FeatureSpec.dependencies`) — Leg 13 #21
- [ ] Read `develop_feature()` actual signature and existing early-exit patterns before writing `copy_detection.py` — Leg 10 #8

### Per New Module

- [ ] Every new `.py` file starts with `from startd8.logging_config import get_logger; logger = get_logger(__name__)` — Leg 13 #15
- [ ] No bare `except Exception` in helper functions; narrow to specific types — Leg 13 #14
- [ ] All path operations use `Path.resolve()`, not `os.path.abspath()` — Leg 9 #20

### Per New Field on Data Models

- [ ] `grep -r "FeatureSpec\|FakeSeedTask" tests/` and update all fixture constructors — Leg 9 #29
- [ ] `grep -r "ForwardElementSpec\|FakeElement\|MockElement" tests/` and update fixtures — Leg 9 #29
- [ ] Run `pip install -e .` after adding enums to `complexity/models.py` — Leg 10 #1

### Per New Validator/Gate

- [ ] Run full existing test suite after adding gate to catch false positives on existing fixtures — Leg 9 #25
- [ ] Use `ast.parse` only (static analysis), never `import`/`exec` — Leg 9 #27
- [ ] Downgrade "element present" checks to WARN in greenfield generation contexts — Leg 13 #18

### Per Test File

- [ ] Use `autospec=True` on all `mock.patch` calls for modified classes — Leg 9 #23
- [ ] Override ALL conjunctive `TaskComplexitySignals` fields when expecting SIMPLE tier — Leg 9 #31
- [ ] Use `getattr(self, "_attr", None)` in code accessed by `__new__`-based fixtures — Leg 9 #26
- [ ] Use `patch.object(module, "attr", create=True)` for optional OTel imports — Leg 9 #28

### Copy Detection Specific

- [ ] `detect_copy_task()` signal must flow to `develop_feature()` skip logic — detection is dead code without action — Leg 13 #20
- [ ] All detection logic lives in `copy_detection.py`, not split across modules — Leg 12 #6

### Phase 3: Function-Body Decomposition Specific

- [ ] `clause_mapper.py` imports `_parse_responsibilities` from `decomposer.py` — verify function is importable (not underscore-private in `__all__`) — Leg 12 #6
- [ ] `FunctionBodyDecomposer.try_decompose()` returns `str | None`, NOT `DecompositionPlan` — enforces leaf-only constraint by construction — R2-S1
- [ ] Engine integration inserts **after** template-first short-circuit, **before** Ollama — verify line ordering in `_handle_simple()` — Leg 13 #21
- [ ] Clause-to-template mapping uses keyword signals only (no LLM, no regex on user content) — keeps Phase 3 deterministic and zero-cost
- [ ] Safe decorator allowlist is a `frozenset` constant, not inline strings — prevents typo drift
- [ ] `getattr(self, "_function_body_decomposer", None)` in engine for `__new__`-based test fixture resilience — Leg 9 #26
- [ ] Lazy import of `FunctionBodyDecomposer` inside `__init__` conditional — Leg 11 #55
- [ ] Update `test_logger_acquisition_policy.py` allowlist for `clause_mapper` module — Leg 9 #33
- [ ] Synthetic `ForwardElementSpec` instances created by clause mapper must NOT set `decomposition_source` (only the final returned code triggers that metadata) — Leg 13 #64

---

## Traceability: Feasibility Suggestions → Plan

| Suggestion | Phase | Status | Notes |
|------------|-------|--------|-------|
| R1-S1 (decision order/exclusivity) | 1 | Accepted | Strategy enum + dispatch routing |
| R1-S2 (config switch/threshold) | 1 | Accepted | `enable_simple_decomposer` config |
| R1-S3 (deterministic child ordering) | 1 | Accepted | `manifest_order` source |
| R1-S4 (template safety gate) | 1 | Accepted | Signature verification before decomposition |
| R1-S5 (validation matrix) | 1 | Accepted | Positive/negative/mixed test cases |
| R1-S6 (telemetry) | Cross-cutting | Accepted | OTel counters |
| R1-S7 (relaxed template allowlist) | 2 | Accepted | Disabled by default |
| R2-S1 (leaf-only constraint) | 1 | Accepted | Assert in tests |
| R2-S2 (`try_decompose` signature) | 1 | Accepted | `Optional[DecompositionPlan]` return |
| R2-S3 (`decomposition_source` field) | 1 | Accepted | `"simple"`, `"moderate"`, `"copy"` |
| R2-S4 (decorator guard) | Cross-cutting | Accepted | Reject decorated classes |
| R2-S5 (integration test corpus) | — | Rejected | Numeric threshold over-specifies for a plan doc |
| R2-S6 (dry-run flag) | Cross-cutting | Accepted | `--dry-run-deterministic` |
| R2-S7 (name sanitization) | 2 | Accepted | Non-identifier rejection |
| R3-S1 (file copy Phase 0) | 0 | Accepted | Core of Phase 0 |
| R3-S2 (strategy enum) | 1 | Accepted | `AssemblyStrategy` enum |
| R3-S3 (copy schema fields) | 0 | Accepted | `copy_source_task_id`, `copy_source_file` |
| R3-S4 (post-assembly validation) | 1 | Accepted | No skeleton markers, no duplicate defs |
| R3-S5 (success criteria %) | Cross-cutting | Accepted | 40% Phase 0+1, 60% Phase 0+1+2 |
| R3-S6 (`copy_and_modify` interface) | 0 | Accepted | Inject predecessor as `{reference_implementation}` |
| R3-S7 (dry-run copy detection) | Cross-cutting | Accepted | Combined into `--dry-run-deterministic` |
| R4-S1 (all-or-nothing assembly) | 1 | Accepted | Assemble in memory, splice on full success |
| R4-S2 (render contract) | 2 | Accepted | Body-only vs full def, indentation policy |
| R4-S3 (DFA-origin anchor) | — | Rejected | Requires DFA schema changes outside this plan's scope |
| R4-S4 (skeleton-signature mismatch) | Cross-cutting | Accepted | Reject on mismatch |
| R4-S5 (idempotence tests) | Cross-cutting | Accepted | Two-pass diff assertion |
| R4-S6 (rejection-reason taxonomy) | Cross-cutting | Accepted | `RejectionReason` enum with typed counts |
| R4-S7 (safe literal serialization) | 2 | Accepted | `repr()` for string defaults |
| R5-S1 (template-first short-circuit) | 1 | Accepted | Fast path in `_handle_simple` |
| R5-S2 (report flag) | Cross-cutting | Accepted | `.startd8/reports/simple-decomposer.json` |
| R5-S3 (template coverage map) | Cross-cutting | Accepted | Per-template-type counts |
| R5-S4 (no-regression guard) | 2 | Accepted | Reject if output equals stub |
| R5-S5 (quick-win test pack) | 2 | Accepted | 5 representative SIMPLE cases |
| R5-S6 (cost-savings estimate) | Cross-cutting | Accepted | `llm_calls_avoided`, `usd_saved_estimate` |
| R5-S7 (identifier guard) | 2 | Accepted | Reject whitespace/non-identifier chars |
| R6-S1 (`ast.parse` gate) | 1 | Accepted | Syntax check before write → `RejectionReason.SYNTAX_ERROR` fallback |
| R6-S3 (Pydantic/dataclass template) | 2 | Accepted | Schema → class body |
| R6-S4 (rejection reason in LLM context) | Cross-cutting | Accepted | Inject failure reason into `_handle_simple` prompt |
| R6-S6 (OTel span attribute) | Cross-cutting | Accepted | `assembly.strategy` attribute |
| R6-S7 (path traversal guard) | 0 | Accepted | `Path.resolve()` + `is_relative_to()` normalization |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **Specificity**: 5 suggestions applied (R1-S1, R1-S2, R2-S1, R3-S1, R4-S1)
- **Dependencies**: 4 suggestions applied (R1-S3, R2-S2, R3-S2, R4-S6)
- **Data Contracts**: 6 suggestions applied (R1-S5, R1-S6, R2-S3, R3-S3, R4-S3, R4-S5)
- **Risk Mitigation**: 5 suggestions applied (R1-S4, R2-S4, R3-S4, R4-S2, R4-S4)
- **Testability**: 3 suggestions applied (R2-S5, R3-S5, R3-S6)
- **Observability**: 4 suggestions applied (R1-S6, R2-S6, R3-S7, R4-S7)
- **Feasibility Traceability**: 3 suggestions applied (R1-S7, R2-S7, R3-S8)

### Areas Needing Further Review

(All 7 areas have reached the threshold of 3 accepted suggestions.)

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Specify the exact routing contract for `AssemblyStrategy` | Codex | Implementation maps to Phase 1, Step 2. Requires unit test mapping each strategy to 1 handler. | 2026-03-07 |
| R1-S2 | Define how template-rendered sub-elements populate `SubElement` | Codex | Implementation maps to Phase 1, Step 1. Test verifying `SubElement.content` assembly. | 2026-03-07 |
| R1-S3 | Add dependency: `copy_and_modify` requires prompt templates to accept `{reference_implementation}` | Codex | Implementation at Phase 0, Step 4. Render test required. | 2026-03-07 |
| R1-S4 | Define overwrite policy for file-copy targets | Codex | Implemented at Phase 0, Step 3. Verification involves conflict collision response. | 2026-03-07 |
| R1-S5 | Specify `GenerationResult` fields for file-copy | Codex | Implementation at Phase 0, Step 3 & Phase 1, Step 3. Ensure test coverage assertions for telemetry. | 2026-03-07 |
| R1-S6 | Define a JSON schema for `.startd8/reports/simple-decomposer.json` | Codex | Implementation in Cross-Cutting. Requires schema validation test for report output. | 2026-03-07 |
| R1-S7 | Add "Status" column to traceability table (Accepted vs Candidate) | Codex | Implemented under Traceability Section. Test visually checks for alignment with CRP state. | 2026-03-07 |
| R2-S1 | Map `ast.parse()` SyntaxError to deterministic=False fallback | Antigravity | Phase 1, Step 5: `try: ast.parse(code)` → on SyntaxError, set fallback and invoke `_handle_simple`. | 2026-03-07 |
| R2-S2 | Sequence SHA-256 verify before predecessor artifact cleanup | Antigravity | Phase 0, Step 3: Predecessor file must remain accessible until verification completes. | 2026-03-07 |
| R2-S3 | Specify GenerationResult schema for TRIVIAL aggregated path | Antigravity | Phase 1, Step 1: `llm_calls=0`, `strategy="simple_decompose"`, `content_map` or equivalent. | 2026-03-07 |
| R2-S4 | Define timeout and cleanup for copy_source file read | Antigravity | Phase 0, Step 3: Add read timeout (e.g. 30s) and `finally` release for I/O locks. | 2026-03-07 |
| R2-S5 | Add leaf-only negative test (recursive boundary block) | Antigravity | Phase 1, Step 7: Test with split payload marker in decomposed template → assert recursive boundary exception. | 2026-03-07 |
| R2-S6 | Specify rejection_reasons as `{reason_enum: count_int}` in report JSON | Antigravity | Cross-Cutting: `{"mismatch": 5, "decorator": 3}` format; no string variations. | 2026-03-07 |
| R2-S7 | Specify where R4-S6 rejection reason surfaces in engine flow | Antigravity | Phase 1, Steps 4–5: Return tuple or exception attribute; telemetry hook captures on fallback. | 2026-03-07 |
| R3-S1 | Use FeatureSpec.dependencies (not depends_on) for copy detection | Claude | Phase 0, Step 1: Copy detection reads `feature.dependencies`; require `len(dependencies)==1`. | 2026-03-07 |
| R3-S2 | Add dependency: template_registry must be available to ClassDecomposeStrategy | Claude | Phase 1, Step 1: Engine passes template_registry to strategy or injects at construction. | 2026-03-07 |
| R3-S3 | Specify CopySource dataclass schema (predecessor_id, source_file) | Claude | Phase 0, Step 2: Exact fields in copy_detection.py. | 2026-03-07 |
| R3-S4 | Define ValueError when predecessor not COMPLETED | Claude | Phase 0, Step 3: Clear error message with task id and status. | 2026-03-07 |
| R3-S5 | Add overwrite-policy test (copy_overwrite config, FileExistsError) | Claude | Phase 0, Step 3: Test target-exists + copy_overwrite=False path. | 2026-03-07 |
| R3-S6 | Add template-first short-circuit test (zero Ollama calls) | Claude | Phase 1, Step 3: Mock Ollama, assert call count 0 for TRIVIAL match. | 2026-03-07 |
| R3-S7 | Specify exact OTel counter names for simple_decompose | Claude | Cross-Cutting: micro_prime.simple_decompose_attempted/succeeded/rejected. | 2026-03-07 |
| R3-S8 | Add Phase 1 Step 9 for R3-S4 file-level validation gate | Claude | Post-splice gate: no skeleton markers, no duplicate defs; rollback on failure. | 2026-03-07 |
| R4-S1 | Specify timeout mechanism (`concurrent.futures` with `timeout=30`) | Codex | Phase 0, Step 3: `ThreadPoolExecutor` + `future.result(timeout=30)` + `finally shutdown`. | 2026-03-07 |
| R4-S2 | TOCTOU-safe overwrite using `open(..., "xb")` | Codex | Phase 0, Step 3: Atomic exclusive creation for `copy_overwrite=False`. | 2026-03-07 |
| R4-S3 | Add `schema_version` and `_meta` to `SimpleDecomposerReport` | Codex | Cross-Cutting: `ReportMeta` dataclass with `schema_version`, `sdk_version`, `python_version`. | 2026-03-07 |
| R4-S4 | Tighten path guard with `is_relative_to()` + fix traceability contradiction | Codex | Phase 0, Step 2: `resolved.is_relative_to(root)` replaces `startswith`. Traceability R6-S7 row updated. | 2026-03-07 |
| R4-S5 | Fallback inference for `copy_source_file` from predecessor's `target_files` | Codex | Phase 0, Step 1: Infer when predecessor has exactly one `target_file`; reject on ambiguity. | 2026-03-07 |
| R4-S6 | Prompt-budget guard for `{reference_implementation}` injection | Codex | Phase 0, Step 4: Tiered compression (strip comments → truncate with marker) at 2000-token budget. | 2026-03-07 |
| R4-S7 | Advisory report writing — `try/except OSError` with warning log | Codex | Cross-Cutting: Report I/O failure logs warning, never fails generation run. | 2026-03-07 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R2

- **Reviewer**: Antigravity
- **Date**: 2026-03-07
- **Scope**: Two-Tier Priority Review (Focusing on Data Contracts, Risk Mitigation, Testability, Observability, and Dependencies)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Specificity | medium | Detail the exact AST validation syntax check mapping for R6-S1 gate. | Saying `ast.parse()` on assembled output is good, but doesn't specify how standard AST exceptions (`SyntaxError`) are mapped to the generic `engine.py` fallback path (`_handle_simple`). We need to state explicitly that `try: ast.parse(code)` maps an exception to a `deterministic=False` fallback. | Phase 1, Step 5 | Introduce syntactically invalid literal string stub, assert error is gracefully handled by `_handle_simple`. |
| R2-S2 | Dependencies | high | Explicitly sequence Phase 0 copy verification hash test *before* dependency artifact ingestion is cleaned up. | Phase 0 states `SHA-256 verify` will be checked against the predecessor object. This defines a hidden dependency that predecessor task file artifacts must remain accessible in the workspace during prime execution and cannot be eagerly garbage collected. | Phase 0, Step 3 | Write a unit test dropping the predecessor file post-generation but pre-validation -> assert correct read error bubbling. |
| R2-S3 | Data Contracts | high | Specify the type mapping and field signature for the `PrimeContractorWorkflow.develop_feature()` fast-path `GenerationResult` emission for TRIVIAL elements. | Phase 1 states "all sub-elements deterministic = skip _handle_simple". We must declare exactly how the aggregated `DecompositionPlan` translates to the final `GenerationResult` (e.g., does it use a new `content_map` key? Are `llm_calls` initialized to 0?). | Phase 1, Step 1 | Assert that `GenerationResult` returned from aggregated TRIVIAL element match has `llm_calls=0` and matching schema fields. |
| R2-S4 | Risk Mitigation | medium | Define fallback timeout and cleanup strategy for `copy_source` retrieval network/disk hangs. | Phase 0 says "If predecessor failed or file missing -> fail". What if the read blocks indefinitely due to I/O lock collisions from other parallel `copy` workers? A specific timeout and `finally` release must be declared. | Phase 0, Step 3 | Stub a mock filesystem read to sleep indefinitely -> assert bounded failure and lock release. |
| R2-S5 | Testability | medium | Add negative test scenarios verifying recursion policy blocks sub-element re-submission when disabled. | Phase 1, Step 7 calls for an assertion that sub-elements are not re-fed unless recursion is enabled; we need a defined test case where a complex sub-element maliciously/accidentally requests further splitting, which must be hard-blocked. | Phase 1, Step 7 | Issue a decomposed template that itself contains a split payload marker -> assert the decompose engine blocks recursion with a bounded rejection reason. |
| R2-S6 | Observability | medium | Specify the context attributes injected into the JSON report schema for `rejection_reasons`. | R1-S6 successfully requested a JSON schema for `.startd8/reports/...`. We need to be specific: `rejection_reasons` must be a mapped dictionary of `{reason_enum: count_int}`. Otherwise, string variations will destroy dashboard grouping. | Cross-Cutting Concerns -> Reporting | Emit 5 failures of `mismatch`, 3 of `decorator`, assert report JSON equates exactly `{ "mismatch": 5, "decorator": 3 }`. |
| R2-S7 | Feasibility Traceability | medium | Provide structural implementation references for Traceability R4-S6 (`rejection-reason taxonomy`). | The plan traces R4-S6 to "Cross-cutting -> no_template_match, skeleton_mismatch, etc.", but does not specify *where* in the engine context flow this is appended (e.g., is it an exception subclass, a returned tuple component?). It must specify how it surfaces to the tracker. | Phase 1, Step 4 & 5 | Emit a `skeleton_mismatch` and assert it is captured identically by the telemetry hook on fallback. |

#### Review Round R3

- **Reviewer**: Claude (Implementation Plan Review Protocol)
- **Date**: 2026-03-07
- **Scope**: Codebase compatibility audit, phase boundary contracts, and gap-filling for Dependencies, Risk Mitigation, Testability, Observability, Feasibility Traceability

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Specificity | high | Use `FeatureSpec.dependencies` (not `depends_on`) when referencing the schema. Plan ingestion maps seed `depends_on` to `FeatureSpec.dependencies`. Add explicit note: copy detection reads `feature.dependencies` and requires `len(dependencies) == 1` for unambiguous copy source. | `FeatureSpec` in `contractors/queue.py` has `dependencies: List[str]`, not `depends_on`. Implementers will search for `depends_on` and find nothing. | Phase 0, Step 1 | Assert `detect_copy_task` reads `feature.dependencies` and rejects when `len(dependencies) != 1`. |
| R3-S2 | Dependencies | medium | Add explicit dependency: Phase 1 Step 1 (ClassDecomposeStrategy TRIVIAL check) requires `template_registry` to be passed into `_handle_moderate` or available on the engine. The Moderate Decomposer currently receives no template registry. | The plan says "check if every sub-element passes template_registry.is_trivial()" but `ClassDecomposeStrategy.plan()` has no access to `template_registry`. The engine must pass it or the strategy must receive it at construction. | Phase 1, Step 1 | Unit test: ClassDecomposeStrategy with injected template_registry correctly marks all-TRIVIAL sub-elements as deterministic. |
| R3-S3 | Data Contracts | medium | Specify `CopySource` dataclass fields: `predecessor_id: str`, `source_file: str`. Add optional `workspace_root: str` for path validation. Place in `copy_detection.py` alongside `detect_copy_task`. | Phase 0 Step 2 mentions `CopySource` but does not define its schema. Implementers need exact field names and types. | Phase 0, Step 2 | Assert `CopySource(predecessor_id="x", source_file="y")` serializes and is consumed correctly. |
| R3-S4 | Risk Mitigation | medium | Define behavior when `copy_source_task_id` is set but predecessor task has `status != COMPLETED`. Plan says "fail with clear error" — specify: raise `ValueError` with message `"Copy source task {id} not completed (status={status})"` and do not attempt file read. | Prevents silent or confusing failures when dependency ordering is violated. | Phase 0, Step 3 | Unit test: predecessor PENDING → copy path raises ValueError with expected message. |
| R3-S5 | Testability | high | Add test: Phase 0 Step 3 — when target file already exists, assert overwrite behavior. Plan says "write to target" but R1-S4 added overwrite policy. Specify: overwrite by default; add config `copy_overwrite: bool = True`; when False and target exists, raise `FileExistsError`. | R1-S4 accepted overwrite policy but no test was defined for the conflict case. | Phase 0, Step 3 | Test: target exists + copy_overwrite=False → FileExistsError; copy_overwrite=True → overwrite succeeds. |
| R3-S6 | Testability | medium | Add test: Phase 1 template-first short-circuit (R5-S1) — when `template_registry.is_trivial()` returns True for a SIMPLE element, assert zero Ollama calls and correct splice. Mock Ollama to count invocations. | The short-circuit is a key cost-saving path; without this test, regressions could silently re-enable LLM for TRIVIAL elements. | Phase 1, Step 3 | Mock Ollama; process SIMPLE element that matches template; assert call count 0 and output matches template render. |
| R3-S7 | Observability | medium | Specify OTel counter names exactly: `micro_prime.simple_decompose_attempted`, `micro_prime.simple_decompose_succeeded`, `micro_prime.simple_decompose_rejected`. Use same meter as existing `micro_prime.decomposition_*` counters for consistency. | Plan references "OTel counters" but R1-S6 and Cross-Cutting use different phrasings. Exact names prevent implementer drift. | Cross-Cutting, Observability | Assert meter has counters with these exact string names. |
| R3-S8 | Feasibility Traceability | medium | Add plan step for R3-S4 (post-assembly file-level validation gate). Traceability maps it to "Phase 1" but no Phase 1 step implements it. Add: "Phase 1, Step 9 — After splice, run file-level gate: no `[STARTD8-SKELETON]` markers, no duplicate defs, required functions/classes present. On failure, rollback splice and escalate." | R3-S4 is in feasibility Appendix A but the plan has no concrete step. The Cross-Cutting table mentions it but Phase 1 steps do not. | Phase 1, new Step 9 | Test: inject skeleton marker into assembled file → gate rejects, splice rolled back. |

#### Review Round R4

- **Reviewer**: Codex
- **Date**: 2026-03-07
- **Scope**: Implementation-readiness gaps and nuance improvements (non-duplicate of applied edits)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|---|---|---|---|---|---|---|
| R4-S1 | Specificity | medium | Specify the timeout mechanism for the “30-second read timeout” (e.g., `concurrent.futures` with `timeout=30`, or explicit watchdog + cancel). | “30-second timeout” is aspirational without a concrete mechanism; implementers need a deterministic approach. | Phase 0, Step 3 (file read) | Unit test with a blocking read (mocked) asserts timeout exception within 30s. |
| R4-S2 | Risk Mitigation | medium | Make the overwrite check TOCTOU-safe: use `open(..., "xb")` for `copy_overwrite=False`, or a single `stat()` in `try/except OSError` (avoid `exists()+stat()`). | Prevents race conditions per SDK Leg 11 #68 (Single-Syscall File Check). | Phase 0, Step 3 (overwrite policy) | Concurrency test: target deleted between checks should not crash; correct failure path triggered. |
| R4-S3 | Data Contracts | medium | Add `schema_version` and `_meta` (e.g., `sdk_version`, `python_version`) to `SimpleDecomposerReport`. | Report readers need stability guarantees; schema versioning prevents silent breaks (Leg 10 #39). | Cross-Cutting → Reporting | Schema validation test asserts presence and types of `_meta` fields. |
| R4-S4 | Risk Mitigation | medium | Tighten the path guard: use `Path.resolve(strict=False)` and `path.is_relative_to(root)` (or parent-chain check). Also update the traceability row for R6-S7 to match `Path.resolve()` (not `os.path.abspath`). | Current text is correct in spirit but easy to mis-implement; the traceability table currently contradicts the plan body. | Phase 0, Step 2 and Traceability table | Test: `/workspace2` should not pass; symlinked paths under `/workspace` should pass. |
| R4-S5 | Data Contracts | low | Add fallback inference for `copy_source_file`: if missing and predecessor has exactly one `target_file`, infer it; otherwise reject. | Low-effort boost to deterministic coverage without new heuristics. | Phase 0, Step 1 or Step 3 | Tests: predecessor with one target infers; multiple targets rejects. |
| R4-S6 | Dependencies | medium | Add a prompt-budget guard for `{reference_implementation}` (truncate or tiered compression with marker). | Prevents copy-and-modify from blowing token limits; aligns with prompt budget lessons (Leg 10 #37). | Phase 0, Step 4 | Render test asserts marker + truncated content when long input. |
| R4-S7 | Observability | low | Treat report writing as advisory: wrap report file I/O in `try/except OSError` with a warning log; do not fail generation. | Matches Leg 11 #70 (Advisory Artifact Persistence); protects successful runs from non-critical write errors. | Cross-Cutting → Reporting | Simulate permission error; generation still succeeds and logs warning. |
