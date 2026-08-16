# Theme-Token Activation — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.2 (post-planning — self-reflective update)   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · architecture `ARCHITECTURE_navig8r-presentation-definition-inheritance.md` (§7 step 2 — the first step ON the REQ-10 keystone)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-10-view-definition-cascade (parent keystone) · SOTTO_DESIGN_PRINCIPLE (byte-identical-when-absent)
**Audience:** operator / SDK contributors / cross-repo adopters (legal · benchmark · dev-os)
**Trust boundary:** local filesystem + authored definitions; no LLM; no network
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-activates-view-definition-theme-ee3af56c`
> **Semantic name:** *SDK navigator activates View Definition theme tokens by projecting resolved theme into the RenderProfile so renderers emit CSS custom properties and a base or domain theme change becomes visible while the app-scaffold path and non-overriding domains stay byte-identical.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-11`

## 0. Why this exists — the cascade's first visible teeth

REQ-10 shipped the keystone: a serializable `ViewDefinition` + a per-leaf cascade `resolve`, with a
`theme` section that both domains **inherit** — but `to_render_profile` deliberately projects only
`vocabulary` + `chrome`, so `theme` is **resolved-but-unprojected** (an inventoried dormancy). The
cascade therefore has real teeth at the *definition* layer that are **invisible at the renderer**: a
base theme change reaches the resolved dict but not a single rendered pixel. This REQ is
`ARCHITECTURE_…-inheritance.md` **§7 step 2** — it activates `theme` (and only `theme`), projecting the
resolved tokens into the existing `RenderProfile` and emitting them as CSS custom properties so a base
or domain theme change is **visible** in the rendered HTML. It is scoped to the *theme* mechanism, not a
design-token system: the CSS cascade IS the engine (base `:root` ⊕ an additive domain override).

## 0. Planning Insights (self-reflective update)

> Planning against the real renderer (`wireframe_view/_template.py`, `wireframe/profile.py`) revealed
> four corrections to the v0.1 draft:

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| The base theme tokens can just be projected as-is | `BASE_NAVIG8R_DEFINITION.theme` carries **placeholder values** (`ink #2a2620 / paper #faf8f3 / accent #3d7a57`) that **do NOT match** the template's real `:root` (`--ink:#241f17 / --paper:#f4efe4 / --accent:#1b545f`, `_template.py:24-28`). Projecting them would recolor **every** domain, breaking byte-identity even for a non-overriding domain. | **FR-1 added** — reconcile the base theme to the exact template `:root` values first (Genchi Genbutsu: bind to the real CSS, not invented tokens). |
| Theme activation must stay byte-identical everywhere | Activation is **inherently byte-breaking for a domain that HAS a theme override** — capability overrode `accent → #3a6a94` in REQ-10; making it visible *is* the point. But **no HTML byte-golden exists** for capability/requirements (tests assert content-presence, `test_metabolize_app_shape.py:104,119`); the only hard byte gate is the app path (`test_no_profile_is_byte_identical`). | Byte-identity is scoped precisely (**FR-2/FR-4**): app path + non-overriding domains stay byte-identical; an overriding domain's visible change is the intended, separately-tested proof (**FR-6**), not a violation. |
| The renderer needs a new theming pass | The template already emits a hardcoded `:root{…}` block; CSS cascade is last-wins. An **additive** second `:root` override (emitted only when `theme_tokens` is non-empty) reuses the existing cascade — the hardcoded block stays as the base/fallback layer. | **FR-4** is additive-only; empty `theme_tokens` ⇒ no override emitted ⇒ byte-identical (the SOTTO / empty-default-is-the-guard pattern). |
| Project the whole palette | The template `:root` has ~15 tokens (card/line/ochre/status colours); only `ink/paper/accent` are plausibly domain-varying today. | **NR-3** — activate only the three tokens the base already declares; leave the rest hardcoded (scope discipline). |

