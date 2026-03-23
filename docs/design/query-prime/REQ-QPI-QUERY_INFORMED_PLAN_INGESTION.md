# Query-Informed Plan Ingestion — Requirements

> **Version:** 1.1.0
> **Status:** DRAFT (revised post-implementation-plan review)
> **Date:** 2026-03-22 (v1.1 same-day revision)
> **Parent:** [QUERY_PRIME_REQUIREMENTS.md](QUERY_PRIME_REQUIREMENTS.md), [KAIZEN_QUERY_PRIME_REQUIREMENTS.md](KAIZEN_QUERY_PRIME_REQUIREMENTS.md)
> **Design Principle:** Secure by construction — safe query patterns are deterministic scaffolds, not LLM judgment calls
> **Scope:** Integrate Query Prime knowledge into plan ingestion so that seeds produce secure query scaffolds before any LLM generation

---

## 1. Problem Statement

### 1.1 The Reference Implementation Poisoning Chain

Plan ingestion currently encodes reference implementation SQL patterns — including vulnerabilities — as acceptance criteria in the seed. This creates a 3-layer poisoning effect:

1. **Seed** — `acceptance_obligations: ["All SQL uses string interpolation"]` + `negative_scope: ["No parameterized queries"]`
2. **Spec** — AC-16 mandates string interpolation, making parameterized queries a spec violation
3. **LLM** — Follows the spec exactly, reproducing the vulnerability

Five independent downstream defenses (P0 security guidance, drafter constraint, reviewer rules, Kaizen hints, semantic checks) all fail to override the spec-level mandate because the LLM resolves the contradiction in favor of the more specific instruction (AC-16).

### 1.2 Root Cause

Plan ingestion treats the reference implementation as authoritative for query construction patterns. It does not consult Query Prime's `DatabasePatternRegistry` — which knows exactly what safe/unsafe patterns look like per (database, language, framework) — before encoding acceptance criteria.

### 1.3 The Fix Direction

Move the security decision **upstream** of the seed. Instead of generating code and then detecting vulnerabilities, produce **pre-approved query scaffolds** at plan ingestion time using Query Prime's existing CRUD templates and safe pattern registry. The LLM fills business logic around a secure scaffold — it never decides between interpolation and parameterization.

---

## 2. Design Principles

| ID | Principle | Rationale |
|----|-----------|-----------|
| DP-1 | **Secure by construction** | Safe query patterns are deterministic output, not LLM judgment. The LLM fills business logic around an already-secure scaffold. |
| DP-2 | **Query Prime is authoritative** | `DatabasePatternRegistry` is the single source of truth for safe query patterns per (database, language). Plan ingestion defers to it. |
| DP-3 | **Scaffold over correction** | Producing a correct scaffold is cheaper and more reliable than producing code, detecting flaws, and repairing. Prevention > detection > repair. |
| DP-4 | **Reference match ≠ vulnerability match** | "Match the reference implementation" applies to behavior (API contract, data flow) not to implementation details (query construction). An acceptance anchor that encodes a vulnerability is not a valid anchor. |
| DP-5 | **Additive, not breaking** | All changes to plan ingestion are additive. Existing features without database operations are unaffected. |

---

## 3. Architecture

### 3.1 Current Flow (No Query Prime Integration)

```
Plan Document → Parse → Derive Features → Derive Tasks → Seed
                                                ↓
                                         acceptance_obligations
                                         (from reference, UNVALIDATED)
                                                ↓
                                         Spec → Draft → Review → Generate
                                                ↓
                                         Detect vulnerabilities (too late)
```

### 3.2 Proposed Flow (Query-Informed Ingestion)

