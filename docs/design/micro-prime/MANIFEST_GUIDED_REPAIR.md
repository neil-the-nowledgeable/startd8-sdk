# Manifest-Guided Repair — Design Document

**Date:** 2026-03-01
**Status:** DRAFT
**Prerequisites:**
- [DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md](../scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md)
- [LOCAL_MODEL_ROUTING_EXPERIMENT.md](../local-model-routing/LOCAL_MODEL_ROUTING_EXPERIMENT.md)
- [OLLAMA_MODEL_TUNING.md](./OLLAMA_MODEL_TUNING.md)

---

## 1. Problem Statement

The local model routing experiment (Round 1) demonstrated that a 7B model can generate correct function bodies — but only 9% of the time. The tuned `startd8-coder` model improves determinism and reduces over-generation, but two structural problems remain:

1. **The model generates too much.** It's asked to produce a complete function definition when the pipeline already has the signature, decorators, class context, and imports from the Forward Manifest. This means 53% of failures are the model mangling structure (indentation, signatures) that was already known to be correct.

2. **Imperfect output is discarded.** When generated code has a fixable defect (wrong indentation, missing import, extra trailing code), it fails `ast.parse()` and the entire element is marked failed. The manifest contains enough structural information to repair many of these defects without an LLM call.

### Current flow

```
ForwardManifest → build prompt (stub + imports + context)
                → local model generates COMPLETE function (signature + body)
                → extract_code_from_response (strip fences)
                → ast.parse() — pass or fail
                → Sonnet verification — pass or fail
```

### Proposed flow

```
ForwardManifest → DeterministicFileAssembler renders skeleton
                → local model generates BODY ONLY (not signature)
                → splice body into skeleton at correct indent
                → manifest-guided repair (imports, trimming, identifiers)
                → ast.parse() — pass, repaired-pass, or fail
                → Sonnet verification — pass or fail
```

The key shift: the model fills a slot in a known-good structure, and the manifest provides a repair specification for imperfect output.

## 2. Three Layers

### Layer 1 — Skeleton-First Prompting (Template/Factory)

Use the `DeterministicFileAssembler` output as a factory that produces the prompt context. Instead of asking the model to generate a complete function, give it the exact insertion point and ask for body lines only.

### Layer 2 — Deterministic File Operations (Zero-LLM Fixes)

Use manifest data and AST operations to fix common defects without any LLM call.

### Layer 3 — Manifest-Guided Post-Generation Repair

Use the Forward Manifest as a structural specification to validate and repair generated code before it reaches Sonnet verification.

---

## 3. Layer 1 — Skeleton-First Prompting

### 3.1 Concept

The `DeterministicFileAssembler` already produces syntactically valid Python skeletons with `raise NotImplementedError` bodies. Today, the experiment prompt asks the model to regenerate all of this structure. This is wasteful and error-prone — the model can mangle signatures, add wrong decorators, or use incorrect class hierarchy.

Instead, give the model the rendered skeleton and ask it to replace only the `raise NotImplementedError` line.

### 3.2 Prompt Transformation

**Current prompt** (from `_build_ollama_prompt`):

```
# Task: Implement the function body below.
# Return ONLY the complete function (with signature and body), no explanation.

# Available imports:
import logging
import json

# Implement this:
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        raise NotImplementedError
```

**Proposed prompt** (body-only):

```
# Context: This function exists in a file with these imports:
import logging
import json
from collections import OrderedDict

# The function signature and class context are fixed — do not change them.
# Replace the placeholder body with a working implementation.
# Return ONLY the body lines, indented with 8 spaces (method inside a class).
# Do not include the def line, class line, or docstring.

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string with ordered fields."""
        raise NotImplementedError  # ← REPLACE THIS LINE
```

**Expected model output:**

```
        data = OrderedDict()
        data['timestamp'] = self.formatTime(record, self.datefmt)
        data['severity'] = record.levelname
        data['name'] = record.name
        data['message'] = record.getMessage()
        return json.dumps(data)
```

### 3.3 Body Splicing

After generation, splice the body into the skeleton:

```python
def splice_body_into_skeleton(
    skeleton_source: str,
    element_fqn: str,
    generated_body: str,
    manifest_element: ForwardElementSpec,
) -> str:
    """Replace 'raise NotImplementedError' with generated body in skeleton."""
    # 1. Parse skeleton to find the target element's body location
    tree = ast.parse(skeleton_source)
    target_node = _find_element_node(tree, element_fqn)

    # 2. Determine the indentation level of the NotImplementedError line
    body_indent = _get_body_indent(skeleton_source, target_node)

    # 3. Normalize generated body to the correct indentation
    normalized = textwrap.dedent(generated_body)
    indented = textwrap.indent(normalized.strip(), body_indent)

    # 4. Replace the raise NotImplementedError line(s) with the body
    return _replace_stub_body(skeleton_source, target_node, indented)
```

