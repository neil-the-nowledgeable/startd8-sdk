# Query-Informed Plan Ingestion — Implementation Plan

> **Requirements:** [REQ-QPI-QUERY_INFORMED_PLAN_INGESTION.md](REQ-QPI-QUERY_INFORMED_PLAN_INGESTION.md)
> **Date:** 2026-03-22
> **Phases:** 3 (Phase 1 unblocks AlloyDB fix immediately)

---

## Phase 1 — Anchor Sanitization + Database Detection (REQ-QPI-100, 200, 201, 400)

**Goal:** Seeds no longer encode SQL injection as acceptance criteria. No scaffolds yet — just clean seeds.

### Step 1.1: Anti-Pattern Anchor Detector

**New file:** `src/startd8/workflows/builtin/plan_ingestion_anchor_sanitizer.py`

```python
def classify_acceptance_anchor(
    anchor: str,
    detected_database: str = "",
    language: str = "",
) -> dict:
    """Classify an acceptance anchor as safe or anti-pattern.

    Returns:
        {"classified": "safe"} or
        {"classified": "anti_pattern", "reason": "...", "safe_replacement": "..."}
    """
```

**Logic:**
1. Check if anchor contains SQL keywords (SELECT/INSERT/UPDATE/DELETE) AND unsafe construction keywords (interpolation, concatenation, `$"`, `String.Format`, `f"`)
2. Check if anchor contains "no parameterized" or "not parameterized" or "intentional...injection"
3. If anti-pattern detected AND `detected_database` is known, look up `DatabasePatternRegistry.get(db, language).safe_param_syntax[0]` for the replacement text
4. Return classification dict

**Also add:**
```python
def sanitize_acceptance_obligations(
    obligations: list[str],
    detected_database: str,
    language: str,
) -> tuple[list[str], list[dict]]:
    """Sanitize a list of acceptance obligations.

    Returns:
        (sanitized_obligations, audit_trail)
    """
```

```python
def strip_conflicting_negative_scope(
    negative_scope: list[str],
    detected_database: str,
) -> tuple[list[str], list[str]]:
    """Remove negative_scope entries that conflict with safe query patterns.

    Returns:
        (cleaned_scope, stripped_entries)
    """
```

**Tests:** `tests/unit/workflows/test_anchor_sanitizer.py`
- "All SQL uses string interpolation" → anti_pattern, replaced with "All SQL uses parameterized queries (cmd.Parameters.AddWithValue(\"@id\", id))"
- "All responses cached for 5 min" → safe, passes through
- "No parameterized queries" negative_scope → stripped
- "No ORM usage" negative_scope → kept (not a security conflict)

### Step 1.2: Database Detection in Task Derivation

**Modify:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

**Location:** `_derive_tasks_from_features()` around line 2576, after feature context assembly.

**Add after existing context population (before acceptance_obligations extraction):**

```python
# REQ-QPI-100: Detect database from feature description + metadata
from startd8.query_prime.decomposer import detect_database_type
_feat_text = f"{feat.description} {' '.join(str(v) for v in ctx.values() if isinstance(v, str))}"
_detected_db = detect_database_type(_feat_text)
if _detected_db is not None:
    ctx["detected_database"] = _detected_db.value if hasattr(_detected_db, 'value') else str(_detected_db)
    ctx["security_sensitive"] = True
    # Look up safe param syntax for this database + target language
    try:
        from startd8.query_prime.patterns import DatabasePatternRegistry
        from startd8.languages import resolve_language
        _lang_id = resolve_language(ctx.get("target_files", [])).language_id if ctx.get("target_files") else "python"
        _pattern = DatabasePatternRegistry.get(_detected_db, _lang_id)
        if _pattern and _pattern.safe_param_syntax:
            ctx["safe_param_syntax"] = _pattern.safe_param_syntax[0]
    except Exception:
        pass
```

**Then modify the acceptance_obligations loop (lines 2581-2591):**

```python
# REQ-QPI-200/201: Sanitize acceptance anchors against unsafe query patterns
if acceptance_obligations and ctx.get("detected_database"):
    from startd8.workflows.builtin.plan_ingestion_anchor_sanitizer import (
        sanitize_acceptance_obligations,
    )
    _lang_id = ctx.get("_lang_id", "csharp")
    acceptance_obligations, _anchor_audit = sanitize_acceptance_obligations(
        acceptance_obligations, ctx["detected_database"], _lang_id,
    )
    if _anchor_audit:
        ctx["replaced_anchors"] = _anchor_audit

# REQ-QPI-201: Strip conflicting negative_scope entries
if ctx.get("negative_scope") and ctx.get("detected_database"):
    from startd8.workflows.builtin.plan_ingestion_anchor_sanitizer import (
        strip_conflicting_negative_scope,
    )
    ctx["negative_scope"], _stripped = strip_conflicting_negative_scope(
        ctx["negative_scope"], ctx["detected_database"],
    )
    if _stripped:
        ctx.setdefault("replaced_anchors", []).extend(
            {"original": s, "reason": "negative_scope_conflict"} for s in _stripped
        )
```

