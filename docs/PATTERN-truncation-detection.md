# Pattern: Truncation Detection for Code Generation

## Context

The startd8 SDK detects LLM output truncation using two layers:
1. **API-level**: `token_usage.was_truncated` from the provider
2. **Heuristic**: `detect_truncation()` in `truncation_detection.py`

The heuristic works well for natural language and markdown responses. But when applied
to **extracted code**, it produces false positives because code contains patterns that
resemble truncation in prose.

### Observed false positive (gabba-stockpile Phase 5, Run 7)

```
✗ REJECTED seed-fillmore-catalog.ts: appears truncated (confidence=80%)
    Mid-sentence ending: ends with comma/colon/semicolon
    Unclosed string at end
    Unclosed inline code at end
```

The file was 429 lines, structurally complete (balanced braces, proper `main().catch()`
closure), and output was 18,734 tokens — well under the 16,384 default limit. The
heuristic was wrong.

**Why it triggered**: TypeScript code legitimately ends with `});` (semicolons), contains
template literals (`${var}`) that look like unclosed inline code, and has trailing commas
in function arguments that look like mid-sentence endings.

---

## Anti-Patterns (what to avoid)

### 1. Treating code as prose
The heuristic was designed for natural language. Indicators like "mid-sentence ending"
and "unclosed string" have different semantics in code:
- Prose ending in `;` = suspicious. Code ending in `});` = normal.
- Prose with unmatched `` ` `` = suspicious. Code with template literals = normal.
- Prose ending in `,` = suspicious. Code with trailing commas = style choice.

### 2. Same threshold for generation vs integration
The SDK runs truncation detection twice:
- **Generation time** (in `lead_contractor_workflow.py`): on the raw LLM response
- **Integration time** (in `prime_contractor.py:564`): on the extracted code file

These have different base rates. The raw response is more likely to be truncated (LLM
hit output limit). The extracted code has already been parsed successfully — a false
positive here blocks a valid file from being integrated.

### 3. No correlation with token usage
Truncation means the LLM hit its output limit. If the output used 3,127 of 16,384
available tokens, truncation is extremely unlikely. The heuristic ignores this signal.

### 4. Binary reject with no override
When the heuristic fires at integration time, the file is hard-rejected:
```python
if trunc_result.is_truncated and trunc_result.confidence >= 0.7:
    print(f"  ✗ REJECTED {source_path.name}: appears truncated")
    continue  # File is skipped entirely
```
There's no "warn and proceed" mode at the integration gate, even though the generation
gate already validated the response.

### 5. No structural validation for code
The heuristic counts backticks and checks for "mid-sentence endings" — surface patterns.
It doesn't check whether the code is structurally complete (balanced delimiters, valid
syntax, complete top-level statements).

---

## Patterns (what to do)

### 1. Trust API-level signal first, heuristic second

The provider's `was_truncated` flag is ground truth. The heuristic is a safety net for
providers that don't report it. Decision tree:

```
API says truncated?
  → YES: Truncated (confidence=100%, fail)
  → NO or unknown:
      Heuristic says truncated?
        → YES with high confidence (>90%): Warn, consider failing
        → YES with medium confidence (70-90%): Warn only, proceed
        → NO: Proceed
```

### 2. Use language-aware structural checks for code

For extracted code files (not raw LLM responses), replace or supplement prose heuristics
with structural checks:

| Check | How | Weight |
|-------|-----|--------|
| Balanced braces `{}` | Count open vs close | High |
| Balanced brackets `[]` `()` | Count open vs close | High |
| File ends with complete statement | Last non-empty line ends with `}`, `};`, `);`, or `)` | High |
| Has expected exports/functions | Grep for `export`, `function`, `class`, `const` | Medium |
| No dangling `else`/`catch`/`finally` | Last keyword isn't a continuation | Medium |

These are more accurate than prose heuristics for code and don't false-positive on
template literals, trailing commas, or semicolons.

### 3. Correlate with token utilization ratio

```python
utilization = output_tokens / max_tokens  # e.g., 3127 / 16384 = 0.19

if utilization < 0.5:
    # Output used less than half the budget — truncation very unlikely
    # Raise the confidence threshold for heuristic detection
    confidence_threshold = 0.95
elif utilization > 0.9:
    # Output nearly hit the limit — truncation is plausible
    # Use normal threshold
    confidence_threshold = 0.7
```

This simple ratio eliminates most false positives. A 429-line file using 19% of its
token budget is almost certainly complete.

### 4. Differentiate generation-time vs integration-time checks

| Stage | Purpose | Action on detection |
|-------|---------|-------------------|
| **Generation** | Catch real truncation from LLM | Fail or retry (drafter can regenerate) |
| **Integration** | Safety net before writing to disk | **Warn only** (file already passed generation check) |

The integration-time check should be softer because:
- The generation stage already validated the response
- The extracted code may have different surface patterns than the raw response
- A false positive at this stage wastes a successful generation ($0.21 in this case)

### 5. Add a bypass for double-checked files

When generation-time truncation detection passes AND the API didn't flag truncation,
mark the generated file as "truncation-cleared". The integration-time check can then
skip or reduce its threshold for these files:

```python
# In lead_contractor.py, after successful truncation check:
result.metadata["truncation_cleared"] = True

# In prime_contractor.py, at integration-time check:
if feature.metadata.get("truncation_cleared"):
    # Already validated — use higher threshold or skip
    confidence_threshold = 0.95
```

### 6. Log which indicators fired and their individual scores

The current output shows the composite confidence but not the breakdown:
```
appears truncated (confidence=80%)
    Mid-sentence ending: ends with comma/colon/semicolon
    Unclosed string at end
```

Add individual indicator scores so developers can tune:
```
appears truncated (confidence=80%)
    Mid-sentence ending (0.3): last line ends with ';'
    Unclosed string (0.2): unmatched backtick in template literal
    Unclosed inline code (0.3): ${...} pattern detected
    → Composite: 0.80 (threshold: 0.70)
```

This makes false positives diagnosable without reading the SDK source.

---

## Recommended implementation priority

1. **Quick win**: At integration time, only warn (don't reject) when generation-time
   check already passed. This unblocks the immediate Phase 5 issue.

2. **Medium term**: Add token utilization ratio to confidence calculation. Halves
   false positive rate with 5 lines of code.

3. **Longer term**: Add language-aware structural checks (balanced delimiters) for
   code files. Replace prose heuristics when file extension is `.ts`, `.tsx`, `.py`, etc.

---

## Test cases for validation

| Scenario | Expected | Heuristic should... |
|----------|----------|-------------------|
| 429-line TS file ending with `});`, 19% token utilization | Not truncated | Pass (structural complete, low utilization) |
| 50-line file ending mid-function `if (x) {`, 95% token utilization | Truncated | Fail (unclosed brace, high utilization) |
| Raw LLM response with unclosed code block | Truncated | Fail (missing closing ```) |
| TS file with template literals `${foo}` | Not truncated | Pass (template literals are valid code) |
| File with trailing comma in last arg | Not truncated | Pass (trailing commas are valid TS) |
