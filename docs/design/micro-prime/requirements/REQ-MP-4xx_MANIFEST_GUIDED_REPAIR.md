# Layer 4 — Manifest-Guided Repair (REQ-MP-4xx)

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** Planned
> **New file:** `src/startd8/utils/manifest_repair.py`
> **Design detail:** [MANIFEST_GUIDED_REPAIR.md](../MANIFEST_GUIDED_REPAIR.md)

---

## Overview

The Forward Manifest is a structural specification — it defines what correct code looks like at every level: element names, signatures, parameter types, import lists, class hierarchy. When a local model produces imperfect output, this specification can be used to repair common defects deterministically, without re-invoking any model.

This layer implements a repair pipeline that sits between local model generation and AST validation. Each step uses manifest data as ground truth to fix a specific class of defect. The pipeline is ordered so that each step creates better conditions for the next.

## Core Principle: Non-Destructive Repair

Every repair step is guarded: if the step would make the code worse (turn valid code invalid), its changes are discarded and the original input is passed through. This is formalized in REQ-MP-406.

## Requirements

### REQ-MP-400: Repair Pipeline Structure

**Status:** planned
**Priority:** P0

A `ManifestRepairPipeline` SHALL process local model output through an ordered sequence of deterministic repair steps.

**Pipeline:**

```
Input (raw model output)
  │
  ├─ Step 1: Fence stripping        ← existing extract_code_from_response()
  ├─ Step 2: Over-generation trim   ← REQ-MP-401
  ├─ Step 3: Bare statement wrap    ← REQ-MP-407
  ├─ Step 4: Indentation normalize  ← REQ-MP-402
  ├─ Step 5: Signature reconcile    ← REQ-MP-403
  ├─ Step 6: Import completion      ← REQ-MP-404
  │
  ▼
Output (repaired code)
  │
  ├─ ast.parse() → PASS → proceed to verification
  └─ ast.parse() → FAIL → escalate to cloud model
```

**Interface:**

```python
@dataclass
class RepairResult:
    code: str                       # Repaired code (or original if repair failed)
    steps_applied: list[str]        # Names of steps that modified the code
    ast_valid: bool                 # Whether the final code passes ast.parse()
    metrics: dict[str, Any]         # Per-step metrics (REQ-MP-601)

def repair(
    raw_output: str,
    target: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    skeleton_source: Optional[str] = None,
) -> RepairResult:
    """Run the full repair pipeline on local model output."""
```

**Acceptance criteria:**
- Steps execute in order; each receives the previous step's output
- A step that cannot improve the code passes it through unchanged
- The pipeline never makes code worse (REQ-MP-406)
- `RepairResult` includes which steps were applied and whether the result is valid

---

### REQ-MP-401: Over-Generation Trimming

**Status:** planned
**Priority:** P0

When the model generates more code than the target element, the repair pipeline SHALL parse the output and extract only the target element.

**Algorithm:**

```python
def _trim_to_target(code: str, target: ForwardElementSpec) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code  # Can't parse — pass through

    for node in ast.iter_child_nodes(tree):
        if _matches_target(node, target):
            return ast.get_source_segment(code, node)

    return code  # Target not found — pass through
```

**Element matching rules:**

| Target Kind | AST Node Type | Match Condition |
|-------------|--------------|-----------------|
| FUNCTION / ASYNC_FUNCTION | FunctionDef / AsyncFunctionDef | `node.name == target.name` |
| METHOD / ASYNC_METHOD | FunctionDef / AsyncFunctionDef (in ClassDef) | `node.name == target.name` and parent class matches `target.parent_class` |
| CLASS | ClassDef | `node.name == target.name` |
| CONSTANT / VARIABLE | Assign / AnnAssign | Target name in assignment targets |

**What gets trimmed:**
- Secondary function/class definitions after the target
- `if __name__ == "__main__"` blocks
- Import statements that the model re-emitted (imports come from the skeleton)
- Explanatory comments before/after the code

**Acceptance criteria:**
- `get_secret` + `list_secrets` + `main()` → trimmed to just `get_secret`
- A class wrapping a method → extracts just the method (if target is a method)
- Trimming preserves the target element's exact source text
- Unparseable input passes through without modification

