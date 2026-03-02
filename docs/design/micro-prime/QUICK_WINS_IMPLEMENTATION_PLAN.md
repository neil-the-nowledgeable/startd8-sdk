# Quick Wins Implementation Plan

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-01
> **Parent requirements:** [REQ-MP-7xx_QUICK_WINS.md](./REQ-MP-7xx_QUICK_WINS.md)
> **Companion to:** [MICRO_PRIME_IMPLEMENTATION_PLAN.md](./MICRO_PRIME_IMPLEMENTATION_PLAN.md)
> **Goal:** Deliver incremental Micro Prime value through 8 ordered steps that maximize the ratio of value delivered to code written. Each step is independently shippable and tested.

---

## Relationship to Main Implementation Plan

The main `MICRO_PRIME_IMPLEMENTATION_PLAN.md` organizes work by subsystem (Phases 1-5: templates, repair, prompting, engine, adapters). This plan reorganizes the **same work** by value delivery order — what to build first so that every intermediate state is useful.

The two plans are compatible. This plan's 8 steps map onto the main plan's phases, but frontload the highest-leverage pieces from each phase rather than completing one subsystem before starting the next.

| Quick Win Step | Main Plan Phase | What's Pulled Forward |
|---------------|----------------|----------------------|
| 1. splice_body() | Phase 2 (splicer.py) | Body insertion mechanism — moved from Phase 2 to Step 1 |
| 2. Template registry | Phase 1A | Unchanged — but now delivers value immediately via splice_body() |
| 3. Model catalog entry | Phase 3 | Pulled from Phase 3 — trivial but prerequisite for Steps 5+ |
| 4. Repair MVP | Phase 1B | Subset of repair pipeline — 2 of 7 steps (fence strip + indent) |
| 5. Classifier extraction | Phase 3 (classifier.py) | Extracted from experiment script, not built from scratch |
| 6. Few-shot wiring | Phase 2 (prompt_builder.py) | Subset of prompt builder — few-shot accumulation only |
| 7. Element-level gate | Phase 3 (classifier.py) | Refinement added to classifier from Step 5 |
| 8. Remaining repair steps | Phase 1B | Remaining 4 of 7 repair steps |

---

## Guiding Principles

1. **Extract before you write.** If the experiment script has validated logic, move it — don't rewrite it (REQ-MP-701).
2. **Delegate, don't duplicate.** If a production utility does the job, import it — don't reinvent it (REQ-MP-700).
3. **Ship subsets safely.** The `@repair_step` decorator (REQ-MP-703) means any subset of repair steps is safe to ship.
4. **Test at each step.** Every step has an integration test gate. Don't proceed if it fails.
5. **Compound wins.** Steps are ordered so that each amplifies the next (REQ-MP-704).

---

## Step 1: splice_body() on DeterministicFileAssembler

**Requirements:** REQ-MP-702, REQ-MP-202, REQ-MP-505
**Modifies:** `src/startd8/utils/file_assembler.py`
**Effort:** ~25 lines + ~8 tests
**Unblocks:** Every subsequent step (all body insertion flows through this method)

### What to build

Add a `splice_body()` method to the existing `DeterministicFileAssembler` class.

### Implementation detail

```python
# In src/startd8/utils/file_assembler.py, add to DeterministicFileAssembler class:

def splice_body(
    self,
    skeleton_source: str,
    element_name: str,
    body: str,
    parent_class: Optional[str] = None,
) -> str:
```

**Algorithm (pseudocode):**

```
1. tree = ast.parse(skeleton_source)
2. Walk tree to find target node:
   - If parent_class: find ClassDef with name == parent_class,
     then find FunctionDef/AsyncFunctionDef with name == element_name inside it
   - Else: find top-level FunctionDef/AsyncFunctionDef/Assign with name == element_name
3. Within target node's body, find:
   - Raise(exc=Name(id="NotImplementedError")) for functions/methods
   - Constant(...) (Ellipsis) for constants/variables
4. Get stub_line = node.lineno (1-indexed), stub_indent from source line leading whitespace
5. Dedent body via textwrap.dedent(), re-indent to stub_indent via textwrap.indent()
6. Split skeleton_source into lines, replace stub line(s) with re-indented body lines
7. result = "\n".join(lines)
8. ast.parse(result)  # Validate — raise ValueError on failure
9. return result
```

**Edge cases to handle:**

| Case | Behavior |
|------|----------|
| Element has docstring before `raise NotImplementedError` | Replace only the `raise` line, preserve docstring |
| Constant with `... ` (Ellipsis) stub | Replace RHS of assignment (`TIMEOUT = ...` → `TIMEOUT = 30`) |
| Body has wrong indentation | Dedent to 0, re-indent to stub level |
| Element not found in skeleton | Raise `ValueError(f"Element {element_name} not found")` |
| Result fails `ast.parse()` | Raise `ValueError(f"Splice produced invalid Python: {error}")` |
| Multiple elements in same class | Only the target element is modified |

### Existing code to leverage

