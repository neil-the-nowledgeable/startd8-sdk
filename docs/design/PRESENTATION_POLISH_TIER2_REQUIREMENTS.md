# Presentation Polish Tier 2 (Bespoke) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-11
**Status:** Draft
**Builds on:** `PRESENTATION_POLISH_CAPABILITY_REQUIREMENTS.md` v0.3 (Tier 1 shipped) — expands the
deferred FR-5/6/8 (vendoring) + FR-16–19/24 (Tier 2) into a dedicated, implementable spec.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the SDK's agent/cost/catalog layers. It de-risked the core mechanism,
> **flipped the vendoring scope**, and surfaced one new sub-requirement. The spine held; vendoring
> moved out of scope for v1 (a >30%-of-the-hard-part change — the loop earned its keep).

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| "LLM emits ThemeTokens" needs JSON-parse + manual validation (OQ-T2-1 open, feasibility-critical) | The SDK already has `agenerate_structured(prompt, output_schema, system_prompt=)` (`agents/claude.py:490`, also Gemini) — tool-use forces a typed object, validates via Pydantic `model_validate`, with **built-in semantic retry** on failure; returns `StructuredResult(value, raw)`. | **T2-FR-3 de-risked** to "call the existing helper." OQ-T2-1 resolved. |
| `ThemeTokens` can be the LLM's output schema directly | `agenerate_structured` requires a **Pydantic `BaseModel`**; `ThemeTokens` is a frozen `@dataclass` (`tokens.py:18`). | **New T2-FR-14:** define a Pydantic `BespokeThemeSchema` the LLM targets, then construct `ThemeTokens` from it — don't Pydantic-ify Tier 1's dataclass. Resolves OQ-T2-6. |
| Vendoring (T2-FR-9/10) is required so the engine can read the skill | The engine can read `~/.claude/skills/<id>/SKILL.md` **directly** (no existing reader, but trivial to add). Vendoring isn't needed for *execution*. | **T2-FR-9/10 downgraded to OPTIONAL / deferred from v1.** Vendoring becomes a separate "make the skill present in the project" nicety, not a Tier-2 blocker. OQ-T2-2 resolved. |
| Cost tracking needs manual wiring (T2-FR-8) | An agent constructed with a `cost_tracker` **auto-records** via `_run_with_cost_tracking` (`agents/base.py`); `TokenUsage.cost_estimate` gives per-call $. | **T2-FR-8 simplified** to "pass a cost_tracker." |
| a11y failure → regenerate (another paid call) | Schema validation retry is built into `agenerate_structured`, but **contrast failure is a different gate** (valid hex that fails AA). | **T2-FR-5 refined:** prefer **deterministic repair** (nudge L\* until contrast passes — $0, bounded) over a second paid call. Resolves OQ-T2-4. |
| Model choice open (OQ-T2-3) | `model_catalog` exposes `Models.CLAUDE_HAIKU_LATEST` / `QUICK_VALIDATION` (cheap tier). The task is tiny + structured. | Default to a **cheap tier**, user-overridable. OQ-T2-3 resolved (with OQ-T2-5 caveat below). |

**Resolved open questions:** OQ-T2-1 (→ `agenerate_structured`), OQ-T2-2 (→ read skill directly;
vendoring optional), OQ-T2-3 (→ cheap default, overridable), OQ-T2-4 (→ deterministic repair),
OQ-T2-6 (→ Pydantic `BespokeThemeSchema`). **Still open:** OQ-T2-5 (does `frontend-design`'s SKILL.md
actually improve token choice vs. a focused hand-written prompt? — needs a build-time spike, like the
Tier-1 OQ-8 spike).

---

## 1. Problem Statement

Tier 1 ships three fixed, deterministic, WCAG-AA themes (professional/editorial/minimal). Some apps
want a **distinctive** aesthetic — a palette/typography matched to a brand vibe — beyond the presets.
Tier 2 lets a user opt into an **LLM-generated bespoke theme** that leverages the `frontend-design`
skill's design sensibility, **without** the user installing or knowing the skill, and **without**
abandoning Tier 1's guarantees (accessibility gate, component reuse, idempotent re-application).

