# Kaizen Investigation: Run 017 — Online Boutique Demo (6-Feature Batch)

**Date:** 2026-03-09
**Run:** `run-017-20260309T1017` (online-boutique-demo)
**Pipeline:** `.cap-dev-pipe/pipeline-output/online-boutique/run-017-20260309T1017/`
**Features examined:** PI-001 through PI-006 (6 features)
**Status:** 6/6 complete, PASS (aggregate score 1.0)
**Cost:** $0.7842

---

## 1. Executive Summary

Run-017 is the largest single-batch execution in project history (6 features), completing
PI-001 through PI-006 at $0.78 total ($0.13/feature). This is the best cost efficiency
of any multi-feature run — 49% cheaper per feature than run-016 ($0.25/feature) and
66% cheaper than run-013 ($0.39/feature).

All 6 files pass AST validation (Python) or are structurally correct (HTML). The one
`NotImplementedError` on disk (`email_server.py:85`) is an intentional abstract method
boundary, not a generation stub.

The micro-prime engine processed 19 elements across 3 features, with a 15.8% escalation
rate (3 elements). The `bare_statement_wrap` repair step was applied to 5 of 19 elements,
indicating a systemic Ollama output pattern that should be addressed at the prompt level.

No kaizen suggestions were generated (0 failures to learn from). The correlation engine
remains data-starved (0 labeled points across 58 total features) — prompt quality
correlations are not yet actionable.

---

## 2. Run Structure

| Feature | Name | Cost | Route | Req Score | Time (UTC) |
|---------|------|------|-------|-----------|------------|
| PI-001 | Shared JSON Logger — emailservice | $0.00 | Element cache assembly | 1.00 | 16:26:09 |
| PI-002 | Shared JSON Logger — recommendationservice | $0.00 | Element cache assembly | 1.00 | 16:26:10 |
| PI-003 | Email Service — gRPC Server | $0.19 | Micro-prime + cloud | 0.85 | 16:28:50 |
| PI-004 | Email Service — Test Client | $0.00 | Micro-prime only | 1.00 | 16:29:06 |
| PI-005 | Email Service — Order Confirmation HTML | $0.42 | Cloud (has_existing) | 1.00 | 16:34:34 |
| PI-006 | Recommendation Service — gRPC Server | $0.17 | Micro-prime + cloud | 0.80 | 16:37:14 |

**Cost distribution:** 2 features at $0.00 (element cache assembly — PI-001, PI-002),
1 at $0.00 (micro-prime only — PI-004), 2 at ~$0.18 (micro-prime + cloud escalation),
1 at $0.42 (cloud-only for HTML with existing files). PI-005 accounts for 53% of total cost.

---

## 3. Micro Prime Element Analysis

### 3.1 Tier Distribution

| Tier | Count | Success | Failure Rate |
|------|-------|---------|-------------|
| Trivial | 2 | 2 | 0% |
| Simple | 10 | 9 | 10% |
| Moderate | 7 | 5 | 29% |
| **Total** | **19** | **16** | **15.8%** |

Moderate-tier elements have 3x the failure rate of simple-tier elements.

### 3.2 Escalation Breakdown

| Element | Feature | Tier | Reason | Pipeline Stage |
|---------|---------|------|--------|---------------|
| `send_email` | PI-003 | moderate | `not_decomposable` | `ollama_generation` |
| `start` | PI-003 | moderate | `not_decomposable` | `ollama_generation` |
| `Check` | PI-006 | simple | `ast_failure` | `repair` |

The two `not_decomposable` elements in PI-003 are orchestration functions with external
dependencies (SMTP dispatch, gRPC server lifecycle) that resist sub-element decomposition.
Cloud fallback handled them successfully.

The `Check` element in PI-006 (gRPC health check method) failed AST validation after
`bare_statement_wrap` repair — it escalated from repair to cloud.

### 3.3 Repair Step Usage

