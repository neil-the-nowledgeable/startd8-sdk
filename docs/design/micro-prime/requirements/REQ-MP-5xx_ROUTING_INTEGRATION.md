# Layer 5 — Routing & Integration (REQ-MP-5xx)

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** Planned
> **Modifies:** `contractors/artisan_phases/development.py`, `contractors/artisan_phases/preflight.py`
> **New package:** `src/startd8/micro_prime/` — `engine.py`, `prime_adapter.py`, `artisan_adapter.py`, `context.py`

---

## Overview

This layer defines how TRIVIAL and SIMPLE elements are routed to their respective handlers (template registry and local model) and how the Micro Prime engine integrates with **both** the Artisan pipeline and the Prime Contractor.

**Dual-workflow architecture:**

| Workflow | Entry Point | Integration Mechanism |
|----------|-------------|----------------------|
| **Artisan** | `ArtisanMicroPrimeAdapter` (REQ-MP-508) | Pre-pass before `ArtisanChunkExecutor` in IMPLEMENT phase |
| **Prime Contractor** | `MicroPrimeCodeGenerator` (REQ-MP-507) | Implements `CodeGenerator` protocol from `contractors/protocols.py` |

Both paths delegate to a shared `MicroPrimeEngine` (REQ-MP-506) that encapsulates the workflow-agnostic core: template registry, prompt builder, local model invocation, repair pipeline, and body splicing.

The key constraints are:
1. **Backward compatibility:** MODERATE and COMPLEX elements must be completely unaffected
2. **Graceful degradation:** The pipeline must work when Ollama is unavailable
3. **Workflow isolation:** The engine has no imports from either workflow's modules

## Requirements

### REQ-MP-500: Four-Tier Complexity Routing

**Status:** planned
**Priority:** P0

The element routing system SHALL support four tiers, extending the existing three-tier system (TIER_1/TIER_2/TIER_3 in `TaskComplexityTier`).

**Tier mapping:**

| Micro-Prime Tier | Artisan Equivalent | Agent | Cost | Selection |
|-----------------|-------------------|-------|------|-----------|
| TRIVIAL | (new) | Template registry | $0.00 | Template match (REQ-MP-304) |
| SIMPLE | (new) | `ollama:startd8-coder` | $0.00 cloud | Heuristic + import gate |
| MODERATE | TIER_1 / TIER_2 | Haiku / Sonnet | ~$0.01-0.03 | Heuristic score ≤ 2 |
| COMPLEX | TIER_3 | Sonnet / Opus | ~$0.05-0.10 | Heuristic score > 2 |

**Routing decision tree:**

```
element
  │
  ├─ template_match(elem, file_spec, contracts)?
  │   └─ YES → TRIVIAL
  │
  ├─ heuristic_score ≤ -1
  │   AND no external API imports (REQ-MP-501)
  │   AND ollama_available (REQ-MP-503)?
  │       └─ YES → SIMPLE
  │
  ├─ heuristic_score ≤ 2?
  │   └─ YES → MODERATE
  │
  └─ else → COMPLEX
```

**Acceptance criteria:**
- Template-matched elements never invoke any model
- SIMPLE elements invoke only the local Ollama model
- Failed SIMPLE elements escalate to MODERATE, not retried locally
- MODERATE/COMPLEX routing is unchanged from current behavior
- The routing decision is recorded per-element in chunk metadata

---

### REQ-MP-501: Import-Based Complexity Gate

**Status:** planned
**Priority:** P0

The heuristic classifier SHALL prevent elements from being classified as SIMPLE when their file imports external libraries with complex APIs that the local model cannot learn from a single prompt.

**Gate implementation:**

```python
_EXTERNAL_API_PACKAGES = {
    # Network / RPC
    "grpc", "grpcio", "httpx", "aiohttp", "requests",
    # Web frameworks
    "flask", "fastapi", "django", "starlette",
    # Template engines
    "jinja2", "mako",
    # Cloud SDKs
    "google.cloud", "google.auth", "google.api_core",
    "boto3", "botocore",
    "azure",
    # Database / ORM
    "sqlalchemy", "alembic", "asyncpg", "psycopg2",
    # Task queues / caching
    "celery", "redis", "kombu",
    # Testing / load
    "locust", "playwright",
}

def _import_complexity_bump(file_spec: ForwardFileSpec) -> int:
    """Count distinct external API packages in file imports."""
    external = set()
    for imp in file_spec.imports:
        pkg = imp.module.split(".")[0]
        if pkg in _EXTERNAL_API_PACKAGES:
            external.add(pkg)
        # Also check dotted prefix (e.g., google.cloud → google)
        if imp.module in _EXTERNAL_API_PACKAGES:
            external.add(imp.module)
    return len(external)
```

