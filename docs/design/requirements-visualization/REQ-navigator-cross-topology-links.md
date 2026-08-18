# Cross-topology links from the requirement full-page view (Move 1) — Requirements

**Project:** startd8-sdk (requirements visualization ladder) · **Criticality:** low
**Version:** 0.2 (post-planning — right-sized against the landed renderers)   **Date:** 2026-08-18
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** the profiled navigator full-page route (`src/startd8/wireframe_view/_template.py` `buildFullView`) · `STRATEGY_navig8r-inflection-two-sided-validation.md` §Move 1
**Inherits standards:** det-req-kit · NODE-SCHEMA · NAMING_CONVENTION · SOTTO_DESIGN_PRINCIPLE · the-verify-liveness-value-prop (no dead links)
**Audience:** operator / requirement reader
**Trust boundary:** local render only · no network · no LLM
**Data classification:** internal

> **DIDL identity (document):**
> - **Semantic name:** Let the navigator's full-page requirement view link the same requirement across the sibling topologies via authored per-topology URL templates, so an operator pivots from the card read to the graph, a11y, index or diff view of that exact requirement without a dead link
> - **Local key (initiative):** `FEAT-navigator-cross-topology-links`
> - **Canonical ref (planned):** `cc:intent:navig8r:interaction:cross-topology-links`
> - **Readable handle:** `feature/navigator-cross-topology-links`

---

## 0. Planning Insights (Self-Reflective Update)

> Move 1, specced reflectively against the LANDED renderers — and planning **right-sized it hard**. The
> strategy's picture ("each requirement's full-page view links to its graph node, its diff, its a11y leaf,
> its corpus-index row") is **not cleanly buildable today**, so v1 ships the authored, resolving,
> byte-identical SEAM and defers the auto-everywhere version behind a named prerequisite.

| v0.1 Assumption | Planning Discovery (grounded) | Impact |
|-----------------|-------------------------------|--------|
| The full-page view can auto-link to the same requirement in all 4 sibling topologies | Only **a11y** emits an anchor-navigable per-key id (`render_a11y.py:198` `id="{sid}"`). Graph has a non-navigable `data-id` (`render_graph.py:412`); **index/diff emit NO per-key anchor**. So an auto-generated `#<key>` link would be **DEAD** in 3 of 4 targets. | **FR-4/FR-5:** v1 does NOT fabricate links — it emits only **authored** per-topology URL templates (the operator supplies the sibling location + anchor that actually resolves). Uniform per-key anchors across renderers is the deferred prerequisite (FR-5). |
| The renderers share an output-filename convention to link between | Each writes to an arbitrary `out_path` (`render_graph.py:487`); there is **no** convention connecting the separate renders. | **FR-3:** the cross-link URL is author-supplied (`--cross-link <topology>=<url-template>`), not derived from a baked-in filename scheme. |
| Cross-links are "one more predicate on the visibility model" | They are chrome affordances on the full-page route (`buildFullView` `_template.py:955`), not per-card classes. | **FR-2:** the links render in the full-page view, additive; nothing touches the Move 3 visibility model. |
| The feature should be on by default | An empty/default render must stay byte-identical, and a link with no authored target would be dead (violates verify-liveness-not-presence). | **FR-1/FR-6:** opt-in — no `cross_links` ⇒ no row ⇒ byte-identical; only configured topologies render, so **no dead link is ever emitted**. |

**Resolved open questions:**
- **OQ-anchor → authored, not auto.** The navigator emits the operator's URL template verbatim (with `{key}` substituted); it never invents a sibling path/anchor, so it can't emit a link to a target that doesn't exist.
- **OQ-scope → the seam now, the anchor-uniformity later.** v1 = the full-page cross-link affordance + the CLI to author it (resolves against a11y today). Making index/graph/diff each emit a stable per-key `id="<key>"` is the follow-on that lets an operator wire all four.

---

## Overview