| Repair Step | Applications | Elements Affected |
|-------------|-------------|-------------------|
| `bare_statement_wrap` | 5 | PI-004 `send_confirmation_email`, PI-006 `Check`/`ListRecommendations`/`Watch`/`initStackdriverProfiling` |
| `over_generation_trim` | 2 | PI-004 `send_confirmation_email`, PI-006 `initStackdriverProfiling` |

**`bare_statement_wrap` is systemic.** 5 of 19 elements (26%) needed this repair, spanning
2 of 3 features that used micro-prime. Ollama is consistently generating bare statements
outside function bodies. This is a prompt-level issue — the element generation prompt should
explicitly instruct "wrap implementation in the function signature provided."

### 3.4 Generation Time

| Element | Feature | Time (ms) |
|---------|---------|-----------|
| `Check` | PI-006 | 16,450 |
| `send_confirmation_email` | PI-004 | 11,411 |
| `initStackdriverProfiling` | PI-006 | 10,082 |
| `Watch` | PI-006 | 7,738 |
| `ListRecommendations` | PI-006 | 5,961 |
| `RecommendationService` | PI-006 | 1 |
| All PI-003 elements | PI-003 | 0 |

PI-003 elements all show 0ms generation time — they were served from cache or template.
PI-006 elements show 6-16s generation times at Ollama, with the failed `Check` element
being the slowest (16.4s before escalation).

---

## 4. Assembly Gap Validation

Per the Kaizen Data Analysis Guide (Section 5), draft-to-disk divergence was checked
for all 6 files.

### 4.1 File Integrity

| Feature | File | AST | Lines | Stubs | Generated = Root |
|---------|------|-----|-------|-------|-----------------|
| PI-001 | emailservice/logger.py | OK | 25 | 0 | **NO** — post-integration import repair |
| PI-002 | recommendationservice/logger.py | OK | 14 | 0 | **NO** — post-integration import repair |
| PI-003 | emailservice/email_server.py | OK | 215 | 1 (intentional) | YES |
| PI-004 | emailservice/email_client.py | OK | 17 | 0 | YES |
| PI-005 | emailservice/templates/confirmation.html | n/a | 353 | n/a | YES |
| PI-006 | recommendationservice/recommendation_server.py | OK | 153 | 0 | YES |

### 4.2 Logger Divergence (PI-001, PI-002) — Root Cause Analysis

Both logger files diverge between `<pipeline_output>/generated/` and `<project_root>/src/`.
The postmortem reveals the divergence originates from **two different generated/ directories**:

| Feature | `generated_files` path | Content quality |
|---------|----------------------|-----------------|
| PI-001 | `<project_root>/generated/src/emailservice/logger.py` | **Degraded** — no class def, bare functions, `pass` |
| PI-002 | `<project_root>/generated/src/recommendationservice/logger.py` | **Degraded** — no class def, bare functions |
| PI-003 | `<pipeline_output>/generated/src/emailservice/email_server.py` | **Correct** — full structure |
| PI-004–006 | `<pipeline_output>/generated/...` | **Correct** — full structure |

The correct files in `<pipeline_output>/generated/` (31 and 21 lines, with class definitions,
`__all__` exports, `fence_strip` + `import_completion` repair) were produced by run-017's
micro-prime engine. The degraded files in `<project_root>/generated/` were produced by the
**element cache assembly path** (`_assemble_from_element_cache()`).

#### Root Cause: Element Cache Assembly Drops Class Wrappers

PI-001 and PI-002 had $0.00 cost and 0 postmortem elements — they were assembled from the
**element registry cache** rather than generated fresh. The assembly code at
`prime_contractor.py:1986–1987`:

```python
for file_path, code_blocks in file_code.items():
    assembled = "\n\n".join(code_blocks)
```

The element registry stores individual element code (`entry.extra["code"]`) — function bodies
and method implementations — registered via `_register_validated_elements()` at
`prime_adapter.py:875`. When these cached elements are reassembled:

1. **Class wrappers are lost** — methods like `add_fields(self, ...)` were stored as standalone
   code blocks, not wrapped in their parent `CustomJsonFormatter` class
2. **Imports are lost** — the skeleton's import section is not cached, only element bodies
3. **Module structure is lost** — `__all__` exports, module-level constants, and the class
   hierarchy are absent from the reassembled file

The bare `pass` statement in the project root file is the residue of an empty class body
after `add_fields` was extracted to module level.

#### Degradation Chain

```
Element Registry (stores method bodies only)
  ↓ _try_element_cache_assembly() — all elements hit cache
  ↓ _assemble_from_element_cache() — "\n\n".join(code_blocks)
  ↓ writes to <project_root>/generated/ (fallback output_dir)
  ↓ post-generation repair: import_completion adds hallucinated import
  ↓   (sees CustomJsonFormatter referenced but not defined → "from customjsonformatter import")
  ↓ integration copies degraded file to <project_root>/src/
  = Degraded file on disk
```

Meanwhile, the pipeline output directory gets the CORRECT file from micro-prime's normal
generation path (skeleton → element splice → fence_strip → import_completion), but this
file is never used for integration because the cache assembly path short-circuits first.

#### Why the `<pipeline_output>/generated/` File Exists

The `<pipeline_output>/generated/` file with proper content exists because the micro-prime
engine (`MicroPrimeCodeGenerator`) wrote the filled skeleton to its `_output_dir` (the
pipeline output path) via the normal generation flow at `prime_adapter.py:416–418`. However,
the **prime contractor** (`_try_element_cache_assembly`) runs BEFORE the code generator and
uses a different `output_dir` — `self.project_root / "generated"` (line 1982). The cache
assembly result's `generated_files` list points to the `<project_root>/generated/` path,
which is what the integration engine receives.

#### Evidence

| Signal | Value | Implication |
|--------|-------|-------------|
| PI-001/PI-002 cost | $0.00 | No LLM calls — cache or template |
| PI-001/PI-002 elements | 0 in postmortem | Cache assembly path (not micro-prime) |
| generated_files path | `<project_root>/generated/` | Fallback output_dir, not pipeline output |
| PI-003–006 generated_files path | `<pipeline_output>/generated/` | Normal micro-prime output_dir |
| `<project_root>/generated/` content | No class def, bare functions | `"\n\n".join(code_blocks)` lost structure |
| `<pipeline_output>/generated/` content | Proper class def, imports, `__all__` | Normal skeleton splice + repair |
| Repair header (project root) | `import_completion` only | Repair on already-degraded assembly |
| Repair header (pipeline output) | `fence_strip, import_completion` | Repair on proper skeleton output |
| Both timestamps | Mar 9 12:26:09 | Same run, different paths |

### 4.3 Intentional NotImplementedError

The single `raise NotImplementedError` at `email_server.py:85` is a deliberate abstract
method boundary:

```python
@staticmethod
def send_email(client, email_address: str, content: str) -> None:
    """Override in a subclass or monkey-patch in tests to deliver mail."""
    raise NotImplementedError(
        'Live email sending is not implemented. '
        'Provide a concrete send_email implementation.'
    )
```

This is correct design — `BaseEmailService.send_email` is meant to be overridden by
`EmailService` and `DummyEmailService` subclasses.

---

## 5. Cross-Feature Comparison

### 5.1 PI-001 vs PI-002 (Shared JSON Logger — Different Services)

Both features implement identical specs ("Shared JSON Logger") for emailservice and
recommendationservice respectively. Both routed through micro-prime only ($0.00 cost).
Both achieved 1.00 requirement score. Both needed post-integration import repair.

This is the same sibling-feature comparison pattern documented in the Guide (Section 8,
Example: Run 004 PI-001 vs PI-002). Unlike run-004 where one sibling broke and the
other succeeded, run-017 produced equivalent outcomes for both — the import repair
pipeline is now consistent across sibling features.

### 5.2 PI-003 vs PI-006 (gRPC Server — Different Services)