**Integration with heuristic classifier:**

```python
# In classify_element_heuristic():
import_bump = _import_complexity_bump(file_spec)
if import_bump > 0:
    complexity_score += import_bump
    reasons.append(f"external APIs: {import_bump} packages")
```

**Additionally:** If any `[BINDING]` constraint references an external API by name, add +2 to the score.

**Acceptance criteria:**
- Element in file importing `grpc` + `google.cloud` gets +2 to complexity score → routes to MODERATE
- Element in file importing only `json` + `logging` (stdlib) is unaffected
- The gate would have caught 8 of 12 Sonnet failures from Round 1
- The external API package set is configurable (not hardcoded in the classifier)

---

### REQ-MP-502: Escalation with Error Context

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-405

When a SIMPLE element fails local generation and repair, it SHALL be escalated to a cloud model with full context about the failure.

**Escalation payload:**

```python
@dataclass
class EscalationContext:
    element_fqn: str
    local_model: str                # "startd8-coder"
    raw_output: str                 # Original model output
    repair_steps_applied: list[str] # Which repairs were attempted
    repaired_code: Optional[str]    # Code after repair (if different from raw)
    error: str                      # SyntaxError or verification failure message
    manifest_element: ForwardElementSpec  # The target specification
```

**Integration point:** This reuses the existing `last_error` / `test_output` injection in `_execute_chunk_inner()`. The escalation context is serialized and injected as `context["last_error"]`, which the prompt builder includes in a `## Retry Feedback` section.

**Cloud model prompt injection:**

```
## Prior Local Model Attempt

Model: startd8-coder (qwen2.5-coder:7b, temperature=0.1)
Element: {element_fqn}

Raw output:
```python
{raw_output}
```

Repair steps attempted: {repair_steps_applied}
Error after repair: {error}

The local model failed. Please generate a correct implementation using the
full context below.
```

**Acceptance criteria:**
- Cloud model receives enough context to avoid repeating the local model's specific error
- Escalation is a one-shot handoff — no back-and-forth between local and cloud
- Escalated elements are tracked in metrics with `escalation_reason` (REQ-MP-600)

---

### REQ-MP-503: Ollama Availability Check

**Status:** planned
**Priority:** P1

At pipeline preflight, the system SHALL verify Ollama availability and model readiness.

**Checks:**

| Check | Method | Failure Behavior |
|-------|--------|-----------------|
| Ollama running | HTTP GET `{base_url}/api/tags` | Route all SIMPLE → MODERATE |
| `startd8-coder` model exists | Model name in `/api/tags` response | Route all SIMPLE → MODERATE |
| Model responds to inference | Optional: test prompt with 10-token limit | Log warning, proceed |

**Integration:** Extends the existing preflight check in `artisan_phases/preflight.py` (lines 1095-1156) which already validates Ollama models.

**Graceful degradation:**
- If Ollama is unavailable, TRIVIAL elements still work (templates need no model)
- SIMPLE elements are silently rerouted to MODERATE
- A warning is logged: `"Ollama unavailable — SIMPLE elements will use cloud model"`
- No pipeline failure — this is a performance optimization, not a hard dependency

**Acceptance criteria:**
- Pipeline completes successfully when Ollama is stopped
- All SIMPLE elements produce correct code via MODERATE fallback
- Warning is logged with clear message about degradation
- Preflight report includes Ollama status

---

### REQ-MP-504: Per-Element Execution in ArtisanChunkExecutor

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-500

The pipeline SHALL support per-element agent selection within the IMPLEMENT phase.

**Three implementation options (choose during implementation):**

#### Option A: Pre-Pass Before IMPLEMENT

Process TRIVIAL and SIMPLE elements during an extended SCAFFOLD phase. By the time IMPLEMENT runs, the skeleton already has some bodies filled in.

```
SCAFFOLD Phase (extended):
  1. Directory creation       [existing]
  2. Module inventory          [existing]
  3. Skeleton rendering        [DeterministicFileAssembler]
  4. TRIVIAL fill (templates)  [NEW — REQ-MP-300]
  5. SIMPLE fill (local model) [NEW — REQ-MP-201]
  6. Repair pipeline           [NEW — REQ-MP-400]

IMPLEMENT Phase:
  - Receives partially-filled skeletons
  - Only MODERATE/COMPLEX elements need cloud generation
  - Cloud models see working examples in the skeleton (from TRIVIAL/SIMPLE)
```

