# Layer 9 — Moderate Decomposer (REQ-MP-9xx)

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** Planned
> **Date:** 2026-03-05
> **Modifies:** `micro_prime/engine.py`, `micro_prime/prime_adapter.py`
> **New module:** `src/startd8/micro_prime/decomposer.py`
> **Depends on:** REQ-MP-500 (four-tier routing), REQ-MP-506 (MicroPrimeEngine), REQ-MP-512 (verification-gated escalation)

---

## Overview

Today, elements classified as MODERATE are immediately escalated to a cloud model (or dropped when no fallback is configured). This layer introduces a **Moderate Decomposer** — a pre-escalation step that analyzes MODERATE elements and, where possible, decomposes them into two or more SIMPLE sub-elements that Ollama can generate serially. The sub-element results are then assembled into the complete MODERATE element.

### Motivating Example

PI-001 (online-boutique `emailservice/logger.py`) produced 5 elements. Four were classified SIMPLE and generated locally at $0.00. The fifth — `CustomJsonFormatter` — was classified MODERATE and escalated with zero generation attempted:

| Signal | Score | Note |
|--------|-------|------|
| 0 params | -1 | |
| no binding constraints | -1 | |
| class definition | +2 | Blanket penalty (classifier.py:193) |
| long docstring | +1 | > 100 chars (classifier.py:198) |
| **Total** | **+1** | MODERATE threshold: score in [0, 2] |

The class has two methods (`add_fields`, `format`) that were **already generated successfully** as separate SIMPLE elements. The class element itself is just a shell: `class CustomJsonFormatter(logging.Formatter):` + docstring. No `__init__`, no class-level state. This is a ~5-line boilerplate wrapper around methods that already exist — not genuinely moderate complexity.

### Design Principle

> **Decompose before escalate.** When a MODERATE element is an aggregate of individually-simple parts, generate the parts locally and assemble them. Only escalate to cloud when decomposition is not possible or a sub-element fails.

This extends the existing Mottainai principle: don't waste cloud budget on work that can be done locally with a different strategy.

### Scope

This layer handles MODERATE elements only. COMPLEX elements (score > 2) are never decomposition candidates — they are genuinely complex and should go to cloud. SIMPLE elements are already handled by the engine. TRIVIAL elements use templates.

---

## Requirements

### REQ-MP-900: Moderate Decomposer Module

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-506 (MicroPrimeEngine)

A `ModerateDecomposer` class SHALL analyze MODERATE elements and produce a `DecompositionPlan` — an ordered list of SIMPLE sub-elements that, when generated serially and assembled, produce the complete MODERATE element.

**Interface:**

```python
# src/startd8/micro_prime/decomposer.py

@dataclass
class SubElement:
    """A SIMPLE-tier piece of a decomposed MODERATE element."""
    name: str
    kind: str                          # "class_shell", "init", "method", "helper", "body_segment"
    prompt_context: str                # Additional context for the sub-element prompt
    depends_on: list[str]              # Names of sub-elements that must be generated first
    assembly_order: int                # Position in final assembly
    element_spec: Optional[ForwardElementSpec]   # Synthetic or existing element spec (None allowed for deterministic class_shell)
    deterministic: bool = False        # True = extract from skeleton without LLM; engine skips _handle_simple and does not increment generation counters [R3-S7]

@dataclass
class DecompositionPlan:
    """A plan to generate a MODERATE element as a sequence of SIMPLE sub-elements."""
    original_element: ForwardElementSpec
    sub_elements: list[SubElement]
    strategy: str                      # Name of the strategy that produced this plan
    assembly_kind: str                 # "class_compose", "function_chain", "sequential_body"
    confidence: float                  # 0.0–1.0 — decomposer's confidence this will work

class ModerateDecomposer:
    """Analyzes MODERATE elements and produces decomposition plans."""

    def decompose(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
    ) -> Optional[DecompositionPlan]:
        """Produce a decomposition plan, or None if no strategy applies.

        This is the single entry point — eliminates the double strategy sweep
        from separate can_decompose() + decompose() calls. [R3-S2]
        Returns None when: no strategy handles the element, plan exceeds
        max_sub_elements, or confidence is below threshold.
        """

    def can_decompose(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
    ) -> bool:
        """Lightweight viability check for dry-run reports only.

        Delegates to strategy.can_handle() without building a full plan.
        Must not be called in the generation path — use decompose() instead. [R3-S2]
        """
```

**Acceptance criteria:**

- `ModerateDecomposer` has no imports from `contractors/` — it is workflow-agnostic like the engine
- `decompose()` is the single entry point for the generation path — it checks strategy applicability, builds the plan, and applies confidence/size filters in one pass. Returns `None` when no strategy applies or the plan is rejected. [R3-S2]
- `can_decompose()` is retained as a lightweight check for dry-run reports only — it delegates to `strategy.can_handle()` without building a full plan. Must not be called in the generation path. [R3-S2]
- `DecompositionPlan.sub_elements` is ordered by `assembly_order` with dependency constraints in `depends_on`
- All sub-elements in a plan are classified SIMPLE or TRIVIAL — if any would classify as MODERATE+, decomposition is rejected
- `class_shell` sub-elements MAY omit `element_spec` when extracted deterministically (no LLM); all other sub-elements MUST provide a spec
- `DecompositionPlan.confidence` is computed via `_compute_confidence(plan, uncertainty_signals) -> float` using the formula `1.0 - (sum(signal_weights) / max_uncertainty)`. Documented uncertainty signals: missing `__init__` in manifest (−0.1), inferred helper signatures (−0.1 per helper), parse-only responsibility detection (−0.1), class-level attribute count >1 (−0.1). `max_uncertainty` is the sum of all possible signal weights; if `max_uncertainty == 0`, confidence is `1.0`, and the result is clamped to `[0.0, 1.0]`. Base confidence is `1.0` for deterministic-only plans (e.g., class shell extraction). [R1-S6]

---

### REQ-MP-901: Class Decomposition Strategy

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-900

The decomposer SHALL support a **class decomposition strategy** that breaks a MODERATE class element into:

1. **Class shell** — The `class` declaration line, base classes, docstring, and `pass` placeholder. This is deterministic (extracted from the skeleton) and requires no LLM generation.
2. **`__init__` method** — If the class has an `__init__` in the manifest element list, generate it as a SIMPLE sub-element via Ollama. If no `__init__` exists in the manifest, the class shell alone suffices.
3. **Class-level attributes** — Constants, type annotations, or default values declared at class scope (not in methods). Generated as a single SIMPLE sub-element if present.

Methods of the class that are already **separate elements in the manifest** are NOT part of the decomposition plan — they are handled by the engine's normal element processing loop.

**Applicability heuristic:**

A class element is decomposable when ALL of the following hold:

- `element.kind == ElementKind.CLASS`
- The class's methods are already present as separate elements in `file_spec.elements` (check `parent_class == element.name`)
- The class has at most 3 class-level attributes (constants/variables not counting methods)
- Class-level attributes are counted only from `file_spec.elements` with `parent_class == element.name` and `kind in {ElementKind.CONSTANT, ElementKind.VARIABLE}` (no manifest entry means no class-level attributes are generated)
- The class does not use metaclasses or complex decorators (`__init_subclass__`, `ABCMeta`, `@dataclass` with complex field factories)

**CustomJsonFormatter example:**

```
Original element:  CustomJsonFormatter (MODERATE, score=+1)
Strategy:          class_decompose
Sub-elements:
  1. class_shell    — deterministic from skeleton, no LLM needed
                      class CustomJsonFormatter(logging.Formatter):
                          """Formats log records as single-line JSON objects..."""
  2. (no __init__)  — not in manifest, not needed
  3. (no class attrs) — none present

Methods add_fields, format — already separate elements in manifest, already SIMPLE
```

In this case the decomposition plan has exactly 1 sub-element (the shell), which is TRIVIAL — it can be extracted directly from the skeleton with no generation at all.

**Acceptance criteria:**

