# Wireframe Mockup Spec (AR-3 — draw the same sketches from data)

**Date:** 2026-07-19
**Status:** Contract doc (the renderer-agnostic mockup grammar)
**Source of truth:** `wireframe_view/compose.py` (`_item_view`) emits it; `--view-json` (LH-2) exposes it.

The lo-fi sketches in the HTML preview (`startd8 wireframe --html`) are drawn from a **structured
view-model**, not from prose. This doc is the contract for that structure, so another surface — a live
web app, the portal, a Figma export — can draw the *same* sketches from `startd8 wireframe --view-json`
without re-implementing the SDK's renderer. The reference renderer is `wireframe_view/_template.py`.

## The rule: structure only where derivable

A `mockup` is attached to an item **only where the composer can derive real structure** (Mottainai —
never fabricated). Two kinds are derived today; a third is a documented *drawing convention* over data
the consumer already has. `mockup: null` means "no derivable structure — draw the item as a labeled
row." An unparseable form `detail` degrades to `null`, never to invented fields.

## Kind: `form` (the `forms` section)

```jsonc
{
  "kind": "form",
  "entity": "Project",              // the record this form edits (drawn in the window title)
  "shown":     ["name", "summary"], // fields a person fills in, in order → one labeled box each
  "multiline": ["summary"],         // AR-3: subset of `shown` drawn as a text AREA (not a 1-line box)
  "omitted": {                      // fields NOT on the form — drawn as muted "filled automatically" tags
    "server_managed": ["id", "createdAt"],
    "owned": ["ownerId"]
  },
  "help": "2/5",                    // optional authored help coverage (renderer may show or ignore)
  "on_create": "Draft"             // optional default-on-create state
}
```

**Draw:** a window titled `"{entity} — add or edit"`; one labeled box per `shown` field (a taller text
area if the field is in `multiline`); a muted "filled in automatically" row listing `omitted.*`; Save /
Cancel actions. Empty `shown` → an empty-state ("no boxes for people to fill in").
`multiline` was a regex *inside* the renderer until AR-3; it now rides in the data (`_multiline_fields`,
the one source), so every surface draws identical text-area choices.

## Kind: `list` (the `entities` section) — LH-1

```jsonc
{
  "kind": "list",
  "entity": "Project",
  "columns": ["name", "status", "owner"]   // the entity's real user-facing columns (harvested from forms)
}
```

**Draw:** a window titled `"{entity} — list"`; a table with a `#` column + up to the first 6 `columns`
as headers, over ~3 skeleton rows. No `columns` → an empty-state ("a simple list").

## Convention: page frame (the `pages` section) — no mockup object

Page items carry `mockup: null` **by design** (a page has no derivable field/column structure —
`test_visual.py` guards this). A page sketch is a *convention* the consumer draws from data it already
has on the item + its section:

- **title** — the item `label`.
- **nav** — the sibling page labels in the same section (the first ~6), drawn as a top nav bar.
- **body** — a placeholder; for the technical voice the item `detail` may fill it.

Because it is derivable by the consumer (the section's items are right there), it is documented here
rather than duplicated into every page item's payload (Accidental-Complexity guard — don't bloat the
embed with data the consumer can compute).

## Consuming it

`startd8 wireframe --view-json --audience end_user` emits the whole view-model; `sections[].items[].mockup`
carries the above. Switch on `mockup.kind` for `form`/`list`; fall back to the page convention for items
in the `pages` section; render a plain labeled row for `mockup: null` elsewhere. Mockup structure is
**identical across audiences** (FR-AUD-4) — only the surrounding narration changes voice.

---

*Reference renderer: `wireframe_view/_template.py` (`formMock` / `listMock` / `pageMock`). Producer:
`wireframe_view/compose.py::_item_view`. Related: `WIREFRAME_VISUAL_REQUIREMENTS.md` (FR-WV),
`AUDIENCE_CONTENT_PATTERN.md` (the voice layer around these sketches).*