**Tests:** `tests/unit/workflows/test_plan_ingestion_query_detection.py`
- Feature with "AlloyDB" → `detected_database: "postgresql"`, `security_sensitive: True`
- Feature with "Redis cache" → `detected_database: "redis"`
- Feature with "gRPC handler" → no database fields
- Anchor sanitization runs only for database-detected features

### Step 1.3: Seed Task Field Population

**Modify:** `src/startd8/seeds/builder.py` — `derive_tasks()` or `_emit_seed()`

Ensure `detected_database` and `security_sensitive` from the task context are promoted to SeedTask model fields (they exist but are never set).

**Modify:** `src/startd8/workflows/builtin/plan_ingestion_emitter.py`

When emitting the seed, if no seed-level `security_contract` exists but per-task `detected_database` fields are populated, auto-derive the contract (REQ-QPI-401):

```python
databases = {t["config"]["context"].get("detected_database") for t in tasks if t["config"]["context"].get("detected_database")}
databases.discard("")
if databases and not seed.get("security_contract"):
    seed["security_contract"] = {
        "databases": sorted(databases),
        "source": "plan_ingestion_auto_detect",
    }
```

### Phase 1 Verification

Run plan ingestion on the online-boutique C# cartservice plan. Assert:
1. AlloyDBCartStore task has `detected_database: "postgresql"`, `security_sensitive: true`
2. SpannerCartStore task has `detected_database: "spanner"`
3. RedisCartStore task has `detected_database: "redis"`
4. AlloyDBCartStore's `acceptance_obligations` say "parameterized queries" not "string interpolation"
5. `negative_scope` no longer contains "no parameterized queries"
6. Seed-level `security_contract` is auto-derived with `databases: ["postgresql", "redis", "spanner"]`

---

## Phase 2 — Query Scaffold Assembly (REQ-QPI-101, 102, 300, 301)

**Goal:** TRIVIAL query operations get pre-approved parameterized method skeletons in the seed.

### Step 2.1: Query Decomposition at Ingestion Time

**Modify:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

After database detection (Step 1.2), add:

```python
# REQ-QPI-101: Decompose database features into query work items
if ctx.get("detected_database"):
    from startd8.query_prime.decomposer import decompose_feature
    work_items = decompose_feature(
        feature_id=tid,
        description=feat.description,
        target_files=ctx.get("target_files", []),
        metadata={"detected_database": ctx["detected_database"]},
    )
    if work_items:
        ctx["query_work_items"] = [
            {
                "id": wi.id,
                "operation": wi.operation_type.value,
                "database": wi.database.value,
                "tables": wi.tables,
                "parameters": [{"name": p.name, "type": p.param_type} for p in wi.parameters],
                "tier": "trivial" if is_trivial(wi) else "simple",
            }
            for wi in work_items
        ]
```

### Step 2.2: Scaffold Assembly Module

**New file:** `src/startd8/workflows/builtin/plan_ingestion_query_scaffold.py`

```python
def assemble_query_scaffolds(
    work_items: list[dict],
    language_id: str,
    database: str,
) -> list[dict]:
    """Produce parameterized method skeletons for TRIVIAL query work items.

    Returns:
        List of {"method_name": str, "code": str, "operation": str, "database": str, "tier": str}
    """
```

**Logic:**
1. For each work item with `tier == "trivial"`:
   - Call `query_prime.templates.generate(work_item)` → complete method
   - Validate with `LanguageProfile.validate_syntax()`
   - Verify at least one `safe_patterns` regex matches
   - If valid, include in scaffolds
2. For each work item with `tier == "simple"`:
   - Produce a stub scaffold: method signature + parameter declarations + `// TODO: implement using parameterized queries` body
3. Return scaffold list

**Tests:** `tests/unit/workflows/test_query_scaffold.py`
- PostgreSQL + C# SELECT → complete scaffold with `@param`
- PostgreSQL + C# UPSERT → stub scaffold with signature + TODO
- Scaffold passes `validate_syntax()`
- Scaffold matches `safe_patterns`, not `unsafe_patterns`

### Step 2.3: Scaffold Injection into Spec Builder

**Modify:** `src/startd8/implementation_engine/spec_builder.py`

In `build_spec_prompt()`, after the security guidance section injection, add:

```python
# REQ-QPI-301: Query scaffold injection at P0 priority
query_scaffolds = context.get("query_scaffolds")
if query_scaffolds and isinstance(query_scaffolds, list):
    scaffold_lines = [
        "## Query Implementation Scaffolds — MANDATORY\n",
        "These scaffolds use pre-approved parameterized query patterns.",
        "Implement the business logic within these method bodies.",
        "DO NOT replace the parameterization pattern with string interpolation.\n",
    ]
    for scaffold in query_scaffolds:
        scaffold_lines.append(f"### {scaffold.get('method_name', 'Query Method')} ({scaffold.get('operation', '')})")
        scaffold_lines.append(f"```csharp\n{scaffold.get('code', '')}\n```\n")
    prioritized.append((0, "query_scaffolds", "\n".join(scaffold_lines)))
```

