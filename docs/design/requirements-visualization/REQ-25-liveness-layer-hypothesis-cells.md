# Liveness Layer — the Hypothesis Cells (fact-rungs ship, judgment-rungs park-by-default) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`RESEARCH_present-but-dead-lacuna-census.md` (the column)** · `REQ-22` (verify-liveness — BUILT, the pattern) · `REQ-23` (the fact cells — BUILT, the layer) · `REQ-18` (invariant 9 + provenance) · `REQ-19` (impl provenance) · `REQ-20` (retrospective destination) · `query_prime/security` (the reused verifier)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern) · **REQ-07 FR-7 (the precision gate)** · Harbor Honesty-Verdict (absence-vs-error) · the fact/hypothesis orthogonality (the cockpit's 0-vs-2/2 data)
**Audience:** operator / validator / SDK contributors
**Trust boundary:** local; advisory (candidate/gap), never blocking; judgment-rungs are declared-not-executed until precision-cleared; any LLM-judge is verify-live
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-adds-the-hypothesis-cells-of-the-defb861b`
> **Semantic name:** *SDK navigator adds the hypothesis cells of the liveness layer by decomposing each into a deterministic fact-rung that ships as a gap reusing existing checkers (mitigation-inert via the security verifier, non-goal-violated via import and AST checks, Touches-dead via a provenance-change trigger) and a semantic judgment-rung parked by default behind a precision gate that ships only as an evidence-citing candidate never a gap, with any LLM judge itself verify-live so the checker never trips its own class.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-25`

## 0. Why this exists — complete the column without crying wolf

REQ-22/23 shipped the liveness layer's **fact cells** (structural death → GAP). The census left three
**hypothesis cells** — `mitigation-inert`, `non-goal-violated`, `Touches-resolves-but-dead` — which check
*semantic* death ("does this present, runnable thing still do what it claims?"). These are **judgments**, and
a wrong judgment shipped as a GAP is the value prop's failure **in reverse**: a durable *red* carrying no
truth. The cockpit measured the risk — its structural facts fired 0 false positives, its one heuristic 2/2.

So this REQ completes the column under one discipline: **decompose each hypothesis cell into a deterministic
fact-rung and a semantic judgment-rung.** The **fact-rungs ship as GAPs, reusing checkers that already exist**;
the **judgment-rungs are parked by default behind the precision gate** (REQ-07 FR-7) — declared for
completeness, executed only when a labeled fixture set proves precision, and even then shipping only as an
evidence-citing **candidate, never a GAP.** And — the finding's own irony made a guard — any LLM-judge is
itself **verify-live** (invariant 9), so the checker cannot trip its own class.

## Design decisions

- **Fact-rung / judgment-rung decomposition.** Each cell = a deterministic trigger (ships as GAP, reuse) +
  a residual semantic judgment (parked, precision-gated candidate).
- **Reuse, don't build** the fact-rungs: `query_prime/security` (mitigation), the import/AST checks (non-goal),
  REQ-19 provenance-change (Touches). No new deterministic checker.
- **Park-by-default.** A judgment-rung's default posture is *declared, not executed* — it degrades gracefully
  (Tier-2 behind Tier-1), and only precision (REQ-07 FR-7) un-parks it.
- **A judgment never ships as a GAP** — only as a candidate (evidence-cited, dismissible-in-one-glance). A
  false GAP is a durable-red-carrying-no-truth.
- **The judge is dog-fooded** — an LLM-judge is LLM-realized ⇒ invariant 9 ⇒ it carries a live verify.

## Overview

Add the three hypothesis cells to the `liveness` layer, each decomposed: `mitigation-inert` fact-rung reuses
`query_prime/security verify_file` (a named security mitigation the verifier reports absent → GAP);
`non-goal-violated` fact-rung reuses the import/AST checks (a structural non-goal the code violates → GAP);
`Touches-dead` fact-rung reuses REQ-19 provenance-change (a Touches'd file whose provenance changed → a
re-judge trigger). Each cell's semantic judgment-rung is parked-by-default behind REQ-07 FR-7, ships only as
an evidence-citing candidate, and — if it uses an LLM-judge — that judge is verify-live. Advisory, additive,
byte-identical; dead claims route to a human-gated retrospective (REQ-20).

## Objectives

