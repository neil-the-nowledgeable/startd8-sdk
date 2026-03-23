# Language Kaizen Requirements — Template

> **Purpose:** Template for creating `KAIZEN_{LANG}_REQUIREMENTS.md` for a new language. Copy this file, replace `{LANG}` placeholders, and fill in language-specific content.
> **Parent:** [KAIZEN_PRIME_REQUIREMENTS.md](KAIZEN_PRIME_REQUIREMENTS.md)
> **Evaluation prompt:** [PIPELINE_EVALUATION_PROMPT_REQUIREMENTS.md](PIPELINE_EVALUATION_PROMPT_REQUIREMENTS.md)
> **MicroPrime:** [MICROPRIME_POLYGLOT_REQUIREMENTS.md](MICROPRIME_POLYGLOT_REQUIREMENTS.md)

---

## Standard 9-Section Structure

Every language Kaizen requirements doc follows this structure. Sections marked **INHERIT** use the parent doc's content with minimal language customization. Sections marked **FILL** require language-specific content.

### Section 1: Overview — FILL

| Subsection | Content |
|-----------|---------|
| Current Capabilities | Table of implemented infrastructure (parser, splicer, validator, repair steps) |
| Key Advantages | What makes this language easier/better to generate |
| Key Challenges | What makes this language harder (boilerplate, tooling gaps, contamination risk) |
| Generation Strategy | MicroPrime element-level OR file-whole, merge strategy, template availability |

### Section 2: Disk Validation (REQ-KZ-{LANG}-100) — FILL

| Check | All Languages | Language-Specific |
|-------|--------------|-------------------|
| Syntax validity | Concept inherited | Tool: `{syntax_check_command}` from language profile |
| Package/namespace declaration | Concept inherited | Convention: package matches directory (Go, Java), namespace matches path (C#), none (Python, Node.js) |
| Cross-language contamination | **INHERIT** — all languages check `GO_CONTAMINATION_FINGERPRINTS` / `PYTHON_FINGERPRINTS` | Language profile determines which fingerprint set to use |
| Import well-formedness | Concept inherited | Syntax: bare `import` (Go), `using` (C#), `import` (Java/Node.js/Python) |
| Function body completeness | Concept inherited | Stub patterns from language profile: `stub_patterns` property |

### Section 3: Semantic Checks (REQ-KZ-{LANG}-200) — FILL

**Common checks (all languages):**

| Check | Category String | Severity | Notes |
|-------|----------------|----------|-------|
| Cross-language contamination | `python_contamination` | error | INHERIT — uses shared fingerprint patterns |
| Unreachable functions | `unreachable_function` | warning | INHERIT — framework-decorator-aware (P0 fix) |
| Orphan dependencies | `orphan_dependency` | warning | INHERIT — build-time package allowlist applied |
| Discarded return values | `discarded_return` | warning | INHERIT — pure function allowlist |

**Language-specific checks:** Define 4-8 additional checks unique to this language (e.g., `unchecked_error` for Go, `async_void_usage` for C#, `wildcard_import` for Java, `cjs_esm_mixing` for Node.js).

### Section 4: Quality Scoring (REQ-KZ-{LANG}-300) — FILL

**Common formula structure:**
```
{lang}_quality_score = (
    compilation_check × W1
  + import_validity   × W2
  + stub_penalty      × W3
  + {lang_dimension}  × W4
  + contamination     × W5
)
```

**Weight guidance:**
- Compilation/syntax: 0.25-0.35 (higher for strongly-typed languages)
- Import validity: 0.15-0.25
- Stub penalty: 0.15-0.25
- Language-specific dimension: 0.10-0.20
- Contamination: 0.10-0.15 (binary: 0.0 or 1.0)

**Contamination override:** If contamination == 0.0, cap aggregate at 0.0 regardless of other dimensions.

### Section 5: Repair Pipeline (REQ-KZ-{LANG}-400) — FILL

**Common repair steps (all languages):**

| Step | What It Fixes | Language-Agnostic? |
|------|--------------|-------------------|
| `fence_strip` | Markdown code fences in LLM output | Yes |
| `bracket_balance` | Unbalanced braces | Yes |
| `todo_uncomment` | Commented-out code blocks | Yes |
| `{lang}_syntax_validate` | Final syntax gate | No — language-specific tool |

**Language-specific steps:** Define 2-5 additional repair steps using the language's external tools (e.g., `goimports -w` for Go, `dotnet format` for C#, `google-java-format` for Java, `prettier` for Node.js).

### Section 6: Feedback Loop Hints (REQ-KZ-{LANG}-500) — FILL

Map each language-specific root cause to a Kaizen hint that injects corrective guidance into the next run's LLM prompt. Structure:

| Root Cause | Target Phase | Hint Text | Confidence |
|-----------|-------------|-----------|------------|
| `{category}` | `spec` or `draft` | "Prior run had X. Do Y instead." | 0.70-0.99 |

**All root causes MUST have entries in both `_SEMANTIC_CATEGORY_TO_SUGGESTION` and `CAUSE_TO_SUGGESTION` in `prime_postmortem.py`.**

### Section 7: Generation Profile (REQ-KZ-{LANG}-600) — FILL

| Property | Value | Source |
|---------|-------|--------|
| MicroPrime routing | TRIVIAL/SIMPLE/MODERATE/COMPLEX | `complexity/classifier.py` |
| Merge strategy | `"ast"` or `"simple"` | Language profile |
| Skeleton assembly | Deterministic assembler or LLM | Per language |
| Post-gen cleanup | Tool and fallback | Language profile |
| Docker images | Builder + runtime | Language profile |
| System prompt role | e.g., "an expert Go engineer" | Language profile |
| Coding standards | Injected into every prompt | Language profile |

### Section 8: Traceability Matrix — FILL

Map language challenges to requirement IDs:

| Challenge | Requirements | Parent Kaizen Gap |
|-----------|-------------|-------------------|
| {description} | REQ-KZ-{LANG}-{NNN} | K-{N} |

### Section 9: Verification Strategy — FILL

| Test | Validates | Test File |
|------|-----------|-----------|
| `test_{lang}_disk_compliance_valid` | REQ-KZ-{LANG}-100 | `tests/unit/...` |
| `test_{lang}_semantic_checks` | REQ-KZ-{LANG}-200 | `tests/unit/validators/...` |

---

## Requirement ID Numbering Convention

```
REQ-KZ-{LANG}-{NNN}

{LANG} codes:
  PY  = Python
  GO  = Go
  CS  = C#
  JV  = Java
  ND  = Node.js

{NNN} ranges:
  100-199 = Disk Validation
  200-299 = Semantic Checks
  300-399 = Quality Scoring
  400-499 = Repair Pipeline
  500-599 = Feedback Loop Hints
  600-699 = Generation Profile
```