- `file_assembler.py:408` — know exact stub format: `raise NotImplementedError` (no message)
- `file_assembler.py:56` — `SKELETON_SENTINEL = "# [STARTD8-SKELETON]"` for file identification
- `file_assembler.py:372` — `_render_element()` shows how indent levels are computed: `body_indent = indent + "    "`

### Tests (`tests/unit/utils/test_file_assembler.py` — extend existing)

1. Splice function body into top-level function stub → valid file
2. Splice method body into class method stub → valid file
3. Splice constant value into ellipsis stub → valid file
4. Splice with wrong indentation in body → corrected to stub level
5. Splice into nonexistent element → `ValueError`
6. Splice that produces invalid Python → `ValueError`
7. Multiple sequential splices into same skeleton → all bodies present, valid file
8. Splice preserves imports, `__all__`, other elements unchanged

### Integration test gate

```python
# Render skeleton → splice a known-good body → ast.parse() passes → body text is in output
assembler = DeterministicFileAssembler()
skeleton = assembler.render_file(file_spec)
result = assembler.splice_body(skeleton, "get_secret", "    return os.environ[name]")
assert ast.parse(result)
assert "return os.environ[name]" in result
assert "raise NotImplementedError" in result  # Other stubs still present
```

---

## Step 2: Template Registry (TRIVIAL tier)

**Requirements:** REQ-MP-300–304
**New file:** `src/startd8/micro_prime/templates.py`
**Effort:** ~100 lines + ~15 tests
**Depends on:** Step 1 (splice_body for integration)

### What to build

A `TemplateRegistry` class that deterministically generates code for TRIVIAL elements — those whose implementation is fully derivable from manifest data.

### Implementation detail

```python
# src/startd8/micro_prime/templates.py

@dataclass
class TemplateMatch:
    template_name: str
    code: str

class TemplateRegistry:
    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._templates: list[tuple[str, MatchFn, RenderFn]] = [
            ("config_constant", self._match_config_constant, self._render_config_constant),
            ("app_instance", self._match_app_instance, self._render_app_instance),
            ("type_alias", self._match_type_alias, self._render_type_alias),
            ("dunder_init", self._match_dunder_init, self._render_dunder_init),
            ("dunder_repr", self._match_dunder_repr, self._render_dunder_repr),
            ("dunder_eq", self._match_dunder_eq, self._render_dunder_eq),
        ]

    def match(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        contracts: list[InterfaceContract],
    ) -> Optional[TemplateMatch]:
        """Try each template in priority order. Return first match or None."""
        if not self._enabled:
            return None
        for name, match_fn, render_fn in self._templates:
            if match_fn(element, file_spec, contracts):
                code = render_fn(element, file_spec, contracts)
                # Validate output
                try:
                    ast.parse(code)
                except SyntaxError:
                    continue  # Skip broken template, try next
                return TemplateMatch(template_name=name, code=code)
        return None
```

### Template implementations

**Config constant** (REQ-MP-301):
- Match: `element.kind == CONSTANT` AND contract with `constant_value` is not None
- Render: `{name}: {type} = {value}` with proper quoting

**App instance** (REQ-MP-302):
- Match: `element.kind == CONSTANT` AND name in `{"app", "application", "server", "api"}` AND file imports Flask/FastAPI
- Render: `app = Flask(__name__)` or `app = FastAPI()`

**Type alias** (REQ-MP-303):
- Match: `element.kind == TYPE_ALIAS`
- Render: `TypeName = BaseType` from manifest metadata

**Dunder methods** (`__init__`, `__repr__`, `__eq__`):
- Match: `element.kind in (METHOD, ASYNC_METHOD)` AND `element.name` is a dunder AND all params are simple types
- Render from signature: `__init__` → `self.x = x` for each param; `__repr__` → f-string; `__eq__` → compare all attrs

**Async awareness** (from R2-S1): Check `element.kind` for `ASYNC_FUNCTION`/`ASYNC_METHOD` from `ElementKind` enum. Emit `async def` accordingly. No `is_async` boolean exists on `ForwardElementSpec`.

### Existing code to leverage

- `forward_manifest.ForwardElementSpec` — `kind`, `name`, `signature`, `decorators`, `parent_class`
- `forward_manifest.InterfaceContract` — `constant_value`, `category`
- `utils/code_manifest.ElementKind` — enum for element type detection
- `utils/code_manifest.Signature`, `Param` — for dunder method rendering

### Tests (`tests/unit/micro_prime/test_templates.py`)

1. Config constant with string value → properly quoted
2. Config constant with int value → numeric literal
3. Config constant with bool → `True`/`False`
4. App instance with Flask import → `app = Flask(__name__)`
5. App instance without framework import → no match
6. Type alias → `TypeName = BaseType`
7. `__init__` with 3 params → `self.x = x` for each
8. `__repr__` → f-string with all attrs
9. `__eq__` → comparison of all attrs
10. Async method → `async def` prefix
11. No match → returns `None`
12. Template disabled → returns `None`
13. Template produces invalid code → skip, try next
14. Template output passes `ast.parse()`
15. Priority order: first matching template wins