---

### REQ-MP-402: Skeleton-Aware Indentation

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-200 (skeleton-first prompting)

When a skeleton is available, indentation normalization SHALL use the skeleton's body indent level as the canonical target, replacing the heuristic multi-strategy approach.

**Algorithm:**

```python
def _normalize_indent(
    body: str,
    target: ForwardElementSpec,
    skeleton_source: Optional[str],
) -> str:
    if skeleton_source:
        # Deterministic: use skeleton's indent level
        target_indent = _get_skeleton_body_indent(skeleton_source, target)
    else:
        # Fallback: compute from nesting depth
        depth = 2 if target.parent_class else 1
        target_indent = "    " * depth

    dedented = textwrap.dedent(body).strip()
    return textwrap.indent(dedented, target_indent)
```

**Why this replaces `_normalize_indentation()`:**

The experiment script's `_normalize_indentation()` uses 5 heuristic strategies (dedent, strip-first-line, strip-last-line, strip-both, tab-to-spaces). Each is a guess. The skeleton provides a ground truth indent level, collapsing all 5 strategies into one deterministic operation.

**Acceptance criteria:**
- Body indented at 12 spaces → normalized to 8 spaces (method in class)
- Body indented at 0 spaces → normalized to 4 spaces (top-level function)
- Mixed tabs and spaces → tabs expanded to 4 spaces, then normalized
- Without a skeleton, the fallback produces correct indent based on `parent_class`

---

### REQ-MP-403: Signature Reconciliation

**Status:** planned
**Priority:** P1

When the model's output contains a function signature that differs from the manifest's `ForwardElementSpec.signature`, the repair pipeline SHALL replace it with the manifest's canonical version.

**Differences detected:**

| Difference | Example | Action |
|-----------|---------|--------|
| Parameter renamed | `rec` instead of `record` | Replace with manifest param name |
| Type annotation dropped | `def format(self, record)` | Add `: logging.LogRecord` from manifest |
| Return annotation dropped | `def format(...)` (no `-> str`) | Add `-> str` from manifest |
| Extra parameters added | `def format(self, record, verbose=False)` | Remove non-manifest params |
| Parameter order changed | `def format(record, self)` | Reorder to match manifest |

**Algorithm:**

```python
def _reconcile_signature(code: str, target: ForwardElementSpec) -> str:
    if not target.signature:
        return code

    tree = ast.parse(code)
    func_node = _find_function_node(tree, target.name)
    if not func_node:
        return code

    # Render canonical signature from manifest
    canonical = _render_signature_from_manifest(target)

    # Replace the def line in source
    lines = code.split("\n")
    def_line = func_node.lineno - 1
    indent = " " * func_node.col_offset
    prefix = "async def" if isinstance(func_node, ast.AsyncFunctionDef) else "def"
    lines[def_line] = f"{indent}{prefix} {target.name}{canonical}:"

    return "\n".join(lines)
```

**The `_render_signature_from_manifest()` function SHALL use the same rendering logic as `DeterministicFileAssembler._render_signature()`** to ensure consistency between skeletons and repaired code.

**Acceptance criteria:**
- `def format(self, rec)` → `def format(self, record: logging.LogRecord) -> str`
- Reconciliation fires only when signatures differ (no-op for matching signatures)
- Multi-line signatures (long parameter lists) are handled correctly
- The function body is preserved unchanged — only the `def` line is modified

---

### REQ-MP-404: Import Completion

**Status:** planned
**Priority:** P1

When the generated body references identifiers that are provided by `ForwardFileSpec.imports` but not imported in the generated code, the repair pipeline SHALL add the missing imports.

**Algorithm:**

```python
def _complete_imports(
    code: str,
    file_spec: ForwardFileSpec,
) -> str:
    tree = ast.parse(code)

    # Collect referenced names (ast.Name nodes)
    referenced = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}

    # Collect already-imported names
    imported = _collect_imported_names(tree)

    # Find manifest imports that provide referenced-but-missing names
    missing = []
    for imp in file_spec.imports:
        if imp.kind == "from":
            needed = [n for n in imp.names if n in referenced and n not in imported]
            if needed:
                missing.append((imp.module, needed))
        else:
            mod = imp.alias or imp.module.split(".")[0]
            if mod in referenced and mod not in imported:
                missing.append((imp.module, []))

    if not missing:
        return code

    # Prepend missing imports
    import_lines = []
    for module, names in missing:
        if names:
            import_lines.append(f"from {module} import {', '.join(names)}")
        else:
            import_lines.append(f"import {module}")

    return "\n".join(import_lines) + "\n\n" + code
```

