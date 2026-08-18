# PLAN-01 — Runnable-Verify Reconciliation — Implementation Plan

**Pairs with:** `REQ-01-runnable-verify-schema-reconciliation.md` · **Version:** 0.1 · **Date:** 2026-08-18
**Status:** spec-only (no implementation this pass) · **Criticality:** high

## Discoveries (locked into REQ §0)

| Assumption (REQ v0.1) | Planning discovery | Impact on plan |
|---|---|---|
| a1 == verify.gate | a1 is a typed 2-form grammar; verify.gate is a bare `str` | Schema step (F-1) makes verify.gate the typed superset; no rewrite of a1 |
| verify.gate liveness accepts a1 forms | `_gate_liveness` borrows `verify_oracle` (startd8-only) → false-GAP on `pytest`/`probe` | F-3 = the load-bearing change: `kind`-dispatch, not verb-set widening |
| Schema lives in the SDK | det-req-kit `SCHEMA.md` §5 is the SSOT (Kagami de-fork) | F-1 is a cross-repo PROPOSAL to the kit; SDK ships conforming parsers only |
| Two oracles | THREE (`verify_oracle`, `grammar`, `verify-liveness`) | F-3 dispatches to two resolvers by `kind`; deletes none |
| verify.gate is shipped so done | shipped UNTYPED (`verify_gate: str`), 0/180 adopted (REQ-27) | typing is migration-free; a1 specs are the first typed corpus (F-2) |

## Design (spec-only — the shape the build would take)

| FR | File · symbol (cross-repo marked ⌂ = det-req-kit / dev-os) | Change |
|----|-----------------------------------------------------------|--------|
| FR-2, FR-4 | ⌂ `dev-os/det-req-kit/SCHEMA.md` §5 · ⌂ `requirement.schema.json` `verify.gate` | PROPOSAL: typed tagged-union `{kind, raw, probe?}`; absent `kind` ⇒ untyped-legacy. **Kit owner's go.** |
| FR-2, FR-8 | `src/startd8/oracle_loop/grammar.py` `parse_verify_clause` | emit the typed handle: `one-shot`→`pytest`/`command`, `service`→`probe`; no-match→`manual` residue |
| FR-4, FR-8 | `src/startd8/navigator/det_req.py` `parse_gate` | emit the typed handle for the startd8-verb span (`command`); keep bare-str fallthrough (untyped-legacy) |
| FR-3, FR-5 | `src/startd8/navigator/govern.py` `_gate_liveness` | dispatch on `verify.gate.kind`: `pytest`/`console-script`/`probe`→`oracle_loop.grammar` resolver; `command`→`verify_oracle`; unresolvable→`dead-structural`; startd8-`command` still `live` |
| FR-1, FR-6, FR-7 | `docs/design/runnable-verify-reconciliation/REQ-01…md` (Appendices A/B/C) | the delta table, the typed schema, the three-oracle map (this doc — done) |

**Ownership split (the cross-repo honesty).** Schema half = det-req-kit (dev-os, Kagami/Mottainai). Parser +
`kind`-aware liveness half = startd8 SDK. No SDK-local rival schema (NR-6).

**Reuse (Mottainai).** No new engine: a1's `run_sandboxed`/`run_service_sandboxed`, `verify_oracle`'s read-only
allow-list, and `govern`'s existing Finding/severity plumbing all stay. The `kind` is the only new typed seam.

## Iterations (≤3 legs; would-be sequence)

| id | FRs | target | state |
|----|-----|--------|-------|
| F-1 (foundation) | FR-2, FR-4 | ⌂ typed `verify.gate` in det-req-kit SCHEMA.md + schema JSON (PROPOSAL; kit owner go) | not started (spec-only) |
| F-2 (logic) | FR-2, FR-8 (SDK) | `grammar.py` + `parse_gate` emit the typed handle; malformed→residue; a1-form parity golden | not started (spec-only) |
| F-3 (integration) | FR-3, FR-5, FR-6, FR-7 | `_gate_liveness` `kind`-dispatch; `probe`/`pytest` gate resolves `live` on a fixture; byte-identical on clean corpora | not started (spec-only) |

**Dependencies:** F-2 after F-1 (SDK emits the kit's shape); F-3 after F-2 (liveness dispatches on the emitted
`kind`). FR-1/FR-6/FR-7 are doc FRs discharged by this REQ's own appendices (F-3 leg). Acyclic.

## Contract-projection touch check

Every FR `Touches:` a `python-cli-surface` entry (`navigator build|govern|verify`, `--run-oracle`,
`--format json`, `startd8`/`extract` console-scripts) or a file path (SDK modules + the cross-repo kit
`SCHEMA.md`/`requirement.schema.json`, exempt as paths). The kit schema files are cited, not owned (FR-4/NR-5).

## Verify (whole change — spec-only)

- **This pass:** `parse_fr_lines_prefer_kit(REQ-01) → named == verify == 8` (confirmed); the REQ is self-consistent.
- **When built (F-2/F-3):** `pytest tests/unit/navigator/ tests/unit/oracle_loop/` green including a fixture where a
  `probe GET /health -> 200` gate and a `pytest tests/x.py -q` gate each resolve `live` under `_gate_liveness`
  (closing the false-GAP), a malformed gate resolves `manual`/residue, and `test_no_profile_is_byte_identical`
  passes unedited on clean corpora.

## Non-goals (plan-level)

- No gate dispatch/execution framework (NR-2); no widening of any runner's execution verbs (NR-3); no rewrite of
  the three oracles (NR-7); no SDK-local rival schema (NR-6). The build is additive + backward-compatible (O-3).
