# Forward Manifest Extractor (Phase 3) Requirements & Implementation Plan

This document outlines the specific requirements, architecture, and implementation steps for Phase 3 of the Forward-Looking Code Manifest (FLCM) integration: `src/startd8/forward_manifest_extractor.py`.

## 1. Goal Description

The extractor's purpose is to gather interface contracts deterministically from the `ParsedFeature` definitions and `.proto` files, as well as handle LLM-discovered tentative contracts. It merges these sources using strict precedence rules to form the final `ForwardManifest` before code generation begins.

## 2. Architecture & Data Flow

The extractor module will expose a main orchestrator function: `extract_forward_contracts()`. Internally, it will use several targeted sub-extractors for different confidence tiers:

1. **`HumanYamlExtractor` (`explicit`)**: Parses the `shared_contracts:` block from plan YAML outputs.
2. **`ProtoExtractor` (`explicit`)**: Parses protobuf definitions into `class_name` and `api_endpoint` contracts.
3. **`DeterministicExtractor` (`inferred`)**: Analyzes the properties of `ParsedFeature` instances.
4. **`TentativeTracker` (`tentative`)**: Consolidates LLM-suggested contracts discovered during the plan-ingestion `REFINE` phase (i.e., `PlanIngestionWorkflow.refine`, not the artisan REVIEW phase). Tentative contracts are gathered in a single pass before code generation, not incrementally during artisan execution.
5. **`ManifestMerger`**: Resolves conflicts and deduplicates contracts based on confidence levels.

## 3. Detailed Requirements by Component

### 3.1 `DeterministicExtractor` Rules

Extracts contracts automatically from the current plan state without calling the LLM.

* **API Signatures (`ParsedFeature.api_signatures`)**:
  * *Input:* A string like `update_user(user_id: str, payload: dict) -> User`
  * *Output:* `InterfaceContract(category="function_name", function_name="update_user", ...)` AND a `ForwardElementSpec` representing the parsed signature.
  * *Rule:* Requires a basic regex/AST syntax parser to safely break down the signature string into `Param` and `return_annotation` fields.
  * *Contract construction:* Extractors **must** call `compute_binding_text(contract)` to populate the required `binding_text` field before constructing the `InterfaceContract`. Omitting `binding_text` will raise a Pydantic validation error.
  * *File spec routing:* The resulting `ForwardElementSpec` must be routed into the `ForwardFileSpec` for the task's first `target_file` (see Section 3.5).
* **Target Files Overlap (`ParsedFeature.target_files`)**:
  * *Input:* `[PI-001.target_files, PI-002.target_files]`
  * *Rule:* If multiple features write to the identical file path, an `inferred` contract is created asserting that file is a shared module. If standard utility patterns are detected (e.g., `logger.py`), a `function_name` or `class_name` contract is instantiated for those conventional exports based on the file name.
* **Protocols (`ParsedFeature.protocol`)**:
  * *Input:* `gRPC`, `HTTP`, `AMQP`
  * *Rule:* Maps directly to `category="infrastructure"` contracts (e.g., enforcing an HTTP framework pattern if "HTTP" is defined).
* **Runtime Dependencies (`ParsedFeature.runtime_dependencies`)**:
  * *Input:* List of package names (e.g., `["langchain", "psycopg2"]`)
  * *Rule:* Maps to `category="import_path"`, preventing the LLM from inventing alternative library choices.

### 3.2 `HumanYamlExtractor` Rules

Parses the `shared_contracts:` block from the plan-ingestion YAML output (the context seed file produced by `PlanIngestionWorkflow`). This is the highest-confidence source.

* *Input:* A YAML block embedded in the context seed or a standalone file:

```yaml
shared_contracts:
  - contract_id: "flcm-fn-render-money"
    category: function_name
    function_name: render_money
    description: "All services must use render_money(units, nanos) for currency formatting"
    applicable_task_ids: ["PI-003", "PI-005"]
  - contract_id: "flcm-ep-post-root"
    category: api_endpoint
    endpoint: "POST /"
    request_schema: { "message": "string", "image": "bytes" }
    description: "Recommendation service accepts POST / with message+image body"
```

* *Rule:* Each entry maps directly to `InterfaceContract` fields. The extractor validates required fields (`contract_id`, `category`, `description`), sets `confidence=explicit`, and calls `compute_binding_text()` to populate `binding_text`.
* *Output:* `explicit` contracts. Missing optional fields are left as `None`.
* *Error handling:* Malformed entries are logged and skipped (Mottainai pattern); the extractor returns all valid contracts from the block.

