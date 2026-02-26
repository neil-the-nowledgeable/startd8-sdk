# Code Manifest Phase 6: Call Graph and Bytecode Analysis

**Status:** Draft
**Date:** 2026-02-24
**Author:** Neil Yashinsky + agent:claude-code
**Parent:** `docs/design/CODE_MANIFEST_REQUIREMENTS.md` (Section 2.4 Layer 4, Section 9 Phase 6)
**Dependencies:** Phase 1 (P0, complete), Phase 2 (P0, complete), Phase 3 (P1, complete)
**Schema Version:** `1.2.0` → `1.3.0` (additive: call graph and bytecode fields)

---

## 1. Objective

Extract intra-function call graphs, attribute access patterns, and dynamic dispatch markers from CPython bytecode using the `dis` module. This enables:

- **Blast radius estimation**: Given a planned change to function F, identify all functions that call F
- **Cross-file dependency graphs**: Build caller→callee edges across the project
- **Dead code detection**: Functions with no inbound call edges (complementary to test coverage)
- **Dynamic dispatch flagging**: Mark elements that use `getattr()`, `eval()`, or computed attribute access, warning consumers that static analysis is incomplete

This phase implements Layer 4 (Bytecode — Instruction Stream) from `CODE_MANIFEST_REQUIREMENTS.md` Section 2.4.

---

## 2. Scope

### 2.1 In Scope

| Capability | Description |
|-----------|-------------|
| Intra-function call extraction | For each callable element, extract the set of functions/methods it calls |
| Attribute access patterns | For each callable, extract `self.x` reads and `self.x = ...` writes |
| Cross-file call graph | Build project-wide caller→callee edges using FQN resolution |
| Dynamic dispatch detection | Flag callables that use `getattr()`, `eval()`, `exec()`, or computed attribute access |
| Blast radius computation | Given a target FQN, return all transitive callers (reverse reachability) |
| Registry integration | Expose call graph queries via `ManifestRegistry` |

### 2.2 Out of Scope

| Exclusion | Rationale |
|-----------|-----------|
| Data flow analysis | Tracking value propagation between variables is P4 (execution trace) |
| Runtime type inference | Requires execution; belongs to Phase 5 (introspection) |
| Cross-language calls (C extensions, FFI) | Python-only; C extension calls appear as `CALL` to unresolvable names |
| Bytecode optimization or modification | Read-only analysis |
| Python version portability | Targets CPython 3.12+ bytecode format (CALL opcode); earlier formats unsupported |

---

## 3. Bytecode Analysis Model

### 3.1 CPython Bytecode Primer

Python compiles source to bytecode instructions executed by the CPython VM. The `dis` module provides programmatic access via `dis.get_instructions(code_object)`, returning `Instruction` named tuples with 12 fields:

| Field | Type | Relevance |
|-------|------|-----------|
| `opname` | `str` | Opcode name (e.g., `CALL`, `LOAD_ATTR`, `LOAD_GLOBAL`) |
| `arg` | `int?` | Raw argument (includes encoded flag bits) |
| `argval` | `any` | Resolved argument value (actual name string, constant, etc.) |
| `argrepr` | `str` | Human-readable argument (includes method flags) |
| `offset` | `int` | Byte offset in instruction stream |
| `line_number` | `int?` | Source line number |
| `positions` | `Positions?` | Source span: `(lineno, end_lineno, col_offset, end_col_offset)` |

### 3.2 Call Detection Strategy

**Target opcodes** (CPython 3.12+):

| Opcode | Meaning | Detection |
|--------|---------|-----------|
| `CALL` | Standard function/method call | Primary call indicator |
| `CALL_KW` | Call with keyword arguments | Same as `CALL`, with kwargs |
| `CALL_FUNCTION_EX` | Call with `*args`/`**kwargs` unpacking | Dynamic arg count |

**Callee resolution** — look backwards from each `CALL` to find the preceding load instruction:

