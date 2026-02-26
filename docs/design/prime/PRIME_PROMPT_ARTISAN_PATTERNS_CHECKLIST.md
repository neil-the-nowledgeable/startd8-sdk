# Prime Contractor: Artisan Pattern Adoption — Checklist

**Parent:** [PRIME_PROMPT_ARTISAN_PATTERNS_IMPLEMENTATION.md](PRIME_PROMPT_ARTISAN_PATTERNS_IMPLEMENTATION.md)  
**Formal Plan:** [PRIME_PROMPT_ARTISAN_PATTERNS_PLAN.md](PRIME_PROMPT_ARTISAN_PATTERNS_PLAN.md)

Quick reference for implementation tracking.

---

## Pattern 1: Mode-Aware System Prompts

- [x] PC-M1: Spec preamble for edit mode (verify existing implementation)
- [x] PC-M2: `_get_drafter_system_prompt(context)` — edit/create/search_replace (Artisan threshold: 50 lines)
- [x] PC-M3: YAML templates `draft_system_edit`, `draft_system_create`, `draft_system_search_replace`
- [x] PC-M4: Inline fallback for each template

## Pattern 2: Quantitative Constraints

- [x] PC-Q1: Quantitative spec constraint (X lines, Y min) in edit preamble
- [x] PC-Q2: Verify draft output format passes `min_output_lines` (already done)
- [x] PC-Q3: Configurable `edit_min_pct` in config

## Pattern 3: Ordering (Existing Before Spec)

- [x] PC-O1: Populate `existing_files` in `gen_context` when target files exist on disk
- [x] PC-O2: Verify `DRAFT_EDIT_PROMPT_TEMPLATE` ordering (already correct)
- [x] PC-O3: Budget for existing files (40KB or configurable)

## Pattern 4: Conditional Framing

- [x] PC-F1: Plan context framing — edit vs create preamble
- [x] PC-F2: Architectural context framing for edit mode
- [x] PC-F3: Task description verb (update vs implement)

## Pattern 5: Modular Assembly

- [x] PC-A1: Extract `_build_spec_*` section helpers
- [x] PC-A2: Remove redundant context dump — pop all structured keys
- [x] PC-A3: Deduplication audit — pop `requirements_context`, `protocol_guidance`, `scope_boundary` (from PipelineContextStrategy)

## Pattern 6: Budget and Truncation

- [x] PC-B1: Plan context truncation in spec (16KB)
- [x] PC-B2: Architectural context truncation (4KB)
- [x] PC-B3: Existing files budget 40KB (or configurable)
- [x] PC-B4: Spec context aggregate budget (12KB)
- [x] PC-B5: Plan load cap 16KB (down from 60KB)

## Pattern 7: YAML Externalization

- [x] PC-Y1: Complete YAML coverage — no hardcoded prompts (Phase 2 framing)
- [x] PC-Y2: `_format_lead_prompt()` with fallback
- [x] PC-Y3: New templates for mode-specific prompts
- [x] PC-Y4: Placeholders documented in YAML

---

## Acceptance Criteria

- [ ] AC-1: Single-feature run ≤ 50K input tokens
- [x] AC-2: Edit-mode receives edit_system + correct ordering
- [ ] AC-3: Plan context ≤ 16KB in spec
- [ ] AC-4: Arch context ≤ 4KB in spec
- [x] AC-5: YAML fallback works when file missing
