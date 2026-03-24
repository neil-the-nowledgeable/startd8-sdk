# Hayai Design Principle

Purpose: establish a cross-cutting design principle for the startd8-sdk pipeline — quality knowledge must bind to artifacts at the earliest pipeline stage where it can be resolved, not deferred to later stages where contamination has already propagated.

This document is intentionally living guidance. Update it as new early-binding opportunities are identified.

---

## The Principle

**Hayai** (早い) — "early." In Japanese, 早い conveys both speed and timeliness — doing something at the right, earliest moment rather than waiting. The character 早 (hayai) literally depicts the sun just appearing above the horizon: the earliest light.

Applied to the pipeline: **when quality knowledge (coding standards, security rules, anti-patterns, domain constraints) can be derived from data available at stage N, it must bind to artifacts at stage N — not stage N+k. Every intermediate stage in the gap is a contamination window where bad patterns enter artifacts, get amplified by LLMs, and require progressively more expensive correction.**

---

## The Diagnostic Question

> **"Do we know enough at this stage to prevent this defect?"**

If the answer is yes and the pipeline is not acting on it, there is a Hayai violation.

---

## Relationship to Other Principles

Hayai completes the anti-waste family alongside the existing design principles:

| Principle | Japanese | Focus | Waste Eliminated | Diagnostic Question |
|-----------|----------|-------|-----------------|-------------------|
| **Mottainai** | もったいない | Don't discard artifacts | Redundant regeneration within a run | "Has this already been computed?" |
| **Kaizen** | 改善 | Don't discard lessons | Repeated failures across runs | "Have we seen this problem before?" |
| **Warm Up** | ウォームアップ | Don't discard context | Lost knowledge across toolchain transitions | "Does the next tool know what the last tool learned?" |
| **Hayai** | 早い | Don't defer enforcement | Contamination from late-bound quality knowledge | "Do we know enough to prevent this defect?" |

Where Mottainai asks "has this artifact been computed?" and Kaizen asks "have we learned this lesson?", Hayai asks **"do we already have the knowledge to prevent this mistake — and if so, why aren't we using it yet?"**

Hayai and Mottainai are complementary but distinct:
- **Mottainai** prevents discarding artifacts that flow *forward* through the pipeline.
- **Hayai** prevents *deferring* quality signals that should bind *earlier* in the pipeline.

A system can obey Mottainai (all artifacts forwarded) while violating Hayai (quality knowledge not applied until the last stage). The PI-002 incident demonstrated this: coding standards existed in the `LanguageProfile` and were forwarded to the spec builder — Mottainai satisfied — but they weren't applied at plan ingestion time, allowing anti-patterns to propagate through three intermediate stages unchecked.

---

## Why This Matters

### The Contamination Window

An LLM-backed pipeline has a unique failure mode: **LLMs amplify patterns in their context.** When an anti-pattern (e.g., `Console.WriteLine`) enters the pipeline at stage 1 and quality knowledge to prevent it (e.g., "use ILogger<T>") isn't applied until stage 4, the LLM at stages 2 and 3 treats the anti-pattern as authoritative input and reproduces it in its output.

```
Stage 1: Plan ingestion    → Console.WriteLine in task description
Stage 2: Spec generation   → LLM echoes Console.WriteLine into spec (amplification)
Stage 3: Draft generation  → LLM follows spec, generates Console.WriteLine (amplification²)
Stage 4: Review            → Reviewer catches it (or doesn't)
```

Each LLM amplification stage makes correction harder:
- At stage 1, sanitization is a regex transform (cost: ~0)
- At stage 2, the spec builder must override its own LLM's output (cost: wasted tokens)
- At stage 3, the drafter must resolve a contradiction between spec and system prompt (cost: inconsistent output)
- At stage 4, the reviewer must adjudicate conflicting standards (cost: score disagreement, human triage)

### The Compounding Cost

Late-bound quality knowledge doesn't just miss defects — it creates **contradictions** that are harder to resolve than the original defect:

1. **Spec says "use Console.WriteLine"** (because the plan said so)
2. **System prompt says "NEVER use Console.WriteLine"** (because the coding standard says so)
3. **The LLM must choose** — and its choice is unpredictable, context-dependent, and unreviewable

This is not a quality problem. It is a **precedence problem** — and precedence problems are strictly harder than quality problems, because they require the LLM to reason about meta-rules instead of following a single clear instruction.

Early binding eliminates precedence problems entirely: if the anti-pattern is transformed before the spec LLM sees it, there is no contradiction to resolve.

---

## The Pattern: Resolve Once, Propagate Forward, Re-Hydrate When Needed

The general Hayai-compliant pattern for quality knowledge in a pipeline:

1. **Resolve at the earliest stage where the input data exists.** If `target_files` are known at plan ingestion, resolve the language profile at plan ingestion — not at spec-building time.

2. **Persist scalar properties in the artifact.** Pipeline artifacts (seeds, specs) are typically JSON-serializable. Complex objects (LanguageProfile instances) can't be serialized, but their scalar properties (`language_id`, `coding_standards`, `system_prompt_role`) can be.

3. **Act on the knowledge immediately.** If the resolved profile has a `sanitize_code_examples()` method, call it on the task description before writing the seed. Don't defer sanitization to a downstream stage.