- `CustomJsonFormatter` from PI-001 decomposes into a single TRIVIAL shell sub-element
- A class with an `__init__` decomposes into shell (TRIVIAL) + `__init__` (SIMPLE)
- A class with class-level constants decomposes into shell (TRIVIAL) + constants (SIMPLE) + `__init__` (SIMPLE if present)
- A class with methods NOT already in the manifest as separate elements is NOT decomposable by this strategy (returns `None`)
- A class with metaclass or `ABCMeta` or complex decorators is NOT decomposable (returns `None`)
- The shell sub-element's code is extracted from the existing skeleton, not LLM-generated
- If the skeleton already contains a stub `__init__`, assembly replaces the stub body rather than inserting a duplicate method
- Class-level attribute generation is only attempted when those attributes are present in `file_spec.elements` (no hallucinated class attrs)

---

### REQ-MP-902: Function Decomposition Strategy

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-900

The decomposer SHALL support a **function decomposition strategy** that breaks a MODERATE function element into a **dispatch body** + one or more **helper sub-functions**.

**Applicability heuristic:**

A function element is decomposable when ALL of the following hold:

- `element.kind in (ElementKind.FUNCTION, ElementKind.METHOD, ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD)`
- The element was classified MODERATE due to **scoring signals only** (param count, docstring length, class membership) — NOT due to external API dependencies or orchestrator detection
- The classification reason does NOT contain any API/orchestrator signal. To avoid fragile substring matching against reason strings (which vary, e.g., `"file has 9 external imports (>8)"` vs `"external API"`), `classify_element()` SHALL return an additional `ClassificationSignal` set alongside the reason string. Signals include: `EXTERNAL_IMPORTS`, `EXTERNAL_API`, `ORCHESTRATOR`, `APP_SERVER_INSTANCE`. The decomposer checks `signals & {EXTERNAL_IMPORTS, EXTERNAL_API, ORCHESTRATOR, APP_SERVER_INSTANCE} == set()` rather than parsing reason text. Until `ClassificationSignal` is implemented, the reason-string match list MUST include: `"external API"`, `"external imports"`, `"orchestrator"`, `"app/server instance"`. [R1-S2]
- The element's docstring or design_doc_sections describe 2+ distinct responsibilities (heuristic: 2+ sentence fragments separated by semicolons or bullet points in the docstring). Note: `"and"` is NOT a clause separator — Python docstrings often use it within a single clause (e.g., "Validate and sanitize the order fields" is one responsibility). [R3-Q2]
- Responsibility parsing is deterministic: split on `;`, bullet markers (`-`, `*`, `•`), or enumerated prefixes (`1.`, `2.`). Ignore clauses shorter than 4 words.

**Decomposition approach:**

1. **Dispatch body** — A SIMPLE sub-element that calls the helpers in sequence. The prompt instructs Ollama to generate a function body that delegates to named helpers (provided as stubs in the prompt context).
2. **Helper sub-functions** — Each responsibility becomes a SIMPLE sub-element. Helper names are derived from the docstring/design sections.

**Example:** A function `process_order(order, config)` with docstring "Validate the order fields; compute totals with tax; format the confirmation email" decomposes into:

```
Sub-elements:
  1. _validate_order_fields(order) -> None     [SIMPLE]
  2. _compute_totals(order, config) -> dict    [SIMPLE]
  3. _format_confirmation(order, totals) -> str [SIMPLE]
  4. process_order dispatch body                [SIMPLE — calls 1, 2, 3]
```

**Constraints:**

- Maximum 4 helper sub-functions per decomposition (if more would be needed, the element is too complex — reject decomposition)
- Helper names are prefixed with `_` to signal they are internal
- Helper names are derived by slugifying responsibility text; if the slug is empty, a Python keyword/builtin, or longer than 48 chars, fall back to `_helper_{n}`
- Helpers are generated BEFORE the dispatch body (so the dispatch body prompt can include their signatures)
- If any helper fails generation, the entire decomposition fails and the original element is escalated to cloud
- For METHOD/ASYNC_METHOD elements, helper placement is explicit:
  - Helpers are generated as private methods on the same class (same `parent_class`)
  - Helper signatures MUST include `self` (or `cls` for classmethods) as the first parameter
- Helpers preserve `async` when the parent method is async and the helper is awaited
- Helper names are uniquified if they collide with existing symbols in the file or class (suffix `_2`, `_3`, etc.)

**Acceptance criteria:**

- Functions classified MODERATE due to scoring (not API/orchestrator) are candidates
- Docstring with 2+ distinct clauses triggers decomposition
- Maximum 4 helpers enforced — 5+ responsibilities rejects decomposition
- Helpers are generated in dependency order (no helper depends on a later helper)
- If any sub-element fails, the entire decomposition is abandoned and the original MODERATE element is escalated to cloud (Mottainai does not apply to partial decomposition — a half-decomposed function is worse than none)
- Functions classified MODERATE due to external API hints or orchestrator detection are never decomposition candidates
- For method decomposition, helper methods are inserted into the class scope and include `self`/`cls` as appropriate
- When `ClassificationSignal` is available, it is the sole source for API/orchestrator exclusion; reason-string parsing is only used as a fallback and SHOULD emit a debug log for traceability

---

### REQ-MP-903: Engine Integration — `_handle_moderate`

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-900, REQ-MP-901, REQ-MP-902

The `MicroPrimeEngine` SHALL add a `_handle_moderate` method that sits between classification and escalation. When an element is classified MODERATE, the engine attempts decomposition before falling back to escalation.

**Modified routing in `engine.py`:**

```python
# Current (engine.py:262-284):
if tier == TierClassification.TRIVIAL:
    result = self._handle_trivial(...)
elif tier == TierClassification.SIMPLE:
    result = self._handle_simple(...)
else:
    # MODERATE/COMPLEX — immediate escalation
    result = ElementResult(... escalation=...)

# Proposed:
if tier == TierClassification.TRIVIAL:
    result = self._handle_trivial(...)
elif tier == TierClassification.SIMPLE:
    result = self._handle_simple(...)
elif tier == TierClassification.MODERATE:
    result = self._handle_moderate(
        element, file_spec, skeleton, contracts,
        file_path, reasoning,
        design_doc_sections=design_doc_sections,
    )
else:
    # COMPLEX only — immediate escalation
    result = ElementResult(... escalation=...)
```

**`_handle_moderate` flow:**

```
_handle_moderate(element, file_spec, manifest, skeleton, ...)
  |
  +-- self._circuit_open? --> YES --> return ElementResult(escalation=CIRCUIT_BREAKER) [R1-S1]
  |
  +-- decomposition_enabled? --> NO --> return ElementResult(escalation=TIER_TOO_HIGH)
  |
  +-- plan = decomposer.decompose(element, file_spec, manifest, reason)  [R3-S2: single entry point]
  |     |
  |     +-- plan is None --> return ElementResult(escalation=NOT_DECOMPOSABLE)
  |     |
  |     +-- plan exists --> for sub_element in plan.sub_elements (ordered):
  |                           |
  |                           +-- sub.deterministic? --> extract from skeleton [R3-S7]
  |                           |
  |                           +-- else --> _handle_simple(sub_element.element_spec, ...)
  |                           |     |
  |                           |     +-- failed? --> rollback staged cache, escalate original
  |                           |
  |                           +-- all succeeded --> assemble(plan, sub_results)
  |                                                  --> _structural_verify(assembled) [R3-S4]
  |                                                  --> ElementResult(success=True)
```

**Acceptance criteria:**

