last
# Forward-Looking Code Manifest (FLCM)

## Status: Completed / Built

**Document**: 04 in the design document series
**Location**: `docs/design/forward-manifest/`
**Depends on**: 01 Context Bridge (consumes `project_structure` + `capability_map`), 03 Issue-to-Localization Mapper (produces forward equivalent of ManifestRegistry)
**Schema version**: 1.0.0

---

## 1. Problem Statement

### 1.1 Evidence: RUN3 Integration Failures

RUN3 of the cap-dev-pipe (online-boutique-demo, Python run) produced **7/7 critical integration failures** — every service that required cross-task interface knowledge generated defective code. Each defect was caused by information that was fully deterministic at plan time but never specified in the generation context.

| Defect ID | Service(s) | Description | Root Cause | Severity |
|-----------|-----------|-------------|------------|----------|
| DEV-R3-001 | PI-003, PI-005 | Template `order.xxx` refs vs flat dict render context — `UndefinedError` at runtime | PI-003 passes `render(template_context)` with flat dict; PI-005 expects `{{ order.order_id }}` nested variable | CRITICAL |
| DEV-R3-002 | PI-005 | Money formatting uses Jinja2 `slice` filter (sequence chunker) instead of integer division | Template macro uses `| slice(0, 2)` but `slice` splits sequences into chunks; reference uses `nanos // 10000000` with `"%02d"` | HIGH |
| DEV-R3-003 | PI-003, PI-006 | Missing OTLPSpanExporter — services invisible in distributed traces | Both use `ConsoleSpanExporter` instead of `OTLPSpanExporter`; reference uses `OTLPSpanExporter` with `COLLECTOR_SERVICE_ADDR` env var | MODERATE |
| DEV-R3-004 | PI-003 | Missing `select_autoescape` in Jinja2 Environment — XSS defense-in-depth gap | Generated omits `select_autoescape(['html', 'xml'])` | MODERATE |
| DEV-R3-005 | PI-003 | Template directory check exits in dummy mode | `sys.exit(1)` if `templates/` missing, even when templates aren't used — blocks testing before PI-005 is deployed | LOW |
| DEV-R3-006 | PI-008 | Endpoint, request, and response contract mismatch with frontend Go service | Reference: `POST /` with `{message, image}`; Generated: `POST /recommendations` with `{query}` | CRITICAL |
| DEV-R3-007 | PI-008 | Library and pipeline divergence from reference | Reference uses LangChain ecosystem (`langchain_google_genai`); Generated uses raw `psycopg2` + `google.generativeai` | CRITICAL |

**Source**: `RUN3_CODE_QUALITY_EVALUATION.md` (online-boutique-demo `.cap-dev-pipe/design/`)

### 1.2 Root Cause Classification

Every defect falls into one of two categories:

1. **Shared interface contracts** (DEV-R3-001, DEV-R3-003, DEV-R3-006): Multiple tasks must use the same function names, API schemas, or configuration patterns, but nothing in the generation context prescribes them.

2. **Cross-cutting infrastructure patterns** (DEV-R3-002, DEV-R3-004, DEV-R3-005, DEV-R3-007): A single correct implementation pattern exists (library choice, formula, security pattern) but the artisan invents alternatives because the correct one is never specified.

### 1.3 Current Gap

The plan decomposes a system into tasks (`ParsedFeature` entries with `feature_id`, `target_files`, `dependencies`) but does not specify the **contracts binding them**. Each task is generated in isolation with no knowledge of what names, schemas, or patterns sibling tasks will use.

REQ-REGEN-004a (from `REGENERATION_REQUIREMENTS.md`) partially addresses this with requirements authoring standards — cross-cutting tables, complete call signatures, concrete value enumeration — but these remain prose in a requirements document. The FLCM makes them machine-readable and pipeline-consumable.

### 1.4 Corroborating Evidence: Ambiguity Audit

The `PYTHON_REQUIREMENTS_AMBIGUITY_AUDIT.md` independently identified 13 ambiguities in the same run, 5 of which directly caused defects (AMB-002 → DEV-R2-002/004, AMB-006 → DEV-R2-001, AMB-007 → DEV-R2-005, AMB-008 → DEV-R2-003). The most damaging (AMB-002: scattered AlloyDB parameters) was never flagged by any reviewer. The FLCM's structured contract format prevents this class of error by requiring complete signatures in a single machine-readable entry.

---

## 2. Goal

A forward-looking specification layer that:

1. **Prescribes** interface contracts (function names, API schemas, env vars, formulas, library choices) BEFORE code generation begins
2. **Threads** these contracts through the Artisan pipeline as `[BINDING]` constraints injected into generation prompts
3. **Validates** generated code against the prescribed contracts post-generation, reporting violations in the REVIEW phase
4. **Progressively refines** through pipeline stages — human-authored contracts merge with deterministically-extracted and LLM-discovered contracts into a single `ForwardManifest`

---

## 3. Relationship to Existing Systems

### 3.1 Three-Layer Forward-Looking Specification Stack

