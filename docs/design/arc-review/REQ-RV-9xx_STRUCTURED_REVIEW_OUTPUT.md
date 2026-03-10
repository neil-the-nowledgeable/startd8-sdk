# Structured Review Output — Requirements (RV-9xx)

**Version:** 1.0.0
**Created:** 2026-03-10
**Parent:** [ARCHITECTURAL_REVIEW_REQUIREMENTS.md](ARCHITECTURAL_REVIEW_REQUIREMENTS.md) (Layer 9)
**Triggered by:** Kaizen run-019 REFINE failure — Opus produced unrecognized table headers twice, skipping the only reviewer

---

## Problem Statement

The Convergent Review Protocol (CRP) currently requires LLMs to serialize structured suggestion data as markdown tables with exact column headers. A validator then parses those tables back into structured dicts. This round-trip through unstructured text fails when the LLM uses different column names, reorders columns, or produces a non-table format — even when the underlying data (id, area, severity, suggestion, rationale) is present and correct.

**Run-019 evidence:** `claude-opus-4-6` produced a review table that, after alias mapping, was still missing 3 of 5 core columns (`Area`, `Severity`, `Rationale`). Both the initial attempt and the retry failed with the same error. The reviewer was skipped entirely, producing zero REFINE suggestions.

**Root cause:** The communication contract between the reviewer LLM and the validation layer is defined implicitly through prompt instructions ("use these exact column headers") rather than explicitly through a schema. The triage step already uses JSON — only the review step uses markdown tables.

### Current Flow (fragile)

```
Reviewer LLM → markdown table text → regex parse columns → alias map
→ validate column presence → extract cell values → structured dict
```

### Proposed Flow (robust)

```
Reviewer LLM → JSON array → schema validate → structured dict
→ render markdown table for document (display only)
```

---

## Design Principles

1. **Align with ContextCore A2A contracts** — Use `GateResult`-compatible severity enums and evidence patterns from `contextcore.contracts.a2a.models` where applicable. Do not create a hard dependency on ContextCore.
2. **JSON-first, table-as-rendering** — The LLM produces structured JSON; markdown tables are rendered from validated data for human readability in the document.
3. **Backward compatible** — Accept both JSON and markdown table output during the transition period. Existing review documents with markdown tables continue to work.
4. **Fail-open on format, fail-closed on content** — Accept any reasonable serialization format but enforce that required fields are present with valid values.

---

## Layer 9: Structured Review Output (RV-9xx)

### RV-900: JSON Review Output Schema

**Status:** Planned
**Priority:** High