### Integration test gate

```python
# Template match → splice into skeleton → valid file
match = registry.match(element, file_spec, contracts)
assert match is not None
result = assembler.splice_body(skeleton, element.name, match.code)
assert ast.parse(result)
```

---

## Step 3: Model Catalog Entry

**Requirements:** REQ-MP-707, REQ-MP-104
**Modifies:** `src/startd8/model_catalog.py`
**Effort:** ~12 lines + 0 new tests (existing catalog tests cover)

### What to build

Add the Ollama provider section and `startd8-coder` entry to the SDK model catalog.

### Implementation detail

**Three insertion points in `model_catalog.py`:**

**1. `Models` class constants** (after existing provider sections, ~line 117):
```python
# Ollama (local)
OLLAMA_STARTD8_CODER = "ollama:startd8-coder"
```

**2. `_MODEL_REGISTRY` dict** (after existing entries, ~line 250):
```python
"startd8-coder": ModelInfo(
    provider="ollama",
    model_id="startd8-coder",
    tier="fast",
    capabilities={"text", "code"},
),
```

**3. `get_latest_model()` tier mapping** (after existing provider cases, ~line 321):
```python
"ollama": {
    "fast": Models.OLLAMA_STARTD8_CODER,
    "balanced": Models.OLLAMA_STARTD8_CODER,
},
```

### Existing code to leverage

- `model_catalog.ModelInfo` — frozen dataclass with `provider`, `model_id`, `tier`, `capabilities`
- Existing entries (23 models) as format templates
- `get_latest_model()` dispatch pattern

### Integration test gate

```python
from startd8.model_catalog import Models, get_latest_model, _MODEL_REGISTRY

assert Models.OLLAMA_STARTD8_CODER == "ollama:startd8-coder"
assert "startd8-coder" in _MODEL_REGISTRY
assert _MODEL_REGISTRY["startd8-coder"].provider == "ollama"
assert get_latest_model("ollama", "fast") == "ollama:startd8-coder"
```

---

## Step 4: Repair Pipeline MVP (Fence Strip + Indent Normalize)

**Requirements:** REQ-MP-703, REQ-MP-706, REQ-MP-400, REQ-MP-402, REQ-MP-405, REQ-MP-406
**New file:** `src/startd8/micro_prime/repair.py`
**Effort:** ~90 lines + ~15 tests
**Depends on:** None (independent of Steps 1-3)

### What to build

The `@repair_step` decorator and the first two repair steps: fence stripping (delegation) and indentation normalization (extraction).

### File structure

```python
# src/startd8/micro_prime/repair.py

"""Manifest-guided repair pipeline for local model output.

Incrementally deployable: each step is decorated with @repair_step
which enforces the non-destructive guarantee (REQ-MP-406).
"""

from startd8.utils.code_extraction import extract_code_from_response

# --- Infrastructure ---

@dataclass
class RepairStepResult:
    name: str
    modified: bool
    rolled_back: bool
    code: str
    metrics: dict[str, Any]

def is_syntactically_valid(code: str) -> bool:
    """Check if code passes ast.parse(). Extracted from experiment script:983-1004."""
    ...  # Extract from experiment script _try_parse(), rename

def extract_syntax_error(code: str) -> str:
    """Get human-readable syntax error. Extracted from experiment script:1061-1067."""
    ...  # Extract verbatim

def repair_step(name: str):
    """Decorator enforcing non-destructive guarantee (REQ-MP-703)."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(code: str, *args, **kwargs) -> RepairStepResult:
            was_valid = is_syntactically_valid(code)
            try:
                repaired = fn(code, *args, **kwargs)
            except Exception:
                return RepairStepResult(name=name, modified=False,
                                        rolled_back=False, code=code, metrics={})

            if repaired == code:
                return RepairStepResult(name=name, modified=False,
                                        rolled_back=False, code=code, metrics={})

            if was_valid and not is_syntactically_valid(repaired):
                return RepairStepResult(name=name, modified=False,
                                        rolled_back=True, code=code,
                                        metrics={"rolled_back": True})

            return RepairStepResult(name=name, modified=True,
                                    rolled_back=False, code=repaired, metrics={})
        return wrapper
    return decorator

# --- MVP Steps ---

@repair_step("fence_strip")
def strip_fences(code: str, **kwargs) -> str:
    """Step 1: Delegate to existing extract_code_from_response(). REQ-MP-400."""
    return extract_code_from_response(code)

@repair_step("indentation_normalize")
def normalize_indentation(
    code: str,
    target: ForwardElementSpec,
    skeleton_source: Optional[str] = None,
) -> str:
    """Step 4: Re-indent to correct level. REQ-MP-402.
    Extracted from experiment script:1007-1058 with skeleton-aware priority added.
    """
    # Priority 1: Skeleton-aware (if skeleton available)
    if skeleton_source:
        target_indent = _get_skeleton_body_indent(skeleton_source, target)
        if target_indent is not None:
            dedented = textwrap.dedent(code).strip()
            return textwrap.indent(dedented, target_indent)

    # Priority 2-6: Heuristic strategies (extracted from experiment script)
    # ... 5 strategies from _normalize_indentation()
    ...

# --- Pipeline ---

class RepairPipeline:
    """Ordered sequence of repair steps. REQ-MP-706: incrementally deployable."""

    # MVP default: only fence strip + indent normalize
    DEFAULT_STEPS = ["fence_strip", "indentation_normalize"]

    def __init__(self, enabled_steps: Optional[list[str]] = None) -> None:
        self._step_registry: dict[str, Callable] = {
            "fence_strip": strip_fences,
            "indentation_normalize": normalize_indentation,
        }
        self._enabled = enabled_steps or self.DEFAULT_STEPS

    def run(
        self,
        code: str,
        target: ForwardElementSpec,
        skeleton_source: Optional[str] = None,
        **kwargs,
    ) -> RepairResult:
        """Run all enabled steps in order. Return final code + per-step attribution."""
        results: list[RepairStepResult] = []
        current = code
        for step_name in self._enabled:
            step_fn = self._step_registry.get(step_name)
            if not step_fn:
                continue
            result = step_fn(current, target=target, skeleton_source=skeleton_source)
            results.append(result)
            current = result.code

        return RepairResult(
            code=current,
            steps_applied=[r.name for r in results if r.modified],
            ast_valid=is_syntactically_valid(current),
            metrics={r.name: r.metrics for r in results},
        )
```

