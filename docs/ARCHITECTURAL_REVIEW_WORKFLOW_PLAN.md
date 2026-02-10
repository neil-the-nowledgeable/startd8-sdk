# Plan: Architectural Review Workflow (High-Quality Sequential Models)

**Status**: Proposed  
**Created**: 2026-02-05  
**Primary validation document**: `/Users/neilyashinsky/Documents/dev/contextcore-demo-retail/personas/IMPLEMENTATION_PLAN.md`

## Goal

Add a StartD8 SDK workflow for **strategic architectural review** that:

- Uses **1+ high-quality (flagship) models** by default
- Runs reviewers **sequentially** (model-after-model)
- Appends **append-only** suggestions into the same target document (no rewriting)
- Prevents wasted cycles by carrying forward **Applied / Rejected (with rationale)** decisions so later models don’t re-suggest rejected items

## Non-Goals

- Automatically applying suggestions to the document body (this remains human/author-driven)
- Fully automating accept/reject decisions (we may *assist* triage, but keep final disposition explicit)
- Replacing `CriticalReviewWorkflow` or `DocEnhancementWorkflow` (this complements them)

---

## Current State (What we already have)

### Existing workflows

- **`critical-review`** (`startd8/workflows/builtin/critical_review_workflow.py`)
  - Produces independent review markdown files
  - Does **not** append into the original document or maintain “applied/rejected memory”

- **`doc-enhancement`** (`startd8/workflows/builtin/doc_enhancement_workflow.py`)
  - Sequential refinement by rewriting the document
  - Not suited for append-only architectural review logs

### New baseline implemented (foundation to build on)

- **`doc-review-log`** (`startd8/workflows/builtin/doc_review_log_workflow.py`)
  - Sequential agents
  - Appends “Review Round R{n}” blocks under an **Applied/Rejected/Incoming** appendix
  - Reads Appendices **A (Applied)** and **B (Rejected)** IDs to avoid re-suggesting
  - Writes a state file: `.startd8/doc_review_state.json`

This baseline already matches the required “one after another + append-only + memory” mechanics.

---

## Proposed Variation: `architectural-review-log` Workflow

### Why a distinct workflow vs. “just pass premium models into doc-review-log”

You *can* already run premium models by passing `agents=["anthropic:claude-opus-…", ...]`.  
The missing “architectural” productization is:

- **Premium defaults** (no need to hand-pick every run)
- **Architecture-specific prompt contract** (forces actionable, structured suggestions)
- **Stronger validation** of the appended snippet schema
- **Optional cost guardrails** (warn/stop thresholds)
- (Optional) **duplication prevention beyond IDs** (hash-based memory to avoid “same suggestion, new ID”)

### Workflow ID / contract

- **Workflow ID**: `architectural-review-log`
- **Execution**: sequential reviewer rounds (one per agent)
- **Output**: appends under the document’s Appendix C only (append-only)

### Inputs (proposed)

- `document_path` *(required)*: path to `.md`
- `agents` *(optional)*: if provided, use exactly these (sequential)
- `quality_tier` *(optional, default=`flagship`)*: selects default models if `agents` not provided
  - values: `flagship | balanced | fast | mini`
- `providers` *(optional)*: restrict default selection (e.g., `["anthropic", "gemini"]`)
- `reviewer_count` *(optional, default=2)*: number of default reviewers if `agents` not provided
- `max_suggestions` *(optional, default=10)*: per round
- `max_cost_usd` *(optional)*: fail-fast if exceeded across the run
- `warn_cost_usd` *(optional)*: emit warnings when exceeded
- `init_if_missing` *(default true)*: bootstrap the appendix structure if missing
- `state_path` *(optional)*: defaults to `.startd8/architectural_review_state.json`
- `review_template` *(optional)*: override prompt template for enterprise customization

### Default agent selection (high-quality)

Leverage `startd8/model_catalog.py` (already supports tiers):

- Default for `flagship`:
  - `Models.CLAUDE_OPUS_LATEST`
  - `Models.GEMINI_PRO_LATEST`
  - (optional third) `Models.GPT4_LATEST`

Selection algorithm:

1. Filter models by `tier == quality_tier`
2. Filter by provider allowlist (if provided)
3. Pick first `reviewer_count` models
4. If fewer available than requested, fall back to `balanced` tier and warn

---

## Prompt / Output Schema (architecture-specific)

