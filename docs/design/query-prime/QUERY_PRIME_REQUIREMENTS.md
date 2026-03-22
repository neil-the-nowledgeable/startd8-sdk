# Query Prime — Secure Query Generation Requirements

> **Version:** 1.1.0
> **Status:** DRAFT
> **Date:** 2026-03-19
> **Parent:** [PRIME_CONTRACTOR_PARADIGM.md](../prime-approach/PRIME_CONTRACTOR_PARADIGM.md)
> **Design Principle:** [ANZEN_DESIGN_PRINCIPLE.md](../../design-princples/ANZEN_DESIGN_PRINCIPLE.md) — Security Correctness by Design
> **Sibling:** [TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md](../prime/TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md) — same pattern (contract derivation → TODO detection → generation → verification), applied to security instead of observability
> **Scope:** Specialized Prime Contractor domain instantiation for generating effective, secure database queries; first implementation of the Anzen (安全) design principle within the Capability Delivery Pipeline
> **Motivation:** Security findings from C# Prime Contractor runs 078–079 (AlloyDB SQL injection, Spanner false positives, credential leakage) demonstrated that code generation pipelines produce real security vulnerabilities in database-facing code. A dedicated Query Prime module applies the Prime paradigm's DECOMPOSE→CLASSIFY→ROUTE→GENERATE→VERIFY loop specifically to query generation, where security is a first-class quality gate — not a post-hoc review finding. More broadly, Query Prime is the entry point for formalizing **security correctness by design** as a pipeline property — the same structural guarantee that TODO Completion provides for observability.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Goals and Non-Goals](#2-goals-and-non-goals)
3. [Architecture Overview](#3-architecture-overview)
4. [Model Tier Strategy](#4-model-tier-strategy)
5. [Query Decomposition](#5-query-decomposition-decompose)
6. [Query Classification](#6-query-classification-classify)
7. [Query Routing](#7-query-routing-route)
8. [Query Generation](#8-query-generation-generate)
9. [Security Verification](#9-security-verification-verify)
10. [Feedback Loop — Kaizen Integration](#10-feedback-loop--kaizen-integration)
11. [Pipeline Integration — Anzen End-to-End](#11-pipeline-integration--anzen-end-to-end)
12. [Security TODO Pattern — Query as Security TODO](#12-security-todo-pattern--query-as-security-todo)
13. [Profile Generation — Pre-Code Security Review](#13-profile-generation--pre-code-security-review)
14. [Traceability Matrix](#14-traceability-matrix)

---

## 1. Problem Statement

### 1.1 Observed Failures (C# Prime Contractor Runs 078–079)

The C# Online Boutique cartservice generation exposed three categories of query-related security failures:

| ID | Finding | Severity | Root Cause |
|----|---------|----------|------------|
| QP-F1 | **AlloyDB SQL injection** — `AlloyDBCartStore` uses string interpolation (`$"DELETE FROM {table} WHERE userId = '{userId}'"`) instead of parameterized queries (`NpgsqlParameter`) | CRITICAL | The reference implementation uses string interpolation; the generator faithfully reproduced the vulnerability. No security gate existed to flag parameterized-query absence in generated SQL. |
| QP-F2 | **Spanner false positives** — Semantic validator flagged Spanner queries as injection-vulnerable when they correctly use `SpannerParameterCollection` with `@userId` parameter binding | HIGH | The validator's SQL injection heuristic detected string concatenation patterns in Spanner client library code without understanding that `@`-prefixed parameters are safely bound. False positives inflated the semantic error count, reducing trust in the validator. |
| QP-F3 | **Credential leakage via connection strings** — `SpannerCartStore` logs the full connection string via `Console.WriteLine`; `AlloyDBCartStore` retrieves passwords from Secret Manager and constructs connection strings that could be logged | CRITICAL | No cross-cutting security requirement prohibited logging of secrets or connection strings. The generator had no guidance that credential-bearing strings require redaction. |
| QP-F4 | **Connection pool exhaustion** — `AlloyDBCartStore.AddItemAsync` creates a new `NpgsqlDataSource` on every call instead of reusing a singleton | HIGH | The generator reproduced a performance anti-pattern from the reference. No query-layer pattern validation checked for resource lifecycle correctness. |

### 1.2 Why a Dedicated Query Module

General-purpose code generation treats SQL/query code identically to business logic. This is insufficient because:

1. **Security asymmetry** — A bug in business logic causes incorrect behavior. A bug in query code causes data breach. The blast radius is fundamentally different.
2. **Validation gap** — The existing semantic validator (`validators/semantic_checks.py`) checks for Python AST issues (duplicate defs, bare except, phantom imports). It has no SQL/query-aware checks.
3. **False positive cost** — When validators produce false positives on safe query patterns (QP-F2), developers lose trust and disable validation, increasing risk.
4. **Pattern specificity** — Parameterized queries, connection pool management, credential handling, and query optimization are all well-understood patterns with deterministic validation rules. They should not require expensive LLM review.

---

## 2. Goals and Non-Goals

### 2.1 Goals

| ID | Goal |
|----|------|
| G-1 | **Eliminate SQL injection in generated code** — Every generated query that accepts external input MUST use parameterized queries (database-appropriate parameter binding). |
| G-2 | **Reduce false positives** — Query security validation MUST understand database-specific parameter binding syntax (e.g., `@param` for Spanner/Npgsql, `$1` for PostgreSQL, `?` for MySQL, `:param` for Oracle). |
| G-3 | **Cost-effective generation** — Use T3 (economy) models for query drafting and review orchestration; T1/T2 (standard/premium) models only for complex queries that fail T3 verification. |
| G-4 | **Credential safety** — Generated code that handles connection strings or secrets MUST follow redaction patterns; logging of credential-bearing values MUST be flagged. |
| G-5 | **Cross-database support** — Support query generation for at minimum: PostgreSQL/AlloyDB (Npgsql), Cloud Spanner, Redis, MySQL, SQLite. |
| G-6 | **Kaizen integration** — Feed query security outcomes back into the prompt loop so future runs avoid repeating the same vulnerabilities. |

### 2.2 Non-Goals

| ID | Non-Goal | Rationale |
|----|----------|-----------|
| NG-1 | Full SQL query optimization (index hints, execution plans) | Out of scope for v1; focus is correctness and security |
| NG-2 | ORM-specific code generation (EF Core migrations, SQLAlchemy models) | ORMs have their own safety guarantees; focus is raw query code |
| NG-3 | Runtime query monitoring or WAF integration | Query Prime operates at generation time, not runtime |
| NG-4 | Schema design or DDL generation | Separate concern; may be a future domain instantiation |

---

## 3. Architecture Overview

Query Prime is a **domain instantiation** of the Prime Contractor paradigm (see [PRIME_CONTRACTOR_PARADIGM.md](../prime-approach/PRIME_CONTRACTOR_PARADIGM.md)). It reuses the existing five-stage loop with query-specific implementations at each stage:

```
┌─────────────────┐
│  DECOMPOSE       │  Plan → discrete query work items (CRUD ops, joins, transactions)
└───────┬─────────┘
        │
        ▼
┌─────────────────┐
│  CLASSIFY        │  Extract query signals → assign tier (TRIVIAL/SIMPLE/MODERATE/COMPLEX)
└───────┬─────────┘
        │
        ▼
┌─────────────────┐
│  ROUTE           │  Tier → model selection (T3 draft → T1/T2 generate → T3 review)
└───────┬─────────┘
        │
        ▼
┌─────────────────┐
│  GENERATE        │  Produce query code with parameterization + credential handling
└───────┬─────────┘
        │
        ▼
┌─────────────────────────────────┐
│  VERIFY (Security-First)         │
│  ├── Injection detection         │
│  ├── Parameter binding check     │
│  ├── Credential redaction check  │
│  ├── Connection lifecycle check  │
│  └── Database-aware false        │
│      positive suppression        │
└─────────────────────────────────┘
```

### 3.1 Module Location

```
src/startd8/query_prime/
├── __init__.py              # Public API exports
├── engine.py                # QueryPrimeEngine — orchestrates the 5-stage loop
├── decomposer.py            # Query-specific work item decomposition
├── classifier.py            # Query complexity signals + tier assignment
├── router.py                # Model tier routing (T3→T1/T2 escalation)
├── generator.py             # Query code generation with security constraints
├── verifier.py              # Security-first verification pipeline
├── models.py                # Data models (QueryWorkItem, QuerySignals, QueryResult)
├── patterns/                # Database-specific parameter binding patterns
│   ├── __init__.py
│   ├── postgresql.py        # Npgsql / psycopg2 / asyncpg patterns
│   ├── spanner.py           # Cloud Spanner client patterns
│   ├── redis.py             # Redis command patterns
│   ├── mysql.py             # MySQL Connector / pymysql patterns
│   └── sqlite.py            # sqlite3 / aiosqlite patterns
├── security/                # Security validation rules
│   ├── __init__.py
│   ├── injection.py         # SQL injection detection (language-aware)
│   ├── credentials.py       # Connection string / secret handling
│   └── lifecycle.py         # Connection/pool lifecycle validation
└── templates/               # Deterministic query templates (TRIVIAL tier)
    ├── __init__.py
    ├── crud.py              # Basic CRUD query templates
    └── health_check.py      # Health check query templates (SELECT 1, PING)
```

---

## 4. Model Tier Strategy

The core innovation of Query Prime is **asymmetric model allocation**: use cheap models for the high-volume work (drafting, orchestration, review scaffolding) and expensive models only where they demonstrably produce better results.

### REQ-QP-100: Three-Role Model Architecture

| Role | Model Tier | Purpose | When Used |
|------|-----------|---------|-----------|
| **Drafter** | T3 (economy: Haiku, Gemini Flash) | Produce initial query specification from work item description; generate review checklists; orchestrate the generation loop | Every query work item |
| **Generator** | T1 (premium: Opus, Gemini Pro) or T2 (standard: Sonnet) | Generate the actual query code with correct parameterization, error handling, and database idioms | When T3 draft verification fails OR query is classified MODERATE/COMPLEX |
| **Reviewer** | T3 (economy) | Run structured security checklist against generated code; produce pass/fail verdict with diagnostics | Every query work item (post-generation) |

**Acceptance criteria:**
- T3 model handles ≥60% of query work items end-to-end (draft + review only, no T1/T2 call) for TRIVIAL/SIMPLE tiers
- T1/T2 model is invoked only when: (a) the query is classified MODERATE or COMPLEX, or (b) T3-generated code fails verification
- Cost per query work item for TRIVIAL/SIMPLE tier SHALL be ≤$0.01 (T3-only path)
- Escalation from T3→T2→T1 follows the existing `GN-004` escalation pattern

### REQ-QP-101: Draft-Generate-Review Pipeline

```
T3 Drafter                    T1/T2 Generator              T3 Reviewer
───────────                   ────────────────              ───────────
1. Read work item
2. Produce query spec
   (tables, params, ops)
3. Classify complexity
4. If TRIVIAL → template
   If SIMPLE → T3 generate
   If MODERATE → T2 generate  ←── 5. Generate query code
   If COMPLEX → T1 generate   ←── 5. Generate query code
                                                           6. Security checklist
                                                           7. Parameterization check
                                                           8. Credential check
                                                           9. Verdict: PASS/FAIL
                              ←── 10. If FAIL: retry
                                      with error context
```

**Acceptance criteria:**
- Maximum 2 retry cycles per work item before escalation to next tier
- Retry context SHALL include the specific verification failure (not just "failed")
- T3 drafter output SHALL be a structured JSON spec, not prose

---

## 5. Query Decomposition (DECOMPOSE)

### REQ-QP-200: Query Work Item Structure

Each query work item extends the base Prime paradigm work item (DC-001 through DC-022) with query-specific fields:

| Field | Type | Description |
|-------|------|-------------|
| `database` | enum | Target database system (postgresql, spanner, redis, mysql, sqlite) |
| `operation_type` | enum | CRUD category (select, insert, update, delete, upsert, transaction, health_check) |
| `tables` | list[str] | Tables/collections involved |
| `parameters` | list[ParameterSpec] | External inputs that MUST be parameterized |
| `joins` | list[JoinSpec] | Join specifications (if multi-table) |
| `transaction_boundary` | optional[str] | Transaction scope (none, single_statement, multi_statement, distributed) |
| `credential_sources` | list[str] | Where connection credentials come from (env_var, secret_manager, config_file) |
| `target_language` | str | Host language for the query code (csharp, python, go, java, nodejs) |
| `target_framework` | str | Database client library (npgsql, psycopg2, spanner_client, redis_py, etc.) |

### REQ-QP-201: Decomposition from Broader Code Generation

When Query Prime operates within a Prime Contractor run (not standalone), it receives work items from the parent pipeline:

**Acceptance criteria:**
- The parent Prime Contractor workflow MAY tag features as `query-bearing` during DECOMPOSE
- Query Prime extracts query work items from the feature's implementation contract
- Each query method (e.g., `GetCartAsync`, `AddItemAsync`, `EmptyCartAsync`) becomes a separate query work item
- Dependencies between query items reflect data flow (e.g., "check existence before upsert")

### REQ-QP-202: Health Check Query Pattern

Health check queries (`Ping()`, liveness probes) are a recurring source of underspecification (see QP-F4, R2-S2, R5-F3). Query Prime SHALL provide deterministic templates:

| Database | Health Check Query | Implementation |
|----------|-------------------|----------------|
| PostgreSQL/AlloyDB | `SELECT 1` | `await using var cmd = dataSource.CreateCommand(); cmd.CommandText = "SELECT 1"; await cmd.ExecuteScalarAsync();` |
| Spanner | `connection.Open()` + `connection.Close()` | Open/close Spanner connection within try/catch |
| Redis | `PING` | `await cache.PingAsync()` or `await cache.GetAsync("health")` |
| MySQL | `SELECT 1` | `cursor.execute("SELECT 1"); cursor.fetchone()` |
| SQLite | `SELECT 1` | `cursor.execute("SELECT 1")` |

**Acceptance criteria:**
- Health check queries SHALL be classified as TRIVIAL (template-only, no LLM call)
- Templates SHALL include proper error handling (catch database-specific exceptions, return bool)
- Templates SHALL NOT log connection strings or credentials

---

## 6. Query Classification (CLASSIFY)

### REQ-QP-300: Query Complexity Signals

Query-specific signals extending the Prime paradigm's `CL-010` through `CL-013`:

| Signal | Type | Description | Source |
|--------|------|-------------|--------|
| `table_count` | int | Number of tables involved | Decomposition |
| `join_count` | int | Number of joins | Decomposition |
| `has_subquery` | bool | Contains nested SELECT | Spec analysis |
| `has_transaction` | bool | Requires transaction boundary | Decomposition |
| `has_dynamic_columns` | bool | Column set varies at runtime | Spec analysis |
| `has_aggregate` | bool | Uses GROUP BY, HAVING, window functions | Spec analysis |
| `parameter_count` | int | Number of external parameters | Decomposition |
| `has_upsert` | bool | INSERT ON CONFLICT / MERGE semantics | Spec analysis |
| `target_framework_familiarity` | float | How well the model tier handles this framework (from Kaizen history) | Kaizen feedback |
| `prior_injection_failure` | bool | A previous run produced injection in this pattern | Kaizen feedback |

### REQ-QP-301: Tier Mapping

| Tier | Criteria | Example |
|------|----------|---------|
| **TRIVIAL** | `table_count == 1` AND `join_count == 0` AND `operation_type in (health_check,)` AND template exists | `SELECT 1`, `PING` |
| **SIMPLE** | `table_count <= 2` AND `join_count <= 1` AND NOT `has_subquery` AND NOT `has_transaction` AND NOT `has_dynamic_columns` | Single-table CRUD, simple lookup with one join |
| **MODERATE** | `table_count <= 4` AND (`has_transaction` OR `has_aggregate` OR `has_upsert`) AND NOT `has_dynamic_columns` | Multi-table transaction, upsert with conflict resolution |
| **COMPLEX** | `table_count > 4` OR `has_dynamic_columns` OR `has_subquery` with aggregate OR `prior_injection_failure` | Dynamic reporting queries, cross-schema joins, queries with prior security failures |

**Acceptance criteria:**
- `prior_injection_failure == True` SHALL force minimum MODERATE tier (never TRIVIAL/SIMPLE)
- Classification SHALL be a pure function per `CL-001`
- All thresholds SHALL be configurable per `CL-005`

---

## 7. Query Routing (ROUTE)

### REQ-QP-400: Tier-to-Model Mapping

| Tier | Drafter | Generator | Reviewer | Estimated Cost |
|------|---------|-----------|----------|----------------|
| **TRIVIAL** | T3 | None (template) | T3 (structural only) | ~$0.002 |
| **SIMPLE** | T3 | T3 (self-generate) | T3 | ~$0.008 |
| **MODERATE** | T3 | T2 (Sonnet/Gemini Pro) | T3 | ~$0.05 |
| **COMPLEX** | T3 | T1 (Opus) | T3 + T2 (dual review) | ~$0.15 |

**Acceptance criteria:**
- COMPLEX queries receive dual review: T3 for structural checks + T2 for semantic security review
- Escalation path: T3 fail → T2 retry → T1 retry → FAILED (max 2 escalations per `GN-004`)
- Budget ceiling per work item SHALL be configurable (default: $0.50)

### REQ-QP-401: Effectiveness-Based Routing

After the initial Kaizen feedback loop accumulates data (≥10 runs), routing SHALL incorporate historical effectiveness:

**Acceptance criteria:**
- If T3 historically succeeds ≥80% on SIMPLE queries for a given `target_framework`, continue routing SIMPLE→T3
- If T3 success rate drops below 60% for a framework, auto-escalate SIMPLE→T2 for that framework
- Effectiveness metrics: parameterization correctness, first-pass verification success rate, injection-free rate
- Routing adjustments SHALL be logged with rationale for forensic analysis

---

## 8. Query Generation (GENERATE)

### REQ-QP-500: Parameterization-First Generation

All generated queries that accept external input SHALL use parameterized queries. This is a **hard constraint**, not a suggestion.

**Acceptance criteria:**
- The generation prompt SHALL explicitly instruct: "Use parameterized queries. NEVER use string interpolation or concatenation for user-supplied values."
- For each `target_framework`, the prompt SHALL include the framework-specific parameterization syntax:
  - Npgsql (C#): `cmd.Parameters.AddWithValue("@userId", userId)`
  - psycopg2 (Python): `cursor.execute("SELECT * FROM t WHERE id = %s", (user_id,))`
  - Spanner (C#): `new SpannerParameterCollection { { "userId", SpannerDbType.String, userId } }`
  - node-postgres (Node.js): `client.query('SELECT * FROM t WHERE id = $1', [userId])`
- Generated code that uses string interpolation for SQL values SHALL fail verification unconditionally

### REQ-QP-501: Connection Lifecycle Patterns

Generated query code SHALL follow proper connection/pool lifecycle patterns:

**Acceptance criteria:**
- `DataSource` / `ConnectionPool` objects SHALL be created once (constructor/init) and reused
- Individual query methods SHALL NOT create new data sources (QP-F4 prevention)
- Connections SHALL be properly disposed (`using`/`with`/`defer`/`try-finally` per language)
- Connection string construction SHALL be separate from connection usage

### REQ-QP-502: Credential Handling Patterns

Generated code that handles database credentials SHALL follow secure patterns:

**Acceptance criteria:**
- Connection strings containing passwords SHALL NOT be logged (QP-F3 prevention)
- Secret retrieval (e.g., Secret Manager) SHALL be isolated in a dedicated method
- Generated code SHALL include redaction before any logging: `log.info(f"Connecting to {host}:{port}/{db}")` (no password)
- Health check and diagnostic methods SHALL NOT expose connection details

### REQ-QP-503: Reference Implementation Deviation Policy

When generating queries that match a reference implementation, Query Prime SHALL deviate from the reference if the reference contains a known security vulnerability:

**Acceptance criteria:**
- If the reference uses string interpolation for SQL, Query Prime SHALL generate parameterized queries instead
- A `// SECURITY: Parameterized query replaces reference string interpolation` comment SHALL mark deviations
- Structural equivalence with the reference is subordinate to security correctness for query code
- This is the key lesson from QP-F1: the generator must NOT faithfully reproduce security vulnerabilities

---

## 9. Security Verification (VERIFY)

### REQ-QP-600: Injection Detection (Database-Aware)

The injection detector SHALL understand database-specific parameter binding to avoid false positives (QP-F2 prevention):

| Database Client | Safe Parameter Syntax | Unsafe Syntax |
|----------------|----------------------|---------------|
| Npgsql (C#) | `@paramName` bound via `NpgsqlParameter` | `$"{value}"` or `"'" + value + "'"` in SQL string |
| Spanner (C#) | `@paramName` bound via `SpannerParameterCollection` | String concat in SQL string |
| psycopg2 (Python) | `%s` with tuple arg | f-string or `.format()` in SQL string |
| node-postgres (Node.js) | `$1, $2` with array arg | Template literal `${value}` in SQL string |
| MySQL Connector | `%s` or `%(name)s` with dict/tuple | f-string or concat in SQL string |
| sqlite3 (Python) | `?` with tuple arg | f-string in SQL string |

**Acceptance criteria:**
- Each database pattern module SHALL define: `safe_patterns: list[regex]` and `unsafe_patterns: list[regex]`
- Detection SHALL operate on the host language AST (not raw text) where available, to avoid matching parameter syntax inside comments or string literals that aren't SQL
- Spanner's `@param` syntax SHALL NOT trigger false positives (QP-F2 fix)
- A test suite SHALL include both true positive (real injection) and true negative (safe parameterization) cases per database

### REQ-QP-601: Credential Leakage Detection

**Acceptance criteria:**
- Detect `Console.WriteLine`, `print()`, `log.*`, `logger.*` calls where the argument contains a variable identified as a connection string or secret
- Connection string variables identified by: name contains `connectionString`, `connStr`, `password`, `secret`, `credential`, `apiKey`; OR is the return value of a secret manager call
- False positive mitigation: allow logging of `host`, `port`, `database` individually (just not the full connection string or password)

### REQ-QP-602: Connection Lifecycle Verification

**Acceptance criteria:**
- Detect `DataSource.Create()` or `new Connection()` inside query methods (should be in constructor/init only)
- Detect missing `using`/`with`/`defer`/`try-finally` on connection or command objects
- Detect missing `Dispose()`/`close()` on connections not in a `using`/`with` block

### REQ-QP-603: Verification Pipeline Order

```
1. Syntax check (host language)           — compilation gate
2. Injection detection (REQ-QP-600)       — hard fail, no override
3. Credential leakage (REQ-QP-601)        — hard fail, no override
4. Connection lifecycle (REQ-QP-602)      — warning (upgradeable to fail)
5. Query correctness (LLM review)         — T3 structured checklist
6. Performance patterns (optional)        — advisory only in v1
```

**Acceptance criteria:**
- Steps 2 and 3 are **deterministic** (no LLM call required) — they use the pattern modules from `patterns/`
- A single injection finding fails the entire work item (zero tolerance)
- Credential leakage findings fail the work item (zero tolerance)
- Connection lifecycle findings produce warnings that are promoted to failures after Kaizen data shows correlation with production issues

---

## 10. Feedback Loop — Kaizen Integration

### REQ-QP-700: Query Security Metrics

Query Prime SHALL emit Kaizen-compatible metrics for cross-run trending:

| Metric | Type | Description |
|--------|------|-------------|
| `injection_found_count` | counter | Injections detected before commit (caught by verification) |
| `injection_escaped_count` | counter | Injections that passed verification (found in post-mortem) |
| `false_positive_count` | counter | Safe patterns incorrectly flagged as injections |
| `parameterization_rate` | gauge | Percentage of query methods using parameterized queries |
| `credential_leak_found_count` | counter | Credential leakage detected |
| `t3_sufficiency_rate` | gauge | Percentage of queries where T3 generation passed verification |
| `escalation_rate` | gauge | Percentage of queries requiring T2/T1 escalation |
| `cost_per_query` | histogram | Dollar cost per query work item by tier |

### REQ-QP-701: Prompt Feedback Injection

When a prior run produced injection findings for a specific database/framework combination, subsequent runs SHALL inject Kaizen hints into the generation prompt:

**Acceptance criteria:**
- Hint format: `"SECURITY WARNING: Prior run {run_id} produced SQL injection in {framework} queries. Use {safe_pattern} for all external inputs."`
- Hints are P1 priority in the prompt budget (see `implementation_engine/budget.py`)
- Maximum 3 Kaizen hints per generation prompt (to avoid overwhelming the generator)

### REQ-QP-702: False Positive Tracking

To prevent the Spanner false positive problem (QP-F2) from recurring:

**Acceptance criteria:**
- When a developer marks a finding as false positive, record: `(database, framework, pattern_hash, finding_type)`
- After 3 confirmed false positives for the same pattern, auto-suppress with WARNING log
- Suppressed patterns are reviewed in Kaizen post-mortem analysis
- No auto-suppression for injection findings (injection is always reviewed)

---

## 11. Pipeline Integration — Anzen End-to-End

Query Prime does not operate in isolation. It is the first implementation of the [Anzen design principle](../../design-princples/ANZEN_DESIGN_PRINCIPLE.md) — security correctness as a structural pipeline property. This section specifies how Query Prime wires into the Capability Delivery Pipeline at each stage, mirroring the pattern established by the TODO Completion workflow for observability.

### REQ-QP-800: Security Contract Derivation at EXPORT (Stage 4)

The ContextCore EXPORT stage MUST derive a security contract from the pipeline's accumulated context and emit it in `onboarding-metadata.json`, analogous to the instrumentation contract (REQ-TCW-003).

**Acceptance criteria:**
1. `onboarding-metadata.json` includes a top-level `security_contracts` key: dict keyed by service ID
2. Each security contract includes: `query_security` (databases, client libraries, parameter syntax, safe/unsafe patterns, resource lifecycle), `credential_handling` (secret sources, connection string rules), `health_checks` (per-store operations, exposure rules)
3. Security contract is derived from: `.contextcore.yaml` `spec.security.data_stores` + language profile pattern databases + Kaizen history
4. If `.contextcore.yaml` has no `spec.security` section, fall back to plan metadata scan for database client imports (graceful degradation — same pattern as REQ-TCW-003 criterion 4)
5. Contract is checksummed and included in the provenance chain

### REQ-QP-801: Security-Aware Task Enrichment at PLAN-INGESTION (Stage 5)

During plan ingestion, tasks that target database-facing files MUST be enriched with security contract context.

**Acceptance criteria:**
1. Tasks whose `target_files` import a database client library (detected via language profile `framework_imports`) are tagged `security_sensitive: true`
2. `gen_context` for tagged tasks includes the relevant `security_contract` section from `onboarding-metadata.json`
3. Complexity classification treats `security_sensitive` tasks as minimum MODERATE tier for the *generation* model (never routed to T3 for code generation), even if query signals would classify as SIMPLE
4. The security contract context is forwarded through the Mottainai artifact chain (not re-derived at each stage)

### REQ-QP-802: Security-Aware Generation at CONTRACTOR (Stage 6)

The Prime Contractor (and Query Prime when invoked as a sub-engine) MUST use the security contract in spec/draft/review prompts.

**Acceptance criteria:**
1. Spec prompt includes database-specific parameterization patterns from the security contract
2. Draft prompt includes a P0 (highest priority, never trimmed by budget enforcement) section: `SECURITY CONSTRAINT: Use parameterized queries for all external inputs. See security contract for {database} patterns.`
3. Review prompt includes a structured security checklist derived from the contract (injection, credentials, lifecycle)
4. Kaizen hints from prior security findings are injected as P1 sections per REQ-QP-701

### REQ-QP-803: Pre-EXPORT Security Verification Gate

Before generated code is exported from the pipeline, a security verification pass MUST run. This is the **Anzen gate** — the structural guarantee that insecure code cannot exit the pipeline.

**Acceptance criteria:**
1. Deterministic checks (injection detection, credential leakage, resource lifecycle, health check exposure) run on all files tagged `security_sensitive`
2. Injection and credential leakage findings are **hard failures** — the file is not exported
3. Resource lifecycle findings are warnings by default, upgradeable to failures via `spec.security.sensitivity: high`
4. Gate produces a `SecurityVerificationResult` per file: `{file, checks_passed, checks_failed, checks_warned, details[]}`
5. Aggregate results are written to `{output_dir}/security-verification.json` alongside other pipeline artifacts
6. Gate runs **after** the TODO Completion instrumentation pass (if enabled) but **before** EXPORT — security verification covers both pass-one and instrumentation code

### REQ-QP-804: Kaizen Security Metrics in Post-Mortem

Security outcomes MUST feed the Kaizen loop as first-class quality dimensions.

**Acceptance criteria:**
1. `kaizen-metrics.json` includes: `injection_found_pre_export`, `injection_escaped`, `false_positive_count`, `credential_leak_prevented`, `security_todo_completion_rate`, `security_contract_coverage`
2. `prime-postmortem-report.json` includes a `security` section per feature with: parameterization correctness, credential handling compliance, lifecycle compliance
3. Cross-run trends track security metrics alongside success rate, cost, and instrumentation coverage
4. New root cause category `SECURITY_VIOLATION` added to `prime_postmortem.py` RootCause enum (alongside existing 16 causes)

---

## 12. Security TODO Pattern — Query as Security TODO

This section defines how queries are represented as a type of security TODO within the existing TODO detection and completion pipeline. This bridges Query Prime (the generation engine) with the TODO Completion workflow (the pipeline automation).

### REQ-QP-900: Category S Classification

The TODO scanner (REQ-TCW-100) MUST be extended to classify security-sensitive TODOs as Category S, orthogonal to the existing A/B/C classification.

**Acceptance criteria:**
1. A TODO is Category S when it resides in a file that imports a database client library (per language profile `framework_imports`)
2. Category S is a **modifier**, not a replacement: a TODO can be `A+S` (commented-out query code), `B+S` (contract-derivable query implementation), or `C+S` (underspecified query)
3. `C+S` TODOs are flagged for **mandatory human review** — they represent security gaps where the pipeline has insufficient context to generate safe code
4. Category S classification records which `security_contract.query_security.databases[]` entry applies
5. `TodoEntry` gains: `security_sensitive: bool`, `security_contract_ref: Optional[str]` (database ID from security contract)

### REQ-QP-901: Security Contract Context Injection for Category S TODOs

Category S TODOs that are also Category B (contract-derivable) MUST receive security contract context in their task specs, in addition to any instrumentation contract context.

**Acceptance criteria:**
1. `gen_context` includes both `instrumentation_contract` (if applicable) and `security_contract` sections
2. Security contract context includes: parameter syntax for the target database, safe/unsafe patterns, resource lifecycle rules, credential handling rules
3. When a method both emits metrics (Category B instrumentation) and executes queries (Category S), both contracts are composed into the task spec — the generated code must satisfy both
4. Example: `GetCartAsync` in AlloyDB cart store is both `B+S`: it needs OTel span attributes (instrumentation) AND parameterized queries (security)

### REQ-QP-902: Security TODO Inventory

The TODO inventory (REQ-TCW-103) MUST include security-specific fields for Category S entries.

**Acceptance criteria:**
1. `TodoInventory` schema gains: `security_todos: int` (count of Category S entries), `security_todo_details: List[SecurityTodoEntry]`
2. Each `SecurityTodoEntry` includes: `todo_id`, `category` (A+S, B+S, C+S), `database_id`, `client_library`, `operation_type` (select/insert/update/delete/upsert/health_check), `parameter_count` (number of external inputs that must be parameterized), `security_contract_checksum`
3. Security TODO inventory is included in Kaizen index for cross-run tracking
4. Inventory is queryable: "how many Category S TODOs exist per database?" enables targeted improvement

### REQ-QP-903: Post-Validation via Security TODOs

After code generation (pass-one or instrumentation pass), the security verification gate (REQ-QP-803) MUST validate generated code against the security TODOs that were identified pre-generation.

**Acceptance criteria:**
1. For each Category S TODO that was resolved (status: `completed`), verify:
   - The generated code uses the parameterization method specified in the security contract
   - No string interpolation or concatenation appears in SQL/query contexts
   - Credential variables are not passed to logging functions
   - Resource creation (DataSource, Connection) occurs in the correct scope (constructor vs per-request)
2. For each Category S TODO that was NOT resolved (status: `pending` or `deferred`), verify:
   - The pre-existing code (from reference or pass-one) is flagged as a known security gap
   - The gap is reported in the postmortem with the specific security contract entries that are unsatisfied
3. The verification result cross-references TODO IDs: `todo_id → verification_status → specific_checks_passed/failed`
4. This creates a **closed loop**: TODOs identified pre-generation → code generated with contract context → code verified against the same TODOs post-generation

---

## 13. Profile Generation — Pre-Code Security Review

One of Query Prime's most valuable capabilities is the ability to evaluate security posture **before any code is generated**. By deriving the security contract from the pipeline's accumulated context (plan, requirements, language profile), the pipeline can identify security concerns during profile generation — before committing LLM cost to code generation.

### REQ-QP-1000: Security Profile Generation

The pipeline MUST support a `--security-profile` mode that produces a security analysis without generating code.

**Acceptance criteria:**
1. Input: plan document + requirements + `.contextcore.yaml` (same inputs as a normal pipeline run)
2. Output: `security-profile.json` containing:
   - Derived security contract (REQ-QP-800)
   - Predicted security TODOs: which methods/files will likely need parameterized queries, credential handling, lifecycle management
   - Risk assessment: per-database risk level based on query complexity signals and Kaizen history
   - Estimated verification coverage: which security checks will be deterministic vs LLM-assisted
3. No LLM calls required for the profile — it is a Hitsuzen derivation from plan + language profile + Kaizen history
4. Cost: $0.00 (no generation, no API calls)

### REQ-QP-1001: Profile-Based Security Review

The security profile MUST be reviewable by a human or T3 model before committing to code generation.

**Acceptance criteria:**
1. `security-profile.json` includes a `review_checklist` section with yes/no questions:
   - "Does the plan specify parameterized queries for {database}?" (checks plan text)
   - "Does the plan prohibit logging of connection strings?" (checks plan text)
   - "Are all credential sources declared in the manifest?" (checks `.contextcore.yaml`)
   - "Does the language profile have safe patterns for {client_library}?" (checks pattern module coverage)
2. A T3 model review of the profile costs ~$0.003 and catches:
   - Missing `spec.security` declarations in the manifest
   - Plan text that specifies string interpolation for SQL (QP-F1 early detection)
   - Databases in the plan that have no pattern module (coverage gap)
3. Profile review can be run as a CI check on plan PRs — security issues caught before any code is written

### REQ-QP-1002: Profile-to-Contract Pipeline

When a security profile is approved (by human or T3 review), it becomes the security contract for the generation run.

**Acceptance criteria:**
1. `--security-profile {path}` flag on `run-prime-contractor.sh` loads a pre-approved profile
2. The loaded profile's security contract is used instead of deriving a new one at EXPORT
3. If the plan has changed since the profile was generated (checksum mismatch), the pipeline warns and re-derives
4. This enables the workflow: generate profile → review profile → approve → run generation with pre-approved security constraints

---

## 14. Traceability Matrix

| Requirement | Addresses Finding | Prime Paradigm Stage | Verification |
|-------------|------------------|---------------------|-------------|
| REQ-QP-100 | Cost efficiency | ROUTE | Cost tracking per work item |
| REQ-QP-101 | Cost efficiency | ROUTE/GENERATE | Tier distribution logging |
| REQ-QP-200 | All | DECOMPOSE | Work item completeness check |
| REQ-QP-201 | QP-F1 | DECOMPOSE | Integration test with Prime Contractor |
| REQ-QP-202 | R2-S2, R5-F3 | DECOMPOSE | Template coverage for all 5 databases |
| REQ-QP-300 | All | CLASSIFY | Unit tests for signal extraction |
| REQ-QP-301 | QP-F1 (prior_injection_failure) | CLASSIFY | Test: injection history forces MODERATE+ |
| REQ-QP-400 | Cost efficiency | ROUTE | Cost per tier tracking |
| REQ-QP-401 | Cost efficiency | ROUTE | A/B effectiveness after 10+ runs |
| REQ-QP-500 | QP-F1 | GENERATE | Injection-free output for all databases |
| REQ-QP-501 | QP-F4 | GENERATE | No per-call DataSource creation |
| REQ-QP-502 | QP-F3 | GENERATE | No credential logging |
| REQ-QP-503 | QP-F1 | GENERATE | Deviation from insecure references |
| REQ-QP-600 | QP-F1, QP-F2 | VERIFY | True positive + true negative test suite |
| REQ-QP-601 | QP-F3 | VERIFY | Credential leak detection tests |
| REQ-QP-602 | QP-F4 | VERIFY | Lifecycle check tests |
| REQ-QP-603 | All | VERIFY | Pipeline order enforcement |
| REQ-QP-700 | Kaizen | FEEDBACK | Metric emission tests |
| REQ-QP-701 | QP-F1 | FEEDBACK | Hint injection in subsequent runs |
| REQ-QP-702 | QP-F2 | FEEDBACK | False positive suppression after 3 confirmations |
| REQ-QP-800 | Anzen pipeline | EXPORT (Stage 4) | Security contract in onboarding-metadata.json |
| REQ-QP-801 | Anzen pipeline | PLAN-INGESTION (Stage 5) | security_sensitive tag on database-facing tasks |
| REQ-QP-802 | Anzen pipeline | CONTRACTOR (Stage 6) | P0 security constraint in draft prompt |
| REQ-QP-803 | All (Anzen gate) | Pre-EXPORT | SecurityVerificationResult per file |
| REQ-QP-804 | Kaizen + Anzen | Post-EXPORT | SECURITY_VIOLATION root cause in postmortem |
| REQ-QP-900 | QP-F1, QP-F3, QP-F4 | TODO Detection | Category S classification in TODO scanner |
| REQ-QP-901 | QP-F1 | TODO Completion | Dual contract injection (instrumentation + security) |
| REQ-QP-902 | All | TODO Inventory | SecurityTodoEntry schema extension |
| REQ-QP-903 | All (closed loop) | Post-Validation | TODO-to-verification cross-reference |
| REQ-QP-1000 | Cost + early detection | Profile Generation | $0.00 security-profile.json |
| REQ-QP-1001 | QP-F1 (early detection) | Profile Review | T3 review of profile (~$0.003) |
| REQ-QP-1002 | Mottainai (reuse) | Profile-to-Contract | Pre-approved profile as contract input |

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **T1 model** | Premium tier LLM (Opus, Gemini Pro) — highest capability, highest cost |
| **T2 model** | Standard tier LLM (Sonnet, Gemini Flash Pro) — balanced capability/cost |
| **T3 model** | Economy tier LLM (Haiku, Gemini Flash) — lowest cost, sufficient for structured tasks |
| **Parameterized query** | SQL query where external values are bound via the database driver's parameter mechanism, not interpolated into the query string |
| **String interpolation** | Constructing SQL by embedding values directly into the query string (e.g., `$"...{value}..."`) — primary injection vector |
| **Query work item** | A discrete unit of query code to generate (one method, one CRUD operation) |
| **Kaizen hint** | A prompt-injected lesson from a prior run's failure, steering the generator away from known mistakes |
| **Security contract** | Structured specification derived from pipeline context declaring what security properties generated code must have (analog of instrumentation contract) |
| **Category S** | Security-sensitive TODO modifier — orthogonal to A/B/C, indicates the TODO involves database-facing code |
| **Anzen gate** | Pre-EXPORT deterministic verification that ensures insecure code cannot exit the pipeline |
| **Security profile** | Pre-generation security analysis derived without LLM calls — identifies security concerns before committing to code generation |

## Appendix B: Related Documents

| Document | Relationship |
|----------|-------------|
| [ANZEN_DESIGN_PRINCIPLE.md](../../design-princples/ANZEN_DESIGN_PRINCIPLE.md) | Governing design principle — security correctness by design |
| [PRIME_CONTRACTOR_PARADIGM.md](../prime-approach/PRIME_CONTRACTOR_PARADIGM.md) | Parent paradigm — Query Prime instantiates this |
| [TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md](../prime/TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md) | Sibling pattern — same contract→TODO→generate→verify loop for observability |
| [KAIZEN_CSHARP_REQUIREMENTS.md](../prime-contractor-csharp/KAIZEN_CSHARP_REQUIREMENTS.md) | C# quality system — semantic checks that produced QP-F2 |
| [CSHARP_PRIME_CONTRACTOR_REQUIREMENTS.md](../prime-contractor-csharp/CSHARP_PRIME_CONTRACTOR_REQUIREMENTS.md) | C# generation requirements — source of QP-F1, QP-F3, QP-F4 |
| [plan-csharp.md](../prime-contractor-csharp/plan-csharp.md) | C# implementation plan — contains AlloyDB/Spanner contracts |
| [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) | Kaizen quality system — feedback loop integration point |
| [MOTTAINAI_DESIGN_PRINCIPLE.md](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Artifact forwarding — security contract follows same pattern |
| [HITSUZEN_DESIGN_PRINCIPLE.md](../../design-princples/HITSUZEN_DESIGN_PRINCIPLE.md) | Deterministic derivation — security profiles are Hitsuzen outputs |

## Appendix C: Data Flow — End-to-End Security Pipeline

```
ContextCore                                     StartD8 SDK
──────────                                      ───────────

Stage 0: CREATE
  .contextcore.yaml
  └── spec.security.data_stores ──────────┐
      (alloydb/npgsql, spanner, redis)    │
                                          │
Stage 4: EXPORT                           │
  onboarding-metadata.json                │
  ├── instrumentation_contracts    ←──────┤── (existing: REQ-TCW-003)
  └── security_contracts           ←──────┘── (NEW: REQ-QP-800)
      ├── query_security (per database)
      │   ├── parameter_syntax
      │   ├── safe_patterns / unsafe_patterns
      │   └── resource_lifecycle
      ├── credential_handling
      └── health_checks
              │
              ══════════ OPTIONAL: Profile Review (REQ-QP-1000) ══════
              │           $0.00 security-profile.json
              │           T3 review (~$0.003) catches plan-level issues
              │           (e.g., "plan specifies string interpolation")
              ▼
Stage 5: PLAN-INGESTION
  prime-context-seed.json
  ├── Tasks tagged security_sensitive: true    (REQ-QP-801)
  ├── gen_context includes security_contract   (REQ-QP-801)
  └── Minimum MODERATE tier for generation     (REQ-QP-801)
              │
              ▼
Stage 6: CONTRACTOR (Pass One)
  generated/
  ├── CartService.cs
  │   ├── GetCartAsync()  ──→ uses parameterized query (REQ-QP-500)
  │   ├── AddItemAsync()  ──→ NpgsqlParameter binding  (REQ-QP-500)
  │   └── EmptyCartAsync() ─→ @userId parameter        (REQ-QP-500)
  ├── AlloyDBCartStore.cs
  │   ├── constructor     ──→ singleton NpgsqlDataSource (REQ-QP-501)
  │   └── no credential logging                        (REQ-QP-502)
  └── SpannerCartStore.cs
      └── SpannerParameterCollection (correctly identified as safe)
              │
              ▼
TODO Scanner (extended: REQ-QP-900)
  todo-inventory.json
  ├── TODO-1: initStats()      → B+S (instrumentation + security)
  ├── TODO-2: Ping() AlloyDB   → S   (security: health check)
  ├── TODO-3: Ping() Spanner   → S   (security: health check)
  └── security_todos: 3
              │
              ▼
TODO Completion (REQ-QP-901)
  ├── Tasks carry dual contract: instrumentation + security
  └── Generated code satisfies both contracts
              │
              ▼
Anzen Gate: Pre-EXPORT Security Verification (REQ-QP-803)
  security-verification.json
  ├── injection_check: PASS (all queries parameterized)
  ├── credential_check: PASS (no connection strings logged)
  ├── lifecycle_check: PASS (DataSource is singleton)
  └── health_check_check: PASS (Ping() uses SELECT 1, not logged)
              │
              ▼
EXPORT
  └── Only security-verified code exits the pipeline
              │
              ▼
Kaizen Post-Mortem (REQ-QP-804)
  ├── security.injection_found_pre_export: 0
  ├── security.credential_leak_prevented: 0
  ├── security.false_positive_count: 0  (Spanner not flagged!)
  └── security_contract_coverage: 100%
```