| Load Pattern | Opcode | Callee Type | Resolution |
|-------------|--------|-------------|------------|
| `LOAD_GLOBAL name` | `LOAD_GLOBAL` with `arg & 1 == 1` | Module-level function | `argval` = function name |
| `LOAD_FAST obj` → `LOAD_ATTR method` | `LOAD_ATTR` with `arg & 1 == 1` | Method call | `argval` = method name; receiver from preceding `LOAD_FAST` |
| `LOAD_FAST obj` → `LOAD_ATTR attr` → `LOAD_ATTR method` | Chained `LOAD_ATTR` | Chained method call | Last `LOAD_ATTR` with method flag = callee |
| `LOAD_FAST func` | `LOAD_FAST` | Local callable | `argval` = local name (limited resolution) |

**Method vs. attribute read discrimination** (CPython 3.12+):
- `LOAD_ATTR` with `arg & 1 == 1` (or `"+ NULL|self" in argrepr`): method load (precedes `CALL`)
- `LOAD_ATTR` with `arg & 1 == 0`: plain attribute read

### 3.3 Attribute Access Detection

| Pattern | Bytecode Sequence | Classification |
|---------|------------------|----------------|
| `self.x` (read) | `LOAD_FAST 'self'` → `LOAD_ATTR 'x'` (no method flag) | Attribute read |
| `self.x = val` | `LOAD_FAST 'self'` → `STORE_ATTR 'x'` | Attribute write |
| `del self.x` | `LOAD_FAST 'self'` → `DELETE_ATTR 'x'` | Attribute delete |

Only `self`-prefixed attribute access is tracked (first parameter of methods). Other object attribute access is tracked as external calls.

### 3.4 Dynamic Dispatch Detection

A callable is flagged as having dynamic dispatch if its bytecode contains any of:

| Pattern | Detection |
|---------|-----------|
| `getattr(obj, name)` | `LOAD_GLOBAL 'getattr'` followed by `CALL` |
| `setattr(obj, name, val)` | `LOAD_GLOBAL 'setattr'` followed by `CALL` |
| `eval(expr)` | `LOAD_GLOBAL 'eval'` followed by `CALL` |
| `exec(code)` | `LOAD_GLOBAL 'exec'` followed by `CALL` |
| `obj.__getattr__` | `LOAD_ATTR '__getattr__'` |

---

## 4. Schema Additions

All additions are **additive** (new optional fields), maintaining backward compatibility per Section 3.5 of the parent requirements. Schema version increments from `1.2.0` to `1.3.0`.

### 4.1 New Model: `CallEntry`

Represents a single outbound call from a callable element.

| Field | Type | Description |
|-------|------|-------------|
| `target` | `string` | Callee name as it appears in bytecode. For method calls: `"method_name"`. For global calls: `"function_name"`. For chained: `"attr.method_name"`. |
| `target_fqn` | `string?` | Resolved FQN of the callee if resolution succeeds (see Section 5.2). `null` when the target cannot be resolved (external, dynamic, or ambiguous). |
| `kind` | `enum` | `function_call`, `method_call`, `builtin_call`, `dynamic_call` |
| `receiver` | `string?` | Name of the receiver variable for method calls (e.g., `"self"`, `"obj"`). `null` for plain function calls. |
| `line` | `int?` | Source line number of the call site |

### 4.2 New Model: `AttributeAccess`

Represents an attribute read or write on `self` within a method.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Attribute name (e.g., `"x"`, `"_config"`) |
| `access` | `enum` | `read`, `write`, `delete` |
| `line` | `int?` | Source line number |

### 4.3 New Model: `CallGraphInfo`

Per-element call graph summary, attached to callable `Element` nodes.

| Field | Type | Description |
|-------|------|-------------|
| `calls` | `list[CallEntry]` | Outbound calls from this callable (deduplicated by `target` + `kind`) |
| `attribute_reads` | `list[string]` | Sorted unique `self.*` attributes read |
| `attribute_writes` | `list[string]` | Sorted unique `self.*` attributes written |
| `has_dynamic_dispatch` | `bool` | `True` if bytecode contains `getattr`/`setattr`/`eval`/`exec` patterns |
| `unresolved_calls` | `list[string]` | Call targets that could not be resolved to FQNs (informational) |