```
Plan Document → Parse → Derive Features
                              ↓
                    ┌─────────────────────┐
                    │  Query Prime Probe   │  (NEW — REQ-QPI-100)
                    │                     │
                    │  For each feature:  │
                    │  1. detect_database  │
                    │  2. decompose_ops   │
                    │  3. classify_tier   │
                    │  4. match_template  │
                    └─────────┬───────────┘
                              ↓
                    ┌─────────────────────┐
                    │  Anchor Sanitization │  (NEW — REQ-QPI-200)
                    │                     │
                    │  1. Validate anchors │
                    │     vs unsafe_patterns│
                    │  2. Replace anti-    │
                    │     pattern anchors  │
                    │     with safe equiv  │
                    │  3. Strip negative_  │
                    │     scope conflicts  │
                    └─────────┬───────────┘
                              ↓
                    ┌─────────────────────┐
                    │  Scaffold Assembly   │  (NEW — REQ-QPI-300)
                    │                     │
                    │  For TRIVIAL/SIMPLE  │
                    │  query operations:  │
                    │  Produce parameterized│
                    │  method skeletons   │
                    │  from CRUD templates │
                    └─────────┬───────────┘
                              ↓
                         Enriched Seed
                         ├── detected_database: "postgresql"
                         ├── security_sensitive: true
                         ├── query_scaffolds: [method skeletons]
                         ├── safe_param_syntax: "..."
                         └── acceptance_obligations: SANITIZED
                              ↓
                    Spec → Draft → Review → Generate
                         (LLM fills scaffolds, never decides query patterns)
```

---

## 3.3 v1.1 Revision — Post-Implementation-Plan Insights

Writing the implementation plan revealed seven gaps in v1.0 that change the requirements:

**Insight 1: The task DESCRIPTION is a bigger poisoning surface than acceptance anchors.**
The AlloyDB seed description says *"Uses string-interpolated SQL matching reference implementation"* — this flows into `task_description`, which the LLM reads directly in the spec body. Sanitizing acceptance_obligations alone leaves the description untouched. **→ Added REQ-QPI-203 (Task Description Sanitization).**

**Insight 2: `design_doc_sections` carry reference SQL examples into the spec independently of anchors.**
Run-104's AlloyDB task has 9 `design_doc_sections` including SQL patterns. The spec builder already has `_detect_sql_interpolation_in_examples()` for design documents, but it doesn't run on `design_doc_sections` from the seed context. **→ Added REQ-QPI-204 (Design Doc Section SQL Sanitization).**

**Insight 3: UPSERT template doesn't exist — the coverage matrix claims it.**
AlloyDB's `AddItemAsync` is INSERT...ON CONFLICT DO UPDATE (UPSERT). `query_prime/templates/crud.py` has SELECT, INSERT, UPDATE, DELETE for PostgreSQL×C# but no UPSERT. The Phase 2 scaffold example showed `"operation": "UPSERT"` but no template would generate it. **→ Fixed REQ-QPI-303 coverage matrix; added UPSERT as a Phase 2 template gap to close.**

**Insight 4: Sanitization must run BEFORE `_CONTEXT_THREADABLE_FIELDS` propagation.**
`negative_scope` is in `_CONTEXT_THREADABLE_FIELDS` (line 96), meaning it auto-propagates from features to task contexts. If sanitization runs after threading, the original `negative_scope` is already copied. **→ Added timing constraint to REQ-QPI-201.**

**Insight 5: Quick wins exist that are independent of the full sanitizer module.**
Populating `detected_database` and `security_sensitive` (which already exist as empty SeedTask fields) is ~10 lines of code that immediately enriches the Anzen gate and spec builder's `_build_security_guidance_section()`. This is smaller than Phase 1 and can ship independently. **→ Added Phase 0 (Quick Wins) to rollout.**

**Insight 6: `detected_database` is already populated in run-104 — but the Anzen gate only found 1 work item.**
The seed shows `detected_database: "postgresql"` on AlloyDB. The gap isn't that the field is empty — it's that the Anzen gate's file-level `detect_database_type(source)` fails to match generated code that uses `Npgsql` without the word "postgres" in it. **→ Added REQ-QPI-105 (Anzen Gate Database Detection Enrichment) to pass seed-level database context to the gate.**

