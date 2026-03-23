# C# Pipeline Prompt Implementation Plan

> **Requirements:** [CSHARP_PIPELINE_PROMPT_REQUIREMENTS.md](CSHARP_PIPELINE_PROMPT_REQUIREMENTS.md)
> **Date:** 2026-03-23
> **Deliverables:** 3 prompt files ready for agent consumption

---

## Deliverable 1: `EVALUATE_CSHARP_RUN.md` (REQ-CSH-P-001)

### What It Does

A self-contained prompt that an agent reads alongside a C# run's output files. The agent evaluates the run across Kaizen code quality, MicroPrime cost efficiency, and Query Prime security — producing letter grades per domain with evidence and requirement references.

### Implementation

**File:** `docs/design/prime-contractor-csharp/EVALUATE_CSHARP_RUN.md`

**Structure:**
```
# Prompt: Evaluate C# Prime Contractor Run

> Provide this prompt to an agent alongside the run output paths.

## Context
[Explain what the agent is evaluating and what references to use]

## Inputs (fill before use)
- Run directory: {run_dir}
- Project root: {project_root}

## Part 1: Kaizen Code Quality (grade against KAIZEN_CSHARP_REQUIREMENTS.md)

For each category, read the postmortem and generated files, then grade:

### 1a. Disk Validation (REQ-KZ-CS-100)
[Check syntax, namespace, contamination, using statements, type/filename, .csproj]

### 1b. Semantic Checks (REQ-KZ-CS-200)
[Check sql_injection_risk count, empty catch blocks, Console.WriteLine, async void, using var lifecycle]

### 1c. Quality Scoring (REQ-KZ-CS-300)
[Check aggregate score, DQS per feature, assembly delta, stubs remaining]

### 1d. Repair Pipeline (REQ-KZ-CS-400)
[Check semantic_repairs_applied, SqlParameterizeStep firing]

### 1e. Feedback Loop (REQ-KZ-CS-500)
[Check kaizen-suggestions.json, reviewer rule effectiveness]

### 1f. Generation Profile (REQ-KZ-CS-600)
[Check .sln, .csproj, Dockerfile, .proto, appsettings.json quality]

### 1g. LanguageProfile (REQ-KZ-CS-700)
[Check protocol compliance]

## Part 2: MicroPrime Cost Efficiency

### 2a. Was MicroPrime active?
[Check kaizen-metrics.json for route, micro_prime_analysis]

### 2b. Template hits
[Check for TRIVIAL dispatch logs, template_used=true in postmortem features]

### 2c. Cost impact
[Compare cost vs all-cloud baseline if available]

## Part 3: Query Prime Security

### 3a. Anchor sanitizer effectiveness
[Read seed, check replaced_anchors, negative_scope]

### 3b. Anzen gate coverage
[Check query_security.total_work_items, by_database]

### 3c. Parameterization compliance
[Read AlloyDB/Spanner .cs files, check for @param patterns]

### 3d. False positive status
[Check for sql_injection_risk on Spanner table-name interpolation]

## Part 4: Summary Table
[Template for grades + delta vs prior run]

## Key Files to Read
[Table of file paths relative to run directory]
```

**Key design decisions:**
- Inputs are parameterized (`{run_dir}`) so the prompt works for any run
- Each grade section references specific REQ IDs
- The "Key Files to Read" section gives the agent exact paths, eliminating exploration time
- Part 4 summary table format matches what we used this session for runs 100-113

### Reusable elements from this session

The evaluation patterns we developed manually this session become the template:
- The letter grade scale (A/B/C/D/F) per category
- The comparison table format (run-100 vs run-104 vs run-106 vs run-113)
- The "What worked / What didn't" split
- The cross-domain composite grade calculation

---

## Deliverable 2: `VALIDATE_CSHARP_MICROPRIME.md` (REQ-CSH-P-002)

### What It Does

Diagnoses MicroPrime behavior on C# features — why elements classify at each tier, whether templates fire, and what cost savings result. Specifically designed to debug the "complex=15" scenario.

### Implementation

**File:** `docs/design/prime-contractor-csharp/VALIDATE_CSHARP_MICROPRIME.md`

