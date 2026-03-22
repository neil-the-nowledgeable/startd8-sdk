# Implementation Plan: Java Semantic-to-Repair Bridge (REQ-KZ-JV-402)

> **Date:** 2026-03-22
> **Status:** PLANNED
> **Requirements:** REQ-KZ-JV-402a through REQ-KZ-JV-402e
> **Reference implementation:** C# semantic-to-repair bridge (REQ-KZ-CS-402a/b/c)

---

## Phase 1: Wiring + Placeholder Routing

**Goal:** Java files with `sql_injection_risk` produce correct `Diagnostic` objects and match a Java-specific routing entry. No actual repair — syntax validation only.

### 1.1 Language-Aware Bridge Dispatch (REQ-KZ-JV-402a.1)

**File:** `src/startd8/repair/semantic_bridge.py`

**Chosen approach:** Option 3 — per-language override dict (most backward-compatible).

**Changes:**
```python
# Add after _CATEGORY_TO_PATTERN (line 40):
_CATEGORY_TO_PATTERN_BY_LANG: dict[str, dict[str, str]] = {
    "java": {
        "sql_injection_risk": "java_sql_injection",
    },
    "csharp": {
        "sql_injection_risk": "csharp_sql_injection",
    },
}
```

**Modify `translate_to_diagnostics()` signature** to accept optional `language_id: str = ""`:
```python
def translate_to_diagnostics(
    semantic_issues: List[dict],
    file_path: str,
    language_id: str = "",
) -> List[Diagnostic]:
```

**Modify pattern resolution** (inside the `route_category is not None` branch, ~line 70):
```python
# Replace:
#   pattern = _CATEGORY_TO_PATTERN.get(category, category)
# With language-aware lookup:
lang_patterns = _CATEGORY_TO_PATTERN_BY_LANG.get(language_id, {})
pattern = lang_patterns.get(category, _CATEGORY_TO_PATTERN.get(category, category))
```

Wait — the current code doesn't use a pattern field in `Diagnostic`. Let me re-examine. The bridge creates `Diagnostic(category=route_category, file=..., message=...)` and the routing table matches on `(category, pattern)`. The pattern comes from `route_failures()` matching logic, not from the Diagnostic itself.

**Revised approach:** The bridge doesn't set a pattern — the routing table matches diagnostics by `category` and then the route's `pattern` field is an identifier. The `_CATEGORY_TO_PATTERN` dict is unused in `translate_to_diagnostics()` currently. Let me re-read.

Actually, looking more carefully at the bridge code: `_CATEGORY_TO_PATTERN` is defined but never referenced in `translate_to_diagnostics()`. It may be used elsewhere or be dead code. The actual routing dispatch in `route_failures()` matches `diagnostic.category` against the routing table's `category` column.

**Corrected analysis:** The routing table entry `("security", "csharp_sql_injection", ..., "csharp")` matches when:
- `diagnostic.category == "security"` (set by bridge via `_CATEGORY_TO_ROUTE`)
- `language_id == "csharp"` (passed by caller)

So for Java, we just need:
1. A new routing entry with `language_id="java"`
2. The bridge already produces `Diagnostic(category="security")` for `sql_injection_risk` — this is language-agnostic

**No bridge change needed for Phase 1.** The routing table's `language_id` column handles discrimination. `_CATEGORY_TO_PATTERN` appears to be unused infrastructure — verify during implementation.

### 1.2 Placeholder Route

**File:** `src/startd8/repair/routing.py`

**Add to `_ROUTING_TABLE`** (after line 92, in the Java routes section):
```python
("security", "java_sql_injection", ["java_syntax_validate"], "HIGH", "java"),
```

This is a placeholder — routes to syntax validation only. Phase 3 replaces the step list.

### 1.3 Tests

**File:** `tests/unit/repair/test_semantic_bridge.py` (extend)

**New test cases:**
- `test_translate_sql_injection_produces_security_diagnostic` — Verify `sql_injection_risk` issue → `Diagnostic(category="security")`
- `test_sql_injection_diagnostic_matches_java_route` — Verify the diagnostic matches the new Java routing entry when `language_id="java"` is passed to `route_failures()`

**File:** `tests/unit/repair/test_routing.py` (extend or create)

**New test cases:**
- `test_java_sql_injection_route_exists` — Verify `route_failures()` with `Diagnostic(category="security")` and `language_id="java"` returns a route containing `java_syntax_validate`
- `test_java_sql_injection_route_does_not_match_csharp` — Verify same diagnostic with `language_id="csharp"` does NOT match the Java route

