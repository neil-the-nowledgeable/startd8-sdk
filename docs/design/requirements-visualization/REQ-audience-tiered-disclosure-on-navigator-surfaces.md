# Audience-tiered disclosure on the navigator's dense surfaces (Move 2) — Requirements

**Project:** startd8-sdk (requirements visualization ladder) · **Criticality:** medium
**Version:** 0.3.1 (post-planning + lessons + principles)   **Date:** 2026-08-18
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** the profiled navigator (`src/startd8/wireframe_view/_template.py`) · `STRATEGY_navig8r-inflection-two-sided-validation.md` §Move 2 · Move 3 (`REQ-unify-card-visibility-predicates`, landed `40efeac6`)
**Inherits standards:** det-req-kit · NODE-SCHEMA · NAMING_CONVENTION · SOTTO_DESIGN_PRINCIPLE · the audience×fluency lens (`cur=role|flu`, `resolveVM`) · REQ-14 definition-owned control taxonomy
**Audience:** operator / requirement reader
**Trust boundary:** local render only · no network · no LLM · every tier is resolved client-side from the already-embedded `#plan-data`
**Data classification:** internal

> **DIDL identity (document):**
> - **Semantic name:** Make audience a first-class disclosure tier on the navigator's dense surfaces so each surface declares its minimal and advanced-only fields, resolved by the existing audience×fluency lens — the deferred band-pare becomes a lens tier, not a delete
> - **Local key (initiative):** `FEAT-navigator-audience-tiered-disclosure`
> - **Canonical ref (planned):** `cc:intent:navig8r:interaction:audience-tiered-disclosure`
> - **Readable handle:** `feature/navigator-audience-tiered-disclosure`

---

## 0. Planning Insights (Self-Reflective Update)

> Move 2, reflectively specced against the LANDED code (Move 3's seam + the doc-context band this session
> built maximal-then-deferring). The v0.1 idea — "audience becomes one more predicate on the unified
> visibility model" (the strategy's phrasing) — was **falsified by planning against `_template.py`**: the
> dense surfaces are CHROME re-rendered from `payload.profile.*`, not per-card classes, so audience-tiering
> is a **re-render disclosure**, not a `PRE_PAGING_REASONS` visibility predicate. Every FR below is grounded.

| v0.1 Assumption | Planning Discovery (grounded) | Impact |
|-----------------|-------------------------------|--------|
| Audience is "one more predicate on the visibility model" (a hide-class like `srch-hidden`) | The doc-context band (`renderDocBand` `_template.py:677-698`) renders from `payload.profile.doc_context` — fixed CHROME, re-emitted by `renderAll`, NOT a per-card class. The lens (`cur=role\|flu`, `resolveVM` `:588`) ALREADY re-renders card *content* per variant, but chrome surfaces ignore it. | **FR-1/FR-3:** audience-tiering is a RE-RENDER disclosure driven off the existing `cur`, not a new hide-class. The reserved `aud-hidden` per-card *visibility* predicate Move 3 left is a DIFFERENT, deferred thing (NG-1). |
| Need a new audience mechanism | The lens key `cur=role\|flu` already carries the fluency depth axis; `renderDocBand` is already called from `renderAll` (`:1113`) on every lens change. | **FR-1:** derive the disclosure tier from the EXISTING `cur` (its fluency) in one function — reuse, don't fork (Mottainai/Kagami). |
| The band shows one fixed field set | The band emits 6 chips (criticality·domain·for·trust·data·version) + counts + a risks `<details>` — ALL always (`:679-696`). The pare deferred this session was exactly trust/data/version/full-risk-detail. | **FR-2/FR-5:** declare which fields are minimal (criticality·counts·risk-summary) vs advanced-only (trust·data·version·full-risk-detail); the deferred pare is the MINIMAL tier, nothing deleted. |
| Tiering could hard-cut fields for beginners | The standing lesson forbids hard-cutting dense surfaces. | **FR-5:** the maximal tier shows the FULL set the band shows today; every field stays reachable — beginners get less by default, not less available. |

### 0.1 Lessons-Learned Hardening (v0.3)
- **[audience-tiered-not-destructive-pare]** — don't hard-cut a dense surface to "pare back"; make disclosure audience-tiered via the role×fluency lens, keep ALL options available, maximal = the advanced tier → drove **FR-5** (the maximal tier is the current full band; minimal is a default, not a deletion) and the whole framing.
- **[content-is-cruft-until-proven]** — checked: every tiered field traces to `payload.profile.doc_context` (authored source), so tiering hides nothing unproven; no field is invented.

