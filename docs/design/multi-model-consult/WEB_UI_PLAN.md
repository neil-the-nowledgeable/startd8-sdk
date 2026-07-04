# Consultation Web View — Implementation Plan

**Version:** 1.0 (Post-reflection)
**Date:** 2026-07-03
**Status:** Draft — pairs with `WEB_UI_REQUIREMENTS.md` v0.3
**Build tool:** `/frontend-design` for the HTML/CSS/JS; Python glue in `consultation/` + `cli_consult.py`.

---

## A. Discoveries (what planning revealed)

| Requirements assumed | Planning revealed | Consequence |
|----------------------|-------------------|-------------|
| Serve from an endpoint | `server/app.py` is a workflow server; `file://` can't `fetch()` a sibling JSON | Self-contained HTML with **embedded** JSON; no server |
| Render images | `session.json` has no bytes (FR-MMC-6a) | Image **indicators** only (filename + short hash) |
| New render path | `comparison_text/table` already render the session | Add `render_html()` **beside** them in `view.py` |
| Drop text in HTML | Model text is untrusted; paths would leak | Escape/sanitize + filename-only (FR-WUI-9) |

The feature is genuinely small: **one pure render function + one CLI subcommand + a static template.**
The only non-trivial parts are (a) safe embedding of untrusted text, and (b) a dependency-free
markdown/collapse UX — both squarely `/frontend-design` + a small amount of Python.

## B. Milestones

### M0 — Design lock (this doc set). Offer CRP before build.

### M1 — `render_html(session)` in `consultation/view.py` (FR-WUI-2/4/5/6/7/9)
1. Pure function `render_html(session: ConsultationSession) -> str` returning a complete HTML
   document string. Co-located with `comparison_text`/`comparison_table` (sibling renderer).
2. Serialize the session to a **safe JSON payload**: drop `source_path` down to *basename*; keep
   sha256(short)/mime/size, statuses, tokens, turn text. Embed as a `<script type="application/json">`
   block (JSON is HTML-safe inside that element when `</` is escaped) **or** pass through the
   template's escaping — decide in M2.
3. Structure per model: a `<details>`/panel per `roster` entry containing its ordered `turns`
   (user/assistant), status + usage badges, header with prompt + image indicators.

### M2 — The HTML/CSS/JS template via `/frontend-design` (FR-WUI-2/3/8)
1. Invoke `/frontend-design` to produce a distinctive, responsive, accessible layout:
   - side-by-side model panels that **stack** on narrow screens;
   - **per-panel collapse/expand** (semantic `<details>` or a button + `aria-expanded`), plus
     **collapse-all / expand-all**;
   - role-styled turns, status colors (ok/failed/skipped), token/latency badges.
2. **Dependency-free**: no CDN, no build step; inline `<style>`/`<script>`; a tiny inline markdown
   renderer (or pre-render answers to sanitized HTML in Python — OQ-5).
3. **XSS-safe** (FR-WUI-9): all model text HTML-escaped before insertion; if markdown is rendered
   client-side, sanitize (escape first, then apply a whitelist of inline formatting only).
4. Apply `/universal-design` pass: focus states, keyboard toggles, contrast, screen-reader labels.

### M3 — `startd8 consult web` subcommand (FR-WUI-1)
1. `consult_app.command("web")`: arg `session_id`, `--out <path>` (default
   `.startd8/consultations/<id>/view.html`, OQ-4), `--open` (webbrowser.open).
2. Load via `ConsultationService.load`, call `render_html`, write the file, print the path.
3. Exit 2 on unknown session (consistent with the other `consult` subcommands).

### M4 — Tests + acceptance
1. `render_html` unit tests: contains each model id, each status, escaped text (inject
   `<script>alert(1)</script>` as a model answer → assert it's escaped, not live); image indicator
   shows basename not absolute path; no `source_path` absolute leak.
2. CLI test (`CliRunner`): `web <id>` writes the file, `--open` guarded; unknown id → exit 2.
3. Acceptance: run against the live-smoke session; open and verify collapse behavior manually.

### M5 — Optional (deferred)
- `--embed-images` (base64 thumbnails from `source_path` at render time) — NR-4/OQ-2.
- Collapse-failed-by-default (OQ-6); print/export.

---

## C. Risks
- **XSS via model output** — the central risk; escape-first is mandatory (M2.3). A test injects a
  script payload as an answer.
- **Path leakage** — absolute `source_path` must be reduced to basename before embedding (M1.2).
- **Offline-ness** — no CDN/build; everything inline, or the artifact fails to open air-gapped (NR-5).
- **Large answers** — long threads inflate the HTML; acceptable for a snapshot (no pagination in v1).

## D. Traceability
| FR | Milestone |
|----|-----------|
| FR-WUI-1 | M3 |
| FR-WUI-2/4/5/6 | M1 + M2 |
| FR-WUI-3 | M2 |
| FR-WUI-7 | M1 |
| FR-WUI-8 | M2 (`/frontend-design` + `/universal-design`) |
| FR-WUI-9 | M1.2 + M2.3 |

---

*v1.0 — The build is small and front-loaded on `/frontend-design` (M2). Python is a thin
`render_html` + one CLI subcommand over the shared session model.*
