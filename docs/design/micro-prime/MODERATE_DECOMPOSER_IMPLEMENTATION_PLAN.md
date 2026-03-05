# Moderate Decomposer — Implementation Plan

> **Requirements:** [REQ-MP-9xx_MODERATE_DECOMPOSER.md](./REQ-MP-9xx_MODERATE_DECOMPOSER.md)
> **Date:** 2026-03-05
> **Validation target:** PI-001 `CustomJsonFormatter` — 5/5 elements local, $0.00

---

## Pre-Implementation Audit

### Files to Modify

| File | Change | Risk |
|------|--------|------|
| `micro_prime/engine.py:262-284` | Add `elif MODERATE` branch calling `_handle_moderate` | Medium — core routing change |
| `micro_prime/models.py:25-34` | Add 2 new `EscalationReason` members | Low — additive |
| `micro_prime/models.py:113-133` | Add decomposition config fields to `MicroPrimeConfig` | Low — defaults preserve behavior |
| `micro_prime/prime_adapter.py:384-397` | Add decomposition counts to metadata dict | Low — additive |
| `micro_prime/prime_adapter.py:461-477` | Annotate dry-run report with decomposition viability | Low — display only |
| `tests/unit/micro_prime/conftest.py` | Add class-element fixtures | Low — additive |

### New Files

| File | Purpose |
|------|---------|
| `micro_prime/decomposer.py` | `ModerateDecomposer`, strategies, assembly (~300 lines) |
| `tests/unit/micro_prime/test_decomposer.py` | Unit tests (~250 lines) |

### Invariants to Preserve

1. **COMPLEX elements never reach `_handle_moderate`** — the `elif` chain puts COMPLEX in the `else` branch
2. **`decomposition_enabled=False` produces identical behavior** — `_handle_moderate` returns escalation immediately
3. **Circuit breaker applies to sub-element failures** — sub-elements go through `_handle_simple` which already updates the breaker
4. **`ForwardElementSpec` is frozen** — synthetic specs are new instances, not mutations
5. **Existing `test_process_moderate_element_escalates` must still pass** — with `decomposition_enabled=False` or when `can_decompose()` returns False
6. **Deterministic sub-elements do not trip the circuit breaker** — only `_handle_simple` attempts affect breaker state
7. **Failed decompositions do not pollute few-shot history** — sub-element successes are staged and rolled back on failure

---

## Phase 1: Class Decomposition End-to-End

**Goal:** `CustomJsonFormatter` (MODERATE class) is generated locally at $0.00.

### Step 1.1 — Models: New Escalation Reasons + Config Fields

**File:** `micro_prime/models.py`

Add to `EscalationReason` enum (after `CIRCUIT_BREAKER`):

```python
DECOMPOSITION_FAILED = "decomposition_failed"
NOT_DECOMPOSABLE = "not_decomposable"
```

Add to `ElementResult` (after existing fields):

```python
decomposition_metadata: Optional[dict] = None  # strategy, sub_elements, timing [R1-S1: moved from Step 2.3]
```

Add to `MicroPrimeCostReport` (REQ-MP-909, R1-S5 from requirements review):

```python
decomposed_count: int = 0
decomposition_failure_count: int = 0
```

Add to `MicroPrimeConfig` (after `docstring_length_threshold`):

```python
# Decomposer settings (REQ-MP-908)
decomposition_enabled: bool = True
max_sub_elements: int = 5
max_helpers_per_function: int = 4
decomposition_confidence_threshold: float = 0.6
class_decompose_enabled: bool = True
function_chain_enabled: bool = True
```

**Verify:** `pytest tests/unit/micro_prime/test_models.py -x` — no regressions.

---

### Step 1.2 — Decomposer Module: Data Classes + Class Strategy

**File:** `micro_prime/decomposer.py` (new)

**Data classes** (REQ-MP-900):

```python
@dataclass
class SubElement:
    name: str
    kind: str                          # "class_shell", "init", "class_attr", "helper", "dispatch_body"
    prompt_context: str
    depends_on: list[str]
    assembly_order: int
    element_spec: Optional[ForwardElementSpec]   # Synthetic or existing (None for deterministic class_shell)
    deterministic: bool = False        # True = extract from skeleton, no LLM

@dataclass
class DecompositionPlan:
    original_element: ForwardElementSpec
    sub_elements: list[SubElement]
    strategy: str
    assembly_kind: str                 # "class_compose", "function_chain"
    confidence: float
```

**Strategy protocol** (REQ-MP-907):

```python
class DecompositionStrategy(Protocol):
    @property
    def name(self) -> str: ...
    def can_handle(self, element, file_spec, manifest, reason,
                   classification_signals: Optional[set["ClassificationSignal"]] = None) -> bool: ...
    def plan(self, element, file_spec, manifest, reason,
             classification_signals: Optional[set["ClassificationSignal"]] = None) -> Optional[DecompositionPlan]: ...
    def assemble(self, plan, sub_results, skeleton) -> Optional[str]: ...
```

**`ClassDecomposeStrategy`** (REQ-MP-901):

`can_handle()` checks:

0. `config.class_decompose_enabled` is True
1. `element.kind == ElementKind.CLASS`
2. Methods of this class already exist as separate elements in `file_spec.elements` (match by `parent_class == element.name`)
3. No metaclass decorators (`ABCMeta`, `__init_subclass__`, `dataclass` with complex factories)
4. At most 3 class-level attributes counted from `file_spec.elements` where `parent_class == element.name` and `kind in {ElementKind.CONSTANT, ElementKind.VARIABLE}`

`plan()` produces:

- 1 sub-element: `class_shell` with `deterministic=True`
  - `element_spec`: synthetic `ForwardElementSpec(kind=CLASS, name=element.name, bases=element.bases)`
  - `assembly_order: 0`
- If class-level attributes exist in `file_spec.elements` (constants/variables with `parent_class == element.name`), add a `class_attr` sub-element
  - Enforce the `<= 3` class-attribute constraint; otherwise reject decomposition
  - Do not generate class-level attributes that are not present in the manifest
  - `element_spec`: synthetic `ForwardElementSpec(kind=CONSTANT, name="_class_attributes", parent_class=element.name)`
- If `__init__` IS in `file_spec.elements` with `parent_class == element.name`, it is a separate manifest element — the engine's normal element loop handles it. Do NOT add it to the decomposition plan. [R3-S1: inverted logic fix]
- Only generate an `init` sub-element if the class genuinely needs one that is NOT in the manifest (e.g., inferred from class context). For Phase 1, this means: if `__init__` is absent from `file_spec.elements` AND the class has no class-level state, no `init` sub-element is needed (the shell with `pass` suffices). If the class needs an `__init__` that the manifest doesn't include, decomposition should be rejected (the manifest is the source of truth).

`assemble()` (REQ-MP-904, `class_compose`):

- The class shell is already in the skeleton (placed by `DeterministicFileAssembler`)
- For `class_shell` sub-element: no action needed — the skeleton already has `class Foo(Base):` + docstring + `raise NotImplementedError`
- For `class_attr` sub-element: splice or insert immediately after the docstring
- For `__init__` sub-element: splice via existing `splice_body_into_skeleton()`; if a stub `__init__` exists, replace its body (do not duplicate)
- Return the class declaration line through the end of the class body (AST `end_lineno`)
- Validate with `ast.parse()`
- Avoid duplicate definitions: always replace existing stubs instead of inserting additional class bodies or methods
- Remove the placeholder `pass` when inserting `class_attr` or `__init__` so non-empty class bodies do not retain a stub

**Key insight for `class_shell`:** The skeleton already contains the full class declaration. The `CustomJsonFormatter` class element's `raise NotImplementedError` stub in the skeleton just needs to be removed (or left — the methods, which are separate elements, will splice their bodies into the skeleton replacing their own stubs). So for a class where all methods are separate elements and there's no `__init__`, the "decomposition" is really just: **mark the class element as successfully handled** and let the normal method splicing do the rest.

