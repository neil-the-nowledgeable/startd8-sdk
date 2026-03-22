# C# Prompt Improvement Requirements — Non-Deterministic Defects

**Date**: 2026-03-21
**Context**: Three recurring C# code quality defects cannot be fixed by deterministic post-generation repair because they require structural code changes (constructor wiring, query restructuring, logging infrastructure). They must be addressed at generation time through stronger prompt guidance and exemplar injection.
**Validated against**: run-093, run-094 (online-boutique cartservice, 15/15 PASS)
**Parent**: `KAIZEN_CSHARP_REQUIREMENTS.md` (REQ-KZ-CS-500 series)

---

## 1. Problem Summary

| Defect | Runs Affected | Severity | Why Not Repairable |
|--------|:---:|----------|-------------------|
| `Console.WriteLine` instead of `ILogger<T>` | 093, 094 (4 files each) | warning | Requires adding constructor parameter, private field, and DI registration — 3 coordinated changes across file scope |
| SQL injection via string interpolation | 093, 094 (AlloyDBCartStore) | error | Requires restructuring every query: new variable declarations, parameter binding calls, different string construction |
| Bare `catch { return false; }` in Ping() | 093, 094 (3 files each) | warning | Requires ILogger to be wired first (Catch→Log dependency), and deciding what to log |

All three defects persisted from run-093 to run-094 despite:
- `build_project_context_section()` containing explicit "NEVER" guidance (added between runs)
- The LLM demonstrably knowing the correct patterns (SpannerCartStore uses parameterized queries; CartService imports `Microsoft.Extensions.Logging`)

**Root cause**: The LLM follows reference code patterns (from the design doc/spec) more strongly than structural rules in the project context section. When the spec's code examples use `Console.WriteLine` and string interpolation, the LLM reproduces those patterns regardless of the "NEVER" instruction.

---

## 2. Requirements

### 2.1 ILogger Dependency Injection (REQ-PI-CS-100 series)

#### REQ-PI-CS-100: ILogger Constructor Pattern in Spec Code Examples

When the spec or draft prompt includes a code example for a C# service class, the example MUST include the ILogger constructor injection pattern, not Console.WriteLine.

**Problem**: The spec code examples (from the design document) show `Console.WriteLine(...)`. The LLM reproduces the example pattern even when the project context says "NEVER use Console.WriteLine."

**Solution**: The spec builder MUST transform code examples that contain `Console.WriteLine` to use `ILogger<T>` before injecting them into the prompt. This is a prompt-time transformation, not a post-generation repair.

**Transformation rules**:
```
Console.WriteLine("message")  →  _logger.LogInformation("message")
Console.WriteLine($"error: {ex}")  →  _logger.LogError(ex, "error")
Console.Error.WriteLine(...)  →  _logger.LogError(...)
```

When the spec includes a class that uses `Console.WriteLine`, the spec builder SHOULD also inject a constructor parameter `ILogger<{ClassName}> logger` and a private field `private readonly ILogger<{ClassName}> _logger = logger;` in the code example.

**Acceptance criteria**:
- Spec prompts for C# service classes never contain `Console.WriteLine`
- Generated code in run-095+ uses `ILogger<T>` in classes that had `Console.WriteLine` in run-094

#### REQ-PI-CS-101: ILogger as Mandatory Constructor Parameter

When generating C# service/implementation classes (detected by: inherits from a base class, implements an interface, or is registered in DI), the spec prompt MUST include this structural requirement:

> "Every service class MUST accept `ILogger<{ClassName}>` as a constructor parameter and store it in a `private readonly` field. This is NON-NEGOTIABLE — the class will fail code review without it."

**Rationale**: "NEVER use Console.WriteLine" is a prohibition. `REQ-PI-CS-101` adds a positive requirement ("MUST accept ILogger") which the LLM follows more reliably than prohibitions.

#### REQ-PI-CS-102: ILogger Framework Import Injection

When `grpc` or `aspnet_core` framework is detected, the `framework_imports` entry MUST include:
- `Microsoft.Extensions.Logging` using directive
- `ILogger<T>` constructor injection example in the preamble

**Status**: Partially done — `Microsoft.Extensions.Logging` is in the using list but the constructor injection example is not in the framework preamble.

---

### 2.2 Parameterized SQL Queries (REQ-PI-CS-200 series)

#### REQ-PI-CS-200: SQL Parameterization in Spec Code Examples