```
Layer 3: Forward-Looking Code Manifest (NEW — this document)
   ├── InterfaceContract: function names, API schemas, env vars, formulas
   ├── ForwardElementSpec: prescribed classes/functions with signatures
   └── ForwardFileSpec: per-file element inventories

Layer 2: Code Manifest (EXISTING — backward-looking, to be mirrored forward)
   ├── FileManifest: Element trees with FQNs, signatures, call graphs
   ├── ManifestRegistry: query layer (fqn_exists, blast_radius, dead_candidates)
   └── ManifestDiff: structural comparison (removed_public, changed_signatures)

Layer 1: Scaffold Manifest (EXISTING — file-level tracking)
   ├── ProjectScaffoldManifest: file_hashes dict (path → SHA-256)
   ├── Safe overwrite: 3-way hash comparison (original vs current vs new)
   └── Persisted to .startd8-scaffold.json

Layer 0: Proto / IDL Contracts (EXISTING — interface-level, language-agnostic)
   ├── demo.proto: 9 services, 15+ RPCs, 20+ message types
   └── health.proto: standard gRPC health check protocol
```

**Key insight**: Proto files are already a forward-looking manifest for gRPC interfaces. The FLCM extends this concept to everything proto doesn't cover — function naming, internal APIs, config patterns, template contracts, infrastructure choices.

### 3.2 Integration Points with Existing Code

| Existing Module | How FLCM Integrates |
|----------------|---------------------|
| `code_manifest.py` (`Element`, `Signature`, `Param`, `ElementKind`, `Visibility`) | `ForwardElementSpec` reuses these types with relaxed validation (no `Span` required) |
| `manifest_registry.py` (`ManifestRegistry`, `ManifestDiff`) | Post-generation validation compares `ForwardManifest` against actual `ManifestRegistry` |
| `plan_ingestion_models.py` (`ArtisanContextSeed`, `ParsedFeature`) | New `forward_manifest` field on `ArtisanContextSeed`; extraction from `ParsedFeature` fields |
| `design_prompts/modules.py` (`PromptFragment` pattern) | New `ContractModule` follows `IdentityModule` pattern |
| `design_prompts/seed_mapping.py` (extractor functions) | New `extract_forward_contracts()` extractor |
| `context_resolution.py` (`PipelineContextStrategy`) | New section after IMP-P5 for contract injection in IMPLEMENT prompts |
| `gate_contracts.py` (`QualitySpec`, `EvaluationSpec`) | Optional `forward_manifest` field at PLAN exit, DESIGN/IMPLEMENT entry |

---

## 4. Schema Design

### 4.1 InterfaceContract

The core prescriptive primitive. Unlike `Element` (which describes what EXISTS), `InterfaceContract` describes what MUST EXIST and what names/shapes MUST be used.

```python
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional


class ContractCategory(str, Enum):
    """Categories of interface contracts, derived from RUN3 defect analysis."""
    FUNCTION_NAME = "function_name"      # Logger API naming, utility function signatures
    CLASS_NAME = "class_name"            # Formatter classes, model classes, stub classes
    API_ENDPOINT = "api_endpoint"        # HTTP routes + request/response schemas
    CONFIG_KEY = "config_key"            # Environment variables, config field names
    IMPORT_PATH = "import_path"          # Required library imports (prevents DEV-R3-007)
    FORMULA = "formula"                  # Computation patterns (money formatting, DEV-R3-002)
    RENDER_PATTERN = "render_pattern"    # Template/serialization patterns (DEV-R3-001)
    INFRASTRUCTURE = "infrastructure"    # Cross-cutting: OTel, health check, security


class ContractConfidence(str, Enum):
    """Confidence level determining binding vs advisory rendering."""
    EXPLICIT = "explicit"    # From proto files, reference code, or stated requirements
    INFERRED = "inferred"    # From cross-task analysis (shared target_files, dep graph)
    TENTATIVE = "tentative"  # LLM-suggested during plan ingestion REFINE phase


class InterfaceContract(BaseModel):
    """A prescriptive interface contract binding one or more tasks."""
    model_config = {"frozen": True}

    contract_id: str = Field(
        ..., description="Unique identifier (e.g., 'logger-convention', 'money-formatting')"
    )
    category: ContractCategory
    confidence: ContractConfidence
    description: str = Field(
        ..., description="Human-readable description of what this contract prescribes"
    )

    # Category-specific fields (all optional — populated based on category)
    function_name: Optional[str] = None
    class_name: Optional[str] = None
    base_class: Optional[str] = None
    endpoint: Optional[str] = None
    request_schema: Optional[dict] = None
    response_schema: Optional[dict] = None
    env_var: Optional[str] = None
    import_path: Optional[str] = None
    formula: Optional[str] = None
    constant_value: Optional[str] = None
    pattern: Optional[str] = None
    dependency: Optional[str] = None

    # Scoping
    applicable_task_ids: list[str] = Field(
        default_factory=list,
        description="Task IDs this contract applies to. Empty = project-wide."
    )
    source_reference: Optional[str] = Field(
        None, description="Where this contract was derived from (proto file, reference code, etc.)"
    )

    # Binding text — precomputed constraint string for prompt injection
    binding_text: str = Field(
        ..., description="[BINDING] or [ADVISORY] constraint string for prompt injection"
    )
```