- **O-1:** The deterministic fact-rungs ship as GAPs reusing existing checkers — target: a named security mitigation the verifier reports absent (GAP), a structural non-goal the code violates (GAP), and a Touches'd file whose provenance changed (re-judge trigger).
- **O-2:** The semantic judgment-rungs are parked-by-default behind the precision gate — target: no judgment-rung executes until it clears a precision threshold on a labeled fixture set; a parked rung is declared not executed; an enabled one ships as a candidate, never a GAP.
- **O-3:** The checker doesn't trip its own class — target: any LLM-judge is verify-live (invariant 9); the cells register in the liveness layer (Tier-2 behind Tier-1) and route dead claims to a human gate.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| integrity | A semantic judgment cries wolf — a false GAP (durable red carrying no truth) | NR-4/FR-4: judgment-rungs are parked-by-default + ship only as precision-cleared candidates, never GAPs | high |
| integrity | The liveness checker itself uses an un-verified LLM-judge (trips its own class) | FR-6: an LLM-judge is LLM-realized ⇒ invariant 9 ⇒ it must be verify-live | high |
| scope | Building new deterministic checkers instead of reusing | NR-2: fact-rungs reuse `query_prime/security`, the import/AST checks, and REQ-19 provenance — no new checker | high |
| quality | A judgment-rung shipped without a precision baseline | FR-4/REQ-07 FR-7: park until a labeled fixture set clears the precision threshold | high |
| dependency | Needs the built liveness layer + reuse machinery + a labeled fixture set | NR-6: REQ-22/23 + `query_prime` + REQ-19 are built; the judgment-rungs additionally need the fixture set before enabling | medium |

## Functional requirements