**Advantages:** Clean separation; cloud models get better context from filled examples.
**Disadvantages:** Adds latency to SCAFFOLD; changes phase boundaries.

#### Option B: Agent Spec Extension

Add an `ollama_spec` to `ArtisanChunkExecutor` alongside `drafter_spec` / `refiner_spec` / `tier3_drafter_spec`.

```python
def _resolve_local_model(self) -> Optional[BaseAgent]:
    """Resolve the local model agent for SIMPLE elements."""
    if not self._ollama_available:
        return None
    return resolve_agent_spec("ollama:startd8-coder", max_tokens=512)
```

**Advantages:** Minimal change to existing architecture.
**Disadvantages:** Chunk executor currently processes full chunks, not individual elements.

#### Option C: Element-Level Chunk Splitting

Split SIMPLE elements into separate single-element chunks processed before the main chunk executor runs.

**Advantages:** Leverages existing chunk processing infrastructure.
**Disadvantages:** Increases chunk count; adds coordination complexity.

**Acceptance criteria (regardless of option chosen):**
- SIMPLE elements are processed by the local model
- MODERATE/COMPLEX elements in the same file are unaffected
- The skeleton has SIMPLE bodies filled in before cloud models see the file
- No regression in existing artisan pipeline tests

---

### REQ-MP-505: Skeleton Preservation Across Tiers

**Status:** planned
**Priority:** P0

When multiple elements in the same file are processed by different tiers, the skeleton file SHALL be the single assembly target. Each tier splices its output independently.

**Processing order constraint:** TRIVIAL and SIMPLE elements SHOULD be processed before MODERATE/COMPLEX elements in the same file.

**Rationale:** When the cloud model generates MODERATE/COMPLEX elements, it benefits from seeing working implementations of SIMPLE elements in the same file. This provides in-context examples at zero additional cost.

**Concurrency constraint:** Multiple elements in the same file SHALL NOT be spliced concurrently. Splicing modifies the skeleton source and must be serialized per file.

**Acceptance criteria:**
- A file with 3 TRIVIAL, 2 SIMPLE, and 4 MODERATE elements has all 9 bodies in the final file
- The skeleton's import block, `__all__`, and structure are never modified by body splicing
- `ast.parse()` passes on the final assembled file after all splices
- Processing order ensures SIMPLE bodies are visible to cloud models

---

### REQ-MP-506: MicroPrimeEngine — Shared Core

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-300 (template registry), REQ-MP-200 (skeleton-first prompting), REQ-MP-400 (repair pipeline)

A `MicroPrimeEngine` class SHALL encapsulate the workflow-agnostic core: template registry, prompt builder, local model invocation, repair pipeline, and body splicing. Both the Artisan adapter and Prime adapter call into this engine.

**Interface:**

```python
class MicroPrimeEngine:
    """Workflow-agnostic micro-prime core.

    Processes TRIVIAL and SIMPLE elements using templates and
    local model inference. Returns results that the caller
    (Artisan adapter or Prime adapter) maps to its workflow.
    """

    def __init__(
        self,
        template_registry: TemplateRegistry,
        repair_pipeline: ManifestRepairPipeline,
        ollama_model: str = "startd8-coder",
        ollama_base_url: str = "http://localhost:11434",
    ) -> None: ...

    def process_elements(
        self,
        elements: list[ForwardElementSpec],
        file_spec: ForwardFileSpec,
        contracts: list[InterfaceContract],
        skeleton_source: str,
        context: MicroPrimeContext,
    ) -> MicroPrimeResult: ...

    def classify_element(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        contracts: list[InterfaceContract],
    ) -> MicroPrimeTier: ...
```

**Result type:**

```python
@dataclass
class MicroPrimeResult:
    """Output from the engine for a single file's elements."""
    assembled_source: str               # Skeleton with bodies spliced in
    element_results: list[ElementResult] # Per-element outcome
    trivial_count: int
    simple_count: int
    simple_escalated: list[EscalationContext]  # Elements needing cloud fallback
    metrics: list[MicroPrimeElementMetrics]

@dataclass
class ElementResult:
    element_fqn: str
    tier: MicroPrimeTier                # TRIVIAL | SIMPLE | MODERATE | COMPLEX
    code: Optional[str]                 # Generated body (None for MODERATE/COMPLEX)
    repair_result: Optional[RepairResult]
    generation_time_ms: int
    generation_tokens: int
```