### 4.4 Element Schema Extension

Add one new optional field to the `Element` model (Section 3.2 of parent):

| Field | Type | Description |
|-------|------|-------------|
| `call_graph` | `CallGraphInfo?` | Bytecode-derived call graph info. Present only for callable elements (function, method, async variants) when bytecode analysis is enabled. `null` when analysis is not performed or the element is not callable. |

### 4.5 FileManifest Extension

Add one new optional field to the `FileManifest` model (Section 3.1 of parent):

| Field | Type | Description |
|-------|------|-------------|
| `call_graph_edges` | `list[CallEdge]?` | File-level summary of all resolved call edges. Each edge is `{caller_fqn, callee_fqn}`. `null` when bytecode analysis is not performed. |

Where `CallEdge` is:

| Field | Type | Description |
|-------|------|-------------|
| `caller_fqn` | `string` | FQN of the calling element |
| `callee_fqn` | `string` | FQN of the called element |

---

## 5. Call Graph Resolution

### 5.1 Intra-File Resolution

For each outbound call extracted from bytecode:

1. **Global function calls** (`LOAD_GLOBAL`): Look up `{module_path}.{name}` in the same file's element list.
2. **Method calls on `self`** (`LOAD_FAST 'self'` → `LOAD_ATTR`): Resolve to `{class_fqn}.{method_name}` using the enclosing class scope. Search class `children` and base classes (if bases are in the same file).
3. **Method calls on other locals**: Attempt type inference from assignment context (best-effort). If the local is assigned from a constructor call (`x = SomeClass()`), resolve methods via that class. Otherwise, mark as unresolved.
4. **Imported names**: Cross-reference against the file's `imports` list. If the call target matches an imported name, resolve to the import's module path.

### 5.2 Cross-File Resolution

Cross-file resolution operates on the full project manifest set (via `ManifestRegistry`):

1. For each `CallEntry` with `target_fqn == null` and a known import source, look up the target FQN in the registry's FQN index.
2. For `self.method()` calls where the class inherits from a base in another file, resolve via the base class's manifest.
3. Record unresolvable targets in `unresolved_calls` for diagnostic purposes.

### 5.3 Resolution Limitations

| Scenario | Behavior |
|----------|----------|
| Dynamic dispatch (`getattr`, computed names) | `has_dynamic_dispatch = True`; call not added to `calls` |
| Calls to third-party libraries | `target_fqn = null`; target name recorded |
| Calls via closures or callbacks | Target recorded as local name; FQN unresolved |
| Decorator-wrapped callables | Bytecode reflects the wrapper, not the original; may produce unexpected targets |
| `super().method()` | Resolved to parent class method via class bases (best-effort) |
| `*args`/`**kwargs` forwarding | `CALL_FUNCTION_EX` detected; callee resolved from preceding load if possible |

---

## 6. Project-Wide Call Graph

### 6.1 Graph Construction

The project-wide call graph is built from individual file manifests:

```
ProjectCallGraph = {
    caller_fqn → set[callee_fqn]
    for each file in project
    for each element in file.elements (recursive)
    for each call in element.call_graph.calls
    if call.target_fqn is not null
}
```

### 6.2 Blast Radius Query

Given a target FQN, compute all transitive callers (reverse reachability):

```
blast_radius(target_fqn) → set[caller_fqn]
```

Algorithm:
1. Build reverse graph: `callee_fqn → set[caller_fqn]`
2. BFS/DFS from `target_fqn` through reverse edges
3. Return all reachable caller FQNs
4. Optional depth limit to prevent unbounded traversal

### 6.3 Registry API Extensions

Add to `ManifestRegistry`:

| Method | Signature | Description |
|--------|-----------|-------------|
| `call_graph` | `() → dict[str, set[str]]` | Full project call graph (caller→callees) |
| `reverse_call_graph` | `() → dict[str, set[str]]` | Reverse graph (callee→callers) |
| `blast_radius` | `(fqn: str, max_depth: int = 10) → set[str]` | Transitive callers of the given FQN |
| `dead_candidates` | `() → list[str]` | Public callables with zero inbound edges (dead code candidates) |
| `callers_of` | `(fqn: str) → set[str]` | Direct (1-hop) callers |
| `callees_of` | `(fqn: str) → set[str]` | Direct (1-hop) callees |

---

## 7. Generation Modes

### 7.1 Mode Integration

Bytecode analysis requires compiling source to code objects via `compile()`. This is **not** runtime execution — `compile()` produces bytecode without importing or running the module. It is safe for any syntactically valid file.

| Mode | Layers | Bytecode Analysis | Safety |
|------|--------|-------------------|--------|
| `ast_only` | AST | No | No compilation |
| `static` | AST + symtable | No | No compilation |
| `bytecode` | AST + symtable + dis | **Yes** | `compile()` only — no import, no execution |
| `introspect` | AST + symtable + inspect | No (separate phase) | Requires import |
| `full` | All | **Yes** | `compile()` + import |

The `bytecode` mode is a new addition between `static` and `introspect`. It uses `compile()` which:
- Requires syntactically valid Python (same as `ast.parse()`)
- Does NOT import the module
- Does NOT execute any code
- Does NOT trigger side effects
- Produces a `code` object with bytecode for every function/class

### 7.2 Compilation Strategy

```python
code_obj = compile(source, str(file_path), "exec")
```

The top-level `code_obj` contains nested code objects for every function and class. These are extracted by walking `code_obj.co_consts` recursively:

```python
def _extract_code_objects(code: types.CodeType) -> dict[str, types.CodeType]:
    """Map qualified_name → code_object for all nested callables."""
    result = {}
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            result[const.co_qualname] = const  # Python 3.11+ co_qualname
            result.update(_extract_code_objects(const))
    return result
```

Code objects are matched to manifest elements by `co_qualname` (Python 3.11+) which mirrors the FQN structure (e.g., `ClassName.method_name`).

### 7.3 Fallback for Compilation Failures

If `compile()` raises `SyntaxError` (should not happen if `ast.parse()` succeeded, but defensive):
- Emit a `ParseError` with `kind: "partial_parse"` and message indicating bytecode compilation failed
- Return the manifest without `call_graph` fields (graceful degradation)
- Log a warning

---

## 8. Performance Requirements

| Metric | Target | Rationale |
|--------|--------|-----------|
| Single file bytecode analysis | < 50ms | `compile()` + `dis.get_instructions()` is fast; resolution is the bottleneck |
| Batch bytecode analysis (full `src/startd8/`) | < 15s total | ~5s for AST+symtable (current) + ~10s budget for bytecode |
| Cross-file resolution (full project) | < 5s | FQN index lookup is O(1); graph construction is O(edges) |
| Memory overhead per file | < 2MB | Call graph data is compact (lists of strings) |

### 8.1 Caching

- Bytecode analysis results are cached alongside manifest data in `.startd8/manifests/`
- Cache key: same `sha256` content digest — bytecode is deterministic for same source
- Cache invalidation: schema version change (`1.2.0` → `1.3.0`) invalidates all cached manifests

### 8.2 Deduplication

- `CallEntry` lists are deduplicated by `(target, kind)` tuple — a function called 10 times produces one entry
- `attribute_reads` and `attribute_writes` are stored as sorted unique sets

---

## 9. CLI Extensions

### 9.1 New Commands

```bash
# Generate manifests with bytecode analysis
startd8 manifest generate [PATH] --mode bytecode

# Show call graph for a specific element
startd8 manifest calls <FQN>
# Output: list of outbound calls with resolution status

# Show callers of a specific element (reverse lookup)
startd8 manifest callers <FQN>
# Output: list of direct callers

# Compute blast radius for a planned change
startd8 manifest blast-radius <FQN> [--max-depth N]
# Output: transitive callers, sorted by depth

# List dead code candidates
startd8 manifest dead-code [PATH]
# Output: public callables with zero inbound call edges
```

