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

Java has the same detection layer (`java_semantic_checks.py`, 9 checks) and collection (compliance_results — just implemented), but no repair steps or dispatch. REQ-KZ-JV-402 defines the convention for wiring Java into this pipeline.

## Task

### Part 1: Validate Requirements

Read REQ-KZ-JV-402 (Section 5, after REQ-KZ-JV-400.3) and validate against the codebase:

1. **Category inventory accuracy** — Confirm all 9 categories in `java_semantic_checks.py` are listed in REQ-KZ-JV-402b. Check category string names match exactly (`check=` field values).
2. **Classification correctness** — For each category classified as "Repairable" or "Potentially repairable," verify the claimed repair technique is feasible:
   - `sql_injection_risk`: Is `_REPAIRABLE_CATEGORIES` in `semantic_bridge.py` already shared? Does the bridge produce a `Diagnostic(category="security")` that would match a Java routing entry?
   - `wildcard_import`: Does `google-java-format --fix-imports-only` actually resolve wildcard imports? Is it a real command?
3. **Compliance results wiring** — Confirm REQ-KZ-JV-402c (IMPLEMENTED) by reading the Java block in `integration_engine.py:_run_semantic_checks()` and verifying results are stored in `compliance_results`.
4. **Routing gap** — Confirm there is NO existing `("security", "java_sql_injection", ..., "java")` route in `routing.py`. The `sql_injection_risk` category routes through `_CATEGORY_TO_ROUTE["sql_injection_risk"] = "security"` which maps to `csharp_sql_injection` — this won't match a `language_id="java"` filter. Flag this as a design issue.
5. **Phase dependencies** — Verify Phase 1 → 2 → 3 ordering is correct. Can Phase 2 (wildcard import) and Phase 3 (SQL parameterize) be implemented independently?

### Part 2: Create Implementation Plan

Produce a phased implementation plan for REQ-KZ-JV-402. For each work item:
- File(s) to modify
- What to add/change (specific function names, routing entries, etc.)
- Test file(s) to create
- Acceptance criteria from the requirements

**Phase 1 deliverables:**
- Add `.java` to `_SEMANTIC_REPAIR_EXTENSIONS` in `orchestrator.py`
- Add `_repair_single_java_file()` function (pattern: `_repair_single_csharp_file()`)
- Add `("security", "java_sql_injection", ["java_syntax_validate"], "HIGH", "java")` route in `routing.py`
- Update `_CATEGORY_TO_PATTERN` in `semantic_bridge.py` so `sql_injection_risk` maps to `java_sql_injection` when file extension is `.java` (or use a language-agnostic pattern name)
- Tests: unit test confirming `.java` files with `sql_injection_risk` reach dispatch

**Phase 2 deliverables:**
- `JavaImportSortStep` in `repair/steps/java_import_sort.py`
- Route `("semantic", "wildcard_import", ["java_import_sort", "java_syntax_validate"], "MEDIUM", "java")`
- Add `wildcard_import` to `_REPAIRABLE_CATEGORIES`
- Tests: `.java` file with `import java.util.*;` → verify explicit imports after repair

**Phase 3 deliverables:**
- `JavaSqlParameterizeStep` in `repair/steps/java_sql_parameterize.py`
- Route update: `java_sql_injection` → `["java_sql_parameterize", "java_syntax_validate"]`
- Tests: string concatenation (`+`), `String.format()`, `StringBuilder.append()` patterns

## Key Files to Read

| File | Purpose |
|------|---------|
| `src/startd8/validators/java_semantic_checks.py` | 9 semantic checks — verify category names |
| `src/startd8/repair/semantic_bridge.py` | `_REPAIRABLE_CATEGORIES`, `_CATEGORY_TO_ROUTE`, `translate_to_diagnostics()` |
| `src/startd8/repair/routing.py` | `_ROUTING_TABLE`, `_STEP_FACTORIES`, `route_failures()` |
| `src/startd8/repair/orchestrator.py` | `_SEMANTIC_REPAIR_EXTENSIONS`, `_repair_single_csharp_file()` (reference pattern), `run_semantic_repair()` |
| `src/startd8/repair/steps/sql_parameterize.py` | C# SQL repair step (reference for Java Phase 3) |
| `src/startd8/contractors/integration_engine.py` | `_run_semantic_checks()` Java block, `_attempt_semantic_repair()` |
| `src/startd8/repair/config.py` | `RepairConfig` — `semantic_repair_categories`, `repairable_categories` |
| `tests/unit/repair/test_semantic_bridge.py` | Existing bridge tests (add Java cases) |
| `tests/unit/repair/test_sql_parameterize.py` | C# SQL repair tests (reference pattern) |
| `docs/design/prime-contractor-java/KAIZEN_JAVA_REQUIREMENTS.md` | REQ-KZ-JV-402 requirements |