**Implementation detail:** The class element's `raise NotImplementedError` in the skeleton sits where class-level code would go. If there's no class-level code (no `__init__`, no class attributes), replace the stub with `pass`. If class-level attributes or `__init__` exist, remove the stub and let `class_attr`/`__init__` insertion populate the class body.

**`ModerateDecomposer`** (REQ-MP-900):

```python
class ModerateDecomposer:
    def __init__(self, strategies=None, config=None):
        self._config = config or MicroPrimeConfig()
        self._strategies = strategies or [ClassDecomposeStrategy(config=self._config)]

    def can_decompose(
        self, element, file_spec, manifest, reason,
        classification_signals: Optional[set["ClassificationSignal"]] = None,
    ) -> bool:
        if not self._config.decomposition_enabled:
            return False
        return any(
            s.can_handle(element, file_spec, manifest, reason, classification_signals)
            for s in self._strategies
        )

    def decompose(
        self, element, file_spec, manifest, reason,
        classification_signals: Optional[set["ClassificationSignal"]] = None,
    ) -> Optional[DecompositionPlan]:
        for s in self._strategies:
            if s.can_handle(element, file_spec, manifest, reason, classification_signals):
                plan = s.plan(element, file_spec, manifest, reason, classification_signals)
                if plan and len(plan.sub_elements) <= self._config.max_sub_elements:
                    if plan.confidence >= self._config.decomposition_confidence_threshold:
                        return plan
        return None

    def assemble(self, plan, sub_results, skeleton) -> Optional[str]:
        for s in self._strategies:
            if s.name == plan.strategy:
                return s.assemble(plan, sub_results, skeleton)
        return None
```

Note: Strategies should short-circuit before heavy work if they can predict `max_sub_elements` would be exceeded.

**Verify:** Unit tests (step 1.4).

---

### Step 1.3 — Engine Integration: `_handle_moderate`

**File:** `micro_prime/engine.py`

**Import additions** (top of file):

```python
from startd8.micro_prime.decomposer import ModerateDecomposer
```

**Engine `__init__`** — add decomposer instance:

```python
self._decomposer = ModerateDecomposer(config=self._config)
```

**Routing change** (line 262-284 in `_process_element_with_tier`):

Replace:

```python
else:
    # MODERATE/COMPLEX — return as needs_cloud
    result = ElementResult(
        element_name=element.name, ...
        escalation=build_escalation_context(reason=EscalationReason.TIER_TOO_HIGH, ...),
    )
```

With:

```python
elif tier == TierClassification.MODERATE:
    result = self._handle_moderate(
        element, file_spec, manifest, skeleton, contracts,
        file_path, reasoning,
        design_doc_sections=design_doc_sections,
        classification_signals=classification_signals,  # optional; added in Phase 3
    )
else:
    # COMPLEX only — immediate escalation
    result = ElementResult(
        element_name=element.name, ...
        escalation=build_escalation_context(reason=EscalationReason.TIER_TOO_HIGH, ...),
    )
```

**New method `_handle_moderate`:**

```python
def _handle_moderate(
    self,
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    manifest: Optional[ForwardManifest],  # [R1-S4: direct parameter, not instance state]
    skeleton: str,
    contracts: list[InterfaceContract],
    file_path: str,
    reasoning: str = "",
    design_doc_sections: Optional[list[str]] = None,
    classification_signals: Optional[set["ClassificationSignal"]] = None,
) -> ElementResult:
    """Handle MODERATE tier: attempt decomposition, then escalate."""
    start_time = time.monotonic()

    # [R1-S7: circuit breaker gate — skip decomposition planning if breaker is open]
    if self._circuit_open:
        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.MODERATE,
            classification_reason=reasoning,
            success=False,
            escalation=build_escalation_context(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                reason=EscalationReason.CIRCUIT_BREAKER,
                detail="Circuit breaker open",
            ),
        )

    # [R1-S5: null-guard for standalone process_element() path]
    if manifest is None:
        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.MODERATE,
            classification_reason=reasoning,
            success=False,
            escalation=build_escalation_context(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                reason=EscalationReason.TIER_TOO_HIGH,
                detail="Manifest unavailable — cannot decompose",
            ),
        )

    if not self._config.decomposition_enabled:
        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.MODERATE,
            classification_reason=reasoning,
            success=False,
            escalation=build_escalation_context(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                reason=EscalationReason.TIER_TOO_HIGH,
                detail="Decomposition disabled",
            ),
        )

    # [R3-Q1: Single entry point — decompose() handles both strategy matching and
    # plan construction in one pass, eliminating the double can_handle() sweep.]
    plan = self._decomposer.decompose(
        element, file_spec, manifest, reasoning, classification_signals,
    )
    if plan is None:
        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.MODERATE,
            classification_reason=reasoning,
            success=False,
            escalation=build_escalation_context(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                reason=EscalationReason.NOT_DECOMPOSABLE,
                detail="Decomposition plan rejected",
            ),
        )

    logger.info(
        "Decomposing %s (MODERATE) via %s: %d sub-elements",
        element.name, plan.strategy, len(plan.sub_elements),
    )

    # Generate each sub-element
    sub_results: dict[str, str] = {}
    total_input = 0
    total_output = 0
    completed_len = len(self._completed)  # stage few-shot history

    for sub in sorted(plan.sub_elements, key=lambda s: s.assembly_order):
        if sub.deterministic:
            # Extract from skeleton — no LLM needed
            code = self._extract_class_shell(element, skeleton)
            if code is not None:
                sub_results[sub.name] = code
                logger.info("Sub-element %s: deterministic extraction (0ms)", sub.name)
                continue
            else:
                # Shell extraction failed — abandon
                logger.warning("Shell extraction failed for %s, abandoning decomposition", element.name)
                # Roll back staged few-shot history before escalating
                self._completed = self._completed[:completed_len]
                return ElementResult(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    classification_reason=reasoning,
                    success=False,
                    escalation=build_escalation_context(
                        element_name=element.name,
                        file_path=file_path,
                        tier=TierClassification.MODERATE,
                        reason=EscalationReason.DECOMPOSITION_FAILED,
                        detail="Shell extraction failed",
                    ),
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=total_input,
                    output_tokens=total_output,
                )

        # Generate via _handle_simple
        # NOTE [R3-S3]: `skeleton` is a Python str (immutable). `_handle_simple` and
        # `splice_body_into_skeleton` return new strings, never mutating the input.
        # No skeleton rollback is needed on failed decomposition — only `self._completed`
        # (few-shot history) requires rollback. The assembled output replaces the skeleton
        # content only after successful assembly + verification.
        if sub.element_spec is None:
            self._completed = self._completed[:completed_len]
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                classification_reason=reasoning,
                success=False,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    reason=EscalationReason.DECOMPOSITION_FAILED,
                    detail=f"Missing element_spec for sub-element {sub.name}",
                ),
                generation_time_ms=(time.monotonic() - start_time) * 1000,
                input_tokens=total_input,
                output_tokens=total_output,
            )
        sub_result = self._handle_simple(
            sub.element_spec, file_spec, skeleton, contracts,
            file_path, f"sub-element of {element.name}",
            design_doc_sections=design_doc_sections,
        )
        total_input += sub_result.input_tokens
        total_output += sub_result.output_tokens

        if not sub_result.success or not sub_result.code:
            logger.warning(
                "Sub-element %s failed — abandoning decomposition of %s",
                sub.name, element.name,
            )
            self._completed = self._completed[:completed_len]
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                classification_reason=reasoning,
                success=False,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    reason=EscalationReason.DECOMPOSITION_FAILED,
                    detail=f"Sub-element {sub.name} failed",
                    last_code=sub_result.code,
                    last_error=sub_result.escalation.detail if sub_result.escalation else None,
                ),
                generation_time_ms=(time.monotonic() - start_time) * 1000,
                input_tokens=total_input,
                output_tokens=total_output,
            )

        sub_results[sub.name] = sub_result.code

    # All sub-elements succeeded — assemble
    assemble_start = time.monotonic()  # [R3-S2: capture assembly timing]
    assembled = self._decomposer.assemble(plan, sub_results, skeleton)
    assembly_time_ms = (time.monotonic() - assemble_start) * 1000
    gen_time = (time.monotonic() - start_time) * 1000

    if assembled is None:
        self._completed = self._completed[:completed_len]
        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.MODERATE,
            classification_reason=reasoning,
            success=False,
            escalation=build_escalation_context(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                reason=EscalationReason.DECOMPOSITION_FAILED,
                detail="Assembly failed",
            ),
            generation_time_ms=gen_time,
            input_tokens=total_input,
            output_tokens=total_output,
        )

    logger.info(
        "Decomposition succeeded for %s: %d/%d sub-elements, %.0fms",
        element.name, len(sub_results), len(plan.sub_elements), gen_time,
    )

    # Record success for cache (skip re-decomposition for same element)
    moderate_fingerprint = f"{element.parent_class or ''}:{element.name}:{file_path}:{TierClassification.MODERATE.value}"
    self._success_cache.add(moderate_fingerprint)

    return ElementResult(
        element_name=element.name,
        file_path=file_path,
        tier=TierClassification.MODERATE,
        classification_reason=reasoning,
        success=True,
        code=assembled,
        decomposition_metadata={
            "strategy": plan.strategy,
            "sub_elements": len(plan.sub_elements),
            "sub_element_results": [
                {"name": s.name, "kind": s.kind, "success": s.name in sub_results}
                for s in plan.sub_elements
            ],
            "assembly_time_ms": assembly_time_ms,  # [R3-S2: populated from assemble_start]
            "total_time_ms": gen_time,
        },
        generation_time_ms=gen_time,
        input_tokens=total_input,
        output_tokens=total_output,
    )
```

