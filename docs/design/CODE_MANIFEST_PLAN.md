# Code Manifest: Implementation Plan

**Status:** Draft
**Date:** 2026-02-24
**Author:** Neil Yashinsky + agent:claude-code
**Requirements:** [CODE_MANIFEST_REQUIREMENTS.md](CODE_MANIFEST_REQUIREMENTS.md)

---

## 1. Design Decisions

| # | Decision | Resolution | Rationale |
|---|----------|-----------|-----------|
| D-1 | Single file vs package | Single file `src/startd8/utils/code_manifest.py` + `manifest_cache.py` | Follows existing `utils/` pattern (`code_extraction.py`, `file_operations.py`). Two files keeps core generation separate from caching/batch concerns. |
| D-2 | Dataclass vs Pydantic | Pydantic `BaseModel` with `ConfigDict(frozen=True)` | SDK convention (see `context_schema.py`, `models.py`). Free validation, JSON serialization, and schema generation. |
| D-3 | Cache location | `.startd8/manifests/{digest}.json` | Follows `.startd8/` storage convention. Digest-keyed files enable automatic deduplication across identical source content. |
| D-4 | Incremental vs full regen | Full regen per-file, short-circuit via content digest | AST parsing is < 100ms per file; digest comparison avoids unnecessary regen. Incremental adds complexity with negligible performance gain at this scale. |
| D-5 | Nesting depth | Recursive via `children: list[Element]` | Two-level AST walker initially (module → class → method). Recursive design allows extension to deeper nesting (nested classes, nested functions) without schema change. |
| D-6 | FQN computation | Derive from `file_path` relative to `project_root` + `src/` prefix stripping | Mirrors Python import resolution. `src/startd8/utils/code_manifest.py` → `startd8.utils.code_manifest`. |
| D-7 | Serialization | `model_dump()` for JSON; `to_yaml()` convenience method via PyYAML | JSON is the primary machine format. YAML for human review. Both round-trip through Pydantic validation. |
| D-8 | Logging | `get_logger(__name__)` from `startd8.logging_config` | Required for OTel log bridge / Loki visibility. See CLAUDE.md "Must Do". |
| D-9 | File writes | `atomic_write()` from `startd8.utils.file_operations` | Prevents partial writes on crash. Existing pattern. |
| D-10 | Stdlib detection | Reuse `STDLIB_FALLBACK` set from `preflight_rules/_helpers.py` | ~120 module names already curated. Import rather than duplicate. |

---

## 2. Files to Create / Modify

### 2.1 New Files

| File | Purpose | Est. Lines |
|------|---------|-----------|
| `src/startd8/utils/code_manifest.py` | Core manifest generator: AST walking, model definitions, FQN computation, element extraction | ~550 |
| `src/startd8/utils/manifest_cache.py` | Batch generation, digest-based caching, staleness checking | ~180 |
| `tests/unit/test_code_manifest.py` | Core generator tests: element extraction, FQN, spans, signatures, imports, edge cases | ~450 |
| `tests/unit/test_manifest_cache.py` | Cache tests: digest hit/miss, staleness detection, batch scanning, skip patterns | ~150 |

### 2.2 Modified Files

| File | Change |
|------|--------|
| `src/startd8/utils/__init__.py` | Add exports: `generate_file_manifest`, `lookup_element`, `generate_project_manifests`, `check_manifests_fresh` |
| `src/startd8/cli.py` | Add `manifest` sub-command group: `generate`, `check`, `show` |

---

## 3. Pydantic Models

All models use `ConfigDict(frozen=True)` for immutability. Defined in `code_manifest.py`.

### 3.1 Enums

```python
class ElementKind(str, Enum):
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    METHOD = "method"
    ASYNC_METHOD = "async_method"
    PROPERTY = "property"
    CONSTANT = "constant"
    VARIABLE = "variable"
    TYPE_ALIAS = "type_alias"

class Visibility(str, Enum):
    PUBLIC = "public"
    PROTECTED = "protected"   # single underscore
    PRIVATE = "private"       # double underscore

class ParamKind(str, Enum):
    POSITIONAL = "positional"
    KEYWORD = "keyword"
    VAR_POSITIONAL = "var_positional"     # *args
    VAR_KEYWORD = "var_keyword"           # **kwargs
    POSITIONAL_ONLY = "positional_only"   # before /
    KEYWORD_ONLY = "keyword_only"         # after *
```

### 3.2 Value Objects

```python
class Span(BaseModel):
    """Source location of a code element."""
    model_config = ConfigDict(frozen=True)

    start_line: int
    start_col: int
    end_line: int
    end_col: int

class Param(BaseModel):
    """A function/method parameter."""
    model_config = ConfigDict(frozen=True)

    name: str
    annotation: str | None = None
    default: str | None = None          # ast.unparse() of default value
    kind: ParamKind = ParamKind.POSITIONAL

class Signature(BaseModel):
    """Callable signature."""
    model_config = ConfigDict(frozen=True)

    params: list[Param]
    return_annotation: str | None = None
```

### 3.3 Core Models

```python
class Element(BaseModel):
    """A structural code element (class, function, variable, etc.)."""
    model_config = ConfigDict(frozen=True)

    kind: ElementKind
    name: str
    fqn: str
    span: Span
    docstring: str | None = None
    decorators: list[str] = []
    children: list["Element"] = []

    # Callable fields (function/method)
    signature: Signature | None = None
    is_static: bool = False
    is_classmethod: bool = False
    is_abstract: bool = False
    visibility: Visibility = Visibility.PUBLIC

    # Class fields
    bases: list[str] = []
    metaclass: str | None = None
    is_dataclass: bool = False
    is_pydantic: bool = False
    class_variables: list["Element"] = []

    # Assignment fields (constant/variable)
    type_annotation: str | None = None
    value_repr: str | None = None
    is_type_alias: bool = False

class ImportEntry(BaseModel):
    """An import statement."""
    model_config = ConfigDict(frozen=True)

    kind: Literal["import", "from"]
    module: str
    names: list[str] = []
    alias: str | None = None
    span: Span
    is_conditional: bool = False

class Dependencies(BaseModel):
    """Classified dependency summary."""
    model_config = ConfigDict(frozen=True)

    internal: list[str] = []     # Intra-project
    external: list[str] = []     # Third-party
    stdlib: list[str] = []       # Standard library
    conditional: list[str] = []  # Optional / guarded

class FileManifest(BaseModel):
    """Complete manifest for a single Python file."""
    model_config = ConfigDict(frozen=True)

    file: str                      # Relative path from project root
    module: str                    # Dot-separated module path
    digest: str                    # sha256:{hex}
    python_version: str            # Minimum Python version (e.g., "3.9")
    elements: list[Element]
    imports: list[ImportEntry]
    dependencies: Dependencies
    generated_at: str              # ISO 8601 timestamp
```

### 3.4 Model Decisions

- **Flat `Element` model** with optional fields (vs. separate `ClassElement`, `FunctionElement`, etc.): Simpler serialization, easier traversal, uniform `children` nesting. The `kind` field discriminates behavior. This mirrors the AST's own design where node type determines which fields are populated.
- **`value_repr` truncation**: Capped at 200 characters to keep manifests readable. Long values (multiline strings, complex data structures) get `"..."` suffix.
- **`is_conditional` on imports**: Detected by checking if the `Import`/`ImportFrom` node's parent is an `If` node testing `TYPE_CHECKING` or a `Try/ExceptHandler` catching `ImportError`/`ModuleNotFoundError`.

---

## 4. Public API

### 4.1 Core Generation (`code_manifest.py`)

