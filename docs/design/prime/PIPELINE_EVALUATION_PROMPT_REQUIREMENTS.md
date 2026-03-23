# Pipeline Evaluation Prompt Requirements — Language-Agnostic

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-23
> **Scope:** Define requirements for evaluation prompts that grade Prime Contractor run quality across Kaizen, MicroPrime, and Query Prime domains — applicable to ALL supported languages
> **Derived from:** `CSHARP_PIPELINE_PROMPT_REQUIREMENTS.md` v1.1 (8 structural insights generalized)
> **Language specializations:** Each language directory has a `{LANG}_PIPELINE_PROMPT_REQUIREMENTS.md` that inherits this structure and fills in language-specific columns

---

## 1. Evaluation Prompt Structure (5 Sections)

Every language evaluation prompt follows this structure:

### Section 1 — Context Block

The prompt receives either structured paths OR pasted terminal output:

**Mode A (structured):** Agent receives `{run_dir}` path directly.

**Mode B (pasted output):** Agent extracts run ID from log output and discovers paths via convention:
```
{project_root}/.cap-dev-pipe/pipeline-output/{project}/run-{id}/plan-ingestion/
```

**Key files to read:**

| File | Purpose |
|------|---------|
| `prime-result.json` | Feature count, success/fail, cost, todo_completion |
| `prime-postmortem-report.json` | Per-feature DQS, assembly delta, semantic errors |
| `prime-postmortem-summary.md` | Human-readable summary |
| `kaizen-metrics.json` | Aggregate score, semantic breakdown, todo metrics |
| `kaizen-suggestions.json` | Cross-feature improvement patterns |
| `todo-inventory.json` | TODO scan results (if instrumentation active) |
| `generated/` | Actual generated source files for spot-checking |

### Section 2 — Kaizen Evaluation

Grade each requirement section (Disk Validation, Semantic Checks, Quality Scoring, Repair Pipeline, Feedback Loop) using the language-specific Kaizen requirements doc.

Key metrics:
- Per-feature DQS scores and assembly deltas
- Semantic issue breakdown by category
- Cross-feature pattern frequency
- Contamination detection (cross-language artifacts)

### Section 3 — MicroPrime Evaluation

Diagnose MicroPrime state (see Section 3 below for 3-state model). When active:
- Tier distribution (TRIVIAL/SIMPLE/MODERATE/COMPLEX)
- Template match rate
- Local vs cloud generation ratio
- Element-level success rate and escalation causes
- Cost comparison: local generation cost vs cloud-equivalent

### Section 4 — Query Prime Evaluation

Grade security posture:
- SQL parameterization rate (all queries use parameterized form)
- Credential leakage detection (no hardcoded secrets)
- False positive rate (legitimate code flagged incorrectly)
- Anchor sanitizer effectiveness (database-specific safe patterns)

### Section 5 — Cross-Domain Summary

- Letter grades per domain (Kaizen, MicroPrime, Query Prime)
- Composite grade
- Delta vs baseline (if baseline_run_dir provided)
- Top 3 actionable improvements for next run

---

## 2. Grade Threshold Framework

### Per-Feature Grades

| Grade | DQS | Semantic Errors | `{LANG_DEFECT_1}` | `{LANG_DEFECT_2}` |
|-------|-----|-----------------|--------------------|--------------------|
| **A** | >= 0.95 | 0 errors | 0 | 0 |
| **B** | 0.85-0.94 | 0 errors, <= 3 warnings | 0 | <= 2 |
| **C** | 0.70-0.84 | <= 3 errors | 0 | <= 5 |
| **D** | 0.50-0.69 | 4+ errors | 1-3 | any |
| **F** | < 0.50 | any | 4+ | any |

**Language-specific columns:**

| Language | `{LANG_DEFECT_1}` | `{LANG_DEFECT_2}` |
|----------|--------------------|--------------------|
| C# | SQL Injection Findings | Console.WriteLine Usage |
| Java | SQL Injection Findings | System.out.println Usage |
| Go | Python Contamination | Unchecked Errors |
| Node.js | CJS/ESM Mixing | var Usage (should be const/let) |
| Python | Bare except:pass | Phantom Imports |

### Per-Domain Grades (Aggregate)

