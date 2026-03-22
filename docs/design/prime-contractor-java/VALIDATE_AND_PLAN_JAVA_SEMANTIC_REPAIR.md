# Prompt: Validate & Plan Java Semantic Repair (REQ-KZ-JV-402)

> Provide this prompt alongside `KAIZEN_JAVA_REQUIREMENTS.md` to validate the requirements and produce an implementation plan.

---

## Context

The StartD8 SDK has a multi-language code generation pipeline (Prime Contractor) with a Kaizen quality system. The C# language already has a working semantic-to-repair bridge:

- **Detection:** `csharp_semantic_checks.py` finds issues (e.g., `sql_injection_risk`)
- **Collection:** Integration engine stores results in `compliance_results` dict
- **Bridge:** `semantic_bridge.py` translates issues → `Diagnostic` objects via `_REPAIRABLE_CATEGORIES`
- **Routing:** `routing.py` matches diagnostics to repair steps by `(category, pattern, language_id)`
- **Repair:** `SqlParameterizeStep` rewrites interpolated SQL → parameterized queries
- **Verification:** Re-runs semantic checks post-repair to confirm fix
- **Orchestrator:** `run_semantic_repair()` dispatches `.cs` files via `_repair_single_csharp_file()`

Java has the same detection layer (`java_semantic_checks.py`, 9 check functions producing 10 category strings) and collection (compliance_results — implemented 2026-03-22), but no repair steps or dispatch. REQ-KZ-JV-402 defines the convention for wiring Java into this pipeline.

## Task

### Part 1: Validate Requirements

Read REQ-KZ-JV-402 (Section 5, after REQ-KZ-JV-400.3) and validate against the codebase:

1. **Category inventory accuracy** — Confirm all 10 category strings from 9 check functions in `java_semantic_checks.py` are listed in REQ-KZ-JV-402b. Note: `_check_package_filepath_alignment()` emits both `package_filepath_mismatch` and `package_case_mismatch`. Check `check=` field values match exactly.
2. **Classification correctness** — For each category classified as "Repairable" or "Potentially repairable," verify the claimed repair technique is feasible:
   - `sql_injection_risk`: Is `_REPAIRABLE_CATEGORIES` in `semantic_bridge.py` already shared? Does the bridge produce a `Diagnostic(category="security")` that would match a Java routing entry? **Known gap:** `_CATEGORY_TO_PATTERN` currently maps unconditionally to `"csharp_sql_injection"` — there is no language dispatch in the bridge. See REQ-KZ-JV-402a.1 for the design options.
   - `wildcard_import`: `google-java-format --fix-imports-only` is a real command that sorts and removes unused imports, but does **not** expand `*` wildcards to explicit imports. The repair step must implement expansion independently.
3. **Compliance results wiring** — Confirm REQ-KZ-JV-402c (IMPLEMENTED) by reading the Java block in `integration_engine.py:_run_semantic_checks()` and verifying results are stored in `compliance_results`.
4. **Routing gap** — Confirm there is NO existing `("security", "java_sql_injection", ..., "java")` route in `routing.py`. The `sql_injection_risk` category routes through `_CATEGORY_TO_ROUTE["sql_injection_risk"] = "security"` which maps to pattern `csharp_sql_injection` — this won't match a `language_id="java"` filter.
5. **RepairConfig opt-in gap** — Confirm `RepairConfig.semantic_repair_categories` defaults to `frozenset()` (empty) in `repair/config.py`. Without adding Java categories to this set, new routes silently fail to activate even if wiring is complete.

### Part 2: Create Implementation Plan

Produce a phased implementation plan for REQ-KZ-JV-402. For each work item:
- File(s) to modify
- What to add/change (specific function names, routing entries, etc.)
- Test file(s) to create or extend
- Acceptance criteria from the requirements

**Phase 1 deliverables (wiring + placeholder routing — no actual repairs):**
- Implement language-aware bridge dispatch (REQ-KZ-JV-402a.1): extend `_CATEGORY_TO_PATTERN` or `translate_to_diagnostics()` so Java files produce `java_sql_injection` pattern, C# files continue to produce `csharp_sql_injection`
- Add `("security", "java_sql_injection", ["java_syntax_validate"], "HIGH", "java")` **placeholder route** in `routing.py` (syntax validation only — the actual parameterize step is added in Phase 3)
- Tests: unit test confirming Java `.java` files with `sql_injection_risk` produce correct `Diagnostic` objects. Extend `tests/unit/repair/test_semantic_bridge.py` with Java cases.

