# Workbook × Audience Personalization — Implementation Plan

**Version:** 1.1 (paired with REQUIREMENTS v0.3; phantom-ref fix: `build_and_maybe_provision`)
**Date:** 2026-07-08
**Status:** Draft (reflective-requirements loop; pre-CRP)
**Scope:** Era 1 only (classic schema). Slice A (tiered intro) + Slice B (audience-default badge).

---

## 0. Approach

Two independent, small changes joined at `portal_build` (the I/O boundary):

- **Slice A (disclosure):** resolve the audience once in `portal_build` → pass a `tier` into the pure
  `build_kickoff_portal_spec` → `_overview_panels` renders the intro from a **new tiered workbook
  experience doc** instead of the inline string.
- **Slice B (surface):** pass the **ledger provenance map** (read once in `portal_build`) into the spec
  builder → `_manifest_section` renders audience-default rows with an override glyph; `_overview_panels`
  discounts shielded fields from the gap-facing widgets.

Both keep `build_kickoff_portal_spec` **pure** (all I/O — audience resolution, ledger read — happens in
`portal_build` and is passed in as data). Both are **fail-open**: absent audience → Intermediate/`light`
→ byte-identical intro; absent/empty ledger → no badges → byte-identical rows.

**Dependency order:** FR-9 (public predicate) → FR-1 (plumb params) → {FR-2/FR-3/FR-4 Slice A} ∥
{FR-5/FR-6/FR-7/FR-8 Slice B}. Slices A and B are independent after the plumbing lands.

---

## 1. Steps

### Step 1 — Public audience-default predicate (FR-9)
**File:** `src/startd8/concierge/confirmation.py`
- Add a public `is_audience_default(entry) -> bool` (thin wrapper over / rename target of the existing
  private `_is_audience_default`) and `audience_default_slug(entry) -> str | None` (returns the `<slug>`
  after the `audience-default:` prefix, or `None`). Keep `_is_audience_default` as a private alias if any
  internal caller uses it, or repoint callers. Export via `__all__` if the module has one.
- **Test:** unit — explicit entry (no provenance) → `False`; `audience-default:project` entry → `True`,
  slug `"project"`; malformed entry → `False`.
- *Why first:* `portal_spec` must read provenance without reaching a private symbol (single-source the
  `AUDIENCE_DEFAULT_PREFIX` logic in `confirmation.py`).

### Step 2 — Plumb audience + provenance into the spec builder (FR-1, FR-6)
**Files:** `src/startd8/kickoff_experience/portal_build.py`, `portal_spec.py`
- In `portal_build.build_and_maybe_provision` (the I/O caller that calls `build_kickoff_portal_spec` at
  `portal_build.py:286`; has `root`): after building `state`, resolve
  `res = resolve_audience_preference(root)`, `tier = disclosure_tier(res.value)`, and
  `ledger = load_ledger(root)` (tolerant). Reuse the exact pattern from
  `concierge_view._build_audience_block`.
- Extend `build_kickoff_portal_spec(state, project, *, roster=None, panel_results=None, pipeline=None,
  audience=None, tier="light", provenance=None)` — new **keyword-only, defaulted** params so every
  existing caller/test stays green (defaults reproduce today's output exactly). `provenance` = the
  `{value_path: entry}` ledger map (or `{}`).
- Thread `tier` into `_overview_panels(...)` and `provenance` into both `_overview_panels(...)` and each
  `_manifest_section(manifest, fields, provenance)`.
- **Test:** existing `test_portal_spec` snapshot with defaults → unchanged (byte-identical guard).

### Step 3 — Tiered workbook experience doc (Slice A: FR-2, FR-3, FR-4, OQ-4)
**Files:** `src/startd8/concierge_templates/KICKOFF_WORKBOOK_INTRO.md` (new),
`src/startd8/concierge/writes.py`, `portal_spec.py`
- **Author** `KICKOFF_WORKBOOK_INTRO.md`: the narrative intro (Brooks' workbook framing, KickoffState
  projection, refresh) with `<!-- PLAIN -->…<!-- /PLAIN -->` (Beginner) and `<!-- TL;DR -->…` (Advanced)
  regions. The `light` body (markers stripped) MUST equal today's intro prose **byte-for-byte** (persona
  FR-4). *(Verify with a test that pins `load_experience_doc("workbook", tier="light")` == the current
  intro narrative.)*
- **Register** `"workbook": "KICKOFF_WORKBOOK_INTRO.md"` in `_EXPERIENCE_DOCS` (writes.py).
- **Render** in `_overview_panels`: replace the inline `intro = (...)` narrative with
  `load_experience_doc("workbook", tier=tier)`; keep the appended dynamic status line + legend table
  **code-side** (they are state, not prose — OQ-4 seam). Lazy-import `load_experience_doc` to avoid a
  cycle (same convention as the `explain_input_domain` import in `_manifest_section`).
- **OQ-3 (if accepted):** append a one-line "_Rendered for: {audience} — re-run `kickoff portal` if your
  audience changes._" when `audience` is a non-default/Beginner/Advanced (skip for Intermediate to
  preserve byte-identity).
- **Test:** `tier="expanded"` renders the PLAIN region; `tier="compact"` the TL;DR; `tier="light"`
  byte-identical to legacy intro; unknown/missing markers degrade to `light` (fail-closed, no raw leak).