**Resolved open questions:** OQ-1 (which tokens?) → the three the base declares (`ink/paper/accent`),
reconciled to the real CSS. OQ-2 (feature flag?) → no — the empty-default `theme_tokens` map + the
consumer's "emit nothing when empty" IS the guard ([[project_prompt_injection_prevention]]-style
empty-default-is-the-guard; no flag).

## Overview

Add an optional `theme_tokens: Mapping[str, str]` (empty default) to `RenderProfile`; have
`to_render_profile` project the resolved definition's `theme` section into it; and have the wireframe
template emit those tokens as an **additive** `:root{ --token: value }` override — *only when the map is
non-empty*. Reconcile `BASE_NAVIG8R_DEFINITION.theme` to the template's actual `:root` values so a
non-overriding domain (requirements) and the app-scaffold path (no profile) stay **byte-identical**,
while an overriding domain (capability's `accent`) renders its override — the cascade's first visible
teeth. Theme only; the CSS cascade is the mechanism (no new engine).

## Objectives

- **O-1:** A resolved definition's theme reaches the rendered HTML — target: `to_render_profile` projects `theme` into `theme_tokens`, and a profiled render emits them as CSS custom properties.
- **O-2:** Byte-identity preserved where it must be — target: the app-scaffold path (no profile) is byte-identical (`test_no_profile_is_byte_identical` unedited), and a non-overriding domain is byte-identical (base theme reconciled to the real `:root`).
- **O-3:** A theme override is visible — target: a base theme change reaches every non-overriding domain's rendered output, and a domain's own override (capability `accent`) renders its value.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Projecting the placeholder base theme recolours every domain → byte-identity break | FR-1: reconcile base theme to the exact template `:root` values before projecting | high |
| quality | The renderer's new override block leaks onto the app path → app bytes change | FR-2/FR-4: `theme_tokens` empty-default + emit nothing when empty (SOTTO); app path never carries a profile | high |
| scope | Creep into the full design-token palette / chrome bindings / shell (later steps) | NR-1/NR-3: theme only, and only the three base-declared tokens | medium |
| complexity | Building a theming engine / token DSL | NR-2: plain string→string tokens → CSS custom properties; the CSS cascade IS the engine | medium |

## Functional requirements

- **FR-1 — Reconcile base theme to the real CSS.** `BASE_NAVIG8R_DEFINITION.theme` is set to the template's actual `:root` values for the activated tokens (`ink=#241f17`, `paper=#f4efe4`, `accent=#1b545f`), replacing REQ-10's placeholder values, so projecting the base theme reproduces today's rendered colours. Name: Navigator reconciles the base ViewDefinition theme tokens to the renderer's actual CSS root values so projecting them is a no-op for non-overriding domains. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: do the base theme tokens equal the template's real :root values?. Verify: `BASE_NAVIG8R_DEFINITION.theme` equals `{"ink": "#241f17", "paper": "#f4efe4", "accent": "#1b545f"}` — the exact `_template.py` `:root` literals for those tokens. Serves: O-2
- **FR-2 — RenderProfile gains an empty-default theme_tokens map.** `RenderProfile` gets `theme_tokens: Mapping[str, str]` defaulting empty, carried in `to_dict`; an empty map is the byte-identity guard — the app path (no profile) and any profile without theme are unchanged. Name: RenderProfile carries an optional empty-default theme_tokens map so an absent theme changes not a single byte. Touches: `src/startd8/wireframe/profile.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: code src/startd8/wireframe/profile.py. Approve?: is theme_tokens empty by default and byte-safe when absent?. Verify: `RenderProfile(statuses=()).theme_tokens == {}` and `test_no_profile_is_byte_identical` passes unedited; a profile with empty theme_tokens emits no `:root` override. Serves: O-2
- **FR-3 — Project resolved theme into the profile.** `to_render_profile` reads the resolved definition's `theme` section (previously unprojected) into `theme_tokens`, so a domain's resolved theme (base ⊕ its override) rides on the profile it produces. Name: Navigator projects a resolved ViewDefinition theme section into the RenderProfile theme_tokens map. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does to_render_profile carry the resolved theme into theme_tokens?. Verify: `to_render_profile(resolve(REQUIREMENTS_DEFINITION)).theme_tokens == BASE_NAVIG8R_DEFINITION.theme` and `to_render_profile(resolve(CAPABILITY_DEFINITION)).theme_tokens["accent"] == "#3a6a94"` (its override) while `["ink"]` equals the base. Serves: O-1
- **FR-4 — Renderer emits theme tokens as an additive CSS override.** When `profile.theme_tokens` is non-empty the wireframe template emits a second `:root{ --token: value; … }` block after the hardcoded one (cascade last-wins); when empty it emits nothing, so the no-profile render is byte-identical. Name: The wireframe renderer emits non-empty theme_tokens as an additive CSS custom-property root override and nothing when empty. Touches: `src/startd8/wireframe_view/_template.py`, `src/startd8/wireframe_view/view.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: code src/startd8/wireframe_view/view.py. Approve?: is the theme override additive and absent when theme_tokens is empty?. Verify: a render with `theme_tokens={"accent": "#3a6a94"}` contains a `:root` override setting `--accent:#3a6a94`; a render with no profile contains no such override block and `test_no_profile_is_byte_identical` passes unedited. Serves: O-1
- **FR-5 — Base theme change propagates to rendered output.** Changing a shared base theme token reaches the emitted CSS override of every non-overriding domain, with no edit to either domain delta — the cascade's propagation made visible. Name: A change to a base theme token propagates to the rendered CSS override of every non-overriding domain. Touches: `tests/unit/navigator/test_view_definition.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_view_definition.py. Approve?: does a base theme change reach both domains' rendered output?. Verify: mutating `BASE_NAVIG8R_DEFINITION.theme["ink"]` changes the projected `theme_tokens["ink"]` (hence the emitted `:root` override) for both requirements and capability, while capability keeps its own `accent`. Serves: O-1
- **FR-6 — A domain theme override renders visibly.** The capability domain's `accent` override renders a different accent than the template default — the concrete proof that the cascade now reaches the pixels (a deliberate, tested visible change; no HTML byte-golden is edited because none exists for the profiled domains). Name: The capability domain renders its own accent override so the theme cascade is visibly proven end to end. Touches: `tests/unit/navigator/test_view_definition.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: does capability's rendered accent differ from the base/template accent?. Verify: capability's rendered HTML `:root` override sets `--accent:#3a6a94` whereas requirements' sets `--accent:#1b545f` (the reconciled base); the app path emits neither. Serves: O-3

## Non-requirements

- **NR-1:** THEME ONLY. This REQ does not add chrome-binding expression grammar (architecture §7 step 3), control schema (step 4), region/layer bindings (step 5), shared shell fragments (step 6), or cross-repo `VIEW-SCHEMA` serialization (step 7) — each is a separate later REQ.
- **NR-2:** No theming engine, no token DSL, no plugin system — the tokens are a plain `str → str` map and the projection emits them as CSS custom properties; the browser's CSS cascade is the inheritance engine (not re-implemented).
- **NR-3:** Activate ONLY the tokens the base already declares (`ink`, `paper`, `accent`). Do NOT extract the rest of the template palette (`card`/`line`/`ochre`/status colours) into the definition — those are not domain-varying yet and stay hardcoded in `_template.py`.
- **NR-4:** The app-scaffold path (no profile) is NEVER themed and the hardcoded `:root` is NOT deleted — it remains the base/fallback layer that an (optional) additive override sits on top of, so absent-theme output is byte-identical.

## Appendix A — Accepted (with where merged)
*(none yet — CRP incoming)*

## Appendix B — Rejected (with rationale)
*(none yet — CRP incoming)*

## Appendix C — Incoming review rounds
*(none yet)*

*v0.2 — Post-planning self-reflective update. 1 requirement added (FR-1 base-theme reconciliation), byte-identity scope tightened to app-path + non-overriding domains, 2 open questions resolved (token set; no feature flag).*
