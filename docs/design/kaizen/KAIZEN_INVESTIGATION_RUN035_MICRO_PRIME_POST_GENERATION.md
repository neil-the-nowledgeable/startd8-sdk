# Kaizen Investigation: Run-035 PI-001 — Micro Prime Post-Generation Validation Failures

## Summary

PI-001 (emailservice Shared JSON Logger) fails on run-035 despite Ollama-whole successfully generating code. The prior investigation (run-033) added file-level Ollama-whole to fix the *generation* path. This investigation reveals four cascading failures in the **post-generation validation pipeline** that discard valid output and pass through broken output. All four are fixed.

**Prior investigation**: `KAIZEN_INVESTIGATION_RUN033_LOGGER_MICRO_PRIME.md`
**Run**: online-boutique run-035-20260311T1601 (PI-001 only, cloud escalation disabled)
**Outcome before fixes**: score=0.00 FAIL — "No files were integrated"

## Failure Chain (Chronological)

Each failure was masked by the one before it. Fixing one revealed the next.

### Stage 1: Size-Regression Guard (False Positive)

**Symptom**: `Micro Prime size-regression guard: src/emailservice/logger.py has 15 semantic lines vs 30 existing (50%) — escalating to fallback`

**Root cause**: The guard compared the `filled_skeleton` against the **entire existing file** at a fixed 55% threshold. When only 1 of 2 elements was successfully filled (e.g., Ollama-whole succeeded for `CustomJsonFormatter` but `getJSONLogger` remained a stub), the skeleton naturally had ~50% of the original content. The guard treated this as a regression, not a partial fill.

**Fix**: Scale the threshold by element fill rate. If 1 of 2 elements succeeded (`fill_rate=0.50`), the effective threshold drops to `0.55 × 0.50 = 0.275`. The 50% ratio clears that. When all elements succeed, the threshold stays at 0.55.

```python
# Before
if ratio < _SIZE_REGRESSION_THRESHOLD and existing_raw >= _MIN_EXISTING_LINES:

# After
total_el = len(file_result.element_results)
filled_el = sum(1 for er in file_result.element_results if er.success)
fill_rate = filled_el / total_el if total_el > 0 else 1.0
effective_threshold = _SIZE_REGRESSION_THRESHOLD * fill_rate
if ratio < effective_threshold and existing_raw >= _MIN_EXISTING_LINES:
```

### Stage 2: Assembly Defect Detection (False Positive)

**Symptom**: `assembly defect: remaining 'raise NotImplementedError' stubs — escalating to fallback`

**Root cause**: `_detect_assembly_defect()` used a blunt `"raise NotImplementedError" in content` string search. This false-positived when generated code legitimately used `raise NotImplementedError` in branches, abstract methods, or guard clauses — not as skeleton stubs.

**Fix**: Replaced string search with AST-based analysis. New `_is_stub_only_body()` function only flags functions/methods whose **entire body** (ignoring docstrings) is solely `raise NotImplementedError` or `raise NotImplementedError()`. Multi-statement bodies with `raise NotImplementedError` in a branch are considered legitimate implementations.

```python
# Before
if "raise NotImplementedError" in content:
    return "remaining `raise NotImplementedError` stubs"

# After — AST walk, only flag stub-only bodies
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if _is_stub_only_body(node.body):
            stub_names.append(node.name)
```

### Stage 3: Escalation-Disabled File Deletion (Logic Bug)

**Symptom**: `Cloud escalation disabled (escalation_enabled=False) — keeping 1 file(s) as partial local output` but `generated_files: []` and `effective_file_count: 0`.

**Root cause**: Two bugs:

1. **File deleted despite disabled escalation**: `_validate_and_finalize_files()` checked `self._fallback is not None` (always true — fallback exists even when escalation is disabled) to decide whether to delete the file and escalate. The file was removed from `generated_files`, unlinked from disk, and added to `escalated_files`. Phase 5b then logged "keeping partial output" — but the file was already gone.

2. **Effective count stays zero**: Files in `stub_escalated` were unconditionally routed to `incomplete_files`, keeping `effective_file_count = 0`. The `GenerationResult` returned `success=False` with an empty `generated_files` list.

**Fix**: Gate the delete-and-escalate branch on `self._config.escalation_enabled`. When disabled, keep the file on disk and in the generated files list (like the "no fallback" branch). Count `stub_escalated` files as effective when escalation is disabled — the partial output is the best we can produce.

```python
# Before
if self._fallback is not None:
    # Always deletes file and escalates

# After
if self._fallback is not None and self._config.escalation_enabled:
    # Only deletes file when escalation can actually proceed
```

### Stage 4: Structural Integrity Gap (Quality Hole)

**Symptom**: With Fixes 1-3 applied, the broken Ollama output would pass through as "successful" — it parses as valid Python and has no stub-only bodies.

