# Next steps / handoff: take REQ-18 (realization regime) through the loop

**Date:** 2026-08-16 · **From:** emeritus/direction session (I direct, I do not implement) · **Base:** `main @ 9dfed1d9`
**For:** a build session · **Spec:** `REQ-18-realization-regime-and-determinism-rollup.md`
**Prerequisite status:** ✅ **CLEARED** — REQ-16/17 landed on `main` (`aaa39178`, 11th loop delivery). `node_field_names()`
now carries `verify, approve, was, derivation`, and the derivation edge's `regime` slot exists. **REQ-18 is build-ready.**

## The one-line goal (and the direction that matters)

Fill the reserved `regime` slot so the IR states *how each node was realized* and rolls it up to a
**determinism-%** — shipped first as **declared** (approach (a)) **through a confidence-aware seam**, on the
explicit path to **measured/grounded** (approach (b)). **The load-bearing direction: build the seam's
honesty guarantee in (a) so (b) can never introduce false grounding.** Everything else is mechanics.

## Two things to internalize before you start (they change what "done" means)

1. **The seam (FR-2) is the deliverable, not a detail.** Its confidence-aware degradation — *absent or
   low-confidence provenance → declared/`unknown`, never assert a measurement* — is the integrity firewall
   that makes (b) safe. If you cut a corner anywhere, do not cut it here.