**Dependency graph:**

```
MicroPrimeEngine
  ├── forward_manifest (ForwardManifest, ForwardFileSpec, ForwardElementSpec)
  ├── utils/file_assembler (DeterministicFileAssembler.splice_body)
  ├── utils/code_templates (TemplateRegistry)
  ├── utils/manifest_repair (ManifestRepairPipeline)
  └── MicroPrimeContext (context.py)
```

**Acceptance criteria:**
- Engine has NO imports from `contractors/artisan_phases/` or `contractors/prime_contractor.py`
- Engine depends only on `forward_manifest`, `utils/file_assembler`, `utils/code_templates`, `utils/manifest_repair`
- Both adapters produce identical results for the same input elements
- Engine is independently testable with mock Ollama responses
- `classify_element()` uses the same heuristic + import gate as REQ-MP-500/REQ-MP-501

---

### REQ-MP-507: CodeGenerator Protocol Implementation (Prime Path)

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-506

A `MicroPrimeCodeGenerator` SHALL implement the `CodeGenerator` protocol from `contractors/protocols.py`, enabling it to be used as the `code_generator` parameter in `PrimeContractorWorkflow`.

**Protocol compliance:**

```python
from startd8.contractors.protocols import CodeGenerator, GenerationResult

class MicroPrimeCodeGenerator(CodeGenerator):
    """CodeGenerator that routes TRIVIAL/SIMPLE elements through
    the local MicroPrimeEngine and delegates MODERATE/COMPLEX
    to a fallback CodeGenerator (typically LeadContractorCodeGenerator).
    """

    def __init__(
        self,
        engine: MicroPrimeEngine,
        fallback: CodeGenerator,        # For MODERATE/COMPLEX elements
        manifest: ForwardManifest,
    ) -> None: ...

    def generate(
        self,
        task: str,
        context: dict[str, Any],
        target_files: list[str],
    ) -> GenerationResult: ...
```

**Context consumption:** The Prime Contractor passes a `gen_context` dict. `MicroPrimeCodeGenerator` SHALL extract:

| Key | Source | Used For |
|-----|--------|----------|
| `domain_constraints` | `ForwardManifest.binding_constraints_for_task()` | Binding constraints in prompts |
| `forward_contracts` | Pipeline mode (Markdown-formatted) | Additional constraints |
| `existing_files` | `PrimeContractorWorkflow.develop_feature()` (40KB budget) | Edit-mode context |
| `service_metadata` | Seed enrichment | Service-specific patterns |
| `feature_name` | `FeatureSpec.name` | Prompt context |

**Processing flow:**

```
MicroPrimeCodeGenerator.generate()
  │
  ├─ 1. Build MicroPrimeContext from gen_context
  ├─ 2. For each target file:
  │     ├─ Resolve ForwardFileSpec from manifest
  │     ├─ Render skeleton via DeterministicFileAssembler
  │     ├─ Call engine.process_elements() for TRIVIAL/SIMPLE
  │     └─ Collect escalated elements
  ├─ 3. If escalated elements exist:
  │     └─ Delegate to fallback.generate() with escalation context
  ├─ 4. Merge results: local + fallback
  └─ 5. Return GenerationResult
```

**Acceptance criteria:**
- `MicroPrimeCodeGenerator` can be passed as `code_generator=` to `PrimeContractorWorkflow`
- Returns `GenerationResult` with `success`, `generated_files`, `cost_usd`, `input_tokens`, `output_tokens`
- Works in both `ExecutionMode.STANDALONE` and `ExecutionMode.PIPELINE`
- Falls back to `LeadContractorCodeGenerator` for MODERATE/COMPLEX elements
- Escalated elements include `EscalationContext` (REQ-MP-502) in the fallback call

---

### REQ-MP-508: Artisan Adapter (Artisan Path)

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-506

An `ArtisanMicroPrimeAdapter` SHALL integrate the `MicroPrimeEngine` into the Artisan IMPLEMENT phase as a pre-pass that fills TRIVIAL and SIMPLE elements before the `ArtisanChunkExecutor` processes MODERATE/COMPLEX elements.

**Integration point:** Between skeleton rendering (SCAFFOLD) and chunk execution (IMPLEMENT).

**Processing flow:**

