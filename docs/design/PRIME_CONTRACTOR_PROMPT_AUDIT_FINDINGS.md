# Prime Contractor Prompt Audit — Findings

> **Date:** 2026-03-05
> **Scope:** What prompts does the PrimeContractorWorkflow persist after a run?
> **Goal:** Audit cloud LLM prompts for quality

---

## Existing Prompt Persistence Mechanisms

### 1. Walkthrough Mode (Dry-Run Prompt Capture)

**Activation:** CLI `--walkthrough` flag or `PrimeContractorWorkflow(walkthrough=True)`

Walkthrough mode persists all LLM prompts **without making API calls**. It writes 5-7 files per feature to `.startd8/walkthrough/prime/{feature_id}/`:

| File | Contents |
|------|----------|
| `spec_user_prompt.md` | Full spec phase user prompt |
| `spec_system_prompt.md` | Spec phase system directive |
| `draft_system_prompt.md` | Draft system prompt (includes existing file context) |
| `draft_user_prompt.md` | Draft user prompt (template + placeholders) |
| `review_system_prompt.md` | Review system prompt |
| `review_user_prompt.md` | Review user prompt (template reference) |
| `metadata.json` | Feature metadata (target files, agent specs, execution mode) |

**Source:** `prime_contractor.py:1779-1918` (`_persist_walkthrough_prompts()`)

**Limitation:** Walkthrough mode skips execution — prompts are captured but no LLM responses are generated. This is a pre-run audit tool, not a post-run audit trail.

---

### 2. Post-Mortem Report (Post-Run Metadata)

Generated after every PrimeContractor run via a daemon thread (`launch_prime_postmortem_async()`).

**Output files in `.startd8/`:**

| File | Format | Contents |
|------|--------|----------|
| `prime-postmortem-report.json` | JSON | Full structured report with per-element metadata |
| `prime-postmortem-summary.md` | Markdown | Human-readable summary |
| `prime-postmortem-lessons.json` | JSON | Extracted lessons learned |

**Per-feature metadata captured in integration history:**

```
feature_name, feature_id, success, cost_usd, error (if failed),
files (integrated paths), generation_metadata (from CodeGenerator),
timestamp (ISO string)
```

**Generation metadata includes (from micro-prime adapter):**
- Tier classifications per element (TRIVIAL/SIMPLE/MODERATE/COMPLEX)
- Escalation reasons and details
- Repair steps applied (import_completion, bare_statement_wrap, over_generation_trim, etc.)
- Per-element success/failure status
- Template usage indicators
- Generation time per element
- Code truncated to 500 chars (avoids bloat)

**Source:** `prime_postmortem.py:890-953` (launcher), `prime_contractor.py:2239-2246` (history append)

**Standalone runner:** `scripts/run_prime_postmortem.py`

**Limitation:** The postmortem captures **what happened** (results, costs, timing) but does **NOT** capture the actual prompts sent to the LLM.

---

### 3. Generation Manifest (Pipeline Mode)

In pipeline mode, a generation manifest is written to `.startd8/generation-manifest.json`:

- Schema version, execution mode, configuration
- Per-feature summary (name, success, cost, model)
- Total cost and token counts
- Source checksum for staleness detection
- File permissions restricted to `0o600`

---

## The Gap

| Capability | Walkthrough Mode | Post-Mortem Report |
|-----------|-----------------|-------------------|
| Captures actual prompts | Yes | **No** |
| Captures LLM responses | No (dry-run) | Partial (code only, truncated) |
| Captures during real runs | No | Yes |
| Per-element granularity | No (per-feature) | Yes |
| Includes cost/timing | No | Yes |
| Includes repair steps | No | Yes |

**There is currently no mechanism to persist the actual prompts alongside their outputs during a real run.**

- Walkthrough captures prompts but skips execution
- Postmortem captures results but not prompts
- Neither provides a paired prompt-response audit trail

---

## Key Source Files

| File | Role |
|------|------|
| `src/startd8/contractors/prime_contractor.py` | Main workflow; walkthrough at lines 1779-1918, history at 2239-2246 |
| `src/startd8/contractors/prime_postmortem.py` | Post-mortem evaluator (evaluate at 335-444, markdown at 759-882) |
| `src/startd8/micro_prime/prime_adapter.py` | Micro-prime metadata serialization (lines 74-95) |
| `src/startd8/contractors/generators/` | LeadContractor prompt construction |
| `scripts/run_prime_postmortem.py` | Standalone post-mortem runner |
| `src/startd8/cli.py` | CLI flags (walkthrough at 1819-1820) |

---

## Phases of the Prime Contractor Pipeline

For prompt audit purposes, the three LLM-calling phases are:

1. **Spec Phase** — Generates implementation specifications from feature requirements
2. **Draft Phase** — Generates code from specs (uses existing file context)
3. **Review Phase** — Reviews generated code for quality

Each phase has a system prompt and a user prompt. Walkthrough mode captures all six prompt files. During real runs, these prompts are constructed identically but not persisted.

---

## Next Steps

To enable full prompt auditing during real runs, options include:

1. **Prompt logging mode** — Persist prompts alongside responses during execution (like walkthrough but with actual API calls)
2. **Postmortem prompt capture** — Thread prompt text through the generation pipeline into the postmortem report
3. **Separate prompt archive** — Write prompt/response pairs to a timestamped directory during execution, independent of the postmortem