**Rendering rule**: `EXPLICIT` and `INFERRED` contracts render as `[BINDING]`. `TENTATIVE` contracts render as `[ADVISORY]`. This distinction flows through to `ConstraintsModule` and `ContractModule` rendering.

### 4.2 ForwardElementSpec

A partial `Element` (from `code_manifest.py`) with relaxed validation. Reuses `ElementKind`, `Visibility`, `Signature`, `Param` from existing models. No `Span` required (no source location for unwritten code).

```python
from startd8.utils.code_manifest import (
    ElementKind, Visibility, Signature
)


class ForwardElementSpec(BaseModel):
    """A prescribed code element that must exist after generation."""
    model_config = {"frozen": True}

    kind: ElementKind
    name: str
    signature: Optional[Signature] = None  # For callables
    bases: list[str] = Field(default_factory=list)  # For classes
    visibility: Visibility = Visibility.PUBLIC
    decorators: list[str] = Field(default_factory=list)
    docstring_hint: Optional[str] = Field(
        None, description="Expected docstring content (advisory, not binding)"
    )
    source_contract_id: Optional[str] = Field(
        None, description="InterfaceContract.contract_id that prescribed this element"
    )

    def to_element(self) -> "Element":
        """Bridge to existing Element model with sentinel Span for ManifestDiff comparison.

        Fills Span(0, 0, 0, 0) since the element doesn't exist in source yet.
        FQN is set to name (no module prefix available until file context is known).
        """
        from startd8.utils.code_manifest import Element, Span
        return Element(
            kind=self.kind,
            name=self.name,
            fqn=self.name,  # Caller should update with module prefix
            span=Span(start_line=0, start_col=0, end_line=0, end_col=0),
            signature=self.signature,
            bases=self.bases,
            visibility=self.visibility,
            decorators=self.decorators,
        )
```

### 4.3 ForwardFileSpec

Per-file container of `ForwardElementSpec` entries plus prescribed imports and dependencies. Maps to `FileManifest` structure for post-generation comparison.

```python
from startd8.utils.code_manifest import ImportEntry, Dependencies


class ForwardFileSpec(BaseModel):
    """Prescribed contents for a single file."""
    model_config = {"frozen": True}

    file: str = Field(..., description="Relative file path")
    elements: list[ForwardElementSpec] = Field(default_factory=list)
    imports: list[ForwardImportSpec] = Field(default_factory=list)
    dependencies: Optional[ForwardDependencies] = None


class ForwardImportSpec(BaseModel):
    """Prescribed import statement (relaxed — no Span required)."""
    model_config = {"frozen": True}

    kind: str = Field(..., pattern="^(import|from)$")
    module: str
    names: list[str] = Field(default_factory=list)
    alias: Optional[str] = None


class ForwardDependencies(BaseModel):
    """Prescribed dependency classification for a file."""
    model_config = {"frozen": True}

    external: list[str] = Field(default_factory=list)
    stdlib: list[str] = Field(default_factory=list)
```

### 4.4 ForwardManifest

Top-level container. Holds all contracts and file specs plus pipeline stage tracking.

```python
class ForwardManifest(BaseModel):
    """Top-level forward-looking code manifest."""

    schema_version: str = Field(default="1.0.0")
    pipeline_run_id: Optional[str] = None
    generated_at: str = Field(default="")
    source_checksum: Optional[str] = Field(
        None, description="Checksum of source inputs for staleness detection"
    )

    contracts: list[InterfaceContract] = Field(default_factory=list)
    file_specs: dict[str, ForwardFileSpec] = Field(
        default_factory=dict,
        description="Keyed by relative file path"
    )
    stages_completed: list[str] = Field(
        default_factory=list,
        description="Pipeline stages that have contributed to this manifest"
    )

    # --- Query methods ---

    def contracts_for_task(self, task_id: str) -> list[InterfaceContract]:
        """Return contracts applicable to a specific task.

        Includes both task-specific contracts (task_id in applicable_task_ids)
        and project-wide contracts (applicable_task_ids is empty).
        """
        ...

    def binding_constraints_for_task(self, task_id: str) -> list[str]:
        """Return precomputed binding_text strings for prompt injection.

        EXPLICIT/INFERRED contracts → [BINDING] prefix.
        TENTATIVE contracts → [ADVISORY] prefix.
        """
        ...

    def file_specs_for_task(self, task_id: str, target_files: list[str]) -> dict[str, ForwardFileSpec]:
        """Return ForwardFileSpec entries matching a task's target_files."""
        ...

    def contract_count_by_category(self) -> dict[str, int]:
        """Summary counts per ContractCategory for diagnostics."""
        ...
```

---

## 5. Extraction Strategy: Progressive Refinement Through Pipeline Stages

The FLCM is built incrementally. Each pipeline stage adds detail at the appropriate confidence level.

### 5.1 Stage Progression