### 3.4 Why This Addresses the Failure Modes

| Round 1 Failure Mode | How Skeleton-First Fixes It |
|---------------------|---------------------------|
| Indentation mangling (53%) | Body is re-indented to match skeleton — model's indentation is discarded |
| Signature mutation | Signature comes from skeleton (manifest), not the model |
| Over-generation (class/function) | Model outputs only body lines; stop sequences + splicing discard extras |
| Wrong decorator/base class | Decorators and bases come from skeleton, not the model |

### 3.5 Prompt Builder Changes

```python
def _build_body_only_prompt(
    elem: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    skeleton_source: str,
    contracts: list[InterfaceContract],
) -> str:
    """Build a prompt that asks for BODY ONLY, not the full function."""

    # Extract the rendered element from the skeleton for full context
    element_context = _extract_element_context(skeleton_source, elem)

    sections = [
        "# Context: This function exists in a file with these imports:",
    ]

    # Include imports
    for imp in file_spec.imports:
        if imp.kind == "from":
            sections.append(f"from {imp.module} import {', '.join(imp.names)}")
        else:
            sections.append(f"import {imp.module}")

    sections.append("")
    sections.append("# The function signature and class context are fixed — do not change them.")
    sections.append("# Replace the placeholder body with a working implementation.")

    # Tell the model what indentation to use
    body_indent = "    " * (2 if elem.parent_class else 1)
    sections.append(f"# Return ONLY the body lines, indented with {len(body_indent)} spaces.")
    sections.append("# Do not include the def line, class line, or docstring.")

    # Binding constraints
    for c in contracts:
        prefix = "[BINDING]" if c.confidence != ContractConfidence.TENTATIVE else "[ADVISORY]"
        sections.append(f"# {prefix} {c.binding_text}")

    sections.append("")
    sections.append(element_context)

    return "\n".join(sections)
```

---

## 4. Layer 2 — Deterministic File Operations (Zero-LLM Fixes)

Some elements don't need an LLM at all. The manifest and contracts contain enough information to generate them deterministically.

### 4.1 Elements Solvable Without an LLM

| Pattern | Manifest Signal | Deterministic Output |
|---------|----------------|---------------------|
| Config constants | `InterfaceContract.category == CONFIG_KEY`, `constant_value` set | `SECRET_KEY = "default-secret"` |
| App instances | `InterfaceContract.category == FORMULA`, element name in {app, server, api} | `app = Flask(__name__)` |
| Import re-exports | `ForwardElementSpec.kind == CONSTANT`, `__init__.py` with `__all__` | `from .module import Class` |
| Simple getters | `ForwardElementSpec.kind == PROPERTY`, 0 params, return matches class field | `return self._name` |
| Enum-like constants | `InterfaceContract.category == FORMULA`, `constant_value` is literal | `STATUS_OK = 200` |
| Type aliases | `ForwardElementSpec.kind == TYPE_ALIAS` | `UserId = NewType("UserId", str)` |

### 4.2 Template Registry

A deterministic template registry maps (element pattern) → (code template):

```python
@dataclass(frozen=True)
class CodeTemplate:
    """A deterministic code template that produces output without an LLM."""
    name: str
    match_fn: Callable[[ForwardElementSpec, ForwardFileSpec, list[InterfaceContract]], bool]
    render_fn: Callable[[ForwardElementSpec, ForwardFileSpec, list[InterfaceContract]], str]

TEMPLATES: list[CodeTemplate] = [
    CodeTemplate(
        name="config_constant",
        match_fn=lambda elem, fs, contracts: (
            elem.kind == ElementKind.CONSTANT
            and any(
                c.category == ContractCategory.CONFIG_KEY and c.constant_value
                for c in contracts
            )
        ),
        render_fn=lambda elem, fs, contracts: _render_config_constant(elem, contracts),
    ),
    CodeTemplate(
        name="flask_app_instance",
        match_fn=lambda elem, fs, contracts: (
            elem.kind == ElementKind.CONSTANT
            and elem.name in ("app", "application")
            and any(
                imp.module == "flask" and "Flask" in imp.names
                for imp in fs.imports
                if imp.kind == "from"
            )
        ),
        render_fn=lambda elem, fs, contracts: 'app = Flask(__name__)',
    ),
    # ... more templates
]

def try_template_match(
    elem: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
) -> Optional[str]:
    """Try each template; return generated code or None if no match."""
    for template in TEMPLATES:
        if template.match_fn(elem, file_spec, contracts):
            return template.render_fn(elem, file_spec, contracts)
    return None
```