| Domain | A | B | C | D | F |
|--------|---|---|---|---|---|
| **Kaizen** (aggregate score) | >= 0.97 | 0.93-0.96 | 0.85-0.92 | 0.70-0.84 | < 0.70 |
| **MicroPrime** (local gen %) | >= 50% | 25-49% | 1-24% | 0% (all COMPLEX) | Not enabled |
| **Query Prime** (param rate) | 100% + 0 FP | 100% + <= 2 FP | 90-99% | 70-89% | < 70% |

---

## 3. MicroPrime 3-State Diagnosis

Evaluation prompts MUST distinguish these three states:

| State | Indicator | Diagnosis |
|-------|-----------|-----------|
| **Not enabled** | No `--micro-prime` flag; no tier distribution in postmortem | Pipeline config issue — `PRIME_CONTRACTOR_EXTRA_ARGS` missing `--micro-prime` |
| **Enabled, all COMPLEX** | Tier distribution shows only `complex: N`; no `simple`/`moderate`/`trivial` | Classification issue — tasks may be over-classified, or language profile not recognized |
| **Active** | Tier distribution shows mix of tiers; MicroPrime section in postmortem | Happy path — evaluate template match rate, local %, cost savings |

---

## 4. Delta Evaluation Mode

When `{baseline_run_dir}` is provided, the evaluation MUST include:

- Side-by-side metric comparison table (aggregate score, semantic issues, cost, tier distribution)
- Per-category delta (e.g., `sql_injection_risk: 6 -> 0, -100%`)
- Root cause attribution for improvements/regressions
- Verdict: IMPROVED / STABLE / REGRESSED

---

## 5. Dual Output Format

Evaluations produce BOTH:

**Markdown:** Human-readable tables, per-feature grades, narrative summary.

**JSON grades object:**
```json
{
  "run_id": "run-113",
  "language": "csharp",
  "kaizen": "A-",
  "microprime": "N/A",
  "query_prime": "B+",
  "composite": "B+",
  "features_graded": 15,
  "features_a": 10,
  "features_b": 3,
  "features_c": 2,
  "delta_vs_baseline": "+0.007"
}
```

---

## 6. Condensed Rubric Checklist

Each language's evaluation prompt includes a ~50-line condensed checklist (not a pointer to the 750+ line requirements doc). Structure:

```
## Quick Rubric
- [ ] All features PASS verdict?
- [ ] Aggregate DQS >= 0.95?
- [ ] 0 semantic errors (errors, not warnings)?
- [ ] 0 {LANG_DEFECT_1} findings?
- [ ] {LANG_DEFECT_2} count <= 2?
- [ ] No cross-language contamination?
- [ ] Dockerfile: digest pinned, multi-stage, non-root USER?
- [ ] MicroPrime: tier distribution shows mix (not all COMPLEX)?
- [ ] Query Prime: 100% parameterization, 0 false positives?
- [ ] TODO completion: activated and executed (if generation_profile=full)?
- [ ] Cost per feature <= $0.20?
- [ ] No orphan dependencies in requirements files?
...
```

---

## 7. File Inventory Helper

The evaluation prompt includes a discovery section:

```
Given run directory {run_dir}, these files exist:
- prime-result.json (feature count, cost, todo_completion)
- prime-postmortem-report.json (per-feature DQS, semantic issues)
- prime-postmortem-summary.md (human-readable)
- kaizen-metrics.json (aggregate score, semantic breakdown)
- kaizen-suggestions.json (improvement patterns)
- todo-inventory.json (TODO scan results)
- generated/ (source files — spot-check 2-3 for quality)
- instrumentation/ (TODO completion artifacts, if active)
- batch-postmortem-report.json (cross-run progression)
```

---

## 8. Language Specialization Contract

Each language MUST provide a `{LANG}_PIPELINE_PROMPT_REQUIREMENTS.md` that:

1. Inherits the 5-section structure from this document
2. Fills in `{LANG_DEFECT_1}` and `{LANG_DEFECT_2}` columns
3. Defines language-specific evaluation rubric items
4. Lists language-specific key files to spot-check
5. Defines language-specific MicroPrime evaluation criteria
6. Defines language-specific Query Prime patterns (database + ORM combinations)