- **FR-1 — `mitigation-inert` fact-rung (reuse the security verifier).** A govern check flags a risk whose named security mitigation the `query_prime/security` verifier reports absent (injection/credentials/lifecycle) as a GAP — the mitigation is present in the spec but not live in the code — reusing the existing verifier, not a new checker. Name: A govern check flags a named security mitigation the security verifier reports absent as a structural gap. Touches: `src/startd8/navigator/govern.py`, `src/startd8/query_prime/security/`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does a named security mitigation the verifier reports absent render a GAP via reuse?. Verify: a risk whose mitigation names a security control the `query_prime/security` verifier reports absent yields a GAP; a mitigation the verifier confirms present yields none; no new verifier is added. Serves: O-1
- **FR-2 — `non-goal-violated` fact-rung (reuse import/AST checks).** A govern check flags a structurally-checkable non-goal (an import ban / AST-detectable property, e.g. "imports nothing from a construction subsystem") that the code violates as a GAP, reusing the existing import/AST checks. Name: A govern check flags a structural non-goal the code violates via reused import and AST checks. Touches: `src/startd8/navigator/govern.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does a violated structural non-goal render a GAP via reused checks?. Verify: a non-goal banning an import that the code nonetheless imports yields a GAP; a respected structural non-goal yields none; the check reuses the import/AST machinery. Serves: O-1
- **FR-3 — `Touches-dead` fact-trigger (reuse provenance-change).** A govern check flags a Touches'd file whose realization provenance (REQ-19) has changed since the requirement's last attestation as a re-judge trigger — a fact (the file changed), not yet a judgment (whether it still matches the claim). Name: A govern check flags a Touches file whose provenance changed as a re-judge trigger using REQ-19 provenance. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/realization.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does a Touches file whose provenance changed raise a re-judge trigger?. Verify: a Touches'd file whose provenance changed since last attestation raises a re-judge trigger; an unchanged Touches'd file raises none. Serves: O-1
- **FR-4 — Judgment-rungs park-by-default behind the precision gate.** Each cell's semantic judgment-rung (soft mitigation, soft non-goal, the Touches re-judge) is declared but NOT executed by default; it runs only when it clears a precision threshold on a labeled fixture set (REQ-07 FR-7); a parked rung degrades gracefully (Tier-2 behind Tier-1). Name: Each semantic judgment-rung is declared but parked and unruns until it clears a precision threshold on a labeled fixture set. Touches: `src/startd8/navigator/govern.py`, `tests/unit/navigator/test_liveness_layer.py`. Lives: code src/startd8/navigator/govern.py. Approve?: are judgment-rungs parked-by-default and gated by measured precision?. Verify: with no precision baseline, a judgment-rung executes nothing and reports parked; supplying a labeled fixture set that clears the threshold un-parks it; below-threshold it stays parked. Serves: O-2
- **FR-5 — An enabled judgment-rung is a candidate, never a GAP.** When a judgment-rung is un-parked, it renders a precision-governed CANDIDATE — evidence-citing (the specific bytes) and dismissible in one glance — never a GAP; a false judgment can therefore be dismissed, not trusted as a fact. Name: An un-parked judgment-rung ships an evidence-citing dismissible candidate never a gap. Touches: `src/startd8/navigator/govern.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does an enabled judgment-rung ship a candidate with evidence not a GAP?. Verify: an un-parked judgment-rung emits a candidate carrying the cited bytes and a one-glance dismissal; it never emits a GAP; a fact-rung on the same cell still emits a GAP. Serves: O-2
- **FR-6 — The LLM-judge is verify-live (don't trip your own class).** Any LLM-judge a judgment-rung uses is LLM-realized, so by invariant 9 it carries a live verify; a judgment-rung whose judge is not verify-live is itself parked — the liveness checker cannot ship a judgment from an unverified judge. Name: Any LLM judge used by a judgment-rung is verify-live per invariant 9 or the rung stays parked. Touches: `src/startd8/navigator/govern.py`, `tests/unit/navigator/test_liveness_layer.py`. Lives: code src/startd8/navigator/govern.py. Approve?: is an LLM-judge required to be verify-live before its rung ships?. Verify: a judgment-rung backed by a verify-live judge may un-park; a judgment-rung whose judge lacks a live verify stays parked with a named reason. Serves: O-3
- **FR-7 — Register in the liveness layer, Tier-2 behind Tier-1, human-gated retirement.** The three cells register in the same `liveness` govern layer as REQ-22/23 with the judgment-rungs staged as Tier-2 behind the Tier-1 fact-rungs (degrading gracefully), and a confirmed dead claim routes to a human-gated retrospective `Lesson` (REQ-20). Name: The hypothesis cells register in the liveness layer Tier-2 behind Tier-1 routing a dead claim to a human-gated retrospective. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/sources_retrospective.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: do the cells register in the liveness layer with Tier-2 staged behind Tier-1 and a human gate?. Verify: `govern` reports the three cells under the `liveness` layer with judgment-rungs Tier-2; the fact-rungs run without the judgment-rungs; a confirmed dead claim produces a `proposed` retrospective Lesson requiring human accept. Serves: O-3
- **FR-8 — Additive, advisory, byte-identical, dogfood.** The cells are additive and advisory (candidate/gap, not blocking); clean corpora render byte-identical; parked judgment-rungs execute nothing; and fixtures (an absent security mitigation, a violated import non-goal, a provenance-changed Touches) surface as GAPs/triggers while clean ones flag 0. Name: The hypothesis cells are additive advisory byte-identical with parked rungs executing nothing and proven by fixtures. Touches: `tests/unit/navigator/test_liveness_layer.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_liveness_layer.py. Approve?: are the cells additive advisory byte-identical with parked rungs inert and proven by fixtures?. Verify: the fact-rung fixtures each yield a GAP/trigger; clean fixtures flag 0; parked judgment-rungs spawn no execution; `test_no_profile_is_byte_identical` passes unedited; no build is blocked. Serves: O-1, O-2

## Non-requirements

- **NR-1:** Does NOT block the build — advisory (candidate/gap), consistent with REQ-07; a dead claim routes to a human decision.
- **NR-2:** Does NOT build new deterministic checkers — the fact-rungs reuse `query_prime/security`, the import/AST checks, and REQ-19 provenance-change.
- **NR-3:** Judgment-rungs are PARKED by default — declared-not-executed until a labeled fixture set clears the REQ-07 FR-7 precision threshold; the default posture ships nothing from them.
- **NR-4:** A judgment-rung NEVER ships as a GAP — only as a precision-cleared, evidence-citing candidate (a false GAP is a durable-red-carrying-no-truth).
- **NR-5:** Does NOT ship a judgment from an unverified LLM-judge — the judge must be verify-live (invariant 9) or the rung stays parked (FR-6).
- **NR-6:** Build-blocked (not spec-blocked): the fact-rungs on REQ-22/23 (built) + `query_prime` (exists) + REQ-19 provenance (built); the judgment-rungs additionally need a labeled fixture set before un-parking.