The navigator's six renderers are chosen upfront by a `--renderer` flag with **zero cross-links** — a reader
on the card browse can't pivot to the same requirement's graph node or a11y leaf. This move adds, to the
full-page requirement view (the `#<key>` route built this session), a small **cross-topology link row**
driven by an **authored** per-topology URL-template map: `--cross-link graph=reqs.graph.html` →
`buildFullView` renders a link to `reqs.graph.html#<key>` for the shown requirement. Only configured
topologies render (so no dead link is ever emitted — the target's existence is the operator's assertion),
and absent any `--cross-link` the payload is unchanged and the app-scaffold render is byte-identical. It is
the *human/business-value navigation* side of the coin: read the requirement's value, then pivot to its
technical topology — from one entry point. The auto-link-everywhere vision is deferred behind a named
per-key-anchor prerequisite (§0).

## Objectives

- **O-1 — Pivot from the value read to the technical topology.** The full-page requirement view offers a link to the same requirement in each *configured* sibling topology, anchored on the existing `#<key>` route.
- **O-2 — No dead links.** A cross-link renders only for a topology the operator authored a URL for; the navigator never fabricates a sibling path/anchor, so it never emits a link to a target that may not exist (verify-liveness).
- **O-3 — Byte-identical + opt-in.** Absent `--cross-link` the payload and render are byte-identical; the whole feature is profiled-navigator-only.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| integrity | The navigator auto-generates a cross-link to a sibling anchor that doesn't exist (a dead link) | FR-4: only AUTHORED URL templates render; the navigator fabricates nothing — the operator asserts the target resolves | high |
| byte-identity | The cross-link machinery leaks onto the app-scaffold path | FR-6: opt-in + profile-gated; empty-default guard; `test_no_profile_is_byte_identical` | high |
| scope | Over-building the auto-everywhere version on renderers that lack anchors | FR-5: v1 = the authored seam; uniform per-key anchors is the deferred, named follow-on | medium |

## Profile

**internal** — a renderer-internal navigation affordance. No new NODE-SCHEMA field; one optional payload map
authored via a CLI flag. Reads the existing full-page `#<key>` route + the requirement's key.

## Functional Requirements