```
SCAFFOLD Phase:
  1. Directory creation              [existing]
  2. Module inventory                [existing]
  3. Skeleton rendering              [DeterministicFileAssembler]
  ──────────────────────────────────
  4. ArtisanMicroPrimeAdapter runs:  [NEW]
     ├─ For each file in chunk:
     │   ├─ Classify elements → TRIVIAL/SIMPLE/MODERATE/COMPLEX
     │   ├─ Process TRIVIAL (templates) and SIMPLE (local model)
     │   ├─ Run repair pipeline on SIMPLE results
     │   └─ Splice bodies into skeleton
     └─ Record escalated SIMPLE elements for chunk executor
  ──────────────────────────────────

IMPLEMENT Phase:
  - ArtisanChunkExecutor receives partially-filled skeletons
  - Only MODERATE/COMPLEX elements need cloud generation
  - Escalated SIMPLE elements are included as MODERATE
  - Cloud models see working TRIVIAL/SIMPLE bodies as in-context examples
```

**Interface:**

```python
class ArtisanMicroPrimeAdapter:
    """Integrates MicroPrimeEngine into the Artisan IMPLEMENT phase."""

    def __init__(self, engine: MicroPrimeEngine) -> None: ...

    def pre_process_chunk(
        self,
        chunk: DevelopmentChunk,
        phase_data: dict,
    ) -> PreProcessResult: ...

@dataclass
class PreProcessResult:
    updated_skeleton_sources: dict[str, str]  # file_path → assembled source
    escalated_elements: list[EscalationContext]
    metrics: list[MicroPrimeElementMetrics]
    elements_filled: int                      # Count of TRIVIAL + SIMPLE bodies inserted
```

**Acceptance criteria:**
- MODERATE/COMPLEX elements are unaffected — existing `ArtisanChunkExecutor` behavior is preserved
- Cloud models receive partially-filled skeletons with TRIVIAL/SIMPLE bodies as in-context examples
- Adapter reuses the existing `_execute_chunk_inner()` retry/escalation pattern for SIMPLE failures
- No regression in existing artisan pipeline tests
- Adapter can be disabled via configuration flag (falls back to all-cloud behavior)

---

### REQ-MP-509: Context Normalization

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-506

The `MicroPrimeEngine` SHALL accept a normalized `MicroPrimeContext` that abstracts away the differences between Artisan and Prime context shapes.

**Context shape differences:**

| Field | Artisan Source | Prime Source |
|-------|---------------|-------------|
| Forward manifest | Phase pipeline data (`phase_data["forward_manifest"]`) | `seed["forward_manifest"]` |
| Binding constraints | `ForwardManifest.binding_constraints_for_task()` | `gen_context["domain_constraints"]` |
| Existing files | Chunk context (`chunk.file_contents`) | `gen_context["existing_files"]` (40KB budget) |
| Target files | `DevelopmentChunk.file_targets` | `feature.target_files` |
| Execution mode | Always pipeline | `ExecutionMode.STANDALONE` or `PIPELINE` |

**Normalized context:**

```python
@dataclass(frozen=True)
class MicroPrimeContext:
    """Workflow-agnostic context consumed by MicroPrimeEngine.

    Each adapter (Artisan, Prime) maps its workflow-specific
    context shape into this normalized form.
    """
    manifest: ForwardManifest
    target_files: list[str]
    binding_constraints: list[str]
    existing_file_contents: dict[str, str]  # file_path → source
    ollama_available: bool
    ollama_model: str = "startd8-coder"
```

**Adapter factory methods:**

```python
class MicroPrimeContext:
    @classmethod
    def from_artisan(
        cls,
        chunk: DevelopmentChunk,
        phase_data: dict,
        ollama_available: bool,
    ) -> "MicroPrimeContext": ...

    @classmethod
    def from_prime(
        cls,
        gen_context: dict[str, Any],
        manifest: ForwardManifest,
        target_files: list[str],
        ollama_available: bool,
    ) -> "MicroPrimeContext": ...
```

**Acceptance criteria:**
- `MicroPrimeEngine` never inspects workflow-specific context keys
- Artisan adapter builds `MicroPrimeContext` from phase pipeline data via `from_artisan()`
- Prime adapter builds `MicroPrimeContext` from `gen_context` dict via `from_prime()`
- Both produce the same `MicroPrimeContext` shape for the same underlying data
- Context is immutable (`frozen=True`) — engine cannot modify it

---

### REQ-MP-510: GenerationResult Emission

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-507, REQ-MP-508

Both adapters SHALL produce results compatible with their respective workflows.

**Prime path:** Return `GenerationResult` directly (required by `CodeGenerator` protocol):

```python
GenerationResult(
    success=True,
    generated_files={"src/service/logger.py": assembled_source},
    cost_usd=0.00,          # Local model — zero cloud cost
    input_tokens=total_in,
    output_tokens=total_out,
)
```