### Extraction from experiment script

| Function | Source Lines | Target | Changes |
|----------|------------|--------|---------|
| `_try_parse()` | 983-1004 | `is_syntactically_valid()` | Rename; no logic changes |
| `_extract_syntax_error()` | 1061-1067 | `extract_syntax_error()` | Verbatim |
| `_normalize_indentation()` | 1007-1058 | `normalize_indentation()` | Add skeleton-aware priority strategy; keep 5 heuristic fallbacks |

### Existing code to leverage

- `utils/code_extraction.extract_code_from_response()` — fence stripping (zero new code for Step 1)
- Experiment script strategies — 5 validated indentation heuristics

### Tests (`tests/unit/micro_prime/test_repair.py`)

1. `@repair_step` decorator: valid→invalid reverts to original
2. `@repair_step` decorator: invalid→valid keeps changes
3. `@repair_step` decorator: no change returns `modified=False`
4. `@repair_step` decorator: step raises exception → code unchanged
5. Fence strip: markdown-fenced code → clean Python
6. Fence strip: already clean code → unchanged
7. Indent normalize: 12-space body → 8-space (method in class) using skeleton
8. Indent normalize: 0-space body → 4-space (top-level function) using skeleton
9. Indent normalize: mixed tabs/spaces → 4-space via heuristic fallback
10. Indent normalize: without skeleton → fallback to depth-based heuristic
11. Pipeline with 2 steps: fenced + wrong indent → clean, correctly indented
12. Pipeline with disabled step: only enabled steps run
13. Pipeline returns per-step attribution
14. `RepairResult.ast_valid` reflects final code state
15. `is_syntactically_valid()` matches experiment script `_try_parse()` for same inputs

### Integration test gate

```python
pipeline = RepairPipeline()  # MVP defaults
result = pipeline.run(
    code="```python\ndef foo():\n        return 42\n```",
    target=element_spec,
    skeleton_source=skeleton,
)
assert result.ast_valid
assert "fence_strip" in result.steps_applied
assert "indentation_normalize" in result.steps_applied
assert "```" not in result.code
```

---

## Step 5: Heuristic Classifier Extraction

**Requirements:** REQ-MP-701, REQ-MP-500, REQ-MP-501
**New file:** `src/startd8/micro_prime/classifier.py`
**Effort:** ~170 lines (148 extracted + 22 new) + ~15 tests
**Depends on:** Step 2 (template registry for TRIVIAL gate)

### What to build

Extract the validated heuristic classifier from the experiment script and add a TRIVIAL tier gate backed by the template registry.

### File structure

```python
# src/startd8/micro_prime/classifier.py

"""Tier classification for Micro Prime elements.

Heuristic classifier extracted from experiment_local_model_routing.py:189-336.
Added: TRIVIAL tier gate via template registry, MicroPrimeTier enum.
"""

class MicroPrimeTier(str, Enum):
    TRIVIAL = "trivial"    # Template-generated, no model
    SIMPLE = "simple"      # Local model (startd8-coder)
    MODERATE = "moderate"  # Cloud model (Haiku/Sonnet)
    COMPLEX = "complex"    # Cloud model (Sonnet/Opus)

@dataclass
class ClassificationResult:
    tier: MicroPrimeTier
    score: int
    reasons: list[str]
    template_match: Optional[TemplateMatch]  # Non-None for TRIVIAL

