# Workbook × Audience Personalization — Implementation Plan

**Version:** 1.2 (paired with REQUIREMENTS v0.4; CRP R1/R2 triaged)
**Date:** 2026-07-08
**Status:** Draft (CRP R1/R2 applied — ready to implement)
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
  `concierge_view._build_audience_block`. **Pass `res.value` (a `KickoffAudience` enum) as `audience=`,
  NOT `res` (the dataclass) nor a raw string (R2-S2).**
- **Error placement (R2-S7):** these two new calls MUST degrade to defaults on failure, NOT be swallowed
  by `build_and_maybe_provision`'s broad `except Exception` (`portal_build.py:~318`) — which would return
  a misleading `skipped_reason="generation failed: …"` and skip the whole board. Wrap each in its own
  tolerant guard (or place before the try) so a config/credential error degrades to `tier="light"` +
  empty provenance with a logged warning, and the board still generates.
- Extend `build_kickoff_portal_spec(state, project, *, roster=None, panel_results=None, pipeline=None,
  audience=None, tier="light", provenance=None)` — new **keyword-only, defaulted** params so every
  existing caller/test stays green (defaults reproduce today's output exactly).
- **`provenance` shape (R1-S6/R2-S5):** it is the **raw entry map** `{value_path: entry}` exactly as
  `load_ledger` returns it (entries `{value, at, mode[, provenance]}`, the `provenance` field optional).
  Do **not** pre-filter to a shielded set. `is_audience_default(entry)` is applied **at render time** so
  Step 5's `shielded` is the **single filtering locus**, and `_overview_panels`/`_manifest_section` share
  one predicate (no parallel already-filtered structure that could drift).
- Thread `tier` into `_overview_panels(...)` and `provenance` into both `_overview_panels(...)` and each
  `_manifest_section(...)`. **Internal call-site update (R2-S1): `portal_spec.py:450` currently calls
  `_manifest_section(manifest, by_manifest[manifest])` positionally — it MUST become
  `_manifest_section(manifest, by_manifest[manifest], provenance)`, or the new required param raises
  `TypeError` at runtime on any board with manifests (no existing test catches it).**
- **Non-dict tolerance (R1-S7):** a dict-shaped ledger with a scalar under some `value_path`
  (`{vp: "oops"}`) must render on extraction basis, not crash — `is_audience_default` returns False for
  non-dict; confirm the value column (`_value_snippet`) is non-crashing.
- **Test — byte-identity baseline (R2-S3):** there is **no** existing full-spec snapshot in
  `test_kickoff_portal_spec.py` (only structural assertions) — the "existing snapshot" must be **created
  new**. Freeze `build_kickoff_portal_spec(demo_state, "demo")` with **default** params **before** this
  change lands, store it, assert `==` after. Any diff with defaults is a regression (persona FR-4 / NR-3).

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
  - **Whitespace seam (R2-F6):** `load_experience_doc` returns `body.strip()` output; the current inline
    `intro` joins narrative→legend→status with `\n\n`. The concatenation MUST reproduce today's exact
    whitespace so the composed-panel golden doesn't fail for a non-functional reason.
- **OQ-3 (RESOLVED: yes):** append a one-line "_Rendered for: {audience.value} — re-run `kickoff portal`
  if your audience changes._" for a **non-default** audience. **Structurally gate** the append on
  `audience` being Beginner/Advanced (R1-S8): for Intermediate, do **not** append at all (an
  appended-then-blanked or trailing-whitespace variant would perturb the Intermediate byte-identity
  golden). Use `audience.value` for the token (R2-S2), never `str(audience)`.
- **Test — tier slicing + degrade guard (R1-S5):** `tier="expanded"` renders the PLAIN region;
  `tier="compact"` the TL;DR; `tier="light"` byte-identical to the legacy narrative; unknown/missing
  markers degrade to `light`. **Plus a positive marker-slice assertion** —
  `load_experience_doc("workbook","expanded") != load_experience_doc("workbook","light")` **and**
  `compact != light` — the ONLY guard against the silent degrade-to-`light` no-op (a mis-authored doc
  passes every byte-identity test because `light` is the pass case).
- **Test — two goldens (R1-S4):** (1) `load_experience_doc("workbook","light")` == the narrative
  substring bytes; (2) the **composed** overview panel dict (narrative + legend + status line) for a
  **fixed** `KickoffState` == pre-change. Separates the movable prose from the dynamic status line.

### Step 4 — Audience-default badge in field rows (Slice B: FR-5, FR-8)
**File:** `src/startd8/kickoff_experience/portal_spec.py`
- **Lock the glyph (R1-S1):** `_AUDIENCE_DEFAULT_DISPLAY = ("🛡️", "safe default set for you")` — 🛡️ is
  **locked** (not `✅`, which collides with the legend and `_ATTENTION_DISPLAY["ok"]`). Reconciled with
  REQUIREMENTS FR-5 (v0.4 no longer says `✅`). Add a test: rendered audience-default glyph ≠
  `_ATTENTION_DISPLAY["ok"][0]`.
- **Lock the sort rank (R1-S2):** audience-default rows sort **with/after `ok`** (a rank ≥ 3 against
  `_ATTENTION_SORT = {blocked:0, review:1, backlog:2, ok:3}`) — **never** at `blocked`'s rank 0. Otherwise
  a shielded field whose extraction attention is `blocked` re-sorts to the top as a gap, contradicting
  FR-7. The override MUST replace the sort key too, not only the glyph.
- In `_manifest_section(manifest, fields, provenance)`: for each field, if
  `is_audience_default(provenance.get(f.value_path))`, render the override glyph/label **instead of** the
  extraction `_ATTENTION_DISPLAY[f.attention]` **and** use the audience-default sort rank. Otherwise
  unchanged. Value column: show the shielded value (it's a real set default).
- FR-8 falls out automatically: once `kickoff confirm` strips the provenance, `provenance[vp]` no longer
  matches → normal ✅ confirmed row on the next build. No extra code.
- **Test:** field with `audience-default:project` provenance → 🛡️ row **sorted after `ok`**; same field
  after provenance stripped → normal row; field absent from ledger → extraction glyph unchanged; a
  blocked+shielded field does not sort to rank 0.

### Step 5 — Honest overview counts (Slice B: FR-7, OQ-2)
**File:** `src/startd8/kickoff_experience/portal_spec.py` (`_overview_panels`)
- **Per-field cross-walk (R1-S3), the single filtering locus:** compute
  `shielded = {vp for vp, e in provenance.items() if is_audience_default(e)}` (ledger-derived), then
  intersect with the extraction basis **before** subtracting:
  `shielded_gaps = {f.value_path for f in state.fields if f.attention == "blocked" and f.value_path in shielded}`.
  The corrected gap figure is `max(0, blocked - len(shielded_gaps))`. Intersecting first is what prevents
  both **underflow** (a shielded vp not in `state.fields` has no effect) and **double-count**.
- Discount only the **gap-facing widgets** (OQ-2 resolved): the "Open Gaps (author action)" stat
  (`vector({blocked})`) and the `**{blocked} gaps**` figure in the intro status line. Leave the
  `Fields Confirmed` gauge and per-domain `slug · confirmed` ratios on extraction basis (NR-6). Optionally
  add a small "N set for you" figure to the status line.
- **Test (R1-S3 + zero-floor R2-F4):** 3 blocked, 2 of them shielded → "Open Gaps" = 1; **all 3 shielded →
  0 (not negative)**; a shielded `value_path` absent from `state.fields` → no effect; gauge + per-domain
  ratios unchanged in every case; no-ledger board → counts identical to today.

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
  `build_kickoff_portal_spec` output **identical** to a **newly-captured pre-change baseline** (R2-S3 — no
  snapshot exists today; create it). Assert on the full spec dict, not just panels. Protects persona FR-4
  + Workbook NR-3 at once. Lives in `test_kickoff_portal_spec.py` (pure-function defaults).
- **Degrade-to-`light` guard (R1-S5, highest-value single test):** positive marker-slice assertion —
  `expanded != light` AND `compact != light` — because the byte-identity guard **cannot** catch a
  mis-authored workbook doc (`light` is the pass case).
- **Fail-open tests, correctly placed (R2-S4):** the new I/O lives in `build_and_maybe_provision`, so
  these go in `test_portal_build.py` (the I/O boundary), NOT `test_kickoff_portal_spec.py`: (a) missing
  `build-preferences.yaml` → no crash, audience defaults to Intermediate, board byte-identical; (b)
  missing/malformed `confirmed.yaml` → no crash, no badges, board byte-identical; (c) `resolve_audience_
  preference` raising (monkeypatched) → board still generates at `tier="light"`, no `skipped_reason`
  (R2-S7).
- **Per-slice unit tests** as listed per step (writes.py tier slicing; portal_spec rows/sort/counts).
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
- **R5 — Mid-project audience change leaves stale shields (R2-S6, ops).** The M3 pre-pass writes
  `audience-default:*` at walk-start, not at `portal` generation. Changing `audience:` without re-running
  `kickoff walk` leaves the prior audience's shields in `confirmed.yaml`; the next `portal` renders the
  new tier but may badge fields shielded by the old audience. **Accepted era-1 limitation** (documented in
  REQUIREMENTS FR-10). Mitigation: none in code (NR-2 — no ledger writes); a manual test documents the
  behavior; the OQ-3 "Rendered for:" note aids the viewer in spotting a stale board.
- **R6 — Internal call-site TypeError (R2-S1).** Adding the required `provenance` param to
  `_manifest_section` without updating its sole caller (`portal_spec.py:450`) is a silent runtime break no
  existing test catches. Mitigation: Step 2/Step 4 name the call site; the byte-identity baseline test
  (default `provenance={}`) exercises the path.

## 5. Out of Scope (see REQUIREMENTS §3)

Live switching (era 2), per-domain prose tiering (Slice C), per-field panel split, any write path, new
extraction attention values.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

> **Areas substantially addressed (R1/R2):** glyph lock + sort rank (Step 4), internal call-site update
> (Step 2/4), provenance single-filtering-locus + non-dict tolerance (Step 2), audience param type +
> error placement (Step 2), byte-identity baseline creation + degrade-to-light guard + composed-panel
> golden (Step 2/3), gap cross-walk + zero-floor (Step 5), fail-open test placement (§3), mid-project
> stale-shield watch-item (R5). Later reviewers: do **not** re-propose these.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Lock 🛡️ (≠ `✅`) + distinctness test | R1 opus-4.8 | Applied → Step 4 glyph-lock bullet | 2026-07-08 |
| R1-S2 | Sort rank ≥ `ok`, never `blocked` rank 0 | R1 opus-4.8 | Applied → Step 4 sort-rank bullet | 2026-07-08 |
| R1-S3 | Per-field cross-walk `shielded_gaps` before subtract | R1 opus-4.8 | Applied → Step 5 | 2026-07-08 |
| R1-S4 | Two goldens (narrative substring + composed panel) | R1 opus-4.8 | Applied → Step 3 test bullets | 2026-07-08 |
| R1-S5 | Positive marker-slice test (degrade-to-light guard) | R1 opus-4.8 | Applied → Step 3 + §3 | 2026-07-08 |
| R1-S6 | `provenance` = raw entry map; single filtering locus | R1 opus-4.8 | Applied → Step 2 shape bullet | 2026-07-08 |
| R1-S7 | Non-dict entry tolerance | R1 opus-4.8 | Applied → Step 2 tolerance bullet | 2026-07-08 |
| R1-S8 | OQ-3 note structurally gated for Intermediate | R1 opus-4.8 | Applied → Step 3 OQ-3 bullet | 2026-07-08 |
| R2-S1 | Name the `portal_spec.py:450` call site (TypeError) | R2 sonnet-4.6 | Applied → Step 2 + Risk R6 | 2026-07-08 |
| R2-S2 | `audience=res.value` (enum); `.value` for display | R2 sonnet-4.6 | Applied → Step 2 + Step 3 OQ-3 | 2026-07-08 |
| R2-S3 | Byte-identity baseline must be created new | R2 sonnet-4.6 | Applied → Step 2 test + §3 | 2026-07-08 |
| R2-S4 | Fail-open tests belong in `test_portal_build.py` | R2 sonnet-4.6 | Applied → §3 | 2026-07-08 |
| R2-S5 | Lock the shielded-computation locus | R2 sonnet-4.6 | Applied → Step 2 shape bullet (merged w/ R1-S6) | 2026-07-08 |
| R2-S6 | Watch-item for mid-project audience change | R2 sonnet-4.6 | Applied → Risk R5 | 2026-07-08 |
| R2-S7 | New I/O placement vs broad `except Exception` | R2 sonnet-4.6 | Applied → Step 2 error-placement bullet | 2026-07-08 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All R1/R2 plan suggestions accepted. | 2026-07-08 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: claude-opus-4-8-1m (Claude Opus 4.8, 1M context)
- **Date**: 2026-07-09 01:28:43 UTC
- **Scope**: Plan-quality review (S-prefix). Grounded in `concierge/confirmation.py` (`load_ledger`, `_is_audience_default`, entry shape), `concierge/writes.py` (`load_experience_doc` tier-degrade), `kickoff_experience/portal_spec.py` (`_overview_panels`, `_manifest_section`, `_ATTENTION_DISPLAY/_SORT`). Weighted per sponsor focus: extraction↔ledger seam (Step 4/5), byte-identity (Steps 2/3), Slice A doc-authoring dependency (Step 3).

**Executive summary (top risks / opportunities):**

- **Step 4 glyph choice is under-specified where it collides:** the intro legend (Step 3 moves it, byte-identical) already binds `✅`="extracted from your authoring docs" and `_ATTENTION_DISPLAY["ok"]=("✅","confirmed")`. Step 4's `_AUDIENCE_DEFAULT_DISPLAY = ("🛡️", …)` is the right instinct — but the plan should **lock 🛡️ (not ✅)** and add a test asserting distinctness, since REQUIREMENTS FR-5 still says "✅".
- **Step 2's `provenance` map keys off an *optional* ledger field:** `load_ledger` entries are `{value, at, mode}` with `provenance` additive/optional (`confirmation.py:41`). `provenance = {value_path: entry}` is the *entry map*, and `is_audience_default` must run per-entry — the plan should say the map value is the raw entry (predicate applied at render), not a pre-filtered shielded set, to keep Step 5's `shielded` derivation the single filtering point.
- **Step 5 gap-recount reads two different bases and must reconcile them:** the intro `**{blocked} gaps**` and the "Open Gaps" stat both come from `state.attention_counts["blocked"]` (extraction basis, `_overview_panels`), while `shielded` comes from the ledger. The plan's "blocked ∧ shielded" rule is correct but requires a per-field cross-walk (state.fields ↔ provenance by value_path) that Step 5 doesn't yet spell out.
- **Step 3 byte-identity golden must pin the narrative substring, not the composed panel** — the composed `intro` includes a dynamic status line that cannot be byte-pinned.
- **Silent degrade-to-`light` is the highest-value untested failure** (Step 3): if the authored markers don't slice, all tiers serve `light` and every byte-identity test passes while personalization is invisible.
- **Sort-rank decision (Step 4, OQ-1) is deferred inside the plan** — leaving `_ATTENTION_SORT` interaction unspecified risks shielded rows sorting as gaps (rank 0) and re-screaming "action needed" ordering.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | high | In **Step 4**, commit to `🛡️` (or another glyph provably ≠ `✅`) for `_AUDIENCE_DEFAULT_DISPLAY` and add an explicit test that the audience-default glyph ≠ `_ATTENTION_DISPLAY["ok"][0]` (`✅`) and ≠ the legend `✅`. Flag that REQUIREMENTS FR-5's "✅ safe default set for you" is inconsistent and must be reconciled. | The legend the plan moves in Step 3 binds `✅`="extracted from your authoring docs"; `_ATTENTION_DISPLAY["ok"]=("✅","confirmed")`. A `✅` audience-default badge is indistinguishable from human confirmation — the plan already leans 🛡️ but doesn't lock it or test distinctness. | Step 4, `_AUDIENCE_DEFAULT_DISPLAY` bullet | Unit test on the rendered row glyph asserting inequality with both `✅` bindings. |
| R1-S2 | Data | high | In **Step 4**, define the sort rank for audience-default rows against `_ATTENTION_SORT` (`{blocked:0, review:1, backlog:2, ok:3}`) explicitly — the plan says "leaning: rank just after `ok`". Lock it: audience-default rows should sort **with/after `ok` (rank ≥ 3)**, never at `blocked`'s rank 0, so a shielded field never re-appears in the "gaps first" ordering it was meant to remove. | `_manifest_section` sorts by `(_ATTENTION_SORT.get(f.attention,9), value_path)`. If the override keeps the field's underlying `blocked` attention for sorting, it sorts to the top as a gap — contradicting FR-7's honesty goal. | Step 4, sort-rank bullet | Test: a shielded field whose extraction attention is `blocked` sorts after `ok` rows, not first. |
| R1-S3 | Data | high | In **Step 5**, spell out the per-field cross-walk: `shielded_gaps = {f.value_path for f in state.fields if f.attention == "blocked" and f.value_path in shielded}`; subtract `len(shielded_gaps)` from the `blocked` figure. Make explicit that `shielded` (ledger-derived) is intersected with `state.fields` (extraction-derived, attention=="blocked") **before** subtraction — this is where join-drift and underflow both live. | Step 5 currently derives `shielded` from provenance and the gap count from `state.attention_counts["blocked"]` — two bases. Only the intersection (blocked ∧ shielded, keyed by value_path) can be subtracted safely; naming it prevents both underflow and double-count. | Step 5, recount computation | Test: 3 blocked, 2 shielded (both among the blocked) → gap 1; a shielded value_path absent from state.fields → no effect. |
| R1-S4 | Validation | high | In **Step 3**, scope the byte-identity golden to the **narrative substring** that moves into `KICKOFF_WORKBOOK_INTRO.md`, and add a **separate** test that the composed overview panel (narrative + code-appended legend + dynamic status line) is unchanged for a **fixed KickoffState**. | The shipped `intro` bundles narrative + legend table + `**{ok}/{total} … {blocked} gaps**` (dynamic) + trailing italic. A single "byte-identical to today's intro" golden conflates the movable prose with the dynamic line. Two tests separate the concerns cleanly. | Step 3, test bullet | Golden 1: `load_experience_doc("workbook","light")` == narrative bytes. Golden 2: full panel dict for a pinned state == pre-change. |
| R1-S5 | Validation | high | Add a **positive marker-slice test** to **Step 3 / §3 Testing**: assert `load_experience_doc("workbook", tier="expanded") != tier="light"` **and** `compact != light`. This is the only guard against the silent degrade-to-`light` failure (writes.py A-FR9b) where mis-authored markers ship zero personalization yet pass every byte-identity test. | The §0 planning table names this exact no-op risk, and R1 (byte-identity) *cannot* catch it because `light` is the pass case. A distinctness assertion converts a silent degrade into a red test. | Step 3 test bullet + §3 Testing Strategy | The two inequality assertions above; fail if any tier collapses to light. |
| R1-S6 | Interfaces | medium | In **Step 2**, clarify that `provenance` passed into the spec builder is the **raw entry map** `{value_path: entry}` (entries as `load_ledger` returns them, `provenance` key optional), and that `is_audience_default` is applied at render time — not a pre-filtered shielded set. This keeps Step 5's `shielded = {vp … if is_audience_default(e)}` as the single filtering locus. | Two consumers (`_manifest_section` per-row, `_overview_panels` for `shielded`) both need the predicate; passing raw entries avoids a second parallel "already-filtered" structure that could drift from the row-level check. | Step 2, `provenance` param description | Test: same map drives both the row badge and the count discount; no separate shielded-set param exists. |
| R1-S7 | Risks | medium | In **Step 2 / R3**, add that the tolerant read must also handle a ledger entry that is **not a dict** (e.g. a malformed scalar under a value_path): `is_audience_default` already returns False for non-dict (`confirmation.py:55`), but the plan should assert the row still renders on extraction basis rather than raising in `_manifest_section`. | Fail-open is claimed but only tested for absent/empty ledger. A partially-corrupt entry (dict-shaped ledger, scalar value) is a distinct path; `_is_audience_default` guards it, but `_manifest_section`'s value column (`_value_snippet`) should be confirmed non-crashing. | Step 2 test / R3 mitigation | Test: ledger `{vp: "oops-a-string"}` → no badge, extraction glyph, no exception. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Ops | low | In **Step 3 (OQ-3 "Rendered for:" note)**, note that emitting the note for Beginner/Advanced but skipping it for Intermediate means the note's *presence* leaks the audience into the board bytes — fine for personalized tiers, but confirm it does not perturb the Intermediate byte-identity golden (gate the append structurally on `audience` being non-default before the string is built, not appended-then-blanked). | The plan says "skip for Intermediate to preserve byte-identity" — correct, but an implementer who appends an empty line or a conditional-blank string would still alter bytes. Make the gate structural (no append at all for the default). | Step 3, OQ-3 bullet | Byte-identity golden with audience=Intermediate asserts no "Rendered for" substring nor trailing-whitespace delta. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — R1 is the first round; no prior untriaged suggestions exist.)

---

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-09

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-09 UTC
- **Scope**: Plan-quality review (S-prefix). Lens: (a) ops/lifecycle — regeneration when audience changes mid-project, ledger staleness, provisioning idempotency; (b) test-strategy completeness — whether byte-identity and fail-open guarantees are testable as written; (c) interface/data contracts between `portal_build` and `portal_spec` (keyword params, provenance map, private function signatures). Grounded in `portal_spec.py` (lines 139–450), `portal_build.py` (lines 244–324), `test_kickoff_portal_spec.py`, `test_portal_build.py`, `concierge/audience.py`. Does NOT re-propose R1 items.

**Executive summary (top risks / gaps):**

- **The `_manifest_section` internal call site at `portal_spec.py:450` must be updated but the plan does not name it** — extending the private signature to `(manifest, fields, provenance)` while `build_kickoff_portal_spec` still calls `_manifest_section(manifest, by_manifest[manifest])` at line 450 is a silent breaking gap. The plan names the private function extension but not the call site.
- **`audience` parameter type in `build_kickoff_portal_spec` is unspecified**: `portal_build` calls `resolve_audience_preference(root)` → `AudienceResolution(value=KickoffAudience, source=str)`. Whether `audience=` receives `.value` (the enum), the string token, or the full `AudienceResolution` is not stated — OQ-3's "Rendered for: {audience}" needs a display string from whichever form is passed.
- **The "existing `test_portal_spec` snapshot" cited in Step 2 does not exist**: `test_kickoff_portal_spec.py` has no snapshot/golden test — only structural assertions. The byte-identity guard must be created new, not extended. The plan implies it already exists.
- **Fail-open tests for new I/O in `build_and_maybe_provision` are unassigned**: §3 lists "missing `build-preferences.yaml`, missing `confirmed.yaml` → no crash" but does not say these belong in `test_portal_build.py` (testing the I/O boundary) vs `test_portal_spec.py` (testing pure function defaults). The I/O paths live in `build_and_maybe_provision` so the tests must cover it.
- **`_overview_panels` receives both `tier` and `provenance` but its shielded-gap computation (Step 5) is not reconciled with the threading spec**: Step 2 threads both params into `_overview_panels`; Step 5 derives `shielded` inside it. Whether `provenance` flows into `_overview_panels` raw or whether `shielded` is pre-computed in `build_kickoff_portal_spec` and passed separately is left as an implementation detail — an important interface decision with test implications.
- **Ops: no spec for audience change mid-project** — when a user changes `audience` in `build-preferences.yaml` and re-runs `startd8 kickoff portal`, the stale `audience-default:*` entries from the previous pre-pass remain in `confirmed.yaml`. FR-10 says "regeneration is the trigger" for the board but not for clearing stale shields. The plan has no watch-item for this state.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Interfaces | high | In **Step 4**, name the **internal call site** at `portal_spec.py:450` (`panels.append(_manifest_section(manifest, by_manifest[manifest]))`) as a required update — extend it to `_manifest_section(manifest, by_manifest[manifest], provenance)`. The plan names the private-function signature extension but omits the only existing caller. | Verified: `build_kickoff_portal_spec` calls `_manifest_section(manifest, by_manifest[manifest])` at line 450 (positional 2-arg call). Adding a required third param without updating this call site produces a `TypeError` at runtime on any board with manifests. | Step 4, implementation bullet | Test: `build_kickoff_portal_spec(state, "demo", provenance={})` completes without `TypeError`; the existing `test_spec_shape` still passes unchanged. |
| R2-S2 | Interfaces | high | In **Step 2**, specify the **type of the `audience=` param**: pass `res.value` (a `KickoffAudience` enum), not `res` (the `AudienceResolution` dataclass) nor the string token. Add a note that OQ-3's "Rendered for: {audience}" should render `audience.value` (the string token, e.g. `"beginner"`) — this collapses the display-string derivation to a one-liner and avoids an untyped `str(audience)`. | `resolve_audience_preference` returns `AudienceResolution(value=KickoffAudience.BEGINNER, source="project")`. The plan says pass `audience` but never states which attribute — three valid options exist. `disclosure_tier` also accepts either (it calls `coerce_audience`), so the caller could accidentally pass the whole dataclass and it would silently re-coerce. Locking the type prevents a latent mismatch at OQ-3 render time. | Step 2, `audience` param description + Step 3 OQ-3 bullet | Test: `build_kickoff_portal_spec(..., audience=KickoffAudience.BEGINNER)` type-checks cleanly; OQ-3 note renders `"beginner"`, not `"KickoffAudience.BEGINNER"`. |
| R2-S3 | Validation | high | In **Step 2**, note that the byte-identity guard ("existing `test_portal_spec` snapshot") must be **created from scratch**, not extended from an existing test — `test_kickoff_portal_spec.py` has no full-spec golden/snapshot. State that this test must be added as a new fixture: capture `build_kickoff_portal_spec(demo_state, "demo")` with defaults pre-change as the baseline, then assert equality post-change. | Verified: all 20+ tests in `test_kickoff_portal_spec.py` use structural assertions (`spec["uid"]`, `_titles(spec)`, panel counts, tag lists). None assert on the full spec dict. The plan's "existing `test_portal_spec` snapshot" implies a pre-existing golden that can be used as-is — but it must be written in Step 2 itself. | Step 2, test bullet | New test: freeze `build_kickoff_portal_spec(demo_state, "demo")` dict BEFORE the change; assert `==` after Step 2 lands with default params. A diff here is a regression. |
| R2-S4 | Validation | high | In **§3 Testing Strategy**, assign the two new fail-open paths to `test_portal_build.py` (the I/O boundary): (a) `build_and_maybe_provision` with `build-preferences.yaml` absent → no crash, audience defaults to Intermediate, board is byte-identical; (b) with `confirmed.yaml` absent → no crash, no badges, board byte-identical. These test `portal_build`'s new I/O callers, NOT the pure-function defaults which belong in `test_portal_spec.py`. | After Step 2, the new I/O lives in `build_and_maybe_provision` (`resolve_audience_preference` + `load_ledger`). Existing `test_portal_build.py` tests already cover toolchain degrade; the new fail-open paths fit that pattern. Assigning them to the wrong file means they never exercise the I/O caller. | §3 Testing Strategy, fail-open bullet | New `test_portal_build.py` tests: missing pref file → `spec` is byte-identical to pre-audience spec; missing ledger → same board, no exception. |
| R2-S5 | Architecture | medium | In **Step 2/Step 5**, decide and state whether `provenance` flows raw into `_overview_panels` (which then derives `shielded` internally) or whether `shielded` is **pre-computed in `build_kickoff_portal_spec`** and passed separately. Either is valid; the plan currently describes threading `provenance` into `_overview_panels` (Step 2) and deriving `shielded` inside it (Step 5) — lock this as the chosen approach so it doesn't leave an ambiguous "two ways to thread" situation at implementation time. | Step 2 says thread `provenance` into `_overview_panels`. Step 5 says compute `shielded = {vp for vp, e in provenance.items() if is_audience_default(e)}` (location unspecified — Step 5 text implies it's inside `_overview_panels`). Inconsistency: if `shielded` is pre-computed in `build_kickoff_portal_spec`, `_overview_panels` also needs it for the gap discount. If computed inside `_overview_panels`, it's duplicated with `_manifest_section`'s per-row check. Pick one and name the data flow. | Step 2 threading bullet + Step 5 computation | Test: confirm `_overview_panels` and `_manifest_section` both use the same filtering predicate (one passes `provenance`, the other derives from it consistently). |
| R2-S6 | Ops | medium | Add a **watch-item R5** for the mid-project audience-change lifecycle: when a user changes `audience:` in `build-preferences.yaml` then re-runs `startd8 kickoff portal`, the `audience-default:*` entries from the *prior* audience's pre-pass remain in `confirmed.yaml` (the pre-pass runs at walk-start, not at `portal` generation). The board will correctly render the new audience's tier — but badges may linger for fields no longer shielded by the new audience. State this as an era-1 accepted limitation (clearing stale shields requires the user to re-run `kickoff walk` or `kickoff confirm`). | `apply_audience_defaults` runs at walk-start (M3 pre-pass), not in `portal_build`. If audience changes, `confirmed.yaml` retains the old provenance stamps until a new walk overwrites them. The current plan has no watch-item for this. Calling it out prevents a misleading "fresh board doesn't match new audience" bug report. | §4 Risks / Watch-items, new R5 | Manual test: set audience=beginner → run portal → change audience=advanced → run portal without re-walking → confirm stale badges appear but do not crash; document as known era-1 limitation. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S7 | Ops | low | Verify that **`build_and_maybe_provision`'s broad `except Exception`** (line 318) swallows errors from the new `resolve_audience_preference` and `load_ledger` calls without logging them. The pattern is fail-open → `skipped_reason` for the workflow error, but audience/ledger failures should degrade silently to defaults, not be caught by the broad handler and skip the whole board. The plan adds these calls BEFORE the try block that wraps spec generation (Step 2 says "after building `state`") — confirm their placement: they should be INSIDE the try block or wrapped individually with their own tolerant handlers so a credential error in `resolve_audience_preference` does not silently skip the whole board. | `portal_build.py:317`: `except Exception as exc: return PortalResult(uid=uid, skipped_reason=f"generation failed: {exc}")`. If `resolve_audience_preference` raises (e.g., config read error), and it is placed inside the try block, it produces a misleading `skipped_reason="generation failed: ..."` instead of a logged warning + degrade to Intermediate. Placement matters for observability. | Step 2, implementation note after the `load_ledger` bullet | Test: monkeypatch `resolve_audience_preference` to raise → board still generates with `tier="light"`, no `skipped_reason`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S5: The positive marker-slice test (degrade detection) is the highest-value single test — endorsing for high triage priority.
- R1-S3: The cross-walk spelling (`shielded_gaps = {f.value_path for f in state.fields if ...}`) is the right way to prevent both underflow and double-count — endorsing.
- R1-S8: Structural gate for OQ-3 "Rendered for" note (no append at all for Intermediate) is load-bearing for the byte-identity guarantee.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to the plan step(s) that address it. Grounded in the source code cited in the R1 round block.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (resolve audience in I/O caller, pass params) | Step 2 | Full | — |
| FR-2 (author tiered workbook doc, Intermediate byte-identical) | Step 3 | Partial | Byte-identity target not scoped to the narrative substring vs the composed panel (R1-S4); no positive marker-slice guard against silent degrade-to-`light` (R1-S5, R1-F8). |
| FR-3 (register `"workbook"` key in `_EXPERIENCE_DOCS`) | Step 3 | Full | — |
| FR-4 (render intro at resolved tier; status line + legend stay code-side) | Step 3 | Full | — |
| FR-5 (audience-default override state / glyph) | Step 4 | Partial | Glyph not locked and collides with `✅` legend/`_ATTENTION_DISPLAY["ok"]`; REQ FR-5 text ("✅") inconsistent with plan lean (🛡️) — reconcile + test distinctness (R1-S1, R1-F1). Sort rank vs `_ATTENTION_SORT` unspecified (R1-S2). |
| FR-6 (fail-open join via `load_ledger`; byte-identical with no entries) | Step 2, Step 4 | Partial | Join reads the *optional* `provenance` entry key (not named); non-dict/malformed-entry path and value_path join-asymmetry (in-ledger-not-in-state / vice-versa) not fully specified (R1-S6, R1-S7, R1-F2, R1-F6). |
| FR-7 (honest overview counts, no underflow) | Step 5 | Partial | Per-field cross-walk (blocked ∧ shielded by value_path) and the non-underflow invariant not fully spelled out; the two corrected figures should be named and the gauge/ratios declared out-of-scope (R1-S3, R1-F3, R1-F4). |
| FR-8 (transient badge; disappears on `kickoff confirm`) | Step 4 (falls out) | Full | — (mechanism verified: `kickoff confirm` rebuilds the entry wholesale with no `provenance`, `confirmation.py:300-304`). |
| FR-9 (public audience-default predicate) | Step 1 | Full | — |
| FR-10 (regeneration is the era-1 trigger) | inherent (no code) | Full | — |
| OQ-1 (glyph/label/sort rank) | Step 4 | Partial | Deferred inside the plan; R1-S1/R1-S2 recommend locking. |
| OQ-2 (gap recount scope) | Step 5 | Partial | Leaning stated; R1-F4 recommends promoting the scope decision (gauge/ratios excluded) into FR-7. |
| OQ-3 (surface audience token on board) | Step 3 | Partial | Conditional; byte-identity gating for Intermediate must be structural (R1-S8). |
| OQ-4 (intro doc content authority — move vs duplicate) | Step 3 | Full | Resolved single-source (doc owns narrative; status line code-side). |