### 9.2 Output Formats

All new commands support `--format {json,yaml,text}` (default: `text` for human-readable, `json` for machine consumption).

---

## 10. Pipeline Integration

### 10.1 Plan Ingestion (Phase 4 consumer)

**Current gap:** Plan ingestion estimates blast radius via regex-extracted API signatures.

**With call graph:**
- Load call graph for files referenced in the plan
- For each planned modification, compute `blast_radius(target_fqn)`
- Annotate `ParsedFeature` with `affected_callers: list[str]` for dependency ordering
- Flag features that modify heavily-called functions (high blast radius warning)

### 10.2 Artisan IMPLEMENT Phase

**Current gap:** No structural context about how a function is used.

**With call graph:**
- Include `callers_of(target_fqn)` in the IMPLEMENT prompt supplement
- LLM sees which functions call the target, enabling backward-compatible modifications
- Post-generation validation: verify the generated code's call graph is compatible with callers

### 10.3 Artisan REVIEW Phase

**Current gap:** Review cannot assess cross-function impact.

**With call graph:**
- Review prompt includes blast radius for each modified element
- Reviewer can check: "this signature change breaks 5 callers" or "this function has no callers — consider removing"

### 10.4 Code Review Skill

**With call graph:**
- Structural change impact: "this PR modifies function X which is called by Y, Z"
- Dead code detection: "function X has no callers — was it recently orphaned?"

---

## 11. Error Handling

| Error Scenario | Behavior |
|---------------|----------|
| `compile()` failure | Log warning; return manifest without `call_graph` fields |
| Bytecode version mismatch | Detected via `sys.version_info`; warn if not CPython 3.12+ |
| Recursive code objects (deep nesting) | Depth limit of 20 on `_extract_code_objects()` |
| Extremely large functions (>10K instructions) | Process with instruction limit; log warning if truncated |
| Unresolvable FQN in cross-file resolution | Record in `unresolved_calls`; do not fail |

---

## 12. Constraints

1. **CPython-only**: Bytecode format is CPython-specific. PyPy, Jython, and other implementations have different bytecodes. The generator must check `platform.python_implementation() == "CPython"` and skip bytecode analysis otherwise.

2. **Version sensitivity**: Bytecode opcodes change between Python versions. This implementation targets CPython 3.12+ (where `CALL` replaced `CALL_FUNCTION`/`CALL_METHOD`). A version check must gate analysis and degrade gracefully for older Pythons.

3. **No execution**: `compile()` is used, NOT `exec()` or `import`. The bytecode is inspected, never run. This maintains the safety guarantee from Phase 1.

4. **Additive schema**: All new fields are optional with `null` defaults. Existing consumers of `1.2.0` manifests ignore unknown fields per the compatibility contract.

5. **Determinism**: For a given Python version and source file, bytecode analysis is fully deterministic. Same source → same call graph.

---

## 13. Implementation Plan

### 13.1 File Changes

| File | Change |
|------|--------|
| `src/startd8/utils/code_manifest.py` | Add `CallEntry`, `AttributeAccess`, `CallGraphInfo`, `CallEdge` models; add `call_graph` field to `Element`; add `call_graph_edges` field to `FileManifest`; implement bytecode analysis visitor; wire `mode="bytecode"` |
| `src/startd8/utils/manifest_cache.py` | Pass `mode` through to `generate_file_manifest()`; handle schema version bump |
| `src/startd8/utils/manifest_registry.py` | Add `call_graph()`, `reverse_call_graph()`, `blast_radius()`, `dead_candidates()`, `callers_of()`, `callees_of()` methods |
| `src/startd8/cli.py` | Add `manifest calls`, `manifest callers`, `manifest blast-radius`, `manifest dead-code` commands; add `--mode` option to `manifest generate` |
| `tests/unit/test_code_manifest_callgraph.py` | New test file for bytecode analysis (target: 40+ tests) |
| `tests/unit/test_manifest_registry_callgraph.py` | New test file for registry call graph queries |

