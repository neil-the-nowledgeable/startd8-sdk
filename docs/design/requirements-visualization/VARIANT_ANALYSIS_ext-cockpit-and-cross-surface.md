# Variant Analysis — Extension: the Cockpit as a Sibling Surface (cross-surface altitudes)

**Date:** 2026-08-17 · **Method:** extend the reflective-abstraction variant analysis *past the
navig8r's edge*. **Grounded** in the built corpus (file:line). **Extends (does not overwrite):**
`VISUALIZATION_VARIANTS_ANALYSIS.md` (the `SOURCE × TOPOLOGY × PRESENTATION × AUDIENCE-LENS` taxonomy,
Node = the fixed waist) + `VARIANT_STATUS_navigator-renderer-inventory.md` (the six renderers).

> **Why this note exists.** The variant analysis and the renderer inventory both map only the
> **navig8r-internal** renderers — they stop at the navigator's edge. But the SAME requirements/project
> state is *also* rendered by a second, non-navig8r surface: the kickoff **workbook cockpit** (the
> Grafana/read-only readiness board). It is a sibling visualization the taxonomy never placed. This
> note confirms the blind spot, places the cockpit (and the ContextCore o11y board) in the taxonomy as
> **sibling surfaces at a different altitude**, and maps the two-way drill/rollup relationship.

---

## 1. Confirm the blind spot — the map stops at the navig8r's edge

Both grounding docs are scoped strictly to the navigator's own renderers:

- `VARIANT_STATUS_navigator-renderer-inventory.md:3-5` — **Scope:** *"the requirements-visualization
  renderers in `src/startd8/navigator/` + `src/startd8/wireframe_view/`."* The six ACTIVE variants it
  enumerates (§2, tree · graph · a11y · index · diff · wireframe) are ALL under those two packages.
- `VISUALIZATION_VARIANTS_ANALYSIS.md` §1–§2 — the catalog and the four-axis product space are drawn
  entirely from `navigator/` + `wireframe_view/` capabilities; no `kickoff_experience/` surface appears.

Grep confirms it: neither doc mentions `cockpit`, `workbook`, `readiness`, or `kickoff_experience`.
**The cockpit is absent from both** — a genuine blind spot, not an intentional exclusion. The variant
set that the reflective-abstraction generalized over was implicitly *"renderers the navigator owns,"*
not *"surfaces that render the requirements/project state."* The cockpit is the second kind.

### The missing surface, grounded

| Surface | What it is | Ground (file:line) |
|---------|-----------|--------------------|
| **workbook cockpit** (v2) | a READ-ONLY readiness/activation board — the Digital Project Workbook, audience-personalized, emitted as Grafana panels (or text) | `build_workbook_v2_and_maybe_provision` `kickoff_experience/portal_build.py:53`; `cockpit_view.py`; `agentic_view.py:122` `AgenticView`; `cli_kickoff.py`; `docs/design/kickoff/GRANT_AND_COCKPIT_ENHANCEMENTS.md`; `docs/design/kickoff-portal/` |
| its **state taxonomy** | readiness-flavored: field `attention_counts = {ok, review, blocked, backlog}`, a `readiness_percent`, an activation severity, a promote gate | `agentic_view.py:156` (`{ok, review, blocked, backlog}`); `agentic_view.py:148-160` `readiness_percent`; `activation.py:61` (`0=ok/activated · 1=attention · 3=blocked`); `promotion.py:59` `promotion_eligibility` (blocked→promotable) |
| its **audience** | operator / exec doing kickoff — *"is my project ready / on-track / activated?"* | `GRANT_AND_COCKPIT_ENHANCEMENTS.md` §1 (read-only cockpit + operator playbook); `portfolio.py` ranked readiness board (`--index --scan`) |

---

## 2. Place the cockpit in the taxonomy — a distinct PRESENTATION × AUDIENCE cell

The cockpit *does* factor along the same axes — it is another point in
`SOURCE × TOPOLOGY × PRESENTATION × AUDIENCE-LENS` — but it occupies a **cell the current map omits**:
a **board/dashboard PRESENTATION** for an **operator/exec AUDIENCE**, over a **rollup TOPOLOGY**
(project-level aggregate, not per-node detail).

| Coordinate | Six navig8r renderers | **Cockpit (this extension)** |
|-----------|------------------------|------------------------------|
| **SOURCE** | requirements · capability-index · node-schema · nodes-json (`Fᵢ : Domainᵢ → Node`) | the kickoff **canonical state / oracle** (`build_assess` → `ReadinessView`, `readiness.py:63`) |
| **TOPOLOGY** | flat · 2-level · N-level tree · corpus-index · graph | **rollup / aggregate** (project → readiness %, attention counts) — a *reduction*, not a node relation |
| **PRESENTATION** | wireframe-card · tree-drill · a11y-text · index-strip · diff-delta · graph-network (all **node-detail** shells) | **board / dashboard** (readiness tiles, burndown timeseries, ranked portfolio) — NOT node-detail |
| **AUDIENCE** | end_user · architect · integrator · a11y · maintainer · auditor | **operator / exec** ("are we ready / on-track / activated?") |

