# Phase 5 Requirements: Forward Manifest Validator & CLI

This document specifies the requirements for the final phase of the Forward-Looking Code Manifest (FLCM) implementation: the post-generation validation engine (`src/startd8/forward_manifest_validator.py`) and its associated CLI commands.

## 1. Goal Description

Phase 5 introduces a structural comparison engine that validates the generated codebase against the prescriptive contracts defined in the `ForwardManifest`. It must detect when the artisan generated interfaces, names, schemas, or dependencies that contradict the specified bindings. The phase also includes exposing this capability via a new CLI command to enable programmatic verification and integration into the REVIEW phase.

## 2. Core Validation Responsibilities

### 2.1 The Validation Engine (`forward_manifest_validator.py`)

The engine must iterate through every `InterfaceContract` and `ForwardFileSpec` to assert compliance against the actual artifacts (e.g., Code Manifests or raw source code files) produced during the IMPLEMENT phase.

* **API/Function Name Conventions (`category="function_name"`)**:
  * Query the existing `ManifestRegistry` to ensure the required function FQN exists.
  * Compare the `Signature` elements (if provided) structually.
* **Class Names & Hierarchies (`category="class_name"`)**:
  * Lookup the required class in the generated `Element` tree.
  * Assert that the required `base_class` or subclass inheritance was properly authored.
* **API Endpoints (`category="api_endpoint"`)**:
  * Since HTTP route decorators are framework-specific, the engine must employ a regex-based or AST-based pattern matching strategy (similar to a grep heuristic) on the generated code lines to confirm the required endpoint path and method (e.g., `@app.route('/recommendations', methods=['POST'])`) were authored.
* **Import Requirements (`category="import_path"`)**:
  * Cross-reference `ForwardImportSpec` dependencies against the actual `FileManifest.imports` data structure.
* **Formulas & Render Patterns (`category="formula" / "render_pattern"`)**:
  * These are highly contextual and often semantically tricky to validate structurally.
  * The engine should register these contracts but inherently treat violations (if detection fails) as `severity="warning"` rather than `severity="error"`, or flag them for human review by default.
* **Prescribed File Elements (`ForwardFileSpec`)**:
  * Assert the physical existence of the file.
  * Verify that the internal element inventory matches the expectation using the `ForwardElementSpec.to_element()` bridge mapped against the actual `ManifestRegistry`.

### 2.2 Violation Model (`ContractViolation`)

When a contradiction is detected, the engine must emit a standardized anomaly report.

```python
@dataclass(frozen=True)
class ContractViolation:
    contract_id: str
    violation_type: str  # e.g., "missing_function", "wrong_signature", "missing_import"
    expected: str
    actual: Optional[str] = None
    file_path: Optional[str] = None
    severity: str = "error" # "error" vs "warning"
```

* **Severity Rules:**
  * Structural gaps (Missing files, mismatched signatures, forbidden dependencies) yield `error`.
  * Advisory gaps (Failing to match a fuzzy `render_pattern` or `formula`) yield `warning`.

## 3. Pipeline Integration (REVIEW Phase)

* **Requirement:** The `ReviewPhaseHandler` must trigger the validation logic automatically.
* **Implementation:**
  * Load `context["forward_manifest"]` and `context.get("manifest_registry")`.
  * Invoke `validate_forward_manifest(...)`.
  * If `ContractViolation` instances are returned, they must be formatted and appended to the `review_output.contract_violations` summary.
  * Any `severity="error"` violation must cause the quality gate to fail, redirecting the Artisan to fix the defect or returning an actionable error trace.

## 4. CLI Architecture

* **Requirement:** Provide a terminal interface so users (and automated scripts) can validate a codebase locally without orchestrating the entire StartD8 pipeline.
* **Implementation:**
  * Extend `startd8 manifest` capability.
  * Command: `startd8 manifest validate-forward <manifest-path> --source-path <project-path>`
  * Behavior: Parse the .json manifest, invoke the validator against the target codebase elements, and output a tabulated summary reporting: Error Severity, Contract ID, Expected vs. Actual, and File Path.
  * Exit Code: Return a non-zero exit code if *any* `error` severity violations are found.

## 5. Proposed Changes

### `src/startd8/forward_manifest_validator.py`

* [NEW] `def validate_forward_manifest(manifest: ForwardManifest, registry: ManifestRegistry) -> List[ContractViolation]`
* [NEW] Internal ruleset validators (e.g., `_validate_class_hierarchy()`, `_validate_imports()`).

### `src/startd8/cli/manifest_cli.py` (or equivalent CLI routing)

* [MODIFY] Add the new `validate-forward` command group and sub-parser wiring.

### `src/startd8/phase_handlers/review_handler.py`

* [MODIFY] Wire up the engine in the quality gate logic to populate `review_output`.

## 6. Verification Plan

1. **Engine Unit Tests:** Mock `ManifestRegistry` scenarios holding deliberately invalid FQNs, missing imports, and conflicting base classes. Assert that `validate_forward_manifest` issues exactly the expected number and type of `ContractViolation` instances.
2. **CLI Return Code Test:** Verify the CLI command returns an exit code `1` when simulated errors exist and `0` when simulated warnings (or no violations) exist.
3. **REVIEW Gate Integration Test:** Execute a mocked pipeline where the Artisan deliberately generates code violating a `function_name` contract, and assert the Review Phase traps generation and flags the failure accurately.