# Signal constants (extracted from experiment script:189-220)
_SIMPLE_NAME_PREFIXES = {"get_", "is_", "has_", "to_", "from_", "set_", "make_"}
_COMPLEX_DECORATORS = {"abstractmethod", "overload", "override"}
_ORCHESTRATOR_NAMES = {"start", "run", "serve", "main", "execute"}
_ORCHESTRATOR_SUFFIXES = {"_server", "_service", "_app", "_worker"}

# External API package set (from REQ-MP-501)
_EXTERNAL_API_PACKAGES = {
    "grpc", "grpcio", "httpx", "aiohttp", "requests",
    "flask", "fastapi", "django", "starlette",
    "jinja2", "mako",
    "google.cloud", "google.auth", "google.api_core",
    "boto3", "botocore", "azure",
    "sqlalchemy", "alembic", "asyncpg", "psycopg2",
    "celery", "redis", "kombu",
    "locust", "playwright",
}

def classify_element(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    template_registry: Optional[TemplateRegistry] = None,
) -> ClassificationResult:
    """Classify element into TRIVIAL/SIMPLE/MODERATE/COMPLEX.

    Gate order (REQ-MP-304):
    1. Template registry match → TRIVIAL
    2. Heuristic scoring → SIMPLE/MODERATE/COMPLEX
    """
    # Gate 1: TRIVIAL (template match)
    if template_registry:
        match = template_registry.match(element, file_spec, contracts)
        if match:
            return ClassificationResult(
                tier=MicroPrimeTier.TRIVIAL, score=-99,
                reasons=["template_match: " + match.template_name],
                template_match=match,
            )

    # Gate 2: Heuristic (extracted from experiment script:221-336)
    score, reasons = _heuristic_score(element, file_spec, contracts)

    # Import complexity gate (REQ-MP-501)
    import_bump = _import_complexity_bump(file_spec)
    if import_bump > 0:
        score += import_bump
        reasons.append(f"external APIs: {import_bump} packages")

    if score <= -1:
        tier = MicroPrimeTier.SIMPLE
    elif score <= 2:
        tier = MicroPrimeTier.MODERATE
    else:
        tier = MicroPrimeTier.COMPLEX

    return ClassificationResult(tier=tier, score=score,
                                 reasons=reasons, template_match=None)


def _heuristic_score(...) -> tuple[int, list[str]]:
    """Scoring logic extracted from experiment script:221-336. ~100 lines."""
    ...

def _import_complexity_bump(file_spec: ForwardFileSpec) -> int:
    """File-level import gate. REQ-MP-501. ~15 lines."""
    ...

def collect_elements(...) -> list[...]:
    """Extracted from experiment script:1263-1292. No changes."""
    ...
```

### Extraction from experiment script

| Function | Source Lines | Target | Changes |
|----------|------------|--------|---------|
| `classify_element_heuristic()` | 189-336 | `classify_element()` + `_heuristic_score()` | Split into public API + internal scoring; add TRIVIAL gate; return `ClassificationResult` instead of `(Complexity, str)` tuple |
| Signal constants | 189-220 | Module-level constants | Moved to module level (already are in experiment script) |
| `collect_elements()` | 1263-1292 | `collect_elements()` | Verbatim |

### Existing code to leverage

- `forward_manifest.ForwardElementSpec` — all classification metadata
- `utils/code_manifest.ElementKind` — element type detection
- Template registry from Step 2 — TRIVIAL gate

### Tests (`tests/unit/micro_prime/test_classifier.py`)

1. Config constant with contract value → TRIVIAL
2. `__init__` with simple params → TRIVIAL (via template match)
3. Element with no template match + low score → SIMPLE
4. Element with external API imports → MODERATE (score bumped)
5. Element with ≥3 binding constraints → COMPLEX
6. Async function → +1 complexity
7. Class definition → +2 complexity
8. Property accessor → SIMPLE
9. Orchestrator name pattern → MODERATE/COMPLEX
10. `get_` prefix with simple return → score -2 (SIMPLE)
11. Import gate: `grpc` + `google.cloud` → +2
12. Import gate: `json` + `logging` → +0
13. `collect_elements()` scoped to task IDs → correct element list
14. Classification result includes reasons for auditability
15. Template registry disabled → no TRIVIAL classifications

### Integration test gate

```python
result = classify_element(element, file_spec, contracts, template_registry)
assert result.tier in MicroPrimeTier
assert len(result.reasons) > 0
# Config constant → TRIVIAL
const_result = classify_element(config_const, file_spec, contracts, template_registry)
assert const_result.tier == MicroPrimeTier.TRIVIAL
assert const_result.template_match is not None
```

---

## Step 6: Few-Shot Wiring + Compound Chain

**Requirements:** REQ-MP-704, REQ-MP-205
**New file:** `src/startd8/micro_prime/prompt_builder.py`
**Effort:** ~60 lines (44 extracted + 16 new) + ~8 tests
**Depends on:** Step 2 (templates produce few-shot examples), Step 5 (classifier determines SIMPLE elements)

### What to build

Extract the few-shot example finder from the experiment script and wire it into the processing order so TRIVIAL results feed SIMPLE generation.

### File structure

```python
# src/startd8/micro_prime/prompt_builder.py

