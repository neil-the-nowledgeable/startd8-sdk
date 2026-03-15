# Semantic Validation Gap Analysis

**Date:** 2026-03-15
**Status:** Analysis Complete
**Author:** Human + Agent collaboration
**Domain:** Post-Generation Quality Gates
**Source Evidence:** Run-049 vs Run-050 comparative analysis (online-boutique calibration workload)

---

## 1. Problem Statement

The Prime Contractor postmortem validation reports 17/17 PASS (score 1.0) for run-050, yet manual review found critical bugs in at least 5 of 17 generated files. The validation pipeline checks **syntactic** properties (AST validity, stubs, duplicate definitions, import presence) but has no **semantic** checks. Code that parses correctly but imports non-existent modules, calls wrong APIs, or has structural logic errors passes all gates.

### Evidence: Run-050 Bugs That Escaped Validation

| Bug | File | Postmortem Score | Actual Quality |
|-----|------|-----------------|----------------|
| Phantom imports (`from alloydbengine import AlloyDBEngine`) | shoppingassistantservice.py | 1.0 | F — module doesn't exist |
| Wrong import paths (`from emailservice.email_server import EmailServiceStub`) | email_client.py | 1.0 | D — symbol doesn't exist at that path |
| Repair-mangled imports (`from recommendationservice.recommendation_server import ListRecommendationsRequest`) | client.py | 1.0 | D — symbol comes from proto stubs |
| Duplicate function across scopes (nested + module-level `talkToGemini`) | shoppingassistantservice.py | 1.0 | F — module-level copy references unbound globals |
| Missing `return app` in `create_app()` | shoppingassistantservice.py | 1.0 | F — Flask app never returned |
| Discarded `os.getenv()` results (3 calls) | shoppingassistantservice.py | 1.0 | C — config silently lost |
| Embedding model typo `"models/embedding-0o01"` | shoppingassistantservice.py | 1.0 | D — 404 at runtime |
| Truncated Docker SHA256 digest (8 chars, need 64) | 3 Dockerfiles | 1.0 | F — build fails |
| `self.index()` vs `index(self)` in Locust TaskSet | locustfile.py | 1.0 | C — on_start fails |
| Template variable mismatch (`shipping_cost_currency_code` vs `shipping_cost_currency`) | confirmation.html | 1.0 | B- — renders blank |
| `customjsonformatter` fake pip dep | requirements.in | 1.0 | C — install fails |

---

## 2. Current Validation Checks

| Check | Implementation | What It Catches | What It Misses |
|-------|---------------|-----------------|----------------|
| `ast_valid` | `ast.parse(source)` | Syntax errors | Correct syntax with wrong semantics |
| `stubs_remaining` | `_count_stubs(tree)` — finds `pass`/`raise NotImplementedError` in function bodies | Incomplete implementations | Functions with wrong implementations |
| `duplicate_definitions` | `_count_duplicate_definitions(tree)` — module-level only | Two `def foo()` at same scope | Duplicates across scopes (nested + module-level) |
| `import_completeness` | Cross-reference actual imports against manifest `spec.imports` | Missing imports declared in manifest | Imports from non-existent modules |
| `contract_compliance` | Count elements from manifest found in AST | Missing elements | Elements present but with wrong behavior |
| `semantic_issues` | (empty list — no checks exist) | Nothing | Everything semantic |
| `_validate_requirements_file` | PEP 508 format + camelCase detection | `setCurrency` as a package name | `customjsonformatter` (valid PEP 508 format) |
| `_validate_dockerfile` | Basic structure checks | Missing FROM/ENTRYPOINT | Truncated SHA256 digests |

---

## 3. Proposed Semantic Validation Layers

### Layer 1: Import Resolution Validation (P0)

**Catches:** 4 bugs (phantom imports, wrong module paths, repair-mangled imports)

Every `import X` and `from X.Y import Z` must resolve to one of:
1. A stdlib module (`sys.stdlib_module_names`)
2. A package in the task's `requirements.in` (via `import_to_pypi` alias map)
3. A sibling file in the same service directory (`.py` stem match)
4. A protobuf stub (`*_pb2`, `*_pb2_grpc`)
5. A directory package (directory name in same service)

Unresolvable imports produce a `semantic_issues` entry with severity `error`.

**Implementation:** AST walk extracting all import top-levels and full dotted paths. Cross-reference against:
- `sys.stdlib_module_names` (already in `requirements_generator.py`)
- `_PROTOBUF_STUB_RE` (already in `requirements_generator.py`)
- Sibling `.py` file stems from disk scan
- Packages from `requirements.in` (reverse `import_to_pypi` lookup)

**Location:** New function `_validate_import_resolution()` in `forward_manifest_validator.py`, called from `validate_disk_compliance()`.

### Layer 2: Cross-Scope Duplicate Detection (P1)

**Catches:** 1 bug (duplicate `talkToGemini` at nested + module scope)

Extend `_count_duplicate_definitions` to walk ALL scopes. When the same function name appears both inside a `def`/`class` body AND at module level, flag it.

**Implementation:** Walk AST collecting `(name, parent_type)` pairs. A name with both `parent=Module` and `parent=FunctionDef` is a cross-scope duplicate.

### Layer 3: Dockerfile Digest Validation (P1)

**Catches:** 2 bugs (truncated SHA256 digests)

In `_validate_dockerfile()`, add regex check: `FROM` lines with `@sha256:` must have exactly 64 hex characters after the prefix.

**Implementation:** `re.findall(r'@sha256:([0-9a-fA-F]+)', line)` → verify `len(digest) == 64`.