```python
def generate_file_manifest(
    file_path: Path | str,
    project_root: Path | str,
    source: str | None = None,
) -> FileManifest:
    """
    Generate a manifest for a single Python file.

    Args:
        file_path: Absolute or relative path to the Python file.
        project_root: Project root directory (for FQN computation).
        source: Optional pre-read source code. If None, reads from file_path.

    Returns:
        FileManifest with all structural elements, imports, and dependencies.

    Raises:
        SyntaxError: If the file cannot be parsed.
        FileNotFoundError: If file_path does not exist and source is None.
    """

def lookup_element(manifest: FileManifest, fqn: str) -> Element | None:
    """
    Find an element in a manifest by fully-qualified name.

    Searches top-level elements and their children recursively.
    Returns None if not found.
    """
```

### 4.2 Batch / Caching (`manifest_cache.py`)

```python
def generate_project_manifests(
    project_root: Path | str,
    source_root: Path | str | None = None,
    cache_dir: Path | str | None = None,
) -> dict[str, FileManifest]:
    """
    Generate manifests for all Python files in a project.

    Args:
        project_root: Project root directory.
        source_root: Source directory to scan (default: project_root / "src").
        cache_dir: Cache directory (default: project_root / ".startd8" / "manifests").

    Returns:
        Dict mapping relative file paths to FileManifest instances.
        Uses cached manifests when source digest matches.

    Skips: __pycache__, .venv, .git, .egg-info, node_modules
    """

def check_manifests_fresh(
    project_root: Path | str,
    source_root: Path | str | None = None,
    cache_dir: Path | str | None = None,
) -> tuple[bool, list[str]]:
    """
    Check if cached manifests are up-to-date.

    Returns:
        (all_fresh, stale_files) — True if all manifests are current,
        plus list of files that need regeneration.
    """
```

### 4.3 CLI Commands

```
startd8 manifest generate [PATH]    # Generate manifests (default: src/)
    --output-dir DIR                 # Output directory (default: .startd8/manifests/)
    --format json|yaml               # Output format (default: json)
    --check                          # Exit non-zero if any manifests are stale
    --verbose                        # Print per-file status

startd8 manifest show FILE           # Pretty-print manifest for one file
    --fqn NAME                       # Show specific element by FQN
    --format json|yaml|tree          # Output format (default: tree)

startd8 manifest check               # Staleness check only (no regen)
```

---

## 5. AST Walking Strategy

### 5.1 Visitor Architecture

Use a single-pass `ast.NodeVisitor` subclass (`_ManifestVisitor`) that:

1. Maintains a **scope stack** (`list[str]`) for FQN construction
2. Visits `ClassDef`, `FunctionDef`, `AsyncFunctionDef`, `Assign`, `AnnAssign`, `Import`, `ImportFrom`
3. Builds `Element` objects in-order with source spans from AST node attributes
4. Handles nesting by pushing/popping scope for class and function bodies
5. Tracks parent nodes to detect conditional imports (`if TYPE_CHECKING`, `try/except ImportError`)

### 5.2 Element Extraction Rules

| AST Node | ElementKind | Notes |
|----------|-------------|-------|
| `ClassDef` | `CLASS` | Extract bases, metaclass, decorators, nested body |
| `FunctionDef` (module-level) | `FUNCTION` | Extract signature, decorators |
| `AsyncFunctionDef` (module-level) | `ASYNC_FUNCTION` | Same as above |
| `FunctionDef` (class body) | `METHOD` or `PROPERTY` | Check `@property`, `@staticmethod`, `@classmethod`, `@abstractmethod` |
| `AsyncFunctionDef` (class body) | `ASYNC_METHOD` | Same decorator checks |
| `Assign` (module-level, UPPER_CASE) | `CONSTANT` | Heuristic: all-caps name |
| `Assign` (module-level, other) | `VARIABLE` | |
| `AnnAssign` with `TypeAlias` | `TYPE_ALIAS` | Detect `x: TypeAlias = ...` |
| `AnnAssign` (other) | `VARIABLE` | |
| `Assign` (class body) | Class variable → `class_variables` | Not top-level elements |

### 5.3 Signature Extraction

```python
def _extract_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Signature:
    """Extract parameter list and return annotation from a function AST node."""
    params = []
    args = node.args

    # positional-only (before /)
    for arg in args.posonlyargs:
        params.append(Param(name=arg.arg, annotation=_unparse(arg.annotation),
                           kind=ParamKind.POSITIONAL_ONLY))

    # regular positional/keyword
    for i, arg in enumerate(args.args):
        default_offset = len(args.args) - len(args.defaults)
        default = args.defaults[i - default_offset] if i >= default_offset else None
        params.append(Param(name=arg.arg, annotation=_unparse(arg.annotation),
                           default=_unparse(default), kind=ParamKind.POSITIONAL))

    # *args
    if args.vararg:
        params.append(Param(name=args.vararg.arg, annotation=_unparse(args.vararg.annotation),
                           kind=ParamKind.VAR_POSITIONAL))

    # keyword-only (after *)
    for i, arg in enumerate(args.kwonlyargs):
        default = args.kw_defaults[i]
        params.append(Param(name=arg.arg, annotation=_unparse(arg.annotation),
                           default=_unparse(default), kind=ParamKind.KEYWORD_ONLY))

    # **kwargs
    if args.kwarg:
        params.append(Param(name=args.kwarg.arg, annotation=_unparse(args.kwarg.annotation),
                           kind=ParamKind.VAR_KEYWORD))

    return Signature(
        params=params,
        return_annotation=_unparse(node.returns),
    )
```

### 5.4 Dependency Classification

```python
def _classify_imports(
    imports: list[ImportEntry],
    project_module: str,    # e.g., "startd8"
    stdlib_set: set[str],   # STDLIB_FALLBACK from _helpers.py
) -> Dependencies:
    """Classify imports into internal, external, stdlib, conditional."""
    internal, external, stdlib, conditional = [], [], [], []

    for imp in imports:
        root = imp.module.split(".")[0]
        if imp.is_conditional:
            conditional.append(imp.module)
        elif root == project_module or imp.module.startswith(project_module + "."):
            internal.append(imp.module)
        elif root in stdlib_set:
            stdlib.append(imp.module)
        else:
            external.append(imp.module)

    return Dependencies(
        internal=sorted(set(internal)),
        external=sorted(set(external)),
        stdlib=sorted(set(stdlib)),
        conditional=sorted(set(conditional)),
    )
```

### 5.5 FQN Computation

```python
def _compute_module_path(file_path: Path, project_root: Path) -> str:
    """
    Compute Python module path from file path.

    Examples:
        src/startd8/utils/code_manifest.py → startd8.utils.code_manifest
        src/startd8/__init__.py → startd8
        tests/unit/test_code_manifest.py → tests.unit.test_code_manifest
    """
    relative = file_path.resolve().relative_to(project_root.resolve())

    # Strip 'src/' prefix if present (standard Python src-layout)
    parts = relative.with_suffix("").parts
    if parts[0] == "src":
        parts = parts[1:]

    # Strip __init__ (package init → package module)
    if parts[-1] == "__init__":
        parts = parts[:-1]

    return ".".join(parts)
```

### 5.6 Digest Computation

```python
def _compute_digest(source: str) -> str:
    """Compute content hash for staleness detection."""
    return "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
```

---

## 6. Caching Strategy

### 6.1 Cache Layout

```
.startd8/
└── manifests/
    ├── sha256_a1b2c3...json      # Manifest keyed by source digest
    ├── sha256_d4e5f6...json
    └── _index.json                # Maps file paths → digest for batch freshness checks
```

### 6.2 Cache Workflow

```
generate_project_manifests(project_root):
    for each .py file:
        digest = sha256(source)
        if cached manifest with matching digest exists:
            load from cache → skip
        else:
            generate_file_manifest(file) → write to cache
    return all manifests
```

### 6.3 Staleness Detection

`check_manifests_fresh()` reads `_index.json`, computes current digests, and compares. Returns `(True, [])` if all match, `(False, stale_files)` otherwise.

