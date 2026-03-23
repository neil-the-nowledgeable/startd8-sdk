# Prompt Accidental Complexity Audit — Prime Contractor Pipeline

> **Date:** 2026-03-23
> **Status:** FINDINGS + PLAN
> **Scope:** All prompt templates, fallback strings, hardcoded fragments, and prompt poisoning vectors across the spec→draft→review pipeline
> **Method:** Exhaustive read of contractor_prompts.yaml, prompts/__init__.py, spec_builder.py, drafter.py, reviewer.py + trace-back from low-graded C# artifacts to identify upstream prompt quality issues
> **Motivation:** C# run-114 scored B+ overall but three artifacts (HealthCheckService B-, CartServiceTests B-, AlloyDBCartStore D) followed their specs faithfully — the specs themselves contained anti-patterns locked in by the prompt pipeline

---

## 1. Executive Summary

The Prime Contractor prompt pipeline has accrued accidental complexity through three mechanisms:

1. **Prompt fragmentation** — Templates are split across YAML, Python fallback strings, and hardcoded f-strings in 3 modules. Changes to one location are not propagated, creating 19 mismatches.

2. **Python-era legacy** — Instructions written for Python-only generation ("Do NOT wrap in a Python script, generator function") persist across all 5 languages. The "CRITICAL imports" instruction appears **8 times** (4 in YAML, 4 in fallbacks).

3. **Negative scope poisoning** — The plan ingestion LLM over-interprets reference implementation patterns as binding exclusions. "Reference uses Console.WriteLine" becomes `negative_scope: ["Do NOT use ILogger<T>"]`, which then locks anti-patterns into specs that downstream generators faithfully implement.

**Net effect:** The prompts are simultaneously too verbose (redundant instructions inflate token usage) and too weak (quality-critical guidance is either absent, contradicted by negative_scope, or dropped by budget enforcement).

---

## 2. Fragmentation: Three Sources of Truth

### Current State

| Source | Location | Templates | Role |
|--------|----------|:-:|--------|
| **YAML** | `contractor_prompts.yaml` | 18 | "Single source of truth" (per header comment) |
| **Fallback** | `prompts/__init__.py` | 13 | Backup when YAML unavailable |
| **Hardcoded** | `spec_builder.py`, `drafter.py` | 7+ | Bypass both YAML and fallback |

### Mismatches Found

| Category | Count | Risk |
|----------|:---:|------|
| Fallback shorter than YAML (missing guidance) | 6 | Degraded prompts when YAML unavailable |
| Fallback has EXTRA guidance not in YAML | 3 | Inconsistent behavior |
| Missing from fallback entirely | 5 | `KeyError` crash when YAML unavailable |
| Hardcoded fragments bypass template system | 7 | Impossible to audit or version-control |

### Key Example: spec_edit_preamble

**YAML version** (10 lines):
```yaml
## EDIT MODE
**Task type: {task_verb}** existing code.
Describe ONLY additions and modifications. List unchanged functions/classes.
Specify exact insertion points.
```

**Fallback in spec_builder.py** (40 lines):
```python
"## EDIT MODE — Existing Code Modification\n"
"**Task type: {task_verb}** existing code.\n\n"
"This task MODIFIES an existing file. The existing code is shown below...\n"
"Your specification must:\n"
"- Describe ONLY the additions and modifications needed\n"
"- List which existing functions/classes to keep unchanged\n"
"- NOT redesign or restructure existing code\n"
"- Specify exact insertion points...\n"
```

The fallback has 4 extra bullet points that the YAML version omits. Which one is correct? Nobody knows — there's no test that verifies parity.

---

## 3. Python-Era Legacy: 8× Redundant Instructions

### "Do NOT wrap in a Python script, generator function"

This instruction appears in ALL 4 system prompt templates:
- `draft_system_create` (YAML line 136 + fallback line 60)
- `draft_system_edit` (YAML line 150 + fallback line 71)
- `draft_system_search_replace` (YAML line 163 + fallback line 82)
- `draft_system_skeleton_fill` (YAML line 176 + fallback line 93)