### Layer 4: Factory Return Value Check (P2)

**Catches:** 1 bug (missing `return app` in `create_app()`)

Functions matching `create_*` or `*_factory` naming patterns that contain no `return <expr>` statement (only bare `return` or no return) are flagged.

**Implementation:** AST walk for `ast.FunctionDef` nodes with matching names, check for `ast.Return` nodes with non-None `value`.

### Layer 5: Requirements-to-Import Cross-Check (P2)

**Catches:** 1 bug (`customjsonformatter` listed but never imported)

For each package in `requirements.in`, verify at least one sibling `.py` file imports it (using `import_to_pypi` reverse lookup).

**Implementation:** Build reverse map `pypi_name → {import_names}`. For each requirement line, check if any import in any sibling file maps to that package.

### Layer 6: Expression Statement Lint (P3)

**Catches:** 1 bug (discarded `os.getenv()` results)

Flag `ast.Expr` nodes containing `ast.Call` where the callee is a known return-value function (`os.getenv`, `os.environ.get`, `dict.get`, etc.).

**Implementation:** Configurable allowlist of `module.function` patterns. Walk AST for `Expr(Call(...))` nodes matching the allowlist.

### Layer 7: Cross-File Template Consistency (P3)

**Catches:** 1 bug (`shipping_cost_currency_code` vs `shipping_cost_currency`)

Extract `{{ variable }}` references from Jinja2 templates and compare against `template.render(key=...)` keyword arguments in the consuming Python file.

**Implementation:** Regex `\{\{\s*(\w+)` on HTML files. AST extraction of `render()` call keyword names from Python files. Requires manifest-based file pairing.

---

## 4. Priority Matrix

| Layer | Bugs Caught | Effort | Dependencies | Priority |
|-------|-------------|--------|-------------|----------|
| L1: Import resolution | 4 | Medium (reuse `requirements_generator.py` infrastructure) | sibling file listing, requirements.in | **P0** |
| L2: Cross-scope duplicates | 1 | Low (extend existing `_count_duplicate_definitions`) | None | **P1** |
| L3: Dockerfile digest | 2 | Low (regex addition to `_validate_dockerfile`) | None | **P1** |
| L4: Factory return | 1 | Low (pattern-based AST check) | None | **P2** |
| L5: Requirements cross-check | 1 | Low (reverse of requirements generator) | requirements.in on disk | **P2** |
| L6: Expression lint | 1 | Medium (needs allowlist curation) | None | **P3** |
| L7: Template consistency | 1 | High (cross-file analysis, manifest pairing) | Jinja2 template ↔ Python file mapping | **P3** |

---

## 5. Run-049 vs Run-050 Regression Root Causes

### Why Run-050 Degraded Despite Same Pipeline

| Factor | Run-049 | Run-050 | Effect |
|--------|---------|---------|--------|
| Seed checksum | `c8a2b5d3c640` | `f789a5364127` | Different prompts to generators |
| Transform phase | Skipped ($0.00) | LLM-backed ($0.35) | Richer task descriptions but prompt drift |
| PI-008 route | Escalated to Sonnet ($0.18) | Micro Prime only ($0.00) | Cheaper but dramatically worse code |
| PI-003, PI-006 | Escalated to Sonnet | Same route | LLM non-determinism — different output despite same route |
| Repair pipeline | 0 repairs needed | 3 repairs applied | Repair fixed syntax but introduced wrong import paths |

### File-Level Winner Comparison

| File | Winner | Severity |
|------|--------|----------|
| email_server.py | Run-050 | Moderate — nails jinja2 import, `__all__`, send_email stub |
| email_client.py | Run-050 | High — run-049 fabricated proto modules |
| recommendation_server.py | Run-049 | Moderate — correct profiler check, tracing order, KeyboardInterrupt |
| client.py | Run-049 | High — run-050 repair-mangled the imports |
| shoppingassistantservice.py | **Run-049** | **Critical** — run-050 has phantom imports, typo, duplicate function, missing entrypoint |
| Dockerfiles (3) | Run-049 | Moderate — valid SHA256 digests |
| requirements.in (email) | Run-050 | Low — removed self-referential `emailservice` |
| requirements.in (rec) | Run-050 | Low — slightly more plausible dep name |
| requirements.in (shopping) | **Run-049** | **High** — run-050 lists phantom modules as pip deps |
| confirmation.html | Run-049 | Moderate — correct template variable names |
| locustfile.py | Tie | Negligible — only function ordering |

**Net**: Run-049 wins 6 files (including the two most critical), run-050 wins 4 files, 1 tie.

### Key Insight: Non-Determinism Is the Primary Quality Threat

The same pipeline, same plan, same requirements, same model produces **different quality** on consecutive runs. The validation gates cannot distinguish good from bad because they only check syntax. The proposed semantic validation layers (especially L1: import resolution) would have flagged 4 of the 11 bugs, preventing the worst regressions from passing as PASS.

---

## 6. Cross-References

| Document | Relationship |
|----------|-------------|
| [KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md](KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md) | Quality phase requirements that motivated this analysis |
| [GOLDEN_SEED_REQUIREMENTS.md](../plan-ingestion/GOLDEN_SEED_REQUIREMENTS.md) | Golden seed specification — golden seed + semantic validation together close the quality loop |
| `forward_manifest_validator.py` | Current validation implementation (target for L1-L6) |
| `requirements_generator.py` | Reusable import resolution infrastructure (stdlib set, protobuf regex, import_to_pypi) |