### 6.4 Cache Invalidation

- Cache entries are content-addressed (digest-keyed), so they never go stale — new content produces a new key.
- Old cache entries accumulate. A `--gc` flag (future) can prune entries not in the current index.

---

## 7. Implementation Phases

### Phase 1: Core Generator + Models (P0)

**Scope:** Single-file manifest generation with all structural elements.

**Deliverables:**
- `src/startd8/utils/code_manifest.py` with:
  - All Pydantic models (Section 3)
  - `_ManifestVisitor` AST walker
  - `generate_file_manifest()` public function
  - `lookup_element()` public function
  - `_compute_module_path()`, `_extract_signature()`, `_classify_imports()`
  - `_unparse()` helper wrapping `ast.unparse()` with None-safety
- `tests/unit/test_code_manifest.py` with:
  - Model construction and validation
  - Element extraction for each `ElementKind`
  - FQN computation (various path layouts)
  - Span accuracy (line/col positions)
  - Signature extraction (all `ParamKind` variants)
  - Import classification (internal, external, stdlib, conditional)
  - Docstring extraction
  - Decorator detection
  - Nested elements (class methods, nested classes)
  - Edge cases: empty files, syntax errors, encoding

**Acceptance criteria:**
- `generate_file_manifest()` produces correct output for a representative set of SDK files
- All `ElementKind` values exercised in tests
- Determinism: same source → byte-identical JSON output
- Performance: < 100ms per file on representative SDK modules

### Phase 2: Batch Generation, Caching, CLI (P0)

**Scope:** Project-wide scanning, digest caching, CLI commands.

**Deliverables:**
- `src/startd8/utils/manifest_cache.py` with:
  - `generate_project_manifests()`
  - `check_manifests_fresh()`
  - Skip patterns (`__pycache__`, `.venv`, `.git`, etc.)
  - Cache read/write using `atomic_write()` from `file_operations.py`
- `tests/unit/test_manifest_cache.py` with:
  - Cache hit/miss scenarios
  - Staleness detection
  - Skip pattern filtering
  - Index round-trip
- CLI additions in `src/startd8/cli.py`:
  - `manifest_app = typer.Typer(name="manifest", ...)`
  - `generate`, `check`, `show` commands
- `src/startd8/utils/__init__.py` updated with new exports

**Acceptance criteria:**
- Full `src/startd8/` scan completes in < 10s
- Cache prevents redundant regeneration
- `--check` mode exits non-zero on stale manifests
- `manifest show` renders readable tree output

### Phase 3: Symbol Table Augmentation (P1)

**Scope:** `symtable` integration for scope and binding analysis.

**Deliverables:**
- Extend `Element` model with optional scope fields:
  - `scope: Literal["local", "global", "nonlocal", "free", "imported"] | None`
  - `is_referenced: bool | None`
  - `is_assigned: bool | None`
- `_augment_with_symtable()` function that enriches a `FileManifest` post-generation
- Tests for scope classification and closure detection

**Acceptance criteria:**
- Scope information added without changing existing Phase 1/2 behavior
- Closure variables correctly identified
- No performance regression (symtable adds < 10ms per file)

### Phase 4: Pipeline Integration (P1)

**Scope:** Connect manifests to plan ingestion, artisan IMPLEMENT, preflight validators, capability index.

**Deliverables:**
- Plan ingestion: load manifests for files referenced in `ParsedFeature`
- Artisan IMPLEMENT: include manifest excerpt in LLM prompts for targeted element modification
- Preflight: share manifest across validators (avoid per-check `ast.parse()`)
- Capability index: validate declared capabilities against source manifests

**Acceptance criteria:**
- Plan ingestion enriches features with manifest-derived structural context
- IMPLEMENT prompts include specific element FQNs and spans
- Preflight validators consume shared manifest (measured reduction in `ast.parse()` calls)

### Phase 5: Runtime Introspection (P2)

**Scope:** Opt-in `inspect`-based augmentation for resolved types and MRO.

**Deliverables:**
- `introspect` generation mode
- Resolved type annotations (forward refs)
- Class MRO chain
- `__all__` resolution for public API surface
- Side-effect isolation (subprocess or `importlib` sandboxing)

### Phase 6: Call Graph + Bytecode (P3)

**Scope:** `dis`-based intra-function call graph extraction.

**Deliverables:**
- `full` generation mode
- Call graph edges per function
- Cross-file dependency graph construction
- Blast radius computation

---

## 8. Reusable Existing Code

| Asset | Location | Reuse Method |
|-------|----------|-------------|
| `STDLIB_FALLBACK` set | `src/startd8/workflows/builtin/preflight_rules/_helpers.py` | Direct import for stdlib detection in `_classify_imports()` |
| AST try-except pattern | `src/startd8/workflows/builtin/preflight_rules/rules_validators.py` | Pattern reference for robust AST walking (graceful handling of malformed nodes) |
| `get_logger()` | `src/startd8/logging_config` | Direct import for all logging |
| `atomic_write()` / `atomic_write_json()` | `src/startd8/utils/file_operations` | Direct import for cache file writes |
| `infer_code_language()` | `src/startd8/truncation_detection` | Potential reuse for language detection in future multi-language support |
| `extract_top_level_imports()` | `src/startd8/workflows/builtin/preflight_rules/_helpers.py` | Pattern reference for import extraction (our implementation is more detailed) |

---

## 9. Edge Cases and Error Handling

### 9.1 Parse Failures

- **SyntaxError**: `generate_file_manifest()` raises `SyntaxError` for unparseable files. Callers (batch generation, CLI) catch and report, continuing with remaining files.
- **Encoding**: Read files as UTF-8 with `errors="replace"`. Log a warning for replacement characters.

### 9.2 AST Node Coverage

- **Walrus operator** (`:=`): Treated as assignment within expression scope. Not extracted as top-level element.
- **Match statements** (Python 3.10+): `match`/`case` bodies visited for nested definitions.
- **`type` statement** (Python 3.12+): Extracted as `TYPE_ALIAS` element.
- **Starred assignments** (`a, *b = ...`): Only the first target extracted as a variable.
- **Augmented assignments** (`x += 1`): Not extracted (modification, not definition).
- **`__all__` lists**: Extracted as a `VARIABLE` element. Value parsed to `list[str]` if it's a literal list/tuple.

### 9.3 Large Files

- No hard limit on file size. AST parsing handles arbitrarily large files.
- `value_repr` truncation at 200 chars prevents manifest bloat from large literals.
- Cache files are per-source-file, so no single cache file grows unboundedly.

---

## 10. Testing Strategy

### 10.1 Test Categories

| Category | File | Count (est.) |
|----------|------|-------------|
| Model validation | `test_code_manifest.py` | ~15 |
| Element extraction | `test_code_manifest.py` | ~25 |
| FQN computation | `test_code_manifest.py` | ~8 |
| Signature extraction | `test_code_manifest.py` | ~12 |
| Import classification | `test_code_manifest.py` | ~8 |
| Edge cases | `test_code_manifest.py` | ~10 |
| Cache hit/miss | `test_manifest_cache.py` | ~8 |
| Staleness detection | `test_manifest_cache.py` | ~5 |
| Batch scanning | `test_manifest_cache.py` | ~5 |

### 10.2 Test Fixtures

Use inline Python source strings as fixtures (not external files) for determinism:

```python
SIMPLE_MODULE = '''
"""Module docstring."""

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from startd8.models import AgentConfig

_CONSTANT: int = 42
public_var = "hello"

def top_function(x: int, y: str = "default") -> bool:
    """Do something."""
    return True

class MyClass(BaseModel):
    """A sample class."""

    class_var: str = "value"

    def method(self, arg: str) -> None:
        ...

    @property
    def prop(self) -> int:
        return 0

    @staticmethod
    def static_method() -> None:
        ...
'''
```

