# Wireframe Visual — Enhancement Backlog

**Date:** 2026-07-19
**Status:** Living backlog (prioritized)
**Scope:** the stacked capabilities we built — **FR-WV** (`--html` preview), **FR-AUD** (audience layer),
**FR-SHC** (content coverage guard), and **the pattern itself** (proven twice: the wireframe preview +
the benchmark-portal `/start`). Grounded in the residuals/OQs surfaced during the build.

Effort key: **XS** trivial · **S** small · **M** medium · **L** large.

---

## ★ Round 2 — Top findings (post-arc pass, 2026-07-19)

*Run after the full arc shipped (QW/LH/AR/EC all ✅). Grounded in the as-built code, not the narrative.
Lead item is a verified built-but-unwired defect; the rest wire what already exists.*

**Grounding note (belief→actual corrections):** I believed `--audience`/`--fluency` were global flags
that voiced *every* surface; grounding showed they reach `--html` + `--view-json` only and silently
no-op on the default `--describe` terminal surface (runtime-proven below). I believed the EC-2 export
"feeds the kickoff loop" (my own EC-2 commit says so); grounding found **no consumer** of a `*-signoff.json`
anywhere in `src/`+`tests/` — the wire's far end is unconnected. Both corrected the answer.

1. **★ DEFECT (built-but-unwired) — `--audience`/`--fluency` silently no-op on the terminal `--describe`
   surface.** `render_plan()` takes no `role`/`fluency` (`render.py:292`); it calls `describe_summary(plan)`
   (`render.py:320`) and `_describe_sections(plan)`→`describe_section(section, plan)` (`render.py:340-351`),
   both defaulting to `architect`. The CLI captures `--audience` but only threads it into `render_to_file`
   / `view_model_json` (`cli_wireframe.py:200,240,265`), never into the two `render_plan()` calls
   (`cli_wireframe.py:247,249`). **Runtime proof:** `--describe`, `--audience pm --describe`, and
   `--audience end_user --describe` emit a byte-identical architect `WHY:` line. So a user asking for the
   plain or PM voice in the terminal silently gets architect jargon — the FR-AUD layer is fully built and
   reaches the HTML/JSON surfaces but never the *default* one. The plumbing all exists (`describe`,
   `describe_summary` already accept `role`/`fluency`); it just isn't threaded through `render_plan`.
   → so a terminal user can read the preview in the voice they asked for, instead of the flag lying. — **S**
   *Closure-Ledger row:* `CL-WV-AUD-TERM | --audience/--fluency wired to --html/--view-json but not the
   terminal --describe tree | Now: L2 (built + wired for 2 of 3 surfaces; silent no-op on the default one)
   | Gate: thread role/fluency through render_plan + _describe_sections + describe_summary; add a test that
   `--audience end_user --describe` ≠ architect | Value at L4: the audience layer works on every surface,
   not just the opt-in ones.*

2. **Validate `--audience`/`--fluency` against the known set (a typo silently degrades to architect).**
   `--audience` is a free `str` (`cli_wireframe.py:85`); an unknown value (`--audience pdm`, a typo) is
   indistinguishable from `architect` — the resolver degrades unknown roles to base with no signal. The
   known set is already enumerable (`delivery_roles.BASE_VOICES + KITS` + `end_user`). Reject/​warn on an
   unknown role. → so a mistyped role fails loudly instead of silently showing the wrong voice. — **XS**

3. **Latent (dormant trap) — a kit's authored section override would be invisible in the HTML toggle.**
   `render_html` embeds only the base-voice variants (`view.py` `_EMBED_COMBOS`) + the CLI default; the
   client `resolveVM` maps every kit to its base variant. So if someone later authors a `pm`-specific
   section override in `descriptive.yaml`, `--view-json --audience pm` and `--audience pm --describe` (once
   #1 lands) would honor it but the **HTML toggle would silently show the base voice**. Dormant today (no
   kit override authored — EC-4 shipped lenses only), so it's a trap, not an active break: embed a kit
   variant iff `compose(kit) != compose(base)`, or document kit overrides as CLI-only. — **S**

<details>
<summary>Round 2 — appendix (grounded, below the fold)</summary>

- **🌱 Surface the delivery-role lens in the terminal.** The EC-4 lens (`delivery_roles.lens_for`) rides in
  the compose audience block but `--describe` never calls `compose` — so `--audience pm --describe` shows no
  lens. Once Top-#1 threads role through `render_plan`, add a one-line lens header for a kit role. — **XS**
- **🚀 Sign-off importer — wire EC-2's far end.** The `Export sign-off` JSON (app/audience/per-section
  status+note) is consumed by nothing (grep-confirmed). An importer that reads it into the kickoff/approve
  loop is what makes "feeds the kickoff loop" true rather than aspirational. — **M**
- **🚀 Connect approve ↔ diff (EC-2 ↔ EC-1).** The sign-off records the snapshot you approved; `--diff`
  already computes planned-vs-built from `inputs_fingerprint`. Feed the sign-off's approved snapshot as
  `--diff`'s baseline so "what changed since **you** approved" is literal, not "since last save". — **M**
- **Honest gaps (decisions, not bugs):**
  - **EC-2 export feeds nothing yet — by my own EC-2 scoping** ("importer beyond EC-2's M"). Confirm
    export-only is the intended interim, or promote the importer above.
  - **`--fluency` help already scopes to "the `--html` end-user voice"** (`cli_wireframe.py:91`), so the
    terminal no-op may be *intended* for fluency — but `--audience` help says "the preview" (ambiguous).
    Top-#1 assumes the default terminal surface *should* be audience-aware; confirm that's the intended shape
    before wiring, or make both flags say "affects `--html`/`--view-json` only" and warn when combined with
    a bare `--describe`.

</details>

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
- ✅ **LH-3 — Finish fluency coverage** — fluency (beginner "Fuller" / advanced "Terser") was authored on
  only 3 of 11 records, so the depth toggle was a no-op on the other 8. Authored beginner + advanced for
  all remaining sections (scaffold, deployment, services, pages, views, display, content, completeness) —
  each overrides `what`/`wont`/`need` and lets `do`/`next`/`title` degrade (sparse per-field, FR-AUD-1).
  Now every section changes with the toggle; verified jargon-free (FR-AUD-C1) across all depths; FR-SHC
  coverage still 100% (fluency is optional enrichment). Content-only, no code. — **S**

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
- ✅ **EC-4 — The pattern → the delivery-role kits** — the 11 FR-J delivery roles now register as **kits**
  (`wireframe/delivery_roles.py`, keyed on `HITM_ROLE_MODEL_REQUIREMENTS.md` §3 — cited, not restated).
  Each declares a **base voice** it overlays (plain `end_user` / technical `architect`) + a one-line
  **lens**; the resolver makes an unauthored kit inherit its base voice's content, so `--audience pm`
  renders plain and `--audience backend-dev` technical with **zero per-section authoring**. Exposed via the
  HTML role toggle (base voices + 10 kits, each with a focus-lens banner), `--audience`, and `--coverage`.
  The AR-2 pattern's "a new audience is a config away" — proven: 10 audiences from a ~40-line registry +
  a resolver fallback, no content matrix. 170 tests pass; live-verified. — **M**

---

## Standard extracted (Hansei — grounded in the 14 shipped enhancements)

The arc proved a repeatable shape for enhancing this class of surface — a **deterministic, offline,
single-file, audience-keyed preview**. Reuse it for the next one (here or on a sibling surface):

1. **Two invariants are the guardrails — never break them, and they let everything else grow safely.**
   *Self-contained/offline* (no CDN/network — `test_html_is_self_contained`) and *deterministic* (same
   plan ⇒ byte-identical HTML — `test_html_is_deterministic`). Every new capability that touches runtime
   (EC-3 live-reload, EC-2 sign-off) is made **opt-in with a `None`/default-off path that stays
   byte-identical**, so the guarantee holds. If a feature can't be made opt-in-preserving, redesign it.
2. **The resolver (`describe._variant`) is the crux — every audience-axis change is a resolver change.**
   It has been reworked 8+ times across the FR-AUD lineage and still broke on EC-4 (a kit leaked the
   architect voice, against its own R1-F3 rule). So: **write the per-field sparse-degrade test _first_** —
   assert the overlay inherits the base for authored fields **and** does not leak for base-omitted fields.
3. **Push logic out of the template into `compose` (data), not the other way.** The single-file constraint
   makes `_template.py` a complexity sink (client JS grew +87/+83/+56 lines across QW/EC-2/EC-4). AR-3
   (mockup `multiline`) and LH-2 (`--view-json`) moved derivations into the composer so *other* surfaces
   can consume them — keep doing that; resist adding client-side derivation.
4. **"Byte-identical" must name its scope.** Rendered *narration* is pinned; *metadata* blocks (the
   `audience` object) are expected to grow — subset-check them, don't assert exact equality (EC-4 broke 3
   such assertions).
5. **Ground before designing, and let the tests shrink the change.** AR-3 was made smaller by an existing
   test (`pages carry no mockup`) that encoded a prior decision. Read the tests + grep the real blast
   radius *first*; a suspected doc-drift dissolved the same way (it was ✅-placement, not drift).
6. **The loop that worked, per enhancement:** name it in this backlog with an effort tag → ground the seam
   (grep real consumers + read the guarding tests) → build the smallest coherent slice → live-verify
   (devtools, 0 console errors) **and** run the self-contained blast radius (`tests/unit/wireframe/`) →
   mark ✅ + append a dated line here. Ship in small, individually-verified units (14 of them, monotonic
   test count 159→170), not one big drop.

*Honest scope note: the suite run each step was `tests/unit/wireframe/` (170), not the whole SDK — adequate
because the seam has no consumers outside wireframe/ + the CLI's terminal `--describe` (verified separately),
but a full-suite run belongs in the pre-merge gate.*

## Do-first shortlist
1. **QW-1** (toggle) — biggest usability jump, small effort.
2. **LH-1** (real list/page mockups) — biggest fidelity jump.
3. **EC-1** (`--diff`) — highest-value new capability; plumbing already exists.

*2026-07-19: ⚡ quick wins QW-1..5 all shipped (`--open`/default path, `--coverage`, in-file audience/fluency toggle, before-launch to-do roll-up, status legend). 159 tests pass. Then LH-1 (real list mockups — 31 entities get real columns) + AR-1 (schema single-sourced into describe.py's resolver; drift-guard test; closes CL-17 L4) shipped. Then EC-1 (`--diff` planned-vs-built) shipped — the verify half of preview→approve→build→verify. Then LH-2 (`--view-json` — the audience view-model as data for a web app/portal) + AR-2 (the audience pattern named + documented as AUDIENCE_CONTENT_PATTERN.md — the Yokoten of a design used 3×) shipped. Then AR-3 (data-complete MOCKUP_SPEC.md + multiline lifted into the composer) + EC-2 (per-section approve/flag/annotate sign-off, localStorage + JSON export — the preview's `approve` verb) shipped; 167 tests pass, live-verified (0 console errors). Then EC-3 (`--watch` live-reload, mirroring the kickoff_view seam) + LH-3 (fluency authored for all 11 records — the depth toggle now bites everywhere) shipped; 169 tests pass, live-verified. Then EC-4 (the 11 FR-J delivery-role kits — overlays on the two base voices; `--audience pm/backend-dev/…`; the AR-2 "config away" promise proven) shipped; 170 tests pass, live-verified. **The wireframe-visual enhancement backlog is now fully shipped (QW-1..5, LH-1/2/3, AR-1/2/3, EC-1/2/3/4).***
