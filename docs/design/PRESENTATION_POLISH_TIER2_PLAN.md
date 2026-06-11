# Presentation Polish Tier 2 (Bespoke) — Implementation Plan

**Version:** 1.0 (matches Requirements v0.2)
**Date:** 2026-06-11
**Status:** Draft — ready to build after the OQ-T2-5 spike (Phase 0)

---

## Approach
One gated LLM call returns a structured theme object via the SDK's existing
`ClaudeAgent.agenerate_structured`, with a skill's `SKILL.md` injected as `system_prompt`. The
result is converted to a Tier-1 `ThemeTokens`, contrast-gated (deterministic repair on failure),
persisted once, and applied through the **existing** Tier-1 pipeline. New code is small because the
hard parts (structured output, cost tracking, CSS render, AA gate, provider) already exist.

New module surface: `src/startd8/presentation_polish/bespoke.py` (+ a Pydantic schema + a skill reader).

## Sequencing

### Phase 0 — OQ-T2-5 spike (do first; gates the SKILL.md dependency)
- Differential: generate tokens with (a) `frontend-design` SKILL.md as system prompt vs. (b) a
  focused hand-written "design-director" prompt encoding its principles. Judge token quality.
- **Outcome:** if SKILL.md wins → vendor/read it (T2-FR-4/9). If the curated prompt is as good →
  drop the SKILL.md dependency entirely (and T2-FR-9/10 vendoring becomes moot). Cheap to run.

### Phase 1 — Bespoke engine
| Step | FR | Seam |
|------|----|------|
| `BespokeThemeSchema` (Pydantic: 12 colors + scale_ratio + optional fonts) | T2-FR-14, T2-FR-3 | new `bespoke.py` |
| Skill reader: `~/.claude/skills/<id>/SKILL.md` (+ plugin cache fallback), graceful if absent | T2-FR-4, T2-FR-12 | new `bespoke.py` (no existing reader — confirmed) |
| Build prompt (SKILL.md → system_prompt; brief → user msg) + `agenerate_structured(..., BespokeThemeSchema, system_prompt=)` | T2-FR-4, T2-FR-13 | `agents/claude.py:490` |
| Convert validated schema → `ThemeTokens` (fill shape fields from Tier-1 defaults) | T2-FR-14, T2-FR-6 | `bespoke.py` → `tokens.ThemeTokens` |
| Contrast gate + deterministic repair (nudge L\* until `verify_contrast` passes; bounded) | T2-FR-5 | reuse `tokens.verify_contrast` + new repair fn |
| Persist `.startd8/polish/bespoke-theme.json`; re-apply reads it ($0) | T2-FR-7 | `bespoke.py` + `engine`/`themes` lookup |

### Phase 2 — Gating, cost, CLI/preview
| Step | FR | Seam |
|------|----|------|
| `startd8 polish bespoke` (or `apply --bespoke`); default stays Tier-1 $0 | T2-FR-1 | `cli_polish.py` |
| Cost estimate + confirm (`--yes` for headless) | T2-FR-2 | `cli_polish.py` |
| Construct agent with a `cost_tracker` → auto-records; report $ | T2-FR-8 | `costs/` + `agents/base.py` |
| Post-generation, pre-write preview: show tokens + contrast report, confirm | T2-FR-11 | `cli_polish.py` |
| Cheap-tier default model, overridable (`--model`) | OQ-T2-3 | `model_catalog` (`CLAUDE_HAIKU_LATEST`/`QUICK_VALIDATION`) |
| Once a bespoke theme is saved, it's a normal theme → `polish apply --theme bespoke` | T2-FR-6/7 | `themes.get_theme` extension |

### Phase 3 — (DEFERRED) Vendoring
Only if Phase 0 shows the SKILL.md is worth shipping into the project. Mirror `CapDevPipeInstaller`
(T2-FR-9/10). Not in v1.

## Key references (verified in planning)
- `agents/claude.py:490` `agenerate_structured(prompt, output_schema, system_prompt=, retry_on_validation=)` → `StructuredResult(value, raw)`; tool-use + Pydantic validate + semantic retry
- `agents/base.py:235` abstract `agenerate_structured`; `:329` `_run_with_cost_tracking` (auto cost)
- `presentation_polish/tokens.py:18` `ThemeTokens` (frozen dataclass), `verify_contrast`
- `presentation_polish/css.py` `render_stylesheet` (deterministic), `engine.apply_polish`, `themes.get_theme`
- `model_catalog.py` `Models.CLAUDE_HAIKU_LATEST` / `QUICK_VALIDATION`; `get_latest_model(provider, tier)`
- `costs/tracker.py:133` `record_cost`; `models.py` `TokenUsage.cost_estimate`
- SKILL.md reader: **none exists** — new; read `Path.home()/".claude/skills"/<id>/"SKILL.md"`

## Risks
- **R1 (OQ-T2-5, the real risk):** SKILL.md may not improve token taste over a curated prompt.
  *Mitigation:* Phase 0 spike decides; the curated-prompt fallback makes Tier 2 viable either way.
- **R2:** non-determinism of the LLM theme. *Mitigation:* persist-once (T2-FR-7) — generate is a
  one-time act; re-apply is deterministic from the saved tokens.
- **R3:** `agenerate_structured` is Claude/Gemini-only (OpenAI path may differ). *Mitigation:* default
  to a Claude agent for bespoke; gate on availability (T2-FR-12).
