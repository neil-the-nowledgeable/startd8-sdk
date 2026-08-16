# Handoff: take REQ-16 + REQ-17 through the Spec Delivery Loop (one 0.4.0 schema bump)

**Date:** 2026-08-16 · **From:** emeritus/architecture session · **Base:** `main @ 277019f8`
**For:** a build session · **Deliver:** REQ-16 + REQ-17 **together** as a single Node schema-version bump.

## What you're building (and why together)

Two specs that both touch `models.Node`'s field set, so they must land in **one** `node_field_names()`
golden change — churn it once, not twice.

| Spec | DIDL name (functionality from the name) | What it lands |
|------|------------------------------------------|---------------|
| **REQ-17** `feature/sdk-navigator-promotes-the-acceptance-oracle-6fb6c312` | *promotes the acceptance oracle, human-approval gate, and change-history into first-class Node fields* | `verify` / `approve` / `was` on `models.Node` (optional, empty-default); the requirements projection carries them instead of dropping them |
| **REQ-16** `feature/sdk-navigator-types-a-derivation-edge-on-the-9d994bb0` | *types a derivation edge on the Node + schema self-conformance* | a first-class **derivation edge object** (distinct from containment `children`) that **reserves an unset `regime` slot**; a field-parity conformance test; a portable status-derivation agreement contract |

**Decision already made (ACCEPTED):** `ADR_promote-oracle-and-human-gate-into-node-ir.md` — the schema
owner is go. **OQ-6 resolved:** realization rides the *derivation edge*, not the node — REQ-16 only
*reserves* the `regime` slot (unset); a later realization REQ fills it. Do not implement realization here.

## Grounding (the finding these fix — verify before you start)

- `det_req.py` parses each FR into `{name, lives, verify, approve_prompts, was, serves, …}` but
  `models.Node` has **no** `verify`/`approve`/`was` → they're dropped at the `det_req→Node` boundary.
  (Confirm: `python3 -c "from startd8.navigator import models; print(models.node_field_names())"`.)
- `NODE-SCHEMA.md` §1 (dev-os) is **stale** — omits `category/orientation/route_state/status_facets/
  child_keys/attributes` the code already has. REQ-16 FR-2's parity gate makes that drift impossible again.
- Status-derivation is forked ≥3 ways (`models.derive_status`, `det-req-kit/extract.py`, Studio
  `req-health.mjs`) with no shared-fixture agreement. REQ-16 FR-3 exports a portable contract for it.

## The loop (LOOP_CATALOG #6 — Spec Delivery Loop)

```bash
# 0. GATE — readiness of both specs
python3 scripts/navigator_spec_delivery_loop.py --status
python3 scripts/navigator_spec_delivery_loop.py REQ-16    # exit 1 if blocked
python3 scripts/navigator_spec_delivery_loop.py REQ-17
python3 scripts/navigator_spec_delivery_loop.py --checklist   # the 7-stage runbook
# 1-4. PREP/BUILD/GATE-2/REVIEW in a worktree (see Gotchas)
# 5-6. LAND (own files only) + RECORD (ledger)
# 7. HARVEST = /harden-then-harvest on the shipped surface (official Stage 7)
```

## Build order (within the one bump)

1. **REQ-17 FR-1** — add `verify`/`approve`/`was` to `models.Node` (optional, empty-default).
2. **REQ-16 FR-1** — add the first-class derivation-edge object (distinct from `children`) with an
   **unset** `regime` slot; keep containment `children` unchanged.
3. **REQ-17 FR-2** — wire `sources_requirements` to project the parsed `verify`/`approve_prompts`/`was`
   onto the new fields (empty when the FR lacks them).
4. **REQ-16 FR-1 (cont.)** — `pipeline_provenance` reads the typed edge instead of longest-prefix ownership.
5. **REQ-16 FR-2 + REQ-17 FR-3** — the field-parity conformance test + register `verify`/`approve`/`was`
   (and the edge) in the manifest. This test is the schema-as-Node self-check.
6. **REQ-16 FR-3** — the status-derivation agreement test + exported `status_contract.json`.
7. **Bump** `NODE-SCHEMA` to **0.4.0** in the SDK-side references; update the golden **once**.

## Hard constraints (the exit criteria)

- **Render byte-identical.** `test_no_profile_is_byte_identical` passes **unedited**. The new fields are
  empty-default and **not rendered**.
- **One golden delta.** The only `node_field_names()` change is exactly
  `{verify, approve, was, <derivation-edge>}` — nothing else.
- **`regime` slot stays UNSET** (REQ-16 NR-6). No realization values, no determinism-% rollup here.
- **No oracle classification** (REQ-08 owns `command|assertion|manual`); `verify` carries the raw clause.
- **No invariant-9 enforcement** (`llm ⇒ verify-required`) — that's the realization REQ.
- **SDK-side only.** Do **not** edit `dev-os/NODE-SCHEMA.md` §1 or the ContextCore mirror — those are the
  authorized-but-separate cross-repo handoff (below).

## Gotchas (this repo, learned this session)

- **Multi-agent concurrency.** `main` moves between turns (it did repeatedly this session). Build in a
  **worktree**; if `main`/`origin/main` diverged, **cherry-pick your fix + FF-push**, never merge into the
  shared tree while another agent commits. Pin `PYTHONPATH=<worktree>/src` (editable install imports from
  the primary worktree otherwise). Stage **your** files only — never `git add -A`.
- **det-req single-line FR parser trap.** Each FR bullet is ONE physical line, and the parser keys on
  `Name:`/`Touches:`/`Lives:`/`Approve?:`/`Verify:`/`Serves:` labels — **do not put literal `Verify:` /
  `Approve?:` tokens (with colons) in FR prose** or it mis-parses (bit us on REQ-17 FR-1; drop the colons).
- **DIDL names are derived.** A spec's handle must equal `naming.name_forms(semantic_name).handle`; if you
  edit a semantic name, regenerate the handle. Validate:
  `parse_fr_lines` count == named-FR count, and handle/ref match `name_forms`.
- **`| tail`/`| head` mask exit codes** — check ruff/pytest `$?` directly.

## After landing — the follow-on chain (not this session's scope)

1. **Cross-repo (authorized by the ADR go, separate handoff):** update `dev-os/NODE-SCHEMA.md` §1 to
   0.4.0 (add the 3 fields + fix the pre-existing staleness); **bus-notify** the ContextCore Node owner to
   adopt the mirror. Until then, REQ-16's parity gate flags the drift — expected.
2. **REQ-08** can then read native `verify` instead of reconstructing (its scope shrinks).
3. **The realization REQ** fills REQ-16's reserved `regime` slot: edge-carried `deterministic|llm|human`,
   node realization derived from incoming edges (like `status`), determinism-% rollup, invariant 9
   enforcement. Provenance is a lift from Kaizen/`ai_layer`/`costs` (already stamped). See
   `RESEARCH_llm-interpreter-backend-and-realization-facet.md` (OQ-1..6).

## Pointers

- ADR: `ADR_promote-oracle-and-human-gate-into-node-ir.md` (Accepted)
- Specs: `REQ-16-node-derivation-edge-and-schema-conformance.md`, `REQ-17-promote-oracle-gate-history-to-node-fields.md`
- Research: `RESEARCH_llm-interpreter-backend-and-realization-facet.md`
- Review that motivated the arc: `REVIEW_view-definition-integration-wired-vs-inert.md` (method) ·
  the Node code: `src/startd8/navigator/models.py` · the IR spec: `dev-os/NODE-SCHEMA.md`
