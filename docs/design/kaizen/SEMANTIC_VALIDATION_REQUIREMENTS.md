# Semantic Validation Requirements

**Date:** 2026-03-15
**Status:** Draft
**Author:** Human + Agent collaboration
**Domain:** Post-Generation Quality Gates — Semantic Layer
**Derived From:** [SEMANTIC_VALIDATION_GAP_ANALYSIS.md](SEMANTIC_VALIDATION_GAP_ANALYSIS.md) (runs 045–055 comparative analysis)

---

## 1. Purpose

Define requirements for semantic validation checks that close the gap between syntactic PASS (17/17, score 1.0) and actual code quality. The current postmortem pipeline validates only structural properties (AST parse, stub count, module-level duplicates, import presence). Code that parses correctly but imports non-existent modules, calls wrong APIs, or has structural logic errors passes all gates.

These requirements target the `semantic_issues` field in `DiskComplianceResult`, which exists but is populated only for non-Python files. For Python files, the field is always empty. Each requirement specifies a check that populates `semantic_issues` entries with structured severity, enabling the existing scoring formula (`-0.15` per issue) to degrade scores for semantically broken code.

### Scoring Integration

The postmortem scoring formula in `compute_disk_quality_score()` already penalizes semantic issues:

```
composite = (contract_compliance × 0.4) + (import_completeness × 0.2)
          + (stub_penalty × 0.2) + (semantic_penalty × 0.2)

semantic_penalty = max(0, 1.0 - (len(semantic_issues) × 0.15))
```

A file with 4+ semantic issues drops the semantic component to 0, reducing the composite by 0.2. A file with 7+ issues (currently impossible since semantic_issues is always empty for Python) degrades past the PASS threshold. **No scoring formula changes are required** — only population of the `semantic_issues` list.

---

## 2. Scope

### In Scope

- Semantic checks for Python files in `validate_disk_compliance()`
- Semantic checks for non-Python files (`_validate_dockerfile()`, `_validate_requirements_file()`)
- Structured `semantic_issues` entries with severity and category
- Integration with golden seed `import_map` (REQ-GS-302) when available
- Reuse of existing infrastructure (`_STDLIB_MODULES`, `_PROTOBUF_STUB_RE`, `import_to_pypi`)

### Out of Scope

- Changes to the scoring formula weights or thresholds
- Runtime validation (actually executing generated code)
- LLM-based semantic review (the REVIEW phase handles this)
- Cross-file validation requiring multi-file context (L7 template consistency — deferred)
- Changes to context resolution or prompt construction

---

## 3. Definitions

| Term | Definition |
|------|-----------|
| **Semantic issue** | A code defect that passes AST parsing but would fail at import time, runtime, or produces incorrect behavior |
| **Phantom import** | An `import X` or `from X import Y` where X does not resolve to any known module (stdlib, PyPI, local, proto) |
| **Import map** | A per-task mapping of import names to their source classification (`stdlib`, `pip:<pkg>`, `proto:<file>`, `local:<file>`) — from golden seed REQ-GS-302 |
| **Cross-scope duplicate** | The same function/class name defined both at module level and inside a nested scope (class method body, inner function) |
| **Factory function** | A function matching `create_*` or `*_factory` naming patterns expected to return a constructed object |
| **Expression statement** | An `ast.Expr` node containing a function call whose return value is discarded |

---

## 4. Requirements

### REQ-SV-100: Semantic Issue Data Model

**REQ-SV-101: Structured Semantic Issue Entry**

Each entry in `semantic_issues` must be a dict with:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `category` | str | Yes | Validation layer identifier (e.g., `import_resolution`, `cross_scope_duplicate`, `dockerfile_digest`) |
| `severity` | str | Yes | `error` (would fail at runtime) or `warning` (likely defect but may work in some contexts) |
| `message` | str | Yes | Human-readable description of the issue |
| `line` | int | No | Source line number where the issue was detected |
| `symbol` | str | No | The offending symbol name (import name, function name, etc.) |

**Rationale:** Structured entries enable downstream consumers (Kaizen, dashboards) to aggregate by category and severity. The existing `-0.15` penalty applies regardless of severity; a future refinement could weight errors more heavily than warnings.

**REQ-SV-102: Backward Compatibility**

The `semantic_issues` field type remains `List[Any]`. Existing non-Python validation entries (strings) continue to work. New entries are dicts per REQ-SV-101. Consumers must handle both formats.

---

### REQ-SV-200: Layer 1 — Import Resolution Validation (P0)

**Catches:** 4 of 11 bugs from run-050 (phantom imports, wrong module paths, repair-mangled imports)

**REQ-SV-201: Import Resolution Check**

