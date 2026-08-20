# Cockpit Tiles Link to Navigator via surface_links — Requirements

**Project:** startd8-sdk   **Criticality:** medium
**Version:** 0.3.2   **Date:** 2026-08-20
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** `PLAN-cockpit-surface-links-adopter.md`
**Inherits standards:** det-req-kit · REQ-cross-surface-view-definition (the declared bindings this adopts) · NODE-SCHEMA v0.3.9
**Audience:** operator (SDK contributors; requirements-viz + kickoff self-use)
**Trust boundary:** local filesystem (kickoff state + View Definition dataclasses); no LLM, no network
**Data classification:** internal

> **Readable handle:** `feature/cockpit-surface-links-adopter`
> **Semantic name:** *Wire cockpit readiness tiles to link to the navigator node via the declared surface_links drill binding and resolve_surface_link_href*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:cockpit-surface-links-adopter`

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning).
> The planning pass revealed 4 corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| The cockpit tile renderer must import and call `resolve_surface_link_href` at render time | `resolve_surface_link_href(link, key)` is already shipped (`view_definition.py:288-297`) and returns `""` when `href` is absent. The cockpit renderer already has access to each field's `key` (it iterates the state's manifest fields). The wiring is a 3-line call in the per-field row renderer. | **FR-1 is trivially implementable** — the helper exists, takes `(link, key)`, returns `"#<key>"`. No new machinery. |
| The cockpit's Grafana board (`portal_spec_v2`) needs to carry the drill href | `portal_spec_v2.py` renders to Grafana JSON — Grafana text panels support markdown links. The v2 board builds field rows with attention badges. Adding a `[field →](#{key})` link is an in-line format insertion. | **FR-2 is cosmetic formatting** — the link is a markdown `[text](href)` in a text panel cell; `resolve_surface_link_href` gives the href. |
| The terminal cockpit view (`cockpit_view.py`) needs a visible link | `cockpit_view.py:39-45` renders only aggregate attention counts (`{ok} ok · {review} review · …`), NOT per-field rows. Rich `Text` does not support clickable hyperlinks. A per-field annotation is impossible without per-field rendering that doesn't exist. | **FR-3 DEFERRED** — the terminal view has no per-field rows to annotate. Requires a prerequisite (per-field terminal rendering) that is out of scope. |
| The web cockpit (`web.py`) needs a new route | The web front-end already serves the navig8r at its own route; the drill link is a relative `#<key>` anchor *into* the navig8r page. The web cockpit's overview can render an `<a href="/navigator#key">` as a standard link. `web.py` already has a `state.json` endpoint; no new route needed — just add an href attribute to the rendered field rows. | **FR-4 adds an anchor tag** — no new endpoint, no new route. |

**Resolved open questions:**

- **OQ-1 (where does the link appear — per-field or per-domain?) → per-field.** The drill binding is cockpit→navig8r at the NODE level, not the domain level. Each field in the cockpit IS a requirement node; the link lands on that node's `#<key>` full-page view.
- **OQ-2 (does the link always render or only on opt-in?) → always render when `surface_links.drill.href` is non-empty on the resolved definition.** The `resolve_surface_link_href` already returns `""` when no href; a falsy return → no link rendered. This is the empty-default pattern: definitions without a drill binding produce no link; no opt-in flag needed.
- **OQ-3 (which renderers are in scope?) → web (primary), Grafana v2 (additive), terminal (annotation only).** The web front-end is the live adopter; the Grafana v2 board adds markdown links; the terminal shows the `#key` for copy-paste. All three read the same resolved definition.

### 0.1 Lessons-Learned Hardening (v0.3)

> Checked SDK `docs/design-princples/` and the cross-surface retrospective findings. Applied:

- **[Phantom-reference audit]** — every code symbol this spec names (`resolve_surface_link_href`, `cockpit_statuses_from_node_state`, `BASE_NAVIG8R_DEFINITION.surface_links`, `_ATTENTION_DISPLAY`, `KickoffState.to_dict()`, `portal_spec_v2.build_workbook_v2`) greps live in `src/startd8/`. No phantom. See §Reference-Audit below.
- **[NR-7 ceiling (from RETROSPECTIVE)]** — this spec IS the "downstream adopter step" NR-7 explicitly scoped out. It consumes the declared bindings without re-declaring or modifying them. The parent REQ's `node_state`/`surface_links` are read-only inputs here.
- **[Single-source / no re-guess]** — the attention↔canonical alignment is NOT re-guessed. This spec reads `cockpit_statuses_from_node_state(resolved.node_state)` (the already-shipped projector, EC-CS-3) and `resolve_surface_link_href(link, key)` (EC-CS-4). No new mapping logic.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked the design-principle index. Applied:

- **[Mottainai]** — `resolve_surface_link_href` (`b346e612`), `cockpit_statuses_from_node_state` (`b346e612`), the resolved `surface_links.drill` data (`67051859`), the `#<key>` route (`wireframe_view/_template.py:900,923`) are ALL shipped bricks. This spec adds ~15 lines of rendering format (an `<a>` tag, a markdown link, a dim annotation) — no engine, no helper, no aggregator. Pure consumption.
- **[Genchi Genbutsu]** — grounded against the actual rendering code: `portal_spec_v2.py:100+` (builds field rows from state), `web.py:9` (overview lists fields + badges), `cockpit_view.py:39-45` (Rich body with attention counts), `portal_spec.py:32-37` (`_ATTENTION_DISPLAY` keys). The adopter adds links into the EXISTING render paths.
- **[SOTTO / byte-identity]** — the navig8r (`view_definition.py`, `wireframe_view/_template.py`) has NO diff. The cockpit rendering gets an ADDITIVE link (the field row gains an `href` that wasn't there); the app-scaffold path is unaffected (the scaffold has no kickoff rendering). Existing tests stay unedited. Adding a link to a field row is additive, not a mutation of the field's semantics.
- **[Kagami]** — edits target the SOURCE of rendering (the three cockpit renderers), never a derived/generated artifact. No `index.html`/generated-JSON is hand-edited.

---

## Overview

Wire the cockpit's readiness-tile renderers to **consume** the `surface_links.drill` binding already declared in the View Definition (`REQ-cross-surface-view-definition` FR-4, shipped `67051859`) and render each per-field row as a navigable link to the navig8r's `#<key>` full-page view. Closes the **NR-7 adopter gap**: the shared taxonomy + drill binding were declared-not-consumed; this spec makes them user-visible. Three rendering surfaces adopt the link: the web front-end (the primary interactive surface), the Grafana v2 board (markdown links in text panels), and the terminal cockpit view (a `#<key>` annotation for copy-paste).

**Shipped bricks reused (do NOT re-spec):**
- `resolve_surface_link_href(link, key)` → `"#{key}"` (`view_definition.py:288-297`, `b346e612`)
- `cockpit_statuses_from_node_state(node_state)` → `{canonical → cockpit_leaf}` (`view_definition.py:250-269`, `b346e612`)
- `BASE_NAVIG8R_DEFINITION.surface_links["drill"]` = `{from_surface: cockpit, to_surface: navig8r, relation: drill, via: fullview, href: "#{key}"}` (`view_definition.py:556-565`, `67051859`)
- `cockpit_attention_colors(node_state)` → `{attention → hex}` (`view_definition.py:272-285`, `cd7c236d`)
- The `#<key>` full-page route (`wireframe_view/_template.py:900,923,1402`)

---

## Objectives

- O-1: Cockpit readiness tiles link each field to the navig8r node's full-page view via the declared drill binding, using `resolve_surface_link_href` — no bespoke URL construction.
- O-2: The three cockpit rendering surfaces (web, Grafana v2, terminal) carry the link in their respective idioms (anchor tag, markdown link, dim annotation).
- O-3: The link renders ONLY when the resolved definition carries a non-empty drill href (the empty-default pattern); definitions without `surface_links.drill.href` produce no link — zero regression on other consumers.
- O-4: `view_definition.py`, `wireframe_view/_template.py`, `graph_projection.py`, and the existing navigator test suite have **zero diff** — the adopter is read-only over the shared definition.

---

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | A wrong key is passed to `resolve_surface_link_href` → the link lands on a non-existent node | FR-1 Verify: the key passed is the same key the navig8r indexes by (`item.key`); test: resolve a known key → expected `#<key>` | medium |
| coupling | The kickoff renderers import `resolve_surface_link_href` from `navigator.view_definition` — introducing a coupling direction | FR-1: import is READ-ONLY (a pure-function call on an already-public API, same pattern as `cockpit_attention_colors` in `portal_spec.py:49-54`). The coupling is deliberate (the drill binding's consumer); NR-2 ensures no write-back | low |
| scope-creep | Rebuilding the cockpit tile layout instead of adding a link to the existing row render | NR-1: the tile layout, badge logic, and attention derivation are untouched. The link is an additive format insertion into the existing per-field row | low |

---

## Profile

Declared profile: **internal** (consumers are SDK contributors and the requirements-viz + kickoff self-use).

---

## Functional requirements

- **FR-1 — Web cockpit field rows carry a drill link.** The web overview's per-field status row (`web.py` overview renderer) includes an anchor `<a href="…">` whose `href` is `resolve_surface_link_href(resolved.surface_links["drill"], field_key)`, so a user clicks a cockpit field → lands on the navig8r's `#<key>` full-page view; the link renders only when the href is non-empty (empty-default). Name: The web cockpit overview renders each field row as an anchor to the navigator node resolved through the declared drill binding. Touches: `src/startd8/kickoff_experience/web.py`, `tests/unit/kickoff_experience/test_cockpit_drill_link.py`. Verify: (a) a rendered overview HTML for a project with surface_links contains an `<a>` tag whose href equals `#<field_key>` for each field; (b) when `surface_links` is absent/empty, no link renders (byte-identical to before); (c) `resolve_surface_link_href` is called with the drill binding dict and the field's key — no bespoke URL construction. Serves: O-1, O-2, O-3

- **FR-2 — Grafana v2 board field rows carry a markdown drill link.** The `portal_spec_v2.build_workbook_v2` field-row rendering includes a markdown link `[→ navig8r](#{key})` per field, so the Grafana text panel is navigable to the navig8r route, and renders only when the drill href is non-empty. Name: The Grafana v2 board renders each field row with a markdown link to the navigator node from the same declared drill binding. Touches: `src/startd8/kickoff_experience/portal_spec_v2.py`, `tests/unit/kickoff_experience/test_cockpit_drill_link.py`. Verify: (a) a built v2 dashboard JSON for a project with surface_links contains the markdown link pattern `[→ navig8r](#<key>)` in a text panel; (b) absence of surface_links → no link text. Serves: O-1, O-2, O-3

- **FR-3 — Terminal cockpit view annotates the key for copy-paste (DEFERRED).** The Rich-rendered terminal cockpit (`cockpit_view.py`) currently shows only aggregate attention counts, not per-field rows, so a per-field `#<key>` annotation requires per-field rendering that doesn't yet exist and is **deferred** to a follow-on that adds per-field terminal rows. Name: The terminal cockpit annotates each field row with its navigator key once per-field terminal rendering exists. Touches: `src/startd8/kickoff_experience/cockpit_view.py` (future). Verify: (deferred — no current test). Serves: O-2

- **FR-4 — Zero diff on shared definition + navigator.** The navigator's `view_definition.py`, `wireframe_view/_template.py`, and `graph_projection.py` have zero diff — the adopter reads `surface_links` from the resolved definition and does not modify, extend, or re-declare it. Name: The navigator and wireframe sources stay byte-identical while the cockpit consumes the shared definition read-only. Touches: (none — this is a no-change assertion). Verify: `git diff --stat src/startd8/navigator/ src/startd8/wireframe_view/` shows 0 files changed. Serves: O-4

- **FR-5 — Empty-default: no regression on definitions without drill href.** A resolved definition whose `surface_links` is absent, empty, or whose `drill.href` is falsy produces no drill link on any of the three surfaces, so existing rendering is byte-identical for those cases. Name: A definition without a drill href renders no link on any cockpit surface so unbound definitions are unchanged. Touches: `tests/unit/kickoff_experience/test_cockpit_drill_link.py`. Verify: (a) pass a definition with `surface_links={}` → render has no link; (b) pass a definition with `surface_links.drill` but `href=""` → render has no link. Serves: O-3

---

## Non-goals

- NR-1: Rebuilding the cockpit tile layout, badge logic, or attention derivation. The link is an additive per-field annotation; the tile structure is untouched.
- NR-2: Writing back to or modifying `surface_links` / `node_state` from the cockpit. This is a read-only consumer.
- NR-3: Adding a new `#<key>` route or changing the existing navig8r full-page route. The drill target is unchanged.
- NR-4: Wiring the rollup binding (FR-5 from the parent spec). The rollup direction (navig8r→cockpit) is a separate concern — this spec covers drill (cockpit→navig8r) only. Adjacent to EC-CS-7 but distinct: EC-CS-7 wires `node_state → activation`; this wires `surface_links.drill → rendered href`.
- NR-5: Supporting non-kickoff cockpits (e.g. a future benchmark cockpit). Scope is `kickoff_experience/` only — the pattern is replicable but not generalized here.

---

## Distinction from EC-CS-7 (rollup → activation)

| This spec (H1 cockpit adopter) | EC-CS-7 |
|---|---|
| **Direction:** cockpit → navig8r (drill) | **Direction:** navig8r → cockpit (rollup) |
| **Consumes:** `surface_links.drill.href` | **Consumes:** `node_state` → `activation.py` |
| **Output:** a visible link on cockpit tiles | **Output:** readiness state derived from node grounding |
| **Scope:** rendering format (additive href) | **Scope:** state derivation (activation logic) |

---

## Owned fields

Only humans enter: nothing (this spec adds a derived rendering element from existing data). The drill href template (`"#{key}"`) is author-owned in the parent View Definition; this spec reads it.

---

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §8 `python-cli-surface` · living homes `~/Documents/dev/startd8-sdk/pyproject.toml`, `~/Documents/dev/startd8-sdk/src/startd8/kickoff_experience/` · reuse sources `src/startd8/navigator/view_definition.py:288-297` (`resolve_surface_link_href`), `:250-269` (`cockpit_statuses_from_node_state`), `:556-565` (`surface_links.drill` with `href: "#{key}"`), `src/startd8/kickoff_experience/portal_spec.py:49-54` (`attention_colors` — same import pattern), `src/startd8/kickoff_experience/portal_spec_v2.py` (Grafana v2 board), `src/startd8/kickoff_experience/web.py` (web front-end), `src/startd8/kickoff_experience/cockpit_view.py` (terminal view)

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| drill-link-web | field | words | `<a href="#{key}">` per field row in the web overview (FR-1) |
| drill-link-grafana | field | words | `[→ navig8r](#{key})` markdown in v2 text panel (FR-2) |
| drill-link-terminal | field | words | dim `#<key>` annotation in Rich output (FR-3) |
| exit-kickoff | exit-class | structure | unchanged (0 = rendered; non-zero = state-load/IO failure) |

---

## Reference-Audit (§0.1 phantom check)

| Symbol | File:line | Grep status |
|--------|-----------|-------------|
| `resolve_surface_link_href` | `view_definition.py:288` | ✅ live (EC-CS-4, `b346e612`) |
| `cockpit_statuses_from_node_state` | `view_definition.py:250` | ✅ live (EC-CS-3, `b346e612`) |
| `cockpit_attention_colors` | `view_definition.py:272` | ✅ live (EC-CS-8, `cd7c236d`) |
| `BASE_NAVIG8R_DEFINITION.surface_links` | `view_definition.py:556` | ✅ live (`67051859`) |
| `_ATTENTION_DISPLAY` | `portal_spec.py:32` | ✅ live |
| `KickoffState.to_dict()` | `state.py` | ✅ live |
| `build_workbook_v2` | `portal_spec_v2.py` | ✅ live |

---

## Iterations

| # | Iteration | FRs | Depends on | Rationale |
|---|-----------|-----|-----------|-----------|
| 1 | **Web drill link** — the primary interactive adopter | FR-1, FR-5 | — | The web cockpit is the live interactive surface; gets the link first. |
| 2 | **Grafana v2 drill link** — additive markdown | FR-2 | — (parallel-safe) | The board builds independently from its own function. |
| 3 | **Terminal annotation** — dim route hint | FR-3 | — (parallel-safe) | Terminal adds a copy-paste route. |
| — | **Zero-diff guard** (cross-cutting) | FR-4 | all | Confirm navigator/wireframe are untouched. |

---

## Dependencies

- **REQ-cross-surface-view-definition** — supplies the resolved `surface_links.drill` binding, `resolve_surface_link_href`, `cockpit_statuses_from_node_state`. **Built + landed (`67051859`, `b346e612`).**
- **EC-CS-4** (`resolve_surface_link_href` + `href: "#{key}"`) — the concrete helper this spec calls. **Built (`b346e612`).**
- **EC-CS-8** (`cockpit_attention_colors`) — same import pattern (kickoff importing from `view_definition`). **Built (`cd7c236d`).**
- **Kickoff web + Grafana v2 + terminal cockpit** — the three rendering surfaces the links are added to. **Built.**

---

## Appendix A — Accepted (with where merged)

*(empty at v0.3.1 — no CRP review run yet)*

## Appendix B — Rejected (with rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| — | Build a generic "drill-link component" reusable across future cockpits | v0.1 scope exploration | YAGNI — scope is `kickoff_experience/` only (NR-5); the pattern is 3 lines per surface. Generalize when a second cockpit exists | 2026-08-19 |
| — | Wire the rollup binding (navig8r→cockpit) in the same spec | ledger adjacency | Different direction + different concern (state derivation vs rendering format); EC-CS-7 already names it. NR-4 | 2026-08-19 |

## Appendix C — Incoming review rounds

*(ready for CRP — optional; the spec is ~S-effort implementable without external review)*

**CRP offer:** this spec is small and well-grounded. A CRP review can run but is likely low-yield given the trivial wiring. Offered per skill protocol; not blocking.

---

*v0.3.2 — Stage-0 ungate: every FR carries a deterministic `Name:` and a `Serves:` edge (FR-1/2 → O-1·O-2·O-3, FR-3 → O-2, FR-4 → O-4, FR-5 → O-3), so the build-readiness gate passes. Test `Touches:` paths corrected to the repo's `tests/unit/kickoff_experience/` convention (the `tests/unit/kickoff/` path was stale). No requirement narrowed, added, or deferred; FR-3 stays DEFERRED.*

*v0.3.1 — Post design-principle hardening. Applied 4 principles: Mottainai, Genchi Genbutsu, SOTTO, Kagami. Applied 3 lessons: phantom-reference audit, NR-7 ceiling, single-source/no-re-guess. 0 requirements narrowed, 0 deferred, 0 added, 3 open questions resolved. Ready for CRP review.*
