# C# Pipeline Prompt & Evaluation Requirements

> **Version:** 1.1.0
> **Status:** DRAFT (revised post-implementation-plan review)
> **Date:** 2026-03-23 (v1.1 same-day revision)
> **Language:** C# (.cs, .csproj, .sln)
> **Scope:** Define requirements for prompts that evaluate, validate, and improve C# Prime Contractor outputs across three domains: Kaizen evaluation, MicroPrime validation, and Query Prime integration

---

## 1. Current State

### What Exists for C#

| Domain | Artifact | Status | Session Validated |
|--------|----------|--------|-------------------|
| **Kaizen evaluation** | `KAIZEN_CSHARP_REQUIREMENTS.md` | Complete (v1.0) | Yes — graded runs 100, 104, 106, 113 |
| **Semantic repair bridge** | REQ-KZ-CS-402a/b/c | Implemented + tested | Yes — false positives eliminated |
| **Anchor sanitizer** | REQ-QPI-200/201/203 | Implemented + tested | Yes — run-113 AlloyDB DQS 0.80→0.98 |
| **MicroPrime templates** | 8 C# templates in `_LANGUAGE_TEMPLATES["csharp"]` | Implemented + integration tested | Yes — unit level; No — pipeline level |
| **MicroPrime splicer** | `_splice_csharp_dispatch()` → `csharp_splicer.splice_csharp_bodies()` | Wired + dispatch tested | No — actual splice untested |
| **MicroPrime SIMPLE bypass** | Removed `_is_non_python_file()` gate | Implemented + unit tested | No — Ollama C# generation untested |
| **Query Prime patterns** | `DatabasePatternRegistry` for PostgreSQL×C# (Npgsql), Spanner×C# | Implemented | Yes — Anzen gate detects in C# runs |
| **UPSERT template** | PostgreSQL×C# INSERT...ON CONFLICT | Implemented + unit tested | No — pipeline level |

### What's Missing for C#

| Gap ID | Domain | Description | Impact |
|--------|--------|-------------|--------|
| **CSH-P-001** | Evaluation | No reusable evaluation prompt that combines Kaizen + Query Prime + MicroPrime grading | Each evaluation is ad-hoc; grading criteria inconsistent |
| **CSH-P-002** | MicroPrime | No prompt for validating polyglot template effectiveness in a real C# run | Can't diagnose "complex=15" or verify cost savings |
| **CSH-P-003** | Query Prime | No prompt for evaluating Query Prime's C#-specific effectiveness (Anzen gate coverage, parameterization rate) | Query Prime evaluation folded into generic Kaizen; C#-specific issues (Npgsql patterns, Spanner exemptions) not checked |

---

## 1b. v1.1 Revision — Post-Implementation-Plan Insights

Writing the implementation plan revealed 8 structural issues not visible during requirements authoring:

**Insight 1: The three-prompt split creates redundancy, not specialization.**
EVALUATE_CSHARP_RUN.md includes MicroPrime and Query Prime sections that duplicate the other two prompts. In practice this session, every evaluation was comprehensive — we never evaluated "just MicroPrime" or "just Query Prime" in isolation. **→ Consolidate into ONE comprehensive prompt with depth flags. The two focused prompts become optional deep-dives, not standalone alternatives.**

**Insight 2: No explicit grading thresholds.**
We graded runs A through F this session but the thresholds were ad-hoc ("DQS 0.80 = C, DQS 0.98 = A"). The requirements say "produce letter grades" but don't define what each grade means numerically. **→ Added REQ-CSH-P-010: Grade Threshold Definitions.**

| Grade | DQS Range | Semantic Errors | SQL Injection | Console.WriteLine |
|-------|-----------|----------------|---------------|-------------------|
| **A** | ≥ 0.95 | 0 | 0 | 0 |
| **B** | 0.85–0.94 | 1–3 (warnings only) | 0 | ≤ 2 |
| **C** | 0.70–0.84 | 4–8 | 0 | ≤ 5 |
| **D** | 0.50–0.69 | 9+ | 1–3 | any |
| **F** | < 0.50 | any | 4+ (real injection) | any |

**Insight 3: Run comparison is the highest-value evaluation mode.**
Every useful finding this session came from delta tables (run-100→104→106→113). The requirements define single-run grading but don't formalize comparative evaluation. **→ Added REQ-CSH-P-011: Delta evaluation mode. The prompt MUST support a `{baseline_run_dir}` input for side-by-side comparison.**