**Root cause**: The only post-generation checks were `ast.parse()` (syntax) and `_detect_assembly_defect()` (stubs, markers, nested dups). There was **no validation that expected classes/functions actually exist** in the output.

The generated `logger.py` was structurally destroyed:

| Expected | Actual |
|----------|--------|
| `class CustomJsonFormatter(jsonlogger.JsonFormatter)` with `add_fields` method | No class — `add_fields` as standalone function |
| `from pythonjsonlogger import jsonlogger` | `from customjsonformatter import CustomJsonFormatter` (nonexistent module) |
| `record.created` for timestamp | `datetime.datetime.now().isoformat()` |
| `StreamHandler(sys.stdout)` | `StreamHandler()` (missing stdout) |
| `logging.INFO` | `logging.DEBUG` |

**Fix**: Added `_check_structural_integrity()` — verifies each successful element result has a corresponding AST node in the output:

- `CLASS` elements → `ClassDef` must exist at top level
- `FUNCTION` elements → `FunctionDef` must exist at top level
- `METHOD` elements → must be nested inside their `parent_class` `ClassDef`

This catches the broken file: `"structural integrity: missing class CustomJsonFormatter"`.

## Existing File Context

The target file `src/emailservice/logger.py` already contains a correct, complete 60-line implementation. The Micro Prime pipeline was attempting to regenerate it from the seed spec — producing a 22-line version that was both shorter and structurally broken.

```
Existing:  60 lines, class + method + function, correct imports, docstrings
Generated: 22 lines, no class def, standalone functions, wrong imports
```

The element registry (`.startd8/state/elements/`) was empty on disk — no validated elements had ever been persisted for this file because prior runs always failed validation (correctly).

## Files Changed

All changes in `src/startd8/micro_prime/prime_adapter.py`:

| Fix | Function/Location | Lines Changed |
|-----|-------------------|---------------|
| 1 | Size-regression guard in `_process_target_files()` | ~8 lines added (fill-rate scaling) |
| 2 | `_is_stub_only_body()` + `_detect_assembly_defect()` | ~35 lines rewritten (AST-based stub detection) |
| 3 | `_validate_and_finalize_files()` + effective count loop | ~6 lines changed (escalation_enabled gate) |
| 4 | `_check_structural_integrity()` + wired into validation | ~55 lines added (new function + 1-line callsite) |

## Test Coverage

- `TestSizeRegressionEscalation`: 3 tests — all pass (threshold now includes fill rate in log output)
- `TestDetectAssemblyDefect`: 7 tests — all pass (AST-based check handles all existing cases)
- Manual edge-case verification:
  - Branched `raise NotImplementedError` (legitimate) → no false positive
  - Stub-only with docstring → correctly detected
  - Multi-statement body with `raise NotImplementedError` → no false positive
  - Missing class, missing method, failed elements skipped → all correct
- Full adapter suite (69 tests): pass

## Lessons Learned

### L1: Guard conditions must match their escalation path

`_validate_and_finalize_files` used `self._fallback is not None` to gate file deletion, but `escalation_enabled=False` disabled the actual escalation in Phase 5b. The two conditions must be conjunctive: `fallback is not None AND escalation_enabled`. **Pattern**: When a guard decides to prepare for an action (delete file) that another guard decides to execute (call fallback), they must share the same predicate.

### L2: String-in checks on generated code are unreliable

`"raise NotImplementedError" in content` cannot distinguish skeleton stubs from legitimate code. Any check on generated content should use AST analysis, not string matching. **Anti-pattern**: Using string containment checks as quality gates on LLM-generated code.

### L3: Post-generation validation needs structural contracts

Syntax-valid does not mean structurally correct. When the input spec declares `class CustomJsonFormatter`, the output must contain a `ClassDef` node with that name — not an import. The forward manifest's element specs provide exactly the structural contract needed for validation. **Pattern**: Validate output structure against input contract, not just syntax.

### L4: Cascading validation failures mask root causes

Each of the four failures was masked by the one before it. Fixing the size-regression guard revealed the assembly defect false positive. Fixing that revealed the file-deletion bug. Fixing that revealed the quality hole. **Heuristic**: When investigating a pipeline failure, fix the first gate and re-run before concluding the root cause is found.

## Cross-Reference

- Prior investigation: `KAIZEN_INVESTIGATION_RUN033_LOGGER_MICRO_PRIME.md` (generation-path fix: file-level Ollama-whole)
- Regression reversal: `KAIZEN_MICRO_PRIME_REGRESSION_REVERSAL.md`
- Design principle: Mottainai — don't discard artifacts within a run
- SDK Lessons Learned: Leg 10 #40 (result-based module contract contamination), Leg 13 #29 (LLM complete-file overwrite)