- MODERATE elements where `decompose()` returns a plan are attempted locally before escalation [R3-S2: single entry point]
- COMPLEX elements are never routed to `_handle_moderate` — they go directly to escalation
- If decomposition produces a plan but any sub-element fails generation/repair/verification, the entire decomposition is abandoned and the original element is escalated with `EscalationReason.DECOMPOSITION_FAILED`
- Successfully decomposed elements are recorded in the few-shot completed list (for subsequent SIMPLE elements to benefit from)
- The circuit breaker (R3-S2) applies to sub-element failures — 3 consecutive sub-element failures trips the breaker
- Deterministic sub-elements (e.g., `class_shell`) do not count toward circuit breaker failure attempts
- `_handle_moderate` checks `self._circuit_open` before any decomposition work; if open, returns `EscalationReason.CIRCUIT_BREAKER` immediately [R1-S1]
- `_handle_moderate` receives `manifest: ForwardManifest` as a parameter, threaded from `process_file()` where the manifest is available [R1-S4]
- After successful decomposition and assembly, the original MODERATE element's fingerprint (`f"{parent_class}:{name}:{file_path}:{tier.value}"`) is added to `_success_cache` to avoid re-decomposition on cache-eligible re-encounters [R1-S7]
- When `decomposition_enabled=False`, `_handle_moderate` returns immediate escalation with `EscalationReason.TIER_TOO_HIGH` to preserve pre-change behavior
- Assembled output MUST be passed through `_structural_verify(assembled_code, original_element)` before returning `success=True`. Assembly validation failure escalates with `EscalationReason.DECOMPOSITION_FAILED`. [R3-S4]
- Sub-elements are generated on a scratch skeleton (or with splicing disabled) and only committed to the real skeleton after successful assembly to avoid partial writes on failed decomposition
- Sub-element successes are staged; if decomposition fails, no sub-element successes are added to `_success_cache` or few-shot history
- `_handle_moderate` is independently testable with mock Ollama responses
- When `decomposer.decompose()` returns `None`, routing and outputs match the current engine; only the escalation reason changes to `NOT_DECOMPOSABLE` when decomposition is enabled [R3-S2]

---

### REQ-MP-904: Assembly Strategies

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-901, REQ-MP-902

The decomposer SHALL define assembly strategies that compose sub-element results into the complete MODERATE element's code.

**Assembly strategies:**

| Strategy | Trigger | Assembly Logic |
|----------|---------|----------------|
| `class_compose` | REQ-MP-901 class decomposition | Insert class-level attributes and `__init__` body into the class shell. Methods are NOT assembled here — they are separate elements handled by the splicer. |
| `function_chain` | REQ-MP-902 function decomposition | Concatenate helper definitions, then append the dispatch body. Helpers are module-level for functions and class-scoped private methods for methods. |
| `sequential_body` | Future: multi-step function bodies | Concatenate body segments in order. |

**`class_compose` assembly:**

```python
def assemble_class(
    plan: DecompositionPlan,
    sub_results: dict[str, str],   # sub_element.name -> generated code
    skeleton: str,
) -> Optional[str]:
    """Assemble a class from its decomposed sub-elements.

    The class shell is already in the skeleton. This method:
    1. Extracts the class node from the skeleton (preserving declaration + docstring)
    2. Inserts class-level attributes (if any) after the docstring
    3. Inserts __init__ body (if any) after attributes
    4. Returns the updated class source

    Methods are NOT inserted here — they are separate manifest elements
    handled by splice_body_into_skeleton() in the normal engine loop.
    """
```

**`function_chain` assembly:**

```python
def assemble_function_chain(
    plan: DecompositionPlan,
    sub_results: dict[str, str],
) -> Optional[str]:
    """Assemble a function from dispatch body + helpers.

    Returns a code block containing:
    1. Helper function definitions (in dependency order)
    2. The main function with dispatch body

    The helpers are placed immediately before the main function
    in the output, so they are available when the main function
    is spliced into the skeleton.

    For METHOD/ASYNC_METHOD elements, helpers are inserted into the
    class body before the main method, preserving class scope.
    """
```

**Assembly validation:**

After assembly, the composed code MUST pass:

1. `ast.parse()` — syntactically valid
2. The original element name exists in the AST (function def or class def). For CLASS elements, `_structural_verify` SHALL check `ast.ClassDef.name == element.name` (currently unvalidated — engine.py:638-677 only checks CONSTANT/VARIABLE). [R1-S3]
3. No `raise NotImplementedError` remains in any assembled body
4. `pass` remains only when the class has no attributes or `__init__` sub-elements (i.e., truly empty shells)

If validation fails, the assembly is rejected and the original element is escalated.

**Acceptance criteria:**

- `class_compose` produces valid Python with correct indentation for class-level code
- `function_chain` produces valid Python with helpers before the main function
- Assembly output passes `ast.parse()` and structural verification
- Assembly failure escalates the original element (does not crash the pipeline)
- Assembly preserves the original element's decorators, base classes, and type annotations
- Assembly replaces existing skeleton stubs rather than duplicating definitions (class and function)
- `sub_results` dict keys are always `SubElement.name`, never `element_spec.name`, to avoid ambiguity when the synthetic spec's name differs (e.g., `_class_attributes` vs the element spec name) [R1-Q2]

---

### REQ-MP-905: Synthetic Element Spec Construction

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-900

When decomposing a MODERATE element into sub-elements, the decomposer SHALL construct **synthetic `ForwardElementSpec` instances** for sub-elements that don't exist in the manifest.

**Why:** The engine's `_handle_simple` method requires a `ForwardElementSpec` to build prompts, run repair, and verify structure. Sub-elements like `__init__` or helper functions may not have entries in the original manifest.

**Construction rules:**

| Sub-element Kind | `name` | `kind` | `signature` | `parent_class` | `docstring_hint` |
|-----------------|--------|--------|-------------|----------------|------------------|
| `class_shell` | Original element name | `ElementKind.CLASS` | None | None | Original docstring |
| `init` | `__init__` | `ElementKind.METHOD` | Inferred from class context | Original class name | "Initialize {class_name}." |
| `class_attr` | `_class_attributes` | `ElementKind.CONSTANT` | None | Original class name | "Class-level attributes for {class_name}." |
| `helper` | `_{responsibility_slug}` | `ElementKind.FUNCTION` / `ASYNC_FUNCTION` for function parents; `ElementKind.METHOD` / `ASYNC_METHOD` for method parents (async preserved when awaited) | Inferred from dispatch context | Original parent (if method) | From decomposition analysis |
| `dispatch_body` | Original element name | Same as original | Same as original | Same as original | "Dispatch to helper functions." |

**Async propagation rules:** When the original element is `ASYNC_FUNCTION` or `ASYNC_METHOD`, helpers that are awaited in the dispatch body MUST use `ElementKind.ASYNC_FUNCTION` (or `ASYNC_METHOD` if class-scoped). Helpers that perform only synchronous work (e.g., validation, formatting) MAY remain synchronous. The dispatch body preserves the original async kind. [R1-Q4]

**Signature inference for helpers:**

Helper signatures are inferred from the parent function's parameters:

- Each helper receives the subset of parent params it needs (determined by docstring/design section analysis)
- Return type is inferred: `None` for side-effect helpers, parent's return type for the final helper in the chain
- If signature inference for any helper is uncertain (cannot determine specific parameters), abort plan construction and return `None` from `plan()` — the element is non-decomposable. An underspecified `(*args, **kwargs) -> Any` signature gives Ollama zero parameter guidance and almost always produces unusable code; the repair pipeline cannot compensate for fundamentally underspecified prompts. [R3-S6]
- For methods, `self`/`cls` is always the first parameter and never omitted during inference

**Acceptance criteria:**

- Synthetic specs pass `ForwardElementSpec` validation (all required fields populated)
- Synthetic specs produce valid prompts when passed to `build_body_prompt()`
- The repair pipeline handles synthetic specs correctly (signature reconciliation uses the synthetic signature)
- Synthetic specs are distinguishable from manifest-origin specs via a `synthetic: bool` field or equivalent marker

---

### REQ-MP-906: Decomposition Metrics and Observability

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-900, REQ-MP-903, REQ-MP-600 (observability layer)

The decomposer SHALL emit metrics and log events for observability.