**Insight 7: The spec builder's existing P0 security guidance already contradicts AC-16 — and the LLM resolves in favor of AC-16.**
This means Phase 1 (anchor sanitization) alone is sufficient to fix the AlloyDB problem. The existing P0 security guidance becomes effective once the contradicting AC is removed. Scaffolds (Phase 2) are a separate cost-optimization value stream, not a prerequisite for security. **→ Reframed Phase 1 as the security fix and Phase 2 as the cost fix.**

---

## 4. Quick Wins — Phase 0 (REQ-QPI-0xx)

These can ship in <30 minutes each, independently of the full sanitizer module. They immediately improve downstream quality even without anchor sanitization.

### REQ-QPI-001: Populate SeedTask.detected_database During Plan Ingestion

**Effort:** ~10 lines. **Impact:** High.

The `SeedTask` model already has `detected_database: str = ""` and `security_sensitive: bool = False` fields (seeds/models.py). Plan ingestion already calls `detect_database_type()` in at least one code path but never stores the result in the seed task.

**What to do:** In `_derive_tasks_from_features()`, after feature context assembly, call `detect_database_type()` on the combined feature text and populate the fields.

**Downstream impact:**
- `_build_security_guidance_section()` in spec_builder.py receives `detected_databases` → P0 security guidance fires with database-specific examples
- Anzen gate can use seed-level database context instead of re-detecting from source code
- Kaizen metrics `by_database` breakdown gets data

### REQ-QPI-002: Copy query-security-metrics.json to Run Directory

**Effort:** ~5 lines. **Impact:** Fixes L4=F (trend script finds 0 runs).

The standalone `query-security-metrics.json` is written to the project root but the trend script scans run directories. Copy the file to `{run_dir}/plan-ingestion/` alongside `kaizen-metrics.json`.

### REQ-QPI-003: Add UPSERT Template for PostgreSQL×C#

**Effort:** ~30 lines in `query_prime/templates/crud.py`. **Impact:** Closes the most common scaffold gap.

AlloyDB's `AddItemAsync` is `INSERT...ON CONFLICT DO UPDATE` — the most common PostgreSQL upsert pattern. Template using `cmd.Parameters.AddWithValue("@param", value)` for both INSERT and UPDATE SET clauses.

---

## 5. Layer 1 — Query Prime Probe (REQ-QPI-1xx)

Run Query Prime's decomposition and classification on each feature during plan ingestion — before any LLM generation.

### REQ-QPI-100: Feature-Level Database Detection

During `_derive_tasks_from_features()`, invoke `query_prime.decomposer.detect_database_type()` on each feature's description + metadata to populate `context.detected_database`.

**Acceptance criteria:**
1. Every task whose description mentions a database keyword gets `detected_database` populated (e.g., `"postgresql"`, `"spanner"`, `"redis"`)
2. The detection uses the same `_DATABASE_PATTERNS` from `decomposer.py` that Query Prime uses at generation time
3. Tasks without database keywords get `detected_database = ""` (no false positives)
4. `security_sensitive = True` is set for all tasks with a detected database

**Implementation:** `plan_ingestion_workflow.py:_derive_tasks_from_features()` — after feature context assembly, before seed emission.

### REQ-QPI-101: Query Work Item Decomposition at Ingestion Time

For each database-facing feature, invoke `query_prime.decomposer.decompose_feature()` to produce `QueryWorkItem` instances. Store the decomposition in the task context as `query_work_items`.

**Acceptance criteria:**
1. Each `QueryWorkItem` has: database, operation_type, tables, parameters, target_language
2. The decomposition is stored as serializable dicts in `context["query_work_items"]`
3. Non-database features produce an empty list (no work items)
4. The work items carry through to the spec builder via `gen_context`

### REQ-QPI-102: Query Tier Classification at Ingestion Time

Classify each `QueryWorkItem` as TRIVIAL, SIMPLE, MODERATE, or COMPLEX using the Query Prime template registry's `is_trivial()` check and operation complexity heuristics.