## Requirements Coverage Matrix — R2

Analysis only (not triage). Grounded in `portal_spec.py` (lines 139–450, internal call sites), `portal_build.py` (line 244–324, I/O boundary), and `test_kickoff_portal_spec.py` / `test_portal_build.py`. Focuses on gaps R1's coverage marked Partial — updated with R2 findings.

| Requirement | Plan Step(s) | Coverage | Gaps (R2 view) |
| ---- | ---- | ---- | ---- |
| FR-1 (resolve audience in I/O caller, pass params) | Step 2 | Partial | `audience=` type is unspecified (`KickoffAudience` enum vs string vs `AudienceResolution`); OQ-3 display depends on this choice (R2-S2). `resolve_audience_preference` placement relative to the broad `except Exception` in `portal_build` is unspecified (R2-S7). |
| FR-2 (author tiered workbook doc, Intermediate byte-identical) | Step 3 | Partial | R1 gaps remain (narrative substring scope, marker-slice test). Additionally: the byte-identity golden test must be created new — no existing snapshot to extend (R2-S3). |
| FR-3 (register `"workbook"` key) | Step 3 | Full | — |
| FR-4 (render intro at resolved tier) | Step 3 | Full | — |
| FR-5 (audience-default override state / glyph) | Step 4 | Partial | R1 gaps remain (glyph lock, sort rank). Additionally: the `_manifest_section` internal call site at `portal_spec.py:450` is unnamed and will break unless updated (R2-S1). |
| FR-6 (fail-open join) | Step 2, Step 4 | Partial | R1 gaps remain. Additionally: new I/O fail-open tests must target `build_and_maybe_provision` in `test_portal_build.py`, not the pure-function (R2-S4). |
| FR-7 (honest overview counts) | Step 5 | Partial | R1 gaps remain. Additionally: whether `shielded` is computed in `_overview_panels` or pre-computed in `build_kickoff_portal_spec` is unresolved (R2-S5). |
| FR-8 (transient badge) | Step 4 (falls out) | Full | — |
| FR-9 (public predicate) | Step 1 | Full | — |
| FR-10 (regen is trigger) | inherent | Partial | Mid-project audience change leaves stale `audience-default:*` entries in the ledger; no watch-item captures this era-1 limitation (R2-S6). |
| OQ-1 (glyph/sort rank) | Step 4 | Partial | Still deferred; R1-S1/R1-S2 + R2-S1 (internal call site) raise the stakes for locking early. |
| OQ-2 (gap recount scope) | Step 5 | Partial | Unresolved; R2-S5 adds the threading ambiguity. |
| OQ-3 (audience token on board) | Step 3 | Partial | Type of `audience=` param must be resolved (R2-S2) before display string is known. |
| OQ-4 (content authority) | Step 3 | Full | — |