**Manifest threading:** `process_file()` already has the manifest. Pass it directly to `_handle_moderate(element, file_spec, manifest, skeleton, ...)` at the call site. For `process_element()` (the standalone entry point), pass `manifest=None` — the null-guard returns immediate escalation (graceful fallback). [R1-S4: no instance variable, thread-safe]

**`_extract_class_shell` helper:**

```python
def _extract_class_shell(
    self,
    element: ForwardElementSpec,
    skeleton: str,
) -> Optional[str]:
    """Extract the class declaration + docstring from the skeleton.

    Returns 'pass' as the body — the real bodies come from
    method elements spliced by the normal engine loop.
    """
    try:
        tree = ast.parse(skeleton)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == element.name:
            # The class exists in the skeleton — the shell is already there.
            # Always return "pass" — attrs/__init__ sub-elements handle their
            # own content; the shell stub just needs a valid placeholder.
            # [R1-S3: returning "" was falsy and broke the caller's `if code is not None` check]
            return "pass"

    return None
```

**Key realization:** For the `CustomJsonFormatter` case, the class shell is already in the skeleton. The methods (`add_fields`, `format`) are separate elements that will be processed by the engine's normal loop and spliced into the skeleton. The class element's `raise NotImplementedError` stub just needs to be replaced with `pass` so the skeleton is valid Python while method bodies are being spliced in.

So `_handle_moderate` for a class with only `class_shell` deterministic sub-element returns `code="pass"` — the splicer (`splice_body_into_skeleton`) will replace the `raise NotImplementedError` with `pass`. If class attributes or `__init__` are present, the stub is removed during assembly and replaced by generated content; then method elements fill in their own stubs normally.

Note: `_extract_class_shell` verifies the class exists in the skeleton via AST parsing. Since `can_decompose()` already checks the class is in `file_spec`, a simpler fast-path that returns `"pass"` without re-parsing is acceptable — but AST verification provides defense-in-depth at negligible cost for typical skeleton sizes. [R1-Q1]

**Verify:**

- `pytest tests/unit/micro_prime/test_engine.py -x` — existing tests pass (MODERATE escalation test needs config tweak, see step 1.5)
- New `test_handle_moderate_class_decomposition` passes

---

### Step 1.4 — Tests

**File:** `tests/unit/micro_prime/conftest.py` — add fixtures:

```python
@pytest.fixture
def class_element_with_methods() -> ForwardElementSpec:
    """A class element whose methods are separate elements."""
    return ForwardElementSpec(
        kind=ElementKind.CLASS,
        name="CustomJsonFormatter",
        bases=["logging.Formatter"],
        docstring_hint="Formats log records as single-line JSON objects with timestamp, severity, name, and message fields.",
    )


@pytest.fixture
def class_file_spec(class_element_with_methods) -> ForwardFileSpec:
    """File spec with a class + its methods as separate elements."""
    return ForwardFileSpec(
        file="src/emailservice/logger.py",
        imports=[
            ForwardImportSpec(kind="import", module="logging"),
            ForwardImportSpec(kind="import", module="json"),
            ForwardImportSpec(kind="from", module="datetime", names=["datetime"]),
        ],
        elements=[
            class_element_with_methods,
            ForwardElementSpec(
                kind=ElementKind.METHOD,
                name="add_fields",
                signature=Signature(
                    params=[
                        Param(name="self"),
                        Param(name="log_record"),
                        Param(name="record"),
                        Param(name="message_dict"),
                    ],
                    return_annotation="None",
                ),
                parent_class="CustomJsonFormatter",
            ),
            ForwardElementSpec(
                kind=ElementKind.METHOD,
                name="format",
                signature=Signature(
                    params=[
                        Param(name="self"),
                        Param(name="record", annotation="logging.LogRecord"),
                    ],
                    return_annotation="str",
                ),
                parent_class="CustomJsonFormatter",
            ),
        ],
    )


@pytest.fixture
def class_skeleton() -> str:
    """Skeleton for the logger file with class + methods.

    NOTE [R1-Q2]: Verify this matches DeterministicFileAssembler output.
    The stub pattern (raise NotImplementedError at class scope + per-method)
    must mirror what the assembler actually produces. If the assembler uses
    a different pattern, update this fixture accordingly.
    """
    return '''# [STARTD8-SKELETON]
import logging
import json
from datetime import datetime

class CustomJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""
    raise NotImplementedError

    def add_fields(self, log_record, record, message_dict) -> None:
        """Add custom fields."""
        raise NotImplementedError

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record."""
        raise NotImplementedError
'''
```

**File:** `tests/unit/micro_prime/test_decomposer.py` (new):

| Test | What it validates |
|------|-------------------|
| `test_can_decompose_class_with_methods` | `can_decompose()` returns True for class whose methods are separate elements |
| `test_cannot_decompose_class_without_separate_methods` | Returns False when methods aren't in file_spec |
| `test_cannot_decompose_function` | Phase 1 has no function strategy — returns False. NOTE [R3-Q2]: In Phase 3, update this test to use `config.function_chain_enabled=False` to remain valid. |
| `test_cannot_decompose_when_disabled` | `decomposition_enabled=False` returns False |
| `test_decompose_class_produces_plan` | Plan has 1 sub-element (class_shell, deterministic) |
| `test_decompose_class_with_init_produces_two_subs` | Plan has 2 sub-elements (shell + **init**) when **init** not in file_spec |
| `test_decompose_class_with_attrs_produces_attr_sub` | Class-level attributes become a `class_attr` sub-element |
| `test_class_attr_detection_from_manifest` | Class-level attributes are detected only from manifest elements |
| `test_class_shell_assembly_returns_pass` | Assemble returns "pass" only for empty class shells (no attrs/init) |
| `test_assembly_validates_ast` | Bad assembly returns None |
| `test_confidence_threshold_rejects_low_confidence` | Plan below threshold returns None |
| `test_failed_decomposition_does_not_pollute_few_shot` | Sub-element successes are rolled back on failure |

**Existing test update** (`test_engine.py:80-96`):