| Pipeline Stage | What Gets Extracted | Confidence | Method |
|----------------|---------------------|------------|--------|
| **Plan Authoring** (human) | Cross-cutting table (protocol, health, OTel, deps per service), API schemas, shared module names | `explicit` | Human writes `shared_contracts:` YAML section in requirements doc per REQ-REGEN-004a |
| **Stage 2 (INIT)** | Proto-derived contracts: service names, RPC signatures, message types | `explicit` | Deterministic parse of `.proto` files |
| **Stage 5 (PLAN-INGESTION)** | Cross-task shared modules (features sharing `target_files`), `ParsedFeature.api_signatures`, protocol contracts, runtime dependency contracts | `inferred` | Deterministic extraction from `ParsedFeature` fields |
| **Stage 5 REFINE** | Additional contracts LLM discovers from plan text and cross-feature analysis | `tentative` | LLM extraction pass with structured output |
| **Stage 6 PLAN** | `applicable_task_ids` resolution, contract consistency validation | — (refines existing) | Deterministic cross-reference against actual task IDs |
| **Stage 6 DESIGN** | `ForwardElementSpec` entries from design doc API Surface sections; consistency check against existing contracts | `explicit` | Design doc parsing + divergence detection |
| **Stage 6 IMPLEMENT** | Read-only consumption — contracts injected as `[BINDING]` constraints | — (consumption only) | Prompt injection |
| **Post-IMPLEMENT** | Validation: compare generated code manifest against FLCM | — (validation only) | `ManifestDiff`-style comparison |

### 5.2 Hybrid Extraction Model

Three sources merge into a single `ForwardManifest`:

1. **Human-authored** (`explicit`): The plan author writes a `shared_contracts:` section in the requirements doc following REQ-REGEN-004a standards. This is the highest-confidence source and is never overridden by automated extraction.

2. **Deterministically extracted** (`inferred`): The pipeline analyzes `ParsedFeature` fields — when multiple features share `target_files`, when `api_signatures` are specified, when `protocol` and `runtime_dependencies` are set — and derives contracts. No LLM cost.

3. **LLM-discovered** (`tentative`): During the REFINE phase of plan ingestion, the LLM reviews the plan text and cross-feature relationships to suggest additional contracts. These render as `[ADVISORY]` rather than `[BINDING]`.

**Merge rules**:

- Human-authored contracts are authoritative (highest precedence)
- Deterministic extraction cannot override human contracts but can add new ones
- LLM-discovered contracts cannot override human or deterministic contracts
- Duplicate `contract_id` values are resolved by highest-confidence source
- Conflicting contracts (same `contract_id`, different values) are logged as warnings

### 5.3 Deterministic Extraction from ParsedFeature

The following `ParsedFeature` fields map directly to `InterfaceContract` entries:

| ParsedFeature Field | Contract Category | Extraction Logic |
|---------------------|-------------------|------------------|
| `api_signatures` | `function_name` or `api_endpoint` | Parse signature string → `ForwardElementSpec` with `Signature` |
| `protocol` | `infrastructure` | Map protocol value to transport contract (gRPC → proto-derived, HTTP → endpoint spec) |
| `runtime_dependencies` | `import_path` | Each dependency → `import_path` contract with package name |
| `negative_scope` | — | Not a contract but a prompt constraint; forwarded via existing `ConstraintsModule` |
| `target_files` (shared across features) | `function_name` / `class_name` | When 2+ features share a `target_file`, extract shared module contracts |

### 5.4 Proto File Extraction

For projects with `.proto` files, deterministic extraction produces:

- One `api_endpoint` contract per RPC method (service name, method, request/response message types)
- One `class_name` contract per message type (field names and types)
- One `infrastructure` contract for the transport layer (gRPC server/client setup)

**Proto extraction is optional** — the FLCM works without it for projects that don't use protobuf.

---

## 6. Storage and Threading

### 6.1 Persistence

```
.startd8/
├── forward-manifest.json      # ForwardManifest (NEW)
├── manifests/                  # Existing code manifest cache
├── state/                      # Existing resume cache
└── scaffold.json               # Existing scaffold manifest
```

The `ForwardManifest` is serialized as JSON. The `source_checksum` field enables staleness detection — if the plan or requirements inputs change, stale contracts are logged and skipped during prompt injection.

### 6.2 Seed Threading

New field on `ArtisanContextSeed`:

```python
@dataclass
class ArtisanContextSeed:
    # ... existing fields ...

    # Forward-looking interface contracts (FLCM)
    forward_manifest: Optional[Dict[str, Any]] = None
```

Populated during EMIT phase of plan ingestion. Serialized via `to_dict()` alongside existing fields. Loaded by `PlanPhaseHandler` at the start of the artisan pipeline.

### 6.3 Handoff Threading

The design-implementation handoff JSON already carries context between the two halves of the artisan pipeline. New field:

```python
handoff = {
    # ... existing handoff fields ...
    "forward_manifest": forward_manifest.model_dump(),  # NEW
}
```

This ensures contracts survive the PLAN→SCAFFOLD→DESIGN → IMPLEMENT→INTEGRATE→TEST→REVIEW→FINALIZE boundary.

### 6.4 Context Dict Threading

Within the artisan pipeline, the forward manifest flows through the shared context dict:

```python
context["forward_manifest"] = ForwardManifest.model_validate(seed_data["forward_manifest"])
```