### 3.3 `ProtoExtractor` Rules (Optional capability)

* *Input:* A directory containing `.proto` files.
* *Rule:* Utilizes a regex-based or lightweight parser (to avoid heavy third-party AST dependencies if possible) to enumerate `service` and `message` definitions.
* *Output:* `explicit` contracts binding RPC handlers and data models.

### 3.4 `ManifestMerger` (Precedence Engine)

When multiple extractors produce contracts for the same namespace, conflicts must be resolved:

* **Identity:** Contracts are considered identical if they have the same `contract_id`.
* **Contract ID Generation:** All extractors must use deterministic IDs with the format `flcm-{category_abbrev}-{name_or_hash}` where `category_abbrev` is a short form of the category (e.g., `fn` for `function_name`, `cls` for `class_name`, `ep` for `api_endpoint`, `cfg` for `config_key`, `imp` for `import_path`, `fml` for `formula`, `pat` for `render_pattern`, `inf` for `infrastructure`). This shared namespace enables cross-extractor deduplication. Example: `flcm-fn-update_user`, `flcm-ep-post-root`, `flcm-imp-langchain`.
* **Precedence Hierarchy:**
    1. `explicit` (Human authored YAML) — `source_reference: "human-yaml"`
    2. `explicit` (Proto extracted) — `source_reference: "proto"`
    3. `inferred` (Deterministic pipeline extraction) — `source_reference: "deterministic"`
    4. `tentative` (LLM discovered) — `source_reference: "llm-refine"`
* **Conflict Resolution:**
  * If a newer contract has *higher* precedence than the existing one, it **overwrites** the existing one.
  * If a newer contract has *equal* precedence but conflicting values, the conflict is **logged as a warning** and the first-seen/human-authored contract is retained.
  * If a newer contract has *lower* precedence, it is **discarded**.

### 3.5 `ForwardFileSpec` Assembly

After all extractors have run and `ManifestMerger` has produced the final contract list, the extractor must assemble `ForwardFileSpec` entries for each target file referenced by the contracts:

* **Element routing:** Each `ForwardElementSpec` produced by `DeterministicExtractor` (from `api_signatures` parsing) or `ProtoExtractor` is routed into the `ForwardFileSpec` for its owning file. The owning file is determined by the first `target_file` of the `ParsedFeature` that sourced the contract.
* **Import/dependency population:** `ForwardImportSpec` and `ForwardDependencies` population is **out of scope** for Phase 3. These models exist in the schema for future use (Phase 4 threading may populate them from `runtime_dependencies` data). Phase 3 leaves `imports` and `dependencies` at their defaults (empty list / `None`).
  * **Import-completeness invariant (added 2026-06-04, run-040 evidence).** Because Phase 3 deliberately leaves `imports` empty, the *rendered skeleton* (the Mottainai pre-assembly artifact the Sapper survey type-checks) can reference names — typing generics, framework symbols — with no import, e.g. `job_export_router = APIRouter()` with empty `imports`, which fails type-check **and** breaks FastAPI/SQLModel `get_type_hints` at runtime. **Invariant:** every name an element references (in signature annotations or `value_repr`) MUST be importable in the rendered skeleton. **Responsibility:** since the plan-declared element carries no module info, the *emitter* (`DeterministicFileAssembler.render_file`) is responsible for completing the import set by resolving referenced names against (a) `typing` (a fixed export set) and (b) the **generated-app framework stack** (FastAPI / SQLModel / Jinja2 / Pydantic — the exact stack `backend_codegen` emits and the convention authority governs). Names it cannot resolve are left unimported **by design** — the Sapper survey then surfaces them as `import_availability` friction rather than masking a genuine plan gap. *(First surfaced by Sapper run-040; the typing half also covers OQ-8.)*
* **File spec keying:** `ForwardFileSpec` entries are keyed by relative file path in the `ForwardManifest.file_specs` dict, matching the path format used in `ParsedFeature.target_files`.

### 3.6 Error Handling (Mottainai Pattern)

* Extraction is a value-add, not a blocking requirement.
* If *any* sub-extractor fails (e.g., unparseable signature, missing proto directory), the error must be caught, logged, and the extractor must gracefully degrade by returning an empty list of contracts for that specific rule without crashing the pipeline.