### 13.2 Implementation Phases (Internal)

| Step | Description | Estimate |
|------|-------------|----------|
| 1 | Pydantic models (`CallEntry`, `AttributeAccess`, `CallGraphInfo`, `CallEdge`) | Small |
| 2 | Bytecode analyzer: `_analyze_bytecode(code_obj) → CallGraphInfo` | Medium |
| 3 | Code object extraction: `compile()` + `co_qualname` matching | Small |
| 4 | Element enrichment: attach `CallGraphInfo` to matching elements | Small |
| 5 | Intra-file FQN resolution | Medium |
| 6 | `FileManifest.call_graph_edges` aggregation | Small |
| 7 | Unit tests for steps 1-6 | Medium |
| 8 | Registry extensions: `call_graph()`, `reverse_call_graph()`, `blast_radius()` | Medium |
| 9 | Cross-file resolution via registry FQN index | Medium |
| 10 | CLI commands | Small |
| 11 | Integration tests + performance benchmarks | Medium |

---

## 14. Success Criteria

| # | Criterion | Validation |
|---|-----------|------------|
| 1 | **Call extraction accuracy**: For a test function with 5 known calls, all 5 are extracted with correct target names | Unit test with controlled function |
| 2 | **Method vs. function discrimination**: Method calls produce `kind: method_call` with correct receiver; function calls produce `kind: function_call` | Unit test with mixed call patterns |
| 3 | **Self-attribute tracking**: `self.x` reads and `self.x = y` writes are correctly classified | Unit test with method accessing instance attributes |
| 4 | **Dynamic dispatch flagging**: Functions using `getattr()` have `has_dynamic_dispatch: True` | Unit test |
| 5 | **Intra-file resolution**: Calls to functions defined in the same file have `target_fqn` populated | Unit test with caller→callee in same file |
| 6 | **Cross-file resolution**: Calls to imported functions have `target_fqn` populated via registry | Integration test with 2-file project |
| 7 | **Blast radius**: `blast_radius("module.func")` returns all transitive callers | Integration test with call chain A→B→C |
| 8 | **Dead code detection**: A public function with no callers appears in `dead_candidates()` | Integration test |
| 9 | **Performance**: Bytecode analysis of full `src/startd8/` completes in < 15s total | Benchmark test with `@pytest.mark.slow` |
| 10 | **No execution**: `mode="bytecode"` never imports or runs target code | Verified by design (`compile()` only) |
| 11 | **Graceful degradation**: Files that fail `compile()` produce manifests without `call_graph` | Error handling test |
| 12 | **Determinism**: Same source file always produces the same call graph | Determinism test (two runs compared) |
| 13 | **Backward compatibility**: Existing `1.2.0` consumers ignore new fields without error | Schema compatibility test |

---

## 15. Open Questions

| # | Question | Impact | Proposed Resolution |
|---|----------|--------|---------------------|
| 1 | Should `mode="static"` automatically include bytecode analysis, or require explicit `mode="bytecode"`? | API ergonomics vs. performance | Propose separate `mode="bytecode"` to keep `static` fast; users opt in |
| 2 | Should the call graph include calls to builtins (`len`, `print`, `isinstance`)? | Graph noise vs. completeness | Propose filtering stdlib builtins by default; `--include-builtins` flag for full graph |
| 3 | How should `super().method()` be resolved when the MRO requires runtime knowledge? | Resolution accuracy | Best-effort: resolve to the first base class that defines the method in the manifest |
| 4 | Should we support Python < 3.12 bytecode format (`CALL_FUNCTION` opcode)? | Portability vs. complexity | Propose CPython 3.12+ only; emit warning and skip for older versions |
| 5 | Should `call_graph_edges` at the file level deduplicate across elements? | Storage efficiency | Yes — deduplicate; individual element `calls` lists preserve per-element detail |