"""Skeleton-first prompt construction for local model generation.

Builds prompts that provide the skeleton context, body-only instruction,
and few-shot examples accumulated from prior successful generations.
"""

@dataclass
class GeneratedBody:
    """A successfully generated body, available as a few-shot example."""
    element_fqn: str
    element_name: str
    parent_class: Optional[str]
    kind: ElementKind
    body: str

def find_few_shot_examples(
    target: ForwardElementSpec,
    completed: list[GeneratedBody],
    max_examples: int = 2,
) -> list[GeneratedBody]:
    """Find 1-2 similar completed elements as few-shot examples.

    Priority (REQ-MP-205): same-class > same-file > same-kind.
    Extracted from experiment script:774-817.
    """
    ...  # Extract from experiment script, adapt ClassifiedElement → GeneratedBody

def estimate_body_lines(element: ForwardElementSpec) -> str:
    """Estimate expected body length hint.
    Extracted from experiment script:756-771. No changes.
    """
    ...
```

### Compound chain implementation (REQ-MP-704)

The compound chain is not a separate module — it's an **ordering constraint** in the engine's per-file processing loop. But since the engine (Phase 3 in main plan) doesn't exist yet, this step prepares the building blocks:

1. `GeneratedBody` dataclass — the unit of few-shot accumulation
2. `find_few_shot_examples()` — the selection logic
3. Processing order contract: TRIVIAL first, then SIMPLE, accumulating `GeneratedBody` list

The engine (built later) will call these in order:

```python
# In engine.process_file() — illustrative, not built in this step
completed: list[GeneratedBody] = []

# Phase 1: TRIVIAL (templates)
for elem in trivial_elements:
    body = template_registry.match(elem, ...).code
    completed.append(GeneratedBody(elem.fqn, elem.name, elem.parent_class, elem.kind, body))
    assembler.splice_body(skeleton, elem.name, body, elem.parent_class)

# Phase 2: SIMPLE (local model with few-shot)
for elem in simple_elements:
    examples = find_few_shot_examples(elem, completed)
    prompt = build_body_prompt(elem, skeleton, examples)  # Uses few-shot
    body = generate_with_local_model(prompt)
    body = repair_pipeline.run(body, elem, skeleton).code
    if is_syntactically_valid(body):
        completed.append(GeneratedBody(...))  # Success → becomes example for next
        assembler.splice_body(skeleton, elem.name, body, elem.parent_class)
```

### Extraction from experiment script

| Function | Source Lines | Target | Changes |
|----------|------------|--------|---------|
| `_find_few_shot_examples()` | 774-817 | `find_few_shot_examples()` | Adapt from `ClassifiedElement` to `GeneratedBody`; keep 3-tier priority |
| `_estimate_body_lines()` | 756-771 | `estimate_body_lines()` | Verbatim |

### Tests (`tests/unit/micro_prime/test_prompt_builder.py`)

1. Few-shot: same-class examples prioritized over same-file
2. Few-shot: max 2 examples returned
3. Few-shot: no completed elements → empty list
4. Few-shot: TRIVIAL body used as example for SIMPLE
5. Few-shot: accumulated SIMPLE success used as example for next SIMPLE
6. `estimate_body_lines()`: property → "1-2"
7. `estimate_body_lines()`: 5-param function → "5-12"
8. `GeneratedBody` dataclass round-trip

### Integration test gate

```python
# Template fills TRIVIAL → becomes few-shot for SIMPLE
trivial_body = template_match.code
completed = [GeneratedBody("Foo.__init__", "__init__", "Foo", ElementKind.METHOD, trivial_body)]
examples = find_few_shot_examples(simple_element, completed)
assert len(examples) >= 1
assert examples[0].body == trivial_body
```

---

## Step 7: Element-Level Import Gate

**Requirements:** REQ-MP-708, REQ-MP-511
**Modifies:** `src/startd8/micro_prime/classifier.py` (from Step 5)
**Effort:** ~30 lines + ~6 tests
**Depends on:** Step 5 (classifier to add the gate to)

### What to build

Add Pass 2 (per-element) to the import complexity gate, refining the file-level Pass 1 (REQ-MP-501) already in the classifier.

### Implementation detail

```python
# Add to src/startd8/micro_prime/classifier.py

def _element_uses_external_api(
    element: ForwardElementSpec,
    file_externals: set[str],
) -> bool:
    """Pass 2: Check if THIS element uses external APIs from file-level imports.

    Three signals (REQ-MP-708):
    1. Binding constraints reference external package names (+2 per match)
    2. Parameter types from external packages (+2 per match)
    3. Name patterns combined with external import presence (+1 per match)
    """
    if not file_externals:
        return False

    score = 0

    # Signal 1: Binding constraints
    for contract in element.binding_constraints or []:
        constraint_text = contract.lower() if isinstance(contract, str) else str(contract).lower()
        if any(pkg in constraint_text for pkg in file_externals):
            score += 2

    # Signal 2: Parameter types
    if element.signature:
        for param in element.signature.params:
            if param.annotation:
                if any(pkg in param.annotation for pkg in file_externals):
                    score += 2

    # Signal 3: Name patterns
    api_name_patterns = {"serve", "handle", "request", "response", "connect", "query"}
    if element.name.lower().rstrip("_") in api_name_patterns:
        score += 1

    return score > 0