### 10.3 Real-File Smoke Test

One integration-style test runs `generate_file_manifest()` on `src/startd8/utils/code_manifest.py` itself (self-referential) and validates:
- Module path is `startd8.utils.code_manifest`
- `FileManifest` class appears in elements
- `generate_file_manifest` function appears in elements
- Element count is reasonable (> 10)

---

## 11. Performance Budget

| Operation | Target | Notes |
|-----------|--------|-------|
| Single-file manifest (AST) | < 100ms | `ast.parse()` + visitor + model construction |
| Single-file manifest (+ symtable) | < 110ms | Phase 3 adds ~10ms |
| Batch scan (150 files) | < 10s | Includes file I/O, excludes cache writes |
| Cache check (150 files) | < 1s | Digest computation only |
| `lookup_element()` | < 1ms | Linear scan of flat element list |

---

## 12. Dependencies

### New Dependencies

**None.** All required modules are in the Python standard library or already in the SDK:
- `ast`, `hashlib`, `symtable` — stdlib
- `pydantic` — already a dependency
- `PyYAML` — already a dependency (via `pyyaml`)
- `typer`, `rich` — already dependencies

### Internal Dependencies

- `startd8.logging_config.get_logger`
- `startd8.utils.file_operations.atomic_write_json`
- `startd8.workflows.builtin.preflight_rules._helpers.STDLIB_FALLBACK`

---

## 13. Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| AST node types missed (e.g., `match`, `type` statement) | Medium | Low | Comprehensive test fixtures covering Python 3.9–3.14 syntax |
| FQN computation fails for non-standard layouts | Medium | Medium | Configurable `source_root` parameter; tested against SDK's `src/` layout |
| Cache corruption on concurrent writes | Low | Low | `atomic_write()` prevents partial files; digest keys prevent overwrite conflicts |
| Large file performance | Low | Low | AST parsing is linear; no file in the SDK exceeds 3000 lines |
| Pydantic v2 serialization edge cases | Low | Low | Frozen models with simple types; no custom serializers needed |

---

## 14. Future Considerations (Out of Scope for P0/P1)

- **Diff-aware manifests**: Generate manifest diffs between two versions of a file (useful for INTEGRATE phase conflict detection)
- **Cross-file dependency graph**: Build a project-wide graph of `imports` → `Elements` (useful for blast radius)
- **Watch mode**: File system watcher that regenerates manifests on source change
- **Multi-language support**: Extend manifest schema to TypeScript, Rust (via tree-sitter)
- **IDE integration**: LSP-compatible manifest endpoint for VS Code extensions

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

- **architecture**: 4 suggestions applied (R1-S5, R1-S8, R1-S10, R2-S4)
- **clarity**: 4 suggestions applied (R1-S7, R2-S5, R2-S6, R2-S7)
- **completeness**: 11 suggestions applied (R1-S1, R1-S2, R1-S3, R1-S4, R1-S7, R2-S2, R2-S3, R2-S5, R2-S6, R2-S7, R2-S8)

### Areas Needing Further Review

