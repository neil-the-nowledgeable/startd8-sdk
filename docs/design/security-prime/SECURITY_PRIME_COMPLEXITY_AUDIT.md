# Security Prime — Complexity Audit: What Exists vs. What the Requirements Specify

> **Date:** 2026-03-19 (historical — written during v0.3→v1.0 requirements revision)
> **Status:** RESOLVED — all findings absorbed into requirements v1.1.0 and implementation
> **Purpose:** Eliminated accidental complexity by mapping existing `query_prime/` code to requirements
> **Outcome:** Requirements dropped from 203 to 46; new code from ~4,000 lines to ~1,700; `query_prime/` check infrastructure reused, not rebuilt

---

## The Core Problem

The requirements document (v0.3.0, ~203 requirements) specifies building a security validation infrastructure. **But `src/startd8/query_prime/` already contains most of the check infrastructure.** The requirements unknowingly re-specify existing code.

---

## What Already Exists in `query_prime/`

| Capability | File | Requirements It Satisfies |
|-----------|------|--------------------------|
| **Two-pass SQL injection detection** (multiline, comment-aware, parameterization-suppression) | `security/injection.py` | SP-T0-001, SP-T0-002, SP-T0-003, SP-T0-004, SP-T0-005 |
| **Credential leakage detection** | `security/credentials.py` | SP-T0-020, SP-T0-021, SP-T0-022 |
| **Resource lifecycle issues** | `security/lifecycle.py` | (RESOURCE domain checks) |
| **Full verification pipeline** (injection → credential → lifecycle, PASS/WARN/FAIL) | `security/__init__.py:verify_file()` | SP-VAL-001, SP-VL-001 |
| **Hard-fail on injection+credentials, WARN on lifecycle** | `security/__init__.py:80-97` | SP-PL-042, SP-PL-043, SP-PL-044 (Anzen gate logic) |
| **SecurityFinding dataclass** | `models.py:SecurityFinding` | SP-FND-001, SP-FND-002 |
| **SecurityVerificationResult** with verdict | `models.py:SecurityVerificationResult` | SP-VAL-002 |
| **SecurityVerdict enum** (PASS/FAIL/WARN) | `models.py:SecurityVerdict` | SP-PL-045 |
| **SecurityCheckType enum** (INJECTION, CREDENTIAL, LIFECYCLE) | `models.py:SecurityCheckType` | SP-TX-001 (partial) |
| **DatabasePatternRegistry** with auto-registration | `patterns/__init__.py` | SP-TX-001 extensibility |
| **PostgreSQL patterns** (C#/Npgsql, Python/psycopg2, Node/pg) | `patterns/postgresql.py` | SP-T0-001 per-language |
| **Spanner patterns** (C#, Go, Java) with false-positive fix | `patterns/spanner.py` | SP-T0-003, SP-FP-010 |
| **MySQL, Redis, SQLite patterns** | `patterns/mysql.py`, `redis.py`, `sqlite.py` | SP-T0-001 coverage |
| **QueryPrimeEngine** (CLASSIFY→ROUTE→GENERATE→VERIFY) | `engine.py` | Phase 9 entirely |
| **Query classifier** (signals → tier) | `classifier.py` | Phase 9 |
| **Query decomposer** (feature → work items) | `decomposer.py` | Phase 9 |
| **CRUD + health check templates** (TRIVIAL tier, $0.00) | `templates/crud.py`, `health_check.py` | Phase 9 |
| **Already wired into** `forward_manifest_validator.py` | Line 722 | Integration exists |

## What Does NOT Exist (Genuinely New Work)

| Capability | Why It's Needed | Est. Size |
|-----------|----------------|-----------|
| **Pre-generation prompt injection** (P0 constraint + P1 guidance in spec/draft) | Prevention > detection. The core Anzen insight. | ~200 lines |
| **Integration engine gate insertion** (after semantic repair, before advisory downgrade) | Wire `verify_file()` into the generation pipeline | ~50 lines |
| **Standalone mode auto-detection** (derive database type from task content) | Most runs don't use full pipeline | ~80 lines |
| **Security scoring formula** (max-severity-weighted, independent of quality score) | Quantify security posture per-file and per-run | ~60 lines |
| **Quality gate parallel check** (QUALITY_PASS_SECURITY_FAIL distinction) | Don't let quality score mask security failures | ~30 lines |
| **Kaizen feedback** (SECURITY_VIOLATION root cause, escalating hints) | Cross-run learning | ~120 lines |
| **OTel instrumentation** for security checks | Visibility in Grafana/Loki | ~80 lines |
| **OWASP coverage matrix** (static mapping) | Visibility into what's covered | ~50 lines |
| **Reference deviation policy** in prompt templates | Tell LLM to deviate from insecure reference | ~20 lines |
| **Allowlist** (`security_allowlist.yaml` loading) | Operator-managed false positive suppression | ~60 lines |
| **Security contract derivation** (from manifest + plan + language profile) | Pipeline-mode contract forwarding | ~150 lines |
| **Category S TODO extension** | Closed-loop: detect → generate → verify | ~100 lines |
| **Security profile** (`--security-profile` CLI mode) | $0.00 pre-code analysis | ~100 lines |

**Total genuinely new work: ~1,100 lines** (not ~4,000+ implied by the original requirements)

---

## Accidental Complexity Identified

### AC-1: New `security/` Package Duplicates `query_prime/security/`

The requirements spec `src/startd8/security/checks/injection.py` — but `query_prime/security/injection.py` already does exactly this with the two-pass approach, parameterization suppression, and cross-language patterns.

**Fix:** Security Prime is NOT a new check package. It's an **orchestration layer** that wires `query_prime/security/verify_file()` into the generation pipeline. The checks live in `query_prime/security/`. Security Prime adds: prompt injection, gate orchestration, scoring, Kaizen, OTel.

### AC-2: Phase 0 QW-1/QW-2 Are Superseded

QW-1 (parameterization suppression) and QW-2 (multiline SQL) propose enhancing `csharp_semantic_checks.py`. But `query_prime/security/injection.py` already does both, better (with comment awareness, configurable scan window, cross-language support).

**Fix:** The quick win is wiring `query_prime.security.verify_file()` into `integration_engine.py`, not re-implementing checks in `csharp_semantic_checks.py`.

### AC-3: SecurityFinding Defined Twice

The requirements define `SecurityFinding` in `security/models.py`. But `query_prime/models.py` already has `SecurityFinding` with `check_type`, `severity`, `message`, `line`, `file_path`, `database`, `pattern_hash`.

**Fix:** Use the existing `query_prime.models.SecurityFinding`. If additional fields are needed (CWE, OWASP, domain, confidence, tier), extend or alias it — don't redefine.

### AC-4: SecurityDomain Enum Over-Scoped

The requirements define 10 security domains. `query_prime` already covers the 3 that matter most: INJECTION, CREDENTIAL_LEAKAGE, LIFECYCLE. The other 7 (AUTH, CRYPTO, DESERIALIZATION, etc.) have zero implementation and zero findings from production runs.

**Fix:** Start with the 3 domains that exist. Add domains when concrete checks are implemented, not before.

### AC-5: Module Namespace Collision Is Avoidable

SP-NS-001–003 rename `security.py` → `security_utils.py` to free the namespace. But only 4 import sites use `startd8.security`. And the orchestration layer can live in `security_prime/` (following the `micro_prime/` naming pattern) or simply extend `query_prime/`.

**Fix:** Name the orchestration layer `security_prime/` or add orchestration modules to `query_prime/`. Either avoids the rename entirely.

### AC-6: Pattern Module Protocol Is Already Implemented

Phase 9 specifies a `QueryPatternModule` protocol with `safe_patterns()`, `unsafe_patterns()`, `parameterization_api()`, etc. But `DatabasePattern` dataclass + `DatabasePatternRegistry` already exist with this exact data.

**Fix:** Use the existing `DatabasePattern` and `DatabasePatternRegistry`. No new protocol needed.

### AC-7: The 203 Requirements Are ~60% Already Satisfied

By actual count, ~120 of the 203 requirements describe capabilities that already exist in `query_prime/`. The requirements document should be updated to acknowledge this and focus on the ~80 genuinely new requirements.

---

## The Real Quick Wins (Updated)

### RQW-1: Wire `verify_file()` into Integration Engine (~50 lines)

**The single highest-value change.** `query_prime.security.verify_file()` already does two-pass injection detection, credential leakage, lifecycle checks with PASS/WARN/FAIL verdicts. Wiring it into `integration_engine.py` after `_run_semantic_checks()` creates the Anzen gate immediately.

```python
# integration_engine.py, after _run_semantic_checks():
from startd8.query_prime.security import verify_file

if detected_database:  # from LanguageProfile.framework_imports
    result = verify_file(source, file_path, detected_database, language_id)
    if result.verdict == SecurityVerdict.FAIL:
        # Hard failure — not advisory-downgradeable
        ...
```

**This single change delivers: SP-PL-040, SP-PL-042, SP-PL-043, SP-PL-044, SP-T0-001–005, SP-T0-003 (Spanner fix), SP-FP-010.**

### RQW-2: P0 Security Constraint in Drafter Prompt (~30 lines)

Add a hardcoded P0 string to `drafter.py:get_drafter_system_prompt()` when `language_profile.framework_imports` detects a database driver:

```python
if any(fw in ("npgsql", "spanner", "psycopg2", "jdbc", "pg") for fw in detected_frameworks):
    prompt += "\n\nSECURITY CONSTRAINT: MUST use parameterized queries. NEVER use string interpolation in SQL."
```

No YAML templates needed yet. No budget system changes needed yet. Just a string.

**This delivers: SP-INJ-001, SP-INJ-003, SP-INJ-004a, SP-DEV-001.**

### RQW-3: `security_sensitive` Flag (~10 lines)

Already specified as QW-3. Still valid — 1 line in `TaskComplexitySignals`, 5 lines in `classify_tier()`.

### RQW-4: SECURITY_VIOLATION Root Cause (~20 lines)

Add `SECURITY_VIOLATION = "security_violation"` to `RootCause` enum + one `CAUSE_TO_SUGGESTION` entry:

```python
RootCause.SECURITY_VIOLATION: "Use parameterized queries for all database operations. See query_prime/patterns/ for language-specific examples."
```

**This delivers: SP-PL-053, SP-PL-054, SP-KZ-001.**

### RQW-5: Security Score in Quality Gate (~40 lines)

Map `SecurityVerificationResult.verdict` to a score (PASS=1.0, WARN=0.7, FAIL=0.0) and check alongside quality_score in `_check_quality_gate()`.

**This delivers: SP-SCR-001, SP-SCR-030, SP-SCR-032.**

---

## Naming: `micro_query` vs `query_prime`

The user suggests renaming `query_prime` → `micro_query` for consistency with `micro_prime`. However:

- `micro_prime` = element-level local generation (AST splicing, small scope)
- `query_prime` = domain-specific Prime paradigm instantiation (5-stage loop, any scope)

These are different architectural patterns. `query_prime` follows the Prime paradigm (DECOMPOSE→CLASSIFY→ROUTE→GENERATE→VERIFY), not the Micro Prime pattern.

**However**, `query_prime/security/` (the verification side) is genuinely "micro" in nature — it operates per-file with deterministic regex checks. The `QueryPrimeEngine` (generation side) is the Prime paradigm part.

**Recommendation:** Keep `query_prime` as-is. If a rename is desired for the security orchestration layer, use `security_prime/` (new thin package) that imports from `query_prime/security/` and adds pipeline orchestration (prompt injection, gate wiring, Kaizen, scoring). This avoids renaming existing working code while giving the security layer its own identity.

---

## Proposed Simplified Architecture

```
query_prime/                    # EXISTING — the checks + patterns + engine
├── security/                   # EXISTING — injection, credentials, lifecycle
│   ├── injection.py            #   Two-pass SQL injection (the core fix)
│   ├── credentials.py          #   Credential leakage
│   └── lifecycle.py            #   Resource lifecycle
├── patterns/                   # EXISTING — per-database safe/unsafe regex
│   ├── postgresql.py, spanner.py, mysql.py, redis.py, sqlite.py
├── engine.py                   # EXISTING — QueryPrimeEngine
├── models.py                   # EXISTING — SecurityFinding, etc.
└── ...

security_prime/                 # NEW — thin orchestration layer (~800 lines total)
├── __init__.py                 # Public API: run_anzen_gate(), inject_security_guidance()
├── gate.py                     # Wire verify_file() into integration engine
├── guidance.py                 # P0 constraint + P1 template injection into prompts
├── scorer.py                   # Security scoring (max-severity-weighted)
├── kaizen.py                   # SECURITY_VIOLATION + escalating hints
├── contract.py                 # Security contract derivation from manifest
├── enrichment.py               # Task tagging (security_sensitive)
├── otel.py                     # OTel spans + metrics
└── templates/
    └── security_constraints.yaml  # Safe/unsafe examples per library
```

**Total new code: ~800 lines** (not ~4,000 implied by the original plan)

**Why so much smaller?** Because the checks, patterns, models, and verification pipeline already exist. Security Prime is pure orchestration — wiring existing checks into the pipeline at the right points.