```

**Integration into `classify_element()`:**

```python
# In classify_element(), after file-level import bump:
import_bump = _import_complexity_bump(file_spec)
if import_bump > 0:
    # Pass 2: per-element refinement (REQ-MP-511, REQ-MP-708)
    if not _element_uses_external_api(element, _file_external_packages(file_spec)):
        # Element doesn't actually use the external APIs — remove the bump
        reasons.append(f"element-level override: no external API usage")
    else:
        score += import_bump
        reasons.append(f"external APIs: {import_bump} packages (element confirmed)")
```

### Tests (add to `tests/unit/micro_prime/test_classifier.py`)

1. `HealthCheck.Check` in file with `grpc` import → SIMPLE (element doesn't use grpc)
2. `serve()` in file with `grpc` import → MODERATE (element name + import match)
3. Element with `grpc.ServicerContext` param type → MODERATE (type signal)
4. Element with `[BINDING: uses grpc streaming]` → MODERATE (constraint signal)
5. Element in file without external imports → unaffected
6. Element-level override logged in `reasons`

### Integration test gate

```python
# HealthCheck.Check in grpc-importing file → SIMPLE (not MODERATE)
result = classify_element(health_check_element, grpc_file_spec, [], template_registry)
assert result.tier == MicroPrimeTier.SIMPLE
assert "element-level override" in str(result.reasons)
```

---

## Step 8: Remaining Repair Steps

**Requirements:** REQ-MP-401 (over-gen trim), REQ-MP-407 (bare wrap), REQ-MP-403 (sig reconcile), REQ-MP-404 (import complete)
**Modifies:** `src/startd8/micro_prime/repair.py` (from Step 4)
**Effort:** ~200 lines + ~15 tests
**Depends on:** Step 4 (repair infrastructure + `@repair_step`)

### What to build

Add the remaining 4 repair steps to the pipeline, each wrapped with `@repair_step` for automatic non-destructive safety.

### Step implementations

**Over-generation trim** (REQ-MP-401):
```python
@repair_step("over_generation_trim")
def trim_to_target(code: str, target: ForwardElementSpec, **kwargs) -> str:
    """Remove extra functions/classes after the target element."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code  # Can't parse — pass through

    for node in ast.iter_child_nodes(tree):
        if _matches_target(node, target):
            return ast.get_source_segment(code, node) or code

    return code  # Target not found — pass through
```

**Bare statement wrap** (REQ-MP-407):
```python
@repair_step("bare_statement_wrap")
def wrap_bare_statements(code: str, target: ForwardElementSpec, **kwargs) -> str:
    """If model output is body-only (no def line), wrap in manifest's signature."""
    try:
        ast.parse(code)
        # Already valid as standalone — might be a full function
        tree = ast.parse(code)
        # Check if it's bare statements (no FunctionDef at top level)
        has_funcdef = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                         for n in ast.iter_child_nodes(tree))
        if has_funcdef:
            return code  # Already has function structure
    except SyntaxError:
        pass  # May be bare body statements — try wrapping

    # Wrap in the manifest's def line
    sig = _render_signature_from_manifest(target)
    prefix = "async def" if target.kind in ("async_function", "async_method") else "def"
    wrapped = f"{prefix} {target.name}{sig}:\n"
    wrapped += textwrap.indent(textwrap.dedent(code).strip(), "    ")
    return wrapped
```

**Signature reconcile** (REQ-MP-403):
```python
@repair_step("signature_reconcile")
def reconcile_signature(code: str, target: ForwardElementSpec, **kwargs) -> str:
    """Replace the model's def line with the manifest's canonical signature."""
    if not target.signature:
        return code
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    func_node = _find_function_node(tree, target.name)
    if not func_node:
        return code

    canonical = _render_signature_from_manifest(target)
    lines = code.split("\n")
    def_line = func_node.lineno - 1
    indent = " " * func_node.col_offset
    prefix = "async def" if isinstance(func_node, ast.AsyncFunctionDef) else "def"
    lines[def_line] = f"{indent}{prefix} {target.name}{canonical}:"

    return "\n".join(lines)