**Extended surface table** — the six renderers plus the two sibling board surfaces:

| # | Surface | PRESENTATION | AUDIENCE | Altitude | Home |
|---|---------|-------------|----------|----------|------|
| 1 | wireframe / navig8r | editorial-card | end_user · architect | node-detail | `wireframe_view/view.py` |
| 2 | tree | N-level drill | integrator | node-detail | `navigator/render_tree.py` |
| 3 | graph | network | architect | node-detail | `navigator/render_graph.py` |
| 4 | a11y | speakable text | screen-reader user | node-detail | `navigator/render_a11y.py` |
| 5 | index | corpus strip | auditor | corpus (multi-doc) | `navigator/render_index.py` |
| 6 | diff | two-state delta | reviewer | node-detail (delta) | `navigator/render_diff.py` |
| **7** | **workbook cockpit** | **board / dashboard** | **operator / exec** | **rollup (project)** | `kickoff_experience/portal_build.py:53` |
| **8** | **ContextCore o11y board** | **board / dashboard** | **exec / lead** | **rollup (goal/feature/agent)** | `ContextCore/src/contextcore/business/board.py` |

The **ContextCore o11y board** (surface 8) is a second sibling at the same altitude: the
pace/leadership board (`board.py:73` `render_board_text`, `board.py:133` `board_payload`) renders
business goals **worst-first** (`board.py:18,34`) — the same "are we on-track?" board altitude, over a
different corpus (business KRs, and its reuse for the delivery-agent board, `board.py:84`). It, too, is
absent from the navig8r variant map, for the same reason: it isn't a `navigator/` renderer.

**Key placement claim:** surfaces 7–8 are **not** new cells *within* the node-detail region the six
renderers tile — they open a **new region of the product space** (the board/rollup × operator cell)
that the navig8r inventory's §1 framing ("the navig8r card view occupies exactly ONE cell") never
reached, because it only enumerated node-detail presentations.

---

## 3. Overlap / complement — two surfaces on the SAME state at different altitudes

navig8r and the cockpit are **not** redundant and **not** substitutes. They render the *same*
requirements/project state at **two altitudes**:

- **cockpit = board altitude** — *"are we ready / on-track / activated?"* A reduction: `readiness_percent`,
  `attention_counts`, promote-eligibility (`agentic_view.py:148`, `promotion.py:59`).
- **navig8r = node-detail altitude** — *"what / how / why / is it grounded?"* Per-node: `does`,
  `status`, `lives`, `children`, evidence-binding (`VISUALIZATION_VARIANTS_ANALYSIS.md` §3).

The relationship is **two-way** — the missing cross-*surface* links:

### (a) cockpit → navig8r: the **drill** (a tile drills into node detail)

A cockpit readiness tile ("3 fields blocked," `activation.py:159-162`) is a *summary of nodes*.
Drilling from that tile into the node-detail view = **Move 1 (hub → detail)**, but crossing a **surface
boundary** (board → node renderer), not staying inside one renderer. This is the cross-surface
generalization of the intra-navig8r hub/drill: today the cockpit's deep-links point back to the *CLI
action* (`FR-E11` cockpit-assistant deep-link, `GRANT_AND_COCKPIT_ENHANCEMENTS.md:75`), **not** to the
navig8r node view. The drill-to-navig8r link is an **open cell**.

### (b) navig8r → cockpit: the **rollup** (node grounding/coverage rolls up into readiness)

The inverse direction. A node's grounding/coverage state (grounded / spec / awaiting) is exactly the
per-item signal that, *aggregated*, becomes cockpit readiness. This is the **composition/rollup
primitive** already specified as `REQ-feature-capability-composition-rollup.md` (2026-08-17): a feature
node declares the capability it composes up to, and capabilities render **ground-up (bottom-up) from
their constituent features** (its §0). Extend the rank direction one more level — feature → capability
→ **project readiness** — and the navig8r node graph *is* the substrate the cockpit reduces. The
rollup primitive is the mechanism; wiring its output into a cockpit readiness tile is the **open cell**.

### The two-sided coin, and the o11y pillars

The composition-rollup spec already frames navig8r as *"the two-sided validation surface — technical
grounding on one side, human/business value on the other"* (`REQ-feature-capability-composition-rollup.md`
§0). The cockpit/navig8r altitude split **is that coin, rendered as two surfaces**:

| Coin side | Surface | Question | Vocab |
|-----------|---------|----------|-------|
| **business-value / readiness** | **cockpit** (board) | is it *ready / activated*? | `ok / review / blocked / backlog`, readiness %, promotable |
| **technical-grounding** | **navig8r** (node-detail) | is the code *there / the check live*? | `grounded / spec / awaiting` |

