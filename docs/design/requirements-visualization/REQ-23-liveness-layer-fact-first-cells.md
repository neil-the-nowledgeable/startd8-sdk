# Liveness Layer — the Fact-First Cells (target-unmeasured + served-by-a-dead-FR) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`RESEARCH_present-but-dead-lacuna-census.md` (the column this fills)** · `REQ-22` (verify-liveness — cell 1, the pattern + the roll-up input) · `REQ-18` (the roll-up machinery) · `REQ-20` (the retrospective destination) · `REQ-06` (govern)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern + FR-7 precision) · REQ-07 (Validation Cockpit — advisory) · Harbor Honesty-Verdict (absence-vs-error) · Feature-Observability coverage-by-construction
**Audience:** operator / validator / SDK contributors
**Trust boundary:** local; advisory (candidate/gap), never a blocking build gate; no execution beyond the resolve-check
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-adds-the-fact-first-cells-of-the-a05441c3`
> **Semantic name:** *SDK navigator adds the fact-first cells of the liveness layer: a target set with no live signal measuring it renders a gap, and an outcome all of whose serving requirements have a dead verify renders a gap by rolling verify-liveness up the serves edge, both structural facts shipped as gaps not candidates, reusing the verify-liveness pattern and routing a dead claim to a human-gated retrospective revision.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-23`

## 0. Why this exists — ship the deterministic column first

The census (`RESEARCH_present-but-dead-lacuna-census.md`) found the requirement-level **present-but-dead
column** is open, and split its cells into **facts** (structural death → GAP, no precision tuning) and
**hypotheses** (provenance/semantic death → precision-governed candidate). This REQ ships the two **fact**
cells — the ones that are true-by-construction and can't cry wolf — leaving the hypothesis cells to a later,
precision-gated REQ (NR-3):

1. **`target-unmeasured`** — an outcome/objective carries a `target` (a measurable goal) but **no live signal
   measures it**. A target with no measurement is a claim with no attestation — the authoring-time twin of
   Feature-Observability's "a declared goal with no live signal is a loud gap." Structural fact → GAP.
2. **`served-by-a-dead-FR`** — an outcome is *served* (not orphan) but **all** its serving FRs fail
   verify-liveness (REQ-22). The outcome is served-on-paper while its guarantee is dead. This is
   **verify-liveness rolled up the serves-edge** — *free* once REQ-22 + the roll-up machinery exist.

Both reuse REQ-22's four-step pattern (bind → check-live → absence-vs-error → human-gated retrospective) and
register in the same **`liveness` govern layer** — one layer, not a scatter.

## Design decisions

- **Fact cells only.** Structural death is a fact → ships as GAP. The hypothesis cells (mitigation-inert,
  non-goal-violated, Touches-resolves-but-dead) are deferred to a precision-governed REQ (NR-3).
- **Reuse, don't build.** `served-by-a-dead-FR` is verify-liveness (REQ-22) rolled up via the existing
  status/realization roll-up; `target-unmeasured`'s signal-binding is a plain optional field (no framework).
- **Advisory + human-gated retirement** — a dead target/outcome routes to a REQ-20 `Lesson`, never a silent drift.

## Overview

Add an optional `target.signal` binding (a live metric/measurement handle beside a target); a
`target-unmeasured` govern check (a target with no bound live signal → GAP, fact); a `served-by-a-dead-FR`
check that rolls verify-liveness up the serves-edge (an outcome all of whose serving FRs are dead → GAP);
both distinguishing absence (no signal / no serving FR) from error (signal/gate broken), both routing to a
human-gated retrospective, both registered in the `liveness` layer. Additive, advisory, byte-identical to
clean corpora.

## Objectives

- **O-1:** A target with no live measurement is loud, not green — target: an outcome carrying a `target` with no bound live signal renders a GAP; a measured target flags 0.
- **O-2:** An outcome served only by dead FRs is loud, not green — target: an outcome all of whose serving FRs fail verify-liveness renders a GAP by roll-up; an outcome with ≥1 live-verified FR flags 0.
- **O-3:** Both are facts, layered, and human-gated — target: both ship as GAPs (not candidates), register in the `liveness` layer, and route a dead claim to a human-gated retrospective proposal.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | `target-unmeasured` fires on a target whose signal exists under a different name (vocabulary miss) | FR-1: bind via an explicit `target.signal` field (presence-checked), not a name-guess — absent binding is the fact, not a heuristic match | high |
| quality | `served-by-a-dead-FR` mis-rolls (an outcome with one live FR wrongly flagged) | FR-3: GAP only when ALL serving FRs fail verify-liveness; ≥1 live FR ⇒ clean (min-rolls-up over the serves-edge) | high |
| scope | Shipping the hypothesis cells here (they cry wolf) | NR-3: fact cells only; mitigation-inert / non-goal-violated / Touches-dead are a later precision-governed REQ | medium |
| dependency | `served-by-a-dead-FR` needs verify-liveness + the roll-up | NR-5: build-blocked on REQ-22 + REQ-18's roll-up; `target-unmeasured` is independent | high |

## Functional requirements

