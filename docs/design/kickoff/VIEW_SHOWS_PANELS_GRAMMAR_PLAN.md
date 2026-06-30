# View `Shows:` Panels Grammar — Implementation Plan

**Version:** 1.0 (Post-planning)
**Date:** 2026-06-29
**Pairs with:** [`VIEW_SHOWS_PANELS_GRAMMAR_REQUIREMENTS.md`](VIEW_SHOWS_PANELS_GRAMMAR_REQUIREMENTS.md) v0.2
**Closes:** lane D9 / spike F3 / REQ-VIEW

---

## Shape (from the planning pass)

The work is **two files of code + one contract doc + tests** — no `view_codegen` changes (the
`Panel{name,fields,show_when}` schema and the detail-compose renderer already exist). The grammar is
purely additive and byte-identical-when-absent.

```
S1  Contract §2.3 — document the `- Panel: Name = a, b, c` production    [doc]      FR-1,2,4,6
S2  extract_views — parse repeatable Panel lines → panels[]              [code]     FR-1,5,9
S3  extract_views — resolve fields against Root entity (flag-don't-guess)[code]     FR-3,8,9
S4  extract_views — kind-gate (detail-compose only) + off-archetype flag [code]     FR-2
S5  Tests — golden fixture + unit suite                                  [test]     FR-1..9
```

## S1 — Contract §2.3 grammar (doc)

In `KICKOFF_AUTHORING_CONTRACT.md` §2.3, under **Line micro-grammars**, add a `Panel:` bullet:

> - `Panel: <Name> = <field>, <field>, …` (detail-compose only) → a `panels` entry
>   `{name, fields, show_when: any_set}`: a named group of **Root-entity fields**, rendered only when
>   ≥1 field is non-empty. Each field resolves (case-tolerant, trailing parenthetical tolerated)
>   against the Root entity's §2.1 fields; an unknown field ⇒ `not_extracted` (named, dropped — never
>   guessed). Repeatable. On any non-detail-compose kind ⇒ `not_extracted(off-archetype)`.

- Bump the GRAMMAR_VERSION note v0.3 → **v0.4** (first post-VIP vocabulary growth).
- Add an Appendix A row (`VSP-G1`) recording the adoption + provenance (D9/spike F3).

## S2 — Parse repeatable Panel lines (`extractors.py` `extract_views`)

- `key_lines` keeps only the **first** value per repeated key, so **do not** read `Panel` from the
  `keys` dict. Add a module regex `_PANEL_LINE_RE = re.compile(r"^\s*-?\s*Panel:\s*(.+?)\s*=\s*(.+)$")`
  and scan `sec.body.splitlines()` for every match (mirrors the completeness-nudge body scan).
- For each match: `panel_name = strip_annotations(group(1))`; the RHS is the field list.
- Emit into `view.setdefault("panels", []).append({"name", "fields", "show_when": "any_set"})` — placed
  alongside the existing `Shows:`/`Also shows:` handling so it shares the view's record block.

## S3 — Resolve fields against the Root entity (flag-don't-guess)

- The graph exposes entities + their fields (`graph.entities[<EntityName>].fields`, each with `.name`,
  per §2.6/human_only usage already in this file). Build a case-tolerant lookup of the Root entity's
  field names once per view.
- Split the RHS on `,`; for each token strip a trailing ` (…)` parenthetical (OQ-4) and whitespace.
- Resolve to the canonical field name; **unknown** → append a `not_extracted` record
  (`/views/{vi}/panels/{name}/{token}`, reason `field {token!r} not on Root {root!r}`) and **drop that
  token** (FR-3). If a panel ends with **zero** resolved fields, drop the whole panel with a
  `not_extracted` record (don't emit an empty-fields panel — `parse_views` would accept it but it
  renders nothing).
- A panel with ≥1 resolved field → `extracted` record `/views/{vi}/panels/{name}` (FR-9). This makes
  the extractor the sole field guard (the round-trip gate doesn't pass `known_fields` — §0 OQ-3).

## S4 — Kind-gate to detail-compose (FR-2)

- A `Panel:` line on any kind other than `detail-compose` → `not_extracted`
  (`reason="`Panel:` is detail-compose-only (off-archetype)"`), the panel dropped. Mirrors the
  existing kind-gating posture (`Group by:`/`Scope:`).
- Genuinely-unstructured `Shows:` prose continues to hit the existing
  `not_extracted(prose)` branch unchanged (FR-6) — the Panel production is independent of it.

## S5 — Tests

- **Golden** (`tests/fixtures/manifest_extraction/kickoff.md` + `test_extract_golden.py`): add a
  `Panel:` line to the existing `Widget Wall` detail-compose (e.g. `- Panel: Details = name, tier`),
  plus one unresolved-field case; assert `views.yaml` carries the `panels` entry and the unknown-field
  `not_extracted` row.
- **Unit** (`tests/unit/manifest_extraction/`): resolution happy path; unknown field dropped + flagged;
  all-unknown ⇒ panel dropped; off-archetype (Panel on a dashboard) flagged; repeatable (two Panel
  lines → two entries); parenthetical tolerance; **byte-identical-when-absent** (a view with no Panel
  line emits no `panels` key); **round-trip** through `parse_views(known_entities=…)`.
- Run `tests/unit/manifest_extraction/ tests/unit/view_codegen/` — view_codegen unaffected (no schema
  change), so its suite must stay green untouched.

## Traceability

| FR | Steps |
|----|-------|
| FR-1 Panel production | S1, S2 |
| FR-2 detail-compose only | S1, S4 |
| FR-3 field resolution flag-don't-guess | S3 |
| FR-4 show_when any_set | S1, S2 |
| FR-5 repeatable | S2 |
| FR-6 prose still flagged | S4 |
| FR-7 byte-identical-when-absent | S2 (guarded append), S5 |
| FR-8 round-trips parse_views | S3, S5 |
| FR-9 two report rows | S2, S3 |

## Risks

- **Repeated-key trap** — using `keys.get("Panel")` would silently drop all but the first panel;
  S2 explicitly scans the body instead. Covered by the repeatable unit test.
- **Empty-fields panel** — a panel whose every field is unknown must drop entirely, not emit
  `fields: []` (renders nothing, misleads). Covered by the all-unknown unit test.
- **Scope creep to workspace** — resist; workspace is polymorphic-only (§0 OQ-2). Out of scope.