This maps onto the **ContextCore o11y pillars**: the cockpit is the **business/leadership pillar**
(`business/board.py` pace/KR board — "are we on-track?"), navig8r is the **technical/feature pillar**
("is the node grounded?"), and drill/rollup are the **cross-pillar links** (roll technical grounding up
into the business readiness number; drill a business tile down into the technical evidence).

---

## 4. The shared-taxonomy insight — one node health, two presentations

The two surfaces' status vocabularies are the **same node health at different presentations**:

| Surface | Status vocab | Ground |
|---------|-------------|--------|
| **navig8r** (REQUIREMENTS_DEFINITION) | `grounded` · `spec` · `awaiting` (severity 0/2/3, `awaiting` is_gap) | `navigator/view_definition.py:400-403` |
| **cockpit** (readiness) | `ok` · `review` · `blocked` · `backlog` (sort `blocked<review<backlog<ok`; activation `0=ok/activated · 1=attention · 3=blocked`) | `agentic_view.py:156`; `portal_spec.py:38`; `activation.py:61` |

These are **isomorphic health lattices** rendered in two dialects — `grounded↔ok` (present/healthy),
`spec↔review` (declared, not settled), `awaiting↔blocked` (needs a decision / gap). navig8r already
resolves its vocabulary through a **ViewDefinition** (`view_definition.py:395` `REQUIREMENTS_DEFINITION`,
a keyed-map `vocabulary.statuses`). The cockpit hard-codes its own parallel vocab in
`kickoff_experience/`. **Flag:** these are a candidate for a **shared cross-surface View Definition** —
one node-health vocabulary both surfaces resolve against, so `grounded/spec/awaiting` and
`ok/review/blocked` stop being two drifting hand-maintained enums. (The sibling spec
**REQ-cross-surface-view-definition** would cover this; it does **not** exist on disk yet — see §5.)

> This is the FF-1 pattern (`VISUALIZATION_VARIANTS_ANALYSIS.md` §3) one level up: FF-1 was *lenses
> welded to one renderer*; the cross-surface version is *the status vocabulary welded per-surface*. The
> ViewDefinition cascade (`REQ-10-view-definition-cascade.md`) is the navig8r-internal answer; lifting
> it to **cross-surface** (cockpit inherits the same `statuses` map) is the next "RenderProfile moment."

---

## 5. What to add to the analysis next — the open cells

| Candidate | Kind | Why (from this extension) |
|-----------|------|---------------------------|
| **Cockpit as a first-class variant** | new region | Add the board/dashboard × operator/exec cell (surfaces 7–8) to `VISUALIZATION_VARIANTS_ANALYSIS.md` §2's product space and to the renderer-inventory framing, so the map covers *surfaces that render the state*, not only navig8r renderers. |
| **Cross-surface View Definition** | factor-out | The shared node-health vocabulary (§4). `REQ-cross-surface-view-definition` — sibling to `REQ-10-view-definition-cascade.md`; **not yet on disk**. Un-welds `grounded/spec/awaiting` (navig8r) and `ok/review/blocked` (cockpit) into one resolved `statuses` map. |
| **cockpit → navig8r drill link** | cross-link | §3(a) — a readiness tile deep-links into the node-detail view (Move 1, cross-surface). Today the deep-link points at the CLI action (`FR-E11`), not navig8r. |
| **navig8r → cockpit rollup wiring** | cross-link | §3(b) — feed the composition-rollup output (`REQ-feature-capability-composition-rollup.md`) up into a cockpit readiness tile: node grounding → capability → **project readiness**. |
| **A cross-surface altitude taxonomy** | reference | Promote §2–§3 (node-detail vs board/rollup; the drill/rollup dual) to a cited standard, so future surfaces declare their **altitude** alongside their `(source, topology, presentation, audience)` coordinates. |

**Bottom line.** The variant analysis generalized over the navig8r's own renderers and missed that the
requirements/project state is *also* rendered at a **board altitude** by the kickoff cockpit (and, in
ContextCore, by the pace board). The cockpit is not a seventh renderer inside the node-detail region —
it is a **sibling surface in a new region** (board/rollup × operator), tied to navig8r by a **drill ↓**
and a **rollup ↑** over the *same* node health, spoken in two isomorphic vocabularies that want one
shared cross-surface View Definition.

---

*Grounded 2026-08-17. Extends `VISUALIZATION_VARIANTS_ANALYSIS.md` + `VARIANT_STATUS_navigator-renderer-inventory.md`;
does not modify them. Cockpit grounded in `kickoff_experience/` (portal_build/agentic_view/activation/promotion/readiness);
CC board in `ContextCore/src/contextcore/business/board.py`; the rollup primitive in
`REQ-feature-capability-composition-rollup.md`. `REQ-cross-surface-view-definition` is a proposed sibling, not yet on disk.*