**New metrics (extending REQ-MP-600):**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `micro_prime.decomposition_attempted` | Counter | `strategy`, `file_path` | Decomposition plans created |
| `micro_prime.decomposition_succeeded` | Counter | `strategy`, `file_path` | Plans where all sub-elements succeeded |
| `micro_prime.decomposition_failed` | Counter | `strategy`, `file_path`, `failure_reason` | Plans abandoned (sub-element failure, assembly failure) |
| `micro_prime.decomposition_rejected` | Counter | `file_path`, `rejection_reason` | Elements where `decompose()` returned None. `rejection_reason` is bounded: `no_strategy`, `metaclass`, `complex_decorator`, `api_dependency`, `orchestrator`, `too_many_attributes`, `confidence_below_threshold`, `max_sub_elements_exceeded`, `signature_inference_failed`. [R3-S5] |
| `micro_prime.sub_elements_generated` | Counter | `strategy`, `tier` | Individual sub-element generation attempts |
| `micro_prime.decomposition_time_ms` | Histogram | `strategy` | End-to-end time for decompose + generate + assemble |

**New escalation reason:**

```python
class EscalationReason(str, Enum):
    # ... existing reasons ...
    DECOMPOSITION_FAILED = "decomposition_failed"   # Sub-element or assembly failed
    NOT_DECOMPOSABLE = "not_decomposable"           # can_decompose() returned False
```

**Log events:**

```
[INFO]  Decomposing CustomJsonFormatter (MODERATE) via class_decompose: 1 sub-elements
[INFO]  Sub-element class_shell: deterministic extraction from skeleton (0ms)
[INFO]  Decomposition succeeded for CustomJsonFormatter: 1/1 sub-elements, 0ms total
```

```
[INFO]  Decomposing process_order (MODERATE) via function_chain: 4 sub-elements
[INFO]  Sub-element _validate_order_fields: SIMPLE generation (4200ms, 180+45 tokens)
[INFO]  Sub-element _compute_totals: SIMPLE generation (3100ms, 210+62 tokens)
[WARN]  Sub-element _format_confirmation: generation failed (AST failure after repair)
[WARN]  Decomposition abandoned for process_order — escalating to cloud
```

**Dry-run report extension (REQ-MP-906a):**

The dry-run classification report (`MicroPrimeCodeGenerator._format_dry_run_report`) SHALL include decomposition analysis for MODERATE elements:

```
  src/emailservice/logger.py (5 elements, skeleton: 45 lines)
    SIMPLE     add_fields                          0 params; simple return (None)
    SIMPLE     format                              1 params; simple return (str)
    SIMPLE     getJSONLogger                       1 params
    SIMPLE     get_logger                          1 params; simple name prefix
    MODERATE   CustomJsonFormatter                 class definition; long docstring
               -> DECOMPOSABLE (class_decompose): 1 sub-element [class_shell: TRIVIAL]
    -> 4 local, 0 escalated, 1 decomposable (5 effective local)
```

`can_decompose()` MUST rely only on data available in dry-run mode (no LLM calls, no I/O, no runtime-only artifacts) to avoid report/runtime divergence.

**Postmortem report extension:**

The `prime-postmortem-report.json` element entries SHALL include decomposition metadata when applicable:

```json
{
  "element_name": "CustomJsonFormatter",
  "tier": "moderate",
  "success": true,
  "decomposition": {
    "strategy": "class_decompose",
    "sub_elements": 1,
    "sub_element_results": [
      {"name": "class_shell", "kind": "class_shell", "success": true, "time_ms": 0}
    ],
    "assembly_time_ms": 1,
    "total_time_ms": 1
  }
}
```

**Acceptance criteria:**

- All 6 metrics are emitted via the existing OTel meter (`startd8.micro_prime`)
- `DECOMPOSITION_FAILED` and `NOT_DECOMPOSABLE` are added to `EscalationReason` enum
- `NOT_DECOMPOSABLE` is used when `can_decompose()` returns False **and** `decomposition_enabled=True`; when decomposition is disabled, `TIER_TOO_HIGH` is preserved
- Dry-run report shows decomposition viability for every MODERATE element
- Postmortem report includes decomposition metadata for elements that were decomposed
- Log messages include element name, strategy, sub-element count, and timing
- If metrics labeling in REQ-MP-600 discourages high-cardinality labels, `file_path` MAY be reduced to basename or a stable file id
- Deterministic sub-elements (e.g., `class_shell`) do not increment `micro_prime.sub_elements_generated`; if counted, they MUST include a `deterministic=true` label

---

### REQ-MP-907: Decomposition Strategy Registry

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-900, REQ-MP-901, REQ-MP-902

Decomposition strategies SHALL be registered in an extensible registry, allowing new strategies to be added without modifying the `ModerateDecomposer` core.

**Registry interface:**

```python
class DecompositionStrategy(Protocol):
    """Protocol for pluggable decomposition strategies."""

    @property
    def name(self) -> str:
        """Unique strategy name (e.g. 'class_decompose', 'function_chain')."""
        ...

    def can_handle(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
    ) -> bool:
        """Fast check: can this strategy decompose this element?"""
        ...

    def plan(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
    ) -> Optional[DecompositionPlan]:
        """Produce a decomposition plan, or None on failure."""
        ...

    def assemble(
        self,
        plan: DecompositionPlan,
        sub_results: dict[str, str],
        skeleton: str,
    ) -> Optional[str]:
        """Compose sub-element results into the complete element code."""
        ...
```

Strategies MUST compute confidence via the shared `_compute_confidence(plan, uncertainty_signals)` module-level function (defined in REQ-MP-900). This ensures the `decomposition_confidence_threshold` setting is meaningful across all strategies. Strategies call `_compute_confidence` internally within `plan()` and set `DecompositionPlan.confidence` before returning. [R3-S3]

**Strategy selection order:**

The decomposer SHALL try strategies in priority order and use the first one that returns `can_handle() == True`:

| Priority | Strategy | Element Kind |
|----------|----------|-------------|
| 1 | `class_decompose` | CLASS |
| 2 | `function_chain` | FUNCTION, METHOD, ASYNC_FUNCTION, ASYNC_METHOD |

If no strategy handles the element, `can_decompose()` returns `False`.

**Acceptance criteria:**

- Strategies implement the `DecompositionStrategy` protocol
- `ModerateDecomposer.__init__` accepts an optional list of strategies (defaults to built-in set)
- Strategies are tried in priority order; first match wins
- Adding a new strategy requires only implementing the protocol and registering it — no changes to `ModerateDecomposer` or `MicroPrimeEngine`

---

### REQ-MP-908: Configuration

**Status:** planned
**Priority:** P2
**Depends on:** REQ-MP-900

The decomposer SHALL be configurable via `MicroPrimeConfig`.

**New config fields:**

```python
class MicroPrimeConfig(BaseModel):
    # ... existing fields ...

    # Decomposer settings (REQ-MP-908)
    decomposition_enabled: bool = True
    max_sub_elements: int = 5            # Reject plans with more sub-elements
    max_helpers_per_function: int = 4    # REQ-MP-902 constraint
    decomposition_confidence_threshold: float = 0.6  # Minimum plan confidence to attempt
    class_decompose_enabled: bool = True
    function_chain_enabled: bool = True
```

**Interaction with existing config:**

