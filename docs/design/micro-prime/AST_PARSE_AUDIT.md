# ast.parse() Audit — MicroPrime Module

> **Date:** 2026-03-24
> **Trigger:** Run-119 `ast.parse gate failed for src/shippingservice/quote.go: invalid syntax` — fifth Python leakage point found
> **Principle:** [Hayai Design Principle](../../design-princples/HAYAI_DESIGN_PRINCIPLE.md), REQ-MPL-105 (Python Leakage Audit)

---

## Summary

**54 `ast.parse()` references** across 10 files in `src/startd8/micro_prime/`. Of these:

| Classification | Count | Action |
|---------------|-------|--------|
| **Explicitly guarded** (language dispatch before call) | 16 | None needed |
| **Implicitly Python-only** (module/function is Python-specific) | 24 | None needed |
| **Error-safe fallback** (try/except, graceful degradation) | 8 | Low priority — works but suboptimal |
| **Silent quality loss** (Go paths lose features) | 4 | **FIX** — Go elements lose few-shot and skeleton context |
| **Fixed this session** | 1 | `prime_adapter.py:913` — was CRITICAL |

**No remaining crash-risk calls.** All unguarded calls have `try/except SyntaxError` fallbacks. The remaining issues are **quality degradation** — Go elements silently lose prompt context that Python elements get.

---

## FIXED (This Session)

| File:Line | Function | Was | Fix |
|-----------|----------|-----|-----|
| `prime_adapter.py:913` | Post-assembly write gate | `ast.parse(final_content)` on all files — Go files rejected | Language dispatch via `validate_syntax()` |

---

## NEEDS FIX (Quality Loss for Non-Python)

These calls silently degrade prompt quality for Go/Java/C#/Node elements. They don't crash (all have try/except), but they reject valid non-Python code as unusable.

### 1. `prompt_builder.py:581` — `_is_usable_example()`

```python
try:
    ast.parse(ce["code"])
except SyntaxError:
    return False  # ← Valid Go code rejected as unusable few-shot example
```

**Impact:** Go elements that complete successfully are never used as few-shot examples for subsequent elements in the same file. Python elements get few-shot learning; Go elements don't.

**Fix:** Accept `language_id` parameter. For non-Python, skip `ast.parse` validation (the code was already validated by `gofmt`/tree-sitter during generation).

### 2. `prompt_builder.py:785` — `_extract_element_context_from_skeleton()`

```python
try:
    tree = ast.parse(skeleton)  # ← Go skeleton fails here
except SyntaxError:
    return None, None, []  # ← Go elements lose skeleton context
```

**Impact:** Go elements lose the rendered skeleton context section in the prompt. The prompt falls back to `_fallback_indent()` which provides minimal context. Python elements get full skeleton context (surrounding functions, class structure).

**Fix:** For non-Python skeletons, use the language's parser instead of AST. Go has `go_parser.py:parse_go_source()`. Or: extract context via text-based heuristics (regex for `func` declarations) when AST is unavailable.

### 3. `prompt_builder.py:508` — `_lookup_init_context()`

```python
try:
    tree = ast.parse(skeleton)  # ← Go skeleton fails here
except SyntaxError:
    pass  # ← Falls through to manifest lookup
```

**Impact:** Minimal — `__init__` is Python-specific. Go doesn't have constructors in the same sense. The fallback to manifest lookup is appropriate.

**Fix:** Low priority. Add `if language_id == "python":` guard for clarity, but functional impact is negligible.

### 4. `engine.py:251` — `_attempt_splice_violation_repair()`

```python
try:
    ast.parse(result.code)  # ← Go code always fails here
except SyntaxError:
    # revert — repair is silently discarded for Go
```

**Impact:** Splice violation repairs that succeed for Go are discarded because the post-repair validation uses Python AST. The repair is correct but the validation rejects it.

**Fix:** Add language dispatch — use `validate_syntax()` for non-Python, `ast.parse()` for Python.

---

## SAFE (No Action Needed)

### Explicitly Guarded (16 calls)

| File | Lines | Guard |
|------|-------|-------|
| `repair.py` | 1277, 1285, 1375, 1382 | `_try_parse()` has `if language_id != "python"` dispatch |
| `structural_verify.py` | 86, 92, 259, 265 | `structural_verify()` and `ast_parse_valid()` dispatch by language |
| `structural_verify.py` | 156 | Inside `check_class_body_statements()` — Python ClassDef only |
| `engine.py` | 1020, 1344, 1353 | `_extract_function_body()` returns early for non-Python |
| `engine.py` | 1577 | `_validate_file_whole_result()` dispatches by language at line 1560 |
| `prime_adapter.py` | 917 | Fixed this session — `if _gate_lang_id == "python"` |

### Implicitly Python-Only (24 calls)

| File | Lines | Why Python-Only |
|------|-------|-----------------|
| `eval_scoring.py` | 175, 189, 250, 309, 314 | Entire module is Python corpus evaluation |
| `clause_mapper.py` | 330 | `FunctionBodyDecomposer` is Python AST-only |
| `skeleton_spec_extractor.py` | 186 | Parses Python skeleton specs |
| `decomposer.py` | 1085 | `ClassDecomposeStrategy` is Python-only |
| `splicer.py` | 440, 605, 676, 1036, 1084 | Inside Python splicer branch (Go/Java/C#/Node dispatched earlier) |
| `engine.py` | 617, 1314, 1440, 1523, 3618, 4648 | Python skeleton enrichment / reordering paths |
| `prime_adapter.py` | 149, 180, 224, 273, 1446 | Python fallback extraction/validation (`.py` guard) |
| `templates.py` | 1454, 1456 | Template validation — Python templates only |
| `repair.py` | 182, 516, 1242 | Python-specific repair steps |

---

## Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| **P0** | `prompt_builder.py:581` (few-shot rejection) | 15 min | Go elements get few-shot learning |
| **P0** | `prompt_builder.py:785` (skeleton context loss) | 30 min | Go elements get full skeleton context |
| **P1** | `engine.py:251` (splice repair validation) | 10 min | Splice repairs not silently discarded for Go |
| **P2** | `prompt_builder.py:508` (init context) | 5 min | Clarity only — functional impact negligible |