**Artisan path:** Write assembled files to the chunk's output directory and populate `exec_output` for the existing phase pipeline:

```python
# ArtisanMicroPrimeAdapter populates:
exec_output = {
    "files_written": ["src/service/logger.py"],
    "elements_filled": 5,      # TRIVIAL + SIMPLE count
    "escalated": 2,            # Elements needing cloud fallback
    "micro_prime_metrics": [...],  # Per-element metrics
}
```

**Cost tracking:**

| Element Tier | `cost_usd` | `input_tokens` / `output_tokens` |
|-------------|-----------|----------------------------------|
| TRIVIAL | $0.00 | 0 / 0 (template — no model) |
| SIMPLE (success) | $0.00 cloud | Local model tokens (informational) |
| SIMPLE (escalated) | Actual cloud cost | Cloud model tokens |
| MODERATE / COMPLEX | Actual cloud cost | Cloud model tokens |

**Acceptance criteria:**
- Prime adapter returns `GenerationResult` with all required fields (`success`, `generated_files`, `cost_usd`, `input_tokens`, `output_tokens`)
- Artisan adapter's output is compatible with `_execute_chunk_inner()` expectations
- Cost tracking distinguishes local (free) from escalated (cloud cost) elements
- Escalated elements' cloud costs are correctly attributed to the SIMPLE tier in metrics

---

### REQ-MP-511: Per-Element API Dependency Analysis

**Status:** planned
**Priority:** P0
**Refines:** REQ-MP-501 (import-based complexity gate)
**Empirical basis:** Round 2 import gate analysis — file-level gate blocks 8 passing elements

The complexity gate SHALL analyze **per-element** API dependencies rather than relying solely on file-level imports. A file may import external libraries, but individual elements within that file may not use them.

**Problem with file-level gating (REQ-MP-501):**

Round 2 experiment showed that a file-level import gate would have:
- **Caught** 10 of 14 failures (elements that use external APIs in their body)
- **Blocked** 8 elements that actually **passed** verification despite being in external-import files

| Element | File | File Imports | Passed? | Body Uses External API? |
|---------|------|-------------|---------|------------------------|
| `HealthCheck.Check` | email_server.py | grpc, jinja2, opentelemetry | **PASS** | No — returns well-known gRPC response |
| `WebsiteUser.viewCart` | locustfile.py | locust, faker | **PASS** | No — `self.client.get("/cart")` |
| `WebsiteUser.emptyCart` | locustfile.py | locust, faker | **PASS** | No — `self.client.post("/cart/empty")` |
| `WebsiteUser.logout` | locustfile.py | locust, faker | **PASS** | No — `self.client.get("/logout")` |
| `get_secret` | shoppingassistantservice.py | flask, google.cloud, langchain | **PASS** | Yes, but simple GCP pattern |
| `WebsiteUser.setCurrency` | locustfile.py | locust, faker | FAIL | Yes — missing `@task` decorator |
| `WebsiteUser.browseProduct` | locustfile.py | locust, faker | FAIL | Yes — needs product IDs from app |

**Per-element analysis signals:**

The gate SHALL examine three signals per element (not just per file):

| Signal | Weight | Detection |
|--------|--------|-----------|
| Element's binding constraints reference external API | +3 | `[BINDING]` text mentions package from `_EXTERNAL_API_PACKAGES` |
| Element's docstring hints at external library usage | +1 | Docstring contains external package names or API verbs (`gRPC call`, `send email`, `render template`) |
| Element has simple HTTP/data pattern despite external file imports | -2 | Name matches `get_*`, `is_*`, `on_start`, `logout`; signature has ≤1 real param; return type is `None` or primitive |

**Two-pass algorithm:**

```python
def classify_element_complexity(
    elem: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
) -> tuple[Complexity, list[str]]:
    """Two-pass complexity classification.

    Pass 1 (REQ-MP-501): File-level import scan — coarse signal.
    Pass 2 (REQ-MP-511): Per-element refinement — override coarse signal.
    """
    score, reasons = _heuristic_base_score(elem)  # Existing heuristic

    # Pass 1: File-level import bump (REQ-MP-501)
    file_import_bump = _import_complexity_bump(file_spec)
    if file_import_bump > 0:
        score += file_import_bump
        reasons.append(f"file imports {file_import_bump} external packages")

    # Pass 2: Per-element refinement (REQ-MP-511)
    elem_signals = _per_element_api_signals(elem, file_spec, contracts)
    score += elem_signals.score_adjustment
    reasons.extend(elem_signals.reasons)

    return _score_to_complexity(score), reasons
```