**Acceptance criteria:**
- [ ] Java `.java` files with `sql_injection_risk` semantic issues produce `Diagnostic(category="security")` via bridge
- [ ] `route_failures()` with `language_id="java"` matches the new route
- [ ] `route_failures()` with `language_id="csharp"` continues to match `csharp_sql_injection` route (no regression)
- [ ] `_CATEGORY_TO_PATTERN` usage verified — dead code or used elsewhere (document finding)

---

## Phase 2: JavaImportSortStep (First Java Repair)

**Goal:** Java files with `wildcard_import` issues are repaired by expanding `import java.util.*;` to explicit imports.

### 2.1 Repair Step

**New file:** `src/startd8/repair/steps/java_import_sort.py`

```python
class JavaImportSortStep:
    """Expand wildcard Java imports to explicit imports (REQ-KZ-JV-402e Phase 2).

    Rewrites `import java.util.*;` to the explicit imports actually used
    in the source file (e.g., `import java.util.List;`).
    """
    name = "java_import_sort"

    def __call__(self, code: str, context: RepairContext, file_path: Path) -> RepairResult:
        ...
```

**Approach:** Regex-based. For each `import pkg.*;` statement:
1. Extract the package prefix (e.g., `java.util`)
2. Scan the source for unqualified class names matching known JDK classes in that package
3. Replace the wildcard import with explicit imports for each used class
4. If no used classes can be determined, leave the wildcard (conservative)

**Known JDK package map** (embedded dict for common packages):
- `java.util` → `List, Map, Set, HashMap, ArrayList, LinkedList, Optional, Collections, Arrays, Iterator, ...`
- `java.io` → `File, InputStream, OutputStream, BufferedReader, IOException, ...`
- `java.nio` → `Path, Paths, Files, ByteBuffer, ...`

### 2.2 Routing + Registration

**File:** `src/startd8/repair/routing.py`

**Add to `_ROUTING_TABLE`:**
```python
("semantic", "wildcard_import", ["java_import_sort", "java_syntax_validate"], "MEDIUM", "java"),
```

**Add to `_CANONICAL_ORDER`** (before `java_syntax_validate`):
```python
"java_import_sort",
```

**Add to `_STEP_FACTORIES`:**
```python
"java_import_sort": JavaImportSortStep,
```

**Add import** at top of file:
```python
from .steps import JavaImportSortStep
```

**File:** `src/startd8/repair/steps/__init__.py`

**Add re-export** for `JavaImportSortStep`.

### 2.3 Bridge Registration

**File:** `src/startd8/repair/semantic_bridge.py`

**Add to `_REPAIRABLE_CATEGORIES`:**
```python
"wildcard_import",
```

No `_CATEGORY_TO_ROUTE` entry needed — `wildcard_import` uses the default `"semantic"` category routing.

### 2.4 Orchestrator Dispatch

**File:** `src/startd8/repair/orchestrator.py`

**Update `_SEMANTIC_REPAIR_EXTENSIONS`:**
```python
_SEMANTIC_REPAIR_EXTENSIONS: frozenset[str] = frozenset({".py", ".cs", ".java"})
```

**Add `_repair_single_java_file()` function** (pattern: `_repair_single_csharp_file()` at line 935):
```python
def _repair_single_java_file(
    fpath: Path,
    config: RepairConfig,
    project_root: Path,
) -> Optional[Dict[str, object]]:
    """Detect, repair, and verify semantic issues in a single Java file (REQ-KZ-JV-402e)."""
    try:
        source = fpath.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("Cannot read %s for Java semantic repair: %s", fpath, exc)
        return None

    from startd8.validators.java_semantic_checks import run_java_semantic_checks
    issues = run_java_semantic_checks(source, file_path=str(fpath))
    repairable = [si for si in issues if si.check in config.semantic_repair_categories]
    if not repairable:
        return None

    found_count = len(repairable)
    semantic_dicts = [
        {"category": si.check, "severity": si.severity,
         "message": str(si.message)[:200], "line": getattr(si, "line", 0)}
        for si in repairable
    ]
    diagnostics = translate_to_diagnostics(semantic_dicts, str(fpath))
    if not diagnostics:
        return None

    # Route + repair
    augmented_categories = config.repairable_categories | frozenset({"security"})
    repair_config = RepairConfig(
        repair_enabled=config.repair_enabled,
        repairable_categories=augmented_categories,
        semantic_repair_categories=config.semantic_repair_categories,
        max_semantic_repairs_per_file=config.max_semantic_repairs_per_file,
        semantic_repair_circuit_breaker_threshold=config.semantic_repair_circuit_breaker_threshold,
        per_step_timeout_s=config.per_step_timeout_s,
        total_timeout_s=config.total_timeout_s,
    )
    route = route_failures(diagnostics, repair_config, language_id="java")
    if not route.steps:
        return {"found": found_count, "repaired": 0, "pre_score": None, "categories": []}

    steps = create_steps_from_route(route)
    if not steps:
        return {"found": found_count, "repaired": 0, "pre_score": None, "categories": []}

    context = RepairContext(diagnostics=diagnostics, config=repair_config, project_root=project_root)
    repaired_code = source
    for step in steps:
        result = step(repaired_code, context, fpath)
        if result.modified:
            repaired_code = result.code

    if repaired_code == source:
        return {"found": found_count, "repaired": 0, "pre_score": None, "categories": []}

    # Verify
    fpath.write_text(repaired_code, encoding="utf-8")
    post_issues = run_java_semantic_checks(repaired_code, file_path=str(fpath))
    post_repairable = [si for si in post_issues if si.check in config.semantic_repair_categories]

    repaired_count = found_count - len(post_repairable)
    if repaired_count > 0:
        logger.info("Java semantic repair: %s — %d/%d issues repaired", fpath.name, repaired_count, found_count)
        return {"found": found_count, "repaired": repaired_count, "remaining": len(post_repairable),
                "pre_score": None, "categories": list({d.category for d in diagnostics})}

    # Rollback
    fpath.write_text(source, encoding="utf-8")
    logger.debug("Java semantic repair rollback: %s — no issues resolved", fpath.name)
    return {"found": found_count, "repaired": 0, "pre_score": None, "categories": []}
```

