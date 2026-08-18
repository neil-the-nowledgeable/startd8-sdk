# Cross-Surface View Definition — Shared Node-State Taxonomy + Drill/Rollup Across navig8r and the Cockpit — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only deliverable; plan follows via reflective-requirements)*
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-10-view-definition-cascade (the cross-DOMAIN cascade this extends to cross-SURFACE) · REQ-feature-capability-composition-rollup (the composition/rollup primitive the rollup binding reuses) · STRATEGY_navig8r-inflection-two-sided-validation (Move 1 hub — this is its surface-level twin)
**Audience:** operator (SDK contributors; cross-repo NODE-SCHEMA adopters; requirements-viz + kickoff self-use)
**Trust boundary:** local filesystem (View Definition dataclasses + det-req markdown + kickoff state); no LLM, no network
**Data classification:** internal

> **Readable handle:** `feature/navigator-cross-surface-view-definition`
> **Semantic name:** *The View Definition lifts the node-state taxonomy from a per-domain vocabulary to a shared cross-SURFACE owner — one canonical node state with a per-surface presentation mapping (navig8r grounded/spec/awaiting ↔ cockpit ok/review/blocked/activated) — and declares a drill binding (cockpit tile → navig8r node by #key) and a rollup binding (navig8r grounding → cockpit readiness) in the definition, reusing the existing cascade, the #key route, and the composition primitive, so both surfaces render the SAME node health and insight flows between them with the app path byte-identical.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:cross-surface-view-definition`

---

## 0. Why this exists — the View Definition is cross-DOMAIN today; the two surfaces speak different vocabularies for the SAME node health

> **The finding this spec is built on (grounded, file:line):** the `ViewDefinition` cascade already lifts a
> taxonomy to a SHARED owner across DOMAINS (requirements · capability · node-schema · pipeline all `extends: "base"`
> and each supplies its own `vocabulary.statuses` — `view_definition.py:395-546`). That machinery is *domain*-shaped:
> every domain is a fresh top-level `vocabulary`, and there is **no notion of one canonical node state presented two
> different ways for two SURFACES**. Meanwhile the cockpit (kickoff readiness board) presents the SAME node health in
> a *readiness* vocabulary — `ok/review/blocked/backlog` (`portal_spec.py:31-37`) + an activation severity
> `ok/attention/blocked` (`activation.py:56-58`) — that has **no shared owner** with the navig8r's
> `grounded/spec/awaiting/excluded/unknown` (`view_definition.py:398-407`). This spec makes the View Definition the
> shared cross-**surface** owner of that one taxonomy (one canonical state, two presentations) and declares the two
> cross-links (drill/rollup) in the definition — reusing the cascade, the `#<key>` route, and the composition
> primitive. It is a Mottainai (reuse) spec: a new base `node_state` section + a per-surface presentation projection
> + two declarative bindings — no surface rewrite, no new renderer.

**navig8r is the two-sided validation surface** (`STRATEGY_navig8r-inflection-two-sided-validation.md` §0): the
**cockpit** validates business value / readiness *at a glance* (exec altitude), the **navig8r** validates technical
grounding *in depth* (auditor altitude). **They are two surfaces on the same node state at different altitudes** —
and today they **speak different vocabularies for the same health** with no shared owner, so an insight on one
surface cannot flow to the other. The strategy's **Move 1 (the hub — topology cross-links)** wants navig8r to pivot
across surfaces; this spec is its **surface-level twin**: it makes the View Definition own the shared vocabulary +
the drill/rollup so the cross-links are *declared data*, not bespoke per-surface glue.

**The five grounded facts that make this mostly reuse:**

1. **The cascade already lifts a taxonomy to a shared owner — but across DOMAINS, not SURFACES.**
   `src/startd8/navigator/view_definition.py:139-176` (`resolve` / `_resolve`) flattens an `extends` chain with
   later-wins-per-leaf + keyed-collection-merge-by-id; `:295-390` `BASE_NAVIG8R_DEFINITION` is the shared root; the
   requirements status vocabulary lives at `:398-407` (`grounded/spec/awaiting/excluded/unknown` with `color`/
   `meaning`/`severity`/`is_gap`). Four domains reuse the base (`:549-555`). The lift-to-shared-owner *mechanism*
   already exists; it just has no *surface* dimension.

2. **The projection to the renderer is a single, reused seam.** `view_definition.py:224-285` `to_render_profile`
   reads `vocabulary.statuses` into `StatusStyle` tuples and projects them to the existing `RenderProfile`
   (`:256-266`) — the byte-identity anchor guarded by `test_no_profile_is_byte_identical`. A shared taxonomy that
   **projects to today's requirements statuses byte-for-byte** rides this exact seam with an empty-default guard.

3. **The cockpit's readiness taxonomy is a separate, shared-once map with NO common owner.** The cockpit derives
   attention ONCE and never re-derives (`portal_spec.py:29-30` note) into `_ATTENTION_DISPLAY = {ok, review, blocked,
   backlog}` (`portal_spec.py:31-37`) with a canonical sort (`:38`); activation adds a severity ladder
   `_SEV_OK/_SEV_ATTENTION/_SEV_BLOCKED` (`activation.py:56-62`) and the `ok/activated` exit convention
   (`activation.py:63-64`). This is the OTHER presentation of the same node health — readiness-flavored — with no
   link to the navig8r vocabulary.

4. **The drill target already exists — the `#<key>` full-page route.** `src/startd8/wireframe_view/_template.py:900`
   (`buildFullView(item)`) + `:923` (`resolveHash` reading `location.hash` → the node by key) + `:1402`
   (`hashchange` listener) are the client-side full-page route the View Definition already registers as the
   `fullview` region (`view_definition.py:382`). A **drill binding** (cockpit tile → navig8r node) is a declared
   pointer at this route — no new route.

5. **The rollup target already exists — the composition/rollup `serves` primitive.** `REQ-feature-capability-
   composition-rollup.md` (FR-3) draws a ground-up rollup edge via the already-target-generic `serves` edge
   (`graph_projection.py:181-182`) with no new edge kind. A **rollup binding** (navig8r grounding → cockpit
   readiness) is a declared reuse of that primitive's rollup direction, not new machinery.

**This is corpus/surface-agnostic — and it is the surface twin of the composition primitive.** The lift lives at the
**View Definition** level (a `node_state` section + a per-surface presentation projection + two bindings), so it
works for any surface pair over the same NODE-SCHEMA state. The composition REQ lifts a *value-lineage edge* between
nodes; this lifts the *node-state vocabulary + the surface cross-links* between two views of those nodes — same
strategy (own the shared thing once, project per consumer), different axis (SURFACE, not DOMAIN).

**Where this sits — the cross-surface ladder:**

| Concern | Grounded state | This spec |
|---|---|---|
| Cross-DOMAIN cascade (lift a taxonomy to a shared owner) | **built** — `view_definition.py:139-176,295-546` | reuse (the mechanism) |
| Projection to the renderer (byte-identity seam) | **built** — `view_definition.py:224-285` | reuse (empty-default guard) |
| One canonical node STATE presented per SURFACE | **absent** — vocabulary is domain-shaped, no surface dimension | **FR-1 (base `node_state`)** |
| navig8r vocabulary projected FROM the shared state, byte-identical | must hold | **FR-2 (presentation mapping · navig8r)** |
| cockpit readiness vocabulary projected FROM the same state | **absent** — `ok/review/blocked/activated` has no shared owner | **FR-3 (presentation mapping · cockpit)** |
| Drill binding (cockpit tile → navig8r node by `#key`) declared in the definition | **absent** — the `#key` route exists but no declared link | **FR-4 (drill binding, reuse route)** |
| Rollup binding (navig8r grounding → cockpit readiness) declared in the definition | **absent** — the rollup primitive exists but no declared link | **FR-5 (rollup binding, reuse composition)** |
| Corpus/surface-agnostic; twin of the composition primitive | the lift is definition-level | **FR-6** |
| navig8r render + cockpit + app-scaffold byte-identical | must hold | **FR-7 (byte-identity guard)** |

---

## 0.1 Planning Insights (Self-Reflective Update)

> What grounding against the real View Definition + cockpit code changed, versus the naïve "merge the two surfaces'
> vocabularies" framing. Bound directly to `view_definition.py`, `portal_spec.py`, `activation.py`,
> `wireframe_view/_template.py`, `graph_projection.py`, and the strategy + PM findings notes.

| Naïve v0.1 Assumption | Grounding Discovery (file:line) | Impact |
|-----------------------|---------------------------------|--------|
| The View Definition needs a new "surface" cascade to carry two surfaces | `view_definition.py:139-176` `resolve` already flattens an `extends` chain with keyed-collection-merge-by-id, and the base already owns shared sections (`control`/`regions`/`theme`) every domain inherits. A shared `node_state` section on the base is just one more inherited keyed map | **No new cascade.** FR-1 adds a `node_state` section to `BASE_NAVIG8R_DEFINITION`; it inherits like `control`/`regions` do |
| The navig8r's `grounded/spec/awaiting` and the cockpit's `ok/review/blocked` are two different taxonomies to reconcile | They are two PRESENTATIONS of the same node health at two altitudes (`STRATEGY…` §0): navig8r = technical grounding, cockpit = readiness. The states line up (`grounded`↔`ok`, `spec/awaiting`↔`review`, gap↔`blocked`) | **One canonical state, two presentation maps** (FR-2/FR-3), not a merge. The canonical `node_state` is neutral; each surface names + colours it |
| Projecting a shared state will recolour today's navig8r render | `to_render_profile` (`view_definition.py:224-285`) reads `vocabulary.statuses` into `StatusStyle`; the requirements statuses at `:398-407` are the renderer's ACTUAL values. If the navig8r presentation map PROJECTS to exactly those (empty-default falls back to the current `vocabulary`), the render is byte-identical | **FR-2 is a byte-identity projection** — the shared state maps to today's `grounded/spec/awaiting/excluded/unknown` with the same `color`/`meaning`/`severity`, guarded by `test_no_profile_is_byte_identical` |
| A drill (cockpit→navig8r) needs a new route / deep-link machinery | `wireframe_view/_template.py:900,923,1402` already implement the `#<key>` full-page route (`buildFullView` + `resolveHash` on `hashchange`), registered as the `fullview` region (`view_definition.py:382`) | **FR-4 is a declared pointer** at the existing route — the drill binding names the target surface + the `#<key>` template; no route code changes |
| A rollup (navig8r→cockpit) needs a new aggregation engine | `REQ-feature-capability-composition-rollup` draws a ground-up rollup via the target-generic `serves` edge (`graph_projection.py:181-182`), no new edge kind | **FR-5 reuses that rollup primitive** as a declared binding (navig8r node grounding → the cockpit readiness state it rolls up to); no new aggregation |
| The cockpit must be rebuilt to read the shared definition | The cockpit derives attention ONCE (`portal_spec.py:29-30`) and its display map is a module constant (`:31-37`). The binding is ADDITIVE: the cockpit can consume the shared presentation map, but its current derivation is untouched (byte-identical) until a consumer opts in | **FR-3/FR-7 keep the cockpit byte-identical** — the cockpit presentation map is DECLARED in the definition (available to consumers) without mutating the cockpit's current rendering |

**Resolved open questions:**

- **OQ-1 (a new `node_state` section, or overload `vocabulary`?) → a new base `node_state` section that `vocabulary` PROJECTS from.** `vocabulary.statuses` is per-domain and per-surface-navig8r-flavored already (`view_definition.py:398-407`); the canonical cross-surface state must be surface-neutral, so it is a distinct base section (`node_state`) carrying the canonical states, and each surface's vocabulary (navig8r `vocabulary.statuses`, cockpit readiness map) is a **presentation projection** of it. This keeps `vocabulary` byte-identical when a domain doesn't opt in (empty-default guard).
- **OQ-2 (how do the two presentation vocabularies line up onto one canonical state?) → a canonical state set with a per-surface `presentation` map keyed by surface.** Canonical states (surface-neutral ids, e.g. `grounded`/`speculative`/`awaiting`/`excluded`/`unknown`), each with `{navig8r: {label, color, meaning, severity, is_gap}, cockpit: {label, color, attention}}`. navig8r projects the `navig8r` leaf to today's statuses byte-for-byte; cockpit projects the `cockpit` leaf to `ok/review/blocked/backlog` (`portal_spec.py:31-37`). The alignment (`grounded↔ok`, `speculative/awaiting↔review`, gap↔`blocked`) is declared ONCE in the map, not re-guessed per surface.
- **OQ-3 (does the cockpit's `activated` severity fit?) → `activated` is a project-level roll-up state, carried as an optional canonical state, not a per-node one.** `activation.py:63-64` treats `activated` as the ok/attention/blocked project verdict (`0=ok/activated`). It rolls up the per-node cockpit states, so the presentation map carries it as the rollup target of the rollup binding (FR-5), keeping per-node states = `ok/review/blocked/backlog`.
- **OQ-4 (where are the bindings declared — a new section or reuse `chrome.bindings`?) → a new `surface_links` section (drill + rollup), distinct from `chrome.bindings`.** `chrome.bindings` is single-field `{field}` string substitution for masthead chrome (`view_definition.py:429-434`, REQ-12) — a different grammar. A surface link is a typed pointer `{from_surface, to_surface, relation: drill|rollup, route|primitive}`, so it is its own base section, resolved by the same cascade (keyed map, merge-by-id) but consumed separately.
- **OQ-5 (does the drill binding hardcode the `#key` route or reference it?) → it references the registered `fullview` region (`view_definition.py:382`), not a literal.** The `#<key>` route is already a registered region binding; the drill binding names `to_surface: navig8r, via: fullview` so the route lives in ONE place (the region binding), and the drill is a pointer to it — no second literal to drift.
- **OQ-6 (does this touch the cockpit's rendering code?) → no; the cockpit binding is declared-and-available, additive, opt-in.** FR-3 puts the cockpit presentation map IN the definition; the cockpit's existing `_ATTENTION_DISPLAY` derivation (`portal_spec.py:31-37`) is untouched (byte-identical) so nothing regresses. Wiring a cockpit consumer to READ the shared map is out of scope (a downstream adopter step), keeping this spec a definition-only change.

---

## 0.2 Lessons-Learned & Design-Principle Hardening

> Consulted `docs/NAMING_CONVENTION.md`, the SDK `docs/design-princples/` (SOTTO/Mottainai/HAYAI), REQ-10's cascade pattern, the composition primitive REQ, the strategy note, and the PM findings note. Applied:

- **[Mottainai — reuse over new]** — Dominated by reuse: the cascade `resolve`/`to_render_profile` (`view_definition.py:139-285`), the `#<key>` route (`wireframe_view/_template.py:900,923`), and the composition rollup edge (`graph_projection.py:181-182`) are all reused. The only genuinely-new code is a base `node_state` section + a per-surface presentation projection (FR-1/FR-2/FR-3) and two declarative bindings (FR-4/FR-5) — data on the existing cascade, not machinery.
- **[Genchi Genbutsu]** — Bound to the real code before specifying: confirmed the cascade lifts a taxonomy to a shared owner across DOMAINS (`view_definition.py:295-546`), the requirements statuses are the renderer's actual values (`:398-407`), the projection seam is `to_render_profile` (`:224-285`), the cockpit taxonomy is a shared-once module map (`portal_spec.py:31-37`) + activation severity (`activation.py:56-64`), and the `#key` route + rollup edge already exist. No guessing.
- **[Shadow-taxonomy avoidance / single authority]** — The canonical node state is defined ONCE in the base `node_state` section; the navig8r↔cockpit alignment (`grounded↔ok`, etc.) is declared ONCE in the presentation map, not re-guessed by substring predicates scattered across two surfaces' renderers. This *removes* a latent shadow taxonomy (two surfaces independently classifying the same health).
- **[SOTTO / byte-identity]** — The navig8r vocabulary PROJECTS to today's `grounded/spec/awaiting/excluded/unknown` byte-for-byte (empty-default guard, `test_no_profile_is_byte_identical`); the cockpit binding is additive and does not touch `portal_spec.py`'s derivation; the app-scaffold path is byte-identical (FR-7).
- **[Accidental-Complexity anti-principle]** — Rejected a new cascade dimension, a surface-merge, a cockpit rebuild, and a new renderer. The lift is a section + a projection + two typed pointers on the EXISTING cascade (NR-1..NR-5).
- **[Two-sided coin / value lineage]** — This is the surface-level realization of the coin (`STRATEGY…` §0) and Move 1's hub twin: one shared vocabulary + drill/rollup so an insight validated on the technical side (navig8r grounding) flows to the value side (cockpit readiness) and back — the PM findings' *"the missing edge is what would join the two validation sides"* (`PM_FINDINGS…` §4.3), applied at the surface layer.
- **[Naming]** — `node_state`, `presentation`, `surface_links`, `drill`, `rollup`, `via: fullview` are descriptive; every FR carries a `Name:` (actor·action·object·outcome). No bare `type+integer` identity.

---

## Overview

A **cross-surface** extension of the navig8r View Definition: lift the node-state taxonomy from a per-domain
vocabulary to a **shared cross-SURFACE owner**, with a per-surface presentation mapping so the navig8r
(`grounded/spec/awaiting`) and the cockpit (`ok/review/blocked/activated`) render the **same** node health as
**one canonical state, two presentations**; and declare the two cross-surface relationships — a **drill binding**
(cockpit tile → navig8r node by the existing `#<key>` route) and a **rollup binding** (navig8r grounding → cockpit
readiness, reusing the composition primitive's `serves` rollup) — **in the definition**, not as bespoke per-surface
glue. Grounding proved this is mostly *reuse*: the cascade already lifts a taxonomy to a shared owner across DOMAINS
(`view_definition.py:139-176,295-546`), the projection seam is `to_render_profile` (`:224-285`), the `#key` route
exists (`wireframe_view/_template.py:900,923`), and the rollup edge exists (`graph_projection.py:181-182`). This spec
therefore: (1) adds a base `node_state` section owning the canonical cross-surface states (FR-1); (2) projects the
navig8r presentation byte-for-byte from it (FR-2); (3) declares the cockpit readiness presentation from the same
state (FR-3); (4) declares a drill binding referencing the existing `fullview` region (FR-4); (5) declares a rollup
binding reusing the composition primitive (FR-5); (6) makes it a corpus/surface-agnostic definition-level primitive,
the surface twin of the composition edge (FR-6); and (7) keeps the navig8r render, the cockpit, and the app-scaffold
path byte-identical (FR-7).

**Adopters this unblocks:**

| Adopter | What they get | Key FR |
|---|---|---|
| requirements-viz + kickoff self-use | One node health rendered consistently on both surfaces; a cockpit readiness tile drills to the navig8r node; navig8r grounding rolls up to cockpit readiness | FR-1, FR-4, FR-5 |
| STRATEGY Move 1 (the hub) | The surface-level cross-links (drill/rollup) as declared data — the hub pivot expressed in the definition, not per-surface glue | FR-4, FR-5 |
| cross-repo NODE-SCHEMA adopters (dev-os / benchmark / legal) | A surface-agnostic node-state taxonomy + drill/rollup any two surfaces over the same state can share | FR-1, FR-6 |

---

## Objectives

- O-1: The View Definition owns a single **canonical node-state taxonomy** (a base `node_state` section) that is the shared cross-SURFACE authority — inherited by domains through the existing cascade, so one node state is defined ONCE, not re-declared per surface.
- O-2: The navig8r surface renders its status vocabulary **projected from the shared canonical state**, byte-for-byte identical to today's `grounded/spec/awaiting/excluded/unknown` (the shared taxonomy projects to the current render, empty-default guard).
- O-3: The cockpit readiness vocabulary (`ok/review/blocked/backlog`, with the `activated` roll-up) is **declared as a per-surface presentation of the same canonical state**, so both surfaces present the SAME node health with two vocabularies owned in one place.
- O-4: A **drill binding** (cockpit tile → navig8r node) is declared in the definition, **reusing the existing `#<key>` full-page route** via the registered `fullview` region — no bespoke per-surface deep-link glue.
- O-5: A **rollup binding** (navig8r node grounding → cockpit readiness) is declared in the definition, **reusing the composition primitive's `serves` rollup** — no new aggregation engine.
- O-6: The cross-surface taxonomy + drill/rollup are a **corpus/surface-agnostic definition-level primitive** (the surface twin of the feature→capability composition edge), applicable to any two surfaces over the same NODE-SCHEMA state.
- O-7: The navig8r render, the cockpit's current rendering, and the app-scaffold path are **byte-identical**; the `node_state` section, the cockpit presentation, and both bindings are strictly additive.

---

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | The navig8r presentation projected from the shared `node_state` recolours/relabels today's render (a shared-owner change that alters `grounded/spec/awaiting/excluded/unknown`) | FR-2 Verify: the navig8r presentation projects to exactly the current `vocabulary.statuses` values (`view_definition.py:398-407`); `test_no_profile_is_byte_identical` passes unedited; a REQUIREMENTS render diff is empty | high |
| architecture | The two surfaces' states are aligned by scattered substring predicates in two renderers (a shadow taxonomy re-guessing `grounded↔ok`) | FR-1/FR-3: the alignment is declared ONCE in the `node_state` presentation map; downstream reads a leaf, never re-classifies. FR-6 Verify asserts no per-surface re-classification predicate | high |
| architecture | The cockpit binding mutates the cockpit's rendering (`portal_spec.py` derivation) and regresses it | FR-3/FR-7: the cockpit presentation is DECLARED in the definition (available, opt-in); `portal_spec.py:31-37` `_ATTENTION_DISPLAY` derivation is untouched (byte-identical); a cockpit consumer wiring is out of scope | high |
| quality | The drill binding hardcodes the `#<key>` route literal and drifts from the registered `fullview` region | FR-4/OQ-5: the drill binding references `via: fullview` (the registered region `view_definition.py:382`), not a route literal — one home for the route | medium |
| scope-creep | Building a new cascade dimension or a surface-merge instead of one shared section on the existing cascade | NR-1/NR-2/FR-1: `node_state` is one more inherited base section resolved by the existing `resolve`; no new cascade, no merge | medium |
| architecture | The rollup binding reinvents aggregation instead of reusing the composition `serves` rollup | NR-4/FR-5: the rollup binding references the composition primitive's rollup direction (`graph_projection.py:181-182`); no new edge kind or aggregation engine | medium |
| quality | A domain that doesn't opt into `node_state` loses its `vocabulary` (an empty-default that erases the current statuses) | FR-2/FR-7: the projection falls back to the domain's existing `vocabulary.statuses` when `node_state` is absent (empty-default guard), so non-opting domains are byte-identical | medium |
| coupling | The `surface_links` bindings collide with `chrome.bindings` (the `{field}` substitution grammar) | NR-5/OQ-4: `surface_links` is a distinct base section with a typed pointer shape (`relation`/`via`), consumed separately from `chrome.bindings` — no grammar overload | low |

---

## Profile

Declared profile: **internal** (consumers are SDK contributors, the requirements-viz + kickoff self-use, STRATEGY Move 1, and cross-repo NODE-SCHEMA adopters — not end-users directly).

---

## Functional requirements

- **FR-1 — Shared canonical node-state taxonomy as a base `node_state` section.** A new `node_state` section on `BASE_NAVIG8R_DEFINITION` owns the canonical, surface-neutral node states (each with a per-surface `presentation` map keyed by surface: `navig8r` / `cockpit`), lifted from the requirements status vocabulary, inherited by every domain through the existing `resolve` cascade like `control`/`regions` are. Name: The View Definition owns one canonical cross-surface node-state taxonomy in a base section that every domain inherits through the existing cascade. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_node_state_taxonomy.py`. Verify: (a) `resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY).node_state` is non-empty and carries the canonical states each with `presentation.navig8r` and `presentation.cockpit` leaves; (b) a domain overriding one canonical state's `presentation.cockpit` keeps its siblings via keyed-collection-merge-by-id (`view_definition.py:61-73`); (c) `node_state` is added to `_SECTIONS` (`view_definition.py:44-45`) and round-trips through `to_dict`/`from_dict`. Serves: O-1

- **FR-2 — navig8r presentation projects to today's statuses byte-for-byte.** The navig8r surface's `vocabulary.statuses` are projected from `node_state`'s `presentation.navig8r` leaves so `to_render_profile` produces exactly today's `grounded/spec/awaiting/excluded/unknown` `StatusStyle` tuples (same `label`/`color`/`meaning`/`severity`/`is_gap`), with an empty-default fallback to the domain's existing `vocabulary.statuses` when `node_state` is absent. Name: The navigator projects its status vocabulary from the shared canonical state so the current render is byte-identical while sharing the taxonomy. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_node_state_projection.py`. Verify: (a) `to_render_profile(resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY)).statuses` equals the current tuple set (`grounded`#3d7a57 · `spec`#6b6252 · `awaiting`#a9781a is_gap · `excluded`#948b78 · `unknown`#ab473a is_gap) exactly; (b) `test_no_profile_is_byte_identical` passes unedited; (c) a domain with no `node_state` opt-in renders byte-identical to before (empty-default fallback). Serves: O-2

- **FR-3 — Cockpit readiness presentation declared from the same canonical state.** The cockpit readiness vocabulary (`ok/review/blocked/backlog` per `portal_spec.py:31-37`) is declared as the `presentation.cockpit` leaf of the same canonical states, so the shared taxonomy owns both surfaces' vocabularies in one place, aligned once (`grounded↔ok`, `speculative`/`awaiting↔review`, gap↔`blocked`), and the cockpit's existing derivation is untouched. Name: The View Definition declares the cockpit readiness vocabulary as a presentation of the same canonical node state so both surfaces present one health from one owner. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_cockpit_presentation.py`. Verify: (a) each canonical node state's `presentation.cockpit` maps to one of `ok`/`review`/`blocked`/`backlog` and the alignment set matches the cockpit's `_ATTENTION_DISPLAY` keys (`portal_spec.py:31-37`); (b) resolving the shared taxonomy yields a `{canonical_state -> {navig8r_label, cockpit_label}}` map for the same state (e.g. `grounded → (Grounded, ok)`); (c) `src/startd8/kickoff_experience/portal_spec.py` has no diff (the cockpit derivation is untouched — the presentation is declared, opt-in). Serves: O-3

- **FR-4 — Drill binding (cockpit tile → navig8r node) declared via the existing `#<key>` route.** A `surface_links` base section carries a `drill` binding `{from_surface: cockpit, to_surface: navig8r, relation: drill, via: fullview}` referencing the registered `fullview` region (`view_definition.py:382`) — the existing `#<key>` full-page route (`wireframe_view/_template.py:900,923,1402`) — so a cockpit tile can address a navig8r node by key with no bespoke deep-link glue. Name: The View Definition declares a drill binding from a cockpit tile to a navigator node by key, reusing the existing full-page route rather than new glue. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_surface_links.py`. Verify: (a) `resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY).surface_links["drill"]` has `to_surface == "navig8r"`, `relation == "drill"`, and `via == "fullview"`; (b) the referenced region `fullview` exists in the resolved `regions.bindings` (`view_definition.py:382`) — the drill points at the registered route, not a literal; (c) the binding is a data pointer only — `grep` shows no new route/handler code added to `wireframe_view/_template.py`. Serves: O-4

- **FR-5 — Rollup binding (navig8r grounding → cockpit readiness) declared via the composition primitive.** The `surface_links` section carries a `rollup` binding `{from_surface: navig8r, to_surface: cockpit, relation: rollup, via: serves}` referencing the composition primitive's `serves` rollup (`graph_projection.py:181-182`, `REQ-feature-capability-composition-rollup` FR-3) so navig8r node grounding rolls up into cockpit readiness (per-node states → the `activated` project verdict) with no new aggregation engine. Name: The View Definition declares a rollup binding from navigator grounding to cockpit readiness, reusing the composition serves-rollup primitive rather than a new aggregator. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_surface_links.py`. Verify: (a) `resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY).surface_links["rollup"]` has `from_surface == "navig8r"`, `to_surface == "cockpit"`, `relation == "rollup"`, and `via == "serves"`; (b) the binding references the `serves` primitive by name (not a new edge kind) — `grep -c "new edge kind\|rollup-edge" src/startd8/navigator/graph_projection.py` is 0; (c) the rollup target (`activated`) is present in the canonical `node_state` as the project-level roll-up state (OQ-3). Serves: O-5

- **FR-6 — Corpus/surface-agnostic primitive, the surface twin of the composition edge.** The cross-surface taxonomy + `surface_links` live at the View Definition (definition) level — surface-neutral canonical states + typed surface pointers — so they apply to any two surfaces over the same NODE-SCHEMA state, and the spec/appendix names this the surface-level twin of the feature→capability composition edge (`REQ-feature-capability-composition-rollup`) and STRATEGY Move 1. Name: The navigator establishes the cross-surface taxonomy and drill/rollup as a corpus-agnostic definition-level primitive that is the surface twin of the composition edge. Touches: `src/startd8/navigator/view_definition.py`, `docs/design/requirements-visualization/REQ-cross-surface-view-definition.md`. Verify: (a) the `node_state` + `surface_links` sections carry no surface-specific renderer imports and no per-surface substring re-classification (the alignment is one declared map, FR-1/FR-3) — a non-requirements domain (e.g. `CAPABILITY_DEFINITION`) can carry the same sections unchanged; (b) this doc's Appendix C cross-references `REQ-feature-capability-composition-rollup.md` (the DOMAIN/value-lineage twin) and `STRATEGY_navig8r-inflection-two-sided-validation.md` §2 Move 1 (the hub). Serves: O-6

- **FR-7 — navig8r render, cockpit, and app-scaffold byte-identical.** The navig8r render (via `to_render_profile`), the cockpit's current rendering (`portal_spec.py` derivation), and the deterministic app-scaffold path are byte-identical; the `node_state` section, the cockpit presentation declaration, and both `surface_links` bindings are strictly additive (empty-default guards throughout). Name: The navigator keeps the navig8r render, the cockpit, and the app-scaffold byte-identical so the cross-surface taxonomy and bindings are strictly additive. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_view_definition.py`, `tests/unit/kickoff/test_portal_spec.py`. Verify: (a) `test_no_profile_is_byte_identical` and the existing `view_definition` unit suite pass without edits; (b) the REQUIREMENTS/CAPABILITY/node-schema/pipeline resolved renders are unchanged; (c) `src/startd8/kickoff_experience/portal_spec.py` and the app-scaffold wireframe byte-identity test have no diff. Serves: O-7

---

## Non-goals

- NR-1: A new cascade dimension or a second resolver for surfaces. `node_state` and `surface_links` are ordinary base sections resolved by the existing `resolve` / `_deep_merge` (`view_definition.py:139-176,61-73`); no surface-specific cascade (FR-1).
- NR-2: Merging the two surfaces. The cockpit and the navig8r stay distinct surfaces at distinct altitudes; this spec shares only the taxonomy + declares the cross-links (FR-3/FR-4/FR-5, STRATEGY §0).
- NR-3: Rebuilding or re-rendering the cockpit. The cockpit's `_ATTENTION_DISPLAY` derivation (`portal_spec.py:31-37`) is untouched; the cockpit presentation is DECLARED in the definition (opt-in), not wired into the cockpit's rendering here (FR-3, OQ-6).
- NR-4: A new rollup/aggregation engine or a new edge kind. The rollup binding references the composition primitive's `serves` rollup (`graph_projection.py:181-182`); no `rollup`/`drill` edge label is added (FR-5).
- NR-5: Overloading `chrome.bindings`. `surface_links` is a distinct typed section (`relation`/`via`); it does not extend the `{field}` masthead-substitution grammar (`view_definition.py:429-434`, OQ-4).
- NR-6: A new HTML renderer or a new `#key`-style route. The drill binding reuses the registered `fullview` region / existing route (`wireframe_view/_template.py:900,923`); no route code (FR-4).
- NR-7: Wiring a live cockpit consumer to READ the shared presentation map. That is a downstream adopter step (a separate delivery); this spec makes the shared owner + bindings available, definition-only (FR-3, OQ-6).
- NR-8: An LLM step. The section, the projection, and the bindings are all deterministic, offline, `$0` — consistent with the whole navigator + kickoff family.

---

## Owned fields

Only humans/authors control: the canonical `node_state` states + their per-surface `presentation` leaves (the
navig8r label/color/meaning/severity + the cockpit label/attention); the `surface_links` `drill`/`rollup` bindings
(`from_surface`/`to_surface`/`relation`/`via`); a domain's optional `node_state`/`surface_links` overrides (via the
keyed cascade); `--source`/`--renderer` selection (unchanged). The alignment map (which canonical state presents as
which navig8r status and which cockpit readiness state) is author-owned, declared once in `node_state`.

---

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §8 `python-cli-surface` · living homes `~/Documents/dev/startd8-sdk/pyproject.toml`, `~/Documents/dev/startd8-sdk/src/startd8/navigator/view_definition.py` · grammar cite `~/Documents/dev/dev-os/NODE-SCHEMA.md` · reuse sources `src/startd8/navigator/view_definition.py:139-176` (`resolve` cascade), `:224-285` (`to_render_profile` projection seam), `:295-390` (`BASE_NAVIG8R_DEFINITION`), `:398-407` (requirements statuses — the taxonomy to lift), `:382` (`fullview` region — the drill target), `src/startd8/kickoff_experience/portal_spec.py:31-37` (cockpit `_ATTENTION_DISPLAY`), `src/startd8/kickoff_experience/activation.py:56-64` (`activated`/severity), `src/startd8/wireframe_view/_template.py:900,923,1402` (the `#<key>` route), `src/startd8/navigator/graph_projection.py:181-182` (the `serves` rollup edge)

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| navigator-build | command | structure | existing (REQ-02/05/10); the resolved definition now carries `node_state` + `surface_links` |
| node-state-section | section | structure | base `node_state` — canonical cross-surface states + per-surface `presentation` (new — FR-1) |
| presentation-navig8r | field | words | `node_state[*].presentation.navig8r` — projects to today's `vocabulary.statuses` byte-for-byte (FR-2) |
| presentation-cockpit | field | words | `node_state[*].presentation.cockpit` — the cockpit readiness vocabulary, declared (FR-3) |
| surface-links-section | section | structure | base `surface_links` — `drill` + `rollup` typed bindings (new — FR-4/FR-5) |
| drill-binding | field | structure | `surface_links.drill` — `{from_surface, to_surface, relation: drill, via: fullview}` (FR-4) |
| rollup-binding | field | structure | `surface_links.rollup` — `{from_surface, to_surface, relation: rollup, via: serves}` (FR-5) |
| exit-navigator | exit-class | structure | 0 = wrote artifact / clean resolve; non-zero = resolve/IO/validation failure |

Library seams (not CLI kinds — cite as Touches file paths):
- `src/startd8/navigator/view_definition.py` (`node_state` + `surface_links` added to `_SECTIONS`, the base definition, and the projection — FR-1/FR-2/FR-3/FR-4/FR-5)
- `src/startd8/kickoff_experience/portal_spec.py` (read-only reference for the cockpit vocabulary; untouched — FR-3/FR-7)
- `src/startd8/kickoff_experience/activation.py` (read-only reference for the `activated` roll-up state — FR-5)
- `src/startd8/wireframe_view/_template.py` (the `#<key>` route reused by the drill binding; untouched — FR-4)
- `src/startd8/navigator/graph_projection.py` (the `serves` rollup reused by the rollup binding; untouched — FR-5)
- `tests/unit/navigator/test_node_state_taxonomy.py`, `test_node_state_projection.py`, `test_cockpit_presentation.py`, `test_surface_links.py` (to-be-created)

---

## Iterations

> Acyclic delivery order — each stage depends only on the prior. Matches the reuse cascade
> (shared state → navig8r projection → cockpit presentation → drill → rollup → surface-agnostic).

| # | Iteration | FRs | Depends on | Rationale |
|---|-----------|-----|-----------|-----------|
| 1 | **Shared state** — base `node_state` section on the cascade | FR-1 | — | The shared owner; canonical states + per-surface `presentation`, inherited like `control`/`regions`. |
| 2 | **navig8r projection** — statuses byte-for-byte from `node_state` | FR-2 | FR-1 | The byte-identity anchor; the shared state projects to today's render. |
| 3 | **cockpit presentation** — readiness vocabulary declared from the same state | FR-3 | FR-1 | Both surfaces' vocabularies owned in one place; cockpit derivation untouched. |
| 4 | **drill binding** — cockpit tile → navig8r node via `fullview` | FR-4 | FR-1 | Declared pointer at the existing `#<key>` route; no glue. |
| 5 | **rollup binding** — navig8r grounding → cockpit readiness via `serves` | FR-5 | FR-1, FR-3 | Reuses the composition rollup; per-node states → `activated`. |
| 6 | **surface-agnostic** — definition-level primitive, twin of composition | FR-6 | FR-1, FR-4, FR-5 | Prove neutrality (a non-requirements domain carries the sections); name the twins. |
| — | **Byte-identity guard** (cross-cutting) | FR-7 | all | navig8r + cockpit + app-scaffold unchanged; strictly additive. |

---

## Dependencies

- **REQ-10** (view-definition cascade) — supplies `ViewDefinition`/`ResolvedDefinition`, `resolve`, `to_render_profile`, `BASE_NAVIG8R_DEFINITION`, the `_SECTIONS` list, and the requirements status vocabulary this lifts. **Built (`view_definition.py` in-tree).**
- **REQ-feature-capability-composition-rollup** — the composition primitive whose `serves` rollup (`graph_projection.py:181-182`) the rollup binding reuses; the DOMAIN/value-lineage twin of this surface-level spec. **Spec (BUILD-READY).**
- **STRATEGY_navig8r-inflection-two-sided-validation** — Move 1 (the hub / topology cross-links) this is the surface-level twin of; the two-sided-coin frame (§0) the whole spec serves. **Direction of record.**
- **Cockpit (kickoff_experience)** — supplies the readiness vocabulary (`portal_spec.py:31-37`) + the `activated` roll-up (`activation.py:56-64`) the cockpit presentation is declared from; untouched here. **Built.**
- **The `#<key>` full-page route** (`wireframe_view/_template.py:900,923,1402`) — the drill target the drill binding references. **Built.**

---

## Appendix A — Accepted (with where merged)

*(empty at v0.1 — no CRP review run yet)*

## Appendix B — Rejected (with rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| — | Add a new "surface" cascade dimension / a second resolver | v0.1 draft | The existing `resolve` already inherits base sections across domains; `node_state`/`surface_links` are ordinary base sections. A second cascade is accidental complexity. NR-1, FR-1. | 2026-08-17 |
| — | Merge the cockpit and navig8r into one surface/vocabulary | v0.1 draft | The two surfaces are distinct altitudes of the two-sided coin (STRATEGY §0); merging erases the value/technical split. Share the taxonomy + declare cross-links only. NR-2. | 2026-08-17 |
| — | Rebuild the cockpit to read the shared definition | v0.1 draft | The cockpit derivation (`portal_spec.py:31-37`) is untouched; the presentation is DECLARED (opt-in). A rebuild breaks byte-identity and over-scopes. NR-3, FR-3, FR-7, OQ-6. | 2026-08-17 |
| — | Add a new `drill`/`rollup` edge kind or a new aggregation engine | v0.1 draft | The `#key` route and the `serves` rollup already exist; the bindings are declared pointers at them. A new edge/engine is a Mottainai violation. NR-4, NR-6, FR-4, FR-5. | 2026-08-17 |
| — | Declare the surface links inside `chrome.bindings` | v0.1 draft | `chrome.bindings` is single-`{field}` masthead substitution (REQ-12) — a different grammar. A surface link is a typed pointer; overloading forks the grammar. NR-5, OQ-4. | 2026-08-17 |

## Appendix C — Incoming review rounds

*(ready for CRP)*

**Cross-surface / cross-domain twins:** this spec is the **surface-level** twin of the DOMAIN-level composition
primitive [`REQ-feature-capability-composition-rollup.md`](./REQ-feature-capability-composition-rollup.md) — the
composition edge lifts a *value-lineage relation between nodes* (feature→capability), this lifts the *node-state
vocabulary + the drill/rollup cross-links between two SURFACES over those nodes*. Both realize the same PM-findings
insight — *"the missing edge is what would join the two validation sides"*
([`PM_FINDINGS_contextcore-o11y-value-lineage.md`](./PM_FINDINGS_contextcore-o11y-value-lineage.md) §4.3) — and both
serve the **two-sided coin** ([`STRATEGY_navig8r-inflection-two-sided-validation.md`](./STRATEGY_navig8r-inflection-two-sided-validation.md)
§0). This spec is specifically the surface-level expression of **Move 1 (the hub)** (STRATEGY §2): the drill/rollup
cross-links declared as data in the View Definition rather than bespoke per-surface glue.

---

*v0.1 — A cross-SURFACE extension of the View Definition. Grounded as **mostly reuse (Mottainai)**: the cascade
already lifts a taxonomy to a shared owner across DOMAINS (`view_definition.py:139-176,295-546`), the projection seam
is `to_render_profile` (`:224-285`), the `#<key>` route exists (`wireframe_view/_template.py:900,923`), and the
`serves` rollup exists (`graph_projection.py:181-182`). FR-1 adds a base `node_state` section (one canonical state,
per-surface `presentation`); FR-2 projects the navig8r vocabulary byte-for-byte; FR-3 declares the cockpit readiness
presentation from the same state; FR-4 declares a drill binding reusing the `fullview` route; FR-5 declares a rollup
binding reusing the composition `serves` rollup; FR-6 makes it a corpus/surface-agnostic definition-level primitive
(the surface twin of the composition edge); FR-7 keeps the navig8r render, the cockpit, and the app-scaffold
byte-identical. Ready for CRP review.*
