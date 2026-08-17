# Self-Dogfood the Verify Gate — adopt on our own corpus, honestly — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`ANALYSIS_corpus-self-study-five-threads.md` Thread 1 (the 96%-afflicted finding)** · `REQ-22` (verify-liveness + `verify.gate` — BUILT) · `REQ-23` (the liveness layer — BUILT) · `VALUE_PROP_verification-that-cannot-silently-die.md`
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern) · REQ-07 (advisory) · `verify_oracle` (classify)
**Audience:** operator / validator / SDK contributors (the corpus's own authors)
**Trust boundary:** local; advisory; the self-gate never blocks — it routes to a human triage decision
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-dogfoods-the-verify-liveness-20926abc`
> **Semantic name:** *SDK navigator dogfoods the verify-liveness value prop on its own requirements corpus by splitting each verify into mechanically-attestable versus legitimately-manual, adopting a runnable verify gate on the mechanical ones, marking the manual ones explicitly so the corpus reads honestly, and standing up a self-liveness gate so the corpus cannot silently regress to present-but-dead.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-27`

## 0. Why this exists — the corpus authored the cure while ~96% afflicted

The self-study dogfood (Thread 1) measured it: **95.6% of our own verifies (172/180) are present-but-dead
prose seeds; `verify.gate` adoption is 0/180; REQ-22 itself is 8/8 prose.** The corpus that authored *"a
requirement can't read verified while its check attests nothing"* fails its own test. The honest response is
**not** a blanket authoring campaign — many of those verifies are *legitimately* human-checked prose
(`assertion`/`manual`), and forcing a gate on them would be a false-mechanical lie in the other direction.
The honest fix has three parts: **(1) split** each verify into *mechanically-attestable* (claims a runnable
check → should carry a gate) vs *legitimately-manual* (human acceptance → mark it, don't fake a gate);
**(2) adopt** `verify.gate` on the mechanical ones (dogfood REQ-22's own remedy); **(3) stand up a
self-liveness gate** so the corpus can't silently regress. The result: "96% dead" becomes an *honest*
"N% real gap (mechanical-but-gateless) + M% explicitly-manual" — the corpus reads true.

## Design decisions

- **Not a blanket gate campaign.** A gate is adopted only where the verify *claims mechanical attestation*;
  legitimately-manual verifies are *marked*, not faked (a false gate is the failure in reverse).
- **Reuse `verify_oracle` + the liveness layer.** The split is `verify_oracle.classify`; the self-gate is
  the built REQ-22/23 liveness layer pointed at our own corpus — no new engine.
- **Advisory + human-triaged.** The self-gate routes a mechanical-but-gateless FR to a human decision
  (adopt-a-gate or mark-manual), never blocks.

## Overview

Classify every corpus FR's verify (`command` / `assertion` / `manual`); for the mechanically-attestable
(`command`-claiming or test-naming) FRs, adopt a `verify.gate` runnable handle (binding to the test/command
the verify already names); mark the legitimately-manual ones with an explicit manual marker so they don't
read as false-mechanical; and wire the built liveness layer (REQ-22/23) to run over the requirements-
visualization corpus as a standing advisory self-gate that reports the adoption rate and routes a
mechanical-but-gateless FR to a human triage. Additive, advisory, reuse-not-build.

## Objectives

- **O-1:** The corpus's verifies read honestly — target: each verify is classified mechanical vs manual; the "96% dead" figure resolves into a real-gap count + an explicit-manual count, not a single misleading number.
- **O-2:** The mechanically-attestable FRs adopt a gate — target: the top-N mechanical FRs carry a `verify.gate` binding to the check their verify names; the corpus's `verify.gate` adoption moves off 0/180.
- **O-3:** The corpus can't silently regress — target: a standing advisory self-liveness gate over the corpus reports adoption + routes a mechanical-but-gateless FR to a human triage; it never blocks.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| integrity | A gate is forced onto a legitimately-manual verify (false-mechanical) | FR-1/FR-4: a gate is adopted ONLY where the verify claims mechanical attestation; manual verifies are marked, not gated | high |
| scope | A blanket 180-FR authoring campaign | NR-1: adopt on the mechanically-attestable subset + mark the rest; not every FR gets a gate | high |
| quality | The self-gate blocks the pipeline on the existing 96% backlog | FR-5/NR-2: advisory only — reports + routes to human triage, never blocks | high |
| dependency | Needs the built liveness layer + verify.gate field | NR-4: REQ-22 (`verify.gate` + verify-liveness) and REQ-23 are built |  medium |

## Functional requirements

- **FR-1 — The mechanical/manual honesty split.** Classify each corpus FR's verify via `verify_oracle.classify` into `command` (a runnable span — mechanically attestable), `assertion` (prose acceptance — legitimately manual), or `manual`, so a present-but-dead verify is separated into *should-have-a-gate* vs *legitimately-manual*. Name: Each verify is classified mechanically-attestable versus legitimately-manual via verify_oracle. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/verify_oracle.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does the split separate mechanically-attestable verifies from legitimately-manual ones?. Verify: over the corpus, each FR's verify is bucketed `command`/`assertion`/`manual`; the count of mechanically-attestable-but-gateless is reported distinctly from legitimately-manual. Serves: O-1
- **FR-2 — Adopt `verify.gate` on the mechanically-attestable FRs.** For FRs whose verify names a runnable check (a test id or a `startd8 navigator` command), add a `verify.gate` binding to that check — dogfooding REQ-22's remedy on our own corpus; target the high-value mechanical FRs first. Name: The mechanically-attestable FRs adopt a verify.gate binding to the runnable check their verify names. Touches: `docs/design/requirements-visualization/REQ-*.md`, tests. Lives: doc docs/design/requirements-visualization/REQ-01-sdk-node-home.md. Approve?: do the mechanically-attestable FRs carry a verify.gate binding to their named check?. Verify: the targeted mechanical FRs each carry a `verify.gate` that `parse_gate` resolves to the test/command their verify names; corpus `verify.gate` adoption is no longer 0. Serves: O-2
- **FR-3 — Mark legitimately-manual verifies explicitly.** An FR whose verify is legitimately human-checked (`assertion`/`manual`) carries an explicit manual marker so it does not masquerade as mechanical — the corpus's liveness reads as "gap vs honest-manual", not a single misleading dead-rate. Name: A legitimately-manual verify carries an explicit marker so it does not read as false-mechanical. Touches: `src/startd8/navigator/det_req.py`, `docs/design/requirements-visualization/REQ-*.md`, tests. Lives: code src/startd8/navigator/det_req.py. Approve?: does a legitimately-manual verify carry an explicit marker distinguishing it from a mechanical gap?. Verify: an FR marked manual is excluded from the mechanical-but-gateless gap count and reported as honest-manual; an unmarked mechanical-claiming FR is not. Serves: O-1
- **FR-4 — The standing self-liveness gate (dogfood, advisory).** Wire the built liveness layer (REQ-22/23) to run over the requirements-visualization corpus as a standing advisory self-gate that reports the `verify.gate` adoption rate and the mechanical-but-gateless count, integrable into the Spec Delivery Loop. Name: The built liveness layer runs over the corpus as a standing advisory self-gate reporting adoption and the mechanical gap. Touches: `src/startd8/navigator/govern.py`, `scripts/navigator_spec_delivery_loop.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does a standing advisory self-gate report adoption and the mechanical gap over the corpus?. Verify: running the self-gate over the corpus reports the adoption rate + the mechanical-but-gateless list; it is advisory (exit non-blocking); it can run from the Spec Delivery Loop. Serves: O-3
- **FR-5 — Route a mechanical-but-gateless FR to human triage.** A mechanically-attestable FR with no `verify.gate` routes to a human decision (adopt-a-gate or mark-manual) via a retrospective `Lesson` (REQ-20) — never a silent green and never a blocking failure. Name: A mechanically-attestable FR without a gate routes to a human triage decision via a retrospective lesson. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/sources_retrospective.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does a mechanical-but-gateless FR route to a human triage rather than block or pass silently?. Verify: a mechanically-attestable gateless FR produces a `proposed` Lesson offering adopt-gate-or-mark-manual; it does not block the build and does not pass as a silent green. Serves: O-3
- **FR-6 — Reuse, additive, byte-identical.** The split, the self-gate, and the marker reuse `verify_oracle` + the built liveness layer (no new engine); the shipped renders and the app-scaffold path are byte-identical; only the targeted REQ docs gain a `verify.gate`/manual marker. Name: The self-dogfood reuses the built liveness layer and leaves the shipped render byte-identical. Touches: `tests/unit/navigator/test_self_liveness.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_self_liveness.py. Approve?: is the self-dogfood a reuse that leaves the shipped render byte-identical?. Verify: the self-gate imports the built liveness layer (no new engine); `test_no_profile_is_byte_identical` passes unedited; only targeted REQ docs change (gate/marker additions). Serves: O-1, O-3

## Non-requirements

- **NR-1:** Does NOT force a gate on every FR — a gate is adopted only where the verify claims mechanical attestation; legitimately-manual verifies are marked, not gated (a false gate is the failure in reverse).
- **NR-2:** Does NOT block the build — the self-liveness gate is advisory; it reports + routes to human triage, it never fails the pipeline on the existing backlog.
- **NR-3:** Does NOT build a new checker — reuses `verify_oracle` + the built REQ-22/23 liveness layer pointed at our own corpus.
- **NR-4:** Build-ready — REQ-22 (`verify.gate` + verify-liveness) and REQ-23 (the layer) are built; this is their self-application.
- **NR-5:** Does NOT re-author verify *prose* — it adds a `verify.gate` binding or a manual marker beside the existing verify; the prose acceptance statement stays as the human-readable residue.