**Update `run_semantic_repair()` dispatch** (~line 1107):
```python
if fpath.suffix == ".cs":
    file_result = _repair_single_csharp_file(fpath, config, project_root)
elif fpath.suffix == ".java":
    file_result = _repair_single_java_file(fpath, config, project_root)
else:
    file_result = _repair_single_file(...)
```

### 2.5 Tests

**New file:** `tests/unit/repair/test_java_import_sort.py`

| Test | Input | Expected |
|------|-------|----------|
| `test_wildcard_util_expansion` | `import java.util.*;` + uses `List`, `Map` | `import java.util.List;` + `import java.util.Map;` |
| `test_wildcard_io_expansion` | `import java.io.*;` + uses `File` | `import java.io.File;` |
| `test_no_change_explicit_imports` | `import java.util.List;` | No modification |
| `test_unknown_package_preserved` | `import com.custom.*;` (not in known map) | Wildcard preserved (conservative) |
| `test_multiple_wildcards` | Two wildcard imports | Both expanded |
| `test_static_import_unaffected` | `import static org.junit.Assert.*;` | Not modified (static wildcards are common) |

**Extend:** `tests/unit/repair/test_semantic_bridge.py`

- `test_wildcard_import_produces_semantic_diagnostic` — `wildcard_import` → `SemanticDiagnostic(category="semantic")`

**Acceptance criteria:**
- [ ] `import java.util.*;` with `List` usage → `import java.util.List;`
- [ ] Unknown packages preserved (no data loss)
- [ ] Static imports untouched
- [ ] `.java` files reach `_repair_single_java_file()` dispatch
- [ ] `wildcard_import` in `_REPAIRABLE_CATEGORIES`
- [ ] `RepairConfig.semantic_repair_categories` documents opt-in

---

## Phase 3: JavaSqlParameterizeStep

**Goal:** Deterministic rewrite of string-concatenated SQL in Java to `PreparedStatement` with parameterized queries.

### 3.1 Repair Step

**New file:** `src/startd8/repair/steps/java_sql_parameterize.py`

```python
class JavaSqlParameterizeStep:
    """Rewrite Java SQL string concatenation to PreparedStatement (REQ-KZ-JV-402e Phase 3).

    Detects patterns:
    1. "SELECT ... " + variable  (string concatenation)
    2. String.format("SELECT ... %s", variable)
    3. new StringBuilder("SELECT ...").append(variable)

    Rewrites to:
        PreparedStatement ps = conn.prepareStatement("SELECT ... WHERE col = ?");
        ps.setString(1, variable);
    """
    name = "java_sql_parameterize"
```