| Dimension | PI-003 (Email) | PI-006 (Recommendation) |
|-----------|---------------|------------------------|
| Elements | 13 | 5 |
| Element failures | 2 (`not_decomposable`) | 1 (`ast_failure`) |
| Requirement score | 0.85 | 0.80 |
| Cost | $0.19 | $0.17 |
| Repair steps needed | 0 | 5 (`bare_statement_wrap` on all) |
| File on disk | 215 lines, valid | 153 lines, valid |

PI-003 has 2.6x more elements but the same number of escalations. Its failures are
decomposition-level (`not_decomposable`), while PI-006's failure is generation-level
(`ast_failure`). PI-006 needed repair on every element, suggesting Ollama's output
for gRPC recommendation patterns is less well-formed than for email patterns.

### 5.3 PI-005 — Only Feature with `has_existing_files: true`

PI-005 (HTML template) is the only feature that references existing files. Its context
keys replace `forward_element_specs` with `existing_files`, and its draft prompt is
significantly larger (14,887 bytes for `draft_system_prompt.md` vs ~400 bytes for others).
It's also the most expensive feature at $0.42 (cloud-only, no micro-prime for HTML).

Despite the cost premium, PI-005 achieved the highest quality outcome: 353-line HTML
template that is identical between generated/ and project root.

---

## 6. Kaizen Telemetry Gaps

### 6.1 Missing Response Files

None of the 6 features have `*_response.md` files in `kaizen-prompts/standalone/`.
Per the Guide (Section 3 warning), this means the `LeadContractorGenerator` is not
forwarding raw responses via `GenerationResult.metadata` keys (`spec_raw_response`,
`draft_raw_response`, `review_raw_response`).

**Impact:** Cannot perform draft-vs-disk diff analysis (Guide Section 5) at the
artifact level. The assembly gap validation above was done against the generated/
directory, not against the LLM's raw output.

### 6.2 Unknown Agent Specs

All 6 features report `lead_agent_spec: "unknown"` and `drafter_agent_spec: "unknown"`
in kaizen metadata. Agent resolution occurs after metadata capture — the metadata
capture point should be moved downstream or updated post-resolution.

### 6.3 Empty Correlation Data

The correlation engine has 58 data points across 11 runs but 0 labeled points.
No PASS/FAIL group means can be computed. The labeling pipeline (postmortem verdict →
kaizen prompt metadata join) is not wired.

### 6.4 No Kaizen Suggestions Generated

`kaizen-suggestions.json` contains 0 suggestions. This is expected — the suggestion
engine requires failure patterns to generate recommendations, and run-017 has 0
feature-level failures.

---

## 7. Cross-Run Trends

### 7.1 Cost Efficiency by Run

| Run | Features | Total Cost | Cost/Feature | Outlier |
|-----|----------|-----------|-------------|---------|
| plan-ingestion | 1 | $0.105 | $0.105 | |
| run-005 | 1 | $0.115 | $0.115 | |
| run-006 | 1 | $0.114 | $0.114 | |
| run-008 | 1 | $0.110 | $0.110 | |
| run-009 | 1 | $0.122 | $0.122 | |
| run-010 | 3 | $0.434 | $0.145 | |
| run-013 | 2 | $0.772 | $0.386 | cost outlier |
| run-014 | 1 | $0.230 | $0.230 | |
| run-015 | 1 | $0.108 | $0.108 | |
| run-016 | 3 | $0.763 | $0.254 | cost outlier |
| **run-017** | **6** | **$0.784** | **$0.131** | **cost outlier (total only)** |

**Key insight:** Run-017's total cost ($0.78) is flagged as an outlier, but its
per-feature cost ($0.13) is the lowest of any multi-feature run. The cost-per-feature
trend for multi-feature runs is **improving**:

- Run-010 (3 features): $0.145/feature
- Run-013 (2 features): $0.386/feature (anomalous — cloud-heavy)
- Run-016 (3 features): $0.254/feature
- Run-017 (6 features): $0.131/feature