**Insight 4: The user pastes log output, not structured paths.**
The requirements assume an agent receives `{run_dir}` paths. In practice, the user pastes terminal output and says "evaluate this." **→ The prompt must handle BOTH modes: (a) structured paths provided, (b) run ID extracted from pasted output, agent discovers paths via convention (`{project_root}/.cap-dev-pipe/pipeline-output/{project}/run-{id}/plan-ingestion/`).**

**Insight 5: KAIZEN_CSHARP_REQUIREMENTS.md is too large for a prompt rubric.**
The requirements doc is 750+ lines. An agent can't internalize it all. **→ Added REQ-CSH-P-012: Condensed rubric. The evaluation prompt includes a ~50-line condensed checklist extracted from the full requirements, not a pointer to the 750-line doc.**

**Insight 6: The "Key Files to Read" table is the highest-leverage section.**
Every evaluation this session started with an agent reading 5-8 specific files. The exact list determines evaluation quality. **→ Added REQ-CSH-P-013: File inventory helper. A small utility (or prompt section) that takes a run directory and lists all evaluable files with their roles, eliminating path guessing.**

**Insight 7: The MicroPrime prompt has a prerequisite that isn't met.**
Run-113 showed "complex=15" — MicroPrime never processed any elements. The MicroPrime validation prompt will always say "inactive" until the classification issue is resolved. **→ The prompt must distinguish "MicroPrime not enabled" from "MicroPrime enabled but all elements COMPLEX" from "MicroPrime enabled and elements processed." Each is a different diagnosis.**

**Insight 8: Machine-readable output enables trend tracking.**
The requirements specify markdown output. But if grades were also emitted as JSON (`{"kaizen": "B+", "microprime": "N/A", "query_prime": "A-", "composite": "B+"}`), we could chart evaluation trends across runs — "is the Kaizen grade improving?" **→ Added REQ-CSH-P-014: Dual output format (markdown + JSON grades).**

---

## 2. REQ-CSH-P-001: C# Comprehensive Evaluation Prompt (Revised)

### Purpose

A self-contained prompt that evaluates a C# Prime Contractor run across ALL three quality domains — Kaizen code quality, MicroPrime cost efficiency, and Query Prime security — using the C#-specific requirements as grading rubric.

### Structure

The prompt MUST include:

**Section 1 — Context Block** (provided to the agent alongside the prompt)
- Path to the run's `prime-postmortem-report.json`
- Path to the run's `kaizen-metrics.json`
- Path to the run's `kaizen-suggestions.json`
- Path to the generated `.cs` files directory
- Reference: `KAIZEN_CSHARP_REQUIREMENTS.md` for grading rubric

**Section 2 — Kaizen Evaluation (from KAIZEN_CSHARP_REQUIREMENTS.md)**
- Grade each REQ-KZ-CS section: Disk Validation (100), Semantic Checks (200), Quality Scoring (300), Repair Pipeline (400), Feedback Loop (500), Generation Profile (600), LanguageProfile (700)
- Compare DQS scores against prior runs if available
- Flag any `PARTIAL:semantic` verdicts and root causes
- Check for Console.WriteLine vs ILogger<T> compliance
- Check for file-scoped vs block-scoped namespace usage

**Section 3 — MicroPrime Evaluation (from REQ-MP-12xx)**
- Check `kaizen-metrics.json` for micro_prime_analysis section
- Count: how many elements were TRIVIAL (template), SIMPLE (local), vs COMPLEX (cloud)?
- Which C# templates matched? (`csharp_di_constructor`, `csharp_property`, etc.)
- Was any cost savings achieved vs all-cloud baseline?
- If all COMPLEX: check logs for classification reasons (REQ-MPV-001 observability)

**Section 4 — Query Prime Evaluation (from KAIZEN_QUERY_PRIME_REQUIREMENTS.md)**
- Check `query_security` section in `kaizen-metrics.json`
- Is `status` = `"no_queries_detected"` (clean) or populated with database findings?
- If populated: check `parameterization_rate`, `injection_total`, `by_database` breakdown
- Check if `sql_injection_risk` appears in `semantic_issue_breakdown` (should be 0 after anchor sanitizer)
- Check if `negative_scope` was sanitized (look for `replaced_anchors` in seed context)
- Grade Anzen gate coverage: `total_work_items` should reflect actual DB-facing files

**Section 5 — Cross-Domain Summary**
- Overall letter grades per domain
- Composite grade
- Delta vs prior run (if baseline available)
- Top 3 actionable improvements

### Acceptance Criteria (Revised v1.1)