**Reference:** `src/startd8/repair/steps/sql_parameterize.py` (C# step).

**Patterns to handle:**

| Pattern | Example | Rewrite |
|---------|---------|---------|
| String concat (`+`) | `"SELECT * FROM t WHERE id=" + userId` | `"SELECT * FROM t WHERE id=?"` + `ps.setString(1, userId)` |
| `String.format()` | `String.format("SELECT * FROM t WHERE id=%s", userId)` | Same PreparedStatement pattern |
| `StringBuilder.append()` | `new StringBuilder("SELECT * FROM t WHERE id=").append(userId)` | Same PreparedStatement pattern |

**Conservative approach:** Only rewrite when the SQL keyword (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) is clearly present in the string literal. Don't rewrite generic string concatenation.

### 3.2 Routing Update

**File:** `src/startd8/repair/routing.py`

**Update existing Phase 1 placeholder route:**
```python
# Replace:
("security", "java_sql_injection", ["java_syntax_validate"], "HIGH", "java"),
# With:
("security", "java_sql_injection", ["java_sql_parameterize", "java_syntax_validate"], "HIGH", "java"),
```

**Add to `_CANONICAL_ORDER`** (before `java_syntax_validate`, after `sql_parameterize`):
```python
"java_sql_parameterize",
```

**Add to `_STEP_FACTORIES`:**
```python
"java_sql_parameterize": JavaSqlParameterizeStep,
```

### 3.3 Tests

**New file:** `tests/unit/repair/test_java_sql_parameterize.py`

| Test | Input Pattern | Expected |
|------|--------------|----------|
| `test_string_concat_select` | `"SELECT * FROM users WHERE id=" + userId` | PreparedStatement with `?` |
| `test_string_concat_insert` | `"INSERT INTO t VALUES('" + name + "')"` | PreparedStatement |
| `test_string_format_select` | `String.format("SELECT * FROM t WHERE id=%s", id)` | PreparedStatement |
| `test_stringbuilder_append` | `new StringBuilder("DELETE FROM t WHERE id=").append(id)` | PreparedStatement |
| `test_no_sql_keyword_skipped` | `"Hello " + name` (no SQL keyword) | No modification |
| `test_parameterized_already` | `conn.prepareStatement("SELECT * FROM t WHERE id=?")` | No modification |
| `test_multiple_concatenations` | `"SELECT * FROM t WHERE a=" + a + " AND b=" + b` | Two `?` placeholders, two `setString` calls |
| `test_nested_in_method` | SQL concat inside a method body | Correctly scoped rewrite |

**Acceptance criteria:**
- [ ] String concat `+` with SQL keywords → PreparedStatement
- [ ] `String.format()` with SQL keywords → PreparedStatement
- [ ] `StringBuilder.append()` with SQL keywords → PreparedStatement
- [ ] Non-SQL string concatenation untouched
- [ ] Already-parameterized queries untouched
- [ ] Phase 1 placeholder route updated to include `java_sql_parameterize`

---

## Dependency Graph

```
Phase 1 (wiring)
  ├── routing.py: placeholder route
  └── test_semantic_bridge.py: Java diagnostic tests
        │
Phase 2 (import sort) ──────────── Phase 3 (SQL parameterize)
  ├── java_import_sort.py            ├── java_sql_parameterize.py
  ├── orchestrator.py: dispatch      ├── routing.py: update placeholder
  ├── semantic_bridge.py: register   └── test_java_sql_parameterize.py
  ├── routing.py: new route
  └── test_java_import_sort.py
```

Phase 2 and Phase 3 are **independent** — they can be implemented in either order or in parallel. Both depend on Phase 1 wiring. Phase 2 is listed first because it adds the orchestrator dispatch (`_repair_single_java_file()`, `.java` extension) that Phase 3 also uses.

---

## Files Modified per Phase

| Phase | Modified | New | Tests |
|-------|----------|-----|-------|
| 1 | `routing.py` | — | `test_semantic_bridge.py` (extend), `test_routing.py` (extend/create) |
| 2 | `semantic_bridge.py`, `routing.py`, `orchestrator.py`, `repair/steps/__init__.py` | `repair/steps/java_import_sort.py` | `test_java_import_sort.py`, `test_semantic_bridge.py` (extend) |
| 3 | `routing.py` | `repair/steps/java_sql_parameterize.py` | `test_java_sql_parameterize.py` |

---

## Risk Register

| Risk | Phase | Mitigation |
|------|-------|------------|
| `_CATEGORY_TO_PATTERN` may be dead code | 1 | Verify usage before modifying; if dead, document and leave for cleanup |
| JDK class map incomplete for wildcard expansion | 2 | Conservative approach: unknown packages preserved. Map covers top-20 JDK packages. |
| SQL rewrite produces syntactically invalid Java | 3 | `java_syntax_validate` runs after `java_sql_parameterize` — invalid rewrites are caught |
| `RepairConfig.semantic_repair_categories` empty by default | 2, 3 | Callers (integration engine, scripts) must opt in. Document in config docstring. |
| Existing C# bridge tests may need `language_id` param added | 1 | Add `language_id=""` default — backward compatible |
