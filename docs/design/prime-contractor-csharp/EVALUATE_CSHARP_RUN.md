# Prompt: Evaluate C# Prime Contractor Run

> Provide this prompt to an agent alongside the run output. The agent evaluates the run across Kaizen code quality, MicroPrime cost efficiency, and Query Prime security — producing letter grades with evidence.
>
> **Supports two input modes:**
> - **Structured:** Provide `{run_dir}` and optional `{baseline_run_dir}` below
> - **Conversational:** Paste the terminal output — the agent extracts the run ID and discovers paths via convention

---

## Inputs

```
Run directory:      {run_dir}/plan-ingestion/
Project root:       {project_root}
Baseline (optional): {baseline_run_dir}/plan-ingestion/
```

If inputs are not provided, extract the run ID from pasted output (e.g., `run-113-20260323T1537`) and resolve:
- `{project_root}/.cap-dev-pipe/pipeline-output/online-boutique/{run_id}/plan-ingestion/`

---

## Files to Read

| File | Role | Required |
|------|------|----------|
| `prime-postmortem-report.json` | Per-feature DQS, semantic issues, verdicts | Yes |
| `kaizen-metrics.json` | Aggregate scores, query_security, semantic breakdown | Yes |
| `kaizen-suggestions.json` | Generated Kaizen hints (0 = perfect) | Yes |
| `prime-context-seed-enriched.json` | Seed: detected_database, replaced_anchors, negative_scope | For Query Prime |
| `generated/src/**/*.cs` | Actual C# code — check SQL patterns, logging, namespaces | For Semantic Checks |
| `generated/.artifacts/*-spec.md` | Spec — check if acceptance criteria were sanitized | For Query Prime deep-dive |
| `generated/.artifacts/*-review-*.md` | Review — check reviewer score and flagged issues | For Feedback Loop |
| `query-security-metrics.json` | Standalone QP metrics (status, by_database) | For Query Prime |

---

## Grade Thresholds (REQ-CSH-P-010)

### Per-Feature (DQS-based)

| Grade | DQS | Semantic Errors | SQL Injection | Console.WriteLine |
|-------|-----|----------------|---------------|-------------------|
| **A** | ≥ 0.95 | 0 errors | 0 | 0 |
| **B** | 0.85–0.94 | 0 errors, ≤ 3 warnings | 0 | ≤ 2 |
| **C** | 0.70–0.84 | ≤ 3 errors | 0 | ≤ 5 |
| **D** | 0.50–0.69 | 4+ errors | 1–3 | any |
| **F** | < 0.50 | any | 4+ | any |

### Per-Domain

| Domain | A | B | C | D | F |
|--------|---|---|---|---|---|
| **Kaizen** (aggregate) | ≥ 0.97 | 0.93–0.96 | 0.85–0.92 | 0.70–0.84 | < 0.70 |
| **MicroPrime** (local %) | ≥ 50% local | 25–49% | 1–24% | 0% (all COMPLEX) | Not enabled |
| **Query Prime** (param rate) | 100% + 0 FP | 100% + ≤ 2 FP | 90–99% | 70–89% | < 70% |

---

## Quick Checklist (condensed from KAIZEN_CSHARP_REQUIREMENTS.md)

### Disk Validation (REQ-KZ-CS-100)
- [ ] All .cs files pass tree-sitter syntax validation
- [ ] File-scoped namespaces used (net8.0+), not block-scoped
- [ ] Zero cross-language contamination (Python/Go/Java fingerprints)
- [ ] .csproj has `<TargetFramework>` + `<Nullable>enable</Nullable>`
- [ ] Type name matches filename (CartStore.cs → class CartStore)

### Semantic Checks (REQ-KZ-CS-200)
- [ ] Zero `sql_injection_risk` errors in semantic_issue_breakdown
- [ ] Zero `async void` methods (except event handlers)
- [ ] ILogger<T> used instead of Console.WriteLine in service classes
- [ ] No empty catch blocks (at minimum log or rethrow)
- [ ] `using var` / `await using var` for IDisposable resources

### Query Security
- [ ] AlloyDB: `NpgsqlParameter` / `AddWithValue` (not `$"...{var}"`)
- [ ] Spanner: `SpannerParameterCollection` (not string interpolation)
- [ ] No connection strings logged (credential leakage)
- [ ] `negative_scope` sanitized (no "parameterized queries not used")
- [ ] `replaced_anchors` present in seed for database-facing tasks

### Generation Quality (REQ-KZ-CS-600)
- [ ] Zero stubs remaining (no `throw new NotImplementedException()` in production)
- [ ] .sln correct format with project GUIDs
- [ ] Dockerfile uses multi-stage build (sdk → runtime-deps chiseled)
- [ ] Proto file uses proto3 syntax with proper package
- [ ] appsettings.json has Kestrel HTTP/2 config

---

## Part 1: Kaizen Code Quality

Read `prime-postmortem-report.json` and `kaizen-metrics.json`.

### 1a. Disk Validation (REQ-KZ-CS-100)
- Read each feature's `disk_compliance.ast_valid` — all should be `true`
- Check `semantic_issue_breakdown` for `block_scoped_namespace` (info, not error)
- Check for any `cross_language_contamination` category
- Grade using the checklist above

### 1b. Semantic Checks (REQ-KZ-CS-200)
- Read `semantic_issue_breakdown` — list all categories with counts
- Focus on error-severity categories: `sql_injection_risk`, `query_security_injection`
- Count `console_writeline_in_service` warnings across features
- Check for `empty_catch_block` warnings
- Compare against thresholds: 0 errors = A component, 1-3 errors = C component

