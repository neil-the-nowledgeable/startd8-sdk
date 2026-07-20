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

- ✅ **LH-1 — Expose entity `fields[]` in the plan JSON** → real **list mockups** (actual columns) + richer
  **page mockups**. Fields are already parsed from `schema.prisma`; they just don't reach the view-model.
  Single biggest *fidelity* jump. (OQ-WV-2) — **M**
- ✅ **LH-2 — Expose the audience view-model as JSON** (`--view-json`) so other surfaces (a web app, the
  portal) reuse the benefit-first content. Turns FR-AUD into a data capability, not just HTML. — **S**
- **LH-3 — Finish fluency / other-role coverage** — fluency is authored on only 3 sections; either
  author the rest or declare it intentionally sparse (content pass). — **S**

## 🏗️ Architectural quick wins

- ✅ **AR-1 — Single-source the record schema** — `describe.py`'s resolver still hardcodes its field list;
  FR-SHC now *declares* `SECTION_SCHEMA`/`SUMMARY_SCHEMA`. Have the resolver read the declaration
  (KM-27 residual / CL-17 L4 gate). Removes a drift seam. — **S**
- **AR-2 — Extract the audience/onboarding pattern as a named capability** ✅ — applied *three* times
  (wireframe FR-AUD · portal `/start` · concierge fluency). Named + documented as the **Audience-Keyed
  Content Pattern** (`docs/design/descriptive-layer/AUDIENCE_CONTENT_PATTERN.md`): the four parts
  (single-source config · sparse-degrading resolver · benefit-first framing rules · coverage guard), the
  three reusable code seams cited (`describe._variant`, `compose.has_jargon`, `descriptive_schema`), and a
  5-step apply recipe — so the next surface is a config away, not a rebuild (Yokoten). Doc, not new
  machinery (Mottainai): the seams already exist; the pattern makes them discoverable. — **M**
- **AR-3 — Lift the mockup renderers out of the HTML string** ✅ — the mockup *contract* is now a
  documented, data-complete spec (`MOCKUP_SPEC.md`): the three kinds (form/list/page), their draw rules,
  and how a live app/portal consumes them from `--view-json`. The one renderer-side derivation left in JS
  — the multi-line-field regex — was lifted into the composer as `mockup.multiline` (`_multiline_fields`,
  single source), verified behavior-preserving (rendered DOM byte-identical bar the regex→data read).
  Page frames stay a *documented convention* over data the consumer already has (no fabricated mockup —
  `test_visual` guards it; Accidental-Complexity: don't bloat the embed). — **M**

## 🚀 Enhanced capabilities

- ✅ **EC-1 — `--diff` (planned-vs-built)** — `inputs_fingerprint` is already persisted *for exactly this*.
  "What changed since you approved" closes the loop: preview → approve → build → verify. Highest-value
  new capability. (OQ-8) — **M/L**
- ✅ **EC-2 — Approve / annotate** — the preview's verb is now *approve*. Every section carries a
  "✓ Looks right / ⚑ Flag this" control + an optional note; state persists in `localStorage` (app-scoped,
  offline, survives reload + audience toggle) and a header ✓/⚑ marker + a top sign-off bar ("N of M
  reviewed · K flagged") track progress. **Export sign-off** downloads a JSON artifact (app, audience,
  per-section status+note) — the sign-off that feeds the kickoff loop. Purely client-side (approve is
  user input, not derived): no composer/CLI change, determinism + self-contained preserved. — **M**
- ✅ **EC-3 — Live-reload / watch mode** — `startd8 wireframe --watch` live-follows the manifests: on
  every change it re-builds the plan + re-renders the preview, and an open browser auto-refreshes via an
  injected meta-refresh + LIVE banner (no server — mirrors the `kickoff_view` `--watch` seam, Mottainai).
  `ManifestWatcher` (poll/follow split, injectable sleep) watches the resolved input set; `render_html`
  gains `live_reload_secs` (`None` ⇒ byte-identical static file — the offline determinism guarantee
  holds). Author-in-the-loop: edit a manifest, watch the preview update. Live-verified end-to-end. — **M**
- **EC-4 — The pattern → the delivery-role kits** — FR-AUD supports role × fluency; only architect +
  end_user are authored. The FR-J roles (BA/PM/backend…) each getting a wireframe voice is a straight
  extension. — **M**

---

## Do-first shortlist
1. **QW-1** (toggle) — biggest usability jump, small effort.
2. **LH-1** (real list/page mockups) — biggest fidelity jump.
3. **EC-1** (`--diff`) — highest-value new capability; plumbing already exists.

*2026-07-19: ⚡ quick wins QW-1..5 all shipped (`--open`/default path, `--coverage`, in-file audience/fluency toggle, before-launch to-do roll-up, status legend). 159 tests pass. Then LH-1 (real list mockups — 31 entities get real columns) + AR-1 (schema single-sourced into describe.py's resolver; drift-guard test; closes CL-17 L4) shipped. Then EC-1 (`--diff` planned-vs-built) shipped — the verify half of preview→approve→build→verify. Then LH-2 (`--view-json` — the audience view-model as data for a web app/portal) + AR-2 (the audience pattern named + documented as AUDIENCE_CONTENT_PATTERN.md — the Yokoten of a design used 3×) shipped. Then AR-3 (data-complete MOCKUP_SPEC.md + multiline lifted into the composer) + EC-2 (per-section approve/flag/annotate sign-off, localStorage + JSON export — the preview's `approve` verb) shipped; 167 tests pass, live-verified (0 console errors). Next: EC-3 (served/live-reload), EC-4 (delivery-role kits), or LH-3 (finish fluency coverage).*