When the spec or draft prompt includes code examples that construct SQL queries, the examples MUST use parameterized queries, even if the reference design document uses string interpolation.

**Problem**: The design document for AlloyDBCartStore explicitly documents string interpolation SQL as the pattern. The LLM faithfully reproduces it. SpannerCartStore uses parameterized queries because its design doc shows `SpannerParameterCollection` — proving the LLM generates correct code when the example is correct.

**Solution**: The spec builder SHOULD detect SQL patterns (`SELECT`, `INSERT`, `UPDATE`, `DELETE` keywords followed by `$"` or `"..."+`) in the spec's code examples and inject a warning:

> "WARNING: The reference code uses string interpolation for SQL queries. This is a SECURITY VULNERABILITY. Replace ALL string-interpolated SQL with parameterized queries using `cmd.Parameters.AddWithValue()`. See the Observability Contract section for the correct pattern."

**Acceptance criteria**:
- AlloyDBCartStore in run-095+ uses `NpgsqlCommand.Parameters.AddWithValue()` instead of `$"SELECT...{userId}"`

#### REQ-PI-CS-201: Database-Aware Parameterization Examples

When a task's context includes `detected_databases` (from instrumentation hints or security contract), the spec prompt MUST include a language-specific parameterized query example for that database:

| Database | C# Pattern |
|----------|-----------|
| PostgreSQL/AlloyDB (Npgsql) | `cmd.CommandText = "SELECT * FROM t WHERE id = @id"; cmd.Parameters.AddWithValue("@id", value);` |
| Spanner | `new SpannerCommand("SELECT * FROM t WHERE id = @id", conn) { Parameters = { { "id", SpannerDbType.String, value } } }` |
| SQL Server | `cmd.CommandText = "SELECT * FROM t WHERE id = @id"; cmd.Parameters.AddWithValue("@id", value);` |
| Redis | N/A (key-value, no SQL) |

**Acceptance criteria**:
- When `detected_databases: ["postgresql"]`, the AlloyDBCartStore spec includes the Npgsql parameterized example

#### REQ-PI-CS-202: SQL Injection Kaizen Escalation

When the `sql_injection_detected` kaizen suggestion fires for 2+ features (as it did in run-094), the hint SHOULD be escalated from P1 (kaizen) to P0 (security) priority in the next run's prompt. P0 sections are never trimmed under budget pressure.

**Rationale**: SQL injection is a security defect, not a quality hint. It should be treated with the same priority as security contract guidance.

**Implementation**: In `spec_builder.py`, when processing kaizen hints, detect `sql_injection_detected` or `query_injection_interpolation` pattern types and promote them to the security section (P0) instead of the kaizen section (P1).

---

### 2.3 Exception Handling in Ping() Methods (REQ-PI-CS-300 series)

#### REQ-PI-CS-300: Ping() Method Exception Handling Pattern

When generating `Ping()` or health check methods for C# cart store / data access classes, the spec prompt MUST include:

> "The `Ping()` method MUST:
> 1. Actually test the connection (e.g., execute `SELECT 1` for SQL, `PING` for Redis)
> 2. Log failures with `_logger.LogWarning(ex, "Health check failed")`
> 3. Return `false` on failure (after logging)
> 4. NEVER use an empty catch block"

**Problem**: All three cart store `Ping()` methods in run-093 and run-094 have `catch { return false; }` — an empty catch that silently swallows errors. RedisCartStore's Ping() doesn't even ping Redis (try body is `return true` with no actual operation).

**Solution**: The spec builder SHOULD detect Ping/HealthCheck methods in the task description and inject the structural requirement above. This is more effective than a general "no empty catches" rule because it provides the specific pattern for the specific method.

#### REQ-PI-CS-301: Catch Block Minimum Content

When the project context section lists "NEVER use empty catch blocks", the spec prompt SHOULD also include the minimum acceptable catch block:

```csharp
// MINIMUM acceptable catch block (never empty):
catch (Exception ex)
{
    _logger.LogError(ex, "Operation failed");
    throw;  // or: return false; for health checks
}
```

**Rationale**: The prohibition "NEVER empty catch" tells the LLM what NOT to do but not what TO do. Providing the minimum pattern gives the LLM a concrete replacement.

#### REQ-PI-CS-302: Catch-Depends-On-Logger Ordering