**The load-bearing design decision (from this session's OQ-8 spike): the LLM does NOT write CSS. It
emits a `ThemeTokens` object** (the same dataclass Tier 1 already uses — ~15 values: palette,
type scale, radii, fonts, shadow). The deterministic `css.py` pipeline then renders the stylesheet,
the `verify_contrast` gate validates it, and the component system applies — exactly as for a Tier-1
theme. This bounds the LLM to a tiny structured choice, makes a11y/stack-safety **free**, and makes a
bespoke theme a first-class re-renderable theme rather than a pile of un-gated LLM CSS.

### 1.1 Gap table

| Component | Current State (Tier 1) | Gap (Tier 2) |
|-----------|------------------------|--------------|
| Theme source | 3 fixed presets in `themes.py` | No way to generate a bespoke palette/type from a brief |
| Skill leverage | None (Tier 1 internalizes theme-factory/universal-design) | `frontend-design`'s sensibility not used |
| Skill execution | None usable (`SkillAgent`/MCP is a stub — never loads `SKILL.md`) | Need a real path: SKILL.md → `system_prompt` |
| LLM cost | $0 (no LLM) | Tier 2 is the one paid path — needs opt-in, estimate, tracking |
| Vendoring | None (not needed for Tier 1) | `frontend-design` must be present without user install |
| a11y | Deterministic gate on fixed themes | Must gate the *generated* tokens too |

---

## 2. Requirements

### A. Gating & cost (Tier 2 is opt-in and paid)
- **T2-FR-1.** Bespoke generation MUST be **explicitly opt-in** (e.g. `startd8 polish bespoke` or
  `polish apply --bespoke`); the default `polish apply` stays **Tier-1-only, $0**.
- **T2-FR-2.** Before any LLM call, the command MUST show an **up-front cost estimate** and require
  confirmation (skippable with an explicit `--yes` for headless/CI).
- **T2-FR-8.** LLM spend MUST be tracked via the SDK `costs/` machinery and reported to the user;
  Tier 1 continues to report `$0.00`. **(Planning: construct the agent with a `cost_tracker` — it
  auto-records via `_run_with_cost_tracking`; `TokenUsage.cost_estimate` gives per-call $.)**

### B. Bespoke generation (the LLM step)
- **T2-FR-3.** The LLM MUST emit a **structured theme object** (palette/type/spacing/radii/fonts) —
  raw CSS from the model is **never** accepted. **(Planning: use the existing
  `ClaudeAgent.agenerate_structured(prompt, output_schema, system_prompt=)` — tool-use forces a typed
  object + validates + retries. Not manual JSON parsing.)**
- **T2-FR-14.** *(new — from planning)* Because `agenerate_structured` requires a Pydantic model but
  Tier 1's `ThemeTokens` is a frozen `@dataclass`, define a Pydantic **`BespokeThemeSchema`** as the
  LLM's output schema (the 12 colors + `scale_ratio` + optional fonts; shape fields like
  `space_unit`/`radius`/`max_width` held at Tier-1 defaults unless deliberately exposed), then
  construct a `ThemeTokens` from the validated result. Do NOT Pydantic-ify the Tier-1 dataclass.
- **T2-FR-4.** The bespoke prompt MUST be built by reading the `frontend-design` `SKILL.md`
  (and optionally `theme-factory`/`universal-design`) and injecting it as the **`system_prompt`** of
  **one** `agenerate_structured` call. It MUST NOT use the `SkillAgent`/MCP stub (it never loads skill
  content). **(Planning: read `~/.claude/skills/<id>/SKILL.md` directly — no vendoring required for
  execution; see T2-FR-9.)**
- **T2-FR-13.** The user MAY provide an optional **brief** (e.g. "warm, trustworthy, fintech";
  brand color hints) that informs the direction. Absent a brief, generation still works.

### C. Safety: it's still a Tier-1 theme
- **T2-FR-5.** The generated tokens MUST pass the **same WCAG-AA `verify_contrast` gate** as Tier 1; a
  failing palette is never shipped. **(Planning: prefer **deterministic repair** — nudge the
  offending color's lightness until the pair passes AA, $0 and bounded — over a second paid
  regeneration. Schema-validity retry is already handled inside `agenerate_structured`; contrast is a
  separate, post-validation gate.)**
- **T2-FR-6.** The accepted `ThemeTokens` MUST flow through the **existing deterministic pipeline**
  (`css.py` render → component partials → provider ownership). A bespoke theme is a normal theme.