1. The prompt produces consistent grades across different agents (reproducible)
2. All grade categories map to specific REQ IDs from the requirements docs
3. The prompt works without modification for any C# Prime Contractor run (different project, different features)
4. Output format: markdown table with grades + evidence + requirement references **+ JSON grade object** (REQ-CSH-P-014)
5. **(v1.1)** Grades use explicit thresholds from REQ-CSH-P-010, not agent judgment
6. **(v1.1)** Supports both structured input (`{run_dir}`) and conversational input (pasted log output with run ID extraction)
7. **(v1.1)** Includes condensed 50-line rubric checklist, not a pointer to the 750-line requirements doc
8. **(v1.1)** Delta mode: when `{baseline_run_dir}` is provided, produces comparison table showing improvement/regression per metric

---

## 3. REQ-CSH-P-002: C# MicroPrime Validation Prompt

### Purpose

A prompt specifically for diagnosing and validating MicroPrime's behavior on C# features — why elements classify at each tier, whether templates fire, and what cost savings result.

### Structure

**Section 1 — Classification Diagnosis**
- Read the run's postmortem for `micro_prime_analysis` section
- If absent or `None`: MicroPrime didn't process any elements — check if it was enabled (`--micro-prime` flag)
- Read Loki logs for `TRIVIAL dispatch:` and `SIMPLE dispatch:` entries (REQ-MPV-001)
- For each C# element: what tier was assigned and why?

**Section 2 — Template Effectiveness**
- Which C# templates matched? List by name + element + file
- Which elements had NO template match? What kind/name were they?
- Calculate template hit rate: `matched / total_trivial_elements`
- For unmatched elements: could a new template handle them? (gap analysis)

**Section 3 — Splicer Validation**
- Did any SIMPLE C# elements reach Ollama generation?
- If so: did the C# splicer fire (`_splice_csharp_dispatch`)?
- Were generated bodies syntactically valid? (`validate_syntax()` pass rate)
- Was any code actually spliced into skeletons?

**Section 4 — Cost Impact**
- Count local vs cloud elements
- Estimate savings: `local_count × avg_cloud_cost_per_element`
- Compare against baseline (all-cloud) run if available

**Key Files to Read**
- `prime-postmortem-report.json` — micro_prime_analysis section
- `kaizen-metrics.json` — route field, tier distribution
- Generation cache files in `.startd8/state/generation_cache/` — per-element metadata
- Loki logs filtered by `startd8.micro_prime.engine`

### Acceptance Criteria (Revised v1.1)