2. **(a) will read `unknown` on most real graphs — and that's correct.** In (a) the regime is *declared*,
   and the only natural place declared regimes exist today is the **pipeline source** (REQ-08 stages — a
   stage's impl-edge is deterministic/llm *by nature*). Application-requirement graphs have no declared
   regime until (b) measures it. So **(a)'s determinism-% is demonstrated on the pipeline fixture and reads
   `unknown` elsewhere** — that is honest, not a bug. (a)'s deliverable is *the machine + the firewall*, not
   a headline number. Do not manufacture declared regimes on real requirement graphs to make the number look
   full — that would be the exact false-grounding this REQ exists to prevent.

## Scope reminder (what NOT to build)

- **NO construction-subsystem imports.** `realization.py` must not import `backend_codegen` / `contractors`
  / `micro_prime`. (a) is navigator-internal; the emitter/normalizer/join is (b). The seam is the firewall.
- **NO planned-vs-realized delta** (OQ-1) — single declared regime; the delta is (b)'s self-monitoring payoff.
- **NO new Node field.** REQ-18 is **pure derivation + render + enforcement**: `derive_realization` is a
  *function*, the facet is *derived*, the determinism-% is a *summary line*, invariant 9 is a *govern check*.
  The `regime` slot already exists (REQ-16). So **`node_field_names()` does NOT change and the schema stays
  0.4.0** — a cleaner byte-identity story than REQ-16/17 had.

## Build order (the 7 FRs)

1. **FR-1** — populate the edge `regime` (declared `deterministic|llm|human`, default `unknown`) on the
   pipeline/base definitions. The pipeline stages are the natural, honest place to declare.
2. **FR-2** — `realization.py::derive_realization` reading regime **through the confidence-aware seam**
   (optional provenance source; absent/low-confidence → declared/`unknown`). In (a) no source is wired.
   *Build the degradation contract + its tests first — it is the firewall.*
3. **FR-3** — node realization = the **distribution** over the subtree (leaf → its edge; parent → counts),
   derived not stored, **not** a min-rollup.
4. **FR-6** — expose the derived `realization` facet (`…:deterministic|llm|human|unknown`, `…:mixed` for a
   spanning parent) to the existing §3a facet engine.
5. **FR-4** — the summary determinism-% line, **explicitly labeled `declared`** (deterministic + speakable,
   SV-7). Renders only when regime data is present; absent → no line.
6. **FR-5** — invariant 9 as a `govern` check: `regime==llm` obligates the target's `verify` non-empty,
   **firing only once `lives` is non-empty** (mirror `ships_when`⟺`lives`); a violation is a named finding.
7. **FR-7** — prove additive/byte-identical: `test_no_profile_is_byte_identical` unedited; no construction imports.

## Hard exit criteria

- **Render byte-identical** on existing domains; **`node_field_names()` unchanged** (no new Node field).
- **Seam degrades honestly** — a stub low-confidence provenance match must degrade to declared/`unknown`,
  proven by a test (this is the firewall; it must have a negative test).
- **Determinism-% labeled `declared`** — never `measured` while no provenance source is wired.
- **Invariant 9 activation-gated** — spec/unbuilt nodes (`lives` empty) never fail; a realized `llm` node
  with empty `verify` does.
- **Zero construction-subsystem imports** in `realization.py`.

## Gotchas (this repo)

- **det-req parser trap** — one physical line per FR; do NOT put literal `Verify:`/`Approve?:`/`Lives:`
  tokens (with colons) in FR prose (it mis-parses; bit REQ-17 FR-1).
- **Concurrency** — `main` moves between turns; build in a worktree, cherry-pick + FF if it diverged, pin
  `PYTHONPATH=<wt>/src`, stage own files only.
- **DIDL** — any spec edit must keep `handle == name_forms(name)`; validate parse-count == named-FR count.
- **`| tail`/`| head` mask exit codes** — check `$?` directly on ruff/pytest.

## The direction beyond (a): what (b) will do, and what (a) must leave for it

**(b) = measured regime, grounded.** It lifts the real per-artifact regime from the scattered construction
provenance (`micro_prime` registry model/strategy, `prime-result`, `$0`-skip decisions), **normalizes** it
to a per-file regime map, and **joins** it to `Node.lives.ref` by file path — then feeds it into the seam
(a) built. (a) must leave in place: (1) the seam's typed contract + confidence-aware degradation, (2) the
`declared`/`measured` label switch, (3) the distribution/rollup that doesn't care whether regime is declared
or measured. If (a) gets those three right, **(b) is an additive layer — implement the emitter/normalizer/
join and fill the seam — not a rewrite.** (b) is where the determinism-% becomes *true*, where planned-vs-
realized regressions (OQ-1) become visible, and where the RETROSPECTIVE bookend gets its feedback data.
**(b) must reuse the seam's honest-degradation — a weak join degrades, never asserts.**

## OQ status (for the record)

| OQ | Resolution | Where |
|----|-----------|-------|
| OQ-1 planned-vs-realized | **deferred to (b)** (its self-monitoring payoff) | REQ-18 NR-3 |
| OQ-2 invariant-9 activation | fire once `lives` non-empty | FR-5 |
| OQ-3 lift vs reference | seam **references** provenance (b fills it) | FR-2 |
| OQ-4 rollup form | distribution + %, labeled `declared` | FR-3/4 |
| OQ-5 cross-repo value set | `unknown` + extensible enum | FR-1 |
| OQ-6 edge vs node | **edge-carried, node derived** (resolved) | REQ-16 |

## Loop entry

```bash
python3 scripts/navigator_spec_delivery_loop.py --status       # REQ-18 should now gate READY
python3 scripts/navigator_spec_delivery_loop.py REQ-18
python3 scripts/navigator_spec_delivery_loop.py --checklist
# Stage 7 HARVEST = /harden-then-harvest on the shipped surface
```

## Pointers
- Spec: `REQ-18-realization-regime-and-determinism-rollup.md` · Research: `RESEARCH_llm-interpreter-backend-and-realization-facet.md`
- Depends-on (landed): `REQ-16` (edge + `regime` slot), `REQ-17` (`verify` field) · Enforcement home: `govern.py` (REQ-06)
- Node code: `src/startd8/navigator/models.py` (the `regime` slot + `derivation` edge) · IR spec: `dev-os/NODE-SCHEMA.md`