**Scope constraint:**

This step ONLY adds imports that the manifest already specifies. It does NOT:
- Invent new imports not in `ForwardFileSpec.imports`
- Add imports for stdlib modules not listed in the manifest
- Remove or modify existing imports in the code

This constraint prevents the repair step from introducing its own errors.

**Acceptance criteria:**
- Body using `json.dumps()` without `import json` → import added (when `json` is in manifest)
- Body using `OrderedDict` without `from collections import OrderedDict` → added
- Imports already present in the code are not duplicated
- Imports not in the manifest are never added
- `from __future__ import annotations` is never added by this step (handled by skeleton)

---

### REQ-MP-405: AST Validation Gate

**Status:** planned
**Priority:** P0

After all repair steps, the result SHALL be validated via `ast.parse()`.

**Decision table:**

| Repair Result | ast.parse() | Action |
|--------------|-------------|--------|
| Code modified by repair | Pass | Proceed to Sonnet verification |
| Code modified by repair | Fail | Escalate to cloud with repair attempt context |
| Code unmodified (no repair needed) | Pass | Proceed to Sonnet verification |
| Code unmodified (no repair needed) | Fail | Escalate to cloud with raw output context |

**Escalation context (injected into cloud model prompt):**

```
## Prior Local Model Attempt

The local model generated the following code, which could not be repaired:

```python
{raw model output}
```

Repair steps attempted: {steps_applied}
Final error: {SyntaxError message}

Please generate a correct implementation.
```

**Acceptance criteria:**
- Syntax-valid repaired code proceeds without re-generation
- Syntax-invalid code includes the error message and repair attempt in escalation context
- The escalation context uses the existing `last_error` injection pattern from `_execute_chunk_inner()`

---

### REQ-MP-406: Non-Destructive Guarantee

**Status:** planned
**Priority:** P0

**Invariant:** No repair step SHALL make syntactically valid code syntactically invalid.

**Implementation pattern:**

```python
def _safe_repair_step(code: str, step_fn, *args) -> tuple[str, bool]:
    """Apply a repair step with rollback on failure."""
    was_valid = _is_valid(code)
    repaired = step_fn(code, *args)

    if repaired == code:
        return code, False  # No change

    if was_valid and not _is_valid(repaired):
        # Step made valid code invalid — rollback
        return code, False

    return repaired, True  # Step applied successfully
```

Every step in the pipeline SHALL be wrapped in this guard.

**Acceptance criteria:**
- If code passes `ast.parse()` before a repair step, it still passes after
- If a repair step introduces a syntax error, the step's changes are discarded
- The guard adds negligible overhead (one extra `ast.parse()` per step, <1ms each)

---

### REQ-MP-407: Bare Statement Wrapping

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-401 (over-generation trimming), REQ-MP-403 (signature reconciliation)
**Strengthens:** REQ-MP-204 (graceful degradation on body-included output)
**Empirical basis:** 3 of 14 verification failures in Round 2 (`JSONFormatter.format` ×2, `WebsiteUser.checkout`)

When the model outputs bare statements that are not wrapped in a function definition (i.e., the code is semantically the function body but the `def` line is missing), the repair pipeline SHALL detect and wrap them.

**Failure pattern observed:**

The model was asked to implement `JSONFormatter.format(self, record) -> str` and returned:

```python
log_entry = OrderedDict()
log_entry["timestamp"] = self.formatTime(record)
log_entry["level"] = record.levelname
return json.dumps(log_entry)
```

This is valid Python (parses via `ast.parse()`) but is bare statements, not a method definition. Sonnet verification correctly rejects it as "bare statements not wrapped in a function definition."

**Detection algorithm:**