**Interaction with other requirements:**
- REQ-MP-501 becomes Pass 1 (coarse file-level gate, unchanged)
- REQ-MP-511 is Pass 2 (fine-grained per-element refinement)
- REQ-MP-500 routing decision tree uses the combined score
- REQ-MP-600 metrics SHALL record both the file-level and per-element scores for analysis

**Projected impact on Round 2 data:**

| Gate | Elements routed locally | Verified | Rate |
|------|------------------------|----------|------|
| No gate (current) | 24 | 10 | 42% |
| File-level only (REQ-MP-501) | 6 | 2 | 33% |
| File-level + per-element (REQ-MP-501 + REQ-MP-511) | ~14 | ~10 | **~71%** |

The per-element refinement would retain the 8 passing elements blocked by the file-level gate while still catching elements whose bodies require external API knowledge.

**Acceptance criteria:**
- Elements in external-import files that don't use external APIs in their body are classified as SIMPLE
- Elements that reference external APIs in binding constraints are bumped to MODERATE
- The file-level gate (REQ-MP-501) is still applied as a coarse first pass
- The per-element refinement can override the file-level bump downward (but not below SIMPLE)
- Both scores (file-level and per-element) are recorded in metrics
- The `_EXTERNAL_API_PACKAGES` set is shared between REQ-MP-501 and REQ-MP-511

---

### REQ-MP-512: Verification-Gated Escalation Flow

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-502 (escalation with error context), REQ-MP-504 (per-element execution), REQ-MP-508 (artisan adapter), REQ-MP-405 (AST validation gate), REQ-MP-407 (bare statement wrapping)
**Strengthens:** REQ-MP-502 by defining the end-to-end flow; REQ-MP-504 by specifying the concrete escalation trigger; REQ-MP-508 by defining how the adapter handles mixed success/failure results
**Empirical basis:** Round 2 end-to-end flow (24 SIMPLE elements, 10 passed, 14 failed verification)

The pipeline SHALL implement a verification-gated escalation flow where locally-generated elements are verified before acceptance and failed elements are escalated to cloud models with full diagnostic context.

**End-to-end flow:**

```
For each SIMPLE element:
  │
  ├─ 1. Generate with local model (ollama:startd8-coder)
  │
  ├─ 2. Run repair pipeline (REQ-MP-400)
  │     ├─ Fence strip → Over-gen trim → Bare wrap (REQ-MP-407)
  │     ├─ Indent normalize → Signature reconcile → Import complete
  │     └─ AST validation gate (REQ-MP-405)
  │
  ├─ 3. AST valid?
  │     ├─ NO → Escalate immediately (syntax failure)
  │     └─ YES → Continue to verification
  │
  ├─ 4. Lightweight verification (semantic check)
  │     ├─ PASS → Accept element, splice into skeleton
  │     └─ FAIL → Escalate with verification failure context
  │
  └─ 5. Escalation (REQ-MP-502):
        ├─ Package EscalationContext (raw output, repair steps, error)
        ├─ Route element to MODERATE tier (cloud model)
        └─ Cloud model receives prior attempt as context
```

**Lightweight verification (Step 4):**

Full Sonnet verification ($0.034 for 24 elements in Round 2) is too expensive for production use per-element. The verification gate SHALL support two modes:

| Mode | Method | Cost | When to Use |
|------|--------|------|-------------|
| **Structural** | AST analysis: checks function has return statement matching return annotation, no bare `raise NotImplementedError`, no placeholder strings | $0.00 | Default — fast, catches obvious failures |
| **Semantic** | Sonnet batch review (existing `verify_with_sonnet()`) | ~$0.001/element | Optional — enabled via config flag for high-confidence requirements |

**Structural verification checks:**

```python
def _structural_verify(
    code: str,
    target: ForwardElementSpec,
) -> tuple[bool, str]:
    """Zero-cost structural verification using AST analysis."""
    tree = ast.parse(code)
    func = _find_function_node(tree, target.name)
    if not func:
        return False, "Target function not found in output"

    # Check 1: No remaining NotImplementedError
    for node in ast.walk(func):
        if isinstance(node, ast.Raise) and _is_not_implemented(node):
            return False, "Body still contains raise NotImplementedError"

    # Check 2: Return statement present if return annotation is non-None
    if target.signature and target.signature.return_annotation:
        ret_ann = target.signature.return_annotation
        if ret_ann not in ("None", "none"):
            has_return = any(
                isinstance(n, ast.Return) and n.value is not None
                for n in ast.walk(func)
            )
            if not has_return:
                return False, f"No return statement for -> {ret_ann}"

    # Check 3: Body is not trivially empty (single pass)
    body_stmts = [s for s in func.body
                  if not isinstance(s, ast.Expr)  # Skip docstrings
                  or not isinstance(s.value, ast.Constant)]
    if len(body_stmts) < 1:
        return False, "Function body is empty after docstring"

    return True, "Structural checks passed"
```