**Problem:** Go, Java, C#, and Node.js don't have "generator functions." The instruction is Python-specific jargon that wastes tokens for non-Python targets. The correct language-neutral version is: "Output raw source code. Do NOT add wrapper code, boilerplate, or meta-programs."

### "CRITICAL: Every file MUST include ALL import statements"

Same instruction, **verbatim**, in all 4 system prompts × 2 sources = 8 occurrences.

**Problem:** This was a fix for an early Python generation bug (the #1 cause of generation failure). It solved the problem but was never removed from the template — it was duplicated into every new template variant. The instruction itself is fine, but:
1. It should be injected ONCE by `get_drafter_system_prompt()`, not hardcoded in every template
2. The "Python" framing ("imports at the top") doesn't apply to all languages — C# has `using` directives, Go has grouped imports with specific ordering requirements

### "bare except in Python, unused imports in Go"

The review system prompt (YAML line 266) uses Python/Go examples but no C#/Java/Node.js examples. When reviewing C# code, the model has no specific guidance for C#-relevant issues like:
- `Console.WriteLine` instead of `ILogger<T>`
- Block-scoped namespaces instead of file-scoped
- Missing `<Nullable>enable</Nullable>`

---

## 4. Negative Scope Poisoning

### The Mechanism

```
Plan document: "Reference uses Console.WriteLine for health check logging"
                    ↓
Plan ingestion PARSE prompt: "Extract negative_scope: things explicitly excluded"
                    ↓
LLM interprets: negative_scope = ["Do NOT use ILogger<T>", "OpenTelemetry excluded"]
                    ↓
Seed task: negative_scope embedded in task_description as prose
                    ↓
Spec builder: negative_scope passed to LLM as binding constraint
                    ↓
Generated code: Console.WriteLine (follows spec), ILogger absent (follows negative_scope)
                    ↓
Quality grade: B- (should use ILogger)
```

### Evidence from Run-114

**HealthCheckService.cs spec** (line 37):
> `Console.WriteLine("Checking CartService Health")` — simple diagnostic stdout logging, no ILogger dependency. This matches the reference implementation pattern intentionally (**negative scope excludes OpenTelemetry**).

**CartServiceTests.cs spec** (line 328):
> "No negative/error path tests" — **Excluded per negative scope**

**AlloyDBCartStore.cs spec** (line 296):
> "No parameterized queries" — **String interpolation matches the reference implementation. This is intentional. Do not change to @param style.**

### Root Cause

The parse prompt instructs the LLM to extract `negative_scope: list of things explicitly excluded or out-of-scope for this feature, if mentioned in the plan`. The LLM **over-generalizes** from reference patterns to exclusions:

| Reference Pattern | LLM Interpretation | Correct Interpretation |
|-------------------|--------------------|-----------------------|
| Reference uses `Console.WriteLine` | "Exclude ILogger" | "Reference uses Console.Write; best practice is ILogger" |
| Reference has 3 happy-path tests | "Exclude error-path tests" | "Reference covers 3 scenarios; comprehensive tests should include error paths" |
| Reference uses string interpolation for SQL | "Exclude parameterized queries" | "Reference has SQL injection vulnerability; use parameterized queries" |

### Current Sanitizer Coverage

The `plan_ingestion_anchor_sanitizer.py` (added in REQ-QPI-200/201) sanitizes negative_scope for **SQL anti-patterns only**:
- Strips "no parameterized queries" when `detected_database` is set
- Strips "use string interpolation for SQL" patterns

It does NOT sanitize:
- Logging anti-patterns ("exclude ILogger", "use Console.Write")
- DI anti-patterns ("exclude constructor injection")
- Testing anti-patterns ("exclude error-path tests")
- Namespace anti-patterns ("use block-scoped namespace")

---

## 5. Contradictions Within Templates

### C-1: Stub instructions conflict across modes

| Template | Instruction | Meaning |
|----------|------------|---------|
| `draft_system_create` | "no stubs, TODOs, or pass bodies" | Don't generate incomplete code |
| `draft_system_skeleton_fill` | "Implement ONLY methods marked with {stub_marker}" | The file HAS stubs — fill them |

The skeleton-fill template is the exception, but the prohibition in create/edit mode is absolute ("no stubs") — it doesn't say "unless you're in skeleton-fill mode." If the system prompt from create mode leaks into a skeleton-fill call (which can happen through caching), the LLM receives contradictory instructions.

### C-2: Review output format has duplicate blocking issue sections

The review template says:
```
### Issues (prefix: BLOCKING / MAJOR / MINOR)
### Blocking Issues
```

So where do blocking issues go? In the "Issues" section with a prefix, or in the dedicated "Blocking Issues" section? The parser (`reviewer.py` line 598) looks for the "Blocking Issues" section separately, meaning blocking issues listed in the "Issues" section with a `[BLOCKING]` prefix are parsed differently than those in the dedicated section.

### C-3: "Forward verbatim" vs "Add sections"

The `spec_from_design` template says both:
1. "Forward ALL design document content verbatim"
2. "ADD: Technical Approach, Code Structure, Acceptance Criteria, Edge Cases, Examples"

If the design document already covers Technical Approach, the LLM must choose between forwarding verbatim (duplicating) or adding (overwriting). No tiebreaker is specified.

---

## 6. Missing Templates (Hardcoded Fragments)

These prompt fragments are constructed in Python f-strings, bypassing the YAML template system entirely:

| Fragment | File | Lines | Should Be Template |
|----------|------|:---:|-------------------|
| Multi-file manifest header | spec_builder.py | 102-108 | `required_output_files` |
| Verified reference section | spec_builder.py | 268-290 | `exemplar_reference` |
| Sibling imports section | spec_builder.py | 456-465 | `sibling_imports` |
| Local modules section | spec_builder.py | 513-525 | `local_modules` |
| Output format fallbacks | drafter.py | 93-104 | Already in YAML — duplicated |
| Framing fallbacks | spec_builder.py | 136-147 | Already in YAML — divergent |
| Language review rules | reviewer.py | 579-584 | `language_review_rules` |

**Impact:** These fragments cannot be audited, version-controlled, or updated alongside the YAML templates. Changes to the YAML have no effect on these fragments, and vice versa.

---

## 7. Prompt Inflation: Sections That Waste Token Budget

### Budget-Dropped Sections

The `enforce_prompt_budget()` function (budget.py) uses P0-P3 priority ordering. P0 is never dropped. But the prompt is often at budget by the time lower-priority sections are evaluated:

| Priority | Section | Typical Size | Impact When Dropped |
|:---:|---------|:---:|---------------------|
| P0 | Security guidance | ~200 tokens | HIGH — SQL injection prevention |
| P0 | Coding standards (REQ-KZ-005) | ~50 tokens | LOW — too thin to be useful |
| P1 | Requirements context | ~300 tokens | HIGH — acceptance criteria |
| P1 | Quality trend warning | ~100 tokens | MEDIUM |
| P2 | Anti-pattern guidance | ~150 tokens | MEDIUM |
| P2 | Run quality hints | ~200 tokens | MEDIUM |
| P3 | Sibling imports | ~400 tokens | LOW — can hallucinate from task description |

**Problem:** `coding_standards` is P0 priority but only ~50 tokens. It survives budget enforcement but is too thin to override reference-matching constraints in the task description (~2000-4000 tokens). The task_description itself is never budget-trimmed (it's the core of the prompt), so negative_scope entries embedded in it always survive while quality guidance may be dropped.

### Token Waste from Redundancy

| Redundancy | Occurrences | Tokens Wasted Per Prompt |
|------------|:---:|:---:|
| "CRITICAL imports" instruction | 1 per prompt (correct) but stored 8× in source | 0 runtime, maintenance burden |
| "Python script, generator function" | 1 per prompt | ~15 (for non-Python targets) |
| 8-section output format repeated | 2 templates | 0 (only one is used per call) |
| "Do not assume imports exist elsewhere" | redundant with "include ALL import statements" | ~10 |

---

## 8. Remediation Plan

### Phase R0 — Eliminate Fragmentation (~1 hour)

**Goal:** Single source of truth for all prompt text.

**R0-1: Sync fallbacks to YAML** — Update all 13 `_FALLBACK_TEMPLATES` entries to match YAML verbatim. Add the 5 missing templates to fallbacks.

**R0-2: Move hardcoded fragments to YAML** — Create 4 new YAML templates (`required_output_files`, `exemplar_reference`, `sibling_imports`, `local_modules`) and replace the f-string construction in spec_builder.py with `format_prompt()` calls.

**R0-3: Remove duplicate fallbacks** — Delete the 4 `_*_FALLBACK` strings in spec_builder.py (lines 136-147) and the 4 output format fallbacks in drafter.py (lines 93-104). These should use `get_template()` which already has fallback logic.

**R0-4: Add sync test** — A unit test that loads YAML templates and fallback strings, asserts they have the same placeholders and produce structurally equivalent output.

### Phase R1 — De-Pythonize Templates (~30 min)

**Goal:** Language-neutral instructions that work for all 5 languages.

**R1-1: Replace Python-specific jargon:**
```yaml
# Before:
"Do NOT wrap content in a Python script, generator function, or any other meta-program."
# After:
"Output raw source code only. Do NOT add wrapper code, boilerplate, or meta-programs."
```

**R1-2: Replace Python-specific review examples:**
```yaml
# Before:
"e.g. wildcard imports in Java, bare except in Python, unused imports in Go"
# After:
"e.g. wildcard imports (Java), bare except (Python), unused imports (Go), Console.Write instead of ILogger (C#), var instead of const (Node.js)"
```

**R1-3: Parameterize the import instruction:**
```yaml
# Before:
"CRITICAL: Every file you produce MUST include ALL import statements at the top."
# After (injected by get_drafter_system_prompt, not in template):
# Python: "Include all import statements at the top of the file."
# C#: "Include all using directives at the top of the file."
# Go: "Include all import declarations in a grouped import block."
# Java: "Include all import statements after the package declaration."
# Node.js: "Include all require() or import statements at the top of the file."
```

### Phase R2 — Fix Negative Scope Poisoning (~1.5 hours)

**Goal:** Prevent reference implementation anti-patterns from becoming binding constraints.

**R2-1: Expand anchor sanitizer** — Add language-aware sanitization to `plan_ingestion_anchor_sanitizer.py`:

```python
_LOGGING_ANTI_PATTERNS = [
    r"(?i)do not use.*ILogger",
    r"(?i)exclude.*ILogger",
    r"(?i)Console\.Write.*intentional",
    r"(?i)no structured logging",
    r"(?i)do not use.*slog",      # Go
    r"(?i)do not use.*winston",   # Node.js
    r"(?i)do not use.*SLF4J",     # Java
]

_DI_ANTI_PATTERNS = [
    r"(?i)do not use.*constructor injection",
    r"(?i)property injection.*intentional",
]

_TESTING_ANTI_PATTERNS = [
    r"(?i)no negative.*test",
    r"(?i)no error.path.*test",
    r"(?i)exclude.*error.*test",
]
```

**R2-2: Change negative_scope parse instruction** — In the plan ingestion PARSE prompt (line 567 of plan_ingestion_workflow.py), change:

```
# Before:
negative_scope: list of things explicitly excluded or out-of-scope for this feature, if mentioned in the plan.

# After:
negative_scope: list of things the PLAN EXPLICITLY states are out-of-scope (e.g., "Kubernetes manifests are not included"). Do NOT infer exclusions from reference implementation patterns — if the reference uses Console.WriteLine, that does NOT mean ILogger is excluded. Only include items the plan text literally says are out of scope.
```

**R2-3: Add quality floor to negative_scope consumption** — In spec_builder.py, when negative_scope entries are embedded in the task_description, append a caveat:

```
Note: negative_scope items above reflect the reference implementation's patterns.
When a negative_scope item conflicts with language coding standards (e.g., "Do not
use ILogger" when C# coding standards require ILogger<T>), prefer the coding
standard. The goal is to generate BETTER code than the reference, not replicate
its limitations.
```

### Phase R3 — Resolve Contradictions (~30 min)

**R3-1: Unify review output format:**
```yaml
# Remove the separate "### Blocking Issues" section.
# Use inline severity prefixes only:
## Output Format
### Score: [0-100]
### Verdict: [PASS/FAIL] (PASS if score >= {pass_threshold} AND no BLOCKING issues)
### Strengths
### Issues
List each issue as: - [BLOCKING|MAJOR|MINOR] description
### Suggestions
```

**R3-2: Make stub prohibition conditional:**
```yaml
# In draft_system_create/edit/search_replace:
"Complete implementations only — no stubs, TODOs, or placeholder bodies."
# In draft_system_skeleton_fill:
"Implement ONLY stub-marked methods. Preserve all pre-filled code exactly."
# (Already distinct — just ensure no leakage between modes)
```

**R3-3: Clarify verbatim forwarding:**
```yaml
# In spec_from_design:
"Forward ALL design document content into the appropriate sections.
If the design document already covers a section (e.g., Technical Approach),
use the design document's version. ADD sections only for gaps."
```

### Phase R4 — Enrich Coding Standards (~1 hour)

**Goal:** Make `coding_standards` substantive enough to override reference-matching constraints.

**R4-1: Enrich CSharpLanguageProfile.coding_standards** — Currently 1 line (~50 chars). Expand to cover the exact issues that caused B- grades:

```python
@property
def coding_standards(self) -> str:
    return (
        "C# Coding Standards (MANDATORY — override reference patterns if they conflict):\n"
        "- Use ILogger<T> injected via constructor for ALL logging. "
        "Do NOT use Console.WriteLine in production services.\n"
        "- Use file-scoped namespaces (namespace Foo;) not block-scoped (namespace Foo { }).\n"
        "- Use constructor injection for all dependencies. "
        "Do NOT use property injection or service locator.\n"
        "- Enable nullable reference types: all parameters and returns must be annotated.\n"
        "- Use parameterized queries for ALL database access. "
        "NEVER use string interpolation in SQL.\n"
        "- Catch specific exception types (IOException, InvalidOperationException). "
        "Do NOT use bare catch or catch(Exception).\n"
        "- Test classes should include both happy-path AND error-path test cases.\n"
    )
```

**R4-2: Enrich all language profiles similarly** — Apply the same treatment to Python, Go, Java, Node.js. Each profile's `coding_standards` should be ~200-300 tokens of specific, actionable guidance that addresses the top 5 quality issues seen in that language's generated code.

**R4-3: Verify P0 section survives budget enforcement** — Add a debug assertion in `enforce_prompt_budget()` that P0 sections are never dropped. If they are dropped (shouldn't be possible), log a WARNING.

### Execution Order

```
R0 (fragmentation)  ─── independent, do first for clean baseline
R1 (de-Pythonize)   ─── depends on R0 (edits same files)
R2 (neg scope)      ─── independent of R0/R1
R3 (contradictions) ─── depends on R0
R4 (coding standards) ─── independent, highest quality impact
```

**Recommended:** R0 → R4 → R2 → R1 → R3 (ordered by quality impact, not dependency)

---

## 9. Impact Projection

| Fix | Languages | Quality Impact | Effort |
|-----|:---------:|:-:|:---:|
| R4 (enriched coding_standards) | All 5 | HIGH — prevents Console.Write, bare catch, property injection | 1 hour |
| R2 (negative scope sanitization) | All 5 | HIGH — prevents reference anti-patterns from becoming binding | 1.5 hours |
| R0 (fragmentation cleanup) | All 5 | MEDIUM — eliminates maintenance burden and divergence risk | 1 hour |
| R1 (de-Pythonize) | Go, Java, C#, Node.js | MEDIUM — removes confusion for non-Python targets | 30 min |
| R3 (contradictions) | All 5 | LOW — edge cases in review parsing | 30 min |

**Total effort: ~4.5 hours**

**Projected grade improvement for C# HealthCheckService pattern:**
- Before: Console.Write + property injection + brace namespace → B-
- After R2+R4: ILogger<T> + constructor injection + file-scoped namespace → A-