`test_process_moderate_element_escalates` uses `run_server` (an orchestrator function). This will still classify as MODERATE and `can_decompose()` will return False (it's a function, not a class; and function strategy isn't in Phase 1). If the test asserts the escalation reason, update it to expect `NOT_DECOMPOSABLE` when decomposition is enabled, or explicitly set `decomposition_enabled=False` in the test to preserve `TIER_TOO_HIGH`.

The class element `CustomJsonFormatter` also classifies as MODERATE. When processed through the engine with decomposition enabled, it should succeed. Add a new test:

```python
def test_process_moderate_class_decomposes(
    self, class_element_with_methods, class_file_spec, class_skeleton,
):
    """MODERATE class with separate methods should decompose successfully."""
    manifest = ForwardManifest(
        schema_version="1.0.0",
        file_specs={"src/emailservice/logger.py": class_file_spec},
        contracts=[],
    )
    engine = MicroPrimeEngine()
    result = engine.process_file(class_file_spec, manifest, class_skeleton)
    # Find the class element result
    class_result = next(
        r for r in result.element_results if r.element_name == "CustomJsonFormatter"
    )
    assert class_result.tier == TierClassification.MODERATE
    assert class_result.success is True
    # [R3-S6: assemble_class() returns "pass" as the body token for the splicer.
    # For a shell-only class (no __init__, no attrs), the class declaration and
    # docstring are already in the skeleton. The splicer replaces the class-scope
    # `raise NotImplementedError` with this body token. The full class text lives
    # in the skeleton, not in ElementResult.code.]
    assert class_result.code == "pass"
    assert class_result.escalation is None
    assert class_result.decomposition_metadata is not None
    assert class_result.decomposition_metadata["strategy"] == "class_decompose"
```

**Verify:** `pytest tests/unit/micro_prime/ -x -v`

---

### Step 1.5 — Prime Adapter Metadata

**File:** `micro_prime/prime_adapter.py`

In the metadata dict returned by `generate()` (line 384-397), add:

```python
"micro_prime_decomposed_count": decomposed_count,
"micro_prime_decomposition_failures": decomposition_failure_count,
```

Track these in the element loop (line 264-274):

```python
decomposed_count = 0
decomposition_failure_count = 0
for er in file_result.element_results:
    ...
    if er.decomposition_metadata is not None:  # [R1-S2: unambiguous signal]
        decomposed_count += 1
    if er.escalation and er.escalation.reason == EscalationReason.DECOMPOSITION_FAILED:
        decomposition_failure_count += 1
```

**Verify:** `pytest tests/unit/micro_prime/test_adapters.py -x`

---

### Step 1.6 — Integration Validation

Run PI-001 against online-boutique-demo:

```bash
cd /Users/neilyashinsky/Documents/dev/online-boutique-demo
source .cap-dev-pipe/pipeline.env
.cap-dev-pipe/run-prime-contractor.sh --provenance ... --filter PI-001
```

**Expected outcome:**

- `CustomJsonFormatter`: MODERATE, decomposed via `class_decompose`, success=True, code="pass"
- `add_fields`, `format`, `getJSONLogger`, `get_logger`: SIMPLE, success=True (unchanged)
- `micro_prime_only: true`, `micro_prime_elements: 5`, `micro_prime_decomposed_count: 1`
- Total cost: $0.00

---

## Phase 2: Registry, Config, Observability, Adapter

**Goal:** Production-ready with full observability and configuration surface.

### Step 2.1 — Dry-Run Report Annotation

**File:** `micro_prime/prime_adapter.py`

In `_dry_run_classify` (line 446-477), after classifying each element:

```python
if tier == TierClassification.MODERATE:
    # [R1-S6: Use inspect() instead of decompose() to avoid full planning
    # and leaky _decomposer access. inspect() returns strategy name + sub-count
    # without building a full plan or applying confidence threshold.]
    info = engine.inspect_decomposition(
        element, file_spec, manifest, reason,
        classification_signals=classification_signals,  # optional; added in Phase 3
    )
    elements_info[-1]["decomposable"] = info.get("viable", False)
    elements_info[-1]["decomposition_strategy"] = info.get("strategy")
    elements_info[-1]["decomposition_sub_count"] = info.get("sub_count", 0)
```

Add to `MicroPrimeEngine` [R1-S6, R3-S4]:

```python
def inspect_decomposition(
    self,
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    manifest: Optional[ForwardManifest],
    reason: str,
    classification_signals: Optional[set["ClassificationSignal"]] = None,
) -> dict[str, Any]:
    """Lightweight decomposition viability check for dry-run reports.

    Returns:
        {"viable": bool, "strategy": Optional[str], "sub_count": int}
        - viable: True if can_decompose() returns True
        - strategy: name of the matching strategy, or None
        - sub_count: estimated number of sub-elements (0 if not viable)
    All three keys are always present (no KeyError risk for callers).
    """
```

Constraint: `inspect_decomposition()` must rely only on data available in dry-run mode (no LLM calls, no I/O), otherwise the report can diverge from runtime behavior.

In `_format_dry_run_report` (line 551-555), after the element line:

```python
if el.get("decomposable"):
    strategy = el.get("decomposition_strategy", "?")
    sub_count = el.get("decomposition_sub_count", 0)
    lines.append(f"               -> DECOMPOSABLE ({strategy}): {sub_count} sub-elements")
```

Update summary line to include decomposable count:

```python
decomposable = sum(1 for el in pf.get("elements", []) if el.get("decomposable"))
lines.append(
    f"    -> {pf['local']} local, "
    f"{pf['escalated']} escalated"
    + (f", {decomposable} decomposable" if decomposable else "")
)
```

**Verify:** Dry-run with `--dry-run` flag shows `DECOMPOSABLE (class_decompose): 1 sub-elements` for `CustomJsonFormatter`.

---

### Step 2.2 — OTel Metrics

**File:** `micro_prime/prime_adapter.py` (or `micro_prime/metrics.py`)

Add counters (REQ-MP-906) alongside existing OTel setup (line 29-47):

```python
_decomp_attempted = _meter.create_counter("micro_prime.decomposition_attempted", ...)
_decomp_succeeded = _meter.create_counter("micro_prime.decomposition_succeeded", ...)
_decomp_failed = _meter.create_counter("micro_prime.decomposition_failed", ...)
_decomp_rejected = _meter.create_counter("micro_prime.decomposition_rejected", ...)
_sub_elements_counter = _meter.create_counter("micro_prime.sub_elements_generated", ...)
_decomp_time = _meter.create_histogram("micro_prime.decomposition_time_ms", ...)
```

Emit from `prime_adapter.py` after inspecting `ElementResult.decomposition_metadata` — NOT from `engine.py` directly. The engine is currently metrics-agnostic (uses `MetricsCollector` abstraction). Adding direct OTel calls to `engine.py` would break this pattern. If engine-level emission is needed, extend `MetricsCollector` with decomposition record types. [R1-Q4]

Note: If REQ-MP-600 discourages high-cardinality labels, reduce `file_path` to basename or a stable file id.
Note: Deterministic sub-elements (e.g., `class_shell`) should not increment `micro_prime.sub_elements_generated`; if counted, include a `deterministic=true` label to avoid inflating LLM usage metrics.

**Verify:** `pytest tests/unit/micro_prime/test_metrics.py -x`

---

### Step 2.3 — Postmortem Report Enrichment

**File:** `micro_prime/prime_adapter.py` — `_serialize_file_result`

Add `decomposition` field to element result serialization when the element was decomposed:

```python
# [R3-S5: Use decomposition_metadata as the signal, not tier+success]
# [R3-Q3: Access as dataclass attribute, not dict .get()]
if er.decomposition_metadata is not None:
    serialized["decomposition"] = {
        "strategy": er.decomposition_metadata["strategy"],
        "sub_elements": er.decomposition_metadata["sub_elements"],
        "sub_element_results": er.decomposition_metadata["sub_element_results"],
        "assembly_time_ms": er.decomposition_metadata["assembly_time_ms"],
        "total_time_ms": er.decomposition_metadata["total_time_ms"],
    }
```