- **FR-1 — Opt-in cross-links map on the profiled payload.** `render_html` accepts an optional `cross_links` map (topology-id → URL template that may contain `{key}`), embedded into the payload ONLY when a profile is present AND the map is non-empty, so the app-scaffold payload is byte-identical. Name: The render embeds an optional cross-links topology-to-URL-template map only under a profile so the app path stays byte-identical. Touches: `src/startd8/wireframe_view/view.py`, `src/startd8/navigator/project.py`. Verify: `render_html(plan, profile=P, cross_links={"graph":"g.html#{key}"})` embeds `cross_links` in the payload; `render_html(plan)` and `render_html(plan, profile=P)` (no cross_links) embed none and are byte-identical. Serves: O-3
- **FR-2 — Cross-topology link row in the full-page view.** `buildFullView` renders a cross-topology "see this requirement in" row from `payload.cross_links`, one link per configured topology whose href is the URL template with `{key}` substituted by the shown requirement's key; absent `cross_links` it renders no row. Name: The full-page requirement view renders a cross-topology link row from the authored cross-links map substituting the requirement key. Touches: `src/startd8/wireframe_view/_template.py`. Verify: with `cross_links={"a11y":"r.a11y.html#{key}"}` the full-page view for key `FR-1` contains a link whose href is `r.a11y.html#FR-1`; with no `cross_links` the full-page view contains no cross-topology row. Serves: O-1
- **FR-3 — Author the links via the CLI.** `navigator build --cross-link <topology>=<url-template>` (repeatable) populates `cross_links`, threaded through `render_nodes_html`; the full-page `#<key>` route is the anchor the links target. Name: The navigator build command authors cross-links via a repeatable topology-equals-url-template option threaded to the render. Touches: `src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/project.py`. Verify: `startd8 navigator build --source requirements --renderer wireframe --cross-link graph=g.html#{key} --out o.html` writes an HTML whose full-page view links to `g.html#{key}`; omitting `--cross-link` leaves the output free of any cross-topology link. Serves: O-1
- **FR-4 — Never fabricate a link (no dead links).** The navigator emits only the operator's authored URL templates verbatim (with `{key}` substituted); it derives NO sibling filename or anchor on its own, so it can never emit a cross-link to a target it did not assert exists. Name: The navigator emits only authored URL templates and fabricates no sibling path or anchor so it never emits a dead cross-link. Touches: `src/startd8/wireframe_view/_template.py`, `src/startd8/navigator/cli_navigator.py`. Verify: no cross-link href appears for a topology the operator did not pass via `--cross-link`; the emitted href equals the authored template with only `{key}` substituted (no invented basename/anchor). Serves: O-2
- **FR-5 — Uniform per-key anchors are the deferred prerequisite.** v1 ships the authored cross-link seam only; making the sibling renderers (index/diff, and a navigable graph id) each emit a stable per-key `id="<key>"` anchor — so an operator can wire all four topologies and every link resolves — is a named follow-on, NOT this move. Name: v1 ships the authored cross-link seam and defers uniform per-key anchors across the sibling renderers as a named follow-on. Touches: `docs/design/requirements-visualization/REQ-navigator-cross-topology-links.md`. Verify: the spec records that only a11y resolves a per-key anchor today and names the per-key-`id` uniformity across index/diff/graph as the deferred prerequisite; v1 touches no sibling renderer. Serves: O-1
- **FR-6 — App-scaffold byte-identity.** With no `--cross-link` (and thus no `cross_links` in the payload) the whole feature is inert and the app-scaffold render emits not one changed byte. Name: The whole cross-link feature is opt-in and profile-gated so the app-scaffold render stays byte-identical. Touches: `src/startd8/wireframe_view/view.py`, `tests/unit/wireframe/test_render_profile.py`. Verify: `render_html(_plan()) == render_html(_plan(), profile=None)` (`test_no_profile_is_byte_identical`) stays green unedited. Serves: O-3

## Non-goals

- **NG-1 — No auto-cross-link to all topologies.** v1 does not generate links to renderers the operator didn't configure — 3 of 4 lack a resolving per-key anchor (§0); that is the deferred follow-on (FR-5).
- **NG-2 — No sibling-filename convention baked in.** The navigator does not assume `<base>.graph.html` etc.; URLs are author-supplied so they match whatever the operator actually generated.
- **NG-3 — No same-page topology rendering.** It links OUT to sibling renders; it does not embed a graph/a11y view inline in the card browse.
- **NG-4 — No new NODE-SCHEMA/payload field beyond the opt-in `cross_links` map.**

## Owned fields

No new NODE-SCHEMA field. It owns: the optional `cross_links` payload map, the `--cross-link` CLI option, and
the full-page view's cross-topology link row.

## Contract projection

- **Backend:** python-cli-surface — the profiled navigator HTML is emitted by `render_html`; the CLI is `navigator build`.
- **Vocabulary home (cite):** the full-page `#<key>` route (`_template.py` `buildFullView`/`resolveHash`); `docs/NAMING_CONVENTION.md`.

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| navigator-build | command | structure | gains `--cross-link` |
| cross-link | option | structure | `--cross-link <topology>=<url-template>` (repeatable) |
| cross-topology row | client render | structure | `buildFullView` renders authored links · `{key}`-substituted |
| byte-identity guard | test | structure | `test_no_profile_is_byte_identical` |

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

*v0.2 — reflective loop right-sized the ambitious "auto-link to all topologies" (3/4 siblings lack a
resolving anchor + no filename convention) down to an authored, resolving, byte-identical seam that resolves
against a11y today; uniform per-key anchors is the named deferred prerequisite. BUILD-READY.*