### Phase 2 Verification

Run plan ingestion + Prime Contractor on the online-boutique C# cartservice plan. Assert:
1. AlloyDB seed has `query_scaffolds` with 3+ method skeletons
2. Each scaffold contains `NpgsqlParameter` / `AddWithValue` — no string interpolation
3. Spec includes "Query Implementation Scaffolds" section at P0
4. Generated AlloyDBCartStore.cs uses parameterized queries (no `$"SELECT...{userId}"`)
5. DQS for AlloyDB improves from 0.80 → 0.95+
6. `sql_injection_risk` findings drop from 6 → 0

---

## Phase 3 — Validation + Coverage + Contract Derivation (REQ-QPI-302, 303, 401)

### Step 3.1: Scaffold Validation Gate

**Add to:** `plan_ingestion_query_scaffold.py`

```python
def validate_scaffold(code: str, database: str, language: str) -> bool:
    """Validate a scaffold against syntax + safe/unsafe pattern checks."""
```

### Step 3.2: Coverage Tracking

**Add to:** `plan_ingestion_query_scaffold.py`

Track which (database, language, operation) combinations produced scaffolds vs fell back to LLM-only. Emit coverage report to seed metadata.

### Step 3.3: Security Contract Auto-Derivation

Already covered in Step 1.3 — promote from task-level `detected_database` to seed-level `security_contract`.

---

## Implementation Sequence

| Order | File | Change | Phase | Est. Lines |
|-------|------|--------|-------|------------|
| 1 | `plan_ingestion_anchor_sanitizer.py` (NEW) | Anti-pattern detection + replacement + negative_scope stripping | 1 | ~120 |
| 2 | `plan_ingestion_workflow.py` | Database detection + anchor sanitization in `_derive_tasks_from_features()` | 1 | ~40 |
| 3 | `plan_ingestion_emitter.py` | Auto-derive `security_contract` from per-task databases | 1 | ~15 |
| 4 | `test_anchor_sanitizer.py` (NEW) | Unit tests for sanitizer | 1 | ~100 |
| 5 | `test_plan_ingestion_query_detection.py` (NEW) | Integration tests for database detection | 1 | ~80 |
| 6 | `plan_ingestion_query_scaffold.py` (NEW) | Scaffold assembly from Query Prime templates | 2 | ~150 |
| 7 | `plan_ingestion_workflow.py` | Query decomposition + scaffold assembly call | 2 | ~30 |
| 8 | `spec_builder.py` | Scaffold injection into spec at P0 | 2 | ~20 |
| 9 | `test_query_scaffold.py` (NEW) | Scaffold tests | 2 | ~120 |
| 10 | `plan_ingestion_query_scaffold.py` | Validation gate + coverage tracking | 3 | ~60 |

**Total:** ~735 lines across 6 files (3 new, 3 modified)

---

## Key Files Reference

| File | Role |
|------|------|
| `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | Main ingestion — add detection + sanitization hooks |
| `src/startd8/workflows/builtin/plan_ingestion_contracts.py` | `_normalize_requirements_hints()` — anchor validation point |
| `src/startd8/workflows/builtin/plan_ingestion_emitter.py` | Seed emission — security_contract auto-derivation |
| `src/startd8/query_prime/decomposer.py` | `detect_database_type()`, `decompose_feature()` — reuse |
| `src/startd8/query_prime/patterns/__init__.py` | `DatabasePatternRegistry` — safe/unsafe pattern lookup |
| `src/startd8/query_prime/templates/crud.py` | CRUD templates — scaffold source |
| `src/startd8/query_prime/templates/health_check.py` | Health check templates — scaffold source |
| `src/startd8/implementation_engine/spec_builder.py` | Scaffold injection into spec at P0 |
| `src/startd8/seeds/builder.py` | SeedTask field population |
| `src/startd8/seeds/models.py` | SeedTask.detected_database, security_sensitive (exist, unpopulated) |

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Anchor sanitizer false positive (removes valid anchor) | Conservative detection: only SQL + interpolation/concat combo triggers. Audit trail preserves originals. |
| Scaffold syntax invalid for target language | REQ-QPI-302 validation gate. Failed scaffolds excluded, feature falls back to LLM-only. |
| Database detection false positive (non-DB feature flagged) | `detect_database_type()` uses the same heuristics Query Prime uses at generation time. Well-tested. |
| Plan ingestion performance (added Query Prime imports) | Lazy imports. Detection is regex-only (no LLM calls). Scaffold assembly uses existing templates (~1ms each). |
| Breaking existing non-DB features | DP-5 (additive). All changes gated by `if ctx.get("detected_database")`. Non-DB features untouched. |
