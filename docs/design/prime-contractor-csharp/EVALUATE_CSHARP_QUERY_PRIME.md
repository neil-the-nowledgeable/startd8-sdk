# Prompt: Evaluate C# Query Prime Security

> Use this prompt to evaluate Query Prime's security chain on a C# Prime Contractor run — from anchor sanitization through Anzen gate to parameterized code on disk.

---

## Inputs

```
Run directory:  {run_dir}/plan-ingestion/
Project root:   {project_root}
```

## Files to Read

| File | What to Check |
|------|--------------|
| `prime-context-seed-enriched.json` | Per-task: `detected_database`, `replaced_anchors`, `negative_scope`, `security_sensitive` |
| `kaizen-metrics.json` | `query_security` section: status, total_work_items, by_database, parameterization_rate |
| `query-security-metrics.json` | Standalone QP metrics (may be in run dir or project root) |
| `kaizen-suggestions.json` | Check for `sql_injection_detected` or `query_credential_logged` patterns |
| `prime-postmortem-report.json` | Per-feature: `semantic_issues` with `sql_injection_risk`, `query_security_*` categories |
| `generated/src/**/*CartStore*.cs` | Actual SQL patterns in database store implementations |
| `generated/.artifacts/*AlloyDB*-spec.md` | Check if AC-16 was sanitized |

---

## Step 1: Anchor Sanitizer Audit

Read `prime-context-seed-enriched.json`. For EACH task with `detected_database` set:

### 1a. Check `replaced_anchors`
- Is the field present? (Absent = sanitizer never fired)
- List each replacement: `original` → `replacement` (reason)
- Expected for AlloyDB: "Uses string interpolation SQL..." → "parameterized SQL using @param with NpgsqlParameter"

### 1b. Check `negative_scope`
- Does it still contain "Parameterized queries not used" or similar?
- Expected: stripped by `strip_conflicting_negative_scope()`
- If still present: the regex didn't match the phrasing — report the exact text

### 1c. Check `task_description`
- Does it still say "string-interpolated SQL" or "matching reference implementation"?
- Expected: sanitized by `sanitize_task_description()`

### 1d. Grade

| Finding | Grade |
|---------|-------|
| All three sanitized (anchors + scope + description) | **A** |
| Two of three sanitized | **B** |
| Only one sanitized | **C** |
| None sanitized but detected_database is set | **D** (sanitizer wired but not firing) |
| detected_database not set on DB-facing tasks | **F** (detection broken) |

---

## Step 2: Generated Code Security

Read each database-facing `.cs` file and check SQL construction patterns:

### AlloyDBCartStore.cs (PostgreSQL/Npgsql)

**PASS indicators** (parameterized):
```
cmd.Parameters.AddWithValue("@userId", userId)
cmd.Parameters.Add(new NpgsqlParameter("@userId", userId))
"SELECT ... WHERE userId = @userId"
```

**FAIL indicators** (string interpolation):
```
$"SELECT ... WHERE userId='{userId}'"
$"INSERT INTO ... VALUES ('{userId}', '{productId}')"
```

Grep for: `AddWithValue|NpgsqlParameter|@userId` (PASS) vs `\$".*\{userId\}` (FAIL)

### SpannerCartStore.cs (Cloud Spanner)

**PASS indicators**:
```
SpannerParameterCollection
cmd.Parameters.Add("userId", SpannerDbType.String, userId)
"SELECT ... WHERE userId = @userId"
```

**FAIL indicators**: `$"SELECT ... FROM {TableName} WHERE userId = {userId}"` with no `@param`

**Note:** `$"SELECT FROM {TableName}"` where `TableName` is a `static readonly string` is SAFE (REQ-KZ-CS-200i exemption) — only user-input variables in SQL are injection risks.

### RedisCartStore.cs

No SQL — check only for:
- Credential leakage: is connection string logged?
- `Console.WriteLine($"...{connectionString}...")` → credential exposure

### Other .cs Files

