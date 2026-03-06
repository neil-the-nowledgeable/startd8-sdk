# Moderate Decomposer — Code Review Report

I have conducted a thorough code review of the Moderate Decomposer implementation (commit `1ba622c`) against the requirements in `REQ-MP-9xx_MODERATE_DECOMPOSER.md` and the implementation plan.

Here are the bugs and deviations proactively discovered:

### 1. Missing `_structural_verify` on Assembled Output (Critical)

**File**: `micro_prime/engine.py` (in `_handle_moderate`)

- **Issue**: After successfully assembling the decomposed sub-elements, `_handle_moderate` immediately returns `success=True` with the `assembled` code. It completely skips calling `_structural_verify(assembled, element)`.
- **Requirement Violated**: `REQ-MP-903` AC11 states: *"Assembled output MUST be passed through `_structural_verify(assembled_code, original_element)` before returning `success=True`. Assembly validation failure escalates with `EscalationReason.DECOMPOSITION_FAILED`."*
- **Note**: Support for verifying `CLASS` elements was correctly added to `_structural_verify` (R1-S3 feature), but the method is never actually invoked in the moderate generation path.

### 2. `__init__` Method Handled Incorrectly in Class Decomposition

**File**: `micro_prime/decomposer.py` (in `ClassDecomposeStrategy.plan`)

- **Issue**: If `__init__` is present in the `file_spec` elements, the strategy intentionally skips adding it to the decomposition plan, assuming the engine's normal loop will handle it.
- **Requirement Violated**: `REQ-MP-901` explicitly requires that if the class has an `__init__` in the manifest, it should be generated as a SIMPLE sub-element via the decomposer and assembled directly into the class shell.
- **Side Effect**: `MODERATE_DECOMPOSER_IMPLEMENTATION_PLAN.md` claims that `test_decompose_class_with_init_produces_two_subs` is implemented. This test does not exist. Instead, `test_init_in_manifest_not_added_to_plan` was written, cementing this deviation from the design document.

### 3. Inefficient `max_sub_elements` Guard

**File**: `micro_prime/decomposer.py` (in `ModerateDecomposer.decompose`)

- **Issue**: The `max_sub_elements` check is performed *after* the `DecompositionStrategy` has done the work to build the full plan.
- **Requirement Violated**: `REQ-MP-908` AC3 states: *"Strategies check `max_sub_elements` before emitting a plan to avoid wasted work."*

### 4. Unrelated Regressions in `micro_prime` Test Suite

While running `pytest tests/unit/micro_prime/`, I found **22 failing tests** masking the status of the pipeline. These appear to be recent regressions in related Micro Prime modules that were not caught:

- **Repair Pipeline**: `run_repair_pipeline` now returns a `RepairResult` object, but 6 tests in `test_repair.py` still attempt to unpack it as a tuple (`repaired, steps = ...`), causing `TypeError`.
- **Template Registry**: `templates.match()` now returns a `TemplateMatch` object, but 12 tests in `test_templates.py` assert against it as if it were a plain string, causing `AssertionError` and `AttributeError` (`'TemplateMatch' object has no attribute 'splitlines'`).
- **Classifier**: `test_many_external_imports_escalates` is bubbling up a failure.
- **Prompt Builder**: 2 async prompt tests are failing.

### Next Steps

Would you like me to go ahead and start developing patches for these issues? I can begin by fixing the `_structural_verify` bug in `engine.py` and realigning the `ClassDecomposeStrategy` with `REQ-MP-901`.
