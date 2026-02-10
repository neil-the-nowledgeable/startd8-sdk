# Artisan Contractor — Model Assignment Correction

**Date:** 2026-02-10
**Branch:** feat/artisan-contractor
**Severity:** Design Deviation — Cost hierarchy inverted, models outdated

---

## Problem Summary

The artisan contractor implementation diverged from its design plan in three ways:

1. **Cost hierarchy inverted** — The plan's core innovation ("low-cost draft → high-cost validate") was flipped. Expensive Sonnet was used as the drafter and cheap Haiku as the validator.
2. **Models are a full generation behind** — Claude 3.5 models (October 2024) were used instead of the specified Claude 4.5/4.6 models.
3. **Reviewer role missing** — The plan calls for Opus as an independent second reviewer for design docs (Phase 3). No reviewer model was configured.

## Plan vs. Implementation

### What the Plan Specified (PLAN-artisan-contractor.md, lines 24-28)

| Role | Model | Tier | Cost/1M in |
|------|-------|------|------------|
| Drafter | `gemini:gemini-2.5-flash-lite` | Mini | $0.075 |
| Validator | `anthropic:claude-sonnet-4-5-20250927` | Balanced | $3.00 |
| Reviewer | `anthropic:claude-opus-4-5-20251101` | Flagship | $5.00 |

**Pattern: cheap generates, expensive validates**

### What Was Actually Implemented (protocols.py, lines 441-493)

| Role | Model | Generation | Cost/1M in |
|------|-------|------------|------------|
| Drafter | `claude-3-5-sonnet-20241022` | 3.5 (old) | ~$3.00 |
| Validator | `claude-3-5-haiku-20241022` | 3.5 (old) | ~$0.80 |
| Reviewer | *missing* | — | — |

**Pattern: expensive generates, cheap validates — the exact opposite**

## Root Cause

The PrimeContractor that generated the artisan code substituted familiar models (Sonnet 3.5 + Haiku 3.5) and assigned them to roles based on a "smart drafter, cheap checker" heuristic rather than reading the plan's explicit "cheap drafter, smart checker" design. The `model_catalog.py` module already had correct current-generation constants (`Models.CLAUDE_OPUS_LATEST`, `Models.CLAUDE_HAIKU_LATEST`, etc.) but the artisan code hardcoded its own stale entries instead of importing from the catalog.

## Cost Impact

With the inverted hierarchy, every draft retry (up to 6 per phase) was billed at Sonnet rates (~$3/1M tokens) instead of the intended Haiku rates (~$1/1M tokens). Meanwhile, the cheap Haiku validator may miss quality issues that Sonnet or Opus would catch, leading to more retry cycles.

## Correction Applied

### Updated Model Assignments (Anthropic-only)

| Role | New Model | Tier | Cost/1M in |
|------|-----------|------|------------|
| **Drafter** | `claude-haiku-4-5-20251008` | Fast | $1.00 |
| **Validator** | `claude-sonnet-4-5-20250929` | Balanced | $3.00 |
| **Reviewer** | `claude-opus-4-6` | Flagship | $15.00 |

### Design Decision: Anthropic-Only

The original plan used `gemini:gemini-2.5-flash-lite` as the drafter. Gemini proved unreliable in practice for code generation tasks. Haiku 4.5 is the cheapest Anthropic model and serves as the replacement drafter, maintaining the "cheap draft, expensive validate" pattern within a single provider ecosystem.

### Files Changed

- `docs/PLAN-artisan-contractor.md` — Cost model table updated
- `src/startd8/contractors/protocols.py` — Model catalog entries corrected
- `src/startd8/contractors/artisan_phases/preflight.py` — Model prefix validation updated

## Lessons

- **Verify generated code against plan specifications** — Automated code generation can silently invert design decisions when the generator's heuristics conflict with the plan.
- **Import from centralized catalogs** — `model_catalog.py` existed with correct constants but wasn't used. Hardcoding model IDs creates drift.
- **Cost hierarchy is a design constraint, not an implementation detail** — The "cheap draft, expensive validate" pattern is the economic foundation of the artisan workflow. Inverting it undermines the entire cost model.
