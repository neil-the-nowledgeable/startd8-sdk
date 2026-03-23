# Cross-Language Wiring Gap Implementation Plan

> **Version:** 1.0.0
> **Date:** 2026-03-23
> **Status:** PLAN
> **Parent:** [CROSS_LANGUAGE_WIRING_GAP_AUDIT.md](CROSS_LANGUAGE_WIRING_GAP_AUDIT.md)
> **Principle:** Fix wiring first, add features second. Each phase must be independently testable and deployable.

---

## Table of Contents

1. [Strategy](#1-strategy)
2. [Phase 0 — Quick Wins (< 1 hour total)](#2-phase-0--quick-wins)
3. [Phase 1 — Critical Wiring Fixes](#3-phase-1--critical-wiring-fixes)
4. [Phase 2 — Feedback Loop Completion](#4-phase-2--feedback-loop-completion)
5. [Phase 3 — Quality Signal Improvements](#5-phase-3--quality-signal-improvements)
6. [Phase 4 — Repair Route Expansion](#6-phase-4--repair-route-expansion)
7. [Dependency Graph](#7-dependency-graph)
8. [Verification Strategy](#8-verification-strategy)
9. [Risk Register](#9-risk-register)

---

## 1. Strategy

### Guiding Principles

1. **Wire before build** — Connect existing components before creating new ones. Most gaps are 1-5 line wiring fixes, not missing functionality.
2. **Detect before repair** — A check that fires with no repair is more valuable than a repair step with no check. Detection feeds Kaizen suggestions, which improve the next run's LLM prompt.
3. **All languages before one language** — Cross-cutting fixes (H-2 prompt injection, M-1 scoring) improve every language simultaneously.
4. **Test the wire, not the component** — Components are already unit-tested. New tests should verify the connection between components (e.g., "semantic check result appears in Kaizen suggestion output").

### Phase Sizing

| Phase | Gaps Fixed | Effort | Languages Improved | Quality Impact |
|-------|-----------|--------|-------------------|---------------|
| 0 | 5 | ~1 hour | All 5 | HIGH — unblocks feedback loops |
| 1 | 4 | ~2 hours | Python, Node.js | CRITICAL — fixes silent skips |
| 2 | 3 | ~3 hours | All 5, esp. Python/Go | HIGH — closes feedback loops |
| 3 | 4 | ~4 hours | All 5 | MEDIUM — improves signal quality |
| 4 | 2 | ~8 hours | Java, C# | MEDIUM — expands repair coverage |

---

## 2. Phase 0 — Quick Wins

**Goal:** Pure dictionary/mapping edits that unblock feedback loops. No logic changes, no new files. Each is independently deployable.

### P0-1: Add 4 Python `_SEMANTIC_CATEGORY_TO_SUGGESTION` Mappings

**Gap:** H-1
**File:** `src/startd8/contractors/prime_postmortem.py`
**Edit:** Add 4 entries to `_SEMANTIC_CATEGORY_TO_SUGGESTION` dict (~line 859-919):

```python
"duplicate_main_guard": "duplicate_definition_detected",
"duplicate_definition": "duplicate_definition_detected",
"bare_except_pass": "empty_catch_detected",  # closest existing suggestion
"phantom_dependency": "import_resolution_failure",  # closest existing suggestion
```

**Prerequisite:** Verify that `duplicate_definition_detected`, `empty_catch_detected`, and `import_resolution_failure` exist as keys in `CAUSE_TO_SUGGESTION`. If not, add corresponding entries.
**Test:** Unit test asserting `_SEMANTIC_CATEGORY_TO_SUGGESTION["duplicate_main_guard"]` resolves to a valid `CAUSE_TO_SUGGESTION` key.
**Effort:** ~10 min

### P0-2: Add `.ts/.tsx/.jsx` to Semantic Validation Dispatch

**Gap:** C-2
**File:** `src/startd8/forward_manifest_validator.py`
**Edit:** Extend the suffix check in `_validate_non_python_file()` (~line 655):

```python
# Before:
elif suffix in (".js", ".mjs", ".cjs"):
# After:
elif suffix in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"):
```

**Test:** Unit test with a `.ts` file containing `var x = 1;` → verify `var_usage` appears in `result.semantic_issues`.
**Effort:** ~5 min

### P0-3: Add `.mjs/.cjs` to Exemplar `_ext_to_language()`

**Gap:** M-5
**File:** `src/startd8/exemplars/models.py`
**Edit:** Add mappings in `_ext_to_language()` (~line 134-144):

```python
".mjs": "nodejs",
".cjs": "nodejs",
```

**Test:** Unit test asserting `_ext_to_language(".mjs") == "nodejs"`.
**Effort:** ~5 min

### P0-4: Fix Python Repair Routing Language Tags

**Gap:** H-5
**File:** `src/startd8/repair/routing.py`
**Edit:** Change Python routes from `language=None` to `language="python"` (~lines 103-110):

```python
# Before:
("syntax", "syntax_error", [...], "HIGH", None),
# After:
("syntax", "syntax_error", [...], "HIGH", "python"),
```

Apply to all ~8 Python routes.
**Test:** Unit test calling `route_failures(language_id="python")` with a syntax error → verify route matches.
**Effort:** ~10 min

### P0-5: Wire Package.json Semantic Checks into `_validate_package_json()`

**Gap:** C-4
**File:** `src/startd8/forward_manifest_validator.py`
**Edit:** In `_validate_package_json()` (~line 1198), after structural validation, call the package.json semantic checks and append to `result.semantic_issues`:

```python
from startd8.validators.nodejs_semantic_checks import run_nodejs_semantic_checks
# After existing validation:
for sem_issue in run_nodejs_semantic_checks(content, file_path=str(abs_path)):
    result.semantic_issues.append({
        "category": sem_issue.check,
        "severity": sem_issue.severity,
        "message": sem_issue.message,
    })
```

**Note:** `run_nodejs_semantic_checks()` already has package.json-specific checks that only fire for package.json files. This is safe to call.
**Test:** Unit test with a package.json missing `"type"` field → verify `missing_module_type` in `result.semantic_issues`.
**Effort:** ~15 min

---

## 3. Phase 1 — Critical Wiring Fixes

**Goal:** Fix the 2 critical silent-skip gaps where entire categories of files receive no validation.

### P1-1: Wire Python Semantic Checks into Integration Engine

**Gap:** C-1
**File:** `src/startd8/contractors/integration_engine.py`
**Edit:** Add a Python branch to `_run_semantic_checks()` (~line 1687-1936).

**Design decision:** Use `validate_disk_compliance()` (the L1-L10 suite) rather than the orphaned `run_semantic_checks()`. This is consistent with how Python validation works in the postmortem and provides richer detection.

```python
# In _run_semantic_checks(), add Python branch:
if fpath.suffix == ".py":
    try:
        compliance = validate_disk_compliance(str(fpath), project_root)
        for issue in compliance.semantic_issues or []:
            issues_found.append({
                "file": str(fpath),
                "category": issue.get("category", "unknown"),
                "severity": issue.get("severity", "warning"),
                "message": issue.get("message", ""),
            })
            logger.warning(
                "Semantic issue in %s: [%s] %s",
                fpath.name,
                issue.get("category"),
                issue.get("message"),
            )
        if compliance.semantic_issues:
            compliance_results[str(fpath)] = {
                "semantic_issues": compliance.semantic_issues,
                "ast_valid": compliance.ast_valid,
                "stubs_remaining": compliance.stubs_remaining,
            }
    except Exception:
        logger.warning("Python semantic check failed for %s", fpath.name, exc_info=True)
```

**Guard:** Wrap in try/except to match the error handling pattern used by C#/Java/Go/Node.js branches.
**Test:** Integration test with a Python file containing a bare `except: pass` → verify it appears in `compliance_results`.
**Effort:** ~30 min

### P1-2: Resolve Orphaned Python Semantic Checks

**Gap:** C-3
**File:** `src/startd8/validators/semantic_checks.py`

**Design decision:** Rather than wiring the orphaned `run_semantic_checks()` as a separate code path, evaluate whether the 4 checks should be migrated INTO `validate_disk_compliance()`:

| Check | Already covered by L1-L10? | Action |
|-------|:---:|--------|
| `check_duplicate_main_guards()` | NO — L1-L10 checks `cross_scope_duplicate` but not duplicate `if __name__` guards | MIGRATE → add as L11 check in `validate_disk_compliance()` |
| `check_duplicate_definitions()` | PARTIAL — `_detect_cross_scope_duplicates()` covers this | VERIFY coverage, then DEPRECATE if redundant |
| `check_bare_except_pass()` | NO — not in L1-L10 | MIGRATE → add as L12 check |
| `check_phantom_dependencies()` | PARTIAL — `_validate_import_resolution()` covers broader import validation | VERIFY coverage, then DEPRECATE if redundant |

**Step 1:** Grep for `cross_scope_duplicate` and `import_resolution` to confirm coverage overlap.
**Step 2:** For non-overlapping checks (duplicate_main_guard, bare_except_pass), add to `validate_disk_compliance()` as new layers.
**Step 3:** Add deprecation comment to `run_semantic_checks()` pointing to the new locations.
**Test:** Unit tests for the new L11/L12 checks.
**Effort:** ~45 min

### P1-3: Verify and Fix `self.` False Positive in Node.js Contamination Check

**Gap:** Documented in KAIZEN_NODEJS_REQUIREMENTS.md QW-1
**File:** `src/startd8/validators/nodejs_semantic_checks.py`
**Edit:** In `_check_python_contamination()`, change from whole-file substring match to line-by-line with line-start anchor for `self.`:

```python
# Before:
if fp in source:
# After (for "self." fingerprint only):
for line in source.splitlines():
    if re.match(r'^\s*self\.', line):
        # found
```

**Test:** Regression test with `"help yourself."` in a JS string → must NOT trigger.
**Effort:** ~15 min

---

## 4. Phase 2 — Feedback Loop Completion

**Goal:** Close the loop between detection → prompt injection. Ensure that every detected issue improves the next run.

### P2-1: Inject Language `coding_standards` into LLM Prompts

**Gap:** H-2
**Files:** `src/startd8/implementation_engine/spec_builder.py`, `src/startd8/contractors/prime_contractor.py`

This is the highest-ROI fix across all phases. Every language profile already has rich `coding_standards` — they just never reach the LLM.

**Edit in `prime_contractor.py`** (~`_build_generation_context()`):
```python
# After language profile is resolved:
if self._language_profile:
    gen_context["coding_standards"] = self._language_profile.coding_standards
    gen_context["language_role"] = (
        f"You are an expert {self._language_profile.display_name} developer. "
        f"Follow {self._language_profile.display_name} idioms and conventions."
    )
```

**Edit in `spec_builder.py`** (~`build_spec_prompt()`):
```python
# Extract and inject into spec:
coding_standards = context.get("coding_standards", "")
if coding_standards:
    spec_sections.append(f"## Coding Standards\n\n{coding_standards}")
```

**Test:** Integration test verifying that a Node.js spec prompt contains "Use `const` instead of `var`" or similar language-specific guidance.
**Effort:** ~45 min

### P2-2: Fix MicroPrime Language Profile Threading

**Gap:** H-4
**File:** `src/startd8/contractors/prime_contractor.py`
**Edit:** In `_apply_language_profile_to_engine()` (~line 3885-3923), add:

```python
# After updating self._engine:
if hasattr(self, "code_generator") and self.code_generator is not None:
    self.code_generator._language_profile = profile
```

**Test:** Unit test verifying `code_generator._language_profile` is not `None` after `_apply_language_profile_to_engine()` is called.
**Effort:** ~15 min

### P2-3: Add Missing `CAUSE_TO_SUGGESTION` Entries for Python

**Gap:** H-1 (companion to P0-1)
**File:** `src/startd8/contractors/prime_postmortem.py`

If P0-1 maps Python categories to existing suggestion keys but some keys don't exist in `CAUSE_TO_SUGGESTION`, add the missing entries:

```python
"duplicate_main_guard_detected": {
    "hint": "Files should have at most one `if __name__ == '__main__':` guard. "
            "Multiple guards indicate copy-paste from different sources. Keep only the "
            "bottom-most guard that serves as the entry point.",
    "phase": "implement",
},
"bare_except_pass_detected": {
    "hint": "Never use bare `except: pass` — this silently swallows all errors including "
            "KeyboardInterrupt and SystemExit. Use specific exception types: "
            "`except (ValueError, TypeError):` or at minimum `except Exception:`.",
    "phase": "implement",
},
```

**Test:** Unit test that `generate_kaizen_suggestions()` produces a suggestion when given a feature with `bare_except_pass` semantic issue.
**Effort:** ~20 min

---

## 5. Phase 3 — Quality Signal Improvements

**Goal:** Improve scoring accuracy and fix remaining detection gaps.

### P3-1: Add C# `block_scoped_namespace` Semantic Check

**Gap:** M-4
**File:** `src/startd8/validators/csharp_semantic_checks.py`
**Edit:** Add `_check_block_scoped_namespace()`:

```python
def _check_block_scoped_namespace(source: str) -> list[SemanticIssue]:
    """Detect C# 9 block-scoped namespaces (obsolete pattern in .NET 6+)."""
    issues = []
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("namespace ") and stripped.endswith("{"):
            issues.append(SemanticIssue(
                check="block_scoped_namespace",
                severity="warning",
                message=f"Block-scoped namespace at line {i}. Use file-scoped namespace (C# 10+): "
                        f"remove the braces and add semicolon.",
                line=i,
            ))
    return issues
```

**Wire into `run_csharp_semantic_checks()`** to include the new check.
**Test:** Unit test with `namespace Foo {` → verify `block_scoped_namespace` issue.
**Effort:** ~30 min

### P3-2: Add Language-Aware Quality Score Dispatch Mechanism

**Gap:** M-1, M-2
**File:** `src/startd8/forward_manifest_validator.py`

**Design:** Add `language_id` parameter to `compute_disk_quality_score()` with language-specific severity overrides:

```python
_LANGUAGE_SEVERITY_WEIGHTS = {
    "go": {"error": 0.4, "warning": 0.15},      # Go errors are more critical
    "csharp": {"error": 0.35, "warning": 0.1},
    "java": {"error": 0.35, "warning": 0.1},
    "nodejs": {"error": 0.3, "warning": 0.1},
    "python": {"error": 0.3, "warning": 0.1},    # default
}

def compute_disk_quality_score(result, language_id=None):
    weights = _LANGUAGE_SEVERITY_WEIGHTS.get(language_id or "python",
              _LANGUAGE_SEVERITY_WEIGHTS["python"])
    # Use weights["error"] and weights["warning"] instead of hardcoded 0.3/0.1
```

**Thread language_id through call sites:**
1. `prime_postmortem.py:_evaluate_disk_quality()` — infer from target file extension
2. `integration_engine.py` — use resolved language profile

**Test:** Unit test verifying Go `unchecked_error` penalizes 0.4 while Python error penalizes 0.3.
**Effort:** ~1 hour

### P3-3: Add Per-Language Semantic Repair Configuration

**Gap:** M-6
**File:** `src/startd8/repair/config.py`
**Edit:** Replace flat `semantic_repair_categories` with language-aware mapping:

```python
semantic_repair_categories_by_language: dict[str, frozenset[str]] = field(
    default_factory=lambda: {
        "python": frozenset({"import_resolution", "method_resolution", "discarded_return", "duplicate_main_guard"}),
        "go": frozenset({"unchecked_error", "dot_import", "python_contamination"}),
        "nodejs": frozenset({"var_usage", "duplicate_require", "python_contamination"}),
        "java": frozenset({"wildcard_import", "java_sql_injection"}),
        "csharp": frozenset({"csharp_sql_injection", "csharp_convention_error"}),
    }
)
```

**Backward compat:** Keep `semantic_repair_categories` as a fallback for unknown languages.
**Test:** Unit test verifying `get_repairable_categories("go")` returns Go-specific set.
**Effort:** ~45 min

### P3-4: Fix Python Semantic Category Terminology Alignment

**Gap:** M-3
**File:** `src/startd8/validators/semantic_checks.py`, `src/startd8/contractors/prime_postmortem.py`

**Option A (preferred):** Add alias mappings in `_SEMANTIC_CATEGORY_TO_SUGGESTION`:
```python
# Aliases for terminology alignment
"cross_scope_duplicate": "duplicate_definition_detected",  # validate_disk_compliance() term
"duplicate_definition": "duplicate_definition_detected",   # semantic_checks.py term
```

**Option B:** Standardize all category names to match `validate_disk_compliance()` output. Higher effort, higher risk.

**Decision:** Option A — additive, no refactoring risk.
**Test:** Unit test verifying both `cross_scope_duplicate` and `duplicate_definition` resolve to the same suggestion.
**Effort:** ~15 min

---

## 6. Phase 4 — Repair Route Expansion

**Goal:** Add repair routes and steps for the 11 orphaned Java/C# semantic checks. This phase creates NEW repair steps (higher effort, higher risk).

### P4-1: Java Repair Steps (6 checks)

**Priority ordering by ROI:**

| Priority | Check | Approach | Effort |
|----------|-------|----------|--------|
| P1 | `missing_override` | Regex: insert `@Override\n` before method declarations that override superclass | ~1 hour |
| P2 | `raw_type_usage` | Regex: `List ` → `List<Object>`, `Map ` → `Map<String, Object>` (conservative) | ~1 hour |
| P3 | `package_filepath_mismatch` | Parse `package` declaration, rewrite to match directory structure | ~1.5 hours |
| P4 | `duplicate_method` | Remove second occurrence, keep first (simple line removal) | ~45 min |
| P5 | `invalid_java_version` | Advisory only — no repair (version choice is architectural) | N/A |
| P6 | `interface_file_contains_class` | Advisory only — no repair (requires file split, too complex for regex) | N/A |

**Implementation pattern for each step:**
1. Create `src/startd8/repair/steps/{step_name}.py` following existing step pattern
2. Register in `_STEP_FACTORIES` in `routing.py`
3. Add routing entry in `_ROUTING_TABLE` with `language="java"`
4. Add to `_CANONICAL_ORDER` (text transform before validation)
5. Unit test for the step
6. Wire test verifying route → step dispatch

**Effort:** ~4 hours for P1-P4 (P5-P6 are intentionally advisory)

### P4-2: C# Repair Steps (5 checks)

**Priority ordering by ROI:**

| Priority | Check | Approach | Effort |
|----------|-------|----------|--------|
| P1 | `missing_nullable_in_csproj` | XML edit: insert `<Nullable>enable</Nullable>` in `<PropertyGroup>` | ~45 min |
| P2 | `missing_access_modifier` | Regex: prefix `class Foo` → `public class Foo` (default to `public`) | ~1 hour |
| P3 | `namespace_filepath_mismatch` | Rewrite `namespace` declaration to match directory structure | ~1 hour |
| P4 | `console_writeline_in_service` | Advisory only — requires project-specific logger (ILogger<T>) | N/A |
| P5 | `missing_async_await` | Advisory only — removing `async` may break interfaces | N/A |

**Effort:** ~3 hours for P1-P3 (P4-P5 are intentionally advisory)

---

## 7. Dependency Graph

```
Phase 0 (all independent, can be done in parallel):
  P0-1 ─── Python suggestion mappings
  P0-2 ─── TS/JSX dispatch
  P0-3 ─── Exemplar extensions
  P0-4 ─── Python routing lang tags
  P0-5 ─── Package.json semantic collection

Phase 1 (depends on Phase 0 completion):
  P1-1 ─── Python integration engine ← (benefits from P0-1 mappings)
  P1-2 ─── Orphaned check migration ← (must decide before P1-1 which checks to use)
  P1-3 ─── Node.js self. false positive ← (independent)

Phase 2 (depends on Phase 1 completion):
  P2-1 ─── Coding standards injection ← (independent, highest ROI)
  P2-2 ─── MicroPrime profile fix ← (independent)
  P2-3 ─── CAUSE_TO_SUGGESTION entries ← (depends on P0-1 mapping decisions)

Phase 3 (depends on Phase 2 completion):
  P3-1 ─── C# block_scoped check ← (independent)
  P3-2 ─── Language-aware scoring ← (depends on M-1 design decision)
  P3-3 ─── Per-language repair config ← (independent, but inform Phase 4)
  P3-4 ─── Category terminology alignment ← (depends on P1-2 migration decisions)

Phase 4 (depends on Phase 3 completion):
  P4-1 ─── Java repair steps ← (depends on P3-3 config)
  P4-2 ─── C# repair steps ← (depends on P3-3 config)
```

**Critical path:** P0-1 → P1-2 → P2-3 → P3-4 (Python feedback loop end-to-end)
**Highest ROI path:** P0-2 + P2-1 (TypeScript coverage + coding standards injection)

---

## 8. Verification Strategy

### Per-Phase Verification

| Phase | Verification Method | Success Criteria |
|-------|-------------------|------------------|
| 0 | `pytest tests/unit/contractors/test_prime_postmortem.py -v` + new mapping tests | All 4 Python categories resolve to suggestions; `.ts` files get semantic checks; `.mjs` exemplars classified |
| 1 | `pytest tests/unit/contractors/ tests/unit/validators/ -v` + integration test with Python file through INTEGRATE | Python semantic issues appear in `compliance_results`; orphaned checks migrated or wired |
| 2 | Run Prime Contractor on a Node.js seed → inspect spec prompt for coding standards | Spec prompt contains language-specific guidance; MicroPrime profile not None |
| 3 | `pytest tests/unit/validators/test_csharp_semantic_checks.py -v` + scoring unit tests | `block_scoped_namespace` detected; Go error penalty = 0.4 |
| 4 | `pytest tests/unit/repair/ -v` + repair route integration tests | New repair steps registered and dispatch correctly |

### End-to-End Verification

After all phases, run Prime Contractor on the same Online Boutique Node.js seed (run-107 repro):
1. Verify TS files get semantic checks (if any `.ts` targets exist)
2. Verify spec prompt contains Node.js coding standards
3. Verify Kaizen suggestions fire for `var_usage` (if detected)
4. Verify disk quality score reflects language-appropriate penalties

### Regression Safety

- Run full test suite after each phase: `pytest --tb=short -q`
- Check test count doesn't decrease (current baseline: ~4000+ tests)
- Verify no existing Kaizen suggestion mappings are broken by new entries

---

## 9. Risk Register

| Risk | Phase | Likelihood | Impact | Mitigation |
|------|-------|:---:|:---:|------------|
| `validate_disk_compliance()` is too slow for integration engine (Python L1-L10 per file) | P1-1 | Medium | Medium | Add timing guard; log if >2s per file; skip optional layers |
| New `CAUSE_TO_SUGGESTION` entries reference non-existent keys | P0-1, P2-3 | Low | High | Verify key existence before adding mapping; add unit test |
| `coding_standards` injection inflates prompt size past budget | P2-1 | Medium | Medium | Truncate to first 500 chars; or inject only in P0 tier (never truncated) |
| Block-scoped namespace detection false positives on `namespace X {` in comments | P3-1 | Low | Low | Only match non-comment lines; strip `//` and `/* */` before matching |
| Java `@Override` insertion before wrong method (constructor, static) | P4-1 | Medium | Medium | Only insert before methods with `@Override`-eligible signatures; validate with `javac` after |
| Breaking existing Python repair routes by changing `None` → `"python"` | P0-4 | Low | High | Verify all `route_failures()` call sites pass `language_id`; add fallback for `None` |
| Category terminology alignment (P3-4) breaks existing suggestion lookups | P3-4 | Medium | Medium | Use additive aliases (Option A), not renames |