- **architecture**: 2 accepted (R1-S5, R1-S8) — needs 1 more to reach threshold of 3
- **maintainability**: 2 accepted (R1-S10, R2-S4) — needs 1 more to reach threshold of 3
- **scalability**: no accepted suggestions yet — needs 3 to reach threshold
- **security**: no accepted suggestions yet — needs 3 to reach threshold
- **testability**: 1 accepted (R1-S6) — needs 2 more to reach threshold of 3

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | The plan's Pydantic models are missing schema_version, errors, scope_guard, overload_index, tags, and is_reexport fields that were added to the requirements via prior review rounds. | claude-4 (claude-opus-4-6) | This is the most critical gap between the plan and the requirements. The requirements document was updated to include these fields through accepted suggestions, but the plan's Section 3 models were never synchronized. Implementing from the current plan models will produce manifests that violate the requirements specification. Every listed field has a clear rationale in the requirements and a defined schema. | 2026-02-24 16:40:39 UTC |
| R1-S2 | The plan's value_repr truncation uses a 200-char cap but the requirements specify a 120-char max with type-specific rules. | claude-4 (claude-opus-4-6) | The requirements define six specific, deterministic truncation rules (80 chars for strings, 120 for collections, multi-line collapse, etc.). The plan's blanket 200-char cap directly contradicts these rules and breaks the determinism contract. The plan must adopt the requirements' rules verbatim. | 2026-02-24 16:40:39 UTC |
| R1-S3 | The plan lacks handling for @property getter/setter/deleter triads and @typing.overload FQN disambiguation using @overload[N] and @getter/@setter/@deleter suffixes. | claude-4 (claude-opus-4-6) | The requirements explicitly define disambiguation schemes for these common Python patterns. Without them, multiple AST nodes sharing the same name produce duplicate FQNs, breaking the core addressability guarantee. The AST walking strategy and FQN computation sections must be updated. | 2026-02-24 16:40:39 UTC |
| R1-S4 | The plan has no handling for conditional block elements or the scope_guard field defined in requirements Section 4.1.1. | claude-4 (claude-opus-4-6) | Elements inside if TYPE_CHECKING, if __name__ == '__main__', and try/except blocks are common in Python codebases. The requirements define scope_guard metadata and @branch[N] FQN suffixes for these. The visitor architecture must track conditional context to produce compliant manifests. | 2026-02-24 16:40:39 UTC |
| R1-S5 | Use sys.stdlib_module_names (Python 3.10+) with STDLIB_FALLBACK as a fallback, rather than always using the static fallback set. | claude-4 (claude-opus-4-6) | sys.stdlib_module_names is authoritative for the running Python version and includes modules added in newer releases (e.g., tomllib in 3.11). The hybrid approach is a trivial one-line change that improves classification accuracy with no downside. | 2026-02-24 16:40:39 UTC |
| R1-S6 | Add tests for the error handling contract: partial manifests for syntax errors, encoding errors, I/O errors, and --strict mode. | claude-4 (claude-opus-4-6) | The requirements define four error kinds and two behavioral modes (graceful vs strict), but the test plan has zero coverage for any of them. Error handling is a key requirements addition that must be verified. | 2026-02-24 16:40:39 UTC |
| R1-S7 | Add --strict flag to CLI and clarify the relationship between 'manifest generate --check' and 'manifest check'. | claude-4 (claude-opus-4-6) | The requirements explicitly define --strict as an opt-in CI hard-failure mode. The plan omits it entirely. The overlap between --check on generate and the standalone check command also needs clarification to avoid user confusion. | 2026-02-24 16:40:39 UTC |
| R1-S8 | Describe how parent node references are maintained in the _ManifestVisitor for conditional import detection and scope_guard computation. | claude-4 (claude-opus-4-6) | ast.NodeVisitor does not provide parent references, but the plan claims to track parents without describing the mechanism. This is a concrete implementation gap that affects is_conditional detection and scope_guard computation. A pre-pass parent annotation or explicit parent stack must be specified. | 2026-02-24 16:40:39 UTC |
| R1-S10 | Add a model_validator to Element that enforces field-presence invariants based on kind (e.g., signature required for callables, bases empty for non-classes). | claude-4 (claude-opus-4-6) | The flat Element model was chosen explicitly over discriminated unions, but without validation, malformed elements silently pass through. A model_validator is the natural Pydantic mechanism to enforce the invariants that discriminated unions would have provided. This catches bugs at construction time. | 2026-02-24 16:40:39 UTC |
| R2-S2 | The FileManifest Pydantic model is missing the errors field required by the requirements for graceful degradation on parse failures. | gemini-2.5 (gemini-2.5-pro) | This is a duplicate of R1-S1's coverage of the errors field, but specifically calls out the Pydantic model gap. Accepting to reinforce — the errors field and ParseError model must be added to Section 3. | 2026-02-24 16:40:39 UTC |
| R2-S3 | The FileManifest model is missing the schema_version field and the plan lacks a versioning strategy. | gemini-2.5 (gemini-2.5-pro) | Duplicate of R1-S1's coverage of schema_version. The requirements define schema_version as '1.0.0' for Phase 1 with semver rules. The plan must include this field in the model. | 2026-02-24 16:40:39 UTC |
| R2-S4 | Replace is_pydantic and is_dataclass boolean flags on Element with a tags: list[str] field for extensible framework detection. | gemini-2.5 (gemini-2.5-pro) | The requirements explicitly replaced is_pydantic with a tags field (applied suggestion R2-S5). The plan still has both is_dataclass and is_pydantic booleans. The plan must adopt the tags approach from the requirements. | 2026-02-24 16:40:39 UTC |
| R2-S5 | The plan's FQN computation does not address @overload, @property triad, or conditional branch disambiguation edge cases. | gemini-2.5 (gemini-2.5-pro) | Duplicate of R1-S3 and R1-S4 in substance. The plan's Section 5.5 only handles the simple module.class.method case. The requirements define detailed disambiguation rules that must be reflected in the plan. | 2026-02-24 16:40:39 UTC |
| R2-S6 | Clarify that the decorators list stores full source expressions, not just names. | gemini-2.5 (gemini-2.5-pro) | The requirements (Section 3.2) explicitly state decorators are stored as full source text with examples like 'dataclass(frozen=True)' and 'app.route("/users", methods=["POST"])'. The plan's model docstring should reflect this to avoid implementer ambiguity. | 2026-02-24 16:40:39 UTC |
| R2-S7 | The plan's value_repr 200-char truncation rule conflicts with the requirements' detailed type-specific truncation rules. | gemini-2.5 (gemini-2.5-pro) | Duplicate of R1-S2. The plan must adopt the requirements' six-rule truncation system with 120-char maximum. | 2026-02-24 16:40:39 UTC |
| R2-S8 | The ImportEntry model is missing the is_reexport field required for public API surface analysis. | gemini-2.5 (gemini-2.5-pro) | Duplicate of R1-S1's coverage of is_reexport. The requirements define three detection heuristics for this field. The plan's ImportEntry model must include it. | 2026-02-24 16:40:39 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S9 | Document that _index.json is advisory and can be regenerated, and that concurrent writes are benign. | claude-4 (claude-opus-4-6) | The plan already states that cache entries are content-addressed and never go stale. The _index.json concurrency concern is a theoretical edge case for CI environments that can be addressed during implementation if it materializes. Adding concurrent-write documentation and testing for an advisory index file is low-value relative to the many higher-priority gaps that need attention. | 2026-02-24 16:40:39 UTC |
| R2-S1 | Align the plan with the requirement for preserving comments and formatting during surgical edits. | gemini-2.5 (gemini-2.5-pro) | The requirements document already addresses this in the applied R2-S1 suggestion, specifying span-based text splicing rather than AST unparse. The manifest generator itself does not perform surgical edits — it generates manifests. Comment preservation is a concern for downstream consumers of the manifest, not for the manifest generator. The plan correctly focuses on generating accurate spans; how those spans are used for editing is a separate concern. | 2026-02-24 16:40:39 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-24 16:36:49 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | completeness | critical | The plan's Pydantic models are missing the `schema_version` field on `FileManifest`, the `errors` field on `FileManifest`, the `scope_guard` field on `Element`, the `overload_index` field on callable elements, the `tags` field on class elements, and the `is_reexport` field on `ImportEntry`. All of these were added to the requirements via applied suggestions (R1-S1, R1-S2, R1-S3, R1-S5, R1-S7, R1-S10, R1-S1, R1-S2, R1-S3, R1-S5) but the plan's Section 3 models do not reflect them. | The requirements document was updated after prior review rounds to include `schema_version`, `errors: list[ParseError]`, `scope_guard`, `overload_index`, `tags`, `is_reexport`, and the `ParseError` model. The plan's Pydantic models in Section 3 are stale relative to the accepted requirements. This is the single largest gap — implementing from these models will produce non-compliant manifests. | Section 3.2 (Value Objects): add `ParseError` model. Section 3.3 (Core Models): add `schema_version`, `errors` to `FileManifest`; add `scope_guard`, `overload_index` to `Element`; add `tags` to `Element` (replacing `is_pydantic`); add `is_reexport` to `ImportEntry`. | Generate a manifest for a file with `@overload`, `@property` setter, conditional definitions, and Pydantic classes. Verify all new fields are populated and round-trip through JSON serialization. |
| R1-S2 | completeness | high | The plan's `value_repr` truncation uses a 200-character cap (Section 3.4 Model Decisions), but the requirements specify a 120-character maximum with type-specific rules (80 chars for strings, 120 for collections/expressions). The plan must adopt the requirements' truncation rules. | Requirements Section 3.2.3 defines six specific representation rules with different thresholds per type. The plan's blanket 200-char cap violates the requirements' determinism contract and will produce non-conformant output. | Section 3.4 "Model Decisions" bullet on `value_repr` truncation: replace "Capped at 200 characters" with the full rule set from requirements Section 3.2.3. Also update `_ManifestVisitor` implementation notes in Section 5. | Write parameterized tests for each of the 6 truncation rules: simple literals, strings >80 chars, collections >120 chars, complex expressions, multi-line collapse, and null fallback. |
| R1-S3 | completeness | high | The plan has no handling for `@property` getter/setter/deleter triads or `@typing.overload` FQN disambiguation. Requirements Section 3.2.1 specifies `@overload[N]` suffixes and `@getter`/`@setter`/`@deleter` suffixes on FQNs. The AST walking strategy (Section 5.2) and FQN computation (Section 5.5) must account for these. | Without this, multiple AST nodes sharing the same name within a class will produce duplicate FQNs, breaking the fundamental addressability guarantee (Success Criterion 2). The requirements explicitly define the disambiguation scheme. | Section 5.2 "Element Extraction Rules": add rows for `@property` setter/deleter and `@overload`. Section 5.5 "FQN Computation": add suffix logic. Section 5.1 "Visitor Architecture": add name-collision tracking per scope. | Test with a class containing `@property` + `@x.setter` + `@x.deleter` and a function with 3 `@overload` variants plus implementation. Verify 4 distinct FQNs for overloads and 3 distinct FQNs for property triad. |
| R1-S4 | completeness | high | The plan has no handling for conditional block elements or the `scope_guard` field. Requirements Section 4.1.1 specifies that elements inside `if TYPE_CHECKING:`, `if __name__ == "__main__":`, `try/except`, and other conditional blocks receive a `scope_guard` field, and duplicate names across branches receive `@branch[N]` FQN suffixes. | The `_ManifestVisitor` in Section 5.1 does not track conditional context. Without this, elements defined in `if __name__ == "__main__":` blocks will either be missed or will lack the metadata needed for correct pipeline behavior (e.g., plan ingestion should not treat `__main__`-guarded code as importable API). | Section 5.1 "Visitor Architecture": add conditional context tracking to the scope stack. Section 5.2: add extraction rules for elements in conditional blocks. Add `scope_guard` to the `Element` model in Section 3.3. | Test with a file containing `if TYPE_CHECKING:`, `if __name__ == "__main__":`, and `try/except ImportError` blocks, each defining functions. Verify `scope_guard` values and `@branch[N]` suffixes where names collide. |
| R1-S5 | architecture | medium | The plan imports `STDLIB_FALLBACK` from `preflight_rules/_helpers.py` (D-10), but the requirements specify using `sys.stdlib_module_names` (Python 3.10+) with a vendored fallback. The plan should prefer the runtime set when available and fall back to the static set, rather than always using the static fallback. | `sys.stdlib_module_names` is authoritative for the running Python version and includes modules added in newer releases. The static `STDLIB_FALLBACK` set (~120 names) may be incomplete for Python 3.12+ (e.g., `tomllib` added in 3.11). Using the runtime set when available improves classification accuracy. | Section 5.4 "Dependency Classification": change `stdlib_set` resolution to `getattr(sys, 'stdlib_module_names', STDLIB_FALLBACK)`. Update D-10 in Section 1 to reflect the hybrid approach. | Test on Python 3.10+ that `tomllib` is classified as stdlib. Test on Python 3.9 that it falls back to the static set. |
| R1-S6 | testability | medium | The testing strategy (Section 10) lacks tests for the requirements' error handling contract: partial manifests for syntax errors, encoding errors, I/O errors, and the `--strict` mode. The `errors` field behavior is a key requirements addition that has no corresponding test plan. | Requirements Section 5.7 defines four error kinds (`syntax_error`, `encoding_error`, `io_error`, `partial_parse`) and two behavioral modes (default graceful vs. `--strict`). Without tests for these, the error handling contract is unverifiable. | Section 10.1 "Test Categories": add an "Error handling" row (~10 tests). Section 10.2 "Test Fixtures": add fixtures for syntax-error files, binary files, and permission-denied scenarios. | Test: file with `SyntaxError` → manifest has empty elements and populated `errors`. Binary file → `encoding_error`. `--strict` flag → non-zero exit on first error. Batch with 1 bad file → other files still processed. |
| R1-S7 | clarity | medium | The plan's CLI section (4.3) does not include the `--strict` flag defined in requirements Section 5.7. The `generate` command needs `--strict` for CI hard-failure mode, and the `check` command's relationship to `--check` on `generate` is unclear (both seem to do staleness checking). | Requirements explicitly define `--strict` as an opt-in flag that treats any parse error as a hard failure. The plan omits it. Additionally, `startd8 manifest generate --check` and `startd8 manifest check` appear to do the same thing, which will confuse users. | Section 4.3 "CLI Commands": add `--strict` to `generate`. Clarify that `check` is a convenience alias for `generate --check` (no regeneration) or differentiate their behavior explicitly. | Verify CLI help text documents `--strict`. Test that `--strict` with a syntax-error file exits non-zero. Test that `check` does not write any cache files. |
| R1-S8 | architecture | medium | The `_ManifestVisitor` uses `ast.NodeVisitor` (Section 5.1), which only provides `visit_*` methods and does not automatically pass parent node references. The plan needs parent tracking for conditional import detection (`is_conditional`) and `scope_guard` computation, but does not describe how parent references are maintained. | `ast.NodeVisitor.generic_visit()` does not set parent references on child nodes. The plan mentions "Tracks parent nodes to detect conditional imports" but does not describe the mechanism. Common approaches: (a) pre-pass that annotates each node with a `parent` attribute, (b) maintaining an explicit parent stack during traversal, or (c) using `ast.walk()` with manual parent tracking. The choice affects visitor complexity. | Section 5.1 "Visitor Architecture": add a bullet describing the parent-tracking mechanism. Recommend a pre-pass `_annotate_parents(tree)` that sets `node._parent` on every node, as this is the simplest and most robust approach. | Test that `is_conditional` is correctly set for imports inside `if TYPE_CHECKING:`, `try/except ImportError`, and nested conditionals. Test that `scope_guard` is set for elements inside `if __name__ == "__main__":`. |
| R1-S9 | scalability | medium | The cache layout (Section 6.1) uses content-addressed digest keys, but the `_index.json` file mapping paths → digests is a single file that must be read/written atomically for the entire project. For large projects or concurrent CI runs, this becomes a bottleneck and a corruption risk. | While `atomic_write()` prevents partial writes, two concurrent `generate_project_manifests()` calls on the same project (e.g., parallel CI jobs) can race on `_index.json`. One process reads the index, generates manifests, and writes the index — but the other process may have written a different index in between. Content-addressed cache files are safe (idempotent), but the index is not. | Section 6.1 "Cache Layout": document that `_index.json` is advisory (used for `check_manifests_fresh()` only) and can be regenerated from the manifest files + current source. Section 6.2: note that concurrent writes to the index are benign because the index is rebuilt on each `generate_project_manifests()` call. | Test: run two concurrent `generate_project_manifests()` calls. Verify no crash, no corrupt index, and all manifests are correct. |
| R1-S10 | maintainability | low | The `Element` model uses a flat structure with many optional fields (Section 3.4 rationale). While this simplifies serialization, it means every `Element` carries `bases`, `metaclass`, `is_dataclass`, `signature`, etc. even for `CONSTANT` elements. Consider adding a `model_validator` that enforces field presence rules based on `kind` (e.g., `signature` must be non-None for callables, `bases` must be empty for non-classes). | Without validation, a malformed `Element` (e.g., a `CONSTANT` with `bases=["Foo"]`) would silently pass through Pydantic. Field-presence invariants tied to `kind` catch bugs at construction time rather than downstream. This is especially important since the flat model was chosen explicitly over discriminated unions. | Section 3.3 "Core Models" `Element` class: add a `@model_validator(mode='after')` that validates field-kind consistency. Section 10.1: add tests for invalid field combinations. | Test that constructing `Element(kind=CONSTANT, bases=["Foo"])` raises `ValidationError`. Test that `Element(kind=FUNCTION, signature=None)` raises `ValidationError`. |

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | ambiguity | medium | The `scope_guard` field introduced in Section 4.1.1 is described in the FQN edge cases section but never added to the Element schema table in Section 3.2. It is an implicit field with no type, default, or optionality defined. | Consumers of the manifest schema will look at Section 3.2 for the canonical field list. `scope_guard` is described narratively but never formally specified with a type (`string?`), default (`null`), or inclusion in the schema table. This creates ambiguity for implementers. | Section 3.2 "Element Schema" table: add `scope_guard` as `string?` with default `null` and description referencing Section 4.1.1 rules. | Verify that the schema table in 3.2 includes every field referenced elsewhere in the document. |
| R1-F2 | ambiguity | medium | The `overload_index` field introduced in Section 3.2.1 is described narratively but not added to the callable elements table. Its type is implied (`int?`) but never formally specified. | Same issue as R1-F1: the field is described in prose but missing from the formal schema table. Implementers may miss it or implement it inconsistently. | Section 3.2.1 callable elements table: add `overload_index` as `int?` with default `null`. | Verify the callable elements table includes `overload_index` with type and default. |
| R1-F3 | completeness | medium | The requirements define `is_reexport` on `ImportEntry` (Section 3.3) with three detection heuristics, but do not specify what happens for re-exports in non-`__init__.py` files that still appear in `__all__`. Heuristic (b) applies to any file, while (a) and (c) are `__init__.py`-specific. This creates an inconsistency. | A non-`__init__.py` module with `__all__ = ["SomeImportedName"]` should arguably mark that import as a re-export per heuristic (b), but the description frames re-exports as primarily an `__init__.py` concern. Clarify whether (b) applies universally or only in `__init__.py`. | Section 3.3 `is_reexport` description: clarify that heuristic (b) (`__all__` membership) applies to all files, while (a) and (c) are `__init__.py`-specific. | Test a non-`__init__.py` file that imports a name and includes it in `__all__`. Verify `is_reexport` is `true`. |
| R1-F4 | completeness | low | The requirements do not specify how relative imports (e.g., `from . import foo`, `from ..utils import bar`) are represented in the `ImportEntry.module` field. Is the module path resolved to an absolute dotted path, or is the relative syntax preserved (e.g., `".foo"`, `"..utils.bar"`)? | Relative imports are extremely common in packages. The `module` field type is `string`, but its content format for relative imports is unspecified. This affects dependency classification (Section 3.4 rule 2 identifies relative imports as internal) and FQN-based lookup. | Section 3.3 `ImportEntry.module` description: specify whether relative imports are stored as-is (`".foo"`) or resolved to absolute paths (`"startd8.utils.foo"`). Recommend storing the resolved absolute path with an additional `is_relative: bool` field for provenance. | Test with `from . import foo` and `from ..utils import bar`. Verify the `module` field format matches the specification. |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| 2.1 Layer 1: AST | Phase 1, Section 5 (AST Walking Strategy) | Partial | Plan does not address AST limitations re: comment/formatting preservation. Plan does not address dynamically generated code exclusion. |
| 2.2 Layer 2: Symbol Table | Phase 3 (Section 7) | Full | Adequately deferred to Phase 3/P1. |
| 2.3 Layer 3: Runtime Introspection | Phase 5 (Section 7) | Full | Adequately deferred to Phase 5/P2. |
| 2.4 Layer 4: Bytecode | Phase 6 (Section 7) | Full | Adequately deferred to Phase 6/P3. |
| 2.5 Layer 5: Execution Trace | Not in plan | Full | Correctly excluded (P4 future). |
| 3.1 File-Level Manifest | Section 3.3 `FileManifest` model | Partial | Missing `schema_version`, `errors`, `ParseError` model. |
| 3.2 Element Schema | Section 3.3 `Element` model | Partial | Missing `scope_guard`, `overload_index`, `tags` (has `is_pydantic` instead). Decorator format not specified as full source expression. |
| 3.2.1 Callable Elements | Section 3.3 `Element` + `Signature` | Partial | Missing `overload_index`. No `@overload` or `@property` triad handling in extraction rules. |
| 3.2.2 Class Elements | Section 3.3 `Element` | Partial | Has `is_pydantic: bool` instead of `tags: list[str]`. Missing `tags` detection heuristics. |
| 3.2.3 Assignment Elements | Section 3.3 `Element` | Partial | `value_repr` truncation rules don't match requirements (200 chars vs. 120 max with type-specific rules). `is_type_alias` still present in plan but removed in requirements. |
| 3.3 Import Schema | Section 3.3 `ImportEntry` model | Partial | Missing `is_reexport` field. |
| 3.4 Dependency Summary | Section 5.4 `_classify_imports()` | Partial | Classification algorithm doesn't match requirements' 4-step rules (e.g., relative imports rule, conditional dual-classification). |
| 3.5 Schema Versioning | Not in plan | None | Requirements define semver strategy and compatibility contract. Plan has no versioning implementation. |
| 4.1 FQN Addressing | Section 5.5 `_compute_module_path()` | Partial | Basic module path computation present. Missing conditional block FQN rules, `@branch[N]` disambiguation, `@overload[N]` suffixes, `@getter/@setter/@deleter` suffixes. |
| 4.1.1 FQN Edge Cases | Not in plan | None | Conditional blocks, duplicate names across branches, nested scopes — all unaddressed. |
| 4.2 Span-Based Addressing | Section 3.2 `Span` model | Full | Span model correctly captures start/end line/col. |
| 4.3 Addressing in Pipeline Prompts | Phase 4 (Section 7) | Full | Deferred to Phase 4/P1. |
| 5.1 Input | Section 4.1 `generate_file_manifest()` | Full | Accepts file path, project root, optional source. |
| 5.2 Output Formats | Section 1 D-7 | Full | JSON primary, YAML convenience. |
| 5.3 Generation Modes | Not in plan | Partial | Plan implements `static` mode only (Phase 1). `introspect` and `full` modes referenced in Phase 5/6 but no mode parameter in API. |
| 5.4 Determinism | Section 7 Phase 1 acceptance criteria | Full | "same source → byte-identical JSON output" stated. |
| 5.5 Performance | Section 11 Performance Budget | Full | Targets match or exceed requirements. |
| 5.6 Staleness Detection | Section 6 Caching Strategy | Full | Digest-based staleness with `--check` mode. |
| 5.7 Error Handling | Not in plan | None | Requirements define 4 error kinds, `--strict` mode, partial manifests, downstream consumer contract. Plan has no error handling beyond "raises SyntaxError". |
| 6.1 Capability Index Build | Phase 4 (Section 7) | Partial | Mentioned but no consumed-fields mapping. |
| 6.2 Plan Ingestion | Phase 4 (Section 7) | Partial | Mentioned but no consumed-fields mapping. |
| 6.3 Artisan IMPLEMENT | Phase 4 (Section 7) | Partial | Mentioned but no consumed-fields mapping. |
| 6.4 Artisan INTEGRATE | Phase 4 (Section 7) | Partial | Mentioned but no consumed-fields mapping. |
| 6.5 Artisan REVIEW | Phase 4 (Section 7) | Partial | Mentioned but no consumed-fields mapping. |
| 6.6 Preflight Validators | Phase 4 (Section 7) | Partial | Mentioned but no consumed-fields mapping. |
| 6.7 Code Review Skill | Phase 4 (Section 7) | Partial | Mentioned but no consumed-fields mapping. |
| 8 Non-Requirements | Section 14 Future Considerations | Full | Exclusions properly deferred. |
| 9 Implementation Phases | Section 7 Implementation Phases | Partial | Plan phases match but Phase 1/2 deliverables don't include all accepted requirements (error handling, schema version, strict mode). |
| 10 Success Criteria | Section 7 acceptance criteria | Partial | Criteria 1, 2, 6, 7 addressed. Criteria 3 (surgical edits), 4 (blast radius), 5 (ground truth), 8 (graceful degradation), 9 (schema evolution) not testable from plan deliverables. |

