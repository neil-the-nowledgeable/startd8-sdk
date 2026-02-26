# FLCM Schema Code Implementation (Phase 2) Requirements & Plan

This document outlines the requirements, design decisions, and implementation details for Phase 2 of the Forward-Looking Code Manifest (FLCM): the Pydantic v2 schema models in `src/startd8/forward_manifest.py` and comprehensive unit tests.

## 1. Goal Description

Phase 2 creates the data-model layer that the rest of the FLCM pipeline depends on. All models are defined in a single new file (`forward_manifest.py`) with no modifications to existing files. The module provides:

- Enum types for contract classification and confidence levels
- Frozen Pydantic v2 models for contracts, element specs, import specs, dependencies, and file specs
- A mutable top-level `ForwardManifest` model with query methods
- A plain `@dataclass(frozen=True)` for violation reporting
- A `compute_binding_text()` helper for prompt-injectable constraint strings

## 2. Files Created

| File | Purpose |
|------|---------|
| `src/startd8/forward_manifest.py` | All Pydantic models, enums, `ContractViolation` dataclass, `compute_binding_text()` helper |
| `tests/unit/test_forward_manifest.py` | ~65 unit tests across 9 test groups |

## 3. Models (in dependency order)

### 3.1 `ContractCategory(str, Enum)`

8 values classifying what an interface contract constrains:

| Value | Meaning |
|-------|---------|
| `function_name` | Named function must exist with this exact name |
| `class_name` | Named class must exist, optionally with a base class |
| `api_endpoint` | HTTP/gRPC endpoint path |
| `config_key` | Environment variable or config key |
| `import_path` | Module import path |
| `formula` | Named constant or formula |
| `render_pattern` | UI rendering pattern |
| `infrastructure` | Infrastructure dependency |

### 3.2 `ContractConfidence(str, Enum)`

3 values indicating constraint strength:

| Value | Prefix | Source |
|-------|--------|--------|
| `explicit` | `[BINDING]` | Human-authored YAML or protobuf |
| `inferred` | `[BINDING]` | Deterministic extraction from plan features |
| `tentative` | `[ADVISORY]` | LLM-suggested during REFINE phase |

### 3.3 `InterfaceContract(BaseModel)` — frozen

A single design-time constraint that code generation must honor.

**Required fields:**
- `contract_id: str` — Unique identifier (e.g., `"C-001"`)
- `category: ContractCategory`
- `confidence: ContractConfidence`
- `description: str` — Human-readable description
- `binding_text: str` — Pre-computed prompt-injectable constraint string

**Category-specific optional fields:**
- `function_name`, `class_name`, `base_class`, `endpoint`
- `request_schema` (dict), `response_schema` (dict)
- `env_var`, `import_path`, `formula`, `constant_value`
- `pattern`, `dependency`

**Scoping fields:**
- `applicable_task_ids: list[str]` — Empty list = project-wide
- `source_reference: Optional[str]`

### 3.4 `ForwardElementSpec(BaseModel)` — frozen

Forward-looking element specification that bridges to `code_manifest.Element`.

**Fields:** `kind` (ElementKind), `name`, `signature` (Optional[Signature]), `bases`, `visibility`, `decorators`, `docstring_hint`, `source_contract_id`

**Validation:** `@model_validator(mode="after")` mirrors `Element._validate_kind_fields`:
- Callable kinds (`function`, `async_function`, `method`, `async_method`, `property`) require `signature`
- Non-class kinds reject `bases`

**Bridge method:** `to_element()` creates a `code_manifest.Element` with:
- Sentinel `Span(0, 0, 0, 0)` (no source location yet)
- `fqn = name` (no module context available)
- All other fields mapped directly

### 3.5 `ForwardImportSpec(BaseModel)` — frozen

- `kind: Literal["import", "from"]` — Matches `ImportEntry.kind` pattern (not regex)
- `module: str`, `names: list[str]`, `alias: Optional[str]`

### 3.6 `ForwardDependencies(BaseModel)` — frozen

- `external: list[str]`, `stdlib: list[str]`
- Intentionally simpler than `Dependencies` — no `internal` or `conditional`

### 3.7 `ForwardFileSpec(BaseModel)` — frozen