Each phase handler can access `context["forward_manifest"]` for contract-aware decisions.

### 6.5 Contract YAML Additions

Optional additions to `artisan-pipeline.contract.yaml`:

```yaml
phases:
  plan:
    exit_requirements:
      # ... existing ...
      forward_manifest:
        required: false  # Optional — pipeline works without it
        type: ForwardManifest
        validation: schema_version_check

  design:
    entry_requirements:
      # ... existing ...
      forward_manifest:
        required: false
        type: ForwardManifest

  implement:
    entry_requirements:
      # ... existing ...
      forward_manifest:
        required: false
        type: ForwardManifest
```

---

## 7. Binding Injection Into Prompts

Two injection paths, both backward-compatible:

### 7.1 Path 1 — Merge Into prompt_constraints (IMPLEMENT phase)

The simplest path. Works with zero changes to prompt modules.

```
PlanPhaseHandler loads forward_manifest from seed
    ↓
For each task:
    task.prompt_constraints.extend(
        forward_manifest.binding_constraints_for_task(task.task_id)
    )
    ↓
Existing ConstraintsModule.render() formats them
    ↓
Flows into IMPLEMENT prompt via PipelineContextStrategy
```

**Backward-compatible**: If `forward_manifest` is `None`, no constraints are added. Existing pipelines work unchanged.

### 7.2 Path 2 — Dedicated ContractModule (DESIGN phase)

Richer rendering for design prompts, following the `IdentityModule` pattern from `design_prompts/modules.py`.

**New extractor** in `seed_mapping.py`:

```python
def extract_forward_contracts(
    task: SeedTask,
    *,
    forward_manifest: ForwardManifest | None = None,
) -> dict[str, Any] | None:
    """Extract forward contracts applicable to this task.

    Returns None if no forward manifest or no applicable contracts
    (Mottainai rule 3: degrade gracefully).
    """
    if forward_manifest is None:
        return None
    contracts = forward_manifest.contracts_for_task(task.task_id)
    if not contracts:
        return None
    return {
        "contracts": [c.model_dump() for c in contracts],
        "file_specs": {
            path: spec.model_dump()
            for path, spec in forward_manifest.file_specs_for_task(
                task.task_id, task.target_files
            ).items()
        },
    }
```

**New module** in `design_prompts/modules.py`:

```python
class ContractModule:
    """Renders forward-looking interface contracts for design prompts.

    Non-droppable (Tier 0 in budget enforcement — contracts are never dropped).
    """

    def render(self, data: dict[str, Any]) -> PromptFragment:
        contracts = data.get("contracts", [])
        file_specs = data.get("file_specs", {})

        sections = ["## Interface Contracts (Cross-Task Bindings)\n"]

        # Group by category for readability
        by_category: dict[str, list] = {}
        for c in contracts:
            by_category.setdefault(c["category"], []).append(c)

        for category, items in by_category.items():
            sections.append(f"### {category.replace('_', ' ').title()}\n")
            for item in items:
                prefix = "[BINDING]" if item["confidence"] != "tentative" else "[ADVISORY]"
                sections.append(f"- {prefix} {item['binding_text']}")
                if item.get("source_reference"):
                    sections.append(f"  Source: {item['source_reference']}")

        # File-level prescribed elements
        if file_specs:
            sections.append("\n### Prescribed File Elements\n")
            for path, spec in file_specs.items():
                sections.append(f"**{path}**:")
                for elem in spec.get("elements", []):
                    sig = elem.get("signature", "")
                    sig_str = f"({sig})" if sig else ""
                    sections.append(f"  - `{elem['kind']}` `{elem['name']}{sig_str}`")

        text = "\n".join(sections)
        return PromptFragment(
            category="contracts",
            text=text,
            token_estimate=len(text) // 4,
            droppable=False,  # Tier 0: never dropped
        )
```

### 7.3 IMPLEMENT Prompt Injection (PipelineContextStrategy)

New section in `resolve_task_context()` after IMP-P5 (Validation Hookpoints):

```python
SECTION_IMP_P6 = "IMP-P6"  # Forward Contract Bindings

SECTION_HEADINGS["IMP-P6"] = "Interface Contract Bindings"
SECTION_FIELD_MAP["IMP-P6"] = ("forward_contracts",)
```

The forward contracts are rendered as a structured binding block within the IMPLEMENT generation context, ensuring the code generator sees the exact function names, API schemas, and patterns it must use.

---

## 8. Post-Generation Validation

### 8.1 Validation Strategy

After code generation (post-IMPLEMENT), the generated code manifests are compared against the `ForwardManifest`. This is a structural comparison, not a semantic one.

```python
@dataclass(frozen=True)
class ContractViolation:
    """A single violation of a forward-looking contract."""
    contract_id: str
    violation_type: str  # "missing_function", "missing_class", "wrong_signature",
                         # "missing_file", "wrong_base_class", "missing_import"
    expected: str
    actual: Optional[str] = None
    file_path: Optional[str] = None
    severity: str = "error"  # "error" | "warning"
```

### 8.2 Validation Checks