For every `import X` and `from X.Y import Z` statement in a Python file, verify that the top-level module name resolves to one of:

1. **stdlib** — member of `sys.stdlib_module_names` (reuse `_STDLIB_MODULES` from `requirements_generator.py`)
2. **PyPI package** — the import's top-level module maps to a package listed in a sibling `requirements.in` file via `import_to_pypi()` reverse lookup (reuse `package_aliases.py`)
3. **Local sibling** — a `.py` file with matching stem exists in the same service directory, or a directory package with matching name exists
4. **Protobuf stub** — matches `_PROTOBUF_STUB_RE` pattern (`*_pb2`, `*_pb2_grpc`)
5. **Golden seed import map** — if the seed provides an `import_map` for this task (REQ-GS-302), the import must appear in the map with a valid classification

An import that resolves to none of these sources produces a `semantic_issues` entry:
```python
{"category": "import_resolution", "severity": "error",
 "message": f"Unresolvable import: '{module_name}' is not stdlib, not in requirements.in, not a local module, and not a protobuf stub",
 "line": node.lineno, "symbol": module_name}
```

**REQ-SV-202: Sibling File Discovery**

The validator must accept an optional `sibling_files: List[str]` parameter (list of file paths in the same service directory). When provided, local module resolution checks file stems against this list. When absent, the validator scans `project_root / parent_dir` for `.py` files.

**Rationale:** During Prime Contractor postmortem, the generated files for a task are known. Passing them explicitly avoids filesystem scans and enables validation of files before they're written to disk.

**REQ-SV-203: Import Map Validation Mode**

When a golden seed `import_map` is provided for the task:
- Every import in the generated code must appear in the import map
- Imports NOT in the map are flagged as `error` (the map is authoritative)
- Imports IN the map but classified as `proto:*` or `local:*` are additionally checked against sibling files/proto stubs
- This is stricter than REQ-SV-201: the import map is a closed-world specification

**REQ-SV-204: Repair-Mangled Import Detection**

Flag imports where the module path contains a service directory name as a prefix (e.g., `from emailservice.email_server import X`). In microservice architectures, services don't import from each other's internal modules — they communicate via proto stubs or HTTP. This heuristic catches the most common repair-pipeline artifact.

Pattern: `from <service_name>.<internal_module> import ...` where `<service_name>` matches a sibling directory name.

Severity: `warning` (legitimate in monorepo structures, error in microservice architectures).

---

### REQ-SV-300: Layer 2 — Cross-Scope Duplicate Detection (P1)

**Catches:** 1 of 11 bugs (duplicate `talkToGemini` at nested + module scope)

**REQ-SV-301: Cross-Scope Duplicate Check**

Extend duplicate detection to walk all AST scopes. When the same function or class name appears at both module level and inside a nested scope (function body, class body), flag it:

```python
{"category": "cross_scope_duplicate", "severity": "warning",
 "message": f"'{name}' defined at module level (line {module_line}) and inside '{parent_name}' (line {nested_line})",
 "line": nested_line, "symbol": name}
```

**REQ-SV-302: Scope-Aware Collection**

Collect `(name, scope_type, line, parent_name)` tuples where `scope_type` is one of `module`, `function`, `class`, `method`. A name with entries at both `module` scope and any other scope is flagged.

**Exception:** Names defined in a class body and also at module level are common (e.g., `__init__` helper functions). Only flag when the module-level definition has the same parameter signature as the nested definition (indicating accidental copy, not intentional shadowing).

---

### REQ-SV-400: Layer 3 — Dockerfile Digest Validation (P1)

**Catches:** 2 of 11 bugs (truncated SHA256 digests in 3 Dockerfiles)

**REQ-SV-401: SHA256 Digest Length Check**

In `_validate_dockerfile()`, for every `FROM` line containing `@sha256:`, verify the digest is exactly 64 hexadecimal characters:

```python
for match in re.findall(r'@sha256:([0-9a-fA-F]+)', line):
    if len(match) != 64:
        result.semantic_issues.append({
            "category": "dockerfile_digest",
            "severity": "error",
            "message": f"Truncated SHA256 digest: {len(match)} chars (expected 64)",
            "line": lineno,
            "symbol": f"sha256:{match[:16]}..."
        })
```

**REQ-SV-402: Digest Format Validation**

Also flag `@sha256:` followed by non-hex characters or an empty string. These indicate LLM hallucination of the digest format.

---

### REQ-SV-500: Layer 4 — Factory Return Value Check (P2)

**Catches:** 1 of 11 bugs (missing `return app` in `create_app()`)

**REQ-SV-501: Factory Function Return Check**

For functions matching naming patterns `create_*`, `make_*`, `build_*`, or `*_factory`:

1. Walk the function body for `ast.Return` nodes
2. If no `Return` node has a non-None `value`, flag:
   ```python
   {"category": "factory_return", "severity": "error",
    "message": f"Factory function '{name}' has no return statement with a value",
    "line": node.lineno, "symbol": name}
   ```

**REQ-SV-502: Configurable Factory Patterns**

The factory function name patterns must be configurable (list of regex patterns), not hardcoded. Default patterns: `^create_`, `^make_`, `^build_`, `_factory$`.

**Rationale:** Different projects have different naming conventions for constructor/factory functions.

---

### REQ-SV-600: Layer 5 — Requirements-to-Import Cross-Check (P2)

**Catches:** 1 of 11 bugs (`customjsonformatter` listed in requirements.in but never imported)

**REQ-SV-601: Orphan Dependency Detection**

For each package in a `requirements.in` file, verify that at least one sibling `.py` file imports a module that maps to that package (via `import_to_pypi` reverse lookup).

Packages with no matching import produce:
```python
{"category": "orphan_dependency", "severity": "warning",
 "message": f"Package '{package}' in requirements.in is not imported by any sibling Python file",
 "line": lineno, "symbol": package}
```

**REQ-SV-602: Cross-File Context Requirement**

This check requires access to sibling Python files' import lists. The validator must accept an optional `sibling_imports: Dict[str, Set[str]]` parameter mapping sibling file paths to their import sets. When absent, the check is skipped (not failed).

**REQ-SV-603: Known Non-Import Packages**

Maintain an allowlist of packages that are legitimately in `requirements.in` without direct imports (e.g., `setuptools`, `wheel`, pytest plugins). Default allowlist: `setuptools`, `wheel`, `pip`, `gunicorn`, `uvicorn`, `gevent`.

---

### REQ-SV-700: Layer 6 — Expression Statement Lint (P3)

**Catches:** 1 of 11 bugs (discarded `os.getenv()` results)

**REQ-SV-701: Discarded Return Value Detection**

Flag `ast.Expr` nodes containing `ast.Call` where the callee matches a configurable set of functions known to return values that should not be discarded:

```python
PURE_FUNCTIONS = {
    "os.getenv", "os.environ.get",
    "dict.get", "list.pop", "str.format", "str.replace",
    "pathlib.Path.resolve", "pathlib.Path.parent",
}
```

Entry:
```python
{"category": "discarded_return", "severity": "warning",
 "message": f"Return value of '{callee}' is discarded",
 "line": node.lineno, "symbol": callee}
```

**REQ-SV-702: Allowlist for Side-Effect Calls**

Do NOT flag calls to functions known to be used for side effects even though they return values (e.g., `list.append`, `dict.update`, `print`, `logging.*`). The pure function list (REQ-SV-701) is opt-in, not opt-out.

---

### REQ-SV-800: Validation Pipeline Integration

**REQ-SV-801: Entry Point**

All semantic checks are invoked from `validate_disk_compliance()`. The function signature gains optional parameters:

```python
def validate_disk_compliance(
    file_path: str,
    project_root: str,
    manifest: Optional[ForwardManifest] = None,
    *,
    sibling_files: Optional[List[str]] = None,
    sibling_imports: Optional[Dict[str, Set[str]]] = None,
    import_map: Optional[Dict[str, str]] = None,
    factory_patterns: Optional[List[str]] = None,
) -> DiskComplianceResult:
```

All new parameters are keyword-only and optional. When absent, the corresponding semantic check either uses defaults or is skipped. This preserves backward compatibility with all existing call sites.

**REQ-SV-802: Check Ordering**

Semantic checks execute after syntactic checks (AST parse, stubs, duplicates, contract compliance) and only when `ast_valid` is True. A file that fails AST parsing cannot have meaningful semantic analysis.

**REQ-SV-803: Performance Budget**

All semantic checks combined must complete within 100ms per file for files under 1,000 lines. No network calls, no subprocess invocations, no disk I/O beyond the sibling file scan in REQ-SV-202.

**REQ-SV-804: Postmortem Caller Updates**

The Prime Contractor postmortem (`prime_postmortem.py`) must pass `sibling_files` and `import_map` (when available from seed) to `validate_disk_compliance()`. The Artisan postmortem (`postmortem.py`) gains the same integration at a lower priority.

---

### REQ-SV-900: Observability

**REQ-SV-901: OTel Span Attributes**

When semantic validation runs within an OTel-instrumented context, emit span attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `semantic_validation.issues_count` | int | Total semantic issues found |
| `semantic_validation.error_count` | int | Issues with severity `error` |
| `semantic_validation.warning_count` | int | Issues with severity `warning` |
| `semantic_validation.categories` | str[] | Distinct categories of issues found |
| `semantic_validation.import_map_mode` | bool | Whether golden seed import map was used |