- **FR-1 — `target.signal` binding (additive plain field).** Add an optional `target.signal` beside an outcome/objective target — a live measurement handle (a metric name or a live query) — as a plain field, not a framework; absent binding leaves the node unchanged. Name: An outcome target gains an optional plain signal field binding it to a live measurement handle. Touches: `src/startd8/navigator/models.py`, `src/startd8/navigator/det_req.py`, tests. Lives: code src/startd8/navigator/models.py. Approve?: is target.signal a plain optional live-measurement binding with no framework?. Verify: an outcome with a `target.signal` carries the handle; an outcome without one is unchanged. Serves: O-1
- **FR-2 — `target-unmeasured` check (fact → GAP).** A govern check flags an outcome/objective that carries a `target` but has no bound live signal (or a bound signal that does not resolve) as a GAP — a structural fact, the authoring-time twin of Feature-Observability's loud-gap-for-a-goal-with-no-live-signal. Name: A govern check flags a target with no bound live signal as a structural gap. Touches: `src/startd8/navigator/govern.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does a target with no live signal render a GAP not a candidate?. Verify: an outcome with a `target` and no bound (or non-resolving) signal yields a GAP; an outcome whose `target.signal` resolves yields none. Serves: O-1
- **FR-3 — `served-by-a-dead-FR` check (verify-liveness rolled up the serves-edge).** A govern check flags an outcome that is served but ALL of whose serving FRs fail verify-liveness (REQ-22) as a GAP, rolling verify-liveness up the serves-edge via the existing roll-up (min-rolls-up: ≥1 live-verified FR ⇒ clean); it reuses REQ-22, not a new checker. Name: A govern check rolls verify-liveness up the serves edge flagging an outcome all of whose serving FRs are dead. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/verify_oracle.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does an outcome served only by dead FRs render a GAP while one live FR clears it?. Verify: an outcome all of whose serving FRs fail verify-liveness yields a GAP; the same outcome with ≥1 live-verified serving FR yields none. Serves: O-2
- **FR-4 — Fact → GAP, absence-vs-error, human-gated route.** Both checks ship structural death as a GAP (not a precision-governed candidate), distinguish absence (no signal / no serving FR) from error (signal or gate broken — Harbor Honesty-Verdict), and route a dead target/outcome to a human-gated retrospective `Lesson` (REQ-20). Name: Both checks ship structural death as a gap distinguish absence from error and route to a human-gated retrospective. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/sources_retrospective.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: do both ship as GAP, separate absence from error, and route to a human gate?. Verify: a no-signal target and an all-dead-served outcome are GAPs; a broken-signal case classifies `error`, not absent; both produce a `proposed` retrospective Lesson requiring human accept to retire the claim. Serves: O-3
- **FR-5 — Register in the `liveness` layer.** Both checks register as members of a single `liveness` govern layer alongside verify-liveness (REQ-22), so the present-but-dead column is enforced as one layer, not a scatter, and reports under one heading. Name: Both checks register in the single liveness govern layer alongside verify-liveness. Touches: `src/startd8/navigator/govern.py`, `tests/unit/navigator/test_govern.py`. Lives: code src/startd8/navigator/govern.py. Approve?: are the checks members of one liveness layer with verify-liveness?. Verify: `govern` reports `target-unmeasured`, `served-by-a-dead-FR`, and `verify-liveness` under one `liveness` layer; a corpus clean on all three reports the layer clean. Serves: O-3
- **FR-6 — Additive, advisory, byte-identical, dogfood.** The checks are additive and advisory (candidate/gap, not blocking); clean corpora render byte-identical; and fixtures (an outcome with an unmeasured target; an outcome served only by dead FRs) surface as GAPs while clean ones flag 0. Name: The liveness fact cells are additive advisory byte-identical and proven by gap and clean fixtures. Touches: `tests/unit/navigator/test_liveness_layer.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_liveness_layer.py. Approve?: are the checks additive advisory byte-identical and proven by fixtures?. Verify: an unmeasured-target fixture and a dead-FR-served fixture each yield a GAP; clean fixtures flag 0; `test_no_profile_is_byte_identical` passes unedited; no build is blocked. Serves: O-1, O-2

## Non-requirements

- **NR-1:** Does NOT block the build — advisory (candidate/gap), consistent with REQ-07; a dead claim routes to a human decision, it does not halt a pipeline.
- **NR-2:** Does NOT build new checkers — `served-by-a-dead-FR` reuses REQ-22 + the existing roll-up; `target-unmeasured` is a presence-check on a plain binding (the resolve-check needs no execution).
- **NR-3:** Does NOT ship the hypothesis cells — `mitigation-inert`, `non-goal-violated`, `Touches-resolves-but-dead` are precision-governed candidates for a later REQ (they cry wolf without a precision gate).
- **NR-4:** `target.signal` is a plain optional field, NOT a metric/dispatch framework (the over-abstraction guard).
- **NR-5:** Build-blocked (not spec-blocked): `served-by-a-dead-FR` on REQ-22 (verify-liveness) + REQ-18's roll-up; `target-unmeasured` is independent and buildable once the liveness layer (REQ-22) exists.