| Contract Type | Validation Method | Uses |
|---------------|-------------------|------|
| `function_name` | `ManifestRegistry.fqn_exists()` with partial match on function name | Existing ManifestRegistry query |
| `class_name` + `base_class` | Element lookup + `bases` field check | Existing Element model |
| `api_endpoint` | Grep-based detection of route decorator/registration patterns | New: pattern-based |
| `import_path` | `ImportEntry` search in `FileManifest.imports` | Existing FileManifest structure |
| `formula` | Not structurally validatable — logged as advisory | — |
| `render_pattern` | Not structurally validatable — logged as advisory | — |
| `ForwardElementSpec` vs actual `Element` | Element-by-element name + kind comparison | `ForwardElementSpec.to_element()` bridge |
| `ForwardFileSpec` | File existence check + element inventory comparison | New: file-level validation |

### 8.3 Integration with REVIEW Phase

The REVIEW phase handler runs validation and appends `ContractViolation` entries to the review output:

```python
# In ReviewPhaseHandler
violations = validate_forward_manifest(
    forward_manifest=context["forward_manifest"],
    manifest_registry=context.get("manifest_registry"),
    generated_files=context["generated_files"],
)
if violations:
    review_output.contract_violations = violations
    # Violations with severity="error" contribute to quality gate failure
```

### 8.4 CLI Command

```bash
startd8 manifest validate-forward .startd8/forward-manifest.json --source-path src/
```

Runs the forward manifest validator against an existing code manifest, printing violations as a table with severity, contract ID, expected/actual values, and file paths.

---

## 9. Relationship to REQ-REGEN-004a

REQ-REGEN-004a (from `REGENERATION_REQUIREMENTS.md`) mandates requirements authoring standards. The FLCM formalizes these as machine-readable contracts:

| REQ-REGEN-004a Requirement | FLCM Equivalent |
|---------------------------|------------------|
| Per-service cross-cutting table (protocol, health, OTel, deps) | `InterfaceContract` with `category=infrastructure`, one per concern |
| Complete call signatures (all params for 3+ param APIs) | `ForwardElementSpec` with full `Signature` (params, return annotation) |
| Concrete value enumeration (versions, IDs, env vars) | `InterfaceContract.env_var`, `.constant_value`, `.dependency` |
| Explicit negative scope | Carried in `ParsedFeature.negative_scope` (already exists) — not duplicated in FLCM |
| Structural patterns (function vs class vs factory) | `ForwardElementSpec.kind` + `ForwardFileSpec.elements` |
| No unresolved conflicts | Contract consistency validation in Stage 6 PLAN (conflicting contracts → error) |

---

## 10. Worked Example: RUN3 Shared Contracts as ForwardManifest

This example shows how the 7 RUN3 defects would have been prevented by the following `ForwardManifest`:

```json
{
  "schema_version": "1.0.0",
  "pipeline_run_id": "online-boutique-python-run3",
  "generated_at": "2026-02-20T00:00:00Z",
  "contracts": [
    {
      "contract_id": "logger-convention",
      "category": "function_name",
      "confidence": "explicit",
      "description": "Shared JSON logger API across all Python services",
      "function_name": "getJSONLogger",
      "class_name": "CustomJsonFormatter",
      "base_class": "jsonlogger.JsonFormatter",
      "dependency": "python-json-logger",
      "applicable_task_ids": ["PI-001", "PI-002", "PI-003", "PI-004", "PI-006", "PI-007"],
      "binding_text": "[BINDING] Logger function must be named 'getJSONLogger' (not 'get_logger'), class 'CustomJsonFormatter' extending 'jsonlogger.JsonFormatter'"
    },
    {
      "contract_id": "money-formatting",
      "category": "formula",
      "confidence": "explicit",
      "description": "Proto Money type nanos-to-cents conversion",
      "formula": "nanos // 10000000",
      "constant_value": "\"%02d\"",
      "applicable_task_ids": ["PI-005"],
      "source_reference": "demo.proto Money message (units: int64, nanos: int32)",
      "binding_text": "[BINDING] Money nanos formatting: use 'nanos // 10000000' with '%02d' format (not Jinja2 slice filter)"
    },
    {
      "contract_id": "otel-tracing",
      "category": "infrastructure",
      "confidence": "explicit",
      "description": "OTel distributed tracing — OTLP exporter with env var gating",
      "import_path": "from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter",
      "env_var": "COLLECTOR_SERVICE_ADDR",
      "pattern": "os.environ[\"ENABLE_TRACING\"] == \"1\"",
      "applicable_task_ids": [],
      "binding_text": "[BINDING] Use OTLPSpanExporter (not ConsoleSpanExporter), gated by ENABLE_TRACING env var, exporter endpoint from COLLECTOR_SERVICE_ADDR"
    },
    {
      "contract_id": "email-template-render",
      "category": "render_pattern",
      "confidence": "explicit",
      "description": "Jinja2 template rendering passes protobuf object directly",
      "pattern": "template.render(order=order)",
      "applicable_task_ids": ["PI-003", "PI-005"],
      "binding_text": "[BINDING] Template render call must use 'template.render(order=order)' — pass protobuf object directly, not a converted dict"
    },
    {
      "contract_id": "shopping-assistant-api",
      "category": "api_endpoint",
      "confidence": "explicit",
      "description": "Shopping assistant HTTP API matching frontend Go service",
      "endpoint": "POST /",
      "request_schema": {"message": "string — user prompt", "image": "string — base64 or URL"},
      "response_schema": {"content": "string — Gemini response with recommendations"},
      "dependency": "langchain_google_genai",
      "applicable_task_ids": ["PI-008"],
      "binding_text": "[BINDING] Shopping assistant endpoint: POST / (not /recommendations), request {message, image}, response {content}. Use langchain_google_genai (not raw google.generativeai)"
    },
    {
      "contract_id": "jinja2-security",
      "category": "infrastructure",
      "confidence": "explicit",
      "description": "Jinja2 autoescape for XSS protection",
      "pattern": "select_autoescape(['html', 'xml'])",
      "applicable_task_ids": ["PI-003"],
      "binding_text": "[BINDING] Jinja2 Environment must use select_autoescape(['html', 'xml'])"
    }
  ],
  "file_specs": {
    "emailservice/logger.py": {
      "file": "emailservice/logger.py",
      "elements": [
        {
          "kind": "function",
          "name": "getJSONLogger",
          "signature": {"params": [{"name": "name", "annotation": "str"}], "return_annotation": "logging.Logger"},
          "source_contract_id": "logger-convention"
        },
        {
          "kind": "class",
          "name": "CustomJsonFormatter",
          "bases": ["jsonlogger.JsonFormatter"],
          "source_contract_id": "logger-convention"
        }
      ]
    },
    "recommendationservice/logger.py": {
      "file": "recommendationservice/logger.py",
      "elements": [
        {
          "kind": "function",
          "name": "getJSONLogger",
          "signature": {"params": [{"name": "name", "annotation": "str"}], "return_annotation": "logging.Logger"},
          "source_contract_id": "logger-convention"
        },
        {
          "kind": "class",
          "name": "CustomJsonFormatter",
          "bases": ["jsonlogger.JsonFormatter"],
          "source_contract_id": "logger-convention"
        }
      ]
    }
  },
  "stages_completed": ["plan_authoring", "plan_ingestion"]
}
```