**Phase 2 deliverables (first Java repair step):**
- `JavaImportSortStep` in `repair/steps/java_import_sort.py` — regex-based wildcard expansion (not `google-java-format`)
- Route `("semantic", "wildcard_import", ["java_import_sort", "java_syntax_validate"], "MEDIUM", "java")`
- Add `wildcard_import` to `_REPAIRABLE_CATEGORIES` in `semantic_bridge.py`
- Add `.java` to `_SEMANTIC_REPAIR_EXTENSIONS` in `orchestrator.py`
- Add `_repair_single_java_file()` dispatch function in `orchestrator.py`
- Add `"wildcard_import"` to `RepairConfig.semantic_repair_categories` default
- Add `"java_import_sort"` to `_CANONICAL_ORDER` and `_STEP_FACTORIES` in `routing.py`
- Tests: `.java` file with `import java.util.*;` → verify explicit imports after repair. Extend `tests/unit/repair/test_semantic_bridge.py`.

**Phase 3 deliverables (SQL parameterize):**
- `JavaSqlParameterizeStep` in `repair/steps/java_sql_parameterize.py`
- Update Phase 1 placeholder route: `java_sql_injection` → `["java_sql_parameterize", "java_syntax_validate"]`
- Add `"sql_injection_risk"` to `RepairConfig.semantic_repair_categories` default
- Add `"java_sql_parameterize"` to `_CANONICAL_ORDER` and `_STEP_FACTORIES` in `routing.py`
- Tests: string concatenation (`+`), `String.format()`, `StringBuilder.append()` patterns. Reference: `tests/unit/repair/test_sql_parameterize.py` (C# pattern).

## Key Files to Read

| File | Purpose |
|------|---------|
| `src/startd8/validators/java_semantic_checks.py` | 9 check functions, 10 category strings — verify names |
| `src/startd8/repair/semantic_bridge.py` | `_REPAIRABLE_CATEGORIES`, `_CATEGORY_TO_ROUTE`, `_CATEGORY_TO_PATTERN`, `translate_to_diagnostics()` |
| `src/startd8/repair/routing.py` | `_ROUTING_TABLE`, `_STEP_FACTORIES`, `_CANONICAL_ORDER`, `route_failures()` |
| `src/startd8/repair/orchestrator.py` | `_SEMANTIC_REPAIR_EXTENSIONS`, `_repair_single_csharp_file()` (reference), `run_semantic_repair()` |
| `src/startd8/repair/config.py` | `RepairConfig` — `semantic_repair_categories` (empty default!), `repairable_categories` |
| `src/startd8/repair/steps/sql_parameterize.py` | C# SQL repair step (reference for Java Phase 3) |
| `src/startd8/contractors/integration_engine.py` | `_run_semantic_checks()` Java block, `_attempt_semantic_repair()` |
| `tests/unit/repair/test_semantic_bridge.py` | Existing bridge tests (extend with Java cases) |
| `tests/unit/repair/test_sql_parameterize.py` | C# SQL repair tests (reference pattern) |
| `docs/design/prime-contractor-java/KAIZEN_JAVA_REQUIREMENTS.md` | REQ-KZ-JV-402 requirements |

## Validated Findings (from code review 2026-03-22)

These findings have been verified against the codebase and incorporated into the updated requirements:

1. **Module docstring fixed** — `java_semantic_checks.py` line 3 now says "Nine checks (10 category strings)".
2. **10th category added** — `package_case_mismatch` added to REQ-KZ-JV-402b table.
3. **Bridge dispatch is new work** — `_CATEGORY_TO_PATTERN` is language-agnostic. REQ-KZ-JV-402a.1 added with 3 design options.
4. **Phase 1 is placeholder only** — Route sends to `java_syntax_validate` only, not an actual repair. Clarified in REQ-KZ-JV-402e.
5. **`google-java-format` limitation** — Does not expand wildcards. Phase 2 step must implement expansion independently.
6. **RepairConfig opt-in required** — REQ-KZ-JV-402d added to document the `semantic_repair_categories` empty-default gap.