### 1c. Quality Scoring (REQ-KZ-CS-300)
- Read `aggregate_score` — apply domain threshold
- Read each feature's `disk_quality_score` — any below 0.85?
- Read `avg_assembly_delta` — lower is better (< 0.05 = excellent)
- Count PARTIAL:semantic verdicts vs PASS verdicts

### 1d. Repair Pipeline (REQ-KZ-CS-400)
- Check if any features have `semantic_repairs_applied > 0`
- Check if `SqlParameterizeStep` fired (look for `pre_semantic_repair_score`)
- If repair_enabled=False for C#: note this as expected (no grade penalty)

### 1e. Feedback Loop (REQ-KZ-CS-500)
- Read `kaizen-suggestions.json` — how many hints generated?
- Were suggestions actionable? (credential leakage, Console.WriteLine, etc.)
- 0 suggestions on a perfect run = correct (not a gap)

### 1f. Generation Profile (REQ-KZ-CS-600)
- Spot-check: .sln format, .csproj validity, Dockerfile multi-stage, .proto syntax
- These are usually clean — grade A unless specific issues found

### 1g. LanguageProfile (REQ-KZ-CS-700)
- Usually A — only grade down if protocol compliance issues found

---

## Part 2: MicroPrime Cost Efficiency

### 2a. Activation Status
Read `kaizen-metrics.json` → `route` field. Read postmortem → `micro_prime_analysis`.

Classify into ONE of three states:
- **Not enabled**: `micro_prime_analysis` absent or `None`, no `--micro-prime` flag → Grade: **F** (configuration issue)
- **Enabled, all COMPLEX**: `micro_prime_analysis` present but `total_elements = 0` or all escalated → Grade: **D** (classification issue — check feature LOC vs `loc_complex_min=500`)
- **Enabled, elements processed**: Some elements handled locally → Grade based on local generation %

### 2b. Template Hits
If MicroPrime processed elements:
- Count features with `template_used: true` and `generation_strategy: "template"`
- List which C# templates matched (csharp_di_constructor, csharp_property, etc.)
- Calculate hit rate: `template_matches / total_trivial_elements`

### 2c. Cost Impact
- If MicroPrime active: compare `cost_usd` per feature vs prior all-cloud run
- If MicroPrime inactive: estimate potential savings (TRIVIAL elements × $0.12 avg cloud cost)

---

## Part 3: Query Prime Security

### 3a. Anchor Sanitizer Effectiveness
Read `prime-context-seed-enriched.json`. For each task with `detected_database`:
- Check `replaced_anchors` — was anything sanitized? List original→replacement
- Check `negative_scope` — was "parameterized queries not used" stripped?
- Check `task_description` — does it still say "string-interpolated SQL"?

### 3b. Anzen Gate Coverage
Read `kaizen-metrics.json` → `query_security` section:
- `status`: `"no_queries_detected"` (clean, no DB) vs populated
- `total_work_items`: should match count of DB-facing .cs files
- `by_database`: all databases represented?
- `parameterization_rate`: should be 1.0 (100%)

### 3c. Parameterization Compliance
Read the actual generated .cs files for database stores:
- **AlloyDBCartStore.cs**: grep for `AddWithValue` / `NpgsqlParameter` (PASS) vs `$"...{userId}"` (FAIL)
- **SpannerCartStore.cs**: grep for `SpannerParameterCollection` / `Parameters.Add` (PASS)
- **RedisCartStore.cs**: no SQL — check for credential leakage only

### 3d. False Positive Status
- SpannerCartStore: any `sql_injection_risk` on `$"SELECT FROM {TableName}"`? (Should be 0 — REQ-KZ-CS-200i exemption)
- Any `query_security_lifecycle` on `using var` lines? (Should be 0 — REQ-KZ-CS-200j)

---

## Part 4: Summary

### Grade Table

| Domain | Grade | Key Evidence |
|--------|-------|-------------|
| **Disk Validation** | ? | ? |
| **Semantic Checks** | ? | ? |
| **Quality Scoring** | ? | ? |
| **Repair Pipeline** | ? | ? |
| **Feedback Loop** | ? | ? |
| **Generation Profile** | ? | ? |
| **LanguageProfile** | ? | ? |
| **MicroPrime** | ? | ? |
| **Query Prime** | ? | ? |
| **Composite** | ? | ? |

### Delta vs Baseline (if baseline provided)

| Metric | Baseline | Current | Delta |
|--------|----------|---------|-------|
| Aggregate score | ? | ? | ? |
| AlloyDB DQS | ? | ? | ? |
| SQL injection errors | ? | ? | ? |
| Cost | ? | ? | ? |
| MicroPrime local % | ? | ? | ? |
| Kaizen suggestions | ? | ? | ? |

**Bold** any delta > 10% improvement or ANY regression.

### JSON Grade Output (REQ-CSH-P-014)

```json
{
  "run_id": "",
  "language": "csharp",
  "grades": {
    "disk_validation": "",
    "semantic_checks": "",
    "quality_scoring": "",
    "repair_pipeline": "",
    "feedback_loop": "",
    "generation_profile": "",
    "language_profile": "",
    "microprime": "",
    "query_prime": "",
    "composite": ""
  },
  "metrics": {
    "aggregate_score": 0,
    "worst_feature_dqs": 0,
    "sql_injection_errors": 0,
    "console_writeline_count": 0,
    "microprime_local_pct": 0,
    "parameterization_rate": 0,
    "cost_usd": 0,
    "features_passed": 0,
    "features_total": 0,
    "kaizen_suggestions": 0
  },
  "delta_vs_baseline": null
}
```

### Top 3 Actionable Improvements

1. ?
2. ?
3. ?
