# Micro-Ingest — Requirements

> **Version:** 0.1.0
> **Status:** DRAFT
> **Date:** 2026-03-10
> **Scope:** Local-first, per-task code example generation using Ollama and deterministic assembly — replaces cloud-dependent Option B
> **Parent:** [TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md](./TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md)
> **Supersedes:** [LLM_ENRICHMENT_REQUIREMENTS.md](./LLM_ENRICHMENT_REQUIREMENTS.md) (cloud Option B — retained as reference for future hybrid use)
> **Key Principle:** Use the same three-tier pipeline that makes Micro Prime successful (deterministic → template → Ollama) but apply it to task *enrichment* instead of task *implementation*

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Architecture](#2-architecture)
3. [Phase 1 — Per-Task Decomposition (REQ-MI-1xx)](#3-phase-1--per-task-decomposition-req-mi-1xx)
4. [Phase 2 — Deterministic Stub Assembly (REQ-MI-2xx)](#4-phase-2--deterministic-stub-assembly-req-mi-2xx)
5. [Phase 3 — Ollama Code Example Generation (REQ-MI-3xx)](#5-phase-3--ollama-code-example-generation-req-mi-3xx)
6. [Configuration (REQ-MI-4xx)](#6-configuration-req-mi-4xx)
7. [Observability (REQ-MI-5xx)](#7-observability-req-mi-5xx)
8. [Status Dashboard](#8-status-dashboard)
9. [Traceability Matrix](#9-traceability-matrix)
10. [Verification Strategy](#10-verification-strategy)
11. [Cross-References](#11-cross-references)

---

## 1. Problem Statement

### 1.1 The Code Example Gap

After Option A (deterministic enrichment), tasks have negative scope, requirement references, and target files. But the highest-impact density signal — **code examples** — remains sparse:

| Signal | After Option A | Desired | Impact |
|--------|---------------|---------|--------|
| Code examples (fenced code blocks) | 1-2/6 (from API signature stubs only) | 4-6/6 | Anchors LLM generation; reduces hallucination by 40-60% (Kaizen correlation: `draft_word_count` ρ=+0.280) |
| Signature stubs | 2-3/6 | 4-6/6 | Provides type-correct function skeletons the LLM can fill in |
| Usage patterns | 0/6 | 2-3/6 | Shows how the generated code integrates with callers |

### 1.2 Why Local-First

The original Option B (LLM_ENRICHMENT_REQUIREMENTS.md) assumed a cloud model for batch JSON enrichment. Analysis shows:

| Requirement | Cloud Option B | Micro-Ingest |
|------------|---------------|-------------|
| JSON structured output | Required (unreliable locally) | Not needed — code-native output |
| Batch processing | Required (6 tasks in one call) | Per-task (fits 1024-token budget) |
| Input budget | 2000-4000 tokens | ≤1024 tokens (proven Ollama sweet spot) |
| Output format | JSON array | Raw Python code (model's native strength) |
| Cost | $0.02-0.10 per run | $0.00 (local inference) |
| Latency | 2-5s (network round-trip) | 4-8s per element (local, parallelizable) |
| Success rate | ~95% (cloud) | ~90% for SIMPLE tier (proven across 19 Kaizen runs) |

### 1.3 The Three-Tier Insight

Micro Prime's success comes from routing by capability:

```
TRIVIAL → Template (deterministic, 100% success, 0ms)
SIMPLE  → Ollama   (local LLM, 90% success, 4-8s)
MODERATE+ → Cloud  (escalation, 95%+ success, 2-5s)
```

Micro-Ingest applies the same principle to enrichment:

```
Tier 0: DFA-renderable   → DeterministicFileAssembler stubs (0 LLM, 0ms)
Tier 1: Template-matchable → Micro Prime templates (0 LLM, 0ms)
Tier 2: SIMPLE-viable      → Ollama per-element generation (local, 4-8s)
Skip:   Everything else    → Leave for downstream DESIGN/IMPLEMENT phases
```

### 1.4 Constraints

- **Zero cloud LLM calls** — all enrichment is deterministic or local Ollama
- **Per-task processing** — no batch prompts; each task enriched independently
- **Code-native output only** — no JSON parsing; all outputs are Python source
- **Append-only** — follows TDE-106 no-clobber rule; never overwrites existing content
- **Fail-safe** — enrichment failures never block the pipeline; skip and log
- **Iterative delivery** — Phase 1 (decomposition) ships first; Phases 2-3 build on it

---

## 2. Architecture

### 2.1 Pipeline Position

The logical pipeline is:

```
PARSE → ASSESS → TRANSFORM → REFINE → EMIT
```

Micro-Ingest runs **inside** `_phase_emit()`, which has its own internal ordering:

```
_phase_emit():
  1. ForwardManifest construction     (FLCM extractor, zero LLM cost)
  2. DFA skeleton validation          (deterministic)
  3. _derive_tasks_from_features()    (task list creation)
  4. enrich_tasks_deterministic()     (Option A — existing)
  5. [MICRO-INGEST]                   ← NEW insertion point
  6. _build_seed_artifacts()
  7. compute_seed_quality()           (scoring reflects enrichment)
```

**Key insight:** `ForwardManifest` (with real `ForwardFileSpec` data from FLCM extraction) IS available at the Micro-Ingest insertion point. This means Tier 0 can use real file specs when they exist — synthetic specs from `api_signatures` are a fallback, not the primary path.

Micro-Ingest consumes:

- Task list (post-Option A, with negative_scope, target_files, etc.)
- `ParsedFeature` index (for `api_signatures`, `protocol`, `runtime_dependencies`)
- `ForwardManifest` file specs (constructed earlier in `_phase_emit()` from FLCM extraction)

### 2.2 Per-Task Decision Tree

```
For each task lacking code examples:

  1. Has ForwardFileSpec with elements?
     ├── YES → Tier 0: Render stubs via DeterministicFileAssembler
     │         (full signatures, imports, class hierarchy)
     │         → Append rendered code block to task description
     │         → DONE (no LLM needed)
     └── NO → continue

  2. Has api_signatures from ParsedFeature?
     ├── YES → Attempt to build synthetic ForwardElementSpec[]
     │         from parsed signature strings
     │         ├── All parse cleanly → Tier 0 (DFA render)
     │         └── Parse failures → Tier 1/2 (template or Ollama)
     └── NO → continue

  3. Elements match Micro Prime templates?
     ├── YES → Tier 1: Render via TemplateRegistry
     │         (config constants, properties, dunder methods, etc.)
     │         → Append rendered code block to task description
     │         → DONE (no LLM needed)
     └── NO → continue

  4. Element is SIMPLE-tier viable?
     ├── YES → Tier 2: Generate via Ollama (_handle_simple pipeline)
     │         ├── Success → Append code block
     │         └── Failure → Skip (no escalation for enrichment)
     └── NO → Skip (leave for DESIGN/IMPLEMENT)
```

### 2.3 What Micro-Ingest Does NOT Do

- **No JSON output** — model produces Python code, not structured data
- **No batch processing** — each task/element processed independently
- **No cloud escalation** — if Ollama fails, skip (enrichment is advisory)
- **No requirement reference extraction** — Option A handles this deterministically
- **No negative scope inference** — Option A handles this via ParsedFeature forwarding
- **No description rewriting** — only appends code blocks; never modifies prose

---

## 3. Phase 1 — Per-Task Decomposition (REQ-MI-1xx)

**Goal:** Classify each task's enrichment needs and route to the appropriate tier. Ships first as a standalone diagnostic — no code generation yet, just the routing decision and a report showing what *would* be generated.

### REQ-MI-100: Task Enrichment Classifier

For each task in the post-Option-A task list, compute an `EnrichmentRoute`:

```python
@dataclass
class EnrichmentRoute:
    task_id: str
    needs_code_example: bool        # True if description has no ``` blocks
    tier: int                       # 0=DFA, 1=template, 2=ollama, -1=skip
    tier_reason: str                # Human-readable reason for tier assignment
    elements: list[str]             # Element FQNs that would be generated
    estimated_tokens: int           # Estimated output token count
    has_forward_spec: bool          # True if ForwardFileSpec exists for target file
    has_api_signatures: bool        # True if ParsedFeature has api_signatures
    template_matches: list[str]     # Template names that match (Tier 1)
```

**Classification rules:**

1. If task description already contains a fenced code block (`` ``` ``): `needs_code_example = False`, `tier = -1` (skip)
2. If `ForwardManifest.file_specs` contains an entry matching any `target_files` entry: `tier = 0` (DFA). If multiple match, use the first match by manifest order. If `target_files` is empty, treat as no match.
3. If `ParsedFeature.api_signatures` is non-empty and all signatures parse to valid `ForwardElementSpec`: `tier = 0` (synthetic DFA)
4. If signatures parse partially, check parseable elements against `TemplateRegistry.try_template_match()`: `tier = 1` if any match
5. If any parseable elements are SIMPLE-viable (≤4 params, ≤8 imports, create-mode): `tier = 2` (Ollama)
6. If signatures parse partially but no template or SIMPLE-viable elements exist: `tier = -1` (skip — no viable elements)
7. If no signatures and no ForwardFileSpec: `tier = -1` (skip — insufficient structural data)

### REQ-MI-101: Signature Parsing

Parse `api_signatures` strings from `ParsedFeature` into synthetic `ForwardElementSpec` entries:

**Supported formats** (from plan ingestion PARSE prompt):

- `"def function_name(param: type) -> return_type"` → `FUNCTION`
- `"async def function_name(param: type) -> return_type"` → `ASYNC_FUNCTION`
- `"Class ClassName(BaseClass)"` → `CLASS`
- `"def ClassName.method_name(self, param: type) -> return_type"` → `METHOD` with `parent_class`

**Normalization before parsing:** Because the supported formats are not always valid Python statements, normalize signature strings before calling `ast.parse()`:

- Rewrite `Class Foo(Base)` → `class Foo(Base): pass`
- Rewrite `def Foo.bar(self, x) -> y` → `def bar(self, x) -> y: pass` and set `parent_class="Foo"`
- Ensure bare `def ...` signatures end with `: pass`
- Strip surrounding backticks or quotes if present

**Implementation:** Reuse Python's `ast.parse()` to parse the normalized signature strings into AST nodes, then map to `ForwardElementSpec` fields. This is the same approach `forward_manifest_extractor.py` uses for source code extraction.

**Failure handling:** If a signature string doesn't parse, log DEBUG and exclude it from the synthetic spec. Never fail the task — partial specs are still useful.

### REQ-MI-102: Enrichment Route Report

After classification, emit an `EnrichmentRouteReport`:

```python
@dataclass
class EnrichmentRouteReport:
    total_tasks: int
    already_enriched: int          # tier = -1, already has code examples
    tier_0_count: int              # DFA-renderable
    tier_1_count: int              # Template-renderable
    tier_2_count: int              # Ollama-viable
    skip_count: int                # tier = -1, insufficient data
    routes: list[EnrichmentRoute]  # Per-task detail
    estimated_ollama_time_s: float # tier_2_count * avg_inference_time
```

This report is diagnostic-only in Phase 1. It shows what Phases 2 and 3 would do, enabling validation before any generation runs.

### REQ-MI-103: Forward Manifest Availability

Micro-Ingest runs after ForwardManifest construction inside `_phase_emit()`. The manifest is typically available (FLCM extraction succeeds when `ParsedFeature` data exists), but Micro-Ingest SHALL degrade gracefully when it is absent:

| Scenario | Tier 0 Available? | Tier 1/2 Available? |
|----------|:-:|:-:|
| ForwardManifest exists with matching file_spec | Yes (real spec — highest fidelity) | Yes |
| ForwardManifest exists but no matching file_spec | Falls back to synthetic | Yes |
| ForwardManifest absent (FLCM failed), api_signatures present | Yes (synthetic) | Yes |
| ForwardManifest absent, api_signatures absent | No | No (skip) |

When no structural data exists for a task, Micro-Ingest skips it entirely. This is correct — without signatures or specs, any generated code would be hallucinated.

**Run-019 projection:** All 6 features had ForwardManifest data via FLCM extraction. 5/6 would use real specs (Tier 0 primary path). The synthetic fallback is for edge cases where FLCM extraction fails or a task's target file isn't in the manifest.

### REQ-MI-104: Integration Point

Phase 1 SHALL be callable as:

```python
from startd8.workflows.builtin.plan_ingestion_micro_ingest import classify_enrichment_routes

report = classify_enrichment_routes(
    tasks=tasks,                    # Post-Option-A task list
    features=parsed_plan.features,  # ParsedFeature index
    forward_manifest=forward_manifest,  # Available from FLCM extraction earlier in _phase_emit()
)
```

Integrated into `_phase_emit()` in `plan_ingestion_workflow.py`, after `enrich_tasks_deterministic()` (line ~4365) and before `_build_seed_artifacts()`. The `forward_manifest` variable is in scope at this point — it was constructed at lines 4107-4150.

```python
if _kc.micro_ingest_enabled:
    _mi_report = classify_enrichment_routes(tasks, features, forward_manifest)
    # Phase 1: diagnostic only — log report, persist to diagnostics
    # Phases 2-3: generate and append code examples
```

---

## 4. Phase 2 — Deterministic Stub Assembly (REQ-MI-2xx)

**Goal:** For Tier 0 and Tier 1 tasks, render code examples without any LLM calls. This is the highest-value, zero-cost enrichment.

### REQ-MI-200: DFA Stub Rendering for Enrichment

For Tier 0 tasks (have `ForwardFileSpec` or synthetic spec from parsed signatures), render a code example using `DeterministicFileAssembler.render_file()`:

**Output:** A fenced Python code block appended to `task["config"]["task_description"]`:

```
## Code Example (from forward manifest)
```python
from __future__ import annotations

from pathlib import Path


class EmailService(demo_pb2_grpc.EmailServiceServicer):
    """gRPC service implementation for email operations."""

    def SendOrderConfirmation(self, request, context) -> demo_pb2.Empty:
        raise NotImplementedError

    def _build_html_body(self, order: demo_pb2.OrderResult) -> str:
        raise NotImplementedError
` ``
```

**Key difference from SCAFFOLD DFA:** The assembler here renders to a *string* for description embedding, not to disk. Reuse `DeterministicFileAssembler.render_file()` but do not call `materialize()`.

### REQ-MI-201: Synthetic ForwardFileSpec Construction

When `ForwardManifest` is unavailable but `ParsedFeature.api_signatures` exist, construct a synthetic `ForwardFileSpec`:

```python
def build_synthetic_file_spec(
    target_file: str,
    api_signatures: list[str],
    runtime_dependencies: list[str],
    protocol: str,
) -> Optional[ForwardFileSpec]:
```

**Steps:**

1. Parse each signature string via `ast.parse()` → extract name, params, return type, async flag
2. Infer `parent_class` from dotted method signatures (`"def EmailService.Send(...)"` → `parent_class="EmailService"`)
3. Group methods under their parent class
4. Infer imports from `runtime_dependencies` and `protocol`:
   - `protocol="grpc"` → `import grpc`, `from concurrent import futures`
   - `runtime_dependencies=["flask"]` → `from flask import Flask`
5. Build `ForwardFileSpec(file=target_file, elements=[...], imports=[...], dependencies=...)`

**Failure:** If zero signatures parse successfully, return `None` (task falls through to Tier 1/2 or skip).

### REQ-MI-202: Template Rendering for Enrichment

For Tier 1 elements that match Micro Prime templates (`config_constant`, `property_getter`, `dunder_method`, `dataclass_boilerplate`, etc.), render via `TemplateRegistry.try_template_match()`:

**Output:** Append a code block showing the template-rendered body:

```
## Code Example (from template: dunder_method)
```python
def __init__(self, host: str, port: int = 8080) -> None:
    self.host = host
    self.port = port
` ``
```

**Note:** Template output is body-only (per render contract in `templates.py`). For enrichment, wrap in the full `def` signature to provide a complete example.

### REQ-MI-203: Mixed Rendering

A single task may have elements at different tiers. The enrichment pass SHALL combine them:

- Tier 0 elements → DFA stub (full file skeleton)
- Tier 1 elements → Template body (wrapped in signature)
- Tier 2 elements → Deferred to Phase 3

If a task has both Tier 0 and Tier 1 elements, prefer the Tier 0 rendering (it includes the full file context). Only use Tier 1 alone for tasks where DFA rendering is unavailable.

**Hybrid fallback (Tier 0 + Tier 1):** If Tier 0 is available but exceeds the line budget and there are template matches for elements omitted by truncation, produce a hybrid code example:

- Truncate the DFA skeleton to leave room for template snippets (see REQ-MI-204)
- Append a short "Template Snippets" section with as many template-rendered elements as fit
- Keep total output within the line budget

### REQ-MI-204: Rendering Budget

Code examples appended to task descriptions SHALL be capped at **80 lines** per task. If the DFA rendering exceeds 80 lines:

1. Render the full skeleton
2. If template matches exist, reserve a snippet budget: `min(20, max(8, micro_ingest_max_lines // 4))` lines
3. Truncate the DFA skeleton to `micro_ingest_max_lines - snippet_budget` lines
4. Append a "Template Snippets" section (Tier 1) using the reserved lines
5. If no template matches exist, truncate to 80 lines directly
6. Append `# ... (truncated after 80 lines; see forward manifest for full spec)`

This prevents description bloat while still providing the structural anchor.

### REQ-MI-205: No-Clobber Extension

Follow TDE-106 no-clobber rule:

- If task description already contains a fenced code block → skip rendering
- If synthetic spec already computed for this task → reuse cached result (do not recompute)
- Log DEBUG when skipping

---

## 5. Phase 3 — Ollama Code Example Generation (REQ-MI-3xx)

**Goal:** For Tier 2 tasks (have signature data but don't match templates), use Ollama to generate a code example via the proven SIMPLE pipeline.

### REQ-MI-300: Per-Element Ollama Generation

For each Tier 2 element in a task, call the Micro Prime SIMPLE generation pipeline:

```python
# Reuse existing _handle_simple() from MicroPrimeEngine
result = engine._handle_simple(
    element=synthetic_element_spec,
    file_spec=synthetic_file_spec,
    skeleton=dfa_skeleton,           # Use DFA output as skeleton context
    contracts=contracts,
    file_path=target_file,
    reasoning="micro_ingest_enrichment",
    task_description=task_description,
)
```

**If success:** Append the generated code as a fenced block in the task description.
**If failure:** Skip — no cloud escalation. Log at DEBUG.

### REQ-MI-301: Skeleton Context

When calling `_handle_simple()`, provide the DFA-rendered skeleton as context. This gives Ollama:

- Import context (what packages are available)
- Class hierarchy (what class the method belongs to)
- Sibling signatures (what other methods exist)

This mirrors how IMPLEMENT uses DFA skeletons — the same pattern that lifted SIMPLE success from 70% to 90%.

### REQ-MI-302: Generation Constraints

Ollama generation for enrichment SHALL use:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `temperature` | 0.1 | Same as production — deterministic output |
| `max_tokens` | 512 | Enrichment stubs don't need full implementations |
| `input_token_budget` | 1024 | Proven Ollama sweet spot |
| `local_max_attempts` | 1 | Single attempt — enrichment is advisory, not critical |
| `repair_enabled` | True | Syntax repair improves output quality |
| `semantic_verification_enabled` | False | Overkill for enrichment stubs |

### REQ-MI-303: Skip Signals

Reuse `moderate_ollama_whole_skip_signals` from `MicroPrimeConfig`:

```python
skip_signals = {"external_api", "orchestrator", "app_server_instance"}
```

Elements with these signals have **0% Ollama success rate** (Kaizen data across 19 runs). Skip immediately and log reason.

### REQ-MI-304: Time Budget

Enrichment SHALL enforce a total time budget:

- Default: `30 seconds` total for all Tier 2 elements
- Per-element timeout: `10 seconds` (covers generation + repair)
- If budget exhausted mid-task: skip remaining elements, log WARNING

This prevents enrichment from dominating pipeline latency when many tasks need Tier 2 generation.

### REQ-MI-305: Engine Reuse Strategy

Micro-Ingest SHALL accept an optional `MicroPrimeEngine` instance passed from the workflow. If unavailable, skip all Tier 2 enrichment (degrade gracefully to Tier 0+1 only).

**Rationale:** `_handle_simple()` depends on engine state (template registry, circuit breaker, OTel metrics, completed element history). Extracting it as a standalone function would require duplicating this setup. Passing the engine instance is cleaner and avoids hidden coupling.

**Workflow instantiation:** The engine is created only when `tier_2_enabled=True`:

```python
_engine = None
if _kc.micro_ingest_tier_2_enabled:
    try:
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import MicroPrimeConfig
        _engine = MicroPrimeEngine(MicroPrimeConfig(
            local_max_attempts=1, repair_enabled=True,
            semantic_verification_enabled=False, max_tokens=512,
        ))
    except Exception as exc:
        logger.warning("micro_ingest: engine init failed: %s — tier_2 disabled", exc)
```

**Graceful degradation:** If Ollama is not running, engine init fails, and Tier 2 is silently disabled. Tier 0+1 still run — covering 60-80% of the code example gap at zero cost.

---

## 6. Configuration (REQ-MI-4xx)

### REQ-MI-400: Kaizen Config Extension

Extend `PlanIngestionKaizenConfig`:

```python
@dataclass
class PlanIngestionKaizenConfig:
    # ... existing fields ...

    # Micro-Ingest (Phases 1-3)
    micro_ingest_enabled: bool = True          # Master switch
    micro_ingest_tier_0_enabled: bool = True   # DFA stub rendering
    micro_ingest_tier_1_enabled: bool = True   # Template rendering
    micro_ingest_tier_2_enabled: bool = False  # Ollama generation (opt-in, ships later)
    micro_ingest_max_lines: int = 80           # Max code example lines per task
    micro_ingest_ollama_timeout_s: int = 30    # Total Ollama time budget
    micro_ingest_ollama_per_element_s: int = 10  # Per-element timeout
```

**Note:** `tier_2_enabled` defaults to `False` — Tier 2 ships in Phase 3 and must be explicitly opted-in until validated by Kaizen runs.

### REQ-MI-401: Config-Driven Activation (No CLI Flag)

Micro-Ingest activation is controlled entirely via `PlanIngestionKaizenConfig`. No dedicated CLI flag is added — this avoids CLI surface area bloat for a feature that should be transparent:

- **Default on:** `micro_ingest_enabled = True` — runs automatically when data is available
- **Graceful fail:** If any tier's dependencies are unavailable (e.g., Ollama not running for Tier 2, ForwardManifest absent for Tier 0), that tier is silently skipped. The pipeline never errors due to Micro-Ingest.
- **Disable via config:** Set `micro_ingest_enabled: false` in `kaizen-config.json` to suppress entirely
- **Per-tier disable:** Individual tiers can be toggled via config without touching the master switch

This follows the same pattern as Option A enrichment — always runs, no CLI flag, config-only override.

### REQ-MI-402: Per-Tier Disable

Each tier is independently disableable. This enables:

- `tier_0_enabled=True, tier_1_enabled=False, tier_2_enabled=False` → DFA only (safest)
- `tier_0_enabled=True, tier_1_enabled=True, tier_2_enabled=False` → deterministic only (no Ollama)
- All three enabled → full pipeline

---

## 7. Observability (REQ-MI-5xx)

### REQ-MI-500: Micro-Ingest Diagnostic Block

The diagnostic report SHALL include a `micro_ingest` section:

```json
{
  "micro_ingest": {
    "enabled": true,
    "route_report": {
      "total_tasks": 6,
      "already_enriched": 1,
      "tier_0_count": 3,
      "tier_1_count": 1,
      "tier_2_count": 1,
      "skip_count": 0
    },
    "generation": {
      "tier_0_rendered": 3,
      "tier_0_truncated": 0,
      "tier_1_rendered": 1,
      "tier_2_attempted": 1,
      "tier_2_succeeded": 1,
      "tier_2_failed": 0,
      "tier_2_skipped_signals": 0,
      "tier_2_skipped_timeout": 0,
      "total_time_ms": 4200,
      "ollama_time_ms": 4100
    },
    "code_examples_added": 5
  }
}
```

### REQ-MI-501: Kaizen Prompt Capture

When Tier 2 generation runs and kaizen prompt capture is active, persist:

- `kaizen-prompts/micro_ingest_{task_id}_prompt.txt`
- `kaizen-prompts/micro_ingest_{task_id}_response.txt`

Follows existing `persist_prompt_response()` pattern.

### REQ-MI-502: Density Score Impact

Micro-Ingest runs before `compute_seed_quality()`, so code examples added here automatically improve the seed quality score's richness component. No changes to scoring needed.

---

## 8. Status Dashboard

| Req ID | Description | Status | Phase |
|--------|-------------|--------|-------|
| **Phase 1 — Per-Task Decomposition** | | | |
| REQ-MI-100 | Task enrichment classifier | PLANNED | 1 |
| REQ-MI-101 | Signature parsing | PLANNED | 1 |
| REQ-MI-102 | Enrichment route report | PLANNED | 1 |
| REQ-MI-103 | Forward manifest availability | PLANNED | 1 |
| REQ-MI-104 | Integration point | PLANNED | 1 |
| **Phase 2 — Deterministic Stub Assembly** | | | |
| REQ-MI-200 | DFA stub rendering for enrichment | PLANNED | 2 |
| REQ-MI-201 | Synthetic ForwardFileSpec construction | PLANNED | 2 |
| REQ-MI-202 | Template rendering for enrichment | PLANNED | 2 |
| REQ-MI-203 | Mixed rendering | PLANNED | 2 |
| REQ-MI-204 | Rendering budget (80 lines) | PLANNED | 2 |
| REQ-MI-205 | No-clobber extension | PLANNED | 2 |
| **Phase 3 — Ollama Code Example Generation** | | | |
| REQ-MI-300 | Per-element Ollama generation | PLANNED | 3 |
| REQ-MI-301 | Skeleton context | PLANNED | 3 |
| REQ-MI-302 | Generation constraints | PLANNED | 3 |
| REQ-MI-303 | Skip signals | PLANNED | 3 |
| REQ-MI-304 | Time budget | PLANNED | 3 |
| REQ-MI-305 | Engine reuse strategy | PLANNED | 3 |
| **Configuration** | | | |
| REQ-MI-400 | Kaizen config extension | PLANNED | 1 |
| REQ-MI-401 | Config-driven activation (no CLI flag) | PLANNED | 1 |
| REQ-MI-402 | Per-tier disable | PLANNED | 1 |
| **Observability** | | | |
| REQ-MI-500 | Micro-Ingest diagnostic block | PLANNED | 1 |
| REQ-MI-501 | Kaizen prompt capture | PLANNED | 3 |
| REQ-MI-502 | Density score impact | PLANNED | 2 |

---

## 9. Traceability Matrix

### Run-019 Findings → Micro-Ingest

| Run-019 Finding | Micro-Ingest Req | How It Helps |
|----------------|-----------------|-------------|
| 0/6 code examples | MI-200, MI-202, MI-300 | Tier 0/1/2 generate code blocks for 4-6/6 tasks |
| Seed quality 0.50 | MI-502 | Code examples boost richness score → 0.65-0.75 |
| REFINE doesn't modify task fields | All MI-1xx/2xx/3xx | Micro-Ingest directly modifies task descriptions |
| `draft_word_count` strongest correlate (ρ=+0.280) | MI-200 | DFA stubs add 20-80 lines → richer drafts downstream |

### Kaizen Model Capability Data → Tier Design

| Evidence | Source | Tier Design Decision |
|----------|--------|---------------------|
| SIMPLE tier 90% success | Run-017, Run-019 | Tier 2 uses SIMPLE pipeline |
| TRIVIAL tier 100% success | Run-017 | Tier 1 uses template registry |
| DFA produces valid skeletons | file_assembler.py (47 tests) | Tier 0 reuses DFA |
| `external_api` elements 0% Ollama success | Run-005, Run-017 | MI-303 skip signals |
| `bare_statement_wrap` 9-26% repair rate | Run-017, Run-019 | MI-302 enables repair |
| 1024-token input budget sweet spot | MicroPrimeConfig | MI-302 budget constraint |
| qwen2.5-coder can't produce reliable JSON | System prompt analysis | No JSON output in any tier |

### Existing Infrastructure Reuse

| Component | Reused By | How |
|-----------|----------|-----|
| `DeterministicFileAssembler.render_file()` | MI-200, MI-201 | Renders ForwardFileSpec → Python source |
| `TemplateRegistry.try_template_match()` | MI-202 | Matches elements to deterministic templates |
| `MicroPrimeEngine._handle_simple()` | MI-300 | Full SIMPLE generation pipeline (template → Ollama → repair) |
| `ast.parse()` signature extraction | MI-101 | Parse `api_signatures` strings to ForwardElementSpec |
| `forward_manifest_extractor.py` | MI-101 | Pattern for AST-based element extraction |
| `classify_tier()` | MI-100 | Determines if element is SIMPLE-viable for Tier 2 |
| `moderate_ollama_whole_skip_signals` | MI-303 | Proven skip list for Ollama-hostile elements |
| `EnrichmentDiagnostic` | MI-500 | Extends existing diagnostic infrastructure |

---

## 10. Verification Strategy

### Phase 1 Tests

| Test | What | Type |
|------|------|------|
| `test_classifier_tier_0_forward_spec` | Task with ForwardFileSpec → tier=0 | Unit |
| `test_classifier_tier_0_synthetic` | Task with parseable api_signatures, no ForwardSpec → tier=0 | Unit |
| `test_classifier_tier_1_template_match` | Task with dunder method signature → tier=1 | Unit |
| `test_classifier_tier_2_simple_viable` | Task with SIMPLE-eligible signature → tier=2 | Unit |
| `test_classifier_skip_no_data` | Task with no signatures, no ForwardSpec → tier=-1 | Unit |
| `test_classifier_skip_already_enriched` | Task with existing code block → tier=-1 | Unit |
| `test_signature_parsing_function` | `"def foo(x: int) -> str"` → ForwardElementSpec | Unit |
| `test_signature_parsing_method` | `"def Cls.method(self, x)"` → METHOD with parent_class | Unit |
| `test_signature_parsing_class` | `"Class Foo(Base)"` → CLASS with bases | Unit |
| `test_signature_parsing_failure` | `"not a signature"` → None (skip, no error) | Unit |
| `test_route_report_counts` | 6 tasks → correct tier distribution | Unit |

### Phase 2 Tests

| Test | What | Type |
|------|------|------|
| `test_dfa_rendering_appended` | Tier 0 task → code block in description | Unit |
| `test_dfa_rendering_truncated` | 100-line skeleton → truncated to 80 | Unit |
| `test_template_rendering_wrapped` | Tier 1 dunder → code block with signature wrapper | Unit |
| `test_synthetic_spec_from_signatures` | api_signatures → valid ForwardFileSpec | Unit |
| `test_synthetic_spec_grpc_imports` | protocol=grpc → grpc imports inferred | Unit |
| `test_no_clobber_existing_code` | Task with code block → not modified | Unit |
| `test_mixed_tier_prefers_dfa` | Task with Tier 0 + Tier 1 elements → DFA used | Unit |
| `test_rendering_without_manifest` | No ForwardManifest, has signatures → synthetic spec works | Unit |

### Phase 3 Tests

| Test | What | Type |
|------|------|------|
| `test_ollama_generation_success` | SIMPLE element → code appended | Unit |
| `test_ollama_generation_failure` | Ollama fails → skip, no error | Unit |
| `test_skip_signals_respected` | external_api element → skipped | Unit |
| `test_time_budget_enforced` | 5 slow elements, 30s budget → partial completion | Unit |
| `test_tier_2_disabled_by_default` | Default config → no Ollama calls | Unit |
| `test_skeleton_context_provided` | Ollama prompt includes DFA skeleton | Unit |

### Integration Tests

| Test | What | Type |
|------|------|------|
| `test_density_score_with_micro_ingest` | Seed quality score higher with micro-ingest | Integration |
| `test_online_boutique_enrichment` | Run-019 plan → code examples on 4+ tasks | Integration |
| `test_phase_1_only_no_generation` | tier_0/1/2 all disabled → report only | Integration |

---

## 11. Cross-References

| Document | Relationship |
|----------|-------------|
| [TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md](./TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md) | Parent: Option A runs first; Micro-Ingest extends density further |
| [LLM_ENRICHMENT_REQUIREMENTS.md](./LLM_ENRICHMENT_REQUIREMENTS.md) | Superseded: cloud Option B retained as reference; Micro-Ingest is local-first replacement |
| [DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md](../scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md) | Reuse: DFA rendering for Tier 0 |
| [KAIZEN_INVESTIGATION_RUN019](../kaizen/KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md) | Trigger: §9 seed density gap, §10 REFINE architectural gap |
| [KAIZEN_INVESTIGATION_RUN017](../kaizen/KAIZEN_INVESTIGATION_RUN017_ONLINE_BOUTIQUE.md) | Evidence: SIMPLE 90% success rate, MODERATE 71%, skip signals |
| [REQ-MP-1xx_MODEL_TUNING.md](../micro-prime/REQ-MP-1xx_MODEL_TUNING.md) | Model capability: qwen2.5-coder 7B constraints and tuning |
| `src/startd8/utils/file_assembler.py` | Reuse: `DeterministicFileAssembler.render_file()` |
| `src/startd8/micro_prime/templates.py` | Reuse: `TemplateRegistry.try_template_match()` |
| `src/startd8/micro_prime/engine.py` | Reuse: `_handle_simple()` pipeline |
| `src/startd8/complexity/classifier.py` | Reuse: `classify_tier()` for SIMPLE viability check |
| SDK Lessons: Leg 13 #33 | Requirements layer gap — data injection ≠ prompt consumption |
| SDK Lessons: Leg 13 #40 | 12-point pipeline field threading checklist |

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

- **Risks**: 4 suggestions applied (R1-S3, R1-S5, R1-S6, R1-S8)
- **Ops**: 3 suggestions applied (R1-S7, R1-S9, R1-S10)
- **Data**: 3 suggestions applied (R2-S1, R2-S2, R2-S3)
- **Validation**: 3 suggestions applied (R2-S4, R2-S5, R2-S6)
- **Security**: 3 suggestions applied (R2-S7, R2-S8, R2-S9)
- **Architecture**: 3 suggestions applied (R1-S1, R1-S2, R2-S10)

### Areas Needing Further Review

- **Interfaces**: 1/3 suggestions accepted (need 2 more) — R1-S4 applied

> **Note:** Area counts reflect accepted S-prefix suggestions only. See Appendix A for full detail.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Add explicit tie-breaking rule when multiple ForwardFileSpecs match a task's target_files | Gemini 2.5 Pro (antigravity) | REQ-MI-100 specifies "use the first match by manifest order" — accepted as written; clarify that "manifest order" == insertion order of `ForwardManifest.file_specs` list | 2026-03-10 |
| R1-S2 | Document the fallback ordering when both real ForwardFileSpec and parseable api_signatures exist | Gemini 2.5 Pro (antigravity) | REQ-MI-100 rules 2 and 3 are evaluated sequentially; rule 2 wins. Accepted — add explicit note in §3 that "real spec beats synthetic" | 2026-03-10 |
| R1-S3 | Add a maximum retry budget for the Tier 2 per-element timeout to avoid silent partial failures | Gemini 2.5 Pro (antigravity) | REQ-MI-304 specifies 10s per-element and 30s total but has no partial-completion reporting. Accepted — add field `tier_2_skipped_timeout` to diagnostic report (already present in REQ-MI-500 example JSON — confirm it is wired) | 2026-03-10 |
| R1-S4 | Specify the exact function signature for `classify_enrichment_routes` including return type | Gemini 2.5 Pro (antigravity) | REQ-MI-104 shows a call site but omits the full module-level function signature with type annotations. Accepted — add typed signature to REQ-MI-104 | 2026-03-10 |
| R1-S5 | Add a requirement for what happens when `DeterministicFileAssembler.render_file()` raises an exception during Tier 0 enrichment | Gemini 2.5 Pro (antigravity) | REQ-MI-200 says "render code example" but has no error contract. Accepted — add: on exception, log WARNING and fall through to Tier 1; never propagate to caller | 2026-03-10 |
| R1-S6 | Clarify the no-clobber check in REQ-MI-205: does it check for *any* fenced code block or specifically a Python fenced block? | Gemini 2.5 Pro (antigravity) | REQ-MI-100 rule 1 says "fenced code block (```)" with no language qualifier. Accepted — specify that any fenced block (regardless of language tag) triggers the skip, matching TDE-106 intent | 2026-03-10 |
| R1-S7 | Add the `estimated_ollama_time_s` field computation formula to REQ-MI-102 | Gemini 2.5 Pro (antigravity) | The field is declared in `EnrichmentRouteReport` but the formula (`tier_2_count * avg_inference_time`) is only in prose. Accepted — add `avg_inference_time = 6.0` seconds as the default constant (midpoint of 4-8s range) | 2026-03-10 |
| R1-S8 | Specify failure behavior when the `MicroPrimeEngine` instance passed to Tier 2 has a tripped circuit breaker | Gemini 2.5 Pro (antigravity) | REQ-MI-305 describes engine reuse but the engine's circuit breaker state is inherited. If tripped, Ollama calls fail immediately. Accepted — add: if circuit breaker is open at Tier 2 entry, skip all Tier 2 elements and log WARNING | 2026-03-10 |
| R1-S9 | Add the `micro_ingest` diagnostic block field `estimated_ollama_time_s` from EnrichmentRouteReport to the REQ-MI-500 JSON schema | Gemini 2.5 Pro (antigravity) | REQ-MI-500 shows the diagnostic JSON but omits `estimated_ollama_time_s` that REQ-MI-102 declares. Accepted — add this field under `route_report` in the JSON schema | 2026-03-10 |
| R1-S10 | Specify the Kaizen prompt capture file naming when `task_id` contains path separators or special characters | Gemini 2.5 Pro (antigravity) | REQ-MI-501 uses `{task_id}` directly in filenames. Accepted — add: sanitize `task_id` by replacing `/`, `\`, and `:` with `_` before constructing the filename | 2026-03-10 |
| R2-S1 | Define the data model for a synthetic `ForwardElementSpec` built from a parsed method signature when `parent_class` is inferred | Gemini 2.5 Pro (antigravity) | REQ-MI-201 describes the steps but never specifies what fields a synthetic `ForwardElementSpec` must have vs. a real one (e.g., is `docstring` required? are `contracts` empty or absent?). Accepted — add a field table to REQ-MI-201 specifying required vs. optional fields for synthetic specs | 2026-03-10 |
| R2-S2 | Specify the import inference rules for `runtime_dependencies` exhaustively — particularly what to do when a dependency string is a package name with no obvious import pattern | Gemini 2.5 Pro (antigravity) | REQ-MI-201 step 4 says `runtime_dependencies=["flask"]` → `from flask import Flask` but this assumes the import is camel-cased. Many packages don't follow this (e.g., `"google-cloud-storage"` → `from google.cloud import storage`). Accepted — scope the rule to well-known protocols and note that unknown dependencies are passed as bare `import {dep}` | 2026-03-10 |
| R2-S3 | Add the caching contract for synthetic `ForwardFileSpec` to the data model — when is a cached spec invalidated? | Gemini 2.5 Pro (antigravity) | REQ-MI-205 says "reuse cached result (do not recompute)" but there is no data model entry specifying the cache key or invalidation rule. If the same target_file appears in two tasks with different api_signatures, should the cache be shared? Accepted — add: cache key = `(target_file, frozenset(api_signatures))`; two tasks with the same target_file but different signatures get independent synthetic specs | 2026-03-10 |
| R2-S4 | Add acceptance criteria for all 11 Phase 1 test cases listed in §10 — each test currently has a name but no explicit pass/fail condition | Gemini 2.5 Pro (antigravity) | §10 (Verification Strategy) lists tests but each row says only "what" (e.g., `test_classifier_tier_0_forward_spec`) not what the assertion is. An implementer can write a passing test that doesn't actually validate the requirement. Accepted — add an Assertion column to the Phase 1/2/3 test tables | 2026-03-10 |
| R2-S5 | Add a required test for the hybrid Tier 0+Tier 1 rendering path introduced in REQ-MI-203/204 | Gemini 2.5 Pro (antigravity) | §10 Phase 2 Tests do not include a test for the hybrid path (`test_dfa_hybrid_with_template_snippets`). This path is now code-level in the implementation plan but unverified by the requirements test table. Accepted — add row to Phase 2 test table | 2026-03-10 |
| R2-S6 | Add a required integration test that verifies the REQ-MI-500 diagnostic JSON schema is complete (all declared fields present) | Gemini 2.5 Pro (antigravity) | §10 integration tests don't include a schema validation test. Given R1 found that `estimated_ollama_time_s` was missing from the example JSON, a schema-completeness test is the systemic fix. Accepted — add `test_diagnostic_json_schema_complete` to integration test table | 2026-03-10 |
| R2-S7 | Specify the threat model for Kaizen prompt capture — who has read access to `kaizen-prompts/` and what data it may contain | Gemini 2.5 Pro (antigravity) | REQ-MI-501 writes `micro_ingest_{task_id}_prompt.txt` and `_response.txt` to disk. The prompt includes task descriptions (which may contain proprietary repo content). No access control or retention policy is specified. Accepted — add: files are written with `mode=0o600` (owner-read only); same policy as existing Kaizen prompt capture | 2026-03-10 |
| R2-S8 | Specify that `task_id` sanitization (R1-S10) must also prevent path traversal via `..` sequences | Gemini 2.5 Pro (antigravity) | R1-S10 covers `/`, `\`, `:`. A `task_id` like `../../secrets/key` would still traverse outside the kaizen-prompts directory after only stripping slashes. Accepted — add: strip leading `./` and `../` sequences; use `pathlib.Path(sanitized).name` to ensure only the base filename component is used | 2026-03-10 |
| R2-S9 | Specify that Ollama-generated code blocks (Tier 2) must not be appended if they fail AST validation — currently only Tier 0 synthetic specs are AST-validated | Gemini 2.5 Pro (antigravity) | REQ-MI-300 says "if success → append code block" but does not require validating the code's syntax before appending. A syntactically broken code block in a task description would corrupt the hint rather than help. REQ-MI-200 does AST-validate Tier 0 output. Accepted — add: Tier 2 output SHALL be validated via `ast.parse()` before appending; on SyntaxError, skip and log DEBUG | 2026-03-10 |
| R2-S10 | Add a requirement specifying what `elements: list[str]` contains in `EnrichmentRoute` — FQNs, simple names, or signatures? | Gemini 2.5 Pro (antigravity) | REQ-MI-100 declares `elements: list[str]` as "Element FQNs that would be generated" but FQN format is undefined. In the codebase, elements are sometimes referenced by simple name (`"SendOrderConfirmation"`), sometimes by dotted class path (`"EmailService.SendOrderConfirmation"`). Accepted — specify: `elements` contains dotted names in the format `"ClassName.method_name"` for methods and plain `"function_name"` for module-level functions | 2026-03-10 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) | | | | |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: Gemini 2.5 Pro (antigravity)
- **Date**: 2026-03-10 14:49:00 UTC
- **Scope**: Full architectural review — initial pass across all 7 areas (first encounter, all areas at 0/3)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add explicit tie-breaking rule when multiple `ForwardFileSpec` entries match a task's `target_files` | REQ-MI-100 rule 2 says "use the first match by manifest order" but does not define what "manifest order" means (insertion order? alphabetical? construction-time order?). An implementer reading this cold could make different choices. | §3 REQ-MI-100 classification rules, rule 2 | Unit test with two matching specs in different insertion orders; verify first-inserted spec is used |
| R1-S2 | Architecture | high | Document the priority ordering when a task has *both* a real `ForwardFileSpec` (from FLCM extraction) *and* parseable `api_signatures` | REQ-MI-100 rules 2 and 3 are sequential, implying rule 2 wins. But this isn't stated — an implementer could reasonably try to merge both sources. The "real spec beats synthetic" invariant should be explicit. | §3 REQ-MI-100, §2.2 Per-Task Decision Tree | Unit test: task with real ForwardFileSpec + api_signatures → confirm real spec is used, synthetic never constructed |
| R1-S3 | Risks | high | Add a requirement for exposing per-element timeout failures in the diagnostic output | REQ-MI-304 defines the time budget but `EnrichmentRouteReport` has no field to track how many elements timed out individually vs. how many completed. The `tier_2_skipped_timeout` field appears in the MI-500 JSON schema (generation block) but is not defined in `EnrichmentRouteReport` or REQ-MI-304. Wire it. | §5 REQ-MI-304, §6 REQ-MI-500 | Inject a slow mock element that exceeds 10s; verify `tier_2_skipped_timeout` increments |
| R1-S4 | Interfaces | medium | Specify the full typed function signature for `classify_enrichment_routes` at REQ-MI-104 | The call site is shown but the module-level function definition is missing type annotations and return type (`-> EnrichmentRouteReport`). Without this, implementers may place the function inline or choose a different signature, breaking the integration contract. | §3 REQ-MI-104 | Import and call the function with typed args; mypy --strict passes |
| R1-S5 | Risks | high | Add an error contract for `DeterministicFileAssembler.render_file()` failures during Tier 0 enrichment | REQ-MI-200 says "render a code example using `DeterministicFileAssembler.render_file()`" but specifies no failure behavior. If `render_file()` raises (e.g., malformed spec), the exception propagates up and violates the "fail-safe" constraint in §1.4. | §4 REQ-MI-200 | Unit test: inject a ForwardFileSpec that causes render_file to raise; verify task is skipped with WARNING log, no exception escapes |
| R1-S6 | Risks | medium | Clarify whether the no-clobber check in REQ-MI-205 requires a Python-tagged fenced block or any fenced block | REQ-MI-100 rule 1 says "fenced code block (` ``` `)" with no language qualifier. A task description might contain a ` ```bash ` block from Option A and still lack a Python example. Unqualified matching silently skips tasks that still need enrichment. | §3 REQ-MI-100 rule 1, §4 REQ-MI-205 | Unit test: task with ` ```bash ` block → verify behavior matches documented intent |
| R1-S7 | Ops | medium | Specify the default `avg_inference_time` constant used to compute `estimated_ollama_time_s` in `EnrichmentRouteReport` | The field is declared and the formula hinted (`tier_2_count * avg_inference_time`) but the constant value is unspecified. Implementers will pick arbitrary values, making estimates inconsistent across runs. | §3 REQ-MI-102 | Unit test: 3 tier-2 tasks → `estimated_ollama_time_s == 18.0` (using 6.0s default) |
| R1-S8 | Risks | high | Specify behavior when the inherited `MicroPrimeEngine` has a tripped circuit breaker at Tier 2 entry | REQ-MI-305 passes in an existing engine whose circuit breaker may be open from prior use in the same `_phase_emit()` run. Without an explicit check, all Tier 2 elements will be attempted, fail immediately, and consume their per-element timeout slots (up to 30s wasted). | §5 REQ-MI-305 | Unit test: pass engine with open circuit breaker → all Tier 2 elements skipped immediately, total time < 1s |
| R1-S9 | Ops | medium | Add `estimated_ollama_time_s` to the REQ-MI-500 diagnostic JSON schema (`route_report` block) | `EnrichmentRouteReport` declares this field (REQ-MI-102) but the JSON schema in REQ-MI-500 omits it from the `route_report` sub-object. This creates a gap between the data model and the emitted diagnostic, making it easy to forget to serialize it. | §7 REQ-MI-500 | Integration test: run pipeline → `micro_ingest.route_report.estimated_ollama_time_s` present in diagnostic JSON |
| R1-S10 | Ops | low | Specify filename sanitization for `task_id` in Kaizen prompt capture filenames (REQ-MI-501) | `task_id` values often include path separators or colons (e.g., `feature_a/task_3`). Using them raw in `kaizen-prompts/micro_ingest_{task_id}_prompt.txt` would create nested directories or invalid filenames on some OS. | §7 REQ-MI-501 | Unit test: task_id with `/` and `:` → verify sanitized filename contains only safe characters |

#### Review Round R2

- **Reviewer**: Gemini 2.5 Pro (antigravity)
- **Date**: 2026-03-10 15:20:00 UTC
- **Scope**: Dual-document review (with MICRO_INGEST_IMPLEMENTATION_PLAN.md) — targeting Data (0/3), Validation (0/3), Security (0/3), Architecture (2/3) per coverage gap analysis

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Data | medium | Define the field specification for synthetic `ForwardElementSpec` objects — which fields are required vs. optional when built from parsed signatures | REQ-MI-201 describes steps to build synthetic specs but never declares the field contract. A synthetic spec built with a missing required field will fail downstream DFA rendering silently. | §4 REQ-MI-201 | Unit test: build synthetic spec → DFA render succeeds; verify required fields present |
| R2-S2 | Data | medium | Scope the import inference rules for `runtime_dependencies` to well-known patterns and define fallback for unknown packages | REQ-MI-201 step 4 gives one example (`"flask"` → `from flask import Flask`) that assumes camelCase import names. Many packages don't follow this (e.g., `google-cloud-storage`). The rule is ambiguous as written. | §4 REQ-MI-201 import inference step | Unit test: `runtime_dependencies=["google-cloud-storage"]` → emits `import google.cloud.storage` not a broken camelCase form |
| R2-S3 | Data | medium | Specify the synthetic `ForwardFileSpec` cache contract — cache key and invalidation rule when the same target file appears in multiple tasks | REQ-MI-205 says "reuse cached result" but no cache key is defined. Two tasks with the same `target_files` but different `api_signatures` would incorrectly share a synthetic spec. | §4 REQ-MI-205 no-clobber section | Unit test: two tasks with same target_file, different api_signatures → each gets its own spec, no cross-contamination |
| R2-S4 | Validation | medium | Add an explicit Assertion column to the Phase 1/2/3 test tables in §10 | Each test row specifies a name and type but not what the pass condition is. An implementer can write a test that passes without actually validating the requirement. | §10 All three test tables | Review: each test row has a one-line assertion that would fail if the requirement isn't met |
| R2-S5 | Validation | medium | Add a Phase 2 test for the hybrid Tier 0+Tier 1 rendering path (REQ-MI-203/204) | §10 Phase 2 tests predate the hybrid fallback addition. No test covers: Tier 0 output exceeds 80 lines + template matches exist → truncated DFA + template snippet block appears in output. | §10 Phase 2 Tests table | `test_dfa_hybrid_with_template_snippets`: 90-line DFA + 2 template matches → output ≤ 80 lines, snippet section present |
| R2-S6 | Validation | high | Add an integration test that validates the REQ-MI-500 diagnostic JSON schema completeness | No test currently verifies that all declared fields in `EnrichmentRouteReport` and `MicroIngestDiagnostic` appear in the emitted JSON. R1 found a missing field — a schema test is the systemic fix. | §10 Integration Tests table | `test_diagnostic_json_schema_complete`: run pipeline → JSON output contains all fields declared in REQ-MI-500 example |
| R2-S7 | Security | medium | Specify that Kaizen prompt capture files are written with owner-only permissions (mode 0o600) | REQ-MI-501 prompts contain task descriptions which may include proprietary code context. No file permission specification exists. Other Kaizen capture uses 0o600 implicitly. | §7 REQ-MI-501 | Unit test: file created → `os.stat().st_mode & 0o777 == 0o600` |
| R2-S8 | Security | high | Extend the `task_id` sanitization (R1-S10) to prevent path traversal via `..` sequences | R1-S10 blocks `/`, `\`, `:` but `../../secrets/key` only needs `/` removal to produce `....secretskey` which still resolves unexpectedly. Using `pathlib.Path(sanitized).name` ensures only the final path component is used regardless of traversal attempts. | §7 REQ-MI-501 | Unit test: `task_id="../../etc/passwd"` → sanitized filename is `....etcpasswd` or similar benign form; directory is always `kaizen-prompts/` |
| R2-S9 | Security | medium | Require AST validation of Tier 2 Ollama output before appending to task descriptions | REQ-MI-300 says "if success → append code block" without requiring syntax validation. A syntactically broken code block in a task description is worse than no code block (corrupts the LLM context). REQ-MI-200 already requires this for Tier 0 — apply consistently. | §5 REQ-MI-300 | Unit test: Ollama returns syntactically invalid Python → code block not appended, DEBUG logged |
| R2-S10 | Architecture | medium | Specify the format of the `elements: list[str]` field in `EnrichmentRoute` — FQNs, simple names, or signatures? | REQ-MI-100 says "Element FQNs that would be generated" but FQN format is undefined. Downstream systems that consume `EnrichmentRoute` for display or further routing need to know: is it `"SendOrderConfirmation"`, `"EmailService.SendOrderConfirmation"`, or the full signature? | §3 REQ-MI-100 `EnrichmentRoute` dataclass | Unit test: classifier output for a method element → `elements[0] == "EmailService.SendOrderConfirmation"` |
