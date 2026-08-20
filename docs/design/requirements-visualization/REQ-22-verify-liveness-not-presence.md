# Verify Liveness (not presence) — a requirement can't read verified while its check attests nothing — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`dev-os/FINDING-verify-liveness-lacuna.md` (the grounding finding + the NetBSD `O-4` incident)** · `REQ-08` (the `verify_oracle` this reuses — BUILT) · `REQ-16` (derivation edge) · `REQ-18` (invariant 9 — this strengthens FR-5) · `REQ-19` (impl provenance) · `REQ-20` (the retrospective destination)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern + FR-7 precision) · REQ-07 (the Validation Cockpit — advisory, NR-1) · Harbor Honesty-Verdict (absence-vs-error) · CL-36 `reconcile_derived` drift gate
**Audience:** operator / validator / SDK contributors / det-req-kit owners (cross-repo)
**Trust boundary:** local; opt-in gate execution under the existing `verify_oracle` sandbox (read-only allow-list, timeout); **advisory, never a blocking build gate**
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-binds-each-requirement-s-verify-b7ff3feb`
> **Semantic name:** *SDK navigator binds each requirement's verify to a runnable gate and checks its liveness so a gate that no longer resolves runs or can compare renders a loud gap not a silent green, re-checks liveness when the implementation provenance changes to catch a refactor that voids a gate, and routes a dead gate to a human-gated retrospective revision, so a requirement can never read verified while its check attests nothing.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-22`

## 0. Why this exists — close the presence≠liveness lacuna (the Functional Spine Fracture)

Grounded in a real incident (`dev-os/FINDING-verify-liveness-lacuna.md`): NetBSD `O-4` claimed
`session ≡ old_session` guarded by `make parity`; a *faithful* refactor (linear interpreter → IPC daemon)
made `session --session` block on a socket, so the parity comparison became **structurally impossible** —
yet `O-4` still has its verify prose, still points at real code, and **passes every structural check**. It
reads green while its guarantee is **dead**: a durable signal carrying no truth. *"A faithful local change
severed a global requirement↔check invariant that no participant was holding."*

Every structural check tests an **absence** (a field/link missing); none tests **present-but-dead**. This is
`honest-grounding` — the corpus's own cross-corpus principle (belief-is-cruft-until-grounded) — applied to
the corpus's own reliability instrument: **a `verify` is cruft until it is grounded in a *live* gate, not a
prose seed.** This REQ makes verification **live, not merely present**, reusing shipped machinery (Mottainai,
over-abstraction guard) — it is not a new verify engine.

**Honesty note this REQ acts on:** the SDK's own invariant 9 (REQ-18 FR-5) currently obligates `verify`
**non-empty** — *presence, not liveness* — so it would pass `O-4` too. This REQ strengthens it (FR-7).

## Design decisions