### Defect-to-Contract Traceability

| Defect | Contract That Prevents It | How |
|--------|--------------------------|-----|
| DEV-R3-001 (template render pattern) | `email-template-render` | `[BINDING]` prescribes `template.render(order=order)` — artisan cannot invent `render(dict)` |
| DEV-R3-002 (money formatting formula) | `money-formatting` | `[BINDING]` prescribes `nanos // 10000000` with `"%02d"` — artisan cannot invent Jinja2 slice |
| DEV-R3-003 (wrong OTel exporter) | `otel-tracing` | `[BINDING]` prescribes `OTLPSpanExporter` — artisan cannot default to `ConsoleSpanExporter` |
| DEV-R3-004 (missing autoescape) | `jinja2-security` | `[BINDING]` prescribes `select_autoescape(['html', 'xml'])` |
| DEV-R3-005 (template dir exit) | `email-template-render` | Contract context gives artisan enough information to handle missing templates gracefully |
| DEV-R3-006 (wrong API endpoint) | `shopping-assistant-api` | `[BINDING]` prescribes `POST /` with exact request/response schema |
| DEV-R3-007 (wrong library choice) | `shopping-assistant-api` | `[BINDING]` prescribes `langchain_google_genai` — artisan cannot choose `google.generativeai` |

**Result**: All 7/7 RUN3 defects are addressable by the FLCM schema.

---

## 11. Implementation Phases

These phases are the subsequent work this requirements document enables:

| Phase | Deliverable | Description |
|-------|-------------|-------------|
| **Phase 1** | This document | Requirements + design specification |
| **Phase 2** | `src/startd8/forward_manifest.py` | Pydantic models: `InterfaceContract`, `ForwardElementSpec`, `ForwardFileSpec`, `ForwardManifest`, `ContractViolation` with `compute_binding_text()` |
| **Phase 3** | `src/startd8/forward_manifest_extractor.py` | Deterministic extraction from `ParsedFeature` + proto files; LLM extraction during REFINE; merge logic with precedence rules |
| **Phase 4** | Threading changes across pipeline | `ArtisanContextSeed.forward_manifest` field, handoff JSON field, `context["forward_manifest"]` threading, `ContractModule` in design prompts, IMP-P6 section in IMPLEMENT prompts |
| **Phase 5** | `src/startd8/forward_manifest_validator.py` | Post-generation validation against `ManifestRegistry`, REVIEW integration, `startd8 manifest validate-forward` CLI command |

---