- **T2-FR-7.** The generated theme MUST be **persisted** (e.g. `.startd8/polish/bespoke-theme.json`)
  so the LLM call happens **once**; subsequent `polish apply` re-renders from the saved tokens at
  **$0** and stays idempotent/byte-stable. (Tier 2 generates the tokens; Tier 1 owns applying them.)

### D. Delivery & robustness
- **T2-FR-9.** *(DEFERRED from v1 — planning downgrade)* Vendoring the skill(s) into the project's
  `.claude/skills/` with provenance is **OPTIONAL**: the bespoke engine reads
  `~/.claude/skills/<id>/SKILL.md` directly, so vendoring is **not required for execution**. It
  remains a nice-to-have for "make the skill present in the downstream project for its own Claude
  Code," and is **out of scope for Tier-2 v1**. When built, mirror `CapDevPipeInstaller`.
- **T2-FR-10.** *(DEFERRED with T2-FR-9.)* Idempotent + re-runnable vendoring modes — only relevant
  once T2-FR-9 is built.
- **T2-FR-11.** After generation, before writing files, the command MUST **present the proposed
  tokens + a contrast report** for confirmation (a post-generation, pre-write preview). (There is no
  $0 pre-generation preview — generation requires the paid call.)
- **T2-FR-12.** Tier 2 MUST **degrade gracefully**: missing API key / unavailable skill / LLM error
  → fall back to Tier 1 with a clear message; never crash.

---

## 3. Non-Requirements
- **NR-1.** Does NOT build a general-purpose skill-execution framework — only the SKILL.md→system_prompt
  path this feature needs.
- **NR-2.** The LLM does NOT emit raw CSS, HTML, or React — only `ThemeTokens`.
- **NR-3.** Does NOT auto-run; always opt-in (NR for safety + cost).
- **NR-4.** Does NOT author brand content, logo, imagery, or copy (bucket 4, user-owned).
- **NR-5.** Does NOT introduce new theme *structure* (component set, layout) — Tier 2 only chooses
  token *values* for the existing Tier-1 structure.
- **NR-6.** Does NOT repair the `SkillAgent`/MCP stub as part of this feature (that's a separate
  cleanup); Tier 2 simply does not use it.

---

## 4. Open Questions

> Resolved in planning (see §0): **OQ-T2-1** (→ `agenerate_structured`), **OQ-T2-2** (→ read skill
> directly; vendoring optional/deferred), **OQ-T2-3** (→ cheap-tier default, overridable), **OQ-T2-4**
> (→ deterministic contrast repair), **OQ-T2-6** (→ Pydantic `BespokeThemeSchema`, T2-FR-14). Remaining:

- **OQ-T2-5. (build-time spike — the key remaining risk) SKILL.md fit.** `frontend-design`'s
  `SKILL.md` is oriented to *writing React/CSS*, not *picking ~15 tokens*. Does injecting it as the
  system prompt actually improve token taste over a focused hand-written prompt that encodes its
  *aesthetic principles*? Resolve with a small differential spike when building (SKILL.md-as-system-
  prompt vs. a curated prompt; judge the token output) — mirrors the Tier-1 OQ-8 discipline. This also
  determines whether vendoring `frontend-design` is worthwhile at all.
- **OQ-T2-7. (new) Brief → tokens grounding.** When the user supplies a brief (T2-FR-13), how is it
  combined with the SKILL.md system prompt (user message vs. appended)? Generation is once-only
  (T2-FR-7), so non-determinism is tolerable — but worth deciding for reproducibility of the saved
  theme.

---

*v0.2 — Post-planning self-reflective update. Core mechanism de-risked (existing `agenerate_structured`
+ `system_prompt`); 1 requirement added (T2-FR-14 Pydantic `BespokeThemeSchema`); vendoring (T2-FR-9/10)
downgraded from required to deferred/optional; T2-FR-5/8 simplified; 5 OQs resolved, 1 new (OQ-T2-7),
OQ-T2-5 remains the key build-time spike. Spine: LLM emits a structured theme object (not CSS) →
existing deterministic pipeline + AA gate; SKILL.md-as-`system_prompt` (not SkillAgent/MCP); opt-in +
cost-tracked + persisted-once ($0 re-apply). Builds on shipped Tier 1.*