### 0.2 Design-Principle Hardening (v0.3.1)
- **[Mottainai]** — don't regenerate what exists → **FR-1** derives the tier from the existing `cur`/`resolveVM` lens; no second audience mechanism.
- **[Kagami]** — edit the source, not a mirror → the tier is read where the surface renders (`renderDocBand`), driven by the one lens key; no forked audience state, no per-surface audience flag to drift.
- **[Accidental-complexity]** — one documented tier→fields map (FR-4) replaces per-surface `if(beginner)` branching, so adding a surface is a registration, not a new conditional.

---

## Overview

The navigator's audience×fluency lens (`cur=role|flu`) re-renders card *content* per variant, but the dense
*chrome* surfaces — flagship: the doc-context band — render a single MAXIMAL field set from
`payload.profile.doc_context` regardless of the reader. This move makes audience a first-class **disclosure
tier**: a surface declares its minimal vs advanced-only fields in one place, a tier is derived from the
existing lens (beginner → minimal · intermediate → standard · advanced → maximal), and each surface re-renders
at that tier through the existing `renderAll` path. The deferred band-pare (trust · data · version · full risk
detail) becomes the *advanced* tier — nothing is deleted; a beginner sees less by default, an auditor sees all.
This is the human/business-value side of the two-sided coin: the right person validates the right thing at the
right depth. Profiled-navigator-only; app-scaffold byte-identical.

## Objectives

- **O-1 — One tier, derived from the existing lens.** A single `discloseTier()` derives minimal/standard/maximal from the existing `cur` audience×fluency key — no second audience mechanism.
- **O-2 — Surfaces declare their tiers.** Each dense surface declares which fields are minimal vs advanced-only in one documented place; the render shows the tier's set.
- **O-3 — Tier, don't delete.** The maximal tier shows the full field set the surface shows today; every field stays reachable — the deferred pare is the minimal default, not a deletion.
- **O-4 — A documented seam.** Adding a surface (or a field) to the tiering is a one-place registration, not per-surface conditional branching.
- **O-5 — Byte-identical app path.** Profiled-navigator-only; with no profile no tiering machinery is active and the app-scaffold render is byte-identical.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Tiering hard-cuts a field a reader needs (regresses to destructive pare) | FR-5: the maximal tier = today's full set; every field reachable at advanced; a beginner default is not a deletion | high |
| architecture | A second audience mechanism forks from the existing lens | FR-1: the tier derives from the existing `cur`/`resolveVM`; no new state | high |
| quality | Per-surface `if(tier)` branching accretes (the accidental complexity being avoided) | FR-4: one documented tier→fields map; a surface registers, doesn't branch | medium |
| byte-identity | The tiering machinery leaks onto the app-scaffold path | FR-6: all machinery is profile-gated; guarded by `test_no_profile_is_byte_identical` | high |

## Profile

**internal** — a renderer-internal disclosure-layer refactor of the profiled navigator. No new CLI surface,
no new payload fields; it reads the existing `payload.profile.doc_context` + the existing `cur` lens key. The
observable delta is that dense surfaces show a tiered field set by audience; the app-scaffold path is unchanged.

## Functional Requirements

