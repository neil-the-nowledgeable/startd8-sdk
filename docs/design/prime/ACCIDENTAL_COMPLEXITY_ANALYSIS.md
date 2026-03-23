# Accidental Complexity Analysis — Prime Contractor Pipeline Code

> **Date:** 2026-03-23
> **Scope:** Code areas targeted by the [wiring gap implementation plan](CROSS_LANGUAGE_WIRING_GAP_PLAN.md)
> **Method:** Parallel agent analysis of 4 modules: integration_engine.py, forward_manifest_validator.py, prime_postmortem.py, routing.py + spec_builder.py + prime_contractor.py
> **Purpose:** Identify opportunistic refactoring during the wiring gap fixes — reduce accidental complexity while the files are already open

---

## Executive Summary

The code that implements the Prime Contractor's quality pipeline has grown through incremental language additions (Python → Go → Java → C# → Node.js). Each language was added as a self-contained copy of the previous language's code with names changed, creating a pattern of **accidental complexity through cloning**. The essential logic (detect → collect → score → suggest → repair) is simple, but it's buried under ~500 lines of boilerplate that repeats identically across 4-5 language branches.

### Headline Numbers

| File | Current Lines | Accidental Lines | Reduction Opportunity |
|------|:---:|:---:|:---:|
| `integration_engine.py` (`_run_semantic_checks`) | 251 | ~162 | 45% |
| `forward_manifest_validator.py` (validators) | ~600 | ~200 | 33% |
| `prime_postmortem.py` (suggestion pipeline) | ~460 | ~120 | 26% |
| `repair/routing.py` (table + dispatch) | ~200 | ~30 | 15% |
| **Total** | **~1,511** | **~512** | **34%** |

---

## 1. integration_engine.py — `_run_semantic_checks()` (Lines 1687-1937)

### The Pattern

