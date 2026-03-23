# C# Pipeline Prompt & Evaluation Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-23
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

## 2. REQ-CSH-P-001: C# Comprehensive Evaluation Prompt

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

### Acceptance Criteria

1. The prompt produces consistent grades across different agents (reproducible)
2. All grade categories map to specific REQ IDs from the requirements docs
3. The prompt works without modification for any C# Prime Contractor run (different project, different features)
4. Output format: markdown table with grades + evidence + requirement references

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

### Acceptance Criteria

1. The prompt diagnoses the "complex=15" issue seen in run-113
2. The prompt identifies template gaps (elements that SHOULD match but don't)
3. The prompt can validate both "MicroPrime active" and "MicroPrime inactive" scenarios

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

When creating Java/Go/Node.js equivalents, replace the C#-specific references but keep the same 5-section structure.
