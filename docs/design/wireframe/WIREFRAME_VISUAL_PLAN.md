# Wireframe Visual Preview — Implementation Plan

**Version:** 0.2 (post-planning; paired with `WIREFRAME_VISUAL_REQUIREMENTS.md` v0.3.1)
**Date:** 2026-07-18
**Status:** Draft

Maps every `FR-WV-*` to concrete files. The dominant move is **reuse**: the summary math, the section
narration, and the HTML delivery pattern all already exist — this plan wires them into one file, and adds
only the two genuinely new pieces (the outline→mockup renderer and the `--html` flag).

## Architecture (three parts, mirroring kickoff_view)

```
plan JSON (schema_version N)  ──┐
descriptive.yaml (what/why)   ──┼─▶  wireframe_view/compose.py  ─▶  wireframe_view/_template.py
footer_lines() (summary math) ──┘        (pure: plan → view-model)      (HTML shell, embedded escaped JSON,
                                                                          client JS renders outline+mockups)
                                                             ▲
                                          cli_wireframe.py  --html <path>  (atomic write, advisory)
```

- **New:** `src/startd8/wireframe_view/` — sibling of `kickoff_view/` (OQ-B resolved). `compose.py`
  (plan → view-model), `_template.py` (the self-contained HTML shell + client renderer), `__init__.py`.
- **Reused verbatim:** the escape-first embed helper from `kickoff_view.view.render_html`; `footer_lines`,
  `plan_body`, `content_completeness`; `descriptive.yaml` via `describe.py` (`describe`/`describe_summary`).

## Steps

- **M-WV0 — View-model (FR-WV-2/3/5/9).** `compose(plan) -> dict`: the summary band (from `footer_lines`
  + `shape`/`status_counts`/`content_completeness`/`readiness`) + the section outline (`sections[]`
  mapped 1:1, each item carrying status/detail/paths) + per-section narration (from `describe`/
  `describe_summary`). Pure, deterministic. **Includes the form-field parser** (`detail` →
  `{shown:[…], omitted:[…]}`; unparseable → `None`, item keeps raw detail). This is the one new bit of
  logic; unit-test it against the real strtd8 `detail` strings.

- **M-WV1 — HTML shell (FR-WV-1/6/7).** `_template.py`: a `<!doctype html>` page with embedded CSS + JS,
  **no CDN**. Embed the view-model as escape-first JSON (`kickoff_view` pattern — escape `<` on embed;
  `application/json` is never executed). Client JS reads it and renders. Byte-identical for identical
  input modulo the timestamp. `schema_version` guard → visible banner on mismatch.

- **M-WV2 — Outline renderer (FR-WV-2/3/5/8).** Client JS: pinned summary band on top (inverted pyramid);
  collapsible section nodes below; each node shows badges (status glyph, count, content %, AI-boundary)
  + the WHAT/WHY from narration. Honest states: `not_defined`/`placeholder`/`invalid` greyed + badged.

- **M-WV3 — Drill-to-mockup renderer (FR-WV-4/9).** Client JS: expanding a **page** → framed screen with
  the default nav bar; **form** → labeled field skeleton (shown fields as `label [____]`, omitted fields
  listed as server/AI-owned); **list/CRUD** → table skeleton (columns from the entity). Pure CSS boxes,
  no images. Fabricates nothing — driven by the M-WV0 view-model only.

- **M-WV4 — CLI wiring (FR-WV-1).** `cli_wireframe.py`: add `--html <path>` (Typer Option). Compose →
  render → atomic write (temp+rename; unwritable dir → warning, exit 0). Print the written path.
  Independent of `--json`/`--describe` (may combine). `--json` byte-identity preserved.

- **M-WV5 — Tests (FR-WV-6/9).** `tests/unit/wireframe/test_visual.py`: (a) `compose(plan)` deterministic
  + covers every section key; (b) form-field parser round-trips real `detail` strings and returns `None`
  (not fabricated fields) on garbage; (c) `--html` writes a self-contained file — **no `http`/`https`/
  `src=`/`cdn` external refs** (grep the output); (d) `schema_version` mismatch → banner marker present;
  (e) golden: same plan → byte-stable HTML modulo timestamp.

## Mapping (every FR has a step; every step traces to an FR)

| FR | Step |
|---|---|
| FR-WV-1 (self-contained HTML) | M-WV1, M-WV4 |
| FR-WV-2 (inverted-pyramid summary) | M-WV0, M-WV2 |
| FR-WV-3 (browsable outline) | M-WV0, M-WV2 |
| FR-WV-4 (drill-to-mockup) | M-WV3 |
| FR-WV-5 (metadata + narration) | M-WV0, M-WV2 |
| FR-WV-6 (deterministic/$0/no-LLM) | M-WV1, M-WV5 |
| FR-WV-7 (versioned embedded data) | M-WV1 |
| FR-WV-8 (honest rendering) | M-WV2 |
| FR-WV-9 (bounded fidelity, no fabrication) | M-WV0 (parser), M-WV3, M-WV5 |

## Risks / discoveries fed to requirements §0

- Form fields live in `detail` prose, not structured data → parse-first (FR-WV-9); the parser is the
  single fragility point → it degrades to raw detail and is the most-tested unit (M-WV0/M-WV5).
- Summary + narration already exist → reuse, don't rebuild (FR-WV-2/5). The only new logic is the
  view-model composer + the client mockup renderer.
- `kickoff_view` proves the self-contained-escaped-HTML pattern works in this SDK → M-WV1 copies its shape.
- `schema_version` coupling: the HTML embeds a versioned body → mismatch must degrade visibly (M-WV1).

## Review log
*(scaffold — CRP suggestions land here as `#### Review Round R{n}` under Appendix C)*

### Appendix A: Applied Suggestions
*(none yet)*

### Appendix B: Rejected Suggestions (with Rationale)
*(none yet)*

### Appendix C: Incoming Suggestions (Untriaged, append-only)
*(awaiting first CRP round)*
