# View Definition Schema and Cascade Resolver — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · architecture `ARCHITECTURE_navig8r-presentation-definition-inheritance.md` (§7 step 1 — the keystone)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-01-sdk-node-home (parent) · REQ-04-lift-lenses-to-shared-transform · REQ-06-corpus-governance
**Audience:** operator / SDK contributors / cross-repo adopters (legal · benchmark · dev-os)
**Trust boundary:** local filesystem + authored definitions; no LLM; no network
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-defines-presentation-as-a-a458d6d7`
> **Semantic name:** *SDK navigator defines presentation as a serializable View Definition that inherits from a shared base via a per-leaf cascade so a base design change propagates atomically to every domain while each keeps its own overrides and renderers stay byte-identical by projecting the resolved definition to the existing RenderProfile.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-10`

## 0. Why this exists — the keystone

`ARCHITECTURE_navig8r-presentation-definition-inheritance.md` establishes the target: presentation as a
**separate, serializable, inheritable View Definition**, distinct from content (the Node graph). This REQ
builds the **keystone** — the schema + the cascade resolver + the two-domain inheritance proof. Every later
step (theme tokens into the definition, region/layer bindings, shared shell fragments, cross-repo
`VIEW-SCHEMA` JSON) builds on this. It is deliberately scoped to the *mechanism*, not a rewrite of the
renderers: renderers keep consuming a `RenderProfile`, now *projected* from the resolved definition.

## Overview

Introduce a `ViewDefinition` (the serializable presentation twin of `NODE-SCHEMA`) with sections mirroring
the scaffold taxonomy (theme · vocabulary · chrome · glance · control · regions · lenses) and an `extends`
pointer. Add a **cascade resolver** — `resolve(def) = deep_merge(resolve(extends), def)` — that merges
**per leaf key** over **keyed collections** (statuses/regions keyed by id, not positional), so an inheritor
overrides at the finest grain and still inherits base updates to its siblings (atomic), and a base change
propagates to every non-overriding inheritor. Provide a shared **base navig8r definition**, re-express the
**requirements** domain as `base + delta`, and prove cross-domain reuse with a **second** domain extending
the same base. Renderers are untouched: a resolved definition **projects to the existing `RenderProfile`**,
so the deterministic app-scaffold path stays byte-identical.

## Objectives

- **O-1:** Presentation is a separate, serializable, inheritable structure — target: `ViewDefinition` round-trips through JSON; a domain definition is expressed as `extends: base` + a thin delta.
- **O-2:** Shared elements propagate atomically — target: a base change reaches every non-overriding inheritor; a domain override of one leaf does NOT freeze its siblings.
- **O-3:** No regression — target: resolved definition projects to `RenderProfile`; renderers unchanged; `test_no_profile_is_byte_identical` green, unedited.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| complexity | Over-building — a bespoke DSL/parser, plugin system, or general theming engine (the requirements-engineering-OS shadow) | NR-1/NR-2: parser-free (plain dict/dataclass + JSON), keystone scope only, prove-with-2 before generalizing | high |
| quality | List (positional) merge makes overrides non-atomic — overriding one status replaces the whole list | FR-2: keyed-collection deep-merge (merge by id), never positional replace | high |
| quality | Divergence from renderers — a new model the renderers can't consume | FR-6: project the resolved definition to the existing `RenderProfile`; renderers unchanged; byte-identity gate | high |
| scope | Scope-creep into theme-token extraction / region bindings / shell (later architecture steps) | NR-3: those are separate REQs; this REQ ships schema + resolver + base + 2-domain proof only | medium |

## Functional requirements