This requires `ElementResult.decomposition_metadata` which was already added in Step 1.1 [R1-S1].

**Verify:** `pytest tests/unit/contractors/test_prime_postmortem.py -x`

---

## Phase 3: Function Decomposition

**Goal:** MODERATE functions with 2+ distinct responsibilities decompose into helpers + dispatch.

### Step 3.0 — ClassificationSignal Plumbing

**File:** `micro_prime/classifier.py`, `micro_prime/engine.py`

Add a `ClassificationSignal` enum and update `classify_element` to return `(tier, reasoning, signals)`:

```python
class ClassificationSignal(str, Enum):
    EXTERNAL_IMPORTS = "external_imports"
    EXTERNAL_API = "external_api"
    ORCHESTRATOR = "orchestrator"
    APP_SERVER_INSTANCE = "app_server_instance"
```

- Update `classify_element(...)` to populate `signals` alongside the reason string.
- Update `process_file()` classification loop to capture `signals` and pass them through `classified` tuples.
- Update `_process_element_with_tier(...)` and `_handle_moderate(...)` to accept `classification_signals` (default to empty set when unavailable).
- Update `ModerateDecomposer`/`DecompositionStrategy` signatures to accept `classification_signals` (already reflected in Step 1.2).

**Verify:** `pytest tests/unit/micro_prime/test_classifier.py -x` with new `test_classification_signals`.

### Step 3.1 — Synthetic Element Spec Construction

**File:** `micro_prime/decomposer.py`

Add `_build_synthetic_spec()` as a **module-level utility function** in `decomposer.py` (not a method on any class). Both `ClassDecomposeStrategy` and `FunctionChainStrategy` call it directly since they share the same module. The leading underscore marks it as internal to the module. [R3-S7]

```python
def _build_synthetic_spec(
    name: str,
    kind: ElementKind,
    params: list[Param],
    return_annotation: str,
    parent_class: Optional[str] = None,
    docstring_hint: Optional[str] = None,
) -> ForwardElementSpec:
    """Build a synthetic ForwardElementSpec for a decomposed sub-element."""
    return ForwardElementSpec(
        kind=kind,
        name=name,
        signature=Signature(params=params, return_annotation=return_annotation),
        parent_class=parent_class,
        docstring_hint=docstring_hint,
    )
```

**Rules:**

- For methods, always include `self`/`cls` as the first parameter.
- For async parents, preserve `async` on helpers when they are awaited.

**Verify:** `test_synthetic_element_spec` — spec passes validation, produces valid prompt.

---

### Step 3.2 — Function Chain Strategy

**File:** `micro_prime/decomposer.py`

Add `FunctionChainStrategy`:

`can_handle()` checks:

0. `config.function_chain_enabled` is True
1. `element.kind in (FUNCTION, METHOD, ASYNC_FUNCTION, ASYNC_METHOD)`
2. If `classification_signals` is provided, ensure `signals` has no intersection with `{EXTERNAL_IMPORTS, EXTERNAL_API, ORCHESTRATOR, APP_SERVER_INSTANCE}`. If signals are unavailable, fall back to reason-string matching of `"external API"`, `"external imports"`, `"complex API:"`, `"orchestrator"`, `"app/server instance"` and emit a debug log indicating fallback was used. [R1-S8]
3. Docstring contains 2+ distinct clauses (deterministic split on `;`, bullet markers `-`, `*`, `•`, or enumerated prefixes `1.`, `2.`; ignore clauses shorter than 4 words)
4. Resulting helper count <= `config.max_helpers_per_function`

`plan()` produces:

1. Parse docstring into responsibility clauses
2. For each clause: create a synthetic `ForwardElementSpec` with inferred params/return
3. Create dispatch body sub-element that calls all helpers
4. Helpers have `assembly_order` 0..N-1, dispatch has `assembly_order` N
5. Helper names are derived by slugifying responsibility text; if the slug is empty, a Python keyword/builtin, or longer than 48 chars, fall back to `_helper_{n}`
6. Helper names are uniquified if they collide with existing symbols (suffix `_2`, `_3`, etc.)
7. For METHOD/ASYNC_METHOD, helpers are generated as private methods on the same class (same `parent_class`) and include `self`/`cls` as the first parameter

`assemble()` (`function_chain`):

1. Concatenate helper definitions
2. Append dispatch body
3. Validate with `ast.parse()`

**This is the most LLM-dependent step** — each helper needs Ollama generation, and the dispatch body prompt must reference helper signatures. The prompt for the dispatch body includes:

```
# Available helpers (already implemented):
def _validate_order_fields(order) -> None: ...
def _compute_totals(order, config) -> dict: ...
def _format_confirmation(order, totals) -> str: ...

# Now implement the dispatch body that calls these helpers:
def process_order(order, config) -> str:
    raise NotImplementedError
```

**Verify:** Unit tests with mock Ollama.
Suggested tests:

- `test_function_chain_clause_parsing` — deterministic clause splitting ignores short fragments
- `test_method_helpers_in_class_scope` — helpers become private class methods with `self`/`cls`
- `test_helper_name_collision_uniquified` — collisions are suffixed (`_2`, `_3`, etc.)
- `test_helper_name_fallback` — invalid/too-long slugs fall back to `_helper_n`
- `test_async_helper_preserves_async` — async helpers remain async when awaited

---

### Step 3.3 — Register Function Strategy

**File:** `micro_prime/decomposer.py`

Update `ModerateDecomposer.__init__` default strategies:

```python
self._strategies = strategies or [
    ClassDecomposeStrategy(),
    FunctionChainStrategy(config=self._config),
]
```

**Verify:** Full test suite, then integration test with a function-heavy feature.

---

## Commit Plan

| Commit | Contents | Tests |
|--------|----------|-------|
| 1 | `models.py`: new EscalationReasons + config fields + `decomposition_metadata` on ElementResult + `MicroPrimeCostReport` fields [R1-S1] | `test_models.py` |
| 2 | `conftest.py`: class element fixtures [R1-Q3: moved before tests that need them] | — |
| 3 | `decomposer.py`: data classes, ClassDecomposeStrategy, ModerateDecomposer | `test_decomposer.py` |
| 4 | `engine.py`: `_handle_moderate`, manifest param threading, `_extract_class_shell`, `inspect_decomposition` | `test_engine.py` (new + existing) |
| 5 | `prime_adapter.py`: metadata enrichment, dry-run annotation | `test_adapters.py` |
| 6 | Integration validation: PI-001 re-run | Manual |

Phase 2 and Phase 3 follow as separate commit batches.

Phase 3 should start with `ClassificationSignal` plumbing (classifier + engine + decomposer interfaces) before adding `FunctionChainStrategy`.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `_handle_moderate` introduces regression for COMPLEX elements | Low | High | COMPLEX is in `else` branch, not `elif MODERATE` — unreachable by `_handle_moderate` |
| Class shell `pass` replacement leaves skeleton with empty class | Low | Medium | Method elements splice their bodies afterward; if no methods succeed, the skeleton has `class Foo: pass` which is valid Python |
| `ForwardElementSpec(frozen=True)` prevents synthetic spec creation | None | — | Synthetic specs are new instances, not mutations |
| Manifest not available in `process_element()` standalone path | Medium | Low | `manifest=None` parameter → null-guard returns immediate TIER_TOO_HIGH escalation [R1-S4/S5] |
| Function chain strategy generates bad helper signatures | Medium | Medium | Phase 3 concern; bounded by `max_helpers=4` and circuit breaker |
| Existing `test_process_moderate_element_escalates` fails | None | — | Uses `run_server` (orchestrator) which has no decomposition strategy → still escalates |
| Few-shot history polluted by failed decomposition | Medium | Medium | Stage `self._completed` length; rollback on any sub-element or assembly failure |
| ClassificationSignal plumbing breaks call sites | Medium | Medium | Add optional `classification_signals` params with defaults; update all classify_element callers in a single commit |