CartService.cs, HealthCheckService.cs, Startup.cs, Program.cs — no direct SQL. Check for:
- `Console.WriteLine` usage (should use ILogger<T>)
- Connection string handling in Startup.cs DI configuration

---

## Step 3: Anzen Gate Coverage

Read `kaizen-metrics.json` → `query_security` section:

| Field | Expected (DB run) | Expected (non-DB run) | Actual |
|-------|-------------------|----------------------|--------|
| `status` | `"pass"` or populated | `"no_queries_detected"` | ? |
| `total_work_items` | ≥ 3 (AlloyDB + Spanner + Redis) | 0 | ? |
| `by_database.postgresql` | present | absent | ? |
| `by_database.spanner` | present | absent | ? |
| `by_database.redis` | present | absent | ? |
| `parameterization_rate` | 1.0 (after sanitizer) | 0.0 | ? |
| `injection_total` | 0 (after sanitizer) | 0 | ? |

**If `total_work_items` is 0 or 1 for a DB run:** The seed→FeatureSpec bridge (REQ-QP-FIX-002) may not be working. Check if `detected_database` and `security_sensitive` appear in the FeatureSpec metadata (queue.py bridge).

---

## Step 4: Semantic Issue Analysis

Read `semantic_issue_breakdown` in `kaizen-metrics.json`:

| Category | Expected (post-sanitizer) | Concern If Present |
|----------|--------------------------|-------------------|
| `sql_injection_risk` | **0** | Anchor sanitizer or P0 security guidance failed |
| `query_security_injection` | **0** | Anzen gate found real injection |
| `query_security_credential_leakage` | Some (warnings) | Console.WriteLine logging connection strings |
| `query_security_lifecycle` | **0** | `using var` recognition should suppress |
| `console_writeline_in_service` | Some (warnings) | Expected until ILogger<T> adoption |
| `block_scoped_namespace` | Info only | Style preference, not security |

---

## Step 5: False Positive Check

### Spanner Table-Name Interpolation (REQ-KZ-CS-200i)
- SpannerCartStore uses `$"SELECT FROM {TableName}"` where `TableName` is `static readonly string`
- This SHOULD NOT produce `sql_injection_risk` (suppressed by Spanner exemption)
- If present: REQ-KZ-CS-200i regex not matching — report the exact flagged line

### Using Var Lifecycle (REQ-KZ-CS-200j)
- Code using `using var conn = new SpannerConnection(...)` or `await using var ds = NpgsqlDataSource.Create(...)`
- This SHOULD NOT produce `query_security_lifecycle` warnings
- If present: REQ-KZ-CS-200j `using var` recognition not matching — report the exact flagged line

---

## Step 6: Run-Over-Run Delta (if baseline available)

| Metric | Baseline | Current | Delta |
|--------|----------|---------|-------|
| AlloyDB DQS | ? | ? | ? |
| sql_injection_risk errors | ? | ? | ? |
| query_security_injection errors | ? | ? | ? |
| Anzen total_work_items | ? | ? | ? |
| parameterization_rate | ? | ? | ? |
| Spanner false positives | ? | ? | ? |
| Lifecycle false positives | ? | ? | ? |
| replaced_anchors count | ? | ? | ? |

**Bold** any delta > 10% improvement or ANY regression.

---

## Output Summary

### Grade

| Aspect | Grade | Evidence |
|--------|-------|---------|
| Anchor sanitizer | ? | replaced_anchors count, negative_scope status |
| Generated code security | ? | parameterized vs interpolated queries |
| Anzen gate coverage | ? | total_work_items, by_database completeness |
| False positive management | ? | Spanner exemption, using var recognition |
| **Query Prime composite** | ? | |

### JSON Output

```json
{
  "query_prime_grade": "",
  "anchor_sanitizer_fired": false,
  "anchors_replaced": 0,
  "negative_scope_sanitized": false,
  "alloydb_parameterized": false,
  "spanner_parameterized": false,
  "sql_injection_errors": 0,
  "false_positives": 0,
  "anzen_work_items": 0,
  "parameterization_rate": 0
}
```
