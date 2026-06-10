# Generated UI trigger to run an AI pass (FR-AIT) — Requirements

**Version:** 0.1
**Date:** 2026-06-10
**Status:** IMPLEMENTED 2026-06-10 — FR-AIT-1..5 in `backend_codegen` (ai_layer `trigger:` + `app/ai/ui.py`
+ per-entity `_ai_triggers.html` + tolerant detail-template include + main.py mount). Proven by a
runtime test (POST → 303 redirect, `ai=ok` and `ai=unavailable`). 345 passed.
**Scope:** Close strtd8 `SDK_QUICK_WINS_2026-06-10` **#3**: AI passes ship **API-only** — there is no
generated UI affordance to *run* one, so a source-bound pass (FR-SBE) is unreachable without
hand-authored owned glue. Emit a "Run {pass}" button on a chosen entity's detail page that triggers
the pass server-side. **No new LLM** — this is bucket-1 reachability wiring.
**Component:** `backend_codegen/ai_layer.py` (manifest + trigger routes/partials),
`backend_codegen/htmx_generator.py` (detail-template seam), `backend_codegen/crud_generator.py` (mount).

## Problem

A source-bound pass generates `POST /ai/<route>` taking JSON `{text, source_id}`, but nothing in
`app/templates/**` POSTs to it (`grep` for any pass route in the generated UI returns nothing). So the
capability isn't reachable without owned glue — every FR-SBE adopter hand-writes the same trigger.

## Manifest surface (the one design choice — adopted, documented for the app team)

A pass opts into a generated trigger via a `trigger:` block in `ai_passes.yaml` (opt-in, not default —
consistent with the manifest-driven architecture; not every pass wants a button):

```yaml
- name: extract_document
  output_entities: [ProofPoint]
  route_path: /extract-document
  prompt: prompts/extract_document.md
  source_binding: sourceDocumentId
  trigger:
    entity: ImportedDocument        # whose detail page hosts the button (explicit — not derived)
    text_field: rawText             # the row field sent as `text`
    label: Extract proof points     # optional (default: "Run <name>")
```

`entity` is **explicit** (not derived from the source_binding FK) — deriving the referenced entity is
fragile, explicit is unambiguous and validated against the contract.

## Functional Requirements

- **FR-AIT-1 — `trigger:` manifest block.** `parse_ai_passes` parses an optional per-pass `trigger`
  (`entity`, `text_field`, optional `label`); both `entity` and `text_field` are required when
  `trigger` is present, else fail loud. Verify: a pass with a valid `trigger` parses; a `trigger`
  missing `entity`/`text_field` raises.

- **FR-AIT-2 — Generated trigger route.** When ≥1 pass has a `trigger`, emit `app/ai/ui.py` with an
  `ai_ui_router`: one `POST /ui/<entity>/{id}/run-<pass>` per triggered pass that loads the row, reads
  `text_field`, calls the pass module `(text, session, source_id=id)`, and **303-redirects back to the
  entity detail page** (`?ai=ok`). A keyless/unavailable provider degrades to `?ai=unavailable` (never
  a crash — composes with FR-40). Verify: the route loads the row, calls the pass with the row's text +
  id, redirects 303; an `AIUnavailableError` redirects with `ai=unavailable`.

- **FR-AIT-3 — Detail-page button via a tolerant seam.** `render_detail_template` includes
  `{% include "<e>/_ai_triggers.html" ignore missing %}` (manifest-free, a no-op when absent — the
  `user_routers` composition pattern). The AI layer emits `app/templates/<entity>/_ai_triggers.html`
  for each entity with ≥1 trigger: a `<form method="post">` button per pass + a flash reading
  `request.query_params.ai`. Verify: the detail template carries the tolerant include; the partial
  renders one form per trigger posting to the FR-AIT-2 route + the ok/unavailable flashes.

- **FR-AIT-4 — Mount tolerantly.** `app/main.py` mounts `ai_ui_router` via the same optional-import
  pattern as `ai_router` (present ⇒ mounted; absent ⇒ skipped). Verify: main.py carries the tolerant
  `from .ai.ui import ai_ui_router` mount block.

- **FR-AIT-5 — No-trigger projects unchanged.** A contract/manifest with no `trigger` emits no
  `ai/ui.py`, no partials, and a byte-identical detail template (the include is inert). Verify: a
  manifest without triggers produces no `app/ai/ui.py` and the detail template only gains the inert
  include line.

## Non-Requirements

- **Not HTMX/JS.** A plain `<form method=post>` + 303 redirect (PRG) — the team's "no HTMX needed."
- **No new pass semantics.** Reuses the existing source-bound pass module + FR-40 degradation.
- **Not emit-by-default.** Opt-in per pass; a pass without `trigger:` is unaffected.
- **No bespoke result rendering.** The flash is ok/unavailable; the pass's output rows surface on
  their own entities' pages as before.

## Acceptance

1. A manifest with a `trigger` emits `app/ai/ui.py` + `app/templates/<entity>/_ai_triggers.html`; the
   detail template gains the tolerant include; main.py mounts `ai_ui_router`.
2. The trigger route loads the row, calls the pass with `(row.text_field, session, source_id=id)`,
   redirects 303 to the detail page; unavailable → `ai=unavailable`, app stays up.
3. A manifest without triggers is unchanged except the inert include line (FR-AIT-5).