- `file: str`, `elements: list[ForwardElementSpec]`, `imports: list[ForwardImportSpec]`
- `dependencies: Optional[ForwardDependencies]`

### 3.8 `ForwardManifest(BaseModel)` — **NOT frozen**

The only mutable model — accumulates contracts from multiple pipeline stages.

**Metadata fields:**
- `schema_version` (default `"1.0.0"`), `pipeline_run_id`, `generated_at`, `source_checksum`

**Content fields:**
- `contracts: list[InterfaceContract]`
- `file_specs: dict[str, ForwardFileSpec]`
- `stages_completed: list[str]`

**Query methods:**
| Method | Returns |
|--------|---------|
| `contracts_for_task(task_id)` | Project-wide + task-specific contracts |
| `binding_constraints_for_task(task_id)` | `list[str]` of binding_text values |
| `file_specs_for_task(task_id, target_files)` | Filtered file specs by path |
| `contract_count_by_category()` | `Counter` grouped by category |

### 3.9 `ContractViolation` — `@dataclass(frozen=True)`

Plain dataclass (NOT Pydantic) for violation reporting:
- `contract_id: str`, `violation_type: str`, `expected: str`
- `actual: Optional[str]`, `file_path: Optional[str]`, `severity: str` (default `"error"`)

### 3.10 `compute_binding_text(contract)` — module-level function

Computes a compact binding-text string from an `InterfaceContract`:
- Prefix: `[BINDING]` for `explicit`/`inferred`, `[ADVISORY]` for `tentative`
- Category dispatch via if/elif: appends relevant category-specific fields
- Parts joined with ` | ` separator
- Graceful degradation: missing category-specific fields → prefix + description only

## 4. Key Design Decisions

1. **`ForwardImportSpec.kind` uses `Literal["import", "from"]`** — matches existing `ImportEntry.kind`, gives static type checking instead of regex
2. **`ForwardElementSpec` duplicates Element's model_validator** — prevents confusing errors where `to_element()` fails because the source spec was silently invalid
3. **`ForwardManifest` is the only non-frozen model** — it accumulates contracts from multiple pipeline stages
4. **`compute_binding_text` uses ` | ` join** — compact single-line format suitable for prompt injection
5. **No circular imports** — `forward_manifest.py` imports from `code_manifest.py`, never the reverse
6. **`ContractViolation` is a dataclass, not Pydantic** — lightweight, no serialization overhead needed for violation tracking

## 5. Conventions Followed

- `from __future__ import annotations` (matches `code_manifest.py`)
- `get_logger(__name__)` for logging (not `logging.getLogger()`)
- `ConfigDict(frozen=True)` on all models except `ForwardManifest`
- `Field(default_factory=list)` for mutable defaults
- `__all__` exports all 10 public names

## 6. Test Coverage

65 unit tests across 9 groups:

| Group | Count | Key coverage |
|-------|-------|--------------|
| Enum validation | 5 | 8 category values, 3 confidence values, str serialization |
| InterfaceContract | 5 | Minimal construction, category-specific fields, frozen, defaults |
| ForwardElementSpec | 10 | Kind/signature invariant, to_element bridge, Element validator pass-through |
| ForwardImportSpec + ForwardDependencies | 8 | Literal kind validation, defaults, frozen |
| ForwardFileSpec | 3 | Construction, optional dependencies, frozen |
| ForwardManifest queries | 9 | contracts_for_task, binding_constraints, file_specs, category counts, mutability |
| compute_binding_text | 13 | Each category, prefix by confidence, description-only fallback |
| JSON round-trip | 7 | model_dump → model_validate for all models, model_dump_json round-trip |
| ContractViolation | 5 | Construction, defaults, frozen, equality |

## 7. Verification Criteria

1. `pytest tests/unit/test_forward_manifest.py -v` — all 65 tests pass
2. `ForwardElementSpec.to_element()` produces valid `Element` (Element's own validator doesn't raise)
3. `ForwardManifest` query methods return correct results for project-wide vs task-specific contracts
4. JSON round-trip: `model_dump()` → `model_validate()` preserves all fields including nested models
5. `ruff check src/startd8/forward_manifest.py` — no lint errors