**Batch escalation optimization:**

When multiple SIMPLE elements fail in the same file, the adapter SHALL batch them into a single escalation rather than individual cloud calls:

```python
@dataclass
class BatchEscalation:
    file_path: str
    elements: list[EscalationContext]
    partial_skeleton: str  # Skeleton with successful SIMPLE bodies filled in
```

The cloud model receives the partially-filled skeleton (showing successful elements as examples) and a list of elements that need generation. This provides stronger in-context examples than individual escalation.

**Interaction with existing requirements:**
- REQ-MP-502 defines the `EscalationContext` payload — this requirement defines WHEN escalation fires and HOW failures are batched
- REQ-MP-504 defines where per-element execution happens — this requirement defines the decision logic within that execution
- REQ-MP-508 defines the artisan adapter interface — this requirement specifies how `pre_process_chunk()` partitions results into accepted vs escalated
- REQ-MP-405 is the AST gate that feeds Step 3 — this requirement adds Step 4 (verification) as a second gate
- REQ-MP-407 (bare statement wrapping) runs in the repair pipeline (Step 2) and can recover elements that would otherwise hit Step 4 as structural failures

**Round 2 projected impact:**

| Stage | Elements | Without REQ-MP-512 | With REQ-MP-512 |
|-------|----------|-------------------|-----------------|
| Generated locally | 24 | All accepted or all escalated | 24 generated |
| Repair recovered | ~3 (REQ-MP-407) | N/A | 3 bare-statement wraps |
| Structural verify PASS | ~13 | N/A | Accepted locally |
| Structural verify FAIL | ~11 | N/A | Escalated to cloud |
| Cloud generates | 0 or 24 | All-or-nothing | ~11 (only failures) |
| **Net cloud calls saved** | — | 0 | **~13 (54%)** |

**Acceptance criteria:**
- Elements that pass both AST validation and structural verification are accepted without cloud calls
- Elements that fail either gate are escalated with full `EscalationContext`
- Escalation is batched per-file (one cloud call per file, not per element)
- The cloud model receives the partially-filled skeleton showing successful elements
- Structural verification mode is the default; semantic (Sonnet) mode is configurable
- Escalated elements are tracked in metrics with `escalation_reason` (syntax_failure | structural_failure | semantic_failure)
- The flow works identically in both Artisan (REQ-MP-508) and Prime (REQ-MP-507) paths

---

## Integration Checklist

| Step | File | Change |
|------|------|--------|
| 1 | `contractors/artisan_phases/preflight.py` | Add `startd8-coder` availability check |
| 2 | `contractors/artisan_phases/development.py` | Add TRIVIAL/SIMPLE routing to `_classify_complexity()` |
| 3 | `contractors/artisan_phases/development.py` | Add file-level import gate (REQ-MP-501) |
| 3a | `micro_prime/engine.py` | Add per-element API dependency analysis (REQ-MP-511) |
| 3b | `micro_prime/engine.py` | Add structural verification + escalation flow (REQ-MP-512) |
| 4 | `utils/code_templates.py` | New: template registry |
| 5 | `utils/manifest_repair.py` | New: repair pipeline (incl. bare statement wrapping, REQ-MP-407) |
| 6 | `utils/file_assembler.py` | Add `splice_body()` method |
| 7 | `micro_prime/engine.py` | New: `MicroPrimeEngine` — workflow-agnostic core |
| 8 | `micro_prime/context.py` | New: `MicroPrimeContext` with `from_artisan()` / `from_prime()` factories |
| 9 | `micro_prime/prime_adapter.py` | New: `MicroPrimeCodeGenerator` implementing `CodeGenerator` protocol |
| 10 | `micro_prime/artisan_adapter.py` | New: `ArtisanMicroPrimeAdapter` pre-pass for IMPLEMENT phase |
| 11 | `contractors/context_seed_handlers.py` | Hook `ArtisanMicroPrimeAdapter` into SCAFFOLD→IMPLEMENT boundary |