---

## Definition of Done

### Phase 1

- [ ] `CustomJsonFormatter` in PI-001 generates locally as MODERATE/decomposed with code="pass"
- [ ] 5/5 elements succeed, `micro_prime_only: true`, total cost $0.00
- [ ] All existing tests pass unchanged
- [ ] New tests: `test_decomposer.py` (9 tests), `test_engine.py` additions (2 tests)
- [ ] `decomposition_enabled=False` produces identical behavior to pre-change

### Phase 2

- [ ] Dry-run report shows DECOMPOSABLE annotation for viable MODERATE elements
- [ ] OTel metrics emitted for decomposition attempts/successes/failures
- [ ] Postmortem report includes decomposition metadata

### Phase 3

- [ ] Function with 2-3 responsibilities decomposes into helpers + dispatch via Ollama
- [ ] 5+ responsibilities rejected (not decomposable)
- [ ] Orchestrator/API-dependent functions never decomposed

---

## Convergent Review — Round R1 (Triaged)

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 16:08 UTC
- **Scope**: Full source-code cross-reference — validated plan against `engine.py` (678L), `models.py` (169L), `classifier.py` (312L)

### Findings

| ID | Step | Severity | Finding | Fix |
|----|------|----------|---------|-----|
| R1-S1 | Step 1.3 + 2.3 | 🔴 high | **`decomposition_metadata` used before defined.** Step 1.3 (`_handle_moderate` at line 385) assigns `decomposition_metadata={...}` to `ElementResult(...)` — but `ElementResult` in `models.py:52-67` has no such field. The plan adds it only in Step 2.3. Any code written for Step 1.3 will raise `TypeError` on construction until Step 2.3 is applied. **Fix:** Move the `decomposition_metadata: Optional[dict] = None` addition from Step 2.3 into **Step 1.1** (alongside the EscalationReason and config changes). Or, include it as part of the Step 1.3 diff. Either way, the field must exist before Step 1.3 code is executed. | Move `decomposition_metadata` field definition to Step 1.1. |
| R1-S2 | Step 1.5 | 🔴 high | **`decomposed_count` uses wrong signal.** Lines 588-589 track `er.tier == MODERATE and er.success` — but this would also count any future case where a MODERATE element succeeds without decomposition (e.g., a hypothetical strategy that directly generates). The correct, unambiguous signal is `er.decomposition_metadata is not None` (once the field exists). Additionally, the count is computed from `file_result.element_results` but the adapter currently iterates at the feature level across files — verify that the loop counts correctly across multi-file features. | Change the condition to `er.decomposition_metadata is not None`. |
| R1-S3 | Step 1.3 | 🟡 medium | **`_extract_class_shell` returns `""` as a success sentinel.** At line 426, `return "pass" if empty_body else ""`. The caller at line 305 checks `if code is not None` — truthy for `"pass"`, **falsy for `""`**. So when `empty_body=False`, `code=""`, the `if code is not None: sub_results[sub.name] = code` branch executes and stores an empty string. The `assembled` result then contains an empty string for the `class_shell` key, producing invalid assembly. Either return `"pass"` in both cases (the class shell is always a stub) or return a sentinel like `_SHELL_SENTINEL = object()`. Per the "simpler realization" note (line 431-435), the correct return for a non-empty-body class shell is still `"pass"` — the attributes/`__init__` sub-elements handle their own content; the shell just needs `pass` removed as a placeholder. | Return `"pass"` for all valid class shells regardless of `empty_body`. |
| R1-S4 | Step 1.3 | 🟡 medium | **`_current_manifest` is a thread-unsafe instance variable.** Line 253 reads `self._current_manifest` which is set in `process_file()` at entry and cleared at exit. If `MicroPrimeEngine` is shared across threads (e.g., in concurrent feature batches from the prime adapter), two simultaneous `process_file()` calls will overwrite each other's `_current_manifest`. The risk register documents the `process_element()` standalone fallback (line 837) but not the concurrency hazard. **Fix:** Prefer passing `manifest` as a direct parameter to `_handle_moderate` rather than storing it as instance state. Since `process_file()` already passes `manifest` explicitly (line 305-380), add `manifest: Optional[ForwardManifest] = None` to `_handle_moderate`'s signature and pass it at the call site. | Eliminate `_current_manifest` instance variable; pass `manifest` as a parameter. |
| R1-S5 | Step 1.3 | 🟡 medium | **No null-guard for `_current_manifest` in standalone `process_element()` path.** The plan says (line 401) "for `process_element()`, set `_current_manifest = None` and `_handle_moderate` will treat it as non-decomposable (graceful fallback)." However, `_handle_moderate` calls `self._decomposer.can_decompose(element, file_spec, manifest, reasoning)` at line 255 where `manifest` could be `None`. `ClassDecomposeStrategy.can_handle()` iterates `file_spec.elements` to check for siblings (not `manifest` directly), so it likely works. But passing `None` as `manifest` could crash strategies that dereference it without guarding. Add: explicit `if manifest is None: return escalate(TIER_TOO_HIGH, "manifest unavailable")` guard at the top of `_handle_moderate`. | Add null-guard: `if manifest is None: return immediately with TIER_TOO_HIGH escalation`. |
| R1-S6 | Step 2.1 | 🟡 medium | **Dry-run path calls full `decompose()` — violates dry-run contract.** Lines 632-634 call `engine._decomposer.decompose(element, ...)` during dry-run reporting. Per REQ-MP-906 AC: "`can_decompose()` MUST rely only on data available in dry-run mode (no LLM calls, no I/O)." `decompose()` builds a full plan which is safe IF strategies are pure, but it also applies the confidence threshold filter — meaning a plan could show `decomposable=True` from `can_decompose()` but then show `strategy=None` from `decompose()` if confidence is below threshold. This would produce a misleading report ("DECOMPOSABLE" with no strategy). Also, calling the private `engine._decomposer` directly from `prime_adapter.py` is a leaky abstraction. **Fix:** Add a `DecompositionStrategy.inspect(element, file_spec, manifest, reason) -> dict` lightweight method (or have `decompose()` return a `DecompositionPlan` that includes a `viable()` flag), and call that instead. | Add a `inspect()` method or expose strategy name/sub-count without full planning. |
| R1-S7 | Step 1.3 | 🟢 low | **Missing explicit circuit breaker gate in `_handle_moderate`.** The invariants (line 33) say "circuit breaker applies to sub-element failures — sub-elements go through `_handle_simple` which already updates the breaker." This is true, but if `self._circuit_open` is already true when `_handle_moderate` is entered, the method runs full decomposition planning (`can_decompose()`, `decompose()`) before hitting `_handle_simple` which then immediately escalates each sub-element. This wastes planning CPU. For consistency with REQ-MP-903 AC (from the requirements review) add a guard at the top of `_handle_moderate`: `if self._circuit_open: return escalate(CIRCUIT_BREAKER, "circuit open")`. | Add `if self._circuit_open` early-exit to `_handle_moderate`. |
| R1-S8 | Step 3.2 | 🟢 low | **`FunctionChainStrategy.can_handle()` inherits the classification reason string fragility.** Step 3.2 (line 759) checks the reason does NOT contain `"external API"` or `"orchestrator"`. But `classifier.py` emits `"file has 9 external imports (>8)"` for the file-level import gate (classifier.py:251) — this string does not contain `"external API"` and would incorrectly mark import-heavy functions as decomposable. This is the same issue identified as R1-S2 in the requirements review. The implementation plan should note this explicitly and require the reason-string check to also match `"external imports"` (and/or `"complex API:"`) from the actual classifier output. | Update the exclusion check in `can_handle()` to match all actual classifier reason strings. |

### Quick Wins

