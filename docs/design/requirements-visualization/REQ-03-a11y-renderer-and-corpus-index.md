# A11y Requirements Renderer + Corpus Index — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** the a11y-renderer track brief `docs/NAVIG8_A11Y_RENDERER_TRACK_FROM_DEV-OS_2026-08-14.md`
**Inherits standards:** NODE-SCHEMA · NAMING_CONVENTION · REQ-01 (SDK Node home) · REQ-02 (N-level tree renderer)
**Audience:** operator / adopter
**Trust boundary:** local filesystem + authored req docs; no network fetch of evidence
**Data classification:** internal

> **Readable handle:** `feature/navigator-a11y-renderer-and-corpus-index`
> **Semantic name:** *SDK navigator renders a requirements doc as a semantic accessible view and a directory of docs as a drill-to-leaf corpus index, as standalone renderers that never import wireframe.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-03`

---

## 0. Why this exists — the mujo recovery

> *Mujo* (無常, impermanence): the deep-drill / **a11y renderer** and **corpus index** capabilities were
> **built and wired in ContextCore** (`navigator/render_a11y.py` — a semantic `ReqView`;
> `navigator/render_index.py` — a drill-to-leaf corpus index), but the port to the SDK navigator
> (the forward home, decision 2026-08-14) carried **only the flattening wireframe projection**. The
> capability was then **deferred twice** — REQ-01 NR-2 ("owning the ContextCore a11y cockpit /
> `render_a11y.py`") and REQ-02 NR-3 ("porting the full CC navigator family"). This REQ **recovers**
> the last piece of the a11y-renderer track (item 5 of the brief) so the full requirements-
> visualization capability lives in the forward home and can't be lost again.

**Track completion map** (the brief's 5 items):

| Item | Capability | Home |
|------|-----------|------|
| 1–4 | N-level drill tree · `--source nodes-json` · `--renderer` · `children` in JSON | **REQ-02** |
| **5** | **a11y requirements view · corpus index** | **this REQ (REQ-03)** |

## Overview

Port ContextCore's `render_a11y.py` (semantic, screen-reader-first requirements view) and
`render_index.py` (a corpus index that drills to per-doc a11y leaves) into the SDK navigator as
**standalone renderers** — their own HTML shell, decoupled from `wireframe_view` (the same structural
choice REQ-02 made for the tree renderer). This gives the forward home the accessible/cockpit surface
the wireframe path deliberately never had, without disturbing it.

## Objectives

- **O-1:** Render a single requirements doc as a **semantic, accessible** view (landmarks, roles,
  screen-reader order) via `startd8 navigator build --format a11y` — target: exit 0, valid a11y HTML.
- **O-2:** Render a **directory** of requirements docs as a **corpus index** that drills to per-doc
  a11y leaves — target: an index page linking to N generated leaf files.
- **O-3:** The a11y + index renderers are **standalone** (never import `wireframe_view`); the
  app-scaffold path stays **byte-identical** — target: existing byte-identity tests pass unedited.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Porting CC dead code (`render.py` had shadowed dupes) | port the LIVE symbols only; add a `grep -c "def <sym>" == 1` gate (as REQ-02 FR-1 did) | high |
| security | XSS on authored/evidence text in the a11y HTML | port CC's `html.escape` / `_safe_href` / `_safe_color` mitigations (CC #398/#400) | high |
| quality | a11y renderer secretly coupling to wireframe | keep its own HTML shell; forbid `import wireframe_view` (a11y is a distinct presentation contract) | high |
| scope-creep | Dragging in the Tier-2/3 lesson·principle cockpit flags | NR-3: port the base a11y `ReqView` + index only; cockpit flags deferred | medium |

## Functional requirements

- **FR-1 — A11y requirements renderer.** Port CC `render_a11y.py` (`ReqView` + `render_html` / `render_a11y_to_file`) into `src/startd8/navigator/render_a11y.py` as a standalone renderer with its own semantic HTML shell (ARIA landmarks, heading order, per-requirement rows with status + evidence) — it must not import `wireframe_view`. Name: SDK navigator renders a requirements doc as a semantic accessible view without importing wireframe. Touches: `src/startd8/navigator/render_a11y.py`, `src/startd8/navigator/cli_navigator.py`. Lives: link ContextCore/src/contextcore/navigator/render_a11y.py. Approve?: is the a11y renderer standalone (no wireframe import) with real landmarks/roles?. Verify: `startd8 navigator build --source requirements --format a11y --out x.html` exits 0; the HTML carries semantic landmarks and per-FR rows; the module has no `import wireframe_view`. Serves: O-1
- **FR-2 — Corpus index (drill-to-leaf).** Port CC `render_index.py` (`render_index_to_file`) into `src/startd8/navigator/render_index.py`: given a directory of requirements docs, render an index page that links to one generated a11y leaf per doc (each via FR-1). Name: SDK navigator renders a directory of requirements as a drill-to-leaf corpus index. Touches: `src/startd8/navigator/render_index.py`, `src/startd8/navigator/cli_navigator.py`. Lives: link ContextCore/src/contextcore/navigator/render_index.py. Approve?: does the index drill to one a11y leaf per doc?. Verify: `startd8 navigator index --dir docs/design/requirements-visualization --out idx.html` writes an index + N leaf files and the links resolve. Serves: O-2
- **FR-3 — CLI seam for a11y + index.** Extend the navigator CLI: `--format a11y` on `build` (single doc) and a new `navigator index` command (a directory), consistent with REQ-02's `--renderer` vocabulary; back-compat preserved (`--format html|json` unchanged). Name: Navigator CLI exposes a11y format on build and a corpus-index command for a directory. Touches: `src/startd8/navigator/cli_navigator.py`. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: are the a11y + index CLI seams additive (no break to html/json)?. Verify: `startd8 navigator --help` lists `index`; `--format a11y` renders; existing `--format html|json` unchanged. Serves: O-1
- **FR-4 — Accessibility contract.** The a11y view meets a stated accessibility bar — semantic landmarks, correct heading order, keyboard-reachable disclosures, sufficient contrast, and no status conveyed by colour alone (the reason this renderer is separate from the wireframe preview). Name: The a11y requirements view meets the semantic-landmark and screen-reader accessibility bar. Touches: `src/startd8/navigator/render_a11y.py`. Lives: link ContextCore/src/contextcore/navigator/render_a11y.py. Approve?: does the a11y view satisfy landmarks / heading order / non-colour-only status?. Verify: rendered HTML has one `<main>`, ordered headings, aria attributes on disclosures, and status conveyed by text+glyph not colour alone. Serves: O-1
- **FR-5 — App-scaffold byte identity + standalone.** `render_a11y.py` and `render_index.py` are standalone modules the wireframe pipeline never imports; no `WireframePlan` / `WireframeItem` / `compose.py` / `_template.py` path changes. Name: The a11y and index renderers leave the app-scaffold wireframe path byte-identical. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is the wireframe path untouched by the a11y port?. Verify: `test_no_profile_is_byte_identical` + determinism pass unedited; `wireframe_view` does not import `render_a11y`/`render_index`. Serves: O-3
- **FR-6 — Port-hazard gates.** Drop CC dead code on port (shadowed duplicate defs) and carry the XSS mitigations, with the same single-live-def gate REQ-02 uses. Name: The a11y port drops CC dead code and carries its XSS escaping mitigations. Touches: `src/startd8/navigator/render_a11y.py`. Lives: link ContextCore/src/contextcore/navigator/render_a11y.py. Approve?: does the port keep only live defs + XSS escaping?. Verify: every ported top-level symbol appears once; authored/evidence text is escaped and hrefs/colours are sanitized. Serves: O-3

## Non-goals

- NR-1: Re-porting the N-level tree renderer or `--source nodes-json` — that is **REQ-02**.
- NR-2: Reusing the audience × fluency lenses in the a11y renderer (it carries its own semantic shell).
- NR-3: The Tier-2/3 lesson·principle cockpit flags family (REQ-06/07/08 lineage) — base `ReqView` +
  index only; the richer cockpit is a follow-on.
- NR-4: Wiring the debug-panel view modes (REQ-01 FR-11..15) onto the a11y surface — different contract.
- NR-5: A new CSS design system — port CC's shell as-is (offline, no CDN).

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `dev-os/NODE-SCHEMA.md` · `docs/NAVIG8_A11Y_RENDERER_TRACK_FROM_DEV-OS_2026-08-14.md`

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| navigator-build | command | structure | existing; gains `--format a11y` |
| navigator-index | command | structure | new: `startd8 navigator index --dir … --out …` |
| format-a11y | option | structure | `--format a11y` (semantic single-doc view) |

Library seams (Touches file paths): `src/startd8/navigator/render_a11y.py`,
`src/startd8/navigator/render_index.py`, `src/startd8/navigator/cli_navigator.py`.

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

*v0.1 — recovers a11y-renderer track item 5 (the mujo-lost a11y view + corpus index). Ready for CRP.*