### 4.3 Routing Priority

Before invoking the local model, check the template registry:

```
ForwardElementSpec
  → Template registry match? → YES → deterministic output (zero cost, instant)
  → Heuristic: SIMPLE?      → YES → local model (zero cloud cost, ~5s)
  → Heuristic: MODERATE?    → YES → cloud model (Haiku/Sonnet)
  → Heuristic: COMPLEX?     → YES → cloud model (Sonnet/Opus)
```

This adds a tier below SIMPLE — call it **TRIVIAL** — that never touches any model.

---

## 5. Layer 3 — Manifest-Guided Post-Generation Repair

When the local model produces imperfect output, the manifest provides enough structural information to attempt deterministic repair before escalating to a cloud model.

### 5.1 Repair Pipeline

```
Local model output
  │
  ├─ Step 1: Fence stripping (existing extract_code_from_response)
  ├─ Step 2: Over-generation trimming (manifest-guided)
  ├─ Step 3: Bare statement wrapping (REQ-MP-407 — wrap body-only output in def line)
  ├─ Step 4: Indentation normalization (existing + skeleton-aware)
  ├─ Step 5: Signature reconciliation (manifest-guided)
  ├─ Step 6: Import completion (manifest-guided)
  ├─ Step 7: AST validation
  │     ├─ PASS → proceed to structural verification (REQ-MP-512)
  │     └─ FAIL → escalate to cloud model
  │
  └─ Metrics: track which repair step recovered the element
```

### 5.2 Step 2 — Over-Generation Trimming

**Problem:** The model generates more code than the target element. Example: asked for `get_secret`, produces `get_secret` + `list_secrets` + a main block.

**Repair using manifest:**

```python
def trim_to_target_element(
    code: str,
    target: ForwardElementSpec,
    file_spec: ForwardFileSpec,
) -> str:
    """Parse generated code and extract only the target element."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code  # Can't parse — pass through to later repair steps

    # Find the target node by name and kind
    for node in ast.iter_child_nodes(tree):
        if _matches_element(node, target):
            # Extract source lines for just this node
            return _extract_node_source(code, node)

    # Target not found — return as-is
    return code

def _matches_element(node: ast.AST, target: ForwardElementSpec) -> bool:
    """Check if an AST node matches a ForwardElementSpec."""
    if target.kind in (ElementKind.FUNCTION, ElementKind.ASYNC_FUNCTION):
        return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target.name
    if target.kind == ElementKind.CLASS:
        return isinstance(node, ast.ClassDef) and node.name == target.name
    if target.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return isinstance(node, (ast.Assign, ast.AnnAssign)) and _assigns_name(node, target.name)
    return False
```

### 5.3 Step 4 — Signature Reconciliation

**Problem:** The model changes the function signature — renames parameters, drops type annotations, changes return type. The manifest has the ground truth.

**Repair:**

```python
def reconcile_signature(
    code: str,
    target: ForwardElementSpec,
) -> str:
    """Replace the generated function signature with the manifest's version."""
    if not target.signature:
        return code

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target.name:
            # Render the canonical signature from the manifest
            canonical_sig = _render_manifest_signature(target)

            # Replace the def line in the source
            lines = code.split("\n")
            def_line_idx = node.lineno - 1
            # Find the end of the def line (may span multiple lines with long signatures)
            def_end = _find_colon_end(lines, def_line_idx)

            indent = " " * node.col_offset
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            new_def = f"{indent}{prefix} {target.name}{canonical_sig}:"

            lines[def_line_idx:def_end + 1] = [new_def]
            return "\n".join(lines)

    return code
```

### 5.4 Step 5 — Import Completion

**Problem:** The model uses `json.dumps()` in the body but doesn't include `import json`. The manifest's `ForwardImportSpec` has the complete import list.

**Repair:**