- **FR-1 — Derive the disclosure tier from the existing lens.** Add one `discloseTier()` that maps the existing `cur` audience×fluency key's fluency to a disclosure tier (`beginner`→minimal · `intermediate`→standard · `advanced`→maximal), reusing the lens (`cur`/`resolveVM`) with no new audience state. Name: A single discloseTier function derives the minimal standard or maximal disclosure tier from the existing audience fluency lens key. Touches: `src/startd8/wireframe_view/_template.py`. Verify: `discloseTier` returns `maximal` for an advanced fluency, `minimal` for a beginner fluency, and reads the existing `cur` (no new payload field or second audience variable is introduced). Serves: O-1
- **FR-2 — The doc-context band declares its tiers.** The doc-context band (`renderDocBand` `_template.py:677-698`) declares a minimal field set (criticality · counts · risk summary) always rendered, and an advanced-only set (trust · data classification · version · the full risk detail rows) rendered only at the maximal tier; a standard tier adds domain · audience. Name: The doc-context band declares a minimal always-on field set and an advanced-only set gated on the maximal tier. Touches: `src/startd8/wireframe_view/_template.py`. Verify: at the minimal tier the band renders the criticality chip · counts · a collapsed risk summary and NO trust/data/version chip; at the maximal tier it renders trust · data · version · expanded risk detail; the standard tier adds the domain and audience chips. Serves: O-2
- **FR-3 — The tier re-renders through the existing path.** The doc-context band re-renders at the current tier on every lens change through the existing `renderAll`/`renderDocBand` path, so switching the audience/fluency select re-tiers the band exactly as it re-renders the cards today. Name: The doc-context band re-renders at the current disclosure tier through the existing renderAll path on every lens change. Touches: `src/startd8/wireframe_view/_template.py`. Verify: changing the fluency select from beginner to advanced re-renders the band from the minimal set to the maximal set without a page reload, via the same `renderAll` invocation that re-renders the cards. Serves: O-1
- **FR-4 — One documented disclosure seam.** Expose one documented in-code seam (a single tier→fields registration naming, per surface, which fields are minimal vs advanced-only) so a new surface or field is tiered by registering it there, with no per-surface `if(tier)` branching duplicated across handlers. Name: A documented single-place disclosure seam registers each surface minimal and advanced fields so tiering a new surface is a registration not a branch. Touches: `src/startd8/wireframe_view/_template.py`. Verify: the seam enumerates the doc-context band's minimal and advanced field sets in one place, and `renderDocBand` reads the tier's set from it rather than open-coding a fluency check per chip. Serves: O-4
- **FR-5 — Tier, never delete.** The maximal tier renders the full field set the doc-context band renders today (criticality · domain · audience · trust · data · version · counts · full risk detail); no field is removed from the surface — a beginner sees a minimal default and reaches the rest by raising the fluency, so the deferred pare is a tier, not a deletion. Name: The maximal tier renders the full current band field set so every field stays reachable and no disclosure is deleted. Touches: `src/startd8/wireframe_view/_template.py`, `tests/unit/wireframe/test_render_profile.py`. Verify: the set of fields the band emits at the maximal tier equals the set it emits today (a parity check over the chip/risk fields); no field present today is absent at maximal. Serves: O-3
- **FR-6 — Disclosure tiering is distinct from card visibility.** Audience-tiered disclosure is a re-render of chrome field-sets (via the lens), NOT a `PRE_PAGING_REASONS` per-card visibility predicate; the reserved `aud-hidden` per-card audience-VISIBILITY predicate stays deferred and is not introduced here. Name: Audience disclosure tiering is a chrome re-render distinct from the deferred per-card aud-hidden visibility predicate. Touches: `src/startd8/wireframe_view/_template.py`. Verify: no card gains an `aud-hidden` class and `PRE_PAGING_REASONS` is unchanged by this move; the tiering only changes which fields a surface renders, never which cards are visible. Serves: O-1
- **FR-7 — App-scaffold byte-identity.** All disclosure-tier machinery is profiled-navigator-only: with no `payload.profile` the doc-context band renders nothing (its existing `if(!c) return ""` guard) and `discloseTier`/the seam are never exercised, so the app-scaffold render emits not one changed byte. Name: The whole disclosure-tier model is profile-gated so the app-scaffold render stays byte-identical. Touches: `src/startd8/wireframe_view/_template.py`, `tests/unit/wireframe/test_render_profile.py`. Verify: `render_html(_plan()) == render_html(_plan(), profile=None)` (`test_no_profile_is_byte_identical`) stays green unedited. Serves: O-5

## Non-goals

- **NG-1 — No per-card audience VISIBILITY predicate.** This move does NOT hide cards by audience (no `aud-hidden` in `PRE_PAGING_REASONS`) — that per-card visibility predicate stays deferred (Move 3 reserved the slot; a future move may fill it). This move is per-surface DETAIL disclosure only.
- **NG-2 — No new payload fields or lens variants.** It reads the existing `payload.profile.doc_context` + `cur`; it adds no `#plan-data` field and no new audience/fluency variant.
- **NG-3 — Not the whole surface inventory in v1.** The doc-context band is the flagship (the surface built maximal-then-deferring this session); the detail peek + card record adopting the same seam are a fast follow, not v1 scope — v1 establishes the tier + seam and tiers the band.
- **NG-4 — No CLI surface / no persisted tier.** The tier derives from the live lens; it is not written to `localStorage` and adds no `startd8` command.

## Owned fields

No new NODE-SCHEMA/payload fields. It owns three in-code artifacts: `discloseTier()` (the tier resolver), the
tier→fields disclosure seam (the registration), and the doc-context band's tiered render.

## Contract projection

- **Backend:** python-cli-surface — the profiled navigator HTML is emitted by `render_html` over `_template.py`.
- **Vocabulary home (cite):** the audience×fluency lens (`cur=role|flu`, `resolveVM`, `_template.py`); `docs/NAMING_CONVENTION.md`.

| Entry | Where | Shape |
|-------|-------|-------|
| `discloseTier()` | `_template.py` client JS | pure `cur` → `minimal\|standard\|maximal` |
| disclosure seam | `_template.py` in-code tier→fields map | per-surface minimal vs advanced field registration |
| tiered doc-context band | `renderDocBand` (`:677-698`) | renders the tier's field set; re-rendered by `renderAll` |
| byte-identity guard | `tests/unit/wireframe/test_render_profile.py::test_no_profile_is_byte_identical` | profile=None ⇒ identical output |

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

*v0.3.1 — reflective loop (planning falsified the "predicate" framing → re-render disclosure) + lessons
(audience-tiered-not-destructive) + principles (Mottainai/Kagami: reuse the lens). BUILD-READY.*