- **`verify.gate` is a plain optional field, not a framework.** A runnable handle (a command / test id /
  named fitness function) beside the prose verify — NO enum/dispatch engine (the finding's over-abstraction guard).
- **Reuse `verify_oracle` (REQ-08), don't build.** It already classifies command/assertion/manual, evaluates
  under a read-only sandbox + timeout, and distinguishes `error` from `fail` (the absence-vs-error move).
- **Structural death is a FACT (GAP); provenance-failure is a CANDIDATE.** A gate that can't resolve/run is
  not a hypothesis; a gate that fails-for-a-provenance-reason is precision-governed (REQ-06 FR-7).
- **Advisory, never blocking (REQ-07 NR-1); retiring an invariant is human-gated** (an explicit sign-off, not a silent drift).

## Overview

Add an optional `verify.gate` runnable handle; a `verify-liveness` check that flags a verify claiming
attestation whose gate doesn't resolve / doesn't run / fails-for-provenance as a LOUD gap (structural =
fact/GAP, provenance = candidate), reusing `verify_oracle`; re-check liveness when the impl's
derivation-edge provenance changes (the drift move) so a gate-voiding refactor is caught; route a dead gate
to a human-gated retrospective `Lesson` (REQ-20) that revises the requirement; and strengthen invariant 9
from presence to liveness. Dogfood against NetBSD `O-4` as the negative-control fixture. Additive, advisory,
byte-identical to clean corpora.

## Objectives

- **O-1:** A present-but-dead verify is loud, not green — target: a verify whose gate doesn't resolve/run renders a GAP; a clean verify flags 0; NetBSD `O-4` surfaces its dead parity gate.
- **O-2:** A gate-voiding refactor is caught at the fracture — target: when the impl a gate depends on changes provenance, the gate's liveness is re-checked and a now-impossible gate flags.
- **O-3:** A dead gate has a human-gated destination — target: a verify-liveness failure produces a retrospective `Lesson` proposing a revision, requiring explicit human sign-off to retire the invariant.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| integrity | The check itself becomes inert (a liveness gap in the liveness checker — the finding's own irony) | O-1/FR-8: the structural case is a FACT that ships as GAP + the NetBSD `O-4` negative-control fixture proves it fires | high |
| security | Executing arbitrary project gates | FR-2: reuse `verify_oracle`'s read-only sandbox + timeout; structural resolve-check needs no execution; a gate outside the allow-list is `unrunnable` → reported, not executed | high |
| quality | False green on a gate that fails for a provenance reason vs a real broken gate | FR-4: the Harbor absence-vs-error move — `error`/`unrunnable` (provenance) is distinguished from `fail` (territory); provenance is a precision-governed candidate (REQ-06 FR-7) | high |
| scope | A `verify.gate` dispatch framework / a blocking build gate | NR-1/NR-4: plain optional field; advisory candidate/gap only (REQ-07 NR-1) | medium |
| coordination | `verify.gate` is a det-req-kit (dev-os) schema addition | NR-5: the schema field is the cross-repo coordination (kit owner's go); the check + tie + routing are SDK-side | medium |

## Functional requirements

- **FR-1 — `verify.gate` runnable handle (additive, plain field).** Add an optional `verify.gate` beside the prose verify — a runnable handle (a command, a test id, or a named fitness function) — as a plain field, not an enum/dispatch framework; absent gate leaves the node exactly as today. Name: A requirement's verify gains an optional plain gate field naming a runnable handle without a dispatch framework. Touches: `src/startd8/navigator/models.py`, `src/startd8/navigator/det_req.py`, tests. Lives: code src/startd8/navigator/models.py. Approve?: is verify.gate a plain optional runnable handle with no dispatch framework?. Manual: human acceptance — the additive-field shape is read in the unit suite; no runnable `startd8` span attests it. Verify: a node with a `verify.gate` carries the handle; a node without one is unchanged and `node_field_names()` reflects only the additive gate. Serves: O-1
- **FR-2 — The `verify-liveness` check (reuse verify_oracle).** A check flags a verify that claims attestation whose gate (a) doesn't resolve, (b) doesn't run, or (c) fails-for-a-provenance-reason as a loud finding — reusing `verify_oracle`'s classify + read-only-sandbox evaluate + timeout — never a silent green. Name: A verify-liveness check flags a gate that does not resolve run or compare reusing verify_oracle rather than a new engine. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/verify_oracle.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does the liveness check reuse verify_oracle and flag a non-resolving or non-running gate?. Manual: human acceptance — a reviewer confirms the check reuses verify_oracle; the runnable half is the unit suite, not a `startd8` command. Verify: a fixture node whose gate does not resolve or does not run yields a named liveness finding; the check imports `verify_oracle` (no new execution engine). Serves: O-1
- **FR-3 — Structural death is a FACT (GAP); provenance-failure is a CANDIDATE.** A gate that structurally can't resolve or run ships as a GAP (a fact, not a hypothesis); a gate that fails for a provenance reason ships as a precision-governed CANDIDATE (REQ-06 FR-7). Name: A non-resolving gate is a fact reported as a gap while a provenance failure is a precision-governed candidate. Touches: `src/startd8/navigator/govern.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: is a structurally-dead gate a GAP and a provenance-failure a candidate?. Manual: human acceptance — the gap-versus-candidate distinction is a judgement a human confirms in the finding text. Verify: a gate that does not resolve is classified GAP; a gate that runs but fails for a provenance reason is classified candidate; the two are not conflated. Serves: O-1
- **FR-4 — Absence-vs-error (Harbor Honesty-Verdict).** The check distinguishes a gate that reports broken (a territory reason) from a gate that can no longer run the comparison (a provenance reason — the Functional Spine Fracture signature), reusing `verify_oracle`'s `error`/`unrunnable` vs `fail` verdicts. Name: The check distinguishes a gate that reports broken from a gate that can no longer run the comparison. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/verify_oracle.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does the check separate a territory fail from a provenance unrunnable?. Manual: human acceptance — the absence-versus-error split is confirmed by reading the two distinct findings. Verify: a gate returning a nonzero territory result classifies `fail`; a gate that can no longer run the comparison classifies `unrunnable`/`error` (the spine-fracture signature), and the two carry distinct findings. Serves: O-2
- **FR-5 — Re-check liveness on impl-provenance change (the drift move).** When the implementation a gate depends on changes provenance (its derivation-edge / REQ-19 provenance changes), the gate's liveness is re-checked, so a refactor that voids a gate is caught at the fracture — the `reconcile_derived` fail-loud-on-staleness move applied to verify. Name: A change in the implementation provenance a gate depends on re-checks the gate liveness catching a gate-voiding refactor. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/realization.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does an impl-provenance change trigger a liveness re-check of the dependent gate?. Manual: human acceptance — the drift re-check is exercised by the unit suite and its meaning confirmed by a reviewer. Verify: changing the provenance of the impl a gate depends on triggers a liveness re-check, and a now-structurally-impossible gate flags where it did not before the change. Serves: O-2
- **FR-6 — Route a dead gate to a human-gated retrospective revision.** A verify-liveness failure produces a grounded retrospective `Lesson` (REQ-20) that derives-from the dead-gate finding and proposes a `revises` to the requirement, requiring explicit human sign-off to retire the invariant — never a silent drift. Name: A verify-liveness failure produces a grounded lesson proposing a human-gated revision to the requirement. Touches: `src/startd8/navigator/sources_retrospective.py`, `src/startd8/navigator/govern.py`, tests. Lives: code src/startd8/navigator/sources_retrospective.py. Approve?: does a dead gate become a human-gated retrospective proposal rather than a silent drift?. Manual: human acceptance — propose-don't-dispose is by definition a human sign-off step. Verify: a verify-liveness GAP produces a `proposed` Lesson deriving-from the finding and revising the requirement; retiring the invariant requires an explicit human accept. Serves: O-3
- **FR-7 — Strengthen invariant 9 from presence to liveness (amends REQ-18 FR-5).** Invariant 9's verify obligation is strengthened from `verify non-empty` (presence) to `verify live` — a `regime==llm` edge to a realized node whose verify is present-but-dead is now a violation, closing the SDK's own instance of this lacuna. Name: Invariant 9 obligates a live verify not merely a present one closing the SDK's own presence-not-liveness gap. Touches: `src/startd8/navigator/govern.py`, `docs/design/requirements-visualization/REQ-18-realization-regime-and-determinism-rollup.md`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does invariant 9 now require a live verify not just a present one?. Manual: human acceptance — the amendment is confirmed by reading REQ-18 FR-5's recorded amendment. Verify: a realized `llm`-regime node with a present-but-dead verify yields an invariant-9 violation; the same node with a live gate does not; REQ-18 FR-5 carries the recorded amendment. Serves: O-3
- **FR-8 — Dogfood NetBSD `O-4`; additive, advisory, byte-identical.** The NetBSD `O-4` dead parity gate is the negative-control fixture (surfaces as a GAP); a clean corpus flags 0; the check is advisory (candidate/gap, not a blocking build gate — REQ-07 NR-1); and clean corpora render byte-identical. Name: The NetBSD O-4 dead gate is the negative-control fixture and the advisory check leaves clean corpora byte-identical. Touches: `tests/unit/navigator/fixtures/`, `tests/unit/navigator/test_verify_liveness.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_verify_liveness.py. Approve?: does the check fire on the O-4 fixture and leave clean corpora byte-identical and unblocked?. Manual: human acceptance — the negative-control verdict is read by a human; test_no_profile_is_byte_identical is the machine half. Verify: the NetBSD `O-4` fixture surfaces its dead parity gate as a GAP; a clean FR flags 0; `test_no_profile_is_byte_identical` passes unedited; the check is advisory (no build blocked). Serves: O-1

## Non-requirements

- **NR-1:** Does NOT block the build — the check is advisory (candidate/gap), consistent with the Validation Cockpit (REQ-07 NR-1); a dead gate routes to a human decision, it does not halt a pipeline.
- **NR-2:** Does NOT build a new verify-execution engine — reuses `verify_oracle` (REQ-08); the structural resolve-check needs no execution at all.
- **NR-3:** Does NOT execute arbitrary project gates outside `verify_oracle`'s read-only sandbox/allow-list — an unrunnable-here gate is REPORTED as unrunnable, never run.
- **NR-4:** `verify.gate` is a plain optional field, NOT an enum/dispatch framework (the over-abstraction guard).
- **NR-5:** The `verify.gate` schema field is a det-req-kit (dev-os) addition — cross-repo, needs the kit owner's go; the check + provenance tie + retrospective routing + invariant-9 strengthening are SDK-side.
- **NR-6:** Build-blocked (not spec-blocked) on REQ-19 (impl provenance) + REQ-20 (the Lesson destination). REQ-08 (`verify_oracle`) and REQ-16 (edge) have landed.