**Acceptance criteria:**
1. TRIVIAL: single-table, single-operation, ≤5 parameters, template exists in `query_prime/templates/`
2. SIMPLE: single-table CRUD, basic JOIN, or upsert without complex conditions
3. MODERATE: multi-table transactions, aggregates, conditional logic
4. COMPLEX: recursive queries, CTEs, dynamic SQL
5. Classification stored in `context["query_tier"]` per work item

### REQ-QPI-105: Anzen Gate Database Detection Enrichment

The Anzen gate's file-level `detect_database_type(source)` misses files that use database libraries (e.g., `Npgsql`) without containing the exact keyword "postgres." Run-104 processed only 1 of 15 features despite 3 database backends.

**Fix:** When the Anzen gate processes integrated files, consult the task's `detected_database` field (from REQ-QPI-100) as a fallback when file-level detection returns None.

**Acceptance criteria:**
1. If `detect_database_type(source)` returns None but the task's `detected_database` is populated, use the task-level value
2. All files belonging to a database-facing task are verified by the Anzen gate
3. `total_work_items` in `query-security-metrics.json` reflects actual database-facing files, not just keyword matches

---

## 5. Layer 2 — Acceptance Anchor Sanitization (REQ-QPI-2xx)

Validate acceptance anchors against Query Prime's `unsafe_patterns` registry and replace anti-pattern anchors with safe equivalents.

### REQ-QPI-200: Anti-Pattern Anchor Detection

When `_normalize_requirements_hints()` processes `acceptance_anchors`, check each anchor against Query Prime's known unsafe patterns.

**Detection rules:**
- Anchor contains SQL keyword (SELECT/INSERT/UPDATE/DELETE) AND interpolation keyword (interpolation, `$"`, concatenation, `String.Format`, `f"`) → **ANTI-PATTERN**
- Anchor contains "intentional" or "reference match" AND SQL/injection context → **ANTI-PATTERN**
- Anchor says "no parameterized queries" or "not parameterized" → **ANTI-PATTERN**

**Acceptance criteria:**
1. Anti-pattern anchors are flagged with `{"classified": "anti_pattern", "safe_replacement": "..."}`
2. Non-SQL anchors pass through unchanged
3. Detection is deterministic (regex, no LLM calls)
4. Flagged anchors produce an INFO log with the original and replacement text

### REQ-QPI-201: Safe Anchor Replacement

Replace flagged anti-pattern anchors with safe equivalents from `DatabasePatternRegistry.safe_param_syntax`:

| Anti-Pattern Anchor | Safe Replacement |
|---------------------|-----------------|
| "All SQL uses string interpolation" | "All SQL uses parameterized queries ({safe_syntax})" |
| "No parameterized queries" | REMOVED from acceptance_obligations |
| "String interpolation intentional" | REMOVED from acceptance_obligations |
| "Matches reference SQL pattern" | "Matches reference API contract; query implementation uses parameterized queries" |

**Acceptance criteria:**
1. Replacement text includes the database-specific safe syntax example
2. Original anchor text is preserved in `context["replaced_anchors"]` for audit trail
3. `negative_scope` entries that conflict with safe query patterns are stripped (e.g., "No parameterized queries")
4. Replacement runs AFTER database detection (REQ-QPI-100) so the correct safe syntax is known
5. **Timing constraint (v1.1):** Sanitization MUST run BEFORE `_CONTEXT_THREADABLE_FIELDS` propagation (line 2543 of `plan_ingestion_workflow.py`), because `negative_scope` is in the threadable set and auto-propagates from features to task contexts. If sanitization runs after threading, the original `negative_scope` is already copied.

### REQ-QPI-202: Sanitization Audit Trail

Produce a structured log of all anchor replacements for postmortem analysis:

```json
{
  "task_id": "PI-009",
  "feature_name": "AlloyDBCartStore",
  "anchors_replaced": [
    {
      "original": "All SQL uses string interpolation",
      "replacement": "All SQL uses parameterized queries (cmd.Parameters.AddWithValue(\"@id\", id))",
      "reason": "anti_pattern:sql_interpolation",
      "database": "postgresql",
      "safe_syntax_source": "DatabasePatternRegistry(postgresql, csharp)"
    }
  ],
  "negative_scope_stripped": [
    "Parameterized queries intentionally not used"
  ]
}
```

