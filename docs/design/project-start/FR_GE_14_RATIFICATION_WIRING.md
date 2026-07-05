# FR-GE-14 — Ratification-Gate Wiring

**Version:** 0.1 (focused spec — reflective loop ran conversationally; the cycle
constraint below is the planning discovery)
**Date:** 2026-07-05
**Status:** Ready to build
**Parent:** `GUIDED_EXPERIENCE_REQUIREMENTS.md` FR-GE-14 (acceptance R1-F10);
`OUTSTANDING_TASKS.md` §1 (corrected 2026-07-05).

---

## 1. Problem Statement

FR-GE-14 requires that *"every synthetic output carries a machine-checkable provenance
marker and a ratification state (unratified by default); the kernel refuses (or warns
on) an unratified synthetic input until the human explicitly ratifies it."*

The **mechanism** is built and tested (`stakeholder_panel/provenance.py`,
`test_provenance.py`): a `synthetic` marker (`qualifier="synthetic"`, `source="panel:…"`),
a typed `is_synthetic()` check, an unratified-by-default state, a serialization round-trip
guard, and the refuse-until-ratified **gate primitive** `assert_ratifiable()` /
`RatificationError`.

**The gap:** the gate is **unwired**. Nothing calls `assert_ratifiable` on a consume/write
path (grep: only `__init__.py` re-exports). `provenance.py` itself anticipated *"the live
ratified store is wired by VIPP in M2,"* but VIPP shipped without wiring it. The invariant
holds today only by construction (no synthetic claim is persisted to a load-bearing store
yet), not by enforcement.

| Component | Current state | Gap |
|-----------|---------------|-----|
| Provenance marker + unratified state | Built (`provenance.py`) | — |
| `assert_ratifiable` gate primitive | Built + tested | **No caller** |
| VIPP applier (`vipp/apply.py`) | Applies ACCEPT/COUNTER through the `apply_proposal` floor behind a human `confirm()` | Does **not** enforce ratification on synthetic claims |

## 2. Requirements

- **FR-RW-1 — Wire the gate on the write path.** `vipp/apply.py:apply_dispositions`
  MUST call `assert_ratifiable()` on every claim of an actionable (ACCEPT/COUNTER)
  disposition **before** it writes via `apply_proposal`. This gives
  `assert_ratifiable` its first live caller.
- **FR-RW-2 — The human `confirm()` IS the ratification.** The ratification token is
  present **iff** the human `confirm(action, disp)` returned `True`. There is exactly one
  human content gate (parent NR-4 / FR-10); this wiring does not add a second prompt — it
  reinterprets the existing confirmation as the ratification act for synthetic claims.
- **FR-RW-3 — Refuse, never crash; leave pending.** A synthetic claim reaching the write
  path **without** ratification (token absent) yields a distinct outcome
  `code="unratified"` (`ok=False`), **no write**, and the disposition is **left pending**
  for a later ratified run (parity with the existing `unconfirmed` lifecycle).
  `RatificationError` is caught inside the loop, never propagated (don't-crash-the-loop,
  Lesson L13-#103).
- **FR-RW-4 — Byte-identical when no synthetic claim is present (SOTTO).** Non-synthetic
  claims pass the gate untouched. Every disposition VIPP produces **today** carries only
  oracle-sourced (non-`panel:`) claims, so `apply` behavior is **byte-identical** to
  pre-wiring for all current flows. The gate is additive and inert until a synthetic claim
  actually flows to `apply` (the forward-looking FR-9b panel-writeback path).
- **FR-RW-5 — Single-source vocabulary; no import cycle.** The claim-level ratification
  primitives (`is_synthetic`, `assert_ratifiable`, `RatificationError`,
  `round_trips_synthetic`, `SYNTHETIC_QUALIFIER`, `SOURCE_PREFIX`) MUST have one owner that
  both `stakeholder_panel` and `vipp` can import without a cycle. They move to a leaf,
  `fde/ratification.py`; `stakeholder_panel.provenance` re-exports them (back-compat).

## 3. Non-Requirements

- **NR-1.** Does not add a second human gate or change the `ConfirmFn` signature.
- **NR-2.** Does not build the FR-9b panel-answer→disposition writeback path (the producer
  of synthetic claims into dispositions). This wiring makes the *consumer* safe **for when**
  that path lands; it is forward-looking by design.
- **NR-3.** Does not change `provenance.py`'s public API — every name it exports today stays
  importable from `stakeholder_panel.provenance` (and `stakeholder_panel`).
- **NR-4.** Does not move the panel-answer-specific helpers (`synthetic_claim`, `brief_hash`)
  — they depend on `PanelAnswer`/`PersonaBrief` and stay in `stakeholder_panel.provenance`.

## 4. Plan

- **M0 — Leaf extraction (FR-RW-5).** Create `src/startd8/fde/ratification.py` holding the
  six claim-level primitives (moved verbatim from `provenance.py`). Rewrite
  `provenance.py` to `from startd8.fde.ratification import *`-style re-export (explicit
  names) and keep `synthetic_claim` + `brief_hash` local. `stakeholder_panel/__init__.py`
  and `test_provenance.py` are untouched and stay green (they import from `provenance`).
- **M1 — Wire the gate (FR-RW-1/2/3/4).** In `apply_dispositions`, replace the
  `if not confirm(...)` block with: call `confirmed = confirm(action, disp)`; derive
  `token = _RATIFY_TOKEN if confirmed else None`; `assert_ratifiable` every claim inside a
  `try` (→ `code="unratified"`, pending, on `RatificationError`); then the existing
  `if not confirmed → unconfirmed` branch; then `apply_proposal`. Import `assert_ratifiable`
  from `..fde.ratification`.
- **M2 — Tests.** `tests/unit/vipp/test_apply.py`: (a) disposition with a synthetic claim +
  `confirm=True` → written (ratified); (b) same + `confirm=False` → `code="unratified"`,
  no write, inbox **not** shredded (pending); (c) disposition with only non-synthetic claims
  → outcomes byte-identical to pre-wiring (regression); (d) grep-guard that
  `assert_ratifiable` now has a caller in `vipp/apply.py`. Keep `test_provenance.py` green.

## 5. Planning Insight (the reflect step)

**Discovery:** the obvious wiring — `vipp/apply.py` imports `assert_ratifiable` from
`stakeholder_panel.provenance` — would create an **import cycle**. `stakeholder_panel/__init__`
imports `vipp_bridge`, and `vipp` already imports `stakeholder_panel` **lazily**
(`assistant.py:155`, function-local) *specifically to avoid* that cycle. A module-level
`vipp → stakeholder_panel` import reintroduces it. **Correction → FR-RW-5:** the claim-level
primitives are a property of `LabeledClaim` (which lives in the leaf `fde/models.py`), so
their true home is a sibling leaf `fde/ratification.py` that both packages import cleanly.
This is the single-source-vocabulary fix, not a workaround.

## 6. Acceptance (traces R1-F10)

- [ ] A synthetic input at the write path **without** ratification is **refused**
  (`code="unratified"`, no write, left pending). ← the FR sentence, now enforced.
- [ ] The same input **with** human confirmation is written (ratified).
- [ ] All current (non-synthetic) dispositions apply **byte-identically** to pre-wiring.
- [ ] `assert_ratifiable` has ≥1 live caller (`vipp/apply.py`); `test_provenance.py` green;
  `stakeholder_panel` public API unchanged.

---
*v0.1 — focused wiring spec. Closes the FR-GE-14 "unwired primitive" gap surfaced in
`OUTSTANDING_TASKS.md` §1.*