```python
def complete_imports(
    code: str,
    file_spec: ForwardFileSpec,
) -> str:
    """Add missing imports that the generated code references but doesn't import."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    # Collect all Name nodes referenced in the code
    referenced_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    # Collect names already imported
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)

    # Find manifest imports that provide referenced-but-not-imported names
    missing_imports = []
    for imp in file_spec.imports:
        if imp.kind == "from":
            for name in imp.names:
                if name in referenced_names and name not in imported_names:
                    missing_imports.append(imp)
                    break
        else:
            mod_name = imp.alias or imp.module.split(".")[0]
            if mod_name in referenced_names and mod_name not in imported_names:
                missing_imports.append(imp)

    if not missing_imports:
        return code

    # Prepend missing imports after any existing imports
    import_lines = []
    for imp in missing_imports:
        if imp.kind == "from":
            import_lines.append(f"from {imp.module} import {', '.join(imp.names)}")
        else:
            alias = f" as {imp.alias}" if imp.alias else ""
            import_lines.append(f"import {imp.module}{alias}")

    return "\n".join(import_lines) + "\n" + code
```

### 5.5 Skeleton-Aware Indentation (Enhanced Step 3)

When Layer 1 (skeleton-first prompting) is active, indentation normalization becomes trivial — the skeleton defines the exact indent level, and the body is re-indented to match:

```python
def normalize_body_indent(
    body: str,
    target: ForwardElementSpec,
    skeleton_source: str,
) -> str:
    """Re-indent a generated body to match the skeleton's indentation level."""
    # Determine target indent from the skeleton
    tree = ast.parse(skeleton_source)
    target_node = _find_element_node(tree, target)

    if target_node is None:
        # Fallback: compute from element nesting
        depth = 2 if target.parent_class else 1
        target_indent = "    " * depth
    else:
        # Use the NotImplementedError line's indentation
        target_indent = _get_body_indent(skeleton_source, target_node)

    # Strip all leading whitespace, then re-indent uniformly
    dedented = textwrap.dedent(body).strip()
    return textwrap.indent(dedented, target_indent)
```

This eliminates the fragile multi-strategy approach (`_normalize_indentation` in the experiment script with 5 heuristic strategies) and replaces it with a single deterministic operation anchored to the skeleton.

---

## 6. Combined Flow

```
ForwardManifest
  │
  ├─ DeterministicFileAssembler → skeleton .py files on disk
  │
  ├─ Per element:
  │    │
  │    ├─ TRIVIAL? (template match)
  │    │    └─ Template registry → deterministic code → splice into skeleton
  │    │
  │    ├─ SIMPLE? (heuristic)
  │    │    ├─ Build body-only prompt (Layer 1)
  │    │    ├─ Local model generates body
  │    │    ├─ Repair pipeline (Layer 3):
  │    │    │    ├─ Strip fences
  │    │    │    ├─ Trim over-generation (manifest)
  │    │    │    ├─ Re-indent to skeleton level
  │    │    │    ├─ Reconcile signature (manifest)
  │    │    │    └─ Complete imports (manifest)
  │    │    ├─ Splice into skeleton
  │    │    ├─ ast.parse() validation
  │    │    │    ├─ PASS → Sonnet verification
  │    │    │    └─ FAIL → escalate to cloud model
  │    │    └─ Sonnet verification
  │    │         ├─ PASS → done
  │    │         └─ FAIL → escalate to cloud model
  │    │
  │    ├─ MODERATE / COMPLEX?
  │    │    └─ Cloud model (existing Artisan pipeline)
  │    │
  │    └─ Escalated from SIMPLE failure
  │         └─ Cloud model (with error context from failed attempt)
  │
  └─ Final assembly: skeleton with all bodies filled in
```

### Cost Model

| Tier | Cost per Element | Latency | Expected Coverage |
|------|-----------------|---------|-------------------|
| TRIVIAL (template) | $0.00 | <1ms | 5-10% of elements |
| SIMPLE (local model + repair) | $0.00 cloud | ~5s | 15-25% of elements |
| SIMPLE → escalated | ~$0.005 (Haiku) | ~3s | 5-10% of elements |
| MODERATE (cloud) | ~$0.01-0.03 | ~5s | 30-40% of elements |
| COMPLEX (cloud) | ~$0.05-0.10 | ~10s | 10-20% of elements |

For a typical 32-element microservice seed, the combined TRIVIAL + SIMPLE surface could handle 8-11 elements at zero cloud cost, saving ~$0.15-0.30 per run.

---

## 7. Integration Points

### 7.1 Where Each Layer Hooks In