The reviewer LLM MUST be prompted to return a JSON object (wrapped in ```json fences) instead of a markdown table. The schema:

```json
{
  "round": 1,
  "reviewer": "claude-4 (claude-opus-4-6)",
  "date": "2026-03-10",
  "scope": "architecture clarity, execution safety, ...",
  "suggestions": [
    {
      "id": "R1-S1",
      "area": "architecture",
      "severity": "high",
      "suggestion": "Add circuit breaker around payment gateway calls",
      "rationale": "Payment API has 2% timeout rate; cascading failures possible",
      "proposed_placement": "Section 3.2 — Payment Integration",
      "validation_approach": "Inject 5s delay; verify circuit opens after 3 failures"
    }
  ],
  "endorsements": [
    {
      "id": "R1-S3",
      "reason": "Aligns with our reliability requirements"
    }
  ]
}
```

**Required fields per suggestion:** `id`, `area`, `severity`, `suggestion`, `rationale`
**Optional fields per suggestion:** `proposed_placement`, `validation_approach`
**Endorsements:** Optional array, only present when prior-round suggestions exist.

**Acceptance criteria:**
- Prompt instructs LLM to produce JSON inside ```json fences
- JSON schema is documented in the prompt (as an example, not as formal JSON Schema)
- `area` values validated against the active `allowed_areas` set (warn, don't reject)
- `severity` values validated against `ALLOWED_SEVERITIES` (warn, don't reject)
- `id` values auto-corrected to `R{round}-S{n}` format if mis-numbered

### RV-901: Dual-Format Validator

**Status:** Planned
**Priority:** High

The snippet validator MUST accept both JSON and markdown table formats. Detection order:

1. **Try JSON parse** — If the response (after stripping code fences) parses as a JSON object with a `suggestions` array, validate against the RV-900 schema.
2. **Fall back to markdown table parse** — If JSON parse fails, use the existing `_validate_snippet()` table parser (with the expanded alias map and positional fallback from the current session's changes).

**Acceptance criteria:**
- A new function `_validate_review_output()` wraps both paths
- JSON path returns `(True, "ok", ids)` when valid, with the same signature as `_validate_snippet()`
- JSON path extracts the same data shape used downstream: `List[Dict]` with keys matching `_extract_untriaged_suggestions()` output
- Markdown fallback preserves all existing leniency (alias map, positional fallback)
- OTel span event records which format was used (`review.output_format: "json" | "markdown_table"`)

### RV-902: JSON-to-Markdown Renderer

**Status:** Planned
**Priority:** High

Validated JSON suggestions MUST be rendered as a markdown review-round block for appending to Appendix C. This preserves backward compatibility with existing document consumers (triage, apply, human readers).

The renderer produces:

```markdown
#### Review Round R{n}

- **Reviewer**: {reviewer_label}
- **Date**: {date}
- **Scope**: {scope}

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | High | Add circuit breaker... | Payment API has 2%... | Section 3.2 | Inject 5s delay... |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R0-S2: Aligns with our reliability requirements
```

**Acceptance criteria:**
- Rendered markdown passes `_validate_snippet()` (round-trip safe)
- Optional columns default to `N/A` when absent from JSON
- Endorsements section only rendered when endorsements array is non-empty
- Pipe characters in cell values are escaped (`|` → `\|`)

### RV-903: Updated Review Prompt

**Status:** Planned
**Priority:** High

The review prompt template (`architectural_review.yaml` → `review`) MUST be updated to request JSON output. The prompt should:

1. Show the complete JSON schema with a worked example
2. Explicitly state "Return ONLY a JSON object wrapped in ```json fences"
3. Include the round metadata fields (round, reviewer, date, scope) in the schema so the LLM doesn't need to format the heading separately
4. Preserve all existing context injection (iteration context, tier steering, gap hunting, endorsements)

**Acceptance criteria:**
- YAML template updated with JSON output instructions
- Prompt includes a concrete example with 2 suggestions and 1 endorsement
- Prompt explicitly lists allowed `area` and `severity` values
- Backward-compatible: if an LLM ignores JSON instructions and produces a table, the dual-format validator (RV-901) still accepts it

### RV-904: Structured Extraction from JSON

**Status:** Planned
**Priority:** Medium

`_extract_untriaged_suggestions()` MUST be updated to also extract suggestions from a structured JSON store in addition to parsing Appendix C tables. During the transition period, both sources are checked.

**Approach:** When RV-902 renders JSON suggestions as a markdown table in Appendix C, the existing table parser already handles extraction. No immediate code change is needed — this requirement is satisfied by the render step (RV-902) producing tables that `_extract_untriaged_suggestions()` can already parse.

**Future optimization (post-transition):** Store the validated JSON alongside the rendered markdown in a sidecar data structure (e.g., a JSON block after the markdown table in Appendix C, or a separate `.review-state.json` file). This would eliminate re-parsing entirely.

**Acceptance criteria:**
- During transition: `_extract_untriaged_suggestions()` continues to work unchanged (RV-902 guarantees parseable tables)
- Extraction produces the same data shape regardless of whether the source was LLM JSON or rendered markdown

### RV-905: Retry Prompt Uses JSON Schema

**Status:** Planned
**Priority:** Medium

When validation fails (both JSON parse and markdown fallback), the retry prompt MUST include the full JSON schema with a concrete example. The current retry prompt references column headers — it should reference the JSON schema instead.

**Acceptance criteria:**
- Retry prompt shows the exact JSON structure expected
- Retry prompt includes the validation error message for context
- Retry prompt explicitly says "Do NOT produce a markdown table — return JSON only"

### RV-906: ContextCore A2A Alignment

**Status:** Planned
**Priority:** Low (Phase 3)

The review suggestion schema SHOULD align with ContextCore `GateResult` patterns for cross-system compatibility:

| CRP Field | ContextCore Equivalent | Notes |
|-----------|----------------------|-------|
| `severity` | `GateSeverity` enum | Values already match: critical, high, medium, low |
| `area` | `phase` (loosely) | CRP areas are domain-specific; not a direct map |
| `rationale` | `reason` | Same purpose |
| `proposed_placement` | `next_action` | Similar: "where to apply the fix" |
| `validation_approach` | `evidence[].description` | Similar: "how to verify" |

This is a documentation/type-alias requirement, not a runtime dependency. ContextCore remains an optional dependency.

**Acceptance criteria:**
- Enum values for severity use the same strings as `GateSeverity`
- Documentation maps CRP fields to ContextCore A2A equivalents
- No runtime import of `contextcore.contracts` is required

---

## Implementation Order

| Phase | Requirements | Risk | Effort |
|-------|-------------|------|--------|
| 1 | RV-901 (dual validator), RV-902 (renderer), RV-903 (prompt) | Low — additive, backward compatible | Medium |
| 2 | RV-900 (schema formalization), RV-905 (retry prompt) | Low — builds on Phase 1 | Small |
| 3 | RV-904 (structured extraction), RV-906 (A2A alignment) | Low — optimization | Small |

**Phase 1 is the minimum viable change** that fixes the run-019 class of failures. It can be deployed independently.

---

## Test Plan

1. **JSON happy path** — Reviewer returns valid JSON → validates → renders markdown → passes `_validate_snippet()` round-trip
2. **Markdown fallback** — Reviewer returns markdown table (no JSON) → falls back to existing validator → succeeds
3. **Malformed JSON** — Reviewer returns broken JSON → falls back to markdown parse → if that also fails, returns error
4. **Missing optional fields** — JSON with only required fields → validates → renders with N/A defaults
5. **Invalid area/severity** — JSON with non-standard values → warns but accepts (matches existing leniency)
6. **ID auto-correction** — JSON with wrong round prefix → IDs corrected to R{n}-S{m}
7. **Pipe escaping** — Suggestion text containing `|` → rendered markdown doesn't break table
8. **Endorsements** — JSON with endorsements → rendered in markdown endorsement section
9. **Empty suggestions** — JSON with empty suggestions array → valid (reviewer found nothing)
10. **Plan ingestion REFINE** — End-to-end: plan ingestion calls arc-review → JSON output → triage → suggestions extracted for seed