### Step 4 — Audience-default badge in field rows (Slice B: FR-5, FR-8)
**File:** `src/startd8/kickoff_experience/portal_spec.py`
- Add an audience-default presentation entry, e.g. `_AUDIENCE_DEFAULT_DISPLAY = ("🛡️", "safe default set
  for you")` and a sort rank (OQ-1) — place it between `ok` and `review`, or its own rank; decide in
  build (leaning: rank just after `ok`, since it's a resolved-for-you state, not a gap).
- In `_manifest_section(manifest, fields, provenance)`: for each field, if
  `is_audience_default(provenance.get(f.value_path))`, render the override glyph/label **instead of** the
  extraction `_ATTENTION_DISPLAY[f.attention]`, and use the audience-default sort rank. Otherwise
  unchanged. Value column: show the shielded value (it's a real set default).
- FR-8 falls out automatically: once `kickoff confirm` strips the provenance, `provenance[vp]` no longer
  matches → normal ✅ confirmed row on the next build. No extra code.
- **Test:** field with `audience-default:project` provenance → 🛡️ row; same field after provenance
  stripped → normal row; field absent from ledger → extraction glyph unchanged.

### Step 5 — Honest overview counts (Slice B: FR-7, OQ-2)
**File:** `src/startd8/kickoff_experience/portal_spec.py` (`_overview_panels`)
- Compute `shielded = {vp for vp, e in provenance.items() if is_audience_default(e)}`. Discount fields in
  `shielded` from the **gap-facing widgets only** (OQ-2): the "Open Gaps (author action)" stat and the
  `**{blocked} gaps**` figure in the intro status line. Leave the `Fields Confirmed` gauge and per-domain
  `slug · confirmed` ratios on their extraction basis (a shielded field is neither a gap nor a human
  confirmation — NR-6). Optionally add a small "N set for you" figure to the status line.
- **Edge:** a shielded field's extraction `attention` may be `blocked` (gap) OR `ok` (if also extracted).
  Only discount from the gap count those whose extraction attention is `blocked` **and** are shielded, so
  the count can't go negative. Pin this in a test.
- **Test:** board with 3 blocked fields, 2 of them shielded → "Open Gaps" stat shows 1, not 3; gauge
  unchanged; no-ledger board → counts identical to today.

### Step 6 — Docs + capability note
- Update `WORKBOOK_AUDIENCE_PERSONALIZATION_NEXT_STEPS.md` status line to "era-1 A+B → REQUIREMENTS/PLAN;
  building" (or leave next-steps as the research record and cross-link the new pair).
- If the Workbook capability is indexed, note audience-awareness (era 1) — defer to `/capability-index`.

---

## 2. Requirement → Step Traceability

| Requirement | Step(s) |
|---|---|
| FR-1 (resolve in caller, pass params) | 2 |
| FR-2 (tiered workbook doc) | 3 |
| FR-3 (register key) | 3 |
| FR-4 (render intro at tier) | 3 |
| FR-5 (audience-default override state) | 4 |
| FR-6 (fail-open join) | 2, 4 |
| FR-7 (honest counts) | 5 |
| FR-8 (transient badge) | 4 (falls out) |
| FR-9 (public predicate) | 1 |
| FR-10 (regen is the trigger) | inherent (no code) |

## 3. Testing Strategy

- **Byte-identity guard (the load-bearing test):** Intermediate audience + empty ledger ⇒
  `build_kickoff_portal_spec` output **identical** to pre-change. This protects persona FR-4 and Workbook
  NR-3 at once. Assert on the full spec dict, not just panels.
- **Per-slice unit tests** as listed per step (writes.py tier slicing, portal_spec rows/counts).
- **Fail-open tests:** missing `build-preferences.yaml`, missing/malformed `confirmed.yaml` → no crash,
  degrade to today's board.
- Run: `PYTHONPATH=<worktree>/src pytest tests/unit/kickoff_experience/ tests/unit/concierge/ -q`
  (per the multiworktree PYTHONPATH pin).

## 4. Risks / Watch-items

- **R1 — Byte-identity of the moved intro (FR-2).** Moving the narrative into a template risks a
  whitespace/markdown drift vs the inline string. Mitigation: a golden test pinning
  `load_experience_doc("workbook", tier="light")` to the exact legacy narrative; author the doc by
  copying the current bytes.
- **R2 — Gap-count underflow (FR-7).** Naive subtraction can go negative or double-count. Mitigation:
  discount only `blocked ∧ shielded` (Step 5 edge). Test with overlapping states.
- **R3 — Provenance is the extraction↔ledger seam.** `FieldState` (extraction) and the ledger are two
  independent sources joined by `value_path`. A value_path mismatch (e.g. schema drift) silently drops a
  badge (fail-open, acceptable) but must never crash. Mitigation: `.get(vp)` with `None`-tolerant
  predicate; test a value_path present in ledger but absent in state and vice-versa.
- **R4 — Era-2 reuse.** Keep the tier-selection and provenance→glyph logic as small pure helpers so era 2
  (dynamic-dashboards M6) can reuse them behind a runtime variable rather than a baked value.

## 5. Out of Scope (see REQUIREMENTS §3)

Live switching (era 2), per-domain prose tiering (Slice C), per-field panel split, any write path, new
extraction attention values.