4. **Re-hydrate when the full object is needed.** Downstream stages that need the full `LanguageProfile` object can re-hydrate it cheaply from `language_id` via a registry lookup — no re-resolution needed.

5. **Downstream enforcement is defense-in-depth, not the primary path.** Spec-time sanitization and review-time precedence rules still exist, but they're safety nets for edge cases (tasks that bypass enrichment, LLM hallucinations), not the primary enforcement mechanism.

---

## Canonical Violations (Baseline)

The following are Hayai violations identified in the startd8-sdk pipeline. The first three have been resolved; the remaining are open for future work.

### Violation H-1: Language Profile Late Binding (RESOLVED)

**What:** `LanguageProfile` resolved at spec-building time (`prime_contractor.py:3898`) despite `target_files` being available at plan ingestion time.

**Contamination window:** Plan ingestion → seed → spec builder (3 stages). Anti-patterns in task descriptions propagated through the seed into spec LLM output.

**Fix (REQ-TDE-200):** Language profile resolved at enrichment time. `language_id`, `coding_standards`, and `language_role` persisted in seed context. Downstream stages consume pre-enriched values via no-clobber pattern.

**Diagnostic:** "Do we know the target language at plan ingestion time?" Yes — `target_files` are available. Hayai violation.

### Violation H-2: Anti-Pattern Sanitization at Spec Time (RESOLVED)

**What:** `Console.WriteLine` → `_logger.LogInformation` transform applied only at spec-building time (`_sanitize_csharp_code_examples`), not at seed creation time.

**Contamination window:** Plan ingestion → seed (1 stage). The seed JSON contained literal `Console.WriteLine` in task descriptions, which the spec LLM echoed.

**Fix (REQ-TDE-203):** Sanitization moved to enrichment step via `LanguageProfile.sanitize_code_examples()`. Spec-time sanitization retained as defense-in-depth.

**Diagnostic:** "Do we know the anti-pattern transform at plan ingestion time?" Yes — the `LanguageProfile` can be resolved from `target_files`. Hayai violation.

### Violation H-3: Review Precedence Rule Missing (RESOLVED)

**What:** When spec and coding standards contradicted, the reviewer had no rule for which source wins. Some reviewers flagged violations (correct), others dismissed them as spec-compliant (incorrect), others missed entirely.

**Root cause:** This precedence problem existed because H-1 and H-2 were unresolved — if the spec never contained the anti-pattern, the reviewer would never face the contradiction.

**Fix:** Explicit precedence rule in `review_system` template: security violations = BLOCKING (spec cannot override), style violations = MAJOR (coding standard takes precedence). This is a safety net for cases that escape H-1/H-2 enforcement.

### Violation H-4: SQL Interpolation Detection (OPEN)

**What:** `_detect_sql_interpolation_in_examples()` runs only at spec-building time and is C#-specific. Language profiles could expose a `detect_security_anti_patterns(text) -> str` method that runs at enrichment time.

**Contamination window:** Plan ingestion → seed → spec builder (2 stages).

**Diagnostic:** "Do we know SQL interpolation is dangerous at plan ingestion time?" Yes. The knowledge exists in the language profile. Hayai violation.

### Violation H-5: Framework Import Detection (OPEN)

**What:** `framework_imports` from the language profile (used for security constraint injection in the drafter) are resolved at spec time. If database frameworks are detectable from `target_files` at plan ingestion time, the security constraint could be persisted in the seed.

**Diagnostic:** Framework detection currently requires file content inspection, not just file names. This may not be resolvable at enrichment time (no file content available). Needs investigation before classifying as a Hayai violation.

---

## Checklist: Adding New Quality Knowledge to the Pipeline

When adding a new quality signal (rule, constraint, anti-pattern, standard):

- [ ] **Identify the earliest stage where the input data is available.** What data does the signal depend on? (`target_files`? `task_description`? file content? LLM output?)
- [ ] **If the data is available at plan ingestion:** Add to the enrichment step. Persist scalar values in seed context.
- [ ] **If the data requires file content:** Cannot run at enrichment time (no filesystem access). Bind at spec time, but flag as a potential Hayai improvement if file content becomes available earlier.
- [ ] **If the data requires LLM output:** Cannot run before the LLM call. Apply as post-processing on the LLM output, before the output is forwarded downstream.
- [ ] **Add defense-in-depth at downstream stages.** Even with early binding, retain checks at spec/draft/review time for edge cases.
- [ ] **Add the quality signal to the language profile if language-specific.** Use the protocol method pattern (`sanitize_code_examples`, `detect_security_anti_patterns`) so all languages benefit from a single wiring point.

---

## Metrics

A Hayai violation can be measured by **contamination distance**: the number of pipeline stages between when the quality knowledge could have been applied and when it actually was applied.

| Contamination Distance | Impact |
|----------------------|--------|
| 0 | No violation — knowledge applied at the earliest possible stage |
| 1 | Low — one stage of potential contamination |
| 2 | Medium — anti-pattern likely amplified by one LLM call |
| 3+ | High — anti-pattern amplified by multiple LLM calls, precedence problems likely |

The goal is contamination distance = 0 for all quality signals where the input data is available.