#### Review Round R2
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-24 16:38:45 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | completeness | critical | Align the plan with the requirement for preserving comments and formatting during surgical edits. | The plan relies on the standard `ast` module, but `ast.unparse()` discards all comments and formatting, which is a dealbreaker for production code modification. The requirements doc correctly identifies this and mandates span-based splicing. The plan should explicitly state this strategy to mitigate the risk of implementing a destructive editing mechanism. | Section 1, D-4 (Incremental vs full regen) or a new Design Decision. | Create a test case where a function containing comments is modified via a generated manifest. Verify that the comments and surrounding whitespace in the resulting file are preserved verbatim. |
| R2-S2 | completeness | high | The `FileManifest` Pydantic model is missing the `errors` field required by the feature specification. | The requirements (Sec 5.7) mandate a graceful degradation strategy where files with syntax errors produce a partial manifest containing an `errors` field. The plan's `FileManifest` model in Section 3.3 omits this field, creating a direct conflict with the requirements and leaving error handling undefined at the data model level. | Section 3.3 (Core Models), update the `FileManifest` Pydantic model. | Create a Python file with a syntax error. Run `generate_file_manifest()` on it. Verify the returned `FileManifest` object has a non-empty `errors` attribute and that the overall process does not crash. |
| R2-S3 | completeness | high | The `FileManifest` model is missing the `schema_version` field and the plan lacks a versioning strategy. | The requirements (Sec 3.5) mandate a `schema_version` field to manage schema evolution across the multi-phase implementation. The plan's data model in Section 3.3 omits this field. Without it, downstream consumers will be unable to handle manifests generated by different versions of the tool, leading to brittle integrations. | Section 3.3 (Core Models), add `schema_version: str` to `FileManifest`. Add a Design Decision in Section 1 about versioning. | Inspect the generated JSON/YAML from `generate_file_manifest()` and confirm the presence of a top-level field like `"schema_version": "1.0.0"`. |
| R2-S4 | maintainability | medium | Generalize the framework-specific `is_pydantic` and `is_dataclass` boolean flags to a more extensible `tags` field. | The plan's `Element` model uses hardcoded boolean flags for specific frameworks. This approach is not scalable and requires schema changes for every new framework (e.g., Django, attrs, FastAPI). The requirements doc (Sec 3.2.2) proposes a more robust `tags: list[string]` field, which the plan should adopt for better maintainability. | Section 3.3 (Core Models), modify the `Element` model to replace `is_pydantic` and `is_dataclass` with `tags: list[str] = []`. | Create test cases with Pydantic, dataclass, and attrs classes. Verify the manifest element for each class contains the correct corresponding tag (e.g., `"pydantic_model"`, `"dataclass"`) in its `tags` list. |
| R2-S5 | clarity | medium | The plan's FQN computation logic does not address the edge cases defined in the requirements. | The requirements (Sec 3.2.1, 4.1.1) specify detailed FQN schemes for complex cases like `@overload`, `@property` triads, and definitions in conditional branches. The plan's FQN computation section (5.5) only covers the simple case, leaving the implementation of these critical edge cases ambiguous and untested. | Section 5.5 (FQN Computation), add details on handling overloads, properties, and conditional branches. | Write unit tests for files containing `@overload` functions, `@property` with setters, and functions defined in `if/else` blocks. Assert that the generated FQNs are unique and follow the disambiguation rules from the requirements. |
| R2-S6 | clarity | medium | Clarify that the `decorators` list stores full source expressions, not just names. | The plan's `Element` model defines `decorators: list[str]`, which is ambiguous. It could mean `"dataclass"` or `"dataclass(frozen=True)"`. The requirements (Sec 3.2) specify storing the full source text, which is more useful. The plan should explicitly adopt this to avoid ambiguity for implementers and consumers. | Section 3.3 (Core Models), add a comment or docstring to the `decorators` field in the `Element` model clarifying its contents. | Create a test function with a decorator that has arguments (e.g., `@pytest.mark.parametrize(...)`). Verify that the manifest contains the full string representation of the decorator expression. |
| R2-S7 | clarity | medium | The plan's `value_repr` truncation rule (200 chars) conflicts with the more detailed, deterministic rules in the requirements. | The requirements (Sec 3.2.3) specify a detailed set of truncation rules for `value_repr` to ensure deterministic output. The plan's model decision note proposes a simpler "capped at 200 characters" rule. This inconsistency should be resolved, preferably by adopting the more specific rules from the requirements to guarantee determinism. | Section 3.4 (Model Decisions), update the "value_repr truncation" note to align with the requirements document. | Create test cases for assignments with a long string, a large dict, and a complex call expression. Verify the `value_repr` in the manifest conforms to the specific truncation rules from the requirements doc. |
| R2-S8 | completeness | medium | The `ImportEntry` model is missing the `is_reexport` field required for public API surface analysis. | The requirements (Sec 3.3) specify an `is_reexport` flag on imports to distinguish names that form a package's public API from internal-use imports. This is critical for pipeline integration points like Plan Ingestion. The plan's `ImportEntry` model in Section 3.3 omits this field. | Section 3.3 (Core Models), add `is_reexport: bool = False` to the `ImportEntry` model. | Generate a manifest for an `__init__.py` file that re-exports a name from a submodule. Verify that the corresponding `ImportEntry` has `is_reexport` set to `true`. |

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | consistency | medium | Consolidate the redundant `is_dataclass` boolean and `"dataclass"` tag in the `Element` schema. | Section 3.2.2 defines both a boolean field `is_dataclass` and a `tags` list that is populated with `"dataclass"`. This is redundant. The schema should use only the `tags` field for all framework identification to provide a single, consistent mechanism. | Section 3.2.2, remove the `is_dataclass` field and rely solely on the `tags` list. | Review the schema to confirm only one field represents dataclass status. Test that a dataclass element correctly receives the `"dataclass"` tag. |
| R2-F2 | ambiguity | medium | The FQN disambiguation syntax using `@` (e.g., `...process@overload[0]`) is not a valid Python identifier path. | Sections 3.2.1 and 4.1.1 propose an FQN syntax that includes `@`, `[` and `]`. While human-readable, this will likely break downstream tooling that expects FQNs to be valid Python dot-separated paths. A more robust separator (e.g., `::__`) or a separate `disambiguator` field should be considered. | Sections 3.2.1 and 4.1.1. | Design a test where a generated FQN is passed to `pydoc.locate()` or a similar tool. The validation should ensure the name can be resolved or that the non-standard part can be easily stripped to get a resolvable path. |
| R2-F3 | consistency | low | The representation of pre-3.12 type aliases is inconsistent. | The note in Section 3.2 says `TypeAlias` assignments are `kind: variable`, but the `ElementKind` enum includes `type_alias`. This is confusing. For consistency, both Python 3.12 `type` statements and `TypeAlias` assignments should resolve to `kind: type_alias`. This simplifies consumer logic as they only need to check the `kind`. | Section 3.2, update the note to state that `X: TypeAlias = ...` patterns should also be classified with `kind: type_alias`. | Create a test file with both a `type` statement and a `TypeAlias` assignment. Verify that both elements in the manifest have `kind: "type_alias"`. |
| R2-F4 | feasibility | low | The `python_version` inference logic is undefined and potentially unreliable. | Section 3.1 requires a `python_version` field inferred "from AST features used." This is a complex heuristic (e.g., `ast.Match` implies 3.10+, but its absence implies nothing). The requirement should clarify if this is a strict minimum version or a best-effort hint, and acknowledge that it may not be perfectly accurate. | Section 3.1, add a note to the `python_version` field description clarifying its nature as a best-effort inference of the minimum required version. | Create a file using a `match` statement and another using only Python 3.8 syntax. Verify the former gets `3.10` (or higher) and the latter gets a lower version, demonstrating the heuristic works for a clear case. |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps / Notes |
|---------------------|--------------|----------|--------------|
| 2. Execution Model Layers | 5 (AST), 7.3 (Symtable), 7.5 (Introspection), 7.6 (Bytecode) | Full | The plan correctly maps each layer to a distinct implementation phase. |
| 3.1 File-Level Manifest | 3.3 (Core Models) | Partial | Plan's `FileManifest` model is missing the required `schema_version` and `errors` fields. |
| 3.2 Element Schema | 3.3 (Core Models) | Partial | Plan uses `is_pydantic`/`is_dataclass` instead of the more extensible `tags` field required. Does not explicitly mention handling for FQN edge cases (`@overload`, etc.). |
| 3.3 Import Schema | 3.3 (Core Models) | Partial | Plan's `ImportEntry` model is missing the required `is_reexport` field. |
| 3.4 Dependency Summary | 3.3 (Core Models), 5.4 (Classification) | Full | The plan includes the `Dependencies` model and a function for classification. |
| 3.5 Schema Versioning | N/A | None | The plan completely omits any mention of schema versioning, a direct contradiction of the requirement. |
| 4. Addressing Scheme | 5.5 (FQN Computation) | Partial | The plan covers basic FQN computation but lacks the detail for handling the edge cases (conditional blocks, overloads) specified in the requirements. |
| 5. Generation Requirements | 1 (Decisions), 4 (API), 7 (Phases), 9 (Error Handling), 11 (Perf) | Full | The plan covers formats, modes, determinism, performance, and error handling. |
| 6. Pipeline Integration | 7.4 (Pipeline Integration) | Full | The plan dedicates a phase to pipeline integration, aligning with the requirements. |
| 7. Existing Code | 8 (Reusable Existing Code) | Full | The plan correctly identifies and plans to reuse existing assets. |
| 8. Non-Requirements | 14 (Future Considerations) | Full | The plan aligns with the specified exclusions. |
| 9. Implementation Phases | 7 (Implementation Phases) | Full | The plan's phases directly map to the phases outlined in the requirements. |
| 10. Success Criteria | 10 (Testing Strategy), 11 (Perf Budget) | Full | The plan's testing and performance sections address the success criteria. |
