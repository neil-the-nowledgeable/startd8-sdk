# Forms-Section Extraction (`extract_forms`) — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-08
**Status:** Plan (post-exploration) — **recommends DEFER; see Discovery D-5**
**Requirements:** `FORMS_EXTRACTION_REQUIREMENTS.md` (v0.2)

---

## Discoveries (planning pass over the v0.1 requirements)

| # | v0.1 Assumption | Planning Discovery |
|---|---|---|
| **D-1** | `extract_forms` is a separate extractor with its own `candidates[...]` slot (OQ-2 open) | **There is only ONE `views.yaml` candidate slot, governed by a `first-non-None-wins` guard** (`extract.py:100`). A separate `extract_forms` assignment would either overwrite `extract_views`' `{"views": [...]}` or be skipped by the guard; worse, across multiple docs the `forms:` could come from a *different* doc than `views:` and be dropped. The forms derivation **must fold into `extract_views`** (one extractor, one candidate, same doc scan). OQ-2 resolved → (b), and it's not optional — (a) is unsound here. |
| **D-2** | Round-trip validation needs wiring (FR-FX-5) | **Already wired.** `extract.py`'s round-trip for `views.yaml` already calls `parse_forms(t, known_entities=known)` (we added it as the gate-half). So an emitted `forms:` is validated with zero new round-trip code — FR-FX-5 is free. |
| **D-3** | The directive home is an open question between a `Forms:` section, an entity key-line, or a table annotation (OQ-1) | `key_lines()` parses `- Key: value` blocks from **any** section body; entities are *also* sections (`heading_path = ("Entities","ProofPoint")`) but are parsed as **tables** (`md_tables`), not key-lines — mixing a key-line into a table-bodied entity section is messy. A dedicated **`Forms:` (or `Post-create:`) section with `<Entity>: <archetype>` key-lines** mirrors `extract_views` exactly and reuses `key_lines` + `graph.resolve_entity` verbatim. OQ-1 → (a). |
| **D-4** | Ordering open (OQ-3) | Emit **sorted-by-entity** (the generator's deterministic-map convention) for byte-stability; `key_lines` preserves declaration order but sorting is the safer round-trip guarantee. Minor. |
| **D-5** | **The feature is worth building** (implicit) | **The real strtd8 corpus — 16 entities, the richest requirements set we have — contains ZERO prose describing per-entity post-create behavior.** No `Forms:`/`On create:` directives, no "after create go to X", and **no rapid/sequential-entry intent** anywhere (the primary `on_create: form` use case). All 16 entities implicitly accept the default `detail`. The derivation half has **no input to derive from** in practice. |

## The D-5 problem (the load-bearing finding)

The reflective heuristic: *if planning reveals >30% of the requirements need revision, they were
premature.* Here it's more fundamental than revision — planning reveals the feature's **input does
not exist** in the one real corpus:

- Per-entity post-create *override* is rare by construction (the default `detail` is right for
  standard CRUD; `form`/`list`/`confirmation` are niche).
- strtd8 (16 entities) expresses **no** such override in prose — not even informally.
- There is therefore nothing for `extract_forms` to extract. Building it now means shipping an
  extractor + teaching authors a `Forms:` convention, to derive a knob no real doc currently sets.
- The **gate-half already shipped** (round-trip validates a hand-authored `forms:`), so the *risk*
  the derivation half would address (a bad `forms:` reaching generation) is already covered.

This is the planning pass earning its keep: it caught a speculative build at **document cost**,
before an extractor nobody's prose feeds.

## Recommendation: DEFER (convention-gated), not WONTFIX

Don't build `extract_forms` now. **Defer until a real project authors a `forms:` override and asks
for it to be derived** — that demand is the missing signal. Two concrete triggers to revisit:

1. A project's requirements prose starts expressing post-create intent (e.g. "let users add several
   ProofPoints in a row") for ≥2 entities — i.e. hand-authoring `forms:` becomes repetitive.
2. The `forms:` knob grows (`on_update`/`on_delete`), raising the per-app override count past the
   hand-authoring break-even.

Until then, the **gate-half is the correct stopping point** (it's the high-value, low-cost half:
safety without speculation), exactly as `FORM_SUBMIT_BEHAVIOR` OQ-4 framed it.

## Build plan — IF/WHEN a trigger fires (kept ready, not executed)

The architecture is settled by the discoveries, so a future build is mechanical:

1. **Fold into `extract_views`** (D-1): after its `View:`-section loop, scan for a `Forms:`-titled
   section (D-3), parse `key_lines(sec.body)` as `<Entity>: <archetype>`, `graph.resolve_entity`
   each, validate the token against the four `on_create` archetypes, and attach a `forms:` key to
   the returned dict (`{"views": [...], "forms": {...}}`).
2. **Forensic records** (FR-FX-4): `ExtractionRecord("views.yaml", f"/forms/{Entity}", EXTRACTED,
   value=archetype, ...)`; `NOT_EXTRACTED` + reason for unknown entity/token.
3. **No round-trip change** (D-2) — already validates `forms:`.
4. **Default = silence** (FR-FX-6): no `Forms:` section → no `forms:` key → generator defaults all
   to `detail`.
5. **Tests**: section → map; unknown token/entity → NOT_EXTRACTED; co-emission of `views:` +
   `forms:` in one `views.yaml`, gate-green; byte-stable sort (D-4).

Effort if triggered: small (~½ day) — one folded scan, no new candidate/round-trip plumbing.

## Open questions — resolved

- **OQ-1 → `Forms:` section + key-lines** (D-3).
- **OQ-2 → fold into `extract_views`** — mandatory, not optional (D-1).
- **OQ-3 → sorted-by-entity** (D-4).
- **OQ-4 → name-only, schema-light** — the extractor resolves names; PK-suitability stays the
  generator's job (FR-FS-8 fallback). Confirmed (no change).
- **OQ-5 → DEFER** — no prose input exists in the real corpus; the gate-half is the right stopping
  point. **This is the plan's headline outcome.**