```

**Import completion** (REQ-MP-404):
```python
@repair_step("import_completion")
def complete_imports(code: str, target: ForwardElementSpec,
                     file_spec: ForwardFileSpec = None, **kwargs) -> str:
    """Add missing imports that the manifest specifies but the code doesn't have."""
    if not file_spec:
        return code
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    referenced = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    imported = _collect_imported_names(tree)

    missing_lines = []
    for imp in file_spec.imports:
        if imp.kind == "from":
            needed = [n for n in imp.names if n in referenced and n not in imported]
            if needed:
                missing_lines.append(f"from {imp.module} import {', '.join(needed)}")
        else:
            mod = imp.alias or imp.module.split(".")[0]
            if mod in referenced and mod not in imported:
                missing_lines.append(f"import {imp.module}")

    if not missing_lines:
        return code

    return "\n".join(missing_lines) + "\n\n" + code
```

### Register new steps in pipeline

```python
# In RepairPipeline.__init__(), update registry:
self._step_registry = {
    "fence_strip": strip_fences,
    "over_generation_trim": trim_to_target,
    "bare_statement_wrap": wrap_bare_statements,
    "indentation_normalize": normalize_indentation,
    "signature_reconcile": reconcile_signature,
    "import_completion": complete_imports,
}

# Update default steps for full pipeline:
FULL_STEPS = [
    "fence_strip",
    "over_generation_trim",
    "bare_statement_wrap",
    "indentation_normalize",
    "signature_reconcile",
    "import_completion",
]
```

### Tests (add to `tests/unit/micro_prime/test_repair.py`)

1. Over-gen trim: `get_secret` + `list_secrets` + `main()` → just `get_secret`
2. Over-gen trim: single target function → unchanged
3. Over-gen trim: unparseable code → pass through
4. Bare wrap: `return 42` → `def foo() -> int:\n    return 42`
5. Bare wrap: already has `def` line → unchanged
6. Bare wrap: async target → `async def`
7. Sig reconcile: `def format(self, rec)` → `def format(self, record: LogRecord) -> str`
8. Sig reconcile: matching signature → unchanged
9. Sig reconcile: no signature in manifest → unchanged
10. Import complete: body uses `json.dumps` without import → `import json` added
11. Import complete: import already present → not duplicated
12. Import complete: import not in manifest → not added
13. Full pipeline (6 steps): raw Ollama output → clean, valid Python
14. Pipeline with subset of steps: only enabled steps run
15. All steps wrapped by `@repair_step`: non-destructive guarantee holds

### Integration test gate

```python
pipeline = RepairPipeline(enabled_steps=RepairPipeline.FULL_STEPS)
result = pipeline.run(
    code=raw_ollama_output,
    target=element_spec,
    skeleton_source=skeleton,
    file_spec=file_spec,
)
assert result.ast_valid
assert len(result.steps_applied) > 0
```

---

## Summary

### Effort by step

| Step | New Lines | Extracted Lines | Tests | Files Touched |
|------|----------|----------------|-------|--------------|
| 1. splice_body() | ~25 | 0 | 8 | 1 modified |
| 2. Template registry | ~100 | 0 | 15 | 1 new |
| 3. Model catalog | ~12 | 0 | 0 | 1 modified |
| 4. Repair MVP | ~20 | ~81 | 15 | 1 new |
| 5. Classifier | ~22 | ~178 | 15 | 1 new |
| 6. Few-shot wiring | ~16 | ~60 | 8 | 1 new |
| 7. Element gate | ~30 | 0 | 6 | 1 modified |
| 8. Remaining repair | ~200 | 0 | 15 | 1 modified |
| **Total** | **~425** | **~319** | **82** | **4 new + 4 modified** |

### Files created

```
src/startd8/micro_prime/
├── templates.py         # Step 2 — template registry
├── repair.py            # Steps 4, 8 — repair pipeline
├── classifier.py        # Steps 5, 7 — tier classification
└── prompt_builder.py    # Step 6 — few-shot finder
```

### Files modified

```
src/startd8/utils/file_assembler.py    # Step 1 — splice_body()
src/startd8/model_catalog.py           # Step 3 — Ollama provider
```

### Cumulative value delivered

```
Step 1: [████                    ]  splice mechanism works
Step 2: [████████                ]  10-15% elements at $0
Step 3: [████████░               ]  SDK resolves local model
Step 4: [████████████            ]  raw output → valid Python (2-step repair)
Step 5: [████████████████        ]  zero-cost routing for all elements
Step 6: [██████████████████      ]  quality amplification via few-shot
Step 7: [███████████████████     ]  recover over-classified elements
Step 8: [████████████████████████]  full repair pipeline (6 steps)
```

### What comes after

These 8 steps deliver the **foundation subsystems**. The remaining work from the main implementation plan covers:

- **Engine orchestrator** (`engine.py`) — wires classifier + templates + repair + splicer into the per-file processing loop
- **Workflow adapters** (`artisan_adapter.py`, `prime_adapter.py`) — integration with Artisan and Prime
- **Models and config** (`models.py`) — Pydantic models for `MicroPrimeConfig`, `MicroPrimeResult`
- **Metrics** (`metrics.py`) — per-element metrics collection, cost reporting
- **Experiment script refactor** — delegate to SDK `MicroPrimeEngine`

Those are covered by Phases 3-5 of the main implementation plan and depend on the Quick Wins foundation being in place.