The ILogger requirement (REQ-PI-CS-100) MUST be listed before the exception handling requirement (REQ-PI-CS-300) in the project context section. The LLM cannot generate `_logger.LogError(ex, ...)` in a catch block if it hasn't been told to wire up `_logger` first.

**Current state**: Both rules exist in `build_project_context_section()` in the correct order (ILogger section appears before exception handling section). This requirement documents the ordering dependency.

---

## 3. Implementation Approach

### 3.1 Prompt-Time Transformations (spec_builder.py)

These changes modify how the spec/draft prompt is constructed, not the generated code:

| Change | Where | Trigger |
|--------|-------|---------|
| Transform `Console.WriteLine` in code examples to `ILogger` | `spec_builder.py` — when building spec context for C# tasks | Language is csharp AND code example contains `Console.Write` |
| Inject SQL parameterization warning | `spec_builder.py` — when building spec context | Code example contains SQL keyword + `$"` or `"..."+` |
| Inject database-specific parameterization example | `spec_builder.py` — observability guidance section or security section | `context.get("detected_databases")` is non-empty |
| Promote SQL injection kaizen to P0 | `spec_builder.py` — kaizen hint processing | Kaizen hint pattern_type is `sql_injection_detected` or `query_injection_*` |

### 3.2 Exemplar-Based Correction

The exemplar registry (run-094: 7 exemplars extracted) can be leveraged:

- **Positive exemplar**: SpannerCartStore uses parameterized queries correctly. When generating AlloyDBCartStore (same interface, different backend), the spec builder can inject SpannerCartStore as a reference implementation showing the correct SQL pattern.
- **Negative exemplar**: AlloyDBCartStore's SQL injection pattern should be flagged so it is NOT used as an exemplar reference in future runs.

#### REQ-PI-CS-400: Exemplar Quality Gate for SQL

The exemplar registry SHOULD NOT promote files with `sql_injection_risk` semantic errors to exemplar status. Files with error-severity semantic issues are negative examples that should be excluded from the exemplar pool.

---

## 4. Expected Improvement Path

### Run-095 (kaizen hints active, no code changes)

The 3 kaizen suggestions from run-094 will be injected as P1 hints:
- Block-scoped namespace → **moot** (repair step fixes this deterministically)
- Console.WriteLine → **may help** (hint says "inject ILogger<T> via constructor")
- SQL injection → **may help** (hint includes concrete BAD/GOOD example)

Expected: partial improvement on Console.WriteLine and SQL injection. Bare catch blocks unlikely to improve (no kaizen suggestion for them yet — threshold of 2+ features not met because `empty_catch_block` appears as `warning` not `error`).

### Run-096+ (after implementing REQ-PI-CS-100/200/300)

With spec-time transformations:
- Console.WriteLine: **high confidence fix** — positive requirement + example transformation
- SQL injection: **high confidence fix** — database-specific example + security escalation
- Bare catch blocks: **medium confidence fix** — depends on ILogger being wired first

### Steady State

Once the feedback loop stabilizes (exemplar quality gates + kaizen hints + spec transformations), these defects should converge to <1 occurrence per run within 3-4 iterations.

---

## 5. Traceability

| Requirement | Addresses | Validated By |
|-------------|-----------|-------------|
| REQ-PI-CS-100 | Console.WriteLine in 4 files (run-094) | `csharp_semantic_checks.check_console_writeline()` |
| REQ-PI-CS-101 | Missing ILogger constructor injection | Manual review (no automated check for DI completeness) |
| REQ-PI-CS-102 | ILogger not in framework preamble | Manual review of spec prompt content |
| REQ-PI-CS-200 | SQL injection in AlloyDBCartStore (run-094) | `csharp_semantic_checks.check_sql_injection_risk()` |
| REQ-PI-CS-201 | No database-specific parameterization example | Manual review of spec prompt content |
| REQ-PI-CS-202 | SQL injection kaizen at P1 instead of P0 | Check `kaizen_hints` processing in `spec_builder.py` |
| REQ-PI-CS-300 | Bare catch in 3 Ping() methods (run-094) | `csharp_semantic_checks.check_empty_catch_blocks()` |
| REQ-PI-CS-301 | No minimum catch pattern in prompt | Manual review of project context section |
| REQ-PI-CS-302 | ILogger must precede catch guidance | Verify ordering in `build_project_context_section()` |
| REQ-PI-CS-400 | SQL-injection files as exemplars | Check exemplar quality filter |