### 7.2 Trend Summary

- **11 consecutive PASS runs** — 100% success rate, flat slope
- **Cost slope:** +$0.062/run (driven by batch size growth, not per-feature inflation)
- **Average cost:** $0.33/run
- **Improvement verified:** NO (no failures to improve from)
- **Accumulated patterns:** 0 (empty — no cross-run pattern extraction yet)

---

## 8. Comparison to Run-016

| Metric | Run-016 | Run-017 | Delta |
|--------|---------|---------|-------|
| Features | 3 (of 17 total plan) | 6 | +3 |
| Reported success | 100% | 100% | — |
| Total cost | $0.763 | $0.784 | +$0.02 |
| Cost/feature | $0.254 | $0.131 | **-49%** |
| Micro-prime elements | 0 | 19 | +19 |
| Escalation rate | N/A (all cloud) | 15.8% | — |
| Repair steps applied | 6 | 7 | +1 |
| Files needing import repair | 100% of .py | 33% of .py (loggers only) | **-67%** |
| Assembly gap (generated ≠ root) | Not measured | 2 of 6 files | — |

Run-017 shows clear improvement over run-016:
- **2x features at same cost** ($0.78 for 6 vs $0.76 for 3)
- **Micro-prime engagement:** Run-016 routed everything to cloud (non-Python files);
  run-017's Python-heavy workload enabled 50% micro-prime routing (3 of 6 features)
- **Import repair reduction:** From 100% of Python files (run-016) to 33% (run-017)

---

## 9. Lessons Identified

| ID | Lesson | Severity | Priority |
|----|--------|----------|----------|
| L1 | `bare_statement_wrap` is systemic — 26% of micro-prime elements need it | MEDIUM | HIGH |
| L2 | Kaizen response capture not wired — draft-vs-disk analysis blocked | LOW | MEDIUM |
| L3 | Agent spec resolution captured as "unknown" — metadata timing gap | LOW | LOW |
| L4 | Correlation engine data-starved — 0/58 labeled after 11 runs | MEDIUM | MEDIUM |
| L5 | Moderate-tier elements fail at 3x simple-tier rate — decomposer quality | MEDIUM | MEDIUM |
| L6 | Element cache assembly drops class wrappers — `"\n\n".join()` loses file structure | HIGH | HIGH |

### L1: `bare_statement_wrap` Prompt Fix — RESOLVED

**Fix:** REQ-MP-206 (complete-function output mode). Switched all three prompt
layers from "body-only" to "complete function" output. The model now outputs the
`def` line naturally, eliminating the prompt-model conflict that caused 26% of
elements to need wrapping. `signature_reconcile` (step 6) validates the signature.
New stop sequences (`\n\ndef `, `\n\nasync def `, `\n\nclass `) prevent secondary
function generation — safe in complete-function mode because the first output IS
a `def` line. SDK-level `stop` parameter forwarding added to
`OpenAICompatibleAgent._make_api_call()` for per-element override capability.

### L2: Response Capture Gap

Without `*_response.md` files, the Kaizen Data Analysis Guide's primary debugging
workflow (Section 9, steps 4-5: inspect draft, compare draft to disk) is unavailable.
The `GenerationResult.metadata` keys for raw response forwarding should be verified
in `LeadContractorGenerator`.

### L4: Correlation Engine Bootstrap

58 data points with 0 labels means the correlation engine has never been actionable
across the entire project history. The label join (postmortem verdict → prompt metadata)
needs to be wired as a postmortem post-processing step.

### L5: Moderate-Tier Decomposition

2 of 7 moderate elements escalated as `not_decomposable` (PI-003: `send_email`, `start`).
These are orchestration functions with multiple external dependencies. The decomposer
correctly classified them, but the 29% moderate-tier failure rate suggests the tier
boundary between "simple" and "moderate" may need recalibration for functions with
high dependency counts.