| ID | Step | Severity | Suggestion |
|----|------|----------|-----------|
| R1-Q1 | Step 1.3 | low | The `_extract_class_shell` function at lines 406-428 parses the full skeleton AST even though its only output is `"pass"` (or `""`). For a 45-line file this is negligible, but for large skeletons it adds unnecessary parse time on every MODERATE class element. Since the plan notes (line 431) "the shell is already in the skeleton — just return `pass`," consider simplifying to: check `element.name in skeleton` as a fast pre-filter before AST parsing, or just return `"pass"` directly without parsing (verification that the class exists is already handled by `can_decompose()`). |
| R1-Q2 | Step 1.4 | low | The fixture `class_skeleton` (line 503-520) has a syntactically invalid class body — `raise NotImplementedError` at class scope (line 511) is valid Python, but methods appearing after a class-scope `raise` may confuse the real-world skeleton format. Verify this matches what `DeterministicFileAssembler` actually produces. If the assembler puts `raise NotImplementedError` inside an auto-generated `__init__` or uses a different stub pattern, the fixture is non-representative and tests could pass while the real integration fails. |
| R1-Q3 | Commit Plan | low | Commit 5 (`conftest.py: class element fixtures`) is listed after Commit 4 (`prime_adapter.py`) but the fixtures are needed by the engine tests in Commit 3. Reorder: move `conftest.py` additions to Commit 2 or 3 so that tests can pass at each commit boundary. The current ordering means tests added in Commit 3 (`test_engine.py` additions) would fail until Commit 5 is applied. |
| R1-Q4 | Step 2.2 | low | Step 2.2 places OTel metric emission in `prime_adapter.py` or `metrics.py` with a reference to "engine.py at the appropriate points" (line 678). But `_handle_moderate` lives in `engine.py`, which is currently metrics-agnostic (it uses `MetricsCollector`, not direct OTel calls). Clarify: either emit decomposition metrics via `MetricsCollector` (add new record types) to keep engine.py clean, or emit directly from `prime_adapter.py` after inspecting `ElementResult.decomposition_metadata`. Direct OTel calls in `engine.py` would break the existing abstraction pattern. |

### Triage Disposition

| ID | Disposition | Applied To | Notes |
|----|------------|------------|-------|
| R1-S1 | **ACCEPTED** | Step 1.1 | `decomposition_metadata` + `MicroPrimeCostReport` fields moved to Step 1.1; Step 2.3 reference updated |
| R1-S2 | **ACCEPTED** | Step 1.5 | Count condition changed to `decomposition_metadata is not None` |
| R1-S3 | **ACCEPTED** | Step 1.3 | `_extract_class_shell` always returns `"pass"` for valid shells |
| R1-S4 | **ACCEPTED** | Step 1.3 | `_current_manifest` eliminated; `manifest` passed as direct parameter |
| R1-S5 | **ACCEPTED** | Step 1.3 | Null-guard added: `if manifest is None → TIER_TOO_HIGH` |
| R1-S6 | **ACCEPTED** | Step 2.1 | `inspect_decomposition()` public method on engine; dry-run no longer calls `decompose()` |
| R1-S7 | **ACCEPTED** | Step 1.3 | `if self._circuit_open` early-exit added at top of `_handle_moderate` |
| R1-S8 | **ACCEPTED** | Step 3.2 | Reason-string exclusion list expanded to match actual classifier output |
| R1-Q1 | **ACCEPTED** | Step 1.3 | Note added about fast-path vs AST verification tradeoff |
| R1-Q2 | **ACCEPTED** | Step 1.4 | Fixture docstring notes DeterministicFileAssembler verification requirement |
| R1-Q3 | **ACCEPTED** | Commit Plan | Fixtures moved to Commit 2 (before Commit 3/4 tests that use them) |
| R1-Q4 | **ACCEPTED** | Step 2.2 | Metrics emit from `prime_adapter.py`, not `engine.py`; MetricsCollector abstraction preserved |

---

## Convergent Review — Round R2 (Triaged)

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 19:10 UTC
- **Scope**: Robustness + plan/requirements alignment after R1 updates

### Findings

| ID | Step | Severity | Finding | Fix |
|----|------|----------|---------|-----|
| R2-S1 | Step 1.3 | 🔴 high | **Few-shot pollution on failed decomposition.** `_handle_simple` appends to `self._completed` for each sub-element. If a later sub-element fails, these few-shot examples remain, contaminating subsequent prompts. | Stage `self._completed` length and roll back on any sub-element or assembly failure. |
| R2-S2 | Step 1.2 | 🟡 medium | **Class attribute detection is underspecified.** The plan allows class attributes but doesn't define how to detect them, risking hallucinated attrs. | Count class attrs only from `file_spec.elements` with `parent_class == element.name` and `kind in {CONSTANT, VARIABLE}`; generate `class_attr` only when present. |
| R2-S3 | Step 3.2 | 🟡 medium | **Helper naming can be invalid/unstable.** Docstring-derived slugs can be empty, overly long, or keywords/builtins, producing invalid code or noisy diffs. | Add deterministic slug rules with length cap and fallback `_helper_{n}`, then apply collision suffixing. |
| R2-S4 | Step 3.0/3.2 | 🟡 medium | **ClassificationSignal plumbing missing.** Requirements now specify `ClassificationSignal`, but the plan only mentions reason-string filtering. | Add a dedicated step to update `classifier.py` + callers to return and pass signals; use signals preferentially with reason-string fallback. |
| R2-S5 | Step 2.2 | 🟢 low | **Deterministic sub-elements skew metrics.** If counted as generated, they inflate LLM usage metrics. | Exclude deterministic sub-elements from `sub_elements_generated` or tag with `deterministic=true`. |

### Quick Wins

| ID | Step | Severity | Suggestion |
|----|------|----------|-----------|
| R2-Q1 | Step 1.3 | low | Remove unused `empty_body` param in `_extract_class_shell` once it always returns `"pass"`. |
| R2-Q2 | Step 1.2/3.2 | low | Add explicit `class_decompose_enabled` / `function_chain_enabled` gate in strategy `can_handle()` checks. |

### Triage Disposition

| ID | Disposition | Applied To | Notes |
|----|------------|------------|-------|
| R2-S1 | **ACCEPTED** | Step 1.3 | Rollback `self._completed` on any sub-element or assembly failure |
| R2-S2 | **ACCEPTED** | Step 1.2 | Class attrs only from manifest elements |
| R2-S3 | **ACCEPTED** | Step 3.2 | Slug + fallback `_helper_n` rules added |
| R2-S4 | **ACCEPTED** | Step 3.0/3.2 | ClassificationSignal plumbing added |
| R2-S5 | **ACCEPTED** | Step 2.2 | Deterministic metric labeling/exclusion added |
| R2-Q1 | **ACCEPTED** | Step 1.3 | `empty_body` removed from `_extract_class_shell` |
| R2-Q2 | **ACCEPTED** | Step 1.2/3.2 | Strategy-level config gates added |

---

## Convergent Review — Round R3 (Triaged)

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 16:26 UTC
- **Scope**: Code-level correctness sweep after R1+R2 integration — validated method bodies, test assertions, and interface contracts

### Findings