**REQ-SV-902: Loki Logging**

Log each semantic issue at WARNING level using `get_logger()` (not `logging.getLogger()`), with structured fields:

```python
logger.warning(
    "Semantic issue: %s",
    issue["message"],
    extra={"category": issue["category"], "severity": issue["severity"],
           "file_path": file_path, "line": issue.get("line")}
)
```

**REQ-SV-903: Kaizen Data Export**

The postmortem report must include per-task semantic issue counts and categories in the Kaizen-consumable output, enabling cross-run trend analysis of semantic quality.

---

## 5. Success Criteria

| Criterion | Metric | Target |
|-----------|--------|--------|
| Run-050 bug detection | Bugs from Section 1 caught by semantic validation | >= 8 of 11 (L1–L5 coverage) |
| No false positives on run-049 | Semantic issues flagged on run-049's 14 byte-identical files | 0 |
| Golden seed import map mode | With import map, all 4 phantom import bugs caught | 4/4 |
| Dockerfile digest bugs | Truncated SHA256 digests caught | 2/2 (3 files) |
| Score discrimination | Run-050's worst files score below PASS threshold | `shoppingassistantservice.py` score < 0.80 |
| Performance | Validation time per file (1000 LOC) | < 100ms |
| Backward compatibility | Existing tests pass without modification | 100% |

---

## 6. Implementation Phases

### Phase 1: Foundation + L1 Import Resolution (P0)

1. Define `SemanticIssue` TypedDict in `forward_manifest_validator.py`
2. Implement `_validate_import_resolution()` — reuse `_STDLIB_MODULES`, `_PROTOBUF_STUB_RE`, `import_to_pypi()`
3. Wire into `validate_disk_compliance()` with optional `sibling_files` and `import_map` params
4. Update `prime_postmortem.py` to pass sibling context
5. Tests: phantom imports, wrong paths, repair-mangled imports, golden seed import map mode

### Phase 2: L2 Cross-Scope Duplicates + L3 Dockerfile Digest (P1)

1. Extend `_count_duplicate_definitions()` to track scope hierarchy
2. Add SHA256 digest length check to `_validate_dockerfile()`
3. Tests: nested+module scope collision, truncated digests

### Phase 3: L4 Factory Return + L5 Requirements Cross-Check (P2)

1. Implement `_validate_factory_returns()` with configurable patterns
2. Implement `_validate_requirements_coverage()` with reverse import map
3. Tests: missing return in `create_*`, orphan dependencies

### Phase 4: L6 Expression Lint + Observability (P3)

1. Implement `_validate_discarded_returns()` with configurable pure function list
2. Add OTel span attributes and Loki logging
3. Add Kaizen export fields

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| False positives on legitimate local imports | Medium | High (breaks PASS scores) | Conservative: only flag when import resolves to NO source; allow `warning` severity for ambiguous cases |
| `import_to_pypi` reverse map is incomplete | Medium | Medium (missed phantom deps) | Expand `package_aliases.py` as gaps are discovered; log unresolvable mappings for Kaizen triage |
| Cross-scope duplicate exceptions are too broad | Low | Low | Start strict (flag all cross-scope), tune exception rules based on false positive data |
| Performance regression with sibling file scanning | Low | Low | Sibling list passed explicitly from postmortem (no disk scan in hot path) |
| Existing `semantic_issues` consumers break on dict format | Low | Medium | REQ-SV-102 requires backward compatibility; existing string entries continue to work |

---

## 8. Cross-References

| Document | Relationship |
|----------|-------------|
| [SEMANTIC_VALIDATION_GAP_ANALYSIS.md](SEMANTIC_VALIDATION_GAP_ANALYSIS.md) | Source evidence — 11 bugs across runs 049/050 that define L1–L7 |
| [GOLDEN_SEED_REQUIREMENTS.md](../plan-ingestion/GOLDEN_SEED_REQUIREMENTS.md) | REQ-GS-302 `import_map` enables L1 closed-world validation |
| [CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md](CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md) | Root cause analysis — proto imports not reaching LLM prompts |
| `forward_manifest_validator.py` | Implementation target — `validate_disk_compliance()` and non-Python validators |
| `prime_postmortem.py` | Scoring consumer — `compute_disk_quality_score()` already penalizes semantic issues |
| `requirements_generator.py` | Reusable infrastructure — `_STDLIB_MODULES`, `_PROTOBUF_STUB_RE`, `extract_third_party_imports()` |
| `package_aliases.py` | Reusable infrastructure — `import_to_pypi()` reverse lookup |
| [KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md](KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md) | Parent quality phase requirements |