- When `decomposition_enabled = False`, `_handle_moderate` falls through to immediate escalation (current behavior)
- When `escalation_enabled = False`, decomposition is still attempted (it's a local-only operation)
- `dry_run = True` reports decomposition viability without executing

**Acceptance criteria:**

- `decomposition_enabled = False` produces identical behavior to current engine (no regression)
- `max_sub_elements` is enforced — plans exceeding it are rejected
- Strategies check `max_sub_elements` before emitting a plan to avoid wasted work
- `decomposition_confidence_threshold` filters low-confidence plans
- Individual strategies can be toggled independently
- All config fields have safe defaults that match the behavior described in REQ-MP-901 and REQ-MP-902

---

### REQ-MP-909: Prime Adapter Integration

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-903, REQ-MP-906

The `MicroPrimeCodeGenerator` (prime_adapter.py) SHALL reflect decomposition results in its metadata and reporting.

**Changes to `prime_adapter.py`:**

1. **Metadata enrichment:** The `GenerationResult.metadata` dict SHALL include:
   - `micro_prime_decomposed_count`: Number of MODERATE elements successfully decomposed
   - `micro_prime_decomposition_failures`: Number of decomposition attempts that failed and escalated
   - Per-file element results already include `ElementResult` — decomposed elements will have `success=True` with `tier=MODERATE`

2. **Cost report fields:** `MicroPrimeCostReport` (models.py:153-168) SHALL add `decomposed_count: int = 0` and `decomposition_failure_count: int = 0`. A successfully decomposed MODERATE element increments `decomposed_count` (and `local_success_count`). A failed decomposition increments `decomposition_failure_count` (and `escalated_count`). [R1-S5]

3. **Element-level escalation path:** The existing `_escalate_elements_to_cloud` method (line 692) handles elements where some succeeded and some escalated. Decomposed elements that succeed are treated identically to successful SIMPLE elements — they stay in the partial skeleton. Decomposition failures join the escalation batch.

4. **Mottainai interaction:** The existing file-level escalation guard (line 297: "only delegate the whole file to fallback when ZERO elements succeeded locally") is unchanged. A successfully decomposed MODERATE element counts as a local success.

5. **Dry-run path:** `_dry_run_classify` SHALL call `decomposer.can_decompose()` for each MODERATE element and annotate the report per REQ-MP-906a.

**Acceptance criteria:**

- A feature with 4 SIMPLE + 1 decomposable MODERATE element reports `micro_prime_only: true` and `micro_prime_elements: 5`. Explicitly: a successfully decomposed MODERATE element (which uses Ollama for sub-elements, not cloud) counts as a local success and does NOT break `micro_prime_only`. Only cloud escalation breaks it. [R3-Q3]
- A feature with 4 SIMPLE + 1 non-decomposable MODERATE element behaves identically to current code (escalation or fallback)
- Dry-run mode shows decomposition viability without invoking Ollama
- Postmortem report includes decomposition metadata per REQ-MP-906

---

## Data Flow

```
classify_element()
  |
  +-- TRIVIAL --> _handle_trivial() --> template --> splice
  |
  +-- SIMPLE  --> _handle_simple()  --> Ollama --> repair --> verify --> splice
  |
  +-- MODERATE --> _handle_moderate()  [NEW]
  |     |
  |     +-- self._circuit_open? --> YES --> escalate (EscalationReason.CIRCUIT_BREAKER) [R3-S1]
  |     |
  |     +-- decomposition_enabled?
  |     |     |
  |     |     +-- NO --> escalate (EscalationReason.TIER_TOO_HIGH)
  |     |     |
  |     +-- plan = decomposer.decompose()?  [R3-S2: single entry point]
  |     |     |
  |     |     +-- plan is None --> escalate (EscalationReason.NOT_DECOMPOSABLE)
  |     |     |
  |     |     +-- plan exists --> for sub in plan.sub_elements:
  |     |                    |     +-- deterministic? --> extract from skeleton
  |     |                    |     +-- else --> _handle_simple(synthetic_spec)
  |     |                    |           +-- failed? --> rollback staged cache, escalate original
  |     |                    |
  |     |                    +-- all OK --> assemble(plan, results)
  |     |                    |               +-- _structural_verify(assembled) [R3-S4]
  |     |                    |               +-- verify failed? --> escalate original
  |     |                    |               +-- OK --> splice
  |     |
  +-- COMPLEX --> escalate (EscalationReason.TIER_TOO_HIGH)
```

---

## Traceability

| Requirement | Modifies | New Files | Tests |
|-------------|----------|-----------|-------|
| REQ-MP-900 | — | `micro_prime/decomposer.py` | `tests/unit/micro_prime/test_decomposer.py` |
| REQ-MP-901 | — | (in decomposer.py) | `test_class_decomposition_strategy` |
| REQ-MP-902 | `micro_prime/classifier.py` | (in decomposer.py) | `test_function_decomposition_strategy`, `test_classification_signals` |
| REQ-MP-903 | `micro_prime/engine.py` | — | `test_handle_moderate`, `test_decomposition_fallback_to_escalation` |
| REQ-MP-904 | — | (in decomposer.py) | `test_class_compose_assembly`, `test_function_chain_assembly` |
| REQ-MP-905 | — | (in decomposer.py) | `test_synthetic_element_spec` |
| REQ-MP-906 | `micro_prime/models.py`, `micro_prime/prime_adapter.py` | — | `test_decomposition_metrics`, `test_dry_run_decomposition`, `test_rejection_reason_bounded` |
| REQ-MP-907 | — | (in decomposer.py) | `test_strategy_registry_ordering` |
| REQ-MP-908 | `micro_prime/models.py` | — | `test_decomposition_config_disabled` |
| REQ-MP-909 | `micro_prime/prime_adapter.py` | — | `test_prime_adapter_decomposition_metadata` |

---

## Verification Strategy

### Unit Tests

| Test | Validates |
|------|-----------|
| `test_class_shell_extraction` | Class shell is extracted from skeleton without LLM |
| `test_class_with_init_decomposition` | Class with `__init__` produces 2 sub-elements (shell + init) |
| `test_class_without_init_decomposition` | Class without `__init__` produces 1 sub-element (shell only) |
| `test_class_methods_already_separate` | Methods already in manifest are excluded from plan |
| `test_class_attr_detection_from_manifest` | Class-level attributes are detected only from manifest elements |
| `test_non_decomposable_class_metaclass` | Metaclass class rejected by `can_decompose()` |
| `test_function_chain_2_helpers` | Function with 2 responsibilities decomposes into 2 helpers + dispatch |
| `test_function_chain_max_helpers` | Function with 5+ responsibilities rejected |
| `test_function_api_dependency_rejected` | Function moderate due to API hint is not decomposable |
| `test_classification_signals` | Classifier emits `ClassificationSignal` set for API/orchestrator detection |
| `test_helper_name_fallback` | Helper naming falls back to `_helper_n` when slug is invalid/too long |
| `test_sub_element_failure_abandons_plan` | One failed sub-element escalates the original |
| `test_failed_decomposition_does_not_commit_sub_elements` | Sub-element successes are not cached on failed decomposition |
| `test_assembly_ast_validation` | Assembled code passes `ast.parse()` |
| `test_assembly_preserves_decorators` | Decorators on original element survive assembly |
| `test_decomposition_disabled_config` | `decomposition_enabled=False` produces identical behavior to current |
| `test_dry_run_shows_decomposable` | Dry-run report annotates MODERATE elements with decomposition viability |
| `test_circuit_breaker_applies_to_sub_elements` | 3 sub-element failures trip the breaker |
| `test_pi_001_classifier_pinning` | `@pytest.mark.parametrize` fixture hard-codes expected tier (`MODERATE`) and reasoning string for `CustomJsonFormatter` to catch classifier drift across scoring constant changes [R1-Q3] |
| `test_decompose_single_entry_point` | `decompose()` returns plan directly without separate `can_decompose()` call in generation path [R3-S2] |
| `test_confidence_uses_shared_formula` | Both `ClassDecomposeStrategy` and `FunctionChainStrategy` compute confidence via `_compute_confidence()` [R3-S3] |
| `test_assembled_output_structural_verify` | Assembled code is passed through `_structural_verify` before `success=True` [R3-S4] |
| `test_rejection_reason_bounded` | `decomposition_rejected` metric uses only values from the bounded `rejection_reason` set [R3-S5] |
| `test_uncertain_signature_rejects_plan` | Helper with uncertain signature aborts plan construction (no `*args, **kwargs` fallback) [R3-S6] |

### Integration Tests

| Test | Validates |
|------|-----------|
| `test_pi_001_logger_full_local` | PI-001 emailservice logger produces 5/5 elements locally (4 SIMPLE + 1 decomposed MODERATE) |
| `test_mixed_decomposable_and_cloud` | File with decomposable + non-decomposable MODERATE elements routes correctly |
| `test_decomposition_with_fallback` | Failed decomposition delegates to cloud fallback seamlessly |

---

## Implementation Order

| Phase | Requirements | Rationale |
|-------|-------------|-----------|
| 1 | REQ-MP-900, REQ-MP-901, REQ-MP-904 (class_compose only), REQ-MP-903 | Class decomposition is the highest-value case (PI-001 validates immediately) |
| 2 | REQ-MP-907, REQ-MP-908, REQ-MP-909, REQ-MP-906 | Registry, config, adapter integration, observability |
| 3 | REQ-MP-902, REQ-MP-904 (function_chain), REQ-MP-905 | Function decomposition requires synthetic spec construction and is lower priority |

---

## Convergent Review — Round R1 (Triaged)

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 16:00 UTC
- **Scope**: Source-code-validated feasibility pass — validated plan against `engine.py` (678L), `classifier.py` (312L), and `models.py` (169L)

### Findings

| ID | Area | Severity | Finding | Source Reference | Proposed Fix |
|----|------|----------|---------|-----------------|-------------|
| R1-S1 | Correctness | high | **Circuit breaker check excludes MODERATE tier.** `_process_element_with_tier` (engine.py:233-236) applies the open-circuit early-exit only for `TRIVIAL` and `SIMPLE`. When `_handle_moderate` calls `_handle_simple` for sub-elements, the sub-elements **will** hit the circuit breaker — but the MODERATE-tier `_handle_moderate` dispatch itself (engine.py:269) is not guarded. If the circuit is open when `_handle_moderate` is entered, the decomposer runs and calls `_handle_simple` — which then escalates each sub-element individually, acting as if the circuit is open for each. The net effect is usually correct, but REQ-MP-903 should explicitly state "if `self._circuit_open`, skip `_handle_moderate` and escalate immediately with `EscalationReason.CIRCUIT_BREAKER`" for clarity and to avoid unnecessary decomposition planning work. | `engine.py:232-259`, `engine.py:269-284` | Add explicit circuit breaker gate in `_handle_moderate` before calling `decomposer.can_decompose()`. |
| R1-S2 | Correctness | high | **`classification_reason` string matching is fragile.** REQ-MP-902 heuristic excludes functions classified MODERATE due to "external API" or "orchestrator" by testing if `classification_reason` contains those strings. However, `classifier.py` produces reasons like `"file has 9 external imports (>8)"` (line 251), `"docstring references complex API: http"` (line 261), and `"orchestrator name (run)"` (line 101). The substring `"external API"` does **not** appear in the file-level import reason string — it would be silently missed, incorrectly marking import-heavy functions as decomposable. Add: "API-hint check MUST also match `'external imports'` in the reason string, or use an enum-based `ClassificationSignal` added to `classify_element`'s return value." | `classifier.py:248-263`, `REQ-MP-902` applicability heuristic | Either extend the reason-string matching list, or add a `ClassificationSignal` enum to `classify_element` return type to avoid fragile substring parsing. |
| R1-S3 | Correctness | medium | **`_structural_verify` never validates CLASS definitions.** REQ-MP-904 assembly validation states "the original element name exists in the AST (function def or class def)" — but `_structural_verify` (engine.py:638-677) only checks `CONSTANT`/`VARIABLE` assignments, then returns `True` for all other kinds without checking for the class definition. Assembled class shells passed through `_handle_simple(class_shell_spec)` will not be verified to contain the correct class name. This means a malformed class shell could pass verification and produce broken code. | `engine.py:638-677`, REQ-MP-904 assembly validation AC1 | Extend `_structural_verify` to check `ast.ClassDef.name == element.name` when `element.kind == ElementKind.CLASS`, or add assembly-specific verification in `assemble_class()` before returning. |
| R1-S4 | Correctness | medium | **`_handle_simple` signature missing `manifest` parameter.** REQ-MP-903 shows `_handle_moderate(element, file_spec, skeleton, contracts, file_path, reasoning, design_doc_sections)` calling `decomposer.decompose(element, file_spec, manifest, reason)` — but `manifest` is only available in `process_file()`, not passed down to `_handle_simple` or `_handle_trivial`. The decomposer needs `manifest` to check `parent_class == element.name` for the class strategy (REQ-MP-901). Either `_handle_moderate` must receive `manifest` as a parameter, or the decomposition plan must be built at `process_file` level where manifest is available. | `engine.py:305-380` (`process_file` has manifest), `engine.py:458-588` (`_handle_simple` does not) | Add `manifest: ForwardManifest` parameter to `_handle_moderate` and update `process_file`'s inner loop to pass it. |
| R1-S5 | Completeness | medium | **`MicroPrimeCostReport` has no decomposition tracking fields.** REQ-MP-909 says `GenerationResult.metadata` gets `micro_prime_decomposed_count` and `micro_prime_decomposition_failures`, but `MicroPrimeCostReport` (models.py:153-168) — which aggregates counts for observability — has no `decomposed_count` or `decomposition_failure_count` fields. A successfully decomposed MODERATE element currently increments neither `local_success_count` (it succeeded) nor `escalated_count` (it didn't escalate), but its origin as MODERATE is lost. Add `decomposed_count: int = 0` and `decomposition_failure_count: int = 0` to `MicroPrimeCostReport`. | `models.py:153-168`, REQ-MP-909 | Add two fields to `MicroPrimeCostReport` and populate them in the prime adapter's cost aggregation. |
| R1-S6 | Robustness | medium | **`DecompositionPlan.confidence` scoring is unspecified.** REQ-MP-900 declares `confidence: float` on `DecompositionPlan` and REQ-MP-908 adds `decomposition_confidence_threshold=0.6`, but nowhere in the document is the confidence scoring formula defined. Without a documented formula, each strategy will score differently, the threshold becomes meaningless, and tests cannot assert expected values. Define: "Confidence is computed as `1.0 - (uncertainty_signals / max_uncertainty)` where uncertainty signals include: missing `__init__` in manifest (−0.1), inferred helper signatures (−0.1 per helper), parse-only responsibility detection (−0.1), class-level attribute count >1 (−0.1)." | REQ-MP-900, REQ-MP-908 | Add a `_compute_confidence(plan: DecompositionPlan, signals: list[str]) -> float` utility to the module with documented formula. |
| R1-S7 | Correctness | low | **Success cache doesn't store decomposed MODERATE element fingerprint.** REQ-MP-903 AC says "successfully decomposed elements are recorded in the few-shot completed list." The success cache fingerprint (engine.py:217) uses `f"{parent_class}:{name}:{file_path}:{tier.value}"`. Sub-elements are cached under their own names + `TRIVIAL`/`SIMPLE` tier. The original MODERATE element's fingerprint is never added, so if the same element appears again (e.g., cross-file template reuse), it would be re-decomposed rather than cache-hit. Add: "After successful decomposition, add the original MODERATE element's fingerprint to `_success_cache`." | `engine.py:217-230`, `engine.py:286-300`, REQ-MP-903 | Add explicit `_success_cache.add(moderate_fingerprint)` after successful assembly in `_handle_moderate`. |
| R1-S8 | Architecture | low | **Pre-classification sort order treats MODERATE = COMPLEX (priority 2).** `_TIER_PRIORITY` (engine.py:95-100) maps both MODERATE and COMPLEX to priority 2, so within a file they're sorted together alphabetically. With the decomposer, MODERATE elements that succeed locally should be treated more like SIMPLE (priority 1) — their successful sub-elements feed few-shot context. Consider: "After decomposition planning at `process_file` level, pre-classified MODERATE elements with viable decomposition plans can be hoisted to priority 1.5 to run before non-decomposable MODERATE and COMPLEX elements." This ensures decomposed helpers are in the few-shot context before truly unhandleable elements are encountered. | `engine.py:95-100`, `engine.py:350` | Add logic during pre-classification to annotate decomposable MODERATE elements and sort them before non-decomposable MODERATE/COMPLEX. |

### Quick Wins

| ID | Area | Severity | Suggestion |
|----|------|----------|-----------|
| R1-Q1 | Editorial | low | Superseded by R2-S1. Final behavior preserves `TIER_TOO_HIGH` when decomposition is disabled; `NOT_DECOMPOSABLE` is used only when decomposition is enabled and no strategy applies. |
| R1-Q2 | Interfaces | low | `SubElement.element_spec` is `Optional[ForwardElementSpec]` with note "None allowed for deterministic class_shell". However REQ-MP-904 assembly passes `sub_results: dict[str, str]` keyed by `sub_element.name`. Clarify: the dict key is always `SubElement.name`, not `element_spec.name`, to avoid confusion when the spec's name differs (e.g., `_class_attributes` vs the synthetic name). |
| R1-Q3 | Testing | low | The integration test `test_pi_001_logger_full_local` (REQ-MP-906 verification) should be pinned to the specific classifier version that produced score=+1 for `CustomJsonFormatter`. If classifier constants change (e.g., `class_score_bonus` tuning), the test may regress silently. Add a `@pytest.mark.parametrize` for the PI-001 fixture that hard-codes the expected tier+reasoning string to catch classifier drift. |
| R1-Q4 | Completeness | low | REQ-MP-905 synthetic spec construction table (lines 372-378) shows `dispatch_body` with `kind` "Same as original" — but for `ASYNC_METHOD`, `ElementKind.ASYNC_METHOD` is correct and the helpers (listed as `ElementKind.FUNCTION`) should be `ElementKind.ASYNC_FUNCTION` to preserve `async def` semantics. Update the table with explicit async propagation rules. |

### Triage Disposition

| ID | Disposition | Target | Notes |
|----|------------|--------|-------|
| R1-S1 | **ACCEPTED** | REQ-MP-903 | Circuit breaker gate added to `_handle_moderate` flow + AC |
| R1-S2 | **ACCEPTED** | REQ-MP-902 | Reason-string match list expanded; `ClassificationSignal` enum specified as target solution |
| R1-S3 | **ACCEPTED** | REQ-MP-904 | CLASS validation added to assembly validation rule #2 |
| R1-S4 | **ACCEPTED** | REQ-MP-903 | `manifest` parameter added to `_handle_moderate` signature + AC |
| R1-S5 | **ACCEPTED** | REQ-MP-909 | `decomposed_count` + `decomposition_failure_count` fields added to `MicroPrimeCostReport` |
| R1-S6 | **ACCEPTED** | REQ-MP-900 | Confidence formula documented with signal weights |
| R1-S7 | **ACCEPTED** | REQ-MP-903 | Success cache fingerprint added after successful assembly |
| R1-S8 | **DEFERRED** | REQ-MP-903 | Sort priority optimization deferred — adds complexity, not required for Phase 1 correctness |
| R1-Q1 | **ACCEPTED** | Data Flow | Superseded by R2-S1; final behavior preserves `TIER_TOO_HIGH` when decomposition is disabled |
| R1-Q2 | **ACCEPTED** | REQ-MP-904 | Dict key clarification added to ACs |
| R1-Q3 | **ACCEPTED** | Verification | Classifier drift pinning test added |
| R1-Q4 | **ACCEPTED** | REQ-MP-905 | Async propagation rules added to spec table |

---

## Convergent Review — Round R2 (Triaged)

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 18:30 UTC
- **Scope**: Robustness and regression-safety sweep after R1 integration

### Findings

| ID | Area | Severity | Finding | Source Reference | Proposed Fix |
|----|------|----------|---------|-----------------|-------------|
| R2-S1 | Correctness | high | **Decomposition-disabled path conflicts with "no regression".** REQ-MP-903 ACs say `decomposition_enabled=False` preserves pre-change behavior, but data flow and escalation reason usage route disabled cases to `NOT_DECOMPOSABLE`. This changes escalation reason semantics and can break tests/analytics. | REQ-MP-903 ACs, Data Flow, REQ-MP-906 ACs | When `decomposition_enabled=False`, `_handle_moderate` returns `EscalationReason.TIER_TOO_HIGH`; `NOT_DECOMPOSABLE` is only used when decomposition is enabled and no strategy applies. |
| R2-S2 | Correctness | high | **Sub-element generation can partially mutate skeleton/cache on failure.** `_handle_simple` may splice into the real skeleton and update success cache as it goes; if a later sub-element fails, the file is left partially modified and the few-shot cache polluted. | REQ-MP-903 flow, engine splicing behavior | Generate sub-elements on a scratch skeleton (or with splicing disabled) and stage cache updates; only commit skeleton/caches after full plan success. |
| R2-S3 | Robustness | medium | **Class-level attribute detection is underspecified.** The spec allows class attributes but doesn't define detection, leading to possible hallucinated attributes or inconsistent counts. | REQ-MP-901 applicability | Count class attributes only from `file_spec.elements` with `parent_class` and `kind in {CONSTANT, VARIABLE}`; generate `class_attr` only when such entries exist. |
| R2-S4 | Robustness | medium | **Helper naming can be invalid or unstable.** Docstring-derived slugs can be empty, too long, or collide with keywords/builtins, causing invalid code or noisy diffs. | REQ-MP-902 constraints | Add deterministic slug rules with length cap and fallback `_helper_{n}`; keep existing collision suffixing. |
| R2-S5 | Completeness | low | **ClassificationSignal adoption needs explicit acceptance.** The spec references `ClassificationSignal` but doesn't state fallback behavior or traceability tests for it. | REQ-MP-902 applicability, Traceability | Require `ClassificationSignal` when available; reason-string parsing is fallback only (emit debug log). Add classifier change to Traceability. |

### Quick Wins

| ID | Area | Severity | Suggestion |
|----|------|----------|-----------|
| R2-Q1 | Editorial | low | Clarify `function_chain` assembly scope: helpers are module-level for functions and class-scoped for methods. |
| R2-Q2 | Consistency | low | Update synthetic spec table to include METHOD/ASYNC_METHOD helper kinds. |
| R2-Q3 | Observability | low | Deterministic sub-elements should not increment `sub_elements_generated` (or must be labeled `deterministic=true`). |

### Triage Disposition

| ID | Disposition | Target | Notes |
|----|------------|--------|-------|
| R2-S1 | **ACCEPTED** | REQ-MP-903, REQ-MP-906, Data Flow | Preserve `TIER_TOO_HIGH` when decomposition is disabled. |
| R2-S2 | **ACCEPTED** | REQ-MP-903 | Stage splicing/cache updates; commit only on success. |
| R2-S3 | **ACCEPTED** | REQ-MP-901 | Class attr detection limited to manifest elements. |
| R2-S4 | **ACCEPTED** | REQ-MP-902 | Deterministic helper naming + fallback rule. |
| R2-S5 | **ACCEPTED** | REQ-MP-902, Traceability | Formalize `ClassificationSignal` use and tests. |
| R2-Q1 | **ACCEPTED** | REQ-MP-904 | Clarified scope in `function_chain` assembly description. |
| R2-Q2 | **ACCEPTED** | REQ-MP-905 | Helper kind table updated for methods/async. |
| R2-Q3 | **ACCEPTED** | REQ-MP-906 | Deterministic metric labeling clarified. |

---

## Convergent Review — Round R3 (Triaged)

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 16:18 UTC
- **Scope**: Correctness and interface completeness pass after R1+R2 integration — validated data flow, Protocol spec, and cross-cutting concerns

### Findings

| ID | Area | Severity | Finding | Source Reference | Proposed Fix |
|----|------|----------|---------|-----------------|-------------|
| R3-S1 | Correctness | high | **Data flow diagram has wrong check order.** The Data Flow section (line 675-677) shows `decomposition_enabled?` as the first gate inside `_handle_moderate`. But REQ-MP-903 AC (line 295) specifies `self._circuit_open` MUST be checked first (`[R1-S1]`). The diagram contradicts the AC — an open circuit would fall through to `decomposition_enabled?` instead of returning `CIRCUIT_BREAKER` immediately. This creates implementation ambiguity: which comes first? | REQ-MP-903 AC line 295, Data Flow lines 675-677 | Swap the gate order in the data flow: `self._circuit_open?` → `decomposition_enabled?` → `can_decompose()?`. Matches the approved AC from R1-S1. |
| R3-S2 | Performance | medium | **`can_decompose()` and `decompose()` perform a double strategy sweep.** `can_decompose()` iterates all strategies calling `can_handle()`. If it returns True, the engine immediately calls `decompose()` — which iterates all strategies again calling `can_handle()` a second time before calling `plan()`. For short strategy lists this is negligible, but it violates the DRY principle and creates a TOCTOU window (a strategy could theoretically respond differently on consecutive calls if strategies are stateful). Either: (a) `decompose()` is the single entry point and returning `None` signals "not decomposable", or (b) `can_decompose()` returns the matched strategy as an opaque token that `decompose()` accepts, skipping the second sweep. | REQ-MP-900 interface, REQ-MP-907 strategy selection | Remove the double sweep: make `decompose()` the sole entry point (returns `None` = not decomposable) and update the engine flow accordingly. |
| R3-S3 | Interface | medium | **`_compute_confidence` is not part of the `DecompositionStrategy` Protocol.** REQ-MP-900 defines `_compute_confidence(plan, signals) -> float` as a utility function. REQ-MP-907 defines the `DecompositionStrategy` Protocol. However, `_compute_confidence` is neither in the Protocol nor injected into strategies. Each strategy will independently implement confidence scoring with no guarantee of formula consistency — the `decomposition_confidence_threshold=0.6` setting becomes unstable: a plan scoring `0.7` in `ClassDecomposeStrategy` may represent entirely different confidence than `0.7` in `FunctionChainStrategy`. Either: add `confidence(self, plan) -> float` to the Protocol (strategies call `_compute_confidence` internally), or inject it as a shared utility into each strategy at construction time. | REQ-MP-900 (confidence formula), REQ-MP-907 (Protocol), REQ-MP-908 (threshold config) | Add `def confidence(self, plan: DecompositionPlan, signals: list[str]) -> float` to `DecompositionStrategy` Protocol, with the shared `_compute_confidence` implementation in a module-level function. |
| R3-S4 | Correctness | medium | **Assembled code is not passed through `_structural_verify`.** The `_handle_moderate` flow (line 284) goes: `assemble(plan, results) → ElementResult(success=True)` with no verification step. The existing SIMPLE path (engine.py:539) explicitly calls `_structural_verify(code, element)` before accepting generated code. REQ-MP-904 validation rules specify 4 assembly checks, but the flow diagram doesn't show where or how these are enforced. Without an explicit `_structural_verify` call on the assembled output, a structurally invalid class or function could be stored as `success=True`. | REQ-MP-904 assembly validation, engine.py:539, Data Flow line 284 | Add to REQ-MP-903 ACs: "Assembled output MUST be passed through `_structural_verify(assembled_code, original_element)` before returning `success=True`. Assembly validation failure escalates with `EscalationReason.DECOMPOSITION_FAILED`." |
| R3-S5 | Observability | medium | **`micro_prime.decomposition_rejected` label `rejection_reason` is unspecified.** REQ-MP-906 metric table (line 443) shows `rejection_reason` as a metric label for `decomposition_rejected`, but no valid values are enumerated. Without a bounded set, dashboards cannot be built and metric cardinality could grow unboundedly. Possible values include: `"no_strategy"`, `"metaclass"`, `"complex_decorator"`, `"api_dependency"`, `"orchestrator"`, `"too_many_attributes"`, `"confidence_below_threshold"`, `"max_sub_elements_exceeded"`. | REQ-MP-906 metric table, `can_decompose()` path | Add a bounded `RejectionReason` enum or literal type with the valid values, and require that `can_decompose()` — when returning False — produces a reason code from this set for metric labeling. |
| R3-S6 | Robustness | low | **`(*args, **kwargs) -> Any` signature fallback will degrade Ollama output quality with no circuit.** REQ-MP-905 line 416 says: "If inference is uncertain, use `(*args, **kwargs) -> Any` as a fallback." A helper spec with `*args, **kwargs` gives Ollama zero parameter guidance — the generated body cannot reference named parameters from the parent function, almost always producing incorrect or unusable code. Rather than accepting low-quality generation, this case should be treated as: "signature inference failed → this helper cannot be specified → decomposition is rejected for this element." The repair pipeline cannot compensate for fundamentally underspecified prompts. | REQ-MP-905 signature inference, REQ-MP-902 constraints | Replace "use `(*args, **kwargs)` as fallback" with "if signature inference for any helper is uncertain, abort plan construction and return `None` from `plan()` (element is non-decomposable)." |
| R3-S7 | Interface | low | **`SubElement.deterministic` is missing from the REQ-MP-900 interface definition.** The dataclass at lines 58-65 defines 6 fields (`name`, `kind`, `prompt_context`, `depends_on`, `assembly_order`, `element_spec`). But the implementation plan, PI-001 example (line 149: "class_shell — deterministic from skeleton, no LLM"), and the metric AC (line 519: "Deterministic sub-elements do not increment...") all rely on a `deterministic: bool` field to distinguish skeleton-extraction from LLM generation. Without this field on the interface, implementors must infer determinism from `kind == "class_shell"` or `element_spec is None` — both are fragile conventions. | REQ-MP-900 interface lines 58-65, REQ-MP-906 AC line 519 | Add `deterministic: bool = False` to `SubElement` with doc: "True = extract from skeleton without LLM; engine skips `_handle_simple` and does not increment generation counters." |

### Quick Wins

| ID | Area | Severity | Suggestion |
|----|------|----------|-----------|
| R3-Q1 | Editorial | low | REQ-MP-907 strategy priority table (lines 576-580) lists `function_chain` as priority 2. Add a `priority: int` field to the `DecompositionStrategy` Protocol so strategies self-declare their priority, enabling future strategies to insert at specific priorities without editing the base `ModerateDecomposer.__init__` ordering. |
| R3-Q2 | Robustness | low | REQ-MP-902 function decomposition (line 180): responsibility parsing splits on `"and"` as a clause separator. But Python docstrings often use `"and"` within a single clause: "Validate and sanitize the order fields" should be one responsibility, not two. Consider removing `"and"` from the split list and restricting splits to `;`, bullet markers, and enumerated prefixes only. |
| R3-Q3 | Completeness | low | REQ-MP-909 AC (line 657): "A feature with 4 SIMPLE + 1 decomposable MODERATE reports `micro_prime_only: true`." But `micro_prime_only` is defined in `prime_adapter.py` based on whether ALL elements were local. Confirm that a _decomposed_ MODERATE element (which calls Ollama for sub-elements) correctly sets `micro_prime_only: true`. If cloud escalation is used only when decomposition fails, this should hold — but it should be an explicit AC rather than implied. |

### Triage Disposition

| ID | Disposition | Target | Notes |
|----|------------|--------|-------|
| R3-S1 | **ACCEPTED** | Data Flow | Gate order fixed: `_circuit_open` → `decomposition_enabled` → `decompose()` |
| R3-S2 | **ACCEPTED** | REQ-MP-900, REQ-MP-903, Data Flow | `decompose()` is the single generation-path entry point; `can_decompose()` retained for dry-run only |
| R3-S3 | **ACCEPTED** | REQ-MP-907 | Strategies must use shared `_compute_confidence()` for cross-strategy threshold consistency |
| R3-S4 | **ACCEPTED** | REQ-MP-903 | `_structural_verify(assembled)` AC added before `success=True` |
| R3-S5 | **ACCEPTED** | REQ-MP-906 | Bounded `rejection_reason` values enumerated in metric table |
| R3-S6 | **ACCEPTED** | REQ-MP-905 | `(*args, **kwargs)` fallback replaced with plan rejection |
| R3-S7 | **ACCEPTED** | REQ-MP-900 | `deterministic: bool = False` field added to `SubElement` |
| R3-Q1 | **DEFERRED** | REQ-MP-907 | `priority: int` on Protocol is over-engineering for 2 strategies; revisit when a 3rd strategy is added |
| R3-Q2 | **ACCEPTED** | REQ-MP-902 | `"and"` removed from clause separators |
| R3-Q3 | **ACCEPTED** | REQ-MP-909 | `micro_prime_only` behavior with decomposed elements made an explicit AC |