1. The prompt diagnoses the "complex=15" issue seen in run-113
2. The prompt identifies template gaps (elements that SHOULD match but don't)
3. **(v1.1)** The prompt distinguishes THREE states:
   - **Not enabled**: `--micro-prime` flag not passed (check pipeline.env)
   - **Enabled, all COMPLEX**: MicroPrime active but all elements escalated (classification issue)
   - **Enabled, elements processed**: Templates matched and/or Ollama generated (the happy path)
   Each state requires different diagnosis and different recommendations.

---

## 4. REQ-CSH-P-003: C# Query Prime Evaluation Prompt

### Purpose

A prompt for evaluating Query Prime's C#-specific security verification — database detection, parameterization checking, false positive management, and the anchor sanitizer's effectiveness.

### Structure

**Section 1 — Anchor Sanitizer Effectiveness**
- Read the seed file (`prime-context-seed-enriched.json`)
- For each database-facing task: check `replaced_anchors` field
- Were anti-pattern anchors ("string interpolation") replaced with safe versions?
- Was `negative_scope` sanitized? (check for "Parameterized queries not used" entry)
- Was `task_description` sanitized? (check for "string-interpolated SQL" language)

**Section 2 — Anzen Gate Coverage**
- Check `query_security.total_work_items` — does it reflect actual DB-facing files?
- Check `query_security.by_database` — are all databases represented (PostgreSQL, Spanner, Redis)?
- Were there files that SHOULD have been verified but were skipped? (compare `total_work_items` vs count of `.cs` files with database imports)
- Did the seed→FeatureSpec bridge work? (check if `detected_database` flowed through)

**Section 3 — Parameterization Compliance**
- Read AlloyDBCartStore.cs — does it use `NpgsqlParameter` / `AddWithValue`?
- Read SpannerCartStore.cs — does it use `SpannerParameterCollection`?
- Check `sql_injection_risk` in `semantic_issue_breakdown` — should be 0
- Check `query_security_injection` — should be 0
- Compare against prior runs (was there a reduction?)

**Section 4 — False Positive Assessment**
- Check SpannerCartStore for false positives — our REQ-KZ-CS-200i exemption should suppress `sql_injection_risk` on table-name interpolation
- Check `query_security_lifecycle` — our REQ-KZ-CS-200j `using var` recognition should suppress lifecycle warnings
- Are there any remaining false positives to investigate?

**Section 5 — Kaizen Hint Delivery**
- Did `kaizen-suggestions.json` generate sql_injection hints? (should NOT if AlloyDB is clean)
- Did credential leakage hints generate? (expected if Console.WriteLine logs connection strings)
- Were hints from prior run injected into this run's context?

**Key Files to Read**
- `prime-context-seed-enriched.json` — per-task `detected_database`, `replaced_anchors`, `negative_scope`
- `kaizen-metrics.json` — `query_security` section, `semantic_issue_breakdown`
- `kaizen-suggestions.json` — generated hints
- Generated `.cs` files — actual SQL patterns in AlloyDB/Spanner/Redis stores
- `prime-postmortem-report.json` — per-feature `disk_quality_score`, `semantic_issues`

### Acceptance Criteria

1. The prompt catches both true positives (real SQL injection) and false positives (Spanner table-name interpolation)
2. The prompt validates the anchor sanitizer's audit trail (`replaced_anchors`)
3. The prompt produces actionable feedback: what's working, what's regressed, what to fix next
4. The prompt works for any C# run with database-facing features, not just the cartservice plan

---

## 5. Prompt File Locations

| Prompt | File | Used By |
|--------|------|---------|
| REQ-CSH-P-001 (Comprehensive Evaluation) | `docs/design/prime-contractor-csharp/EVALUATE_CSHARP_RUN.md` | Agent evaluating any C# Prime Contractor run |
| REQ-CSH-P-002 (MicroPrime Validation) | `docs/design/prime-contractor-csharp/VALIDATE_CSHARP_MICROPRIME.md` | Agent diagnosing MicroPrime behavior on C# |
| REQ-CSH-P-003 (Query Prime Evaluation) | `docs/design/prime-contractor-csharp/EVALUATE_CSHARP_QUERY_PRIME.md` | Agent evaluating Query Prime security on C# |

---

## 6. Cross-Language Pattern

These prompts follow a pattern that should be replicated for Java, Go, and Node.js:

| Section | C# Specifics | Generic Pattern |
|---------|-------------|-----------------|
| Kaizen evaluation | `KAIZEN_CSHARP_REQUIREMENTS.md` grading rubric | Each language has its own `KAIZEN_{LANG}_REQUIREMENTS.md` |
| MicroPrime templates | 8 C# templates (DI constructor, property, etc.) | Each language has its own template list in `_LANGUAGE_TEMPLATES` |
| Splicer | `csharp_splicer.splice_csharp_bodies()` | Each language has (or will have) its own splicer |
| Query Prime | Npgsql `@param`, Spanner `SpannerParameterCollection` | Each language has database-specific safe patterns in `DatabasePatternRegistry` |
| Anchor sanitizer | `replaced_anchors` in seed context | Language-agnostic but database-specific |

When creating Java/Go/Node.js equivalents, replace the C#-specific references but keep the same structure. **v1.1: Also replicate the grade thresholds (REQ-CSH-P-010), delta mode (REQ-CSH-P-011), condensed rubric (REQ-CSH-P-012), and JSON output (REQ-CSH-P-014) for each language.**

---

## 7. Additional Requirements (v1.1)

### REQ-CSH-P-010: Grade Threshold Definitions

All evaluation prompts MUST use these explicit thresholds for letter grades. Removes subjective agent judgment.

**Per-Feature Thresholds (DQS-based):**

| Grade | DQS | Semantic Errors | SQL Injection Findings | Console.WriteLine |
|-------|-----|----------------|----------------------|-------------------|
| **A** | ≥ 0.95 | 0 errors | 0 | 0 |
| **B** | 0.85–0.94 | 0 errors, ≤ 3 warnings | 0 | ≤ 2 |
| **C** | 0.70–0.84 | ≤ 3 errors | 0 | ≤ 5 |
| **D** | 0.50–0.69 | 4+ errors | 1–3 | any |
| **F** | < 0.50 | any | 4+ | any |

**Per-Domain Thresholds:**

| Domain | A | B | C | D | F |
|--------|---|---|---|---|---|
| **Kaizen** (aggregate score) | ≥ 0.97 | 0.93–0.96 | 0.85–0.92 | 0.70–0.84 | < 0.70 |
| **MicroPrime** (local gen rate) | ≥ 50% elements local | 25–49% local | 1–24% local | 0% (all COMPLEX) | Not enabled |
| **Query Prime** (parameterization) | 100% + 0 FP | 100% + ≤ 2 FP | 90–99% | 70–89% | < 70% |

### REQ-CSH-P-011: Delta Evaluation Mode

The comprehensive prompt MUST support an optional `{baseline_run_dir}` input. When provided, the output includes a comparison table:

```markdown
| Metric | Run-106 (baseline) | Run-113 (current) | Delta |
|--------|-------------------|-------------------|-------|
| Aggregate score | 0.97 | 0.97 | +0.00 |
| AlloyDB DQS | 0.80 | 0.98 | **+0.18** |
| SQL injection errors | 13 | 0 | **-13** |
| Cost | $2.43 | $1.91 | -$0.52 |
| MicroPrime local % | 0% | 0% | +0% |
```

The delta column MUST bold significant changes (> 10% improvement or any regression).

### REQ-CSH-P-012: Condensed Rubric

The evaluation prompt MUST include a ~50-line condensed checklist instead of pointing to the 750-line KAIZEN_CSHARP_REQUIREMENTS.md. The checklist covers the essential pass/fail checks per grade category:

```markdown
## Quick Checklist (from KAIZEN_CSHARP_REQUIREMENTS.md)

### Disk Validation
- [ ] All .cs files pass tree-sitter syntax validation
- [ ] File-scoped namespaces used (net8.0+)
- [ ] Zero cross-language contamination (Python/Go/Java fingerprints)
- [ ] .csproj has <TargetFramework> + <Nullable>enable</Nullable>
- [ ] Type name matches filename (CartStore.cs → class CartStore)

### Semantic Checks
- [ ] Zero sql_injection_risk errors
- [ ] Zero async void methods (except event handlers)
- [ ] ILogger<T> used instead of Console.WriteLine
- [ ] No empty catch blocks (at minimum log or rethrow)
- [ ] using var / await using var for IDisposable resources

### Query Security
- [ ] AlloyDB: NpgsqlParameter / AddWithValue (not $"...{var}")
- [ ] Spanner: SpannerParameterCollection (not string interpolation)
- [ ] No connection strings logged (credential leakage)
- [ ] negative_scope sanitized (no "parameterized queries not used")

### Generation Quality
- [ ] Zero stubs remaining (no NotImplementedException in production)
- [ ] .sln correct format with project GUIDs
- [ ] Dockerfile uses multi-stage build (sdk → runtime-deps)
- [ ] Proto file uses proto3 syntax with proper package
```

### REQ-CSH-P-013: File Inventory Section

The prompt MUST include a parameterized file inventory that the agent can resolve from `{run_dir}`:

```markdown
## Files to Read (resolve from {run_dir}/plan-ingestion/)

| File | Role | Required |
|------|------|----------|
| `prime-postmortem-report.json` | Per-feature DQS, semantic issues, verdicts | Yes |
| `kaizen-metrics.json` | Aggregate scores, query_security, semantic breakdown | Yes |
| `kaizen-suggestions.json` | Generated Kaizen hints (0 = perfect) | Yes |
| `prime-context-seed-enriched.json` | Seed context: detected_database, replaced_anchors, negative_scope | For Query Prime |
| `generated/src/**/*.cs` | Actual C# code — check SQL patterns, logging, namespaces | For Semantic Checks |
| `generated/.artifacts/*-spec.md` | Spec — check if acceptance criteria were sanitized | For Query Prime |
| `generated/.artifacts/*-review-*.md` | Review — check reviewer score and flagged issues | For Feedback Loop |
| `query-security-metrics.json` | Standalone QP metrics (status, by_database) | For Query Prime |
```

### REQ-CSH-P-014: Dual Output Format

The evaluation prompt MUST produce both markdown (for human reading) and a JSON grade object (for trend tracking):

```json
{
  "run_id": "run-113-20260323T1537",
  "language": "csharp",
  "grades": {
    "kaizen": "B+",
    "microprime": "N/A",
    "query_prime": "A-",
    "composite": "B+"
  },
  "metrics": {
    "aggregate_score": 0.97,
    "alloydb_dqs": 0.98,
    "sql_injection_errors": 0,
    "microprime_local_pct": 0,
    "cost_usd": 1.91,
    "features_passed": 15,
    "features_total": 15
  },
  "delta_vs_baseline": null
}
```

This enables: `jq '.grades.composite' eval-*.json` to chart grade trends across runs.