| Layer | Integration Point | File |
|-------|------------------|------|
| Skeleton rendering | `ScaffoldPhaseHandler.execute()` (after directory creation) | `contractors/context_seed_handlers.py` |
| Template registry | New: `utils/code_templates.py`, called before `generate_with_ollama()` | New file |
| Body-only prompt | Modify `_build_ollama_prompt()` in experiment script; eventually `LLMChunkExecutor._build_prompt()` | `contractors/artisan_phases/development.py` |
| Body splicing | New: function in `utils/file_assembler.py` | Existing file |
| Repair pipeline | New: `utils/manifest_repair.py` | New file |
| Escalation | Existing retry loop in `_execute_chunk_inner()` with `last_error` context injection | `contractors/artisan_phases/development.py` |

### 7.2 Existing Infrastructure Reuse

| Component | Already Exists | Reused For |
|-----------|---------------|------------|
| `DeterministicFileAssembler.render_file()` | Yes (`utils/file_assembler.py`) | Skeleton generation (Layer 1) |
| `extract_code_from_response()` | Yes (`utils/code_extraction.py`) | Fence stripping (Layer 3, Step 1) |
| `STUB_SENTINEL` / `SKELETON_SENTINEL` | Yes | Detecting unfilled stubs |
| `_normalize_indentation()` | Yes (experiment script) | Replaced by skeleton-aware indent (Layer 3, Step 3) |
| `TaskComplexitySignals` | Yes (`development.py`) | Extended with template-match flag |
| Error feedback injection | Yes (`_execute_chunk_inner`) | Escalation context for failed SIMPLE elements |
| `ForwardManifest.contracts_for_task()` | Yes | Constraint lookup for templates and repair |

### 7.3 New Files

| File | Purpose | LOC (est.) |
|------|---------|------------|
| `src/startd8/utils/code_templates.py` | Template registry for TRIVIAL elements | ~150 |
| `src/startd8/utils/manifest_repair.py` | Repair pipeline (trim, reconcile, complete) | ~250 |
| `tests/unit/utils/test_code_templates.py` | Template match and render tests | ~200 |
| `tests/unit/utils/test_manifest_repair.py` | Repair step tests | ~300 |

---

## 8. Experiment Plan

Before full integration, validate each layer independently with the existing experiment script.

### 8.1 Round 2a — Skeleton-First Prompting

Modify `_build_ollama_prompt()` to use body-only format. Run against the same 32 elements. Measure:
- Syntax success rate (expect: >85%, up from ~50-74%)
- Sonnet pass rate (expect: >40%, up from 9-20%)
- Tokens per element (expect: <50, down from 85-555)

### 8.2 Round 2b — Template Registry

Implement 3-5 templates for the online-boutique-demo seed. Identify which elements would be TRIVIAL. Measure:
- Elements matched by templates (expect: 3-5 of 32)
- Correctness of template output (expect: 100% — deterministic)

### 8.3 Round 2c — Repair Pipeline

Run Round 2a's failures through the repair pipeline. Measure:
- Elements recovered by trim (over-generation)
- Elements recovered by signature reconciliation
- Elements recovered by import completion
- Net syntax success rate after repair (expect: >90%)

### 8.4 Round 2d — Combined

Run the full pipeline (templates → body-only prompt → repair → verification). Measure:
- End-to-end usable code rate (target: >50%, up from 9%)
- Cloud cost savings vs all-cloud baseline
- Latency per element

---

## 9. Open Questions

1. **Body extraction ambiguity.** When the model is asked for "body only" and returns code that includes the def line anyway, should the repair pipeline strip it (detecting via AST match against the manifest signature) or reject and retry?

2. **Multi-statement bodies.** Some function bodies are a single expression (`return self._name`), others are multi-statement blocks. Should the prompt format differ for estimated-short vs estimated-long bodies?

3. **Repair metrics granularity.** Should the repair pipeline track which step recovered each element (for tuning the pipeline), or is pass/fail sufficient? The experiment script already tracks `indent_recovered` — extending this to `trim_recovered`, `signature_reconciled`, `imports_completed` would give good signal.

4. **Template versioning.** Templates are framework-specific (Flask app instance, gRPC server setup). Should they be per-seed or global? The online-boutique-demo seed uses Flask, gRPC, and GCP — a different seed might use FastAPI and AWS.

5. **Interaction with skeleton-first and the existing ArtisanChunkExecutor.** The Artisan pipeline generates full files via `LLMChunkExecutor` and splits with `extract_multi_file_code()`. The skeleton-first approach generates per-element bodies and splices them in. These are different assembly strategies. Integration requires either: (a) a new executor mode for local-model elements, or (b) converting the body-splice result into the same format `extract_multi_file_code()` produces.