### 3.7 `binding_text` Construction Requirement

All extractors **must** call `compute_binding_text(contract)` from `forward_manifest.py` when constructing `InterfaceContract` instances. The `binding_text` field is required by Pydantic validation. The recommended pattern is:

```python
from startd8.forward_manifest import (
    InterfaceContract, ContractCategory, ContractConfidence, compute_binding_text,
)

# Build a partial contract (without binding_text) to compute the text
partial = InterfaceContract.model_construct(
    contract_id="flcm-fn-update_user",
    category=ContractCategory.FUNCTION_NAME,
    confidence=ContractConfidence.INFERRED,
    function_name="update_user",
    description="Must use update_user as the function name",
    binding_text="",  # placeholder
)
binding = compute_binding_text(partial)

# Now construct the validated contract
contract = InterfaceContract(
    **{**partial.model_dump(), "binding_text": binding}
)
```

Alternatively, extractors may compute the binding text string directly and pass it to the constructor.

## 4. Proposed Changes

### `src/startd8/forward_manifest_extractor.py`

* [NEW] `forward_manifest_extractor.py`
  * `def extract_forward_contracts(...) -> ForwardManifest`
  * `class DeterministicExtractor`
  * `class HumanYamlExtractor`
  * `class ProtoExtractor`
  * `class ManifestMerger`
  * `def _parse_python_signature(sig_str: str) -> Signature`

### `src/startd8/contractors/artisan_phases/design_prompts/seed_mapping.py`

* [MODIFY] `seed_mapping.py`
  * Import and connect `extract_forward_contracts` logic so it propagates to the prompt templates.
  * Fix `logging.getLogger(__name__)` → `get_logger(__name__)` per OTel log bridge convention.

## 5. Verification Plan

### Automated Tests (`tests/unit/test_forward_manifest_extractor.py`)

#### Signature Parsing (3 tests)
1. **`test_parse_python_signature_basic`**: `foo(bar: int) -> str` properly converts to `Signature` with correct `Param` and `return_annotation`.
2. **`test_parse_python_signature_no_return`**: `foo(x: int, y: str)` produces `Signature` with `return_annotation=None`.
3. **`test_parse_python_signature_malformed`**: Unparseable strings return `None` (or empty) without raising.

#### DeterministicExtractor (4 tests)
4. **`test_deterministic_api_signatures`**: `ParsedFeature` with `api_signatures` produces both `InterfaceContract` and `ForwardElementSpec` routed to the correct `ForwardFileSpec`.
5. **`test_deterministic_runtime_dependencies`**: `runtime_dependencies=["langchain"]` produces `import_path` contract.
6. **`test_deterministic_protocol`**: `protocol="gRPC"` produces `infrastructure` contract.
7. **`test_deterministic_shared_files`**: Overlapping `target_files` across features produce shared-module contracts.

#### HumanYamlExtractor (2 tests)
8. **`test_human_yaml_valid_block`**: Well-formed `shared_contracts:` YAML produces `explicit` contracts with correct fields and `binding_text`.
9. **`test_human_yaml_malformed_entry`**: Block with one valid and one malformed entry produces 1 contract (malformed skipped with log warning).

#### ProtoExtractor (2 tests)
10. **`test_proto_service_extraction`**: `.proto` file with `service` and `message` definitions produces `class_name` and `api_endpoint` contracts.
11. **`test_proto_missing_directory`**: Missing proto directory returns empty list (Mottainai degradation).

#### ManifestMerger (3 tests)
12. **`test_merger_higher_precedence_overwrites`**: `explicit` contract overwrites `inferred` contract with same `contract_id`.
13. **`test_merger_equal_precedence_retains_first`**: Two `inferred` contracts with same ID — first is retained, conflict logged.
14. **`test_merger_lower_precedence_discarded`**: `tentative` contract cannot override `inferred` contract.

#### End-to-End (2 tests)
15. **`test_extract_forward_contracts_mixed_sources`**: Features + YAML + proto combined into a single `ForwardManifest` with correct contract count and category distribution.
16. **`test_extract_forward_contracts_empty_input`**: No features, no YAML, no proto → empty `ForwardManifest` (no crash).

### Manual Verification

* Run the extraction logic against the existing online-boutique mock data (RUN3 context) and manually verify that it emits the `[BINDING]` constraints that solve the 7 major generation defects highlighted in `04_FORWARD_MANIFEST.md`.