```python
def _is_bare_statements(code: str, target: ForwardElementSpec) -> bool:
    """Detect if code is the body of the target without the def wrapper."""
    if target.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return False  # Constants/variables are bare by design

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    # If the target is a function/method, the output should contain
    # a FunctionDef. If it doesn't, it's bare statements.
    has_funcdef = any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        for n in ast.iter_child_nodes(tree)
    )
    if has_funcdef:
        return False  # Model included the def line — not bare

    # Heuristic: non-trivial code without a function/class definition
    # is likely the body of the target function
    stmts = [n for n in ast.iter_child_nodes(tree)
             if not isinstance(n, (ast.Import, ast.ImportFrom))]
    return len(stmts) > 0
```

**Wrapping algorithm:**

```python
def _wrap_bare_statements(
    code: str,
    target: ForwardElementSpec,
) -> str:
    """Wrap bare statements in the target function's def line."""
    # Render the canonical signature from the manifest
    sig = _render_signature_from_manifest(target)  # Shared with REQ-MP-403

    prefix = "async def" if target.kind in (
        ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD
    ) else "def"

    # Indent the bare statements as the function body
    body = textwrap.indent(textwrap.dedent(code).strip(), "    ")

    # Optionally add docstring if available
    docstring = ""
    if target.docstring_hint:
        docstring = f'    """{target.docstring_hint}"""\n'

    return f"{prefix} {target.name}{sig}:\n{docstring}{body}\n"
```

**Pipeline position:** Between over-generation trimming (REQ-MP-401) and indentation normalization (REQ-MP-402):

```
Step 1: Fence stripping        ← existing
Step 2: Over-generation trim   ← REQ-MP-401
Step 3: Bare statement wrap    ← REQ-MP-407 (NEW)
Step 4: Indentation normalize  ← REQ-MP-402
Step 5: Signature reconcile    ← REQ-MP-403
Step 6: Import completion      ← REQ-MP-404
```

**Rationale for ordering:**
- After over-generation trimming: if the output has both the target function AND bare statements, trimming extracts the function and this step is a no-op
- Before indentation normalization: the wrapping step produces correctly-indented code, but the normalization step ensures consistency with the skeleton

**Interaction with other requirements:**
- REQ-MP-204 handles the inverse case: model returns a full `def` line when asked for body-only. REQ-MP-407 handles the model returning body-only when asked for a full function. Together they cover both directions.
- REQ-MP-403 (signature reconciliation) shares `_render_signature_from_manifest()` — the wrapping step uses the canonical manifest signature, ensuring type annotations are always correct.
- REQ-MP-406 (non-destructive guarantee) applies: if the wrapping produces invalid code, the step is rolled back.

**Round 2 impact:** Would have recovered 3 of 14 verification failures (21%), raising the verified rate from 42% to potentially 54% (13/24).

**Acceptance criteria:**
- Bare statements detected when output has no `FunctionDef` node but the target is a function/method
- Wrapping uses the manifest's canonical signature (params, types, return annotation)
- Constants/variables are never wrapped (they are bare by design)
- Wrapped code passes `ast.parse()`
- If wrapping fails, the step is rolled back (REQ-MP-406)
- Detection does not fire on correctly-formed function definitions

---

## Implementation Notes

### File Location

`src/startd8/utils/manifest_repair.py` — new file, ~250 LOC. Dependencies: `ast`, `textwrap`, `forward_manifest.py`, `code_manifest.py`.

### Pipeline vs Individual Functions

The module exposes both:
- `repair()` — full pipeline (for typical use)
- Individual step functions (`trim_to_target()`, `normalize_indent()`, etc.) — for testing and selective application

### Interaction with Skeleton-First (Layer 2)

When skeleton-first prompting is active:
- The model generates body-only text (no `def` line)
- Signature reconciliation (REQ-MP-403) rarely fires because there's no signature to reconcile
- Indentation normalization (REQ-MP-402) uses the skeleton's indent level
- Over-generation trimming (REQ-MP-401) handles cases where the model ignores the body-only instruction

When skeleton-first is NOT active (standalone repair):
- All steps are relevant
- Indentation normalization uses the fallback depth computation
- Signature reconciliation is the primary defense against signature mutation