Each of 4 language branches (Java, Go, C#, Node.js) repeats **36 lines of identical boilerplate**:

```python
elif fpath.suffix == ".java":        # 1. Extension check (1 line)
    try:                             # 2. Try wrapper (1 line)
        from X import Y             # 3. Language-specific import (2 lines)
        source = fpath.read_text()   # 4. Read file (1 line)
        issues = Y(source, ...)      # 5. Call check function (1 line)
        for issue in issues:         # 6. Log each issue (4 lines)
            logger.warning(...)
        if issues:                   # 7. Build compliance dict (20 lines)
            rel = str(fpath.relative_to(self.project_root))
            compliance_results[rel] = {
                "ast_valid": True,
                "stubs_remaining": 0,           # ← hardcoded
                "duplicate_definitions": 0,      # ← hardcoded
                "import_completeness": 1.0,      # ← hardcoded
                "contract_compliance": 1.0,      # ← hardcoded
                "semantic_issues": [...]
            }
    except Exception as exc:         # 8. Error handler (3 lines)
        logger.debug(...)
```

Steps 1-8 are byte-for-byte identical across Java, Go, Node.js. Only the import path and logger prefix string change. C# adds 38 extra lines for `.csproj` search + using coverage check.

### Accidental Complexity

| What | Lines | Why It's Accidental |
|------|:---:|---------------------|
| 4× repeated try/except/log/collect pattern | 144 | Same structure, different import path |
| 4× hardcoded compliance dict construction | 80 | Same shape, same stub values |
| 5 if/elif extension checks | 5 | `_EXT_TO_LANGUAGE` already exists in `routing.py` |
| Python early-return on ImportError | 3 | Inconsistent with other branches (log and continue) |
| C# inline `.csproj` directory walk | 28 | Should be extracted to a utility |

### Essential Form

```python
def _run_semantic_checks(self, files, project_root):
    compliance_results = {}
    for fpath in files:
        lang = _EXT_TO_LANGUAGE.get(fpath.suffix.lower())
        if lang is None:
            continue
        issues = self._run_checks_for_language(fpath, lang)
        if issues:
            compliance_results[_relpath(fpath, project_root)] = (
                _make_compliance_dict(semantic_issues=issues)
            )
    return compliance_results
```

**Savings: ~162 lines (45% of method)**

### Opportunistic Refactoring Recommendation

Since we're already adding the Python branch (C-1 fix), extract the parameterized helper at the same time. This turns the C-1 fix from "add a 5th copy of the 36-line block" into "add Python to the language dispatch table." Net code change: negative (adding a feature while removing code).

---

## 2. forward_manifest_validator.py — Dispatch + Scoring

### 2a. `_validate_non_python_file()` Dispatch (Lines 609-672)

**14 if/elif branches** dispatch by file extension or filename. Each branch calls a validator function with slightly different parameter signatures.

| Accidental Pattern | Count | Lines |
|-------------------|:---:|:---:|
| Extension branches that could be a lookup table | 14 | 63 |
| Inconsistent parameter passing (`file_path` passed to some, not others) | ~10 | scattered |
| `sibling_imports` plumbed through all 14 branches but used by 1 | 1 param | everywhere |

**Essential form:** Two dispatch tables (filename → validator, extension → validator) with a single loop:

```python
_FILENAME_VALIDATORS = {"go.mod": _validate_go_mod, "package.json": _validate_package_json, ...}
_EXTENSION_VALIDATORS = {".go": _validate_go_file, ".java": _validate_java_file, ...}
```

### 2b. Language Validator Boilerplate (4 validators)

`_validate_go_file()`, `_validate_java_file()`, `_validate_csharp_file()`, `_validate_js_file()` share >50% identical structure:

| Shared Step | Lines per Validator |
|-------------|:---:|
| Empty file check | 3-4 |
| Python fingerprint guard | 4-6 |
| Brace balance check | 16 |
| Semantic check import + collect | 10-12 |
| **Total shared** | **33-38** |
| **Total per validator** | **70-120** |
| **Boilerplate ratio** | **42-54%** |

The brace balance check is **byte-for-byte identical** across Go, Java, and C#. It should be a shared `_check_brace_balance(content)` helper.

### 2c. `compute_disk_quality_score()` (Lines 461-503)

| Accidental Complexity | Impact |
|---|---|
| Hardcoded weights (0.4, 0.2, 0.2, 0.2) | Cannot dispatch by language |
| No `language_id` parameter | Scoring is permanently language-blind |
| Semantic penalty calculation duplicated in `_emit_semantic_observability()` (lines 2052-2061) | Same error/warning counting logic in 2 places |
| `DiskComplianceResult` fields set/mutated across 14 different validators with no builder | Shape inconsistency risk |

**Essential form:** Extract `_compute_semantic_penalty()` helper, add `language_id` parameter with severity weight lookup table. Since we're already adding language-aware scoring (P3-2), this is a natural time to do the extraction.

---

## 3. prime_postmortem.py — Suggestion Pipeline

### 3a. Two-Dict Indirection (Lines 859-919 + 396-853)

The suggestion pipeline uses a **two-level lookup** that adds zero value:

```
semantic_issue.category
  → _SEMANTIC_CATEGORY_TO_SUGGESTION[category]     # 43 entries, 60 lines
    → CAUSE_TO_SUGGESTION[suggestion_key]            # 66 entries, 457 lines
      → {"hint": "...", "phase": "..."}
```

Most mappings follow a trivial convention: `category → "${category}_detected"`. The 43-entry dict could be replaced by a 5-line resolver function:

```python
def _resolve_suggestion(category):
    if category in CAUSE_TO_SUGGESTION:
        return CAUSE_TO_SUGGESTION[category]
    if f"{category}_detected" in CAUSE_TO_SUGGESTION:
        return CAUSE_TO_SUGGESTION[f"{category}_detected"]
    return None
```

**Savings: 60 lines, eliminates the dict that is the source of H-1 (missing Python mappings)**

This is the highest-ROI refactoring target because the `_SEMANTIC_CATEGORY_TO_SUGGESTION` dict is exactly where wiring gaps hide. If the dict is eliminated in favor of a naming convention, new checks automatically get suggestions as long as they follow the `{category}_detected` pattern in `CAUSE_TO_SUGGESTION`.

### 3b. Triplicated Suggestion Construction (Lines 938-989, 1036-1075)

Three nearly-identical blocks build suggestion dicts with the same 9-field structure:

| Block | Source | Lines |
|-------|--------|:---:|
| Root cause patterns | `cross_feature_patterns` | 16 |
| Semantic issues | `semantic_category_features` | 30 |
| Observability issues | `category_services` | 14 |

All three follow: iterate → threshold check → lookup template → construct dict → append.

**Essential form:** Single `_build_suggestion()` helper called 3 times. **Savings: ~30 lines.**

### 3c. Duplicate Hint Text (Lines 443-493)

4 hints appear twice — once as a base cause and once as a `repeated_escalation:` variant:

| Cause | `repeated_escalation:` Variant | Same Hint? |
|-------|------|:---:|
| `ollama_empty_response` | `repeated_escalation:empty_response` | YES |
| `repair_exhausted` | `repeated_escalation:repair_exhausted` | YES |
| `ollama_circuit_breaker` | `repeated_escalation:circuit_breaker` | YES |
| `ollama_timeout` | `repeated_escalation:timeout` | YES |

**Essential form:** 4 base entries + escalation prefix injection at lookup time. **Savings: ~30 lines + 4 entries.**

### 3d. Dead Code (Line 985)

```python
"config_key": template.get("confidence", "prompt_hints")
              if isinstance(template.get("confidence"), str) else "prompt_hints"
```

`confidence` is stored as a float (0.75, 0.95, 1.0) or absent — never a string. The `isinstance(..., str)` branch is unreachable. `config_key` is always `"prompt_hints"`.

---

## 4. repair/routing.py + prime_contractor.py

### 4a. Routing Table Structure (Lines 101-138)

5-element tuples force positional unpacking. A `NamedTuple` or `dataclass` would make the table self-documenting:

```python
# Current:
("syntax", "syntax_error", ["fence_strip", "ast_validate"], "HIGH", "python")
# Which is which? Position-dependent.

# Essential:
RoutingEntry(category="syntax", pattern="syntax_error",
             steps=["fence_strip", "ast_validate"], severity="HIGH", language="python")
```

### 4b. 3 Unused Step Factories (Lines 141-179)

`dedup_require`, `semantic_method_fix`, and `var_to_const` are registered in `_STEP_FACTORIES` but referenced by zero routing entries. These are either planned steps that were registered prematurely or steps that lost their routes during refactoring.

### 4c. Language Profile Threading in prime_contractor.py

**The fundamental timing bug:** `_build_generation_context()` both resolves the language profile AND calls the drafter. The profile is resolved mid-function (~line 3887), but the drafter is called earlier (lines 2410-2414, 3095-3099). So `language_role` and `coding_standards` are added to `gen_context` AFTER the drafter already consumed it.

```
Current timeline:
  _build_generation_context() called
    ├─ drafter called with gen_context  ← coding_standards is None here
    ├─ language_profile resolved        ← SET HERE
    └─ coding_standards added to gen_context  ← TOO LATE for drafter
  _apply_language_profile_to_engine()   ← updates engine but not code_generator
```

**Essential fix:** Resolve language profile BEFORE `_build_generation_context()`. This is a prerequisite for REQ-KZ-005 (coding_standards injection) — if the profile isn't available when the spec is built, the standards can't be injected.

### 4d. Extension→Language Mapping Scattered Across 5 Files

| Location | Mapping | Format |
|----------|---------|--------|
| `repair/routing.py:_EXT_TO_LANGUAGE` | 10 extensions | dict |
| `languages/resolution.py` | per-profile `source_extensions` | property |
| `integration_engine.py:_run_semantic_checks` | if/elif suffix checks | inline |
| `forward_manifest_validator.py:_validate_non_python_file` | 14 if/elif branches | inline |
| `exemplars/models.py:_ext_to_language` | 10 extensions | function |

All 5 encode the same information. The `LanguageRegistry` already has all registered profiles with their `source_extensions`. A single `LanguageRegistry.get_extension_map()` call would replace all 5.

---

## 5. Root Cause: Clone-and-Modify Development Pattern

All 4 modules exhibit the same root cause: **each language was added by cloning the previous language's code block and changing names**. This is a natural development pattern (working code → copy → adapt), but without subsequent consolidation, it produces:

1. **Boilerplate multiplication** — N languages × M lines per language = N×M total lines, when M-K lines are language-independent
2. **Wiring gap fragility** — Adding a new check requires edits in N places. Missing any one of the N creates a silent wiring gap (exactly the pattern found in the audit)
3. **Inconsistency accumulation** — Each clone drifts slightly (C# adds `.csproj` search, Python uses different error handling, Node.js adds extra extensions). These drifts make it harder to reason about the pipeline as a whole

The fix is not to rewrite everything, but to **extract the shared pattern once** and parameterize the language-specific parts. This is textbook refactoring: "extract method, introduce parameter."

---

## 6. Opportunistic Refactoring Matrix

These refactorings are recommended as companions to the wiring gap fixes, since the files are already being modified:

| Plan Phase | Fix Being Made | Opportunistic Refactoring | Effort | Net Code Impact |
|:---:|---|---|:---:|:---:|
| P0-2 | Add `.ts/.tsx/.jsx` to dispatch | Replace 14 if/elif with dispatch table | +30 min | -30 lines |
| P0-5 | Wire package.json semantics | Normalize all validator parameter signatures | +15 min | -10 lines |
| P1-1 | Add Python to integration engine | Extract `_run_checks_for_language()` helper + `_make_compliance_dict()` | +45 min | -130 lines |
| P2-1 | Inject coding_standards | Fix language profile timing (resolve before context build) | +30 min | net 0 (restructure) |
| P2-3 | Add CAUSE_TO_SUGGESTION entries | Replace `_SEMANTIC_CATEGORY_TO_SUGGESTION` with naming convention resolver | +30 min | -55 lines |
| P3-2 | Language-aware scoring | Extract `_compute_semantic_penalty()` helper | +15 min | -15 lines |

**Total additional effort: ~2.75 hours**
**Net code reduction: ~240 lines**
**New wiring gaps prevented by table-driven dispatch: future languages get automatic coverage**

---

## 7. Decision Framework: Refactor Now vs Later

| Criterion | Refactor Now | Defer |
|-----------|:---:|:---:|
| File already open for wiring fix? | Yes → refactor | No → defer |
| Refactoring prevents future wiring gaps? | Yes → refactor | No → defer |
| Refactoring changes function signatures? | Caution → ensure tests cover | — |
| Refactoring touches >1 call site? | Scope carefully | — |
| Refactoring is purely internal (no API change)? | Yes → safe to refactor | — |

**Recommended approach:** Bundle each refactoring with its corresponding plan phase fix. The wiring fix is the functional change (verified by tests); the refactoring is the structural improvement (verified by existing tests continuing to pass). Ship together as "fix + simplify."

**Anti-pattern to avoid:** Refactoring first, then implementing the fix. This creates two rounds of risk. Instead: fix first (minimal change, tests pass), then simplify (structural change, same tests still pass).
