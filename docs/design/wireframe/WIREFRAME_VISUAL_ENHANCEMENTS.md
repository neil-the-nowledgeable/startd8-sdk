# Wireframe Visual — Enhancement Backlog

**Date:** 2026-07-19
**Status:** Living backlog (prioritized)
**Scope:** the stacked capabilities we built — **FR-WV** (`--html` preview), **FR-AUD** (audience layer),
**FR-SHC** (content coverage guard), and **the pattern itself** (proven twice: the wireframe preview +
the benchmark-portal `/start`). Grounded in the residuals/OQs surfaced during the build.

Effort key: **XS** trivial · **S** small · **M** medium · **L** large.

---

## ⚡ Quick wins (small, high-value — built on what exists)

| # | Enhancement | Why it helps | Effort | Status |
|---|---|---|:--:|:--:|
| QW-1 | **In-file audience/fluency toggle** — embed the variants + a JS switcher so a reviewer flips architect↔end-user / beginner↔advanced live (no regenerate). View-model is deterministic + small. (OQ-WV-1) | biggest usability jump | S | ✅ |
| QW-2 | **`--open` + default `--html` path** — bare `--open` writes `.startd8/wireframe/preview.html` and launches the browser; always print a clickable `file://` URL. Kills the "where do I put it / `/tmp` perms" friction. | removes setup friction | XS | ✅ |
| QW-3 | **Top-level "before launch" to-do roll-up** — aggregate per-section `need_items` (+ content gaps) into one banner up top. Directly serves the omission-catching thesis. | one glance = all outstanding | S | ✅ |
| QW-4 | **Wire a coverage CLI** — `matrix_coverage()` (FR-SHC) only runs via `python -m`; expose `startd8 wireframe --coverage`. | makes the guard usable | XS | ✅ |
| QW-5 | **Status legend** — the colored badges (planned/not-defined/placeholder) mean nothing to a non-technical author; a one-line legend. | comprehension | XS | ✅ |

## 🌱 Low-hanging fruit

- **LH-1 — Expose entity `fields[]` in the plan JSON** → real **list mockups** (actual columns) + richer
  **page mockups**. Fields are already parsed from `schema.prisma`; they just don't reach the view-model.
  Single biggest *fidelity* jump. (OQ-WV-2) — **M**
- **LH-2 — Expose the audience view-model as JSON** (`--view-json`) so other surfaces (a web app, the
  portal) reuse the benefit-first content. Turns FR-AUD into a data capability, not just HTML. — **S**
- **LH-3 — Finish fluency / other-role coverage** — fluency is authored on only 3 sections; either
  author the rest or declare it intentionally sparse (content pass). — **S**

## 🏗️ Architectural quick wins

- **AR-1 — Single-source the record schema** — `describe.py`'s resolver still hardcodes its field list;
  FR-SHC now *declares* `SECTION_SCHEMA`/`SUMMARY_SCHEMA`. Have the resolver read the declaration
  (KM-27 residual / CL-17 L4 gate). Removes a drift seam. — **S**
- **AR-2 — Extract the audience/onboarding pattern as a named capability** — applied twice now
  (wireframe + portal `/start`); a small shared renderer + a documented pattern makes the next surface a
  config away, not a rebuild (Yokoten). — **M**
- **AR-3 — Lift the mockup renderers out of the HTML string** — the form/page/list drawers live in the
  template JS; the structured data is already in the view-model. A mockup spec lets a live app/portal
  draw the same sketches. — **M**

## 🚀 Enhanced capabilities

- **EC-1 — `--diff` (planned-vs-built)** — `inputs_fingerprint` is already persisted *for exactly this*.
  "What changed since you approved" closes the loop: preview → approve → build → verify. Highest-value
  new capability. (OQ-8) — **M/L**
- **EC-2 — Approve / annotate** — the preview is read-only; the requirements-preview capability's actual
  verb is *approve*. Per-section "looks right / flag this" (localStorage or export) → sign-off that feeds
  the kickoff loop. — **M**
- **EC-3 — Served / live-reload mode** — reuse the `kickoff_view` serve seam so the preview auto-updates
  as manifests change (author-in-the-loop). — **M**
- **EC-4 — The pattern → the delivery-role kits** — FR-AUD supports role × fluency; only architect +
  end_user are authored. The FR-J roles (BA/PM/backend…) each getting a wireframe voice is a straight
  extension. — **M**

---

## Do-first shortlist
1. **QW-1** (toggle) — biggest usability jump, small effort.
2. **LH-1** (real list/page mockups) — biggest fidelity jump.
3. **EC-1** (`--diff`) — highest-value new capability; plumbing already exists.

*2026-07-19: ⚡ quick wins QW-1..5 all shipped (`--open`/default path, `--coverage`, in-file audience/fluency toggle, before-launch to-do roll-up, status legend). 159 tests pass. Next candidates: LH-1 (real list/page mockups), AR-1 (single-source schema), EC-1 (`--diff`).*