### REQ-QPI-203: Task Description Sanitization

**Added in v1.1** — Implementation planning revealed that the task `description` is a larger poisoning surface than acceptance anchors.

Run-104's AlloyDB seed description says: *"Uses string-interpolated SQL matching reference implementation."* This flows into `task_description`, which the LLM reads directly in the spec body — independently of acceptance criteria.

**Requirement:** When a task has `detected_database` set and its `task_description` contains SQL anti-pattern language (same detection rules as REQ-QPI-200), replace the anti-pattern language in-place.

**Rules:**
- "string-interpolated SQL" → "parameterized SQL using {safe_param_syntax}"
- "string interpolation matching reference" → "parameterized queries (deviating from reference for security)"
- Preserve all other description content unchanged

**Timing constraint:** Must run AFTER database detection (REQ-QPI-100) and BEFORE seed emission, in the same pass as anchor sanitization.

### REQ-QPI-204: Design Doc Section SQL Sanitization

**Added in v1.1** — The seed's `design_doc_sections` carry reference SQL examples into the spec independently of anchors and descriptions.

The spec builder already has `_detect_sql_interpolation_in_examples()` (spec_builder.py:763) that detects SQL interpolation in design documents and appends a warning. But this only runs on the design document at spec time — not on `design_doc_sections` from the seed context.

**Requirement:** Apply the same `_detect_sql_interpolation_in_examples()` detection to each `design_doc_section` string during plan ingestion. If SQL interpolation is detected in a section:
1. Append a `⚠ WARNING` block (same format as spec_builder.py:763) to the section text
2. Log the flagged section for audit

**Alternative (simpler):** Instead of modifying sections at ingestion time, extend the spec builder to also scan `design_doc_sections` (not just the design document). This leverages existing code without adding new ingestion logic.

**Recommendation:** The simpler alternative — extend spec_builder to cover `design_doc_sections`. Less ingestion complexity, same protection.

---

## 6. Layer 3 — Query Scaffold Assembly (REQ-QPI-3xx)

Produce pre-approved, parameterized method skeletons for database-facing tasks using Query Prime's existing CRUD templates.

### REQ-QPI-300: Scaffold Generation from CRUD Templates

For each `QueryWorkItem` classified as TRIVIAL, generate a parameterized method skeleton using `query_prime.templates.generate()`.