**Structure:**
```
# Prompt: Validate C# MicroPrime Behavior

## Inputs
- Run directory: {run_dir}
- Project root: {project_root}

## Step 1: Check MicroPrime Activation
Read kaizen-metrics.json → route field. Check postmortem → micro_prime_analysis.
If None: MicroPrime may not have been enabled. Check pipeline.env for
PRIME_CONTRACTOR_EXTRA_ARGS containing --micro-prime.

## Step 2: Classification Diagnosis
Search Loki or run logs for "TRIVIAL dispatch:" and "SIMPLE dispatch:" entries.
For each C# element logged:
- What tier? What template matched (or "NONE")?
- If COMPLEX: what signal triggered it? (estimated_loc, blast_radius, etc.)

If no TRIVIAL/SIMPLE dispatch logs appear:
- Check feature-level tier: was everything COMPLEX at the feature level?
- Read seed → per-task estimated_loc. Are any under 500?
- Simulate: call classify_tier() with the seed signals to verify

## Step 3: Template Effectiveness
For each C# template in _LANGUAGE_TEMPLATES["csharp"]:
- csharp_di_constructor: requires name==parent_class + interface params
- csharp_constructor: requires name==parent_class
- csharp_property: requires getter/setter pattern
- csharp_equals, csharp_gethashcode, csharp_tostring
- csharp_dispose: requires IDisposable
- csharp_async_method: requires async Task return

Which elements COULD have matched but didn't? Common reasons:
- parent_class not set (element not recognized as method within a class)
- Kind is FUNCTION instead of METHOD
- Signature params don't match expected pattern

## Step 4: Splicer Chain
If any SIMPLE elements reached Ollama:
- Did _splice_csharp_dispatch fire? (check for "csharp_splicer" in logs)
- Was the body spliced? Or did SpliceResult.code return None?
- Was the spliced output valid? (check validate_syntax log)

## Step 5: Cost Assessment
Count from postmortem:
- Features with template_used=True: $0.00 each
- Features with local Ollama: ~$0.01-0.05 each
- Features escalated to cloud: ~$0.10-0.20 each
- Total cost vs estimated all-cloud baseline

## Key Files
[Same parameterized table]
```

---

## Deliverable 3: `EVALUATE_CSHARP_QUERY_PRIME.md` (REQ-CSH-P-003)

### What It Does

Evaluates Query Prime's C#-specific security chain — from anchor sanitization through Anzen gate to parameterized code on disk.

### Implementation

**File:** `docs/design/prime-contractor-csharp/EVALUATE_CSHARP_QUERY_PRIME.md`

**Structure:**
```
# Prompt: Evaluate C# Query Prime Security

## Inputs
- Run directory: {run_dir}
- Project root: {project_root}

## Step 1: Anchor Sanitizer Audit
Read seed (prime-context-seed-enriched.json).
For EACH task with detected_database set:
- Was replaced_anchors populated? List original→replacement pairs
- Was negative_scope stripped of "parameterized queries not used"?
- Was task_description sanitized of "string-interpolated SQL"?
- Grade: A (all three sanitized), B (partial), F (none)

## Step 2: Generated Code Security
Read each database-facing .cs file:
- AlloyDBCartStore.cs: grep for AddWithValue/@param (PASS) vs $"...{userId}" (FAIL)
- SpannerCartStore.cs: grep for SpannerParameterCollection (PASS) vs $"...{var}" (FAIL)
- RedisCartStore.cs: no SQL — check for credential leakage in logging

## Step 3: Anzen Gate Coverage
Read kaizen-metrics.json → query_security section:
- status: "no_queries_detected" vs populated
- total_work_items: should be ≥3 for cartservice (AlloyDB + Spanner + Redis)
- by_database: each DB represented?
- If total_work_items is 0 or 1: the seed→FeatureSpec bridge may be broken

## Step 4: Semantic Issue Analysis
Read semantic_issue_breakdown in kaizen-metrics.json:
- sql_injection_risk: should be 0 (anchor sanitizer + parameterized queries)
- query_security_injection: should be 0
- query_security_credential_leakage: expected some (connection string logging)
- query_security_lifecycle: should be 0 (using var recognition working)

## Step 5: False Positive Check
- SpannerCartStore: any sql_injection_risk on $"SELECT ... FROM {TableName}"?
  If yes: REQ-KZ-CS-200i exemption not firing
- Any query_security_lifecycle on lines with "using var"?
  If yes: REQ-KZ-CS-200j recognition not firing

## Step 6: Delta Report
Compare vs prior run if available:
| Metric | Prior | Current | Delta |
|--------|-------|---------|-------|
| AlloyDB DQS | ? | ? | ? |
| sql_injection_risk errors | ? | ? | ? |
| Anzen work items | ? | ? | ? |
| parameterization_rate | ? | ? | ? |

## Key Files
[Parameterized table]
```

---

## Implementation Sequence

| Order | File | Effort | Depends On |
|-------|------|--------|------------|
| 1 | `EVALUATE_CSHARP_RUN.md` | ~200 lines | Requirements doc (done) |
| 2 | `EVALUATE_CSHARP_QUERY_PRIME.md` | ~120 lines | Requirements doc (done) |
| 3 | `VALIDATE_CSHARP_MICROPRIME.md` | ~120 lines | Requirements doc (done) |

Total: ~440 lines across 3 files. No code changes — these are prompt documents only.

---

## Verification

After creating the prompts:

1. **Smoke test each prompt** on run-113 output (the most recent C# run):
   - Give `EVALUATE_CSHARP_RUN.md` to an agent with run-113 paths → verify it produces consistent grades matching our manual evaluation (0.97 score, AlloyDB DQS 0.98, 0 SQL injection)
   - Give `VALIDATE_CSHARP_MICROPRIME.md` to an agent → verify it diagnoses the "complex=15" issue
   - Give `EVALUATE_CSHARP_QUERY_PRIME.md` to an agent → verify it finds the sanitized anchors and clean AlloyDB code

2. **Cross-check against session grades**: The manual grades we assigned this session (runs 100-113) should be reproducible by an agent using these prompts.
