# Micro Prime — Requirements

> **Version:** 0.4.0
> **Status:** ACTIVE — core engine built, Prime Contractor wired (REQ-MP-700–703, 710, 711 DONE)
> **Date:** 2026-03-01
> **Scope:** Local-model code generation with manifest-guided repair, callable from both the **Artisan workflow** and the **Prime Contractor**
> **Depends on:** [DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md](../../scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md), [LOCAL_MODEL_ROUTING_EXPERIMENT.md](../../local-model-routing/LOCAL_MODEL_ROUTING_EXPERIMENT.md), [PRIME_CONTRACTOR_REQUIREMENTS.md](../../prime/PRIME_CONTRACTOR_REQUIREMENTS.md)
> **Extends:** Artisan IMPLEMENT phase (`contractors/artisan_phases/development.py`), Prime Contractor `CodeGenerator` protocol (`contractors/protocols.py`)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Design Principles](#2-design-principles)
3. [Status Dashboard](#3-status-dashboard)
4. [Layer 1 — Model Selection & Tuning (REQ-MP-1xx)](#4-layer-1--model-selection--tuning-req-mp-1xx)
5. [Layer 2 — Skeleton-First Prompting (REQ-MP-2xx)](#5-layer-2--skeleton-first-prompting-req-mp-2xx)
6. [Layer 3 — Template Registry (REQ-MP-3xx)](#6-layer-3--template-registry-req-mp-3xx)
7. [Layer 4 — Manifest-Guided Repair (REQ-MP-4xx)](#7-layer-4--manifest-guided-repair-req-mp-4xx)
8. [Layer 5 — Routing & Integration (REQ-MP-5xx)](#8-layer-5--routing--integration-req-mp-5xx)
9. [Layer 6 — Observability & Metrics (REQ-MP-6xx)](#9-layer-6--observability--metrics-req-mp-6xx)
10. [Layer 7 — Quick Wins & Acceleration (REQ-MP-7xx)](#10-layer-7--quick-wins--acceleration-req-mp-7xx)
11. [Layer 8 — Shared Complexity Router (REQ-MP-8xx)](#11-layer-8--shared-complexity-router-req-mp-8xx)
12. [Layer 9 — Moderate Decomposer (REQ-MP-9xx)](#12-layer-9--moderate-decomposer-req-mp-9xx)
13. [Data Flow](#13-data-flow)
14. [Traceability Matrix](#14-traceability-matrix)
15. [Verification Strategy](#15-verification-strategy)
16. [Related Documents](#16-related-documents)

---

## 1. Overview

### 1.1 Vision

Micro Prime is a **workflow-agnostic local-first code generation engine** that uses a tuned Ollama model to fill in SIMPLE function bodies, backed by a deterministic repair pipeline that uses the Forward Manifest as a structural specification to fix imperfect output. It introduces two new complexity tiers — TRIVIAL (zero-model, template-based) and SIMPLE (local model) — and is callable from **both** the Artisan workflow and the Prime Contractor.

**Dual-workflow architecture:**

| Workflow | Integration Point | How Micro Prime Plugs In |
|----------|------------------|--------------------------|
| **Artisan** | `ArtisanChunkExecutor` in IMPLEMENT phase | Pre-pass that fills TRIVIAL/SIMPLE elements in skeletons before cloud models process MODERATE/COMPLEX |
| **Prime Contractor** | `CodeGenerator` protocol in `PrimeContractorWorkflow.develop_feature()` | `MicroPrimeCodeGenerator` implements `CodeGenerator`, returns `GenerationResult` |

The core engine (template registry, prompt builder, local model invocation, repair pipeline, body splicing) is shared. Only the integration adapters differ.

### 1.2 Problem

The IMPLEMENT phase currently sends all code generation to cloud models regardless of complexity. For a typical microservices seed (32 elements), ~20-35% are simple enough that a local 7B model could produce them — but only if the pipeline compensates for the model's limitations:

| Limitation | Observed Impact (Round 1) | Mitigation |
|-----------|--------------------------|------------|
| Indentation mangling | 53% syntax failure rate | Skeleton-first prompting: model generates body only, spliced into known-good skeleton |
| API hallucination | 80% of syntax-valid code fails semantics | Import-based complexity gating, system prompt constraining to provided imports |
| Over-generation | ~10% produce 3-5x expected tokens | Token cap, stop sequences, manifest-guided trimming |
| Non-determinism | 47-74% variance across runs | Near-greedy sampling (temperature 0.1) |

### 1.3 Success Criteria

| Metric | Round 1 Baseline | Round 2 Actual | Target |
|--------|-----------------|----------------|--------|
| End-to-end usable code rate (SIMPLE) | 9% | **42%** | >50% |
| Syntax success rate | 47% | **100%** | >95% |
| Cloud cost reduction per seed | $0.00 | $0.034 vs $0.23 | 20-35% fewer cloud API calls |
| Latency per SIMPLE element | ~10.5s | **5.3s** | <6s |
| TRIVIAL elements (template, no model) | 0 | 0 | 5-10% of total elements |
| Callable from Artisan | N/A | N/A | Yes |
| Callable from Prime Contractor | N/A | N/A | Yes |

---

## 2. Design Principles

| Principle | Source | Application |
|-----------|--------|-------------|
| **Manifest as specification** | Forward Manifest design | The manifest is not just a planning artifact — it defines structural ground truth (signatures, imports, element boundaries) usable for repair |
| **Deterministic before probabilistic** | DeterministicFileAssembler (NFR-001) | Templates and file operations before model inference; repair before re-generation |
| **Imperfect content is recoverable** | Indentation normalization (Experiment §7.1) | Don't discard output that has fixable defects; use the manifest to repair it |
| **Escalate, don't retry blindly** | Artisan retry loop (`_execute_chunk_inner`) | Failed SIMPLE elements escalate to cloud with error context, not retried locally |
| **Zero-code model tuning** | Ollama Modelfile | Inference parameters baked into the model variant, not the SDK code path |
| **Mottainai** | FR-009 (file assembly) | Never destroy or discard work that can be salvaged |
| **Workflow-agnostic core** | Prime Contractor `CodeGenerator` protocol | Core engine is shared; only integration adapters are workflow-specific |

---

## 3. Status Dashboard

| Layer | ID Range | Total | Implemented | Partial | Planned |
|-------|----------|-------|-------------|---------|---------|
| Model Selection & Tuning | REQ-MP-1xx | 5 | 4 | 0 | 1 |
| Skeleton-First Prompting | REQ-MP-2xx | 6 | 0 | 1 | 5 |
| Template Registry | REQ-MP-3xx | 5 | 0 | 0 | 5 |
| Manifest-Guided Repair | REQ-MP-4xx | 8 | 0 | 0 | 8 |
| Routing & Integration | REQ-MP-5xx | 13 | 0 | 0 | 13 |
| Observability & Metrics | REQ-MP-6xx | 4 | 0 | 0 | 4 |
| Quick Wins & Acceleration | REQ-MP-7xx | 9 | 0 | 0 | 9 |
| Shared Complexity Router | REQ-MP-8xx | — | 0 | 0 | — |
| Moderate Decomposer | REQ-MP-9xx | 10 | 0 | 0 | 10 |
| **Total** | | **60** | **4** | **1** | **55** |

---

## 4. Layer 1 — Model Selection & Tuning (REQ-MP-1xx)

> Detailed requirements: [`REQ-MP-1xx_MODEL_TUNING.md`](./REQ-MP-1xx_MODEL_TUNING.md)

### REQ-MP-100: Base Model Selection

**Status:** implemented
**Priority:** P0

The micro-prime pipeline SHALL use `qwen2.5-coder:7b` as the base local model. Selection criteria: best-in-class code completion at 7B parameter count, strong type signature adherence, compatible resource footprint with Apple Silicon development hardware (≤8 GB RAM at inference).

**Acceptance criteria:**

- Model is available via `ollama pull qwen2.5-coder:7b`
- Inference completes in <6s per element on M1 Pro 32GB

### REQ-MP-101: Modelfile Configuration

**Status:** implemented
**Priority:** P0

Inference parameters SHALL be configured via an Ollama Modelfile that creates a named model variant (`startd8-coder`). The Modelfile SHALL set:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `temperature` | 0.1 | Near-deterministic output for reproducible results |
| `top_p` | 0.85 | Reduce tail-probability tokens (hallucinated identifiers) |
| `top_k` | 30 | Restrict candidate pool from default 40+ |
| `num_predict` | 512 | Prevent over-generation; truncation signals escalation |
| `repeat_penalty` | 1.1 | Prevent degenerate repetition loops |

**Acceptance criteria:**

- `ollama create startd8-coder -f Modelfile.startd8-coder` succeeds
- 3 consecutive runs of the same prompt produce identical output (determinism)
- Model listed via `ollama list` with expected size (~4.7 GB)

### REQ-MP-102: System Prompt

**Status:** implemented
**Priority:** P0

The Modelfile SHALL include a SYSTEM prompt that constrains the model to:

1. Output only code — no explanation, no markdown fences, no extra text
2. Use only imports shown in the prompt — do not invent APIs
3. Match the exact function signature provided
4. Prefer the shortest correct solution
5. Use 4-space indentation consistently
6. Write methods at top level (no class wrapper) — prompt provides class context separately
7. For constants/variables, output only the assignment statement
8. STOP after the single requested element

**v2 changes:** Role broadened from "function body generator" to "code generator for the startd8 pipeline" (handles constants/variables); Rule 6 aligned with top-level method rendering (FIX #3); Rules 7-8 added for constants and explicit stop.

**Acceptance criteria:**

- Model does not hallucinate imports not present in the prompt context
- Model does not emit explanatory text between code blocks
- Model generates constants as single assignment statements (not full functions)

### REQ-MP-103: Stop Sequences

**Status:** implemented
**Priority:** P1

The Modelfile SHALL define stop sequences that halt generation at natural code boundaries without killing the first output token.

**Valid stop sequences (validated in Round 2):**

- `"\nif __name__"` — common Python trailer
- `"\n# Task:"` / `"\n# Implement"` / `"\n# Define"` — prompt template echo
- `"\n\n\n"` — triple newline (generation exhausted)

**Constraints (validated empirically — see Appendix B in OLLAMA_MODEL_TUNING.md):**

- `"```"` MUST NOT be used — qwen2.5-coder starts output with ` ```python `, triggering immediate stop
- `"\ndef "` and `"\nclass "` MUST NOT be used — fires on the target function's own definition
- `"\n\ndef "` MUST NOT be used — response starts with `\n` then `\ndef`, matching immediately

**Acceptance criteria:**

- Model generates complete function bodies without premature truncation
- Model does not generate secondary functions/classes after the target element
- Zero elements truncated in Round 2 experiment (24/24 complete)

### REQ-MP-104: Model Registry Entry

**Status:** planned
**Priority:** P2
**Depends on:** REQ-MP-500

The `startd8-coder` model SHALL be registered in the SDK's model catalog (`model_catalog.py`) with appropriate defaults: `max_tokens=512`, `context_window=32768`, `provider=ollama`.

**Acceptance criteria:**

- `resolve_agent_spec("ollama:startd8-coder")` returns a valid agent
- Agent defaults match Modelfile parameters where applicable

---

## 5. Layer 2 — Skeleton-First Prompting (REQ-MP-2xx)

> Detailed requirements: [`REQ-MP-2xx_SKELETON_FIRST_PROMPTING.md`](./REQ-MP-2xx_SKELETON_FIRST_PROMPTING.md)

### REQ-MP-200: Skeleton as Prompt Context

**Status:** planned
**Priority:** P0
**Depends on:** DeterministicFileAssembler (FR-001 through FR-008)

The prompt builder SHALL use the rendered skeleton from `DeterministicFileAssembler.render_file()` as the structural context for the local model, rather than reconstructing the function stub from raw `ForwardElementSpec` fields.

**Acceptance criteria:**

- Prompt includes the complete rendered element (decorators, class wrapper, signature, docstring) from the skeleton
- The `raise NotImplementedError` line is clearly marked as the replacement target

### REQ-MP-201: Body-Only Generation

**Status:** planned
**Priority:** P0

The prompt SHALL instruct the model to generate ONLY the function body — not the `def` line, not the class wrapper, not the docstring. The prompt SHALL specify the exact indentation level expected.

**Acceptance criteria:**

- Model output does not contain `def` or `class` lines when following the prompt correctly
- Prompt specifies indent depth in spaces (e.g., "indented with 8 spaces for a class method")

### REQ-MP-202: Body Splicing

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-200

After generation, the pipeline SHALL splice the generated body into the skeleton source by replacing the `raise NotImplementedError` line at the target element's location.

**Splicing algorithm:**

1. Parse the skeleton via `ast.parse()` to locate the target element's body
2. Identify the `raise NotImplementedError` statement by AST node type and line number
3. Dedent the generated body via `textwrap.dedent()`
4. Re-indent to match the skeleton's body indentation level
5. Replace the stub line(s) with the re-indented body
6. Validate the result via `ast.parse()`

**Acceptance criteria:**

- A correctly-generated body produces a syntactically valid file after splicing
- An incorrectly-indented body is normalized to the skeleton's indent level before splicing
- The skeleton's structure (imports, other elements, `__all__`) is preserved unchanged

### REQ-MP-203: Element Extraction from Skeleton

**Status:** planned
**Priority:** P1

The prompt builder SHALL extract the target element's rendered source from the skeleton to provide as context, including:

- All decorator lines
- The class definition line (if method)
- The `def` line with full signature
- The docstring (if present)
- The `raise NotImplementedError` stub

**Acceptance criteria:**

- Extracted context matches the exact text from `render_file()` output
- Sibling methods in the same class are included as signature-only stubs (for context)

### REQ-MP-204: Graceful Degradation on Body-Included Output

**Status:** planned
**Priority:** P1

When the model returns output that includes the `def` line (ignoring the body-only instruction), the repair pipeline (Layer 4) SHALL detect and strip the redundant structure rather than failing.

**Detection:**

- Parse the output; if it contains a `FunctionDef`/`AsyncFunctionDef` node matching the target name, extract only its body statements
- If the output is unparseable, fall through to indentation normalization (REQ-MP-402)

**Acceptance criteria:**

- Model output containing `def target_name(...):` followed by body is handled without error
- The body is extracted and spliced as if the model had followed the body-only instruction

### REQ-MP-205: Few-Shot Body Examples

**Status:** partial (implemented in experiment script, not yet in SDK)
**Priority:** P2

When the same file contains elements that have already been successfully generated (by template, local model, or cloud model), the prompt builder SHALL include 1-2 completed function bodies as few-shot examples.

**Round 2 validation:** 17 of 24 elements had few-shot examples injected. Two-tier priority: same-class examples first (highest signal for methods), then same-file. Examples accumulate during sequential generation — earlier successes benefit later elements.

**Acceptance criteria:**

- Examples are drawn from the same `ForwardFileSpec` (same file, same import context)
- Examples are limited to 2 maximum to avoid prompt bloat
- Examples show only body lines at the correct indentation level

---

## 6. Layer 3 — Template Registry (REQ-MP-3xx)

> Detailed requirements: [`REQ-MP-3xx_TEMPLATE_REGISTRY.md`](./REQ-MP-3xx_TEMPLATE_REGISTRY.md)

### REQ-MP-300: Template Registry Structure

**Status:** planned
**Priority:** P1

A `CodeTemplate` registry SHALL provide deterministic code generation for TRIVIAL elements — those whose implementation can be fully derived from manifest data and contracts without any model inference.

**Registry entry structure:**

- `name: str` — template identifier (e.g., `"config_constant"`, `"flask_app_instance"`)
- `match_fn` — predicate: `(ForwardElementSpec, ForwardFileSpec, list[InterfaceContract]) → bool`
- `render_fn` — generator: `(ForwardElementSpec, ForwardFileSpec, list[InterfaceContract]) → str`

**Acceptance criteria:**

- Templates produce syntactically valid code (`ast.parse()` passes)
- Templates use only information available in the manifest and contracts (zero LLM)
- Template output is deterministic (same input → same output)

### REQ-MP-301: Config Constant Template

**Status:** planned
**Priority:** P1

Elements matching ALL of the following SHALL be generated by the `config_constant` template:

- `ForwardElementSpec.kind == CONSTANT`
- An `InterfaceContract` with `category == CONFIG_KEY` and `constant_value` is non-None

**Output:** `{name}: {type} = {constant_value}`

**Acceptance criteria:**

- String values are properly quoted
- Numeric values are rendered as literals
- Boolean values render as `True`/`False`

### REQ-MP-302: App Instance Template

**Status:** planned
**Priority:** P1

Elements matching ALL of the following SHALL be generated by the `app_instance` template:

- `ForwardElementSpec.kind == CONSTANT`
- `ForwardElementSpec.name` in `{"app", "application", "server", "api"}`
- `ForwardFileSpec.imports` contains a framework import (Flask, FastAPI, etc.)

**Output patterns:**

- Flask: `app = Flask(__name__)`
- FastAPI: `app = FastAPI()`

**Acceptance criteria:**

- Template selects the correct framework constructor based on import analysis
- Only fires when the framework import is present (no hallucination)

### REQ-MP-303: Type Alias Template

**Status:** planned
**Priority:** P2

Elements with `kind == TYPE_ALIAS` SHALL be generated deterministically when the alias definition is derivable from the element's `type_annotation` or `value_repr` fields.

**Acceptance criteria:**

- `NewType` aliases rendered as `TypeName = NewType("TypeName", BaseType)`
- Simple aliases rendered as `TypeName = BaseType`

### REQ-MP-304: Template Priority in Routing

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-500

Template matching SHALL be attempted BEFORE complexity classification. If a template matches, the element is classified as TRIVIAL and skips all model inference.

**Routing order:**

1. Template registry → match → TRIVIAL (deterministic, $0.00, <1ms)
2. Heuristic classifier → SIMPLE → local model
3. Heuristic classifier → MODERATE/COMPLEX → cloud model

**Acceptance criteria:**

- Template-matched elements never reach `generate_with_ollama()` or cloud agents
- Template match results are recorded in per-element metadata

---

## 7. Layer 4 — Manifest-Guided Repair (REQ-MP-4xx)

> Detailed requirements: [`REQ-MP-4xx_MANIFEST_GUIDED_REPAIR.md`](./REQ-MP-4xx_MANIFEST_GUIDED_REPAIR.md)

### REQ-MP-400: Repair Pipeline Structure

**Status:** planned
**Priority:** P0

A repair pipeline SHALL process local model output through a sequence of deterministic steps before `ast.parse()` validation. Each step uses the Forward Manifest as structural ground truth.

**Pipeline order:**

1. Fence stripping (existing `extract_code_from_response`)
2. Over-generation trimming (REQ-MP-401)
3. Bare statement wrapping (REQ-MP-407)
4. Indentation normalization (REQ-MP-402)
5. Signature reconciliation (REQ-MP-403)
6. Import completion (REQ-MP-404)
7. AST validation (REQ-MP-405)

**Acceptance criteria:**

- Steps execute in order; each step receives the output of the previous step
- A step that cannot improve the code passes it through unchanged
- The pipeline never makes code worse (no destructive transforms)

### REQ-MP-401: Over-Generation Trimming

**Status:** planned
**Priority:** P0

When the model generates more code than the target element, the repair pipeline SHALL parse the output and extract ONLY the node matching the target `ForwardElementSpec` by name and kind.

**Algorithm:**

1. Attempt `ast.parse()` on the raw output
2. Walk top-level nodes; find the node where `node.name == target.name` and AST type matches `target.kind`
3. Extract source lines for that node only
4. If parse fails, pass through to indentation normalization

**Acceptance criteria:**

- An output containing `get_secret` + `list_secrets` + `if __name__` is trimmed to just `get_secret`
- An output containing a class wrapper around the target method extracts just the method
- Trimming preserves the target element's exact source text (no re-rendering)

### REQ-MP-402: Skeleton-Aware Indentation

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-200

When splicing a body into the skeleton, the repair pipeline SHALL normalize indentation to match the skeleton's body indent level rather than using heuristic multi-strategy recovery.

**Algorithm:**

1. Determine the target indent from the skeleton (parse skeleton → find `raise NotImplementedError` node → read its column offset)
2. `textwrap.dedent()` the generated body to remove all leading whitespace
3. `textwrap.indent()` with the target indent string
4. Validate via `ast.parse()` after splicing

**Acceptance criteria:**

- A body indented at 12 spaces (model imagined 3 levels of nesting) is normalized to 8 spaces (method in a class)
- Mixed tabs and spaces are normalized to 4-space indentation
- The heuristic 5-strategy recovery (`_normalize_indentation`) is superseded by this single deterministic operation

### REQ-MP-403: Signature Reconciliation

**Status:** planned
**Priority:** P1

When the model's output includes a function signature that differs from the manifest's `ForwardElementSpec.signature`, the repair pipeline SHALL replace the generated signature with the manifest's canonical version.

**Detection:**

- Parse the generated code's AST
- Compare the generated `FunctionDef.args` against `ForwardElementSpec.signature.params` for: parameter names, annotations, defaults, parameter kinds

**Repair:**

- Render the canonical signature from the manifest using the same `_render_signature()` logic as `DeterministicFileAssembler`
- Replace the `def` line in the source

**Acceptance criteria:**

- A generated function with `def format(self, rec)` is reconciled to `def format(self, record: logging.LogRecord) -> str`
- Return type annotations are preserved from the manifest even if the model dropped them
- Reconciliation fires only when signatures differ (no-op when they match)

### REQ-MP-404: Import Completion

**Status:** planned
**Priority:** P1

When the generated body references names that are available in `ForwardFileSpec.imports` but not imported in the generated code, the repair pipeline SHALL add the missing imports.

**Algorithm:**

1. Parse the generated code; collect all `ast.Name` nodes (referenced identifiers)
2. Collect all imported names from the code's `ast.Import` / `ast.ImportFrom` nodes
3. For each referenced-but-not-imported name, check if any `ForwardImportSpec` in the file spec provides it
4. Add matching imports to the code

**Scope constraint:** This step adds imports that the manifest already specifies. It does NOT invent new imports — that would be the model's job, and failure to use manifest-provided imports is the specific defect being repaired.

**Acceptance criteria:**

- A body using `json.dumps()` without `import json` gets the import added (when `json` is in `ForwardFileSpec.imports`)
- A body using `OrderedDict` without `from collections import OrderedDict` gets the import added
- Imports not in the manifest are never added
- Existing imports in the code are not duplicated

### REQ-MP-405: AST Validation Gate

**Status:** planned
**Priority:** P0

After all repair steps, the repaired code SHALL be validated via `ast.parse()`. The result determines routing:

| `ast.parse()` Result | Action |
|----------------------|--------|
| Success | Proceed to Sonnet verification (or accept if verification is skipped) |
| `SyntaxError` | Escalate to cloud model with error context |

**Acceptance criteria:**

- Syntax-valid repaired code proceeds to verification without re-generation
- Syntax-invalid code after repair is escalated with: the original model output, the repair attempt, and the `SyntaxError` message — all injected into the cloud model's prompt context

### REQ-MP-406: Non-Destructive Guarantee

**Status:** planned
**Priority:** P0

No repair step SHALL make syntactically valid code syntactically invalid. Each step SHALL be guarded:

```
input_code → attempt repair → ast.parse(result)
  → success: use repaired version
  → failure: revert to input_code (pre-repair)
```

**Acceptance criteria:**

- If code passes `ast.parse()` before a repair step, it still passes after
- If a repair step introduces a syntax error, the step's changes are discarded

### REQ-MP-407: Bare Statement Wrapping

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-401, REQ-MP-403
**Empirical basis:** 3 of 14 Round 2 verification failures

When the model outputs bare statements without a `def` wrapper (the body of a function without the function definition), the repair pipeline SHALL detect and wrap them using the manifest's canonical signature. Sits between over-generation trimming (Step 2) and indentation normalization (Step 4) in the repair pipeline.

**Acceptance criteria:**

- Bare statements detected when output has no `FunctionDef` but target is a function/method
- Wrapping uses the manifest's canonical signature (params, types, return annotation)
- Constants/variables are never wrapped (bare by design)
- Would recover 3 of 14 Round 2 failures (42% → ~54% verified)

---

## 8. Layer 5 — Routing & Integration (REQ-MP-5xx)

> Detailed requirements: [`REQ-MP-5xx_ROUTING_INTEGRATION.md`](./REQ-MP-5xx_ROUTING_INTEGRATION.md)

### REQ-MP-500: Four-Tier Complexity Routing

**Status:** planned
**Priority:** P0

The element routing system SHALL support four tiers:

| Tier | Agent | Cost | Latency | Selection Criteria |
|------|-------|------|---------|-------------------|
| TRIVIAL | Template registry | $0.00 | <1ms | Template match (REQ-MP-304) |
| SIMPLE | `ollama:startd8-coder` | $0.00 cloud | ~5s | Heuristic score ≤ -1, no external API imports, pure data transform |
| MODERATE | Haiku + Sonnet | ~$0.01-0.03 | ~5s | Heuristic score ≤ 2, or orchestrator pattern |
| COMPLEX | Sonnet / Opus | ~$0.05-0.10 | ~10s | Heuristic score > 2, or multi-service orchestration |

**Acceptance criteria:**

- Template-matched elements never invoke any model
- SIMPLE elements invoke only the local Ollama model
- Failed SIMPLE elements escalate to MODERATE (not retried locally)

### REQ-MP-501: Import-Based Complexity Gate

**Status:** planned
**Priority:** P0

The heuristic classifier SHALL add an import-based complexity signal: if the file's imports include external libraries with complex APIs, the element's complexity score SHALL be bumped to prevent local model routing.

**External API packages (initial set):**

```
grpc, grpcio, flask, fastapi, jinja2, django, google.cloud, google.auth,
boto3, azure, sqlalchemy, alembic, celery, redis, locust
```

**Gate logic:**

- Count distinct external API packages in `ForwardFileSpec.imports`
- Add count to the heuristic complexity score
- If any `[BINDING]` constraint references an external API, add +2

**Acceptance criteria:**

- An element in a file importing `grpc` and `google.cloud` gets +2 to complexity score
- An element in a file importing only `json` and `logging` (stdlib) is unaffected
- The gate catches elements that would have been Sonnet-FAIL in Round 1 (8 of 12 failures were external API related)

### REQ-MP-502: Escalation with Error Context

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-405

When a SIMPLE element fails both local generation and repair, it SHALL be escalated to a cloud model with the following context injected into the prompt:

1. The original local model output (raw)
2. The repair steps attempted and their outcomes
3. The `SyntaxError` or Sonnet verification failure message
4. The manifest element specification

This reuses the existing `last_error` / `test_output` injection pattern in `_execute_chunk_inner()`.

**Acceptance criteria:**

- The cloud model receives enough context to avoid repeating the local model's specific error
- Escalated elements are tracked separately in metrics (REQ-MP-600)

### REQ-MP-503: Ollama Availability Check

**Status:** planned
**Priority:** P1

At pipeline preflight, the system SHALL check that:

1. Ollama is running (`http://localhost:11434/api/tags` responds)
2. The `startd8-coder` model is available in the model list
3. If either check fails, all SIMPLE elements are routed to MODERATE (graceful degradation)

This extends the existing Ollama preflight check in `artisan_phases/preflight.py` (lines 1095-1156).

**Acceptance criteria:**

- Pipeline does not fail if Ollama is unavailable — it degrades to cloud-only
- A warning is logged when Ollama is unavailable

### REQ-MP-504: Per-Element Execution in ArtisanChunkExecutor

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-500

The `ArtisanChunkExecutor` SHALL support per-element agent selection within a single chunk. Today, a chunk is routed to one agent (drafter). With micro-prime, a chunk may contain elements at different tiers.

**Options (choose one during implementation):**

- (a) Split SIMPLE elements into a separate pre-pass before the chunk executor runs
- (b) Add an `ollama_spec` to `ArtisanChunkExecutor` alongside `drafter_spec` / `refiner_spec`
- (c) Process TRIVIAL and SIMPLE elements during the SCAFFOLD phase extension, before IMPLEMENT

**Acceptance criteria:**

- SIMPLE elements are processed by the local model regardless of which option is chosen
- MODERATE/COMPLEX elements in the same chunk are unaffected
- The skeleton file has SIMPLE bodies filled in before cloud models process MODERATE/COMPLEX elements in the same file

### REQ-MP-505: Skeleton Preservation Across Tiers

**Status:** planned
**Priority:** P0

When multiple elements in the same file are processed by different tiers (TRIVIAL, SIMPLE, MODERATE, COMPLEX), the skeleton file SHALL be the shared assembly target. Each tier splices its output into the skeleton independently.

**Ordering constraint:** TRIVIAL and SIMPLE elements SHOULD be processed before MODERATE/COMPLEX elements, so that cloud models receive a partially-filled skeleton with working examples as context.

**Acceptance criteria:**

- A file with 3 TRIVIAL, 2 SIMPLE, and 4 MODERATE elements has all 9 bodies spliced into a single coherent file
- The skeleton's import block, `__all__`, and structure are never modified by body splicing
- `ast.parse()` passes on the final assembled file

### REQ-MP-506: MicroPrimeEngine — Shared Core

**Status:** planned
**Priority:** P0

A `MicroPrimeEngine` class SHALL encapsulate the workflow-agnostic core: template registry, prompt builder, local model invocation, repair pipeline, and body splicing. Both the Artisan adapter and Prime adapter call into this engine.

**Interface:**

```python
class MicroPrimeEngine:
    def process_elements(
        self,
        elements: list[ForwardElementSpec],
        file_spec: ForwardFileSpec,
        contracts: list[InterfaceContract],
        skeleton_source: str,
        context: MicroPrimeContext,
    ) -> MicroPrimeResult
```

**Acceptance criteria:**

- Engine has no imports from `contractors/artisan_phases/` or `contractors/prime_contractor.py`
- Engine depends only on `forward_manifest`, `utils/file_assembler`, `utils/code_templates`, `utils/manifest_repair`
- Both adapters produce identical results for the same input elements

### REQ-MP-507: CodeGenerator Protocol Implementation (Prime Path)

**Status:** planned
**Priority:** P0

A `MicroPrimeCodeGenerator` SHALL implement the `CodeGenerator` protocol from `contractors/protocols.py`, enabling it to be used as the `code_generator` in `PrimeContractorWorkflow`.

**Protocol requirements:**

```python
class MicroPrimeCodeGenerator(CodeGenerator):
    def generate(
        self,
        task: str,
        context: dict[str, Any],
        target_files: list[str],
    ) -> GenerationResult
```

**Context consumption:** The Prime Contractor passes a `gen_context` dict. `MicroPrimeCodeGenerator` SHALL extract:

| Key | Source | Used For |
|-----|--------|----------|
| `domain_constraints` | `ForwardManifest.binding_constraints_for_task()` | Binding constraints in prompts |
| `forward_contracts` | Pipeline mode (Markdown-formatted) | Additional constraints |
| `existing_files` | `PrimeContractorWorkflow.develop_feature()` (40KB budget) | Edit-mode context |
| `service_metadata` | Seed enrichment | Service-specific patterns |
| `feature_name` | `FeatureSpec.name` | Prompt context |

**Acceptance criteria:**

- `MicroPrimeCodeGenerator` can be passed as `code_generator=` to `PrimeContractorWorkflow`
- Returns `GenerationResult` with `success`, `generated_files`, `cost_usd`, `input_tokens`, `output_tokens`
- Works in both standalone and pipeline execution modes
- Falls back to `LeadContractorCodeGenerator` for MODERATE/COMPLEX elements

### REQ-MP-508: Artisan Adapter (Artisan Path)

**Status:** planned
**Priority:** P0

An `ArtisanMicroPrimeAdapter` SHALL integrate the `MicroPrimeEngine` into the Artisan IMPLEMENT phase as a pre-pass that fills TRIVIAL and SIMPLE elements before the `ArtisanChunkExecutor` processes MODERATE/COMPLEX elements.

**Integration point:** Between skeleton rendering (SCAFFOLD) and chunk execution (IMPLEMENT).

**Acceptance criteria:**

- MODERATE/COMPLEX elements are unaffected — existing `ArtisanChunkExecutor` behavior is preserved
- Cloud models receive partially-filled skeletons with TRIVIAL/SIMPLE bodies as in-context examples
- Adapter reuses the existing `_execute_chunk_inner()` retry/escalation pattern for SIMPLE failures

### REQ-MP-509: Context Normalization

**Status:** planned
**Priority:** P1

The `MicroPrimeEngine` SHALL accept a normalized `MicroPrimeContext` that abstracts away the differences between Artisan and Prime context shapes.

**Context shape differences:**

| Field | Artisan Source | Prime Source |
|-------|---------------|-------------|
| Forward manifest | Phase pipeline data | `seed["forward_manifest"]` |
| Binding constraints | `ForwardManifest.binding_constraints_for_task()` | `gen_context["domain_constraints"]` |
| Existing files | Chunk context | `gen_context["existing_files"]` (40KB budget) |
| Target files | `DevelopmentChunk.file_targets` | `feature.target_files` |
| Execution mode | Always pipeline | `ExecutionMode.STANDALONE` or `PIPELINE` |

**Normalized context:**

```python
@dataclass(frozen=True)
class MicroPrimeContext:
    manifest: ForwardManifest
    target_files: list[str]
    binding_constraints: list[str]
    existing_file_contents: dict[str, str]
    ollama_available: bool
    ollama_model: str = "startd8-coder"
```

Each adapter (Artisan, Prime) maps its workflow-specific context into this shape.

**Acceptance criteria:**

- `MicroPrimeEngine` never inspects workflow-specific context keys
- Artisan adapter builds `MicroPrimeContext` from phase pipeline data
- Prime adapter builds `MicroPrimeContext` from `gen_context` dict
- Both produce the same `MicroPrimeContext` shape for the same underlying data

### REQ-MP-510: GenerationResult Emission

**Status:** planned
**Priority:** P1

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

**Artisan path:** Write assembled files to the chunk's output directory and populate `exec_output` for the existing phase pipeline.

**Cost tracking:**

- TRIVIAL/SIMPLE elements report `cost_usd=0.00` for cloud cost
- Escalated elements report the actual cloud cost of the fallback generation
- Both adapters populate `input_tokens` and `output_tokens` for local model usage (informational)

**Acceptance criteria:**

- Prime adapter returns `GenerationResult` with all required fields
- Artisan adapter's output is compatible with `_execute_chunk_inner()` expectations
- Cost tracking distinguishes local (free) from escalated (cloud cost) elements

### REQ-MP-511: Per-Element API Dependency Analysis

**Status:** planned
**Priority:** P0
**Refines:** REQ-MP-501
**Empirical basis:** Round 2 — file-level gate blocks 8 passing elements

The complexity gate SHALL analyze per-element API dependencies rather than relying solely on file-level imports. A file may import external libraries, but individual elements within that file may not use them. Implements a two-pass algorithm: Pass 1 (REQ-MP-501) is the coarse file-level scan; Pass 2 (REQ-MP-511) refines per-element using binding constraints, docstring hints, and name/signature patterns.

**Acceptance criteria:**

- Elements in external-import files that don't use external APIs in their body are classified as SIMPLE
- File-level gate (REQ-MP-501) still applies as coarse first pass; per-element refinement can override downward
- Projected impact: routes ~14 elements locally (vs 6 file-level only) at ~71% verified rate (vs 33%)

### REQ-MP-512: Verification-Gated Escalation Flow

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-502, REQ-MP-504, REQ-MP-508, REQ-MP-405, REQ-MP-407

The pipeline SHALL implement a verification-gated escalation flow: generate locally → repair (REQ-MP-400) → AST validate (REQ-MP-405) → structural verify → accept or escalate to cloud. Includes a zero-cost structural verification mode (AST-based: checks for return statements, no `NotImplementedError`, non-empty body) and batch escalation per file with partially-filled skeleton as context.

**Acceptance criteria:**

- Elements passing both AST and structural verification are accepted without cloud calls
- Failed elements are escalated with full `EscalationContext` (REQ-MP-502)
- Escalation is batched per-file; cloud model receives partially-filled skeleton as examples
- Projected impact: ~13 of 24 elements accepted locally (54% cloud call reduction)

---

### REQ-MP-513: Configurable Cloud Escalation Retries

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-512

When element-level cloud escalation is used, the system SHALL retry direct cloud generation up to a configurable maximum.

**Acceptance criteria:**
- A new Micro Prime configuration value `cloud_escalation_max_attempts` MUST control the maximum attempts (default: 1).
- Retries are per element and only trigger on: empty response, code extraction failure, or splice failure.
- Retries MUST NOT re-run local Ollama generation or decomposition for the same element.
- If all attempts fail, the element remains escalated and the workflow continues (no crash).

### REQ-MP-514: Cache-Friendly Retry Strategy

**Status:** planned
**Priority:** P1

Retry behavior SHALL support a cache-friendly prompt strategy while allowing error-informed retries when requested.

**Acceptance criteria:**
- A new configuration value `cloud_escalation_retry_strategy` MUST support at least:
  - `same_prompt` (default): prompt and system prompt are byte-for-byte identical across attempts.
  - `append_error`: a bounded failure summary and attempt number are appended for attempts >= 2.
- If `same_prompt` is selected, no attempt-specific tokens are added that would defeat provider caching.
- If `append_error` is selected, the added retry context MUST be capped to a fixed character budget (default: 512 chars).

### REQ-MP-515: Retry Telemetry and Repair Sequencing

**Status:** planned
**Priority:** P1

The system SHALL record retry outcomes and ensure post-generation repair runs after the final retry/splice pass.

**Acceptance criteria:**
- Per-element metadata MUST include: `cloud_retry_attempts`, `cloud_retry_success`, `cloud_retry_strategy`, and `cloud_retry_last_error` (if any).
- `element_escalation_count` and cost accounting MUST reflect only successful cloud attempts.
- Post-generation file repair (`_run_post_generation_repair`) MUST run once after the final retry/splice pass, not after each attempt.

---

## 9. Layer 6 — Observability & Metrics (REQ-MP-6xx)

> Detailed requirements: [`REQ-MP-6xx_OBSERVABILITY.md`](./REQ-MP-6xx_OBSERVABILITY.md)

### REQ-MP-600: Per-Element Generation Metrics

**Status:** planned
**Priority:** P1

Each element's generation SHALL be tracked with:

| Field | Type | Description |
|-------|------|-------------|
| `element_fqn` | str | Fully qualified name |
| `tier` | str | TRIVIAL / SIMPLE / MODERATE / COMPLEX |
| `generation_time_ms` | int | Wall-clock time for generation |
| `generation_tokens` | int | Input + output tokens (0 for TRIVIAL) |
| `repair_steps_applied` | list[str] | Which repair steps modified the code |
| `repair_recovered` | bool | Whether repair turned a syntax failure into a pass |
| `ast_valid` | bool | After repair |
| `verification_verdict` | str | pass / fail / skipped |
| `escalated` | bool | Whether the element was escalated to cloud |
| `escalation_reason` | str | syntax_error / verification_fail |
| `template_name` | str | Template used (TRIVIAL elements only) |

**Acceptance criteria:**

- Metrics are emitted for every element regardless of tier
- Metrics are serializable to JSON for experiment result files

### REQ-MP-601: Repair Step Attribution

**Status:** planned
**Priority:** P2

Each repair step SHALL record whether it modified the code, enabling analysis of which steps provide the most value:

| Step | Metric |
|------|--------|
| Fence stripping | `fence_stripped: bool` |
| Over-generation trim | `trimmed: bool`, `nodes_removed: int` |
| Bare statement wrap | `bare_wrapped: bool` (REQ-MP-407) |
| Indentation normalization | `indent_normalized: bool` |
| Signature reconciliation | `signature_reconciled: bool`, `params_changed: int` |
| Import completion | `imports_added: int`, `import_names: list[str]` |

**Acceptance criteria:**

- After an experiment run, the user can answer: "How many elements were recovered by indentation normalization vs signature reconciliation?"

### REQ-MP-602: Cost Accounting

**Status:** planned
**Priority:** P1

The pipeline SHALL track cost per tier and report savings relative to an all-cloud baseline:

- **Baseline cost:** Estimated cost if all elements were processed by MODERATE tier (Haiku/Sonnet)
- **Actual cost:** Sum of cloud costs for MODERATE/COMPLEX elements + escalated SIMPLE elements
- **Savings:** Baseline - Actual
- **Local model cost:** $0.00 (reported for completeness)

**Acceptance criteria:**

- Cost report is included in experiment output JSON
- Cost report shows per-tier breakdown

### REQ-MP-603: Experiment Result Schema

**Status:** planned
**Priority:** P1

Experiment runs SHALL produce a JSON result file with schema:

```json
{
  "run_id": "string",
  "timestamp": "ISO-8601",
  "model": "startd8-coder",
  "seed": "seed-name",
  "total_elements": 32,
  "tier_breakdown": {
    "TRIVIAL": { "count": 3, "all_passed": true },
    "SIMPLE": { "count": 10, "syntax_pass": 9, "repair_recovered": 2, "verification_pass": 7, "escalated": 3 },
    "MODERATE": { "count": 15, "passed": 14 },
    "COMPLEX": { "count": 4, "passed": 3 }
  },
  "repair_summary": {
    "fence_stripped": 8,
    "trimmed": 2,
    "bare_wrapped": 3,
    "indent_normalized": 4,
    "signature_reconciled": 1,
    "imports_added": 3
  },
  "cost": {
    "baseline_all_cloud": 1.85,
    "actual": 1.20,
    "savings_pct": 35.1
  },
  "elements": [ ... per-element detail ... ]
}
```

**Acceptance criteria:**

- Schema is versioned (`schema_version` field)
- Result files from different runs can be compared programmatically

---

## 10. Layer 7 — Quick Wins & Acceleration (REQ-MP-7xx)

> Detailed requirements: [`REQ-MP-7xx_QUICK_WINS.md`](./REQ-MP-7xx_QUICK_WINS.md)

This layer identifies the smallest changes that unlock the most value. Most Micro Prime subsystems are 70-95% already built as production utilities, experiment script logic, or manifest models. The remaining gap is ~687 lines of glue code — but the **order** in which those lines are written determines how much cumulative value is delivered at each step.

### REQ-MP-700: Existing Code Delegation Contracts

**Status:** planned
**Priority:** P0

The implementation SHALL delegate to existing production code rather than reimplementing. Mandatory contracts: fence stripping → `extract_code_from_response()`, skeleton rendering → `DeterministicFileAssembler.render_file()`, element metadata → `ForwardElementSpec` fields, signature rendering → `DeterministicFileAssembler._render_signature()`, agent resolution → `resolve_agent_spec()`.

**Acceptance criteria:**
- No delegation target is modified to accommodate Micro Prime (consume-only contracts)
- `micro_prime/repair.py` does not contain regex-based fence stripping

### REQ-MP-701: Experiment Script Extraction Map

**Status:** planned
**Priority:** P0

Validated functions from the experiment script (~319 lines across 7 functions) SHALL be extracted to the `micro_prime` package rather than rewritten. Key extractions: `classify_element_heuristic()` → `classifier.py`, `_try_parse()` / `_normalize_indentation()` / `_extract_syntax_error()` → `repair.py`, `_find_few_shot_examples()` / `_estimate_body_lines()` → `prompt_builder.py`, `collect_elements()` → `classifier.py`.

**Acceptance criteria:**
- Extracted functions retain validated behavior (unit tests compare output against experiment script)
- No extracted function exceeds 20% diff from its experiment script source

### REQ-MP-702: splice_body() on DeterministicFileAssembler

**Status:** planned
**Priority:** P0
**Extends:** REQ-MP-202, REQ-MP-505

The `DeterministicFileAssembler` SHALL expose a `splice_body()` method (~25 lines) that replaces a specific element's `raise NotImplementedError` stub with generated body code. This is the keystone that bridges generation to output — all tiers (template, local model, cloud) share one insertion mechanism.

**Acceptance criteria:**
- Splicing preserves all other elements, imports, `__all__`, and class structure
- Multiple sequential splices into the same skeleton produce a valid file
- Incorrect indentation in body input is corrected to match stub indent level

### REQ-MP-703: Non-Destructive Repair Step Decorator

**Status:** planned
**Priority:** P0
**Implements:** REQ-MP-406

A `@repair_step` decorator SHALL wrap any repair function with before/after AST validation and automatic rollback. This enables incremental delivery: ship with 2 steps, add more later, each independently safe.

**Acceptance criteria:**
- Repair step that turns valid Python into invalid Python has changes discarded
- Adding a new step requires only: write function + decorate + append to step list

### REQ-MP-704: Compound Value Chain — Template-to-Few-Shot Pipeline

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-300, REQ-MP-205, REQ-MP-505

TRIVIAL elements filled by template SHALL be immediately available as few-shot examples for subsequent SIMPLE generation. Processing order within each file: TRIVIAL first (always correct, $0), then SIMPLE (with accumulated few-shot examples). Each success improves the next generation — a self-reinforcing quality cycle.

**Acceptance criteria:**
- A file with 2 TRIVIAL + 5 SIMPLE elements: first SIMPLE receives 2 few-shot examples from TRIVIAL bodies
- Processing order is deterministic: TRIVIAL first (alphabetical), then SIMPLE (alphabetical)

### REQ-MP-705: Accelerated Build Order

**Status:** planned
**Priority:** P1

Implementation SHALL follow a sequence maximizing cumulative value: (1) `splice_body()` ~25 lines → (2) template registry ~100 lines → (3) model catalog entry ~12 lines → (4) `@repair_step` + fence strip + indent normalize ~90 lines → (5) classifier extraction ~170 lines → (6) few-shot wiring ~60 lines → (7) element-level import gate ~30 lines → (8) remaining repair steps ~200 lines.

**Acceptance criteria:**
- Each step is independently shippable (no step depends on a later step)
- Each step has an integration test gate that passes before proceeding

### REQ-MP-706: Incremental Repair Pipeline Delivery

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-703

The repair pipeline SHALL be delivered in phases: MVP (fence strip + indent normalize, ~60% recovery), Phase 2 (+ over-gen trim + bare wrap, ~80%), Phase 3 (+ sig reconcile + import complete, ~90%). Each step is feature-flaggable via `RepairConfig.enabled_steps`.

**Acceptance criteria:**
- Pipeline with only MVP steps produces measurable improvement over raw model output
- Removing a step requires only removing its name from `enabled_steps`

### REQ-MP-707: Model Catalog Ollama Provider Section

**Status:** planned
**Priority:** P1
**Implements:** REQ-MP-104

~12 lines total: `Models.OLLAMA_STARTD8_CODER` constant, `_MODEL_REGISTRY` entry (`provider="ollama"`, `tier="fast"`, `capabilities={"text", "code"}`), and `get_latest_model()` tier mapping for Ollama.

**Acceptance criteria:**
- `resolve_agent_spec("ollama:startd8-coder")` returns a valid agent
- `get_latest_model("ollama", "fast")` returns `"ollama:startd8-coder"`

### REQ-MP-708: Element-Level Import Gate Refinement

**Status:** planned
**Priority:** P2
**Refines:** REQ-MP-511

Per-element import gate uses three signals: binding constraints referencing external packages (+2), parameter types from external packages (+2), and name patterns combined with file-level external imports (+1). Recovers elements like `HealthCheck.Check` that the file-level gate incorrectly blocks.

**Acceptance criteria:**
- Elements in external-import files whose constraints don't reference those packages are classified as SIMPLE
- Recovers at least 2 additional elements per seed compared to file-level only

---

## 11. Layer 8 — Shared Complexity Router (REQ-MP-8xx)

> Detailed requirements: [`REQ-MP-8xx_SHARED_COMPLEXITY_ROUTER.md`](./REQ-MP-8xx_SHARED_COMPLEXITY_ROUTER.md)

Extracts Artisan's complexity routing into a shared module, creating a unified 4-tier classification system across all code generation paths.

---

## 12. Layer 9 — Moderate Decomposer (REQ-MP-9xx)

> Detailed requirements: [`REQ-MP-9xx_MODERATE_DECOMPOSER.md`](./REQ-MP-9xx_MODERATE_DECOMPOSER.md)

Pre-escalation decomposition of MODERATE elements into SIMPLE sub-elements that Ollama can generate serially. Introduces pluggable decomposition strategies (class decomposition, function chaining) with assembly and verification. Extends the Mottainai principle: don't spend cloud budget on work that can be decomposed and done locally.

### Summary of Requirements

| ID | Name | Priority | Status |
|----|------|----------|--------|
| REQ-MP-900 | Moderate Decomposer Module | P0 | planned |
| REQ-MP-901 | Class Decomposition Strategy | P0 | planned |
| REQ-MP-902 | Function Decomposition Strategy | P1 | planned |
| REQ-MP-903 | Engine Integration — `_handle_moderate` | P0 | planned |
| REQ-MP-904 | Assembly Strategies | P0 | planned |
| REQ-MP-905 | Synthetic Element Spec Construction | P1 | planned |
| REQ-MP-906 | Decomposition Metrics and Observability | P1 | planned |
| REQ-MP-907 | Decomposition Strategy Registry | P1 | planned |
| REQ-MP-908 | Configuration | P2 | planned |
| REQ-MP-909 | Prime Adapter Integration | P0 | planned |

---

## 13. Data Flow

### 11.1 Dual Entry Points

```
┌─────────────────────────────┐    ┌──────────────────────────────────┐
│  ARTISAN WORKFLOW            │    │  PRIME CONTRACTOR                 │
│                              │    │                                   │
│  SCAFFOLD phase              │    │  PrimeContractorWorkflow          │
│    └─ DeterministicFile-     │    │    └─ develop_feature()           │
│       Assembler              │    │         └─ code_generator         │
│                              │    │              .generate()          │
│  IMPLEMENT phase             │    │                                   │
│    └─ ArtisanMicroPrime-     │    │  MicroPrimeCodeGenerator          │
│       Adapter                │    │    (implements CodeGenerator)     │
│                              │    │                                   │
└──────────┬───────────────────┘    └──────────────┬────────────────────┘
           │                                       │
           │    ┌──────────────────────────┐        │
           └───►│  MicroPrimeContext       │◄───────┘
                │  (normalized)            │
                └───────────┬──────────────┘
                            │
                            ▼
                ┌──────────────────────────┐
                │  MicroPrimeEngine        │
                │  (workflow-agnostic)     │
                └───────────┬──────────────┘
                            │
                            ▼
```

### 11.2 Engine Internals

```
MicroPrimeEngine.process_elements()
  │
  ├─ DeterministicFileAssembler.render_file() → skeleton .py
  │
  ├─ Per element:
  │    │
  │    ├─ Template registry match?
  │    │    └─ YES → TRIVIAL (deterministic, $0.00, <1ms)
  │    │
  │    ├─ Heuristic: SIMPLE?
  │    │    ├─ Body-only prompt → startd8-coder → Repair pipeline
  │    │    │    ├─ ast.parse() FAIL → escalate to cloud
  │    │    │    ├─ Structural verify PASS → splice into skeleton
  │    │    │    └─ Structural verify FAIL → escalate to cloud (REQ-MP-512)
  │    │    └─ Splice into skeleton
  │    │
  │    └─ MODERATE / COMPLEX → escalate to cloud
  │
  ├─ Assembled .py (all locally-resolved bodies filled in)
  │
  └─ MicroPrimeResult
       ├─ assembled_files: dict[str, str]
       ├─ resolved_elements: list[str]     (FQNs filled by TRIVIAL/SIMPLE)
       ├─ escalated_elements: list[str]    (FQNs needing cloud generation)
       ├─ metrics: MicroPrimeElementMetrics[]
       └─ cost_usd: float                 (0.00 for local, >0 for escalated)

                            │
                ┌───────────┴──────────────┐
                │                          │
                ▼                          ▼
┌──────────────────────────┐  ┌──────────────────────────────┐
│  Artisan Adapter          │  │  Prime Adapter                │
│                           │  │                               │
│  Writes filled skeletons  │  │  Returns GenerationResult     │
│  to chunk output dir.     │  │  with assembled files.        │
│  Escalated elements       │  │  Escalated elements fall      │
│  processed by existing    │  │  back to LeadContractor-      │
│  ArtisanChunkExecutor.    │  │  CodeGenerator.               │
└──────────────────────────┘  └──────────────────────────────┘
```

---

## 14. Traceability Matrix

| Requirement | Implementation File | Test File | Status |
|------------|-------------------|-----------|--------|
| REQ-MP-100 | `Modelfile.startd8-coder` | Smoke test (manual) | implemented |
| REQ-MP-101 | `Modelfile.startd8-coder` | Determinism test (manual) | implemented |
| REQ-MP-102 | `Modelfile.startd8-coder` | API hallucination test (manual) | implemented |
| REQ-MP-103 | `Modelfile.startd8-coder` | Stop sequence validation (manual) | planned |
| REQ-MP-104 | `src/startd8/providers/openai.py` | `tests/unit/providers/test_ollama.py` | planned |
| REQ-MP-200 | `src/startd8/utils/file_assembler.py` | `tests/unit/utils/test_file_assembler.py` | planned |
| REQ-MP-201 | `scripts/experiment_local_model_routing.py` | Experiment run | planned |
| REQ-MP-202 | `src/startd8/utils/file_assembler.py` | `tests/unit/utils/test_body_splicing.py` | planned |
| REQ-MP-203 | `scripts/experiment_local_model_routing.py` | Experiment run | planned |
| REQ-MP-204 | `src/startd8/utils/manifest_repair.py` | `tests/unit/utils/test_manifest_repair.py` | planned |
| REQ-MP-205 | `scripts/experiment_local_model_routing.py` | Experiment run | planned |
| REQ-MP-300 | `src/startd8/utils/code_templates.py` | `tests/unit/utils/test_code_templates.py` | planned |
| REQ-MP-301 | `src/startd8/utils/code_templates.py` | `tests/unit/utils/test_code_templates.py` | planned |
| REQ-MP-302 | `src/startd8/utils/code_templates.py` | `tests/unit/utils/test_code_templates.py` | planned |
| REQ-MP-303 | `src/startd8/utils/code_templates.py` | `tests/unit/utils/test_code_templates.py` | planned |
| REQ-MP-304 | `src/startd8/contractors/artisan_phases/development.py` | Integration test | planned |
| REQ-MP-400 | `src/startd8/utils/manifest_repair.py` | `tests/unit/utils/test_manifest_repair.py` | planned |
| REQ-MP-401 | `src/startd8/utils/manifest_repair.py` | `tests/unit/utils/test_manifest_repair.py` | planned |
| REQ-MP-402 | `src/startd8/utils/manifest_repair.py` | `tests/unit/utils/test_manifest_repair.py` | planned |
| REQ-MP-403 | `src/startd8/utils/manifest_repair.py` | `tests/unit/utils/test_manifest_repair.py` | planned |
| REQ-MP-404 | `src/startd8/utils/manifest_repair.py` | `tests/unit/utils/test_manifest_repair.py` | planned |
| REQ-MP-405 | `src/startd8/utils/manifest_repair.py` | `tests/unit/utils/test_manifest_repair.py` | planned |
| REQ-MP-406 | `src/startd8/utils/manifest_repair.py` | `tests/unit/utils/test_manifest_repair.py` | planned |
| REQ-MP-407 | `src/startd8/utils/manifest_repair.py` | `tests/unit/utils/test_manifest_repair.py` | planned |
| REQ-MP-500 | `src/startd8/micro_prime/engine.py` | Integration test | planned |
| REQ-MP-501 | `src/startd8/micro_prime/engine.py` | Experiment run | planned |
| REQ-MP-502 | `src/startd8/micro_prime/engine.py` | Integration test | planned |
| REQ-MP-503 | `src/startd8/contractors/artisan_phases/preflight.py` | `tests/unit/contractors/test_preflight.py` | planned |
| REQ-MP-504 | `src/startd8/micro_prime/artisan_adapter.py` | Integration test | planned |
| REQ-MP-505 | `src/startd8/utils/file_assembler.py` | `tests/unit/utils/test_file_assembler.py` | planned |
| REQ-MP-506 | `src/startd8/micro_prime/engine.py` | `tests/unit/micro_prime/test_engine.py` | planned |
| REQ-MP-507 | `src/startd8/micro_prime/prime_adapter.py` | `tests/unit/micro_prime/test_prime_adapter.py` | planned |
| REQ-MP-508 | `src/startd8/micro_prime/artisan_adapter.py` | `tests/unit/micro_prime/test_artisan_adapter.py` | planned |
| REQ-MP-509 | `src/startd8/micro_prime/context.py` | `tests/unit/micro_prime/test_context.py` | planned |
| REQ-MP-510 | `src/startd8/micro_prime/prime_adapter.py` | `tests/unit/micro_prime/test_prime_adapter.py` | planned |
| REQ-MP-511 | `src/startd8/micro_prime/engine.py` | `tests/unit/micro_prime/test_element_gate.py` | planned |
| REQ-MP-512 | `src/startd8/micro_prime/engine.py` | `tests/unit/micro_prime/test_escalation_flow.py` | planned |
| REQ-MP-513 | `src/startd8/micro_prime/prime_adapter.py` | `tests/unit/micro_prime/test_prime_adapter.py` | planned |
| REQ-MP-514 | `src/startd8/micro_prime/prime_adapter.py` | `tests/unit/micro_prime/test_prime_adapter.py` | planned |
| REQ-MP-515 | `src/startd8/micro_prime/prime_adapter.py` | `tests/unit/micro_prime/test_prime_adapter.py` | planned |
| REQ-MP-600 | `scripts/experiment_local_model_routing.py` | Experiment run | planned |
| REQ-MP-601 | `src/startd8/utils/manifest_repair.py` | Unit test | planned |
| REQ-MP-602 | `scripts/experiment_local_model_routing.py` | Experiment run | planned |
| REQ-MP-603 | `scripts/experiment_local_model_routing.py` | Schema validation test | planned |
| REQ-MP-700 | Cross-cutting (delegation contracts) | Code review | planned |
| REQ-MP-701 | `src/startd8/micro_prime/` (multiple) | Unit tests comparing against experiment script | planned |
| REQ-MP-702 | `src/startd8/utils/file_assembler.py` | `tests/unit/utils/test_file_assembler.py` | planned |
| REQ-MP-703 | `src/startd8/micro_prime/repair.py` | `tests/unit/micro_prime/test_repair.py` | planned |
| REQ-MP-704 | `src/startd8/micro_prime/engine.py` | `tests/integration/test_compound_chain.py` | planned |
| REQ-MP-705 | Implementation plan (build order) | Integration test gates per step | planned |
| REQ-MP-706 | `src/startd8/micro_prime/repair.py` | `tests/unit/micro_prime/test_repair.py` | planned |
| REQ-MP-707 | `src/startd8/model_catalog.py` | `tests/unit/test_model_catalog.py` | planned |
| REQ-MP-708 | `src/startd8/micro_prime/classifier.py` | `tests/unit/micro_prime/test_classifier.py` | planned |

---

## 15. Verification Strategy

### 13.1 Experiment Rounds (Pre-Integration)

| Round | Focus | Measures |
|-------|-------|----------|
| 2a | Skeleton-first prompting (Layer 2) | Syntax rate, Sonnet pass rate, tokens/element |
| 2b | Template registry (Layer 3) | Elements matched, correctness |
| 2c | Repair pipeline (Layer 4) | Recovery rate per step, net syntax rate |
| 2d | Combined (all layers) | End-to-end usable rate, cost savings |

### 13.2 Unit Tests (~60 tests across 4 files)

| File | Count | Coverage |
|------|-------|----------|
| `test_code_templates.py` | ~15 | Template matching, rendering, edge cases |
| `test_manifest_repair.py` | ~25 | Each repair step: trim, indent, signature, imports; non-destructive guarantee |
| `test_body_splicing.py` | ~10 | Splice into skeleton, indent normalization, multi-element files |
| `test_experiment_integration.py` | ~10 | End-to-end: manifest → template/generate → repair → validate |

### 13.3 Integration Acceptance Criteria

| Criterion | Measurement |
|-----------|-------------|
| No regression in MODERATE/COMPLEX elements | Run existing artisan test suite with micro-prime enabled |
| Graceful degradation without Ollama | Run pipeline with Ollama stopped; all elements route to cloud |
| Deterministic output | 3 consecutive runs produce identical results for TRIVIAL and SIMPLE tiers |
| Cost savings ≥ 20% | Compare actual cloud cost vs baseline for online-boutique-demo seed |

---

## 16. Related Documents

| Document | Relationship |
|----------|-------------|
| [DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md](../../scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md) | Foundation — provides skeleton rendering (Layer 2 depends on this) |
| [LOCAL_MODEL_ROUTING_EXPERIMENT.md](../../local-model-routing/LOCAL_MODEL_ROUTING_EXPERIMENT.md) | Experiment baseline — Round 1 results that motivated this design |
| [OLLAMA_MODEL_TUNING.md](../OLLAMA_MODEL_TUNING.md) | Layer 1 implementation — model selection and Modelfile configuration |
| [MANIFEST_GUIDED_REPAIR.md](../MANIFEST_GUIDED_REPAIR.md) | Layer 4 design exploration — detailed repair pipeline algorithms |
| `ARTISAN_REQUIREMENTS.md` | Parent pipeline — complexity-driven model routing (REQ-CMR-000) that micro-prime extends |
| `src/startd8/forward_manifest.py` | Schema — ForwardManifest, ForwardElementSpec, InterfaceContract |
| `src/startd8/utils/file_assembler.py` | Implementation — DeterministicFileAssembler |
| `src/startd8/utils/code_extraction.py` | Implementation — extract_code_from_response, STUB_SENTINEL |
| [MICRO_PRIME_IMPLEMENTATION_PLAN.md](./MICRO_PRIME_IMPLEMENTATION_PLAN.md) | Implementation plan — phased build order, package structure, existing assets |
| `scripts/experiment_local_model_routing.py` | Experiment script — source for extraction targets (REQ-MP-701) |
| `src/startd8/model_catalog.py` | Model registry — target for Ollama provider section (REQ-MP-707) |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal - suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: codex (gpt-5)
- **Date**: 2026-03-01 19:12:31 UTC
- **Scope**: Requirements-quality review for clarity, execution risk, and testability before implementation

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | Replace REQ-MP-504's "choose one during implementation" options with a single normative integration path and move alternatives into an ADR note. | Leaving three implementation options in a requirement makes it ambiguous and weakens testability across teams. | Section 8, REQ-MP-504 | Verify REQ-MP-504 specifies one required path and no longer uses unresolved option bullets. |
| R1-F2 | Interfaces | high | Define explicit partial-success semantics for `GenerationResult` when some elements are escalated, including where escalated element metadata is surfaced to callers. | Adapter consumers need a stable contract for mixed local/cloud outcomes; current wording focuses on success fields but not mixed-state shape. | Section 8, REQ-MP-507 and REQ-MP-510 | Verify one example shows a mixed local/escalated result and names required fields for escalated elements. |
| R1-F3 | Data | high | Refactor the Traceability Matrix to point at the new `src/startd8/micro_prime/` module layout and add an ownership/update rule to keep mappings current. | The matrix currently references several legacy files that conflict with the proposed package structure, making it unreliable for execution tracking. | Section 11, Traceability Matrix | Verify each REQ-MP row maps to an existing planned file and test artifact in the implementation plan. |
| R1-F4 | Risks | high | Extend REQ-MP-503 with runtime health-failure handling (not just preflight), including mid-run Ollama outage behavior and fallback guarantees. | Preflight-only checks do not cover long runs where local model availability can change during execution. | Section 8, REQ-MP-503 | Validate a test scenario where Ollama becomes unavailable after preflight and elements still degrade safely to cloud routing. |
| R1-F5 | Validation | medium | Add explicit compatibility rules for REQ-MP-603 result schema (`schema_version` bump policy and minimum supported reader versions). | The document requires a version field but does not define how version changes are managed or validated over time. | Section 9, REQ-MP-603 | Verify the schema section states backward-compatible vs breaking changes and the required version increment behavior. |
| R1-F6 | Ops | high | Add requirements for local inference resource governance: max concurrent SIMPLE requests, per-element timeout, and queue/backpressure policy. | Without operational guardrails, local routing can starve CPU/RAM or introduce nondeterministic latency under load. | Section 8, Layer 5 (new REQ-MP-516 or extension to REQ-MP-500/503) | Verify load tests assert bounded concurrency and timeout behavior with deterministic fallback when limits are hit. |
| R1-F7 | Security | high | Add prompt and telemetry sanitization requirements to prevent secrets from `existing_files` or bindings leaking into logs/metrics/escalation payloads. | The design forwards rich context into prompts and escalation payloads but does not define redaction controls for sensitive data. | Section 8 (REQ-MP-502/509) and Section 9 (REQ-MP-600/603) | Validate tests that inject secret-like values and assert redaction/hashing before persistence or telemetry emission. |
| R1-F8 | Architecture | medium | Add a source-of-truth requirement for shared utilities (`code_templates`, `manifest_repair`) to avoid long-term duplication between legacy utils and new `micro_prime` modules. | Both reuse and rewrite paths are described across docs; without a migration rule, drift and divergent fixes are likely. | Section 8, REQ-MP-506 and Section 13 related docs | Verify one canonical module is declared for each subsystem and any compatibility wrappers are explicitly temporary. |

#### Review Round R2

- **Reviewer**: Antigravity
- **Date**: 2026-03-01
- **Scope**: Requirements review for consistency, completeness, and error robustness.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Templates | medium | Clarify handling of `async` functions in Layer 3 (Template Registry). | Modern frameworks (FastAPI, etc.) rely heavily on `async`, but templates currently only show sync examples. | REQ-MP-3xx | Verify templates correctly emit `async def` when manifest specifies `is_async=True`. |
| R2-S2 | Repair | low | Add explicit handling for `pass` bodies in REQ-MP-401 (Over-Generation Trimming). | If a model generates `pass` as a placeholder, it might satisfy syntax but fail intent. Should be treated as failure or specifically stripped. | REQ-MP-401 | Add test case where model returns `pass` and ensure it escalates if functionality was expected. |
| R2-S3 | Repair | low | Extend REQ-MP-404 (Import Completion) to handle relative imports. | Manifests often use relative imports for local package components. The repair logic should ensure relative context is preserved. | REQ-MP-404 | Test repair with `from .utils import foo` and verify it's correctly completed if used but missing. |
| R2-S4 | Lifecycle | medium | Add a "Requirement Retirement" policy for when REQs are superseded by implementation realities. | As 36 REQs are planned, some may prove redundant. A process for marking REQs as `superseded` would preserve traceability. | New Section 14 | Update REQ-MP-xxx with `Status: superseded by REQ-MP-yyy`. |
| R2-S5 | Routing | high | Define fallback behavior if Ollama is running but the specific `startd8-coder` model is missing and cannot be pulled (e.g., offline). | REQ-MP-503 mentions checking for the model, but not the "cannot pull" edge case in restricted environments. | REQ-MP-503 | Test preflight with no internet and no local model; verify immediate graceful degradation to cloud. |

#### Review Round R3

- **Reviewer**: codex (gpt-5)
- **Date**: 2026-03-01 21:08:26 UTC
- **Scope**: Novel low-effort/high-value opportunities beyond REQ-MP-7xx quick wins and prior rounds

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Interfaces | high | Add a `classification_reason_codes` requirement so each tier decision carries machine-readable reasons (for example: `template_match`, `external_api_gate`, `binding_signal`, `timeout_fallback`). | This is a small extension to existing classifier outputs and unlocks fast debugging/tuning without new generation infrastructure. | Layer 5, REQ-MP-500/501/511 (or new REQ-MP-709) | Verify per-element metrics and experiment JSON include stable reason codes for every routing decision. |
| R3-F2 | Ops | high | Add a run-level local failure circuit breaker: after N consecutive SIMPLE failures/timeouts, auto-route remaining SIMPLE elements to cloud for that run. | A few lines of control logic can prevent long degraded runs when local model quality or runtime health collapses mid-execution. | Layer 5, REQ-MP-503/512 (or new REQ-MP-710) | Simulate repeated local failures and assert deterministic trip behavior plus automatic cloud fallback. |
| R3-F3 | Validation | high | Add bounded escalation-context rules with deterministic priority ordering and a hard token budget for fallback prompts. | Escalation quality improves when context is prioritized; cost/latency improves when oversized payloads are trimmed predictably. | Layer 5, REQ-MP-502 (or new REQ-MP-711) | Verify escalation payload never exceeds budget and always retains required high-priority fields (error, signature, imports, target stub). |
| R3-F4 | Data | medium | Add a strict output reuse cache for successful SIMPLE generations keyed by element fingerprint (FQN + signature hash + constraint hash + stub hash). | Minimal in-memory/disk caching can eliminate duplicate local inference across retries/re-runs for unchanged elements. | Layer 5/6, REQ-MP-506 and REQ-MP-600 (or new REQ-MP-712) | Re-run the same seed with unchanged fingerprints and verify cached hits skip local generation while preserving identical assembled output. |
| R3-F5 | Validation | medium | Add a tiny golden corpus regression requirement: a fixed set of representative SIMPLE/TRIVIAL elements replayed in CI to detect classifier/repair regressions quickly. | Small curated fixtures provide outsized protection against accidental regressions while keeping CI cost low. | Verification Strategy + Layer 6 (or new REQ-MP-713) | Ensure CI fails if pass rate, routing decisions, or repair outcomes drift beyond defined tolerances on the corpus. |
