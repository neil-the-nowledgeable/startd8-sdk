# CRP Focus — `editors:` archetype review (R1)

Weight these concerns; ground every suggestion in the actual `backend_codegen` source where possible.

1. **Drift / idempotency (highest priority).** FR-ED-10/FR-ED-15 rest on a *verified* claim: `fastapi-flow`
   is registered in no drift renderer, so `generate backend --check` exits 1 on a clean `flows:` app.
   Scrutinize: is the proposed editors drift path (S7, `_FORMS_KINDS`/`_check_forms_drift` model with the
   editor name in the `startd8-entity` header slot) actually sufficient for a single-editor byte re-render?
   Are there multi-editor / name-collision / empty-section edge cases that still false-flag drift?

2. **Reset vs. dirty-detection correctness (FR-ED-12).** Is the data-default + "store only if changed"
   rule airtight? Consider: a child whose *legitimate* desired override equals the source/default text;
   concurrent edits; whitespace-only differences; the resolver returning a value that changes between GET
   and POST. Does the rule ever lose a real edit or silently materialize a default?

3. **Security (FR-ED-14, anti-IDOR).** Is the server-side editable-set allow-list complete? Consider the
   parent-id in the route itself (who may open `<route>` for a given parent?), the `filter` being trusted,
   and field-level write scope (only `edit_field`, never other columns via form params).

4. **Seam / interface (FR-ED-9).** Fixed-module resolver convention vs. flows' `on_finish`: is the
   signature `(child_row, session) -> str` right? What about resolver exceptions at request time, and the
   `default_value`-omitted mode (OQ-10)?

5. **Plan completeness / sequencing.** Does every FR map to a step? Is FR-ED-15 truly independently
   shippable? Any missing step (CLI `--check` pass-through, provider entry-point, gates.py interaction)?