## 12. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM extraction produces noisy contracts | False `[BINDING]` constraints cause incorrect code | Confidence levels: `tentative` renders as `[ADVISORY]` not `[BINDING]`; human review step before pipeline execution |
| Token budget pressure from contract injection | Contracts consume prompt budget, displacing other context | Tier 0 (never dropped) but capped at 20 contracts per task; contract text is compact (single `binding_text` line per contract) |
| Forward manifest staleness after plan edits | Stale contracts prescribe wrong names/patterns | `source_checksum` validation at pipeline entry; stale contracts logged and skipped; re-extraction triggered on checksum mismatch |
| Schema drift between ForwardElementSpec and Element | `to_element()` bridge produces invalid Elements | Version-gated validation; sentinel `Span(0,0,0,0)` clearly marks forward elements; `ManifestDiff` handles missing spans gracefully |
| Conflicting contracts from multiple sources | Human, deterministic, and LLM sources disagree | Strict precedence: human > deterministic > LLM; duplicate `contract_id` resolved by highest-confidence source; conflicts logged as warnings |
| Over-specification constrains LLM creativity | Excessive contracts prevent the artisan from making reasonable implementation choices | Contracts cover only interface boundaries, not implementation details; `[ADVISORY]` level for uncertain contracts; category-specific fields are all optional |

---

## 13. Design Decisions

### 13.1 Why Not Extend Element Directly?

`Element` from `code_manifest.py` is frozen (immutable) and requires `Span` (source location). Forward-looking specs describe code that doesn't exist yet — they have no source location. Rather than making `Span` optional on `Element` (which would weaken validation for all existing backward-looking manifests), `ForwardElementSpec` is a separate model with a `to_element()` bridge.

### 13.2 Why Precomputed binding_text?

Each `InterfaceContract` carries a precomputed `binding_text` string rather than being rendered dynamically. This is intentional:

1. **Human-authored contracts** need human-written constraint text (not template-generated)
2. **Deterministic extraction** can compute binding text at extraction time (no repeated work)
3. **Prompt injection** is a simple `extend()` call — no rendering logic needed at injection point
4. **Auditability** — the exact text injected into prompts is visible in the persisted manifest

### 13.3 Why Contract Categories Instead of Free-Form Tags?

The `ContractCategory` enum is closed (8 values) rather than open-ended. This is derived directly from the RUN3 defect taxonomy — each defect maps to exactly one category. A closed enum enables:

- Category-specific validation (e.g., `api_endpoint` contracts must have `endpoint` field)
- Category-aware rendering in `ContractModule` (grouped sections)
- Analytics (which categories produce the most violations?)

### 13.4 Why Two Injection Paths?

Path 1 (merge into `prompt_constraints`) works for IMPLEMENT with zero module changes. Path 2 (dedicated `ContractModule`) provides richer rendering for DESIGN prompts where the artisan needs to understand *why* a contract exists, not just *what* it prescribes. Both paths are wired because DESIGN and IMPLEMENT prompts have different rendering pipelines (`design_prompts/modules.py` vs `context_resolution.py`).

### 13.5 Why Optional Throughout?

Every threading point (`ArtisanContextSeed.forward_manifest`, handoff field, contract YAML `required: false`) is optional. This ensures:

- Existing pipelines work unchanged (no forward manifest → no contract injection → no validation)
- Incremental adoption (can start with human-authored contracts only, add extraction later)
- Backward compatibility with persisted seeds and handoff files from before FLCM existed

---

## 14. Testing Strategy

### 14.1 Unit Tests

| Test Area | What to Test |
|-----------|-------------|
| `InterfaceContract` model | Field validation, `binding_text` rendering, category-specific field requirements |
| `ForwardElementSpec.to_element()` | Bridge produces valid `Element` with sentinel `Span`; round-trip through `ManifestDiff` |
| `ForwardManifest.contracts_for_task()` | Task-specific filtering, project-wide inclusion, empty task ID handling |
| `ForwardManifest.binding_constraints_for_task()` | `[BINDING]` vs `[ADVISORY]` prefix based on confidence level |
| Extraction from `ParsedFeature` | `api_signatures` → contracts, `target_files` overlap detection, `runtime_dependencies` mapping |
| Merge precedence | Human > deterministic > LLM; duplicate `contract_id` resolution; conflict warning |
| Staleness detection | `source_checksum` mismatch → stale contracts skipped |

### 14.2 Integration Tests

| Test Area | What to Test |
|-----------|-------------|
| Seed threading | `ArtisanContextSeed.to_dict()` round-trip with `forward_manifest` field |
| Handoff threading | Design-half → implementation-half with forward manifest preservation |
| Prompt injection (Path 1) | `prompt_constraints` extended with binding text; `ConstraintsModule` renders them |
| Prompt injection (Path 2) | `ContractModule.render()` produces correct `PromptFragment` with category grouping |
| Post-generation validation | `ContractViolation` entries for missing functions, wrong signatures, missing files |
| CLI command | `startd8 manifest validate-forward` with sample manifest + generated code |

### 14.3 Verification Checklist

After implementation, verify:

1. Every RUN3 defect (DEV-R3-001 through DEV-R3-007) is addressable by the schema — confirmed in Section 10
2. Schema reuses existing models: `ElementKind`, `Signature`, `Param`, `Visibility`, `ImportEntry`, `Dependencies` — confirmed in Section 4
3. Pipeline threading covers all 8 artisan phases — confirmed in Section 6
4. Extraction handles the hybrid model (human + deterministic + LLM) — confirmed in Section 5
5. Backward compatibility: pipelines without forward manifest work unchanged — confirmed in Section 13.5
