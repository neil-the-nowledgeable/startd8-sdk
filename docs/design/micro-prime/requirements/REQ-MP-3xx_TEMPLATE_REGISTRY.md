# Layer 3 — Template Registry (REQ-MP-3xx)

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** Planned
> **New file:** `src/startd8/utils/code_templates.py`

---

## Overview

Some elements in a Forward Manifest can be generated with zero model inference — their implementation is fully determined by manifest data and contracts. A config constant with a known value, a Flask app instance where the import tells you the constructor, a type alias — these are deterministic string operations.

The template registry introduces a TRIVIAL tier below SIMPLE: matched elements are rendered by a pure function at zero cost and sub-millisecond latency. This is the "deterministic before probabilistic" principle applied at the element level.

## Rationale

In the online-boutique-demo seed (32 elements), the following were classified as MODERATE by the heuristic only because they were orchestrator-like names (`app`, `start`, `serve`). Several of these are actually trivial:

| Element | Current Classification | Template-Solvable? | Why |
|---------|----------------------|-------------------|-----|
| `app` (Flask instance) | MODERATE | Yes | `app = Flask(__name__)` — derivable from import |
| `SECRET_KEY` constant | SIMPLE | Yes | Value in `InterfaceContract.constant_value` |
| `PORT` constant | SIMPLE | Yes | Value in contract |

Expanding the template set to cover these patterns increases the zero-cost surface.

## Requirements

### REQ-MP-300: Template Registry Structure

**Status:** planned
**Priority:** P1

A registry of `CodeTemplate` entries SHALL match elements against manifest data and produce deterministic code.

**Template entry:**

```python
@dataclass(frozen=True)
class CodeTemplate:
    name: str
    match_fn: Callable[
        [ForwardElementSpec, ForwardFileSpec, list[InterfaceContract]],
        bool,
    ]
    render_fn: Callable[
        [ForwardElementSpec, ForwardFileSpec, list[InterfaceContract]],
        str,
    ]
```

**Registry behavior:**
- Templates are evaluated in registration order
- First match wins (no ambiguity)
- `match_fn` SHALL be a pure function with no side effects
- `render_fn` SHALL produce syntactically valid Python (`ast.parse()` must pass)
- Both functions receive the same three arguments: element spec, file spec, applicable contracts

**Acceptance criteria:**
- Registry is a module-level list (`TEMPLATES: list[CodeTemplate]`)
- `try_template_match(elem, file_spec, contracts) → Optional[str]` returns rendered code or None
- Templates never raise exceptions — a non-matching template returns False from `match_fn`

---

### REQ-MP-301: Config Constant Template

**Status:** planned
**Priority:** P1

**Match criteria (ALL must hold):**
- `ForwardElementSpec.kind == ElementKind.CONSTANT`
- At least one `InterfaceContract` exists where:
  - `contract.category == ContractCategory.CONFIG_KEY`
  - `contract.constant_value` is not None
  - Contract applies to the element (by name match or applicable_task_ids)

**Render logic:**

```python
def _render_config_constant(elem, contracts):
    contract = _find_config_contract(elem, contracts)
    value = contract.constant_value
    annotation = elem.signature.return_annotation if elem.signature else None

    # Quote strings, pass through numbers/booleans
    if isinstance(value, str):
        rendered_value = repr(value)
    else:
        rendered_value = str(value)

    if annotation:
        return f"{elem.name}: {annotation} = {rendered_value}"
    return f"{elem.name} = {rendered_value}"
```

**Acceptance criteria:**
- `SECRET_KEY` with `constant_value="changeme"` → `SECRET_KEY = 'changeme'`
- `PORT` with `constant_value=8080` → `PORT = 8080`
- `DEBUG` with `constant_value=True` → `DEBUG = True`
- String values are properly escaped (quotes, backslashes)

---

### REQ-MP-302: App Instance Template

**Status:** planned
**Priority:** P1

**Match criteria (ALL must hold):**
- `ForwardElementSpec.kind == ElementKind.CONSTANT`
- `ForwardElementSpec.name` in `{"app", "application", "server", "api"}`
- `ForwardFileSpec.imports` contains a recognized framework import

**Recognized frameworks and their constructors:**

| Import | Constructor |
|--------|------------|
| `from flask import Flask` | `Flask(__name__)` |
| `from fastapi import FastAPI` | `FastAPI()` |
| `from starlette.applications import Starlette` | `Starlette()` |
| `from django.core.wsgi import get_wsgi_application` | `get_wsgi_application()` |

**Render logic:**

```python
def _render_app_instance(elem, file_spec, contracts):
    framework = _detect_framework(file_spec.imports)
    if framework == "flask":
        return f"{elem.name} = Flask(__name__)"
    elif framework == "fastapi":
        return f"{elem.name} = FastAPI()"
    # ... etc.
```

**Acceptance criteria:**
- Correct framework detected from imports (not from element name alone)
- Only fires when a framework import is present — never guesses
- Produces `ast.parse()`-valid output

---

### REQ-MP-303: Type Alias Template

**Status:** planned
**Priority:** P2

**Match criteria (ALL must hold):**
- `ForwardElementSpec.kind == ElementKind.TYPE_ALIAS`
- Either `type_annotation` or `value_repr` provides the alias definition

**Render patterns:**

| Pattern | Output |
|---------|--------|
| Simple alias | `TypeName = BaseType` |
| NewType | `TypeName = NewType("TypeName", BaseType)` |
| Union | `TypeName = Union[TypeA, TypeB]` |

**Acceptance criteria:**
- NewType aliases include the string name matching the variable name
- Imports required by the alias (e.g., `NewType` from `typing`) are already in the manifest's import list
- Output passes `ast.parse()` with `from __future__ import annotations`

---

### REQ-MP-304: Template Priority in Routing

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-500

Template matching SHALL be the FIRST step in element routing, before heuristic complexity classification.

**Routing sequence:**

```
1. try_template_match(elem, file_spec, contracts)
   → match: classify as TRIVIAL, use template output
   → no match: continue to step 2

2. classify_element_heuristic(elem, file_spec, contracts)
   → SIMPLE: route to local model (REQ-MP-201)
   → MODERATE: route to Haiku/Sonnet
   → COMPLEX: route to Sonnet/Opus
```

**Acceptance criteria:**
- Template-matched elements never invoke `generate_with_ollama()` or cloud agents
- Template match decision is recorded in element metadata (`template_name` field)
- The heuristic classifier does not re-evaluate template-matched elements

---

## Implementation Notes

### File Location

`src/startd8/utils/code_templates.py` — new file, ~150 LOC. Dependencies: `forward_manifest.py` (models), `code_manifest.py` (ElementKind, Visibility).

### Extensibility

The template registry is a list — new templates are added by appending to `TEMPLATES`. No subclassing or registration ceremony needed. Templates for project-specific patterns (e.g., gRPC service stubs) can be added without modifying existing templates.

### Testing

Each template needs:
- A positive match test (element that should match)
- A negative match test (similar element that should NOT match)
- An output validation test (`ast.parse()` + content assertion)
- An edge case test (missing fields, empty contracts)