### Required appended snippet format

Each reviewer must output ONLY a markdown snippet that appends a new block:

- `#### Review Round R{n}`
- reviewer metadata
- a markdown table with these columns (strict):
  - `ID` (e.g., `R3-S1`)
  - `Area` (one of: `Architecture | Interfaces | Data | Risks | Validation | Ops | Security`)
  - `Severity` (`critical | high | medium | low`)
  - `Suggestion`
  - `Rationale`
  - `Proposed Placement`
  - `Validation Approach` (how to prove it’s correct)

This makes triage fast and reduces “hand-wavy” feedback.

### Snippet validation (checkpoint)

Add validation rules on agent output before appending:

- Must contain correct round heading
- Must contain at least 1 suggestion row, <= `max_suggestions`
- Must not contain “Appendix A” or “Appendix B” headers
- Must match expected table columns
- Severity must be in allowed enum
- Area must be in allowed enum

Fail-fast if invalid (do not append partial/malformed output).

---

## Memory: Preventing duplicate suggestions

### Baseline (already implemented)

- Dedup via explicit IDs in Appendix A / B (prevents re-proposing already processed suggestions)

### Enhancement (recommended)

Add “semantic duplicate” prevention so models don’t propose the same thing under a new ID:

- Parse incoming suggestion rows
- Compute a stable hash: `hash(normalize(Area + Suggestion))`
- Store in state JSON as `seen_suggestion_hashes`
- Include the hashes (or a short list of recent suggestion summaries) in the next reviewer prompt

This keeps Appendix A/B as the authoritative record, but further reduces repetition.

---

## Implementation Plan (SDK changes)

### Phase 1 — Workflow implementation (MVP)

- Add `startd8/workflows/builtin/architectural_review_log_workflow.py`
  - Reuse core logic from `DocReviewLogWorkflow`
  - Add premium default model selection via `model_catalog`
  - Add architecture-specific prompt + snippet schema validator
  - Add cost guardrails (track from token usage, fail/warn thresholds)

- Register workflow in:
  - `startd8/workflows/builtin/__init__.py`
  - `startd8/workflows/registry.py`

### Phase 2 — State + dedupe enhancements

- Extend state JSON to include:
  - `seen_suggestion_hashes`
  - per-round suggestion summaries

- Extend prompts to include:
  - “Do not repeat these suggestion themes” list (from hashes / summaries)

### Phase 3 — Testing + docs

- Tests (using `MockAgent`) to verify:
  - appends only to Appendix C
  - respects applied/rejected IDs
  - fails on malformed snippet
  - stable round numbering
  - state file written

- Docs:
  - `docs/WORKFLOWS_ARCHITECTURAL_REVIEW.md` (usage, examples, schema)
  - Add to README “Workflows” section (short)

---

## Validation Plan (using the provided document)

### Offline/unit validation (no real API calls)

1. Copy `/Users/neilyashinsky/Documents/dev/contextcore-demo-retail/personas/IMPLEMENTATION_PLAN.md` to a temp path.
2. Run the workflow with `MockAgent` that returns a valid snippet.
3. Assert:
   - Appendix scaffolding created if missing
   - A new `Review Round R{n}` appended under Appendix C
   - State JSON created under `.startd8/`
4. Re-run and assert:
   - Round increments (R{n+1})
   - Previously applied/rejected IDs included in prompt (by inspection via mock capture)

### Live validation (optional)

Run with flagship agents (sequential) against the real file and verify:

- Suggestions are structured (Area/Severity/Validation)
- No “zombie” repeats after you record rejections in Appendix B

---

## Risks / Mitigations

- **Cost blow-ups with flagship models**
  - Mitigation: `warn_cost_usd`, `max_cost_usd`, and clear printed summary

- **Prompt length bloat (large documents)**
  - Mitigation: keep appendix out of prompt (already done in `doc-review-log`), and add optional `max_chars` truncation with a warning

- **Agents try to rewrite the document instead of appending**
  - Mitigation: strict output schema validation + fail-fast

---

## Recommended defaults (initial)

- `quality_tier`: `flagship`
- `reviewer_count`: `2`
- default agents (if available):
  - `anthropic:claude-opus-4-5-20251101`
  - `gemini:gemini-2.5-pro`
- `max_suggestions`: `10`
- `warn_cost_usd`: `$2.00` (tune)
- `max_cost_usd`: `$5.00` (tune)