**Acceptance criteria:**
1. TRIVIAL query work items produce a complete method skeleton with parameterized queries
2. The skeleton uses `await using var` (C# 8+), `with` (Python), pool pattern (Node.js) — matching each language's lifecycle conventions
3. Scaffolds include the correct `using`/`import` directives for the database client library
4. Non-TRIVIAL work items produce a **scaffold stub** with the method signature + parameter declarations + a `// TODO: implement` body (the LLM fills this)
5. Scaffolds are stored in `context["query_scaffolds"]` as a list of `{method_name, code, operation, database}` dicts

### REQ-QPI-301: Scaffold Injection into Spec Context

The spec builder MUST use `query_scaffolds` from the seed context when constructing the spec:

1. If scaffolds exist, include them in a "## Query Implementation Scaffolds" section at P0 priority
2. The section header MUST say: "These scaffolds use pre-approved parameterized query patterns. Implement the business logic within these method bodies. DO NOT replace the parameterization pattern with string interpolation."
3. For TRIVIAL scaffolds (complete methods), the spec says: "Use this method as-is; adjust only column names and business logic."
4. For non-TRIVIAL scaffold stubs, the spec says: "Fill the method body using the parameterization pattern shown in the signature and parameter declarations."

### REQ-QPI-302: Scaffold Validation at Assembly Time

Each generated scaffold MUST pass validation before being included in the seed:

1. Language-specific syntax validation via `LanguageProfile.validate_syntax()`
2. Safe pattern verification: at least one `safe_patterns` regex from `DatabasePatternRegistry` matches the scaffold code
3. Unsafe pattern rejection: zero `unsafe_patterns` regexes match
4. Scaffolds that fail validation are logged and excluded (the feature falls back to LLM-only generation)

### REQ-QPI-303: Scaffold Coverage Matrix

Define the minimum scaffold coverage by database and language:

| Database | C# | Python | Node.js | Go | Java |
|----------|-----|--------|---------|-----|------|
| PostgreSQL | SELECT, INSERT, UPDATE, DELETE, UPSERT, HEALTH | SELECT, INSERT, DELETE, HEALTH | SELECT, INSERT, HEALTH | — | — |
| Spanner | SELECT, INSERT, DELETE, HEALTH | HEALTH | HEALTH | SELECT, HEALTH | HEALTH |
| Redis | GET, SET, DELETE, HEALTH | GET, SET, DELETE, HEALTH | GET, SET, HEALTH | — | — |
| MySQL | SELECT, INSERT, UPDATE, DELETE, HEALTH | SELECT, INSERT, DELETE, HEALTH | SELECT, INSERT, HEALTH | — | — |
| SQLite | SELECT, INSERT, UPDATE, DELETE, HEALTH | SELECT, INSERT, DELETE, HEALTH | — | — | — |

Cells marked `—` have no template today. Features targeting these combinations fall back to LLM generation with P0 security guidance (existing behavior).

---

## 7. Layer 4 — Seed Enrichment (REQ-QPI-4xx)

### REQ-QPI-400: Per-Task Security Context Population

During seed assembly, populate the existing but currently empty SeedTask fields:

| Field | Source | Example |
|-------|--------|---------|
| `detected_database` | `decomposer.detect_database_type()` | `"postgresql"` |
| `security_sensitive` | `True` if `detected_database != ""` | `True` |
| `context["safe_param_syntax"]` | `DatabasePatternRegistry.get(db, lang).safe_param_syntax[0]` | `'cmd.Parameters.AddWithValue("@id", id)'` |
| `context["query_work_items"]` | `decomposer.decompose_feature()` serialized | `[{...}, {...}]` |
| `context["query_scaffolds"]` | Scaffold assembly output (REQ-QPI-300) | `[{method_name, code, ...}]` |
| `context["query_tier"]` | Max tier across work items | `"SIMPLE"` |

### REQ-QPI-401: Security Contract Derivation from Seed

When the seed-level `security_contract` is absent (no `.contextcore.yaml` or manifest), derive it from the per-task `detected_database` fields:

```python
databases = {t.context["detected_database"] for t in seed.tasks if t.context.get("detected_database")}
if databases:
    seed.security_contract = {
        "databases": sorted(databases),
        "client_libraries": [infer_client_library(db, language) for db in databases],
        "source": "plan_ingestion_auto_detect",
    }
```

This ensures `_build_security_guidance_section()` in the spec builder receives a `security_contract` even when the project doesn't have explicit security metadata.

---

## 8. Phased Rollout (Revised v1.1)

| Phase | Requirements | What It Enables | Risk | Effort |
|-------|-------------|-----------------|------|--------|
| **0 (Quick Wins)** | REQ-QPI-001, 002, 003 | Populate empty SeedTask fields, fix trend file location, add UPSERT template | None — filling empty fields, copying a file, adding a template | <1 hour |
| **1 (Security Fix)** | REQ-QPI-100, 200, 201, 203, 400 | **THE security fix.** Seeds no longer encode anti-patterns. Existing P0 security guidance in spec builder becomes effective because AC-16 no longer contradicts it. | Low — additive enrichment, no generation changes | 1 day |
| **1b (Breadth)** | REQ-QPI-105, 204 | Anzen gate uses seed-level database context (more files verified). Design doc sections scanned for SQL interpolation. | Low | Half day |
| **2 (Cost Fix)** | REQ-QPI-101, 102, 300, 301, 003 | TRIVIAL operations get $0.00 scaffolds. LLM fills non-trivial. This is **cost optimization**, not security — Phase 1 already fixed the security issue. | Medium — scaffold quality validation | 2 days |
| **3 (Quality)** | REQ-QPI-302, 303, 401 | Validation gate + coverage matrix + auto-derived security contract. | Low | 1 day |

### Key v1.1 Insight: Phase 1 Alone Fixes the Security Problem

The implementation plan revealed that the spec builder already has comprehensive P0 security guidance (`_build_security_guidance_section()`) that says "MANDATORY OVERRIDE: use parameterized queries." This guidance ALREADY EXISTS in every C# database-facing spec. The reason it doesn't work is that AC-16 ("All SQL uses string interpolation") contradicts it, and the LLM follows the more specific instruction.

**Phase 1 removes AC-16.** Once the acceptance anchor is sanitized, the existing P0 security guidance has no contradiction to resolve. The LLM receives consistent instructions: both the security section and the acceptance criteria say "use parameterized queries." This is the cheapest possible fix — remove the poison, let existing defenses work.

Phase 2 (scaffolds) is valuable for cost reduction and belt-and-suspenders security, but it's not required to eliminate SQL injection. It's a separate value stream.

### Phase 1 Expected Impact (AlloyDB Example)

**Before (current):**
```
acceptance_obligations: ["All SQL uses string interpolation"]
negative_scope: ["Parameterized queries intentionally not used"]
detected_database: ""  (empty)
security_sensitive: false
```

**After Phase 1:**
```
acceptance_obligations: ["All SQL uses parameterized queries (cmd.Parameters.AddWithValue(\"@id\", id))"]
negative_scope: []  (stripped)
detected_database: "postgresql"
security_sensitive: true
safe_param_syntax: "cmd.Parameters.AddWithValue(\"@id\", id)"
replaced_anchors: [{original: "All SQL uses string interpolation", ...}]
```

**Impact:** The spec builder receives a clean seed. AC-16 becomes "All SQL uses parameterized queries" instead of "All SQL uses string interpolation." The LLM has no contradictory instructions. The P0 security guidance and the acceptance criteria now agree.

### Phase 2 Expected Impact (AlloyDB Example)

In addition to Phase 1, the seed now contains:

```
query_scaffolds: [
  {
    method_name: "GetCartAsync",
    code: "public async Task<Cart> GetCartAsync(...)\n{\n    await using var conn = ...\n    await using var cmd = new NpgsqlCommand(\"SELECT ... WHERE userId = @userId\", conn);\n    cmd.Parameters.AddWithValue(\"@userId\", userId);\n    ...\n}",
    operation: "SELECT",
    database: "postgresql"
  },
  {
    method_name: "AddItemAsync",
    code: "...(parameterized INSERT/UPSERT)...",
    operation: "UPSERT",
    database: "postgresql"
  },
  ...
]
```

**Impact:** The LLM receives pre-approved method skeletons in the spec. It fills business logic (column mapping, error handling, return types) but the query construction pattern is already determined. Zero cost for the scaffold generation. SQL injection is architecturally impossible.

---

## 9. Traceability Matrix

| Requirement | Phase | Implements | Leverages | Files |
|-------------|-------|-----------|-----------|-------|
| REQ-QPI-001 | 0 | Quick win | `SeedTask` empty fields | `plan_ingestion_workflow.py` (~10 lines) |
| REQ-QPI-002 | 0 | Quick win | File copy | `integration_engine.py` or pipeline script (~5 lines) |
| REQ-QPI-003 | 0 | Quick win | CRUD template pattern | `query_prime/templates/crud.py` (~30 lines) |
| REQ-QPI-100 | 1 | DP-2 (Query Prime authoritative) | `decomposer.detect_database_type()` | `plan_ingestion_workflow.py` |
| REQ-QPI-105 | 1b | DP-2 | Seed-level `detected_database` | `integration_engine.py` Anzen gate |
| REQ-QPI-101 | 2 | DP-1 (Secure by construction) | `decomposer.decompose_feature()` | `plan_ingestion_workflow.py` |
| REQ-QPI-102 | 2 | DP-3 (Scaffold over correction) | `templates.is_trivial()` | `plan_ingestion_workflow.py` |
| REQ-QPI-200 | 1 | DP-4 (Reference ≠ vulnerability) | `DatabasePatternRegistry` unsafe_patterns | NEW: `plan_ingestion_anchor_sanitizer.py` |
| REQ-QPI-201 | 1 | DP-4 | `DatabasePatternRegistry` safe_param_syntax | NEW: `plan_ingestion_anchor_sanitizer.py` |
| REQ-QPI-202 | 1 | Audit trail | — | `plan_ingestion_workflow.py` |
| REQ-QPI-203 | 1 | DP-4 (v1.1) | Same sanitizer, applied to `task_description` | NEW: `plan_ingestion_anchor_sanitizer.py` |
| REQ-QPI-204 | 1b | DP-4 (v1.1) | Existing `_detect_sql_interpolation_in_examples()` | `spec_builder.py` (extend to `design_doc_sections`) |
| REQ-QPI-300 | 2 | DP-1, DP-3 | `templates/crud.py`, `templates/health_check.py` | NEW: `plan_ingestion_query_scaffold.py` |
| REQ-QPI-301 | 2 | DP-1 | `spec_builder.py` P0 sections | `spec_builder.py` |
| REQ-QPI-302 | DP-1 | `LanguageProfile.validate_syntax()`, `DatabasePatternRegistry` | NEW: `plan_ingestion_query_scaffold.py` |
| REQ-QPI-303 | Coverage | `templates/__init__.py` registry | Documentation |
| REQ-QPI-400 | DP-2 | `SeedTask` model fields (exist, unpopulated) | `plan_ingestion_workflow.py`, `seeds/builder.py` |
| REQ-QPI-401 | DP-2 | `SecurityContract` derivation | `plan_ingestion_emitter.py` |

---

## 10. Verification Strategy

### Unit Tests

| Test | Target | Method |
|------|--------|--------|
| AlloyDB feature → `detected_database: "postgresql"` | REQ-QPI-100 | Feature with "alloydb" in description → assert field populated |
| Redis feature → `detected_database: "redis"` | REQ-QPI-100 | Feature with "redis cache" → assert field populated |
| Non-DB feature → `detected_database: ""` | REQ-QPI-100 | Feature with "gRPC handler" → assert field empty |
| "All SQL uses string interpolation" anchor → replaced | REQ-QPI-200/201 | Assert anti-pattern detected and replacement uses `safe_param_syntax` |
| "All responses cached for 5 min" anchor → unchanged | REQ-QPI-200 | Assert non-SQL anchor passes through |
| `negative_scope` containing "no parameterized" → stripped | REQ-QPI-201 | Assert entry removed |
| TRIVIAL SELECT → complete scaffold | REQ-QPI-300 | Assert scaffold contains `@param` pattern, passes `validate_syntax()` |
| MODERATE transaction → stub scaffold | REQ-QPI-300 | Assert scaffold has signature + TODO body |
| Scaffold matches safe_patterns, not unsafe_patterns | REQ-QPI-302 | Assert regex validation |

### Integration Tests

| Test | Target | Method |
|------|--------|--------|
| Full plan ingestion with AlloyDB plan → seed has sanitized anchors | REQ-QPI-200 | End-to-end plan → seed → assert no "string interpolation" in obligations |
| Full plan ingestion → seed has query_scaffolds | REQ-QPI-300 | Assert scaffolds present for DB-facing tasks |
| Seed → spec builder → spec has "Query Implementation Scaffolds" section | REQ-QPI-301 | Assert P0 section in generated spec |

### Smoke Test

Re-run the online-boutique C# cartservice plan ingestion (the AlloyDB/Spanner/Redis plan). Verify:
1. AlloyDBCartStore seed has `detected_database: "postgresql"`, `security_sensitive: true`
2. Acceptance obligations say "parameterized queries" not "string interpolation"
3. `query_scaffolds` contains 3+ CRUD method skeletons with `@param` syntax
4. Subsequent Prime Contractor run produces AlloyDB code with `NpgsqlParameter` — no string interpolation
