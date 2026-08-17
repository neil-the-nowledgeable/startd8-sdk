# Research: the present-but-dead lacuna census — verify-liveness is one cell of an empty column

**Date:** 2026-08-16 · **Type:** pattern analysis / Mendeleev census (emeritus) · **Status:** grounded
**Generalizes:** `REQ-22` (verify-liveness) · `VALUE_PROP_verification-that-cannot-silently-die.md`
**Grounded in:** `dev-os/FINDING-verify-liveness-lacuna.md` (the axis-of-symmetry move) · SDK `govern.py` +
`forward_manifest_validator.py` (the real check-sets) · the cockpit's false-positive data (`dev-os/REQ-07`)

## The move

The finding named the axis: run the check-set against its **axis of symmetry** — every check tests either
*"is X **absent**?"* or *"is X **present-but-dead**?"* verify-liveness fills one present-but-dead cell. This
note **censuses the whole column** (the Mendeleev move) against the *real* check-sets, and finds the lacuna
is not random — it is a **layer gap**.

## The key finding — the present-but-dead column is FILLED at the code level, EMPTY at the requirement level

Grounded in the actual code:
- **`forward_manifest_validator` (code level)** already fills present-but-dead cells: **stubs** (a function
  present but empty), **reachability** (code present but unreachable), **discarded-returns** (a return
  present but ignored). Liveness-checking *exists* for generated code.
- **`govern.py` (requirement level)** is almost pure *absence*: missing-name, missing-verify, missing-serves,
  dangling-xref (a *reference* that doesn't resolve — the closest to liveness, but it checks resolution, not
  truth). **No requirement-level check asks "is this claim present-but-dead?"**

So the lacuna is a **stratum gap**: the corpus learned to detect present-but-dead *code* but never lifted it
to present-but-dead *requirements*. **verify-liveness (REQ-22) is the first requirement-level liveness check** —
and the census shows the rest of that column is open. (This is the stratified grammar again: *liveness* is a
layer, present at the code stratum, absent at the requirement stratum.)

## The census (grounded in the real absence-checks)

| absence-check (mature) | its present-but-dead twin (the lacuna) | fact / hypothesis | status |
|---|---|---|---|
| no-verify | **verify-liveness** — gate doesn't resolve / run / compare | structural=fact · provenance=hyp | **REQ-22 (specced)** |
| no-target | **target-unmeasured** — a target set with no *live* signal measuring it | fact if no signal binds; hyp if stale | GAP (the feature-observability twin the finding cites) |
| no-mitigation | **mitigation-inert** — a mitigation named but not wired / not firing | hypothesis | GAP |
| orphan / unserved-outcome | **served-only-by-a-dead-FR** — an outcome served, but its FR's verify is dead | derived (verify-liveness rolled up) | GAP — *composes* REQ-22 up the graph |
| (orphan) | **serves-a-dead-outcome** — links to an outcome deleted/renamed | fact (ref) | PARTIAL — `dangling-xref` catches ref-death, not semantic-death |
| no-non-goals | **non-goal-violated** — a non-goal stated but the code violates it | hypothesis | GAP |
| dangling-Touches | **Touches-resolves-but-dead** — points at real code that no longer does what's claimed | hypothesis (map-vs-territory) | GAP — the finding's named sibling |

## The shared pattern — one pattern × N claims, not N engines

Every present-but-dead check is the *same* shape (the verify-liveness pattern, generalized):

1. **Bind** the claim to a **live signal** (verify→gate · target→metric · Touches→behavior · non-goal→code-assertion · mitigation→a firing guard).
2. **Check the signal is live** (resolves / runs / attests).
3. **Distinguish absence-vs-error** (the Harbor Honesty-Verdict move): *structural death* (can't resolve/run) is a **FACT → GAP**; *provenance failure* (bound but no longer attests) is a **HYPOTHESIS → candidate**.
4. **Route a dead signal** to a **human-gated retrospective** (retiring an invariant needs sign-off, not silent drift).

So filling the column is not N new engines — it is REQ-22's pattern applied per claim, reusing the same
machinery (`verify_oracle`, the derivation edge, the retrospective `Lesson`, the `govern` precision gate).

## The fact/hypothesis orthogonality (grounded — don't ship hypotheses as facts)

The cockpit's own data settles how each new check ships: its structural facts (orphan / verify-present /
mitigation) fired **0** false positives; its one heuristic (weak-verify) fired **2/2**. `kind` (gap vs
candidate) is **orthogonal** to source. So: **structural-death cells ship as GAPs** (fact — a gate that
can't resolve is not a hypothesis); **provenance/semantic cells ship as candidates** (precision-governed,
REQ-06 FR-7). Don't let the hypothesis cells (non-goal-violated, Touches-dead) cry wolf — park them behind a
precision gate; ship the deterministic cells first.

## The amplified value prop

REQ-22 alone: *"a requirement can't lie about being **verified**."* The full column:

> **A requirement cannot carry ANY present-but-dead claim.** Every assertion it makes — verified · targeted ·
> mitigated · scoped · served · wired — is bound to a **live signal**, and a signal that silently dies renders
> **loud, not green.** The durable green made honest, across the whole requirement.

This is `honest-grounding` applied not just to `verify` but to *every* field a requirement asserts. It is the
same one principle, censused across the check-set.

## How it composes (next)

- **REQ-22 = cell 1** (verify-liveness). The remaining cells are **REQ-23+**, each the same pattern on a
  different claim — sequence by fact-first (target-unmeasured, serves-a-dead-outcome) before hypothesis
  (non-goal-violated, Touches-dead).
- **Ship the deterministic column first** (facts → GAPs), park the heuristic cells behind the precision gate.
- The `served-only-by-a-dead-FR` cell is *free* once REQ-22 lands — it is verify-liveness **rolled up** the
  serves-edge (the roll-up machinery already exists, like status/realization).
- Everything reuses REQ-22's four-step pattern → a single **`liveness` layer** of govern checks, not a scatter.