- **FR-1 — ViewDefinition model.** A serializable `ViewDefinition` (dataclass or typed dict) in `src/startd8/navigator/view_definition.py` with an `extends: Optional[str]` pointer and sections mirroring the scaffold taxonomy — `theme`, `vocabulary`, `chrome`, `glance`, `control`, `regions`, `lenses` — using **keyed maps** for overridable collections (e.g. `vocabulary.statuses` keyed by status id), round-trippable via `to_dict`/`from_dict` (JSON). Name: Navigator introduces a serializable ViewDefinition model with an extends pointer and scaffold-taxonomy sections using keyed collections. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does ViewDefinition round-trip through JSON and use keyed maps for overridable collections?. Verify: a `ViewDefinition` with an `extends` + a keyed `statuses` map round-trips `from_dict(to_dict(d)) == d`; positional lists are not used for overridable collections. Serves: O-1
- **FR-2 — Cascade resolver (deep-merge, per-leaf, keyed).** `resolve(definition, registry) -> ResolvedDefinition` computes `deep_merge(resolve(extends), definition)` — recursive over `extends`, later-wins **per leaf key**, merging keyed collections **by id** (never positional-replace), scalars replaced, so overrides are atomic. Name: Navigator resolves a ViewDefinition by deep-merging its extends chain per leaf key and merging keyed collections by id. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does resolve merge per leaf and merge keyed collections by id rather than replacing the whole collection?. Verify: `resolve` of a domain that overrides `theme.accent` yields the domain accent AND the base `theme.ink`; overriding one `statuses[id].color` keeps the other base statuses; a scalar override wins. Serves: O-2
- **FR-3 — Base navig8r definition.** A shared `BASE_NAVIG8R_DEFINITION` (the top-level design definition) providing the defaults every domain inherits — the shared theme, lenses reference, control-panel structure, glance bindings, and the region/layer skeleton. Name: Navigator ships a shared base navig8r ViewDefinition that domain definitions extend for their defaults. Touches: `src/startd8/navigator/view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: is there one shared base definition all domains extend?. Verify: `BASE_NAVIG8R_DEFINITION` exists, has `extends=None`, and carries the shared theme/lenses/control/glance/region defaults; resolving it is idempotent. Serves: O-1
- **FR-4 — Requirements domain definition.** The requirements domain is expressed as `REQUIREMENTS_DEFINITION` = `extends: base` + a thin delta (its vocabulary/statuses + chrome), replacing the standalone masthead derivation as the definition's owner (FR-17/FR-18 derivations move under `chrome`). Name: The requirements domain is a thin ViewDefinition delta that extends the base rather than a standalone profile. Touches: `src/startd8/navigator/view_definition.py`, `src/startd8/navigator/sources_requirements.py`. Lives: code src/startd8/navigator/sources_requirements.py. Approve?: is the requirements presentation now base + a thin delta?. Verify: `REQUIREMENTS_DEFINITION.extends` points at the base; its own keys are only the domain delta (vocabulary/chrome), not a full copy; resolving it reproduces today's requirements chrome. Serves: O-1
- **FR-5 — Second domain proves cross-domain reuse.** A second domain (capability-index or node-schema) is expressed as `extends: base` + its own delta, sharing the same base. Name: A second domain definition extends the same base to prove cross-domain reuse of the shared presentation. Touches: `src/startd8/navigator/view_definition.py`, `src/startd8/navigator/sources_capability.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: do two domains share one base with only their own deltas?. Verify: the 2nd domain definition `extends` the same base; its resolved theme/lenses/control equal the base's (not re-specified); its vocabulary is its own. Serves: O-2
- **FR-6 — Base-change propagation.** Changing a shared value in the base propagates to BOTH domains' resolved definitions with no edit to either domain delta. Name: A change to the base definition propagates to every non-overriding domain without editing the domain deltas. Touches: `tests/unit/navigator/test_view_definition.py`. Lives: test tests/unit/navigator/test_view_definition.py. Approve?: does a base change reach all non-overriding inheritors automatically?. Verify: mutating a base theme token changes the resolved value for both domains that did not override it; a domain that DID override keeps its own value. Serves: O-2
- **FR-7 — RenderProfile projection (byte-identity).** A resolved definition projects to the existing `RenderProfile` (`to_render_profile(resolved) -> RenderProfile`) so renderers are unchanged and the deterministic app-scaffold path stays byte-identical. Name: A resolved ViewDefinition projects to the existing RenderProfile so renderers and the app-scaffold path are unchanged. Touches: `src/startd8/navigator/view_definition.py`, `src/startd8/navigator/cli_navigator.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does the resolved requirements definition project to the same RenderProfile the renderer used before?. Verify: `to_render_profile(resolve(REQUIREMENTS_DEFINITION))` equals today's derived requirements profile for REQ-01; `test_no_profile_is_byte_identical` passes unedited. Serves: O-3

## Non-requirements

- **NR-1:** No bespoke parser / DSL syntax — the definition is plain dict/dataclass + JSON; the only expression grammar (chrome bindings `{doc.title}`) is a LATER REQ (architecture §7 step 3), not this one.
- **NR-2:** No plugin system, no general theming engine, no runtime extension points — keystone scope only; generalize after a 2nd real cross-repo adopter.
- **NR-3:** Do NOT extract theme tokens out of the template CSS, formalize region bindings, or extract shared shell fragments yet — those are architecture §7 steps 2/5/6, separate REQs. This REQ ships the schema + resolver + base + 2-domain proof + RenderProfile projection only.
- **NR-4:** No cross-repo serialization/adopter onboarding yet (architecture §7 step 7) — the JSON round-trip (FR-1) is the seam that enables it later, but no external consumer is wired here.
