# Cross-Repo VIEW-SCHEMA Import — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · architecture `ARCHITECTURE_navig8r-presentation-definition-inheritance.md` (§7 step 7 — cross-repo serialization; **mechanism only**, real-adopter onboarding is out of scope)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-10-view-definition-cascade (parent keystone) · REQ-11/REQ-12 (siblings)
**Audience:** operator / SDK contributors / cross-repo adopters (legal · benchmark · dev-os)
**Trust boundary:** local filesystem (a JSON file); no network/remote fetch; no LLM
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-consumes-an-externally-authored-d055cadd`
> **Semantic name:** *SDK navigator consumes an externally-authored View Definition by loading its VIEW-SCHEMA JSON, resolving it against the shipped base, and projecting it to a RenderProfile so a second repo can author its presentation as a base+delta and render through the navigator without importing Python.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-13`

## 0. Why this exists — the export seam's other half

REQ-10 made a `ViewDefinition` serializable (`to_dict`/`from_dict`) and EC-1 shipped the **export**
half (`navigator view-definition` dumps JSON). This REQ ships the **import** half — the mechanism by
which a *second repo* (legal · benchmark · dev-os) authors its presentation as a base+delta JSON and the
navigator **consumes** it: loads it, resolves it against the shipped base (so it inherits the shared
theme/lenses/control/glance/regions), validates it, and projects it to the `RenderProfile` the renderers
already use — without the adopter importing any Python. It is scoped to the **mechanism + a synthetic
proof**; onboarding a *real* second repo is the outward, cross-team step this unblocks (NR-1).

## Overview

Add `load_definition(source)` (JSON file/dict → `ViewDefinition` via `from_dict`) and a way to resolve an
externally-authored definition against the shipped `DEFINITION_REGISTRY` (so its `extends: "base"` chain
flattens against the real base). Wire `navigator view-definition --from <file.json>` to load + resolve +
`validate_definitions` + dump the resolved JSON — the consumption proof. Prove cross-repo reuse with a
**synthetic adopter fixture** (a fictional "legal" domain JSON) that inherits the base theme/lenses and
renders its own vocabulary/chrome. All-new surface; the shipped registry, domains, and app path are
byte-identical.

## Objectives

- **O-1:** The navigator consumes an externally-authored definition — target: `load_definition` + resolve-against-base + project, driven by `view-definition --from`.
- **O-2:** An external definition inherits the shared base — target: a fixture `extends: "base"` resolves to the base theme/lenses/control + its own vocabulary/chrome, proving cross-repo reuse (the "2nd repo" without a real repo).
- **O-3:** Safe + byte-identical — target: a malformed external definition is rejected with a clear error (reusing `validate_definitions`); no network; the shipped surface is unchanged.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | A malformed external JSON crashes or silently renders wrong | FR-3: load → `validate_definitions` (resolve + binding-field check) → clear error, exit 1 | high |
| scope | Building a real adopter / remote fetch / a definition-authoring UI | NR-1/NR-3: mechanism + a local-file synthetic proof only; real onboarding + remote transport are out of scope | high |
| quality | Import mutates the shipped registry | NR-2: import is a read-only projection — the external def resolves against a *copy* of the registry, never written into the source | medium |

## Functional requirements

- **FR-1 — Load an external definition from JSON.** `load_definition(source)` reads a VIEW-SCHEMA JSON file (path) or dict and returns a `ViewDefinition` via `from_dict`, raising a clear `ValueError` when the payload is not an object or lacks `name`. Name: Navigator loads an externally-authored View Definition from a VIEW-SCHEMA JSON file or dict. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does load_definition turn a VIEW-SCHEMA JSON into a ViewDefinition?. Verify: `load_definition({"name": "x", "extends": "base", "vocabulary": {...}})` returns a `ViewDefinition` with `name == "x"`; a payload without `name` raises `ValueError`. Serves: O-1
- **FR-2 — Resolve an external definition against the shipped base.** `resolve_external(definition, registry=DEFINITION_REGISTRY)` resolves an external definition against a registry that includes it plus the shipped base, so its `extends: "base"` chain flattens and it inherits the base theme/lenses/control/glance/regions. Name: Navigator resolves an external definition against the shipped base registry so it inherits the shared defaults. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does an external definition inherit the shipped base when resolved?. Verify: a fixture `extends: "base"` resolved via `resolve_external` has `theme == BASE_NAVIG8R_DEFINITION.theme` and `lenses == BASE_NAVIG8R_DEFINITION.lenses` plus its own vocabulary. Serves: O-2
- **FR-3 — CLI consumes + validates an external file.** `navigator view-definition --from <file.json>` loads the external definition, resolves it against the base, runs `validate_definitions` on the augmented registry, and dumps the resolved JSON; a malformed external definition (bad `extends` or unknown binding field) is rejected with a clear error and exit 1. Name: The view-definition CLI consumes an external VIEW-SCHEMA file and rejects a malformed one with a clear error. Touches: `src/startd8/navigator/cli_navigator.py`, `tests/unit/navigator/test_sources_and_cli.py`. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: does `--from` load, validate, and dump an external definition?. Verify: `view-definition --from <good.json>` exits 0 and dumps the resolved JSON (base theme inherited); `--from <bad-extends.json>` exits 1 with an "unknown definition" / validation error. Serves: O-1, O-3
- **FR-4 — Synthetic-adopter proof.** A checked-in fixture VIEW-SCHEMA JSON (a fictional "legal" domain — `extends: "base"` + its own vocabulary/chrome) loads, resolves inheriting the base, and projects to a `RenderProfile` with its own eyebrow and the inherited base theme — the "2nd repo" proof without a real repo. Name: A synthetic legal-domain fixture proves an external repo can author base+delta and render through the navigator. Touches: `tests/unit/navigator/fixtures/`, `tests/unit/navigator/test_view_definition.py`. Lives: test tests/unit/navigator/test_view_definition.py. Approve?: does a synthetic external domain render through the navigator inheriting the base?. Verify: loading the fixture, `to_render_profile(resolve_external(defn))` yields the fixture's own `eyebrow` and `theme_tokens == BASE_NAVIG8R_DEFINITION.theme`. Serves: O-2
- **FR-5 — All-new surface, byte-identical.** The import path is entirely additive — the shipped `DEFINITION_REGISTRY`, the three domains, and the app-scaffold path are byte-identical; `test_no_profile_is_byte_identical` passes unedited. Name: The import mechanism is additive so the shipped registry, domains, and app path stay byte-identical. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_view_definition.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is the shipped surface unchanged by the import path?. Verify: `test_no_profile_is_byte_identical` passes unedited; the shipped `DEFINITION_REGISTRY` still validates clean; the three domain profiles are unchanged. Serves: O-3

## Non-requirements

- **NR-1:** Onboarding a REAL second repo (legal/benchmark/dev-os authoring + shipping its own VIEW-SCHEMA) is OUT OF SCOPE — that is the outward, cross-team step this mechanism unblocks. This REQ ships the mechanism + a synthetic in-repo fixture only.
- **NR-2:** Import is a read-only projection — an external definition is resolved against a COPY of the registry and projected; it is NEVER written into `DEFINITION_REGISTRY` or the shipped source.
- **NR-3:** No network / remote transport — the source is a local JSON file (or dict). Fetching a definition over HTTP is a separate concern (trust boundary).
- **NR-4:** No new schema/versioning negotiation — the VIEW-SCHEMA is the existing `to_dict`/`from_dict` shape; a versioned handshake is a later concern if real adopters diverge.