| ID | Step | Severity | Finding | Fix |
|----|------|----------|---------|-----|
| R3-S1 | Step 1.2 | 🔴 high | **`__init__` detection logic is inverted.** Line 143 says: "If `__init__` is NOT already in `file_spec.elements` with `parent_class == element.name`, add a second sub-element for `__init__`." This is backwards. If `__init__` is NOT in the manifest, there is no spec for it — the decomposer has nothing to generate. The correct logic is: if `__init__` IS in `file_spec.elements` (it exists as a separate element awaiting generation), it's already handled by the engine's normal loop and should NOT be added to the plan. If `__init__` is NOT in `file_spec.elements`, it doesn't exist and the class doesn't need one — don't add it. The plan should only decompose what the manifest says exists. | Rewrite as: "If `__init__` IS in `file_spec.elements`, it is a separate manifest element — do NOT add it to the plan (the engine handles it). Only generate an `init` sub-element if the manifest explicitly includes it AND it is not yet handled by the engine's element loop." |
| R3-S2 | Step 1.3 | 🔴 high | **`assembly_time_ms: 0` placeholder is never populated.** The `decomposition_metadata` dict at line 501 sets `"assembly_time_ms": 0` with a comment "set from assembly timing" — but there is no code to capture a pre-assembly timestamp or compute this value. As written it will always be `0` in the postmortem report. Either: (a) capture `assemble_start = time.monotonic()` before line 455 and compute `(time.monotonic() - assemble_start) * 1000`, or (b) remove `assembly_time_ms` from the dict entirely if it's not meaningful for Phase 1 (since class shell assembly is trivial). | Add `assemble_start = time.monotonic()` before `self._decomposer.assemble(...)` and compute `assembly_time_ms` from it. |
| R3-S3 | Step 1.3 | 🟡 medium | **Sub-elements passed `skeleton` may cause live-skeleton side-effects.** `_handle_simple(sub.element_spec, file_spec, skeleton, ...)` at line 418 passes the real `skeleton` string. `_handle_simple` calls `splice_body_into_skeleton(code, element, skeleton)` internally which returns a new string rather than mutating — BUT if any implementation detail inside `_handle_simple` writes to the skeleton object or if the splicer has side effects, the live skeleton is polluted. More concretely: `_handle_simple` for a sub-element `_class_attributes` will splice attribute code into the skeleton, advancing the skeleton's state. If a subsequent sub-element fails, the skeleton has been partially modified before the rollback of few-shot history — but skeleton rollback is never done. The plan only rolls back `self._completed`; it doesn't restore the skeleton. | Either pass a copy `skeleton[:]` (strings are immutable; this is fine), or document explicitly that `_handle_simple` for sub-elements is called with `splice=False` / a different skeleton accumulation mode. Verify `_handle_simple` does not mutate shared state beyond `self._completed`. |
| R3-S4 | Step 2.1 | 🟡 medium | **`inspect_decomposition()` interface is undefined — no return contract.** Line 760 says "returns strategy name + estimated sub-count without building a full plan." But neither the return type nor the dict keys are specified. The caller at line 755-757 reads `info.get("viable")`, `info.get("strategy")`, `info.get("sub_count")` — if `inspect_decomposition` omits any of these keys (e.g., returns `{}` when not decomposable), the report silently shows wrong values (`False`, `None`, `0`). Define the explicit return contract: `{"viable": bool, "strategy": Optional[str], "sub_count": int}`. | Add return type annotation `-> dict[str, Any]` and specify all keys in the Step 2.1 spec. |
| R3-S5 | Step 2.3 | 🟡 medium | **Postmortem serialization condition is different from the tracking condition.** Step 1.5 tracks decomposed elements via `er.decomposition_metadata is not None`. Step 2.3 (line 819) checks `er.get("tier") == "moderate" and er.get("success")` — this uses a *serialized dict* (the JSON repr of `ElementResult`), not the dataclass field directly. These conditions are different: a MODERATE element that succeeded but wasn't decomposed (future scenario) would pass Step 2.3's condition but not Step 1.5's. Align: use `er.get("decomposition_metadata") is not None` in the serialization check too. | Change Step 2.3 condition to `if er.get("decomposition_metadata") is not None`. |
| R3-S6 | Step 1.4 | 🟡 medium | **Test assertion `class_result.code == "pass"` may be wrong for `class_compose` strategy.** At line 681, the integration test asserts `code == "pass"`. But the `assemble()` method returns the composed class code — for a class shell with no attrs and no `__init__`, this is the class declaration + docstring + `pass` body: multiple lines, not the single string `"pass"`. The engine sets `ElementResult.code = assembled`, which is the full assembled output. If assemble returns just `"pass"` as the body token to pass to the splicer, or if it returns the full class text, the assertion must match. Clarify: does `assemble_class()` return `"pass"` (the body token) or `"class CustomJsonFormatter(...):\n    ...\n    pass"` (the full class)? | Determine what `assemble_class()` returns for a shell-only plan and fix the assertion accordingly. Add a comment in the test explaining what `code` represents in this context. |
| R3-S7 | Step 3.1 | 🟢 low | **`_build_synthetic_spec` is a module-level function but Step 3.3 registers it as a strategy, not on the decomposer.** Step 3.1 defines `_build_synthetic_spec()` as a free function in `decomposer.py`. `FunctionChainStrategy.plan()` will need to call it to build helper specs. The `ClassDecomposeStrategy` also needs it for the `class_attr` and `__init__` synthetic specs. Since both strategies need it, it should be a shared utility — confirm it's accessible from both strategies (same module) and that the naming convention (`_build_synthetic_spec` with leading underscore) marks it as internal to the module, not a method on any class. | Add a note: "`_build_synthetic_spec` is a module-level utility in `decomposer.py` — not a method. Both `ClassDecomposeStrategy` and `FunctionChainStrategy` call it directly." |

### Quick Wins

| ID | Step | Severity | Suggestion |
|----|------|----------|-----------|
| R3-Q1 | Step 1.3 | low | The `can_decompose()` + `decompose()` double sweep (R3 carry from REQ review) exists in the plan too: `_handle_moderate` calls `can_decompose()` (line 319) and then `decompose()` (line 337), which internally calls `can_handle()` again. Consider collapsing into a single `try_decompose() -> Optional[DecompositionPlan]` call that returns `None` for "not decomposable" — eliminating the redundant pass. Low-priority since strategy lists are small. |
| R3-Q2 | Step 1.4 | low | `test_cannot_decompose_function` (line 646) says "Phase 1 has no function strategy — returns False." This test will become wrong in Phase 3 when `FunctionChainStrategy` is added. Add a note that this test needs updating in Phase 3, or parametrize it with `config.function_chain_enabled=False` to remain valid. |
| R3-Q3 | Step 2.3 | low | The postmortem check at line 819 uses `er.get("tier")` and `er.get("success")` as if operating on a dict — but earlier in the method `er` refers to `ElementResult` dataclass instances. Verify whether `_serialize_file_result` processes dataclasses or dicts. If dataclasses, the access should be `er.tier` and `er.success`. If dicts, the check should use `.get()`. The mismatch is a latent AttributeError. |

### Triage Disposition

| ID | Disposition | Applied To | Notes |
|----|------------|------------|-------|
| R3-S1 | **ACCEPTED** | Step 1.2 | `__init__` detection logic rewritten: manifest elements handled by engine loop, not decomposition plan |
| R3-S2 | **ACCEPTED** | Step 1.3 | `assemble_start` timing added; `assembly_time_ms` populated from real measurement |
| R3-S3 | **ACCEPTED** | Step 1.3 | Skeleton immutability documented; no rollback needed for strings |
| R3-S4 | **ACCEPTED** | Step 2.1 | `inspect_decomposition` return contract specified: `{"viable": bool, "strategy": Optional[str], "sub_count": int}` |
| R3-S5 | **ACCEPTED** | Step 2.3 | Postmortem condition aligned: `er.decomposition_metadata is not None` with dataclass attribute access |
| R3-S6 | **ACCEPTED** | Step 1.4 | Test assertion clarified: `code == "pass"` is the body token for splicer; `decomposition_metadata` also asserted |
| R3-S7 | **ACCEPTED** | Step 3.1 | `_build_synthetic_spec` documented as module-level shared utility |
| R3-Q1 | **ACCEPTED** | Step 1.3 | `can_decompose()` + `decompose()` collapsed to single `decompose()` call in generation path |
| R3-Q2 | **ACCEPTED** | Step 1.4 | Phase 3 update note added to `test_cannot_decompose_function` |
| R3-Q3 | **ACCEPTED** | Step 2.3 | Dataclass attribute access used instead of dict `.get()` |