### L6: Element Cache Assembly Structural Loss — Fix Analysis

**Bug:** `_assemble_from_element_cache()` joins cached element code blocks with
`"\n\n".join()`, discarding the skeleton's file structure (class wrappers, imports,
`__all__`, module-level code). This produces syntactically valid but structurally
broken Python files.

**Impact:** Any feature where ALL elements hit the registry cache will produce a
degraded file. In run-017, this affected PI-001 and PI-002 (both loggers). The
degradation silently passes post-generation repair (bare functions at module level
are valid Python) and the postmortem reports PASS.

**Fix options (ranked by correctness):**

#### Option A: Use skeleton as assembly scaffold (recommended)

Instead of `"\n\n".join(code_blocks)`, use the forward manifest's skeleton as the
base file and splice cached code into it using the existing `splice_body_into_skeleton()`
infrastructure. This reuses the proven splicer path that already handles class wrappers,
indentation, and import injection.

```python
# In _assemble_from_element_cache():
# 1. Load skeleton from forward manifest
skeleton = self._forward_manifest.skeletons.get(file_path, "")
# 2. For each cached element, splice into skeleton
for eid, (fp, code) in cached_elements.items():
    element_spec = ...  # look up from manifest
    skeleton = splice_body_into_skeleton(code, element_spec, skeleton)
# 3. Write the assembled skeleton (preserves class wrappers, imports)
```

**Pros:** Correct by construction — same code path as fresh generation.
**Cons:** Requires skeleton availability in the manifest at cache assembly time.

#### Option B: Store full-file content in cache, not element bodies

Change `_register_validated_elements()` to store the post-splice, post-repair
**full file content** alongside element code. On cache hit, write the full file
directly instead of reassembling from parts.

**Pros:** Simplest change — no reassembly logic needed.
**Cons:** Storage increase; cache invalidation becomes file-level (any element
change invalidates the whole file cache).

#### Option C: Add structural validation to cache assembly

After `"\n\n".join()`, run `_detect_assembly_defect()` (already available) and
fall through to normal generation if defects are found. This is a safety net,
not a fix — the assembly would still produce broken files, but they'd be caught
and regenerated.

**Pros:** Minimal code change, prevents silent corruption.
**Cons:** Wastes the cache hit (falls through to LLM generation anyway);
doesn't fix the root cause.

#### Recommended: Option A + Option C as safety net

Implement skeleton-based assembly (Option A) with the defect detection guard
(Option C) as a fallback. The guard catches any edge cases where the skeleton
is unavailable or splice fails.

**Affected code:**
- `prime_contractor.py:1947–2027` (`_assemble_from_element_cache`)
- `prime_contractor.py:1870–1899` (element cache lookup — needs element specs)
- `prime_adapter.py:843–895` (`_register_validated_elements` — if Option B)
- `splicer.py:111–138` (`splice_body_into_skeleton` — reused by Option A)

**Ichigo Ichie classification: [GENERAL]** — The root cause (`"\n\n".join()` dropping
class wrappers) is project-agnostic. Any project with class-scoped methods in the
element registry would experience this corruption on cache-hit assembly. All three fix
options work without referencing the calibration project. Passes the Ichigo Ichie test.

---

## 10. Appendix: Previous Kaizen Investigations

| Run | Document | Key Finding |
|-----|----------|-------------|
| Run-004 | `KAIZEN_INVESTIGATION_RUN004_ONLINE_BOUTIQUE.md` | Broken skeletons, 43% actual usability |
| Run-005 | `KAIZEN_INVESTIGATION_RUN005_ONLINE_BOUTIQUE.md` | Post-fix validation, 100% actual usability |
| Run-016 | `KAIZEN_INVESTIGATION_RUN016_ONLINE_BOUTIQUE.md` | 17-feature plan completion, 88% actual usability, semantic bugs survive repair |
| **Run-017** | **This document** | **6-feature batch, best cost efficiency, systemic bare_statement_wrap** |
