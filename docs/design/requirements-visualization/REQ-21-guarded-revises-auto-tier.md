# Guarded `revises` Auto-Tier (byte-identity-gated, fail-safe, audited) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`REQ-20` (the `revises` edge this narrows the gate on — amends its NR-1)** · `RESEARCH_retrospective-bookend-as-ir-feedback-edge.md` · `REQ-17` (`approve` — the human gate this preserves for the consequential loop) · `REQ-18/19` (the trust-regime pattern this mirrors)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern) · `feedback_zero_risk_autonomous` (grounding-is-what-makes-it-safe) · the byte-identity guard (`test_no_profile_is_byte_identical` family)
**Audience:** operator / SDK contributors
**Trust boundary:** local repo; **auto-applies ONLY a byte-identity-proven, reversible revise; every product-changing revise stays human-gated**
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-auto-applies-a-revises-edge-257b39ea`
> **Semantic name:** *SDK navigator auto-applies a revises edge without human judgment only when it is proven byte-identical on the generated product, reversible, and drawn from a high-confidence lesson, enforcing the proof through the byte-identity guard itself, failing safe to a human proposal on any uncertainty, and auditing every auto-applied revise, so the consequential product-changing loop stays human-gated.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-21`

## 0. Why this exists — auto the provably-safe, gate the ambiguous (un-erodably)

REQ-20 made the `revises` edge absolutely human-gated (propose-don't-dispose). That is the right *default*,
but not every revise needs judgment: a revise that **provably does not change the generated product** (a
description clarification, an additive empty-default field, a mirror-test-proven rename) has **no downside by
construction**. This REQ adds a narrow **auto-tier** for exactly that class — the retrospective-bookend
instance of the system's universal principle (`deterministic` = trust-by-construction / `llm` =
trust-by-verification; zero-risk-autonomous; HTH XS-auto) — so the human's judgment is spent only where it
changes the product.

**The gate is a mechanical guard, not a judgment.** The eligibility bar is **byte-identity of the generated
product** — the objective, already-trusted guard — NOT "trivial complexity" (which targets edit-size, is a
human discretion, and *erodes*: "just this once" is how a gate rots). Anchoring to byte-identity makes the
"is it safe?" question un-creepable, bounds both the edit's downside *and* the wrong-inference risk (a
byte-identical revise is harmless even if the lesson was wrong), and keeps every consequential (product-
changing) revise human-gated. The proof is **enforced, not declared** — the revise is applied *through* the
guard, so a mis-classification is caught by the guard, not shipped; and any uncertainty **fails safe to a
human proposal**.

## Design decisions

- **Byte-identity is the gate.** Auto-eligible ⟺ the SDK's byte-identity guard proves the generated product
  unchanged. Product-changing revises are, by definition, the consequential ones — they stay human-gated.
- **Enforce, don't declare.** Apply through the guard; the guard catches a mis-classification (fail-closed).
- **Fail-safe to human.** ALL eligibility properties must be affirmatively proven; any unknown → human.
- **Autonomy with a trail.** Every auto-applied revise is audited + reversible; never silent.
- **Start narrow.** The safest class only; widening is a separate, evidenced decision (NR-3).

## Overview

Add a revise-tier classifier that marks a `revises` edge `auto` **iff** ALL of: byte-identity-provable on the
generated product, reversible (git-tracked, no spend/outward-ship), and drawn from an above-confidence-floor
Lesson — else `human` (REQ-20 propose). The auto path applies the revise **through** the byte-identity guard
(fail-closed) and writes an audit record; any uncertain property defaults to `human`. Additive over REQ-20:
the default stays human; only the proven-safe class auto-applies; the consequential loop is untouched.

## Objectives

- **O-1:** A provably-no-downside revise auto-applies without human judgment — target: a byte-identity-proven, reversible, above-floor revise auto-applies, enforced through the guard.
- **O-2:** The gate is un-erodable and fail-safe — target: eligibility is the objective byte-identity guard (not "trivial"), and any uncertain property defaults to `human`.
- **O-3:** Autonomy with a trail; consequential loop stays gated — target: every auto-apply is audited + reversible, and any product-changing revise stays human-gated.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| security/integrity | Gate erosion — "trivial" creeps until the human gate is meaningless | O-2/NR-2: gate on the OBJECTIVE byte-identity guard, not a triviality judgment — no discretion to creep; NR-3 forbids widening here | high |
| security/integrity | A mis-classified revise auto-applies a product change | FR-2: the revise is applied THROUGH the byte-identity guard (fail-closed) — a product change is caught by the guard and downgraded to human | high |
| integrity | A low-confidence / wrong-inference lesson auto-applies | FR-4: an above-confidence-floor Lesson is required; and byte-identity bounds the damage of a wrong-but-identical revise | high |
| integrity | Silent autonomous change | FR-6: every auto-apply is audited (lesson · target · guard result · revert ref) and reversible | high |
| scope | Auto-tier widened past the safest class, or edit-size used as the gate | NR-2/NR-3: byte-identity + reversibility + confidence only; widening is a separate evidenced decision | medium |
| dependency | Needs REQ-20's `revises` edge + Lesson | NR-6: spec-ready; build-blocked until REQ-20 lands | high |

## Functional requirements

- **FR-1 — The auto-tier eligibility classifier (the conjunction).** A `revises` edge is classified `auto` only when ALL hold — byte-identity-provable on the generated product, reversible (git-tracked, no spend/outward-ship side effect), and drawn from an above-confidence-floor Lesson — otherwise `human`; the classifier is the sole decider of the tier. Name: A classifier marks a revises edge auto only when it is byte-identity-provable reversible and above the lesson confidence floor. Touches: `src/startd8/navigator/revise_tier.py`, `tests/unit/navigator/test_revise_tier.py`. Lives: code src/startd8/navigator/revise_tier.py. Approve?: does auto require ALL of byte-identity-provable reversible and above-floor?. Verify: a revise meeting all three is classified `auto`; a revise failing any single one is classified `human`. Serves: O-1
- **FR-2 — Byte-identity is enforced, not declared (fail-closed).** The auto path applies the revise THROUGH the SDK byte-identity guard on the generated product; if the guard does not prove the product unchanged, the revise is NOT auto-applied and is downgraded to `human` — a mis-classification is caught by the guard, never shipped. Name: The auto path applies through the byte-identity guard and downgrades to human when the product is not proven unchanged. Touches: `src/startd8/navigator/revise_tier.py`, `tests/unit/navigator/test_revise_tier.py`. Lives: code src/startd8/navigator/revise_tier.py. Approve?: is a revise that changes the product caught by the guard and downgraded rather than auto-applied?. Verify: an `auto`-classified revise whose application changes the generated product is rejected by the byte-identity guard and downgraded to `human`; only a proven-byte-identical revise auto-applies. Serves: O-1, O-2
- **FR-3 — Reversibility + no irreversible side effect.** An auto-applied revise must touch only git-tracked artifacts and carry no irreversible side effect — no LLM spend, no outward publish, no external ship triggered; a revise that would trigger any is not auto-eligible. Name: An auto-applied revise touches only git-tracked artifacts with no spend outward publish or external ship. Touches: `src/startd8/navigator/revise_tier.py`, `tests/unit/navigator/test_revise_tier.py`. Lives: code src/startd8/navigator/revise_tier.py. Approve?: is a revise with any irreversible side effect excluded from auto?. Verify: a revise touching only git-tracked artifacts with no spend/ship is auto-eligible; a revise that would trigger a regeneration-with-spend or an outward publish is classified `human`. Serves: O-1, O-3
- **FR-4 — Grounding-confidence floor.** A revise auto-applies only if its Lesson clears a grounding-confidence floor; a below-floor Lesson's revise is `human` regardless of the other properties — a weakly-grounded belief never auto-modifies. Name: A revise auto-applies only when its lesson clears a grounding confidence floor else it is human. Touches: `src/startd8/navigator/revise_tier.py`, `tests/unit/navigator/test_revise_tier.py`. Lives: code src/startd8/navigator/revise_tier.py. Approve?: does a below-floor lesson force human even when byte-identical and reversible?. Verify: a revise from a Lesson below the confidence floor is classified `human` even when byte-identity-provable and reversible; only above-floor Lessons are auto-eligible. Serves: O-2
- **FR-5 — Fail-safe to human on any uncertainty.** If any eligibility property is unknown or unresolved, the revise defaults to `human` (REQ-20 propose) — auto is opt-in-by-proof, human-gated-by-default. Name: Any unresolved eligibility property defaults the revise to a human proposal. Touches: `src/startd8/navigator/revise_tier.py`, `tests/unit/navigator/test_revise_tier.py`. Lives: code src/startd8/navigator/revise_tier.py. Approve?: does any unresolved property default to human rather than auto?. Verify: a revise with any eligibility property unresolved or uncertain is classified `human`; `auto` requires all properties affirmatively proven. Serves: O-2
- **FR-6 — Audit trail (autonomy with a trail).** Every auto-applied revise writes an auditable record — the Lesson, the target node, the byte-identity guard result, a timestamp, and a revert reference — so a human can review-after and revert; auto-apply is never silent. Name: Every auto-applied revise writes an auditable reversible record naming the lesson target guard-result and revert reference. Touches: `src/startd8/navigator/revise_tier.py`, `src/startd8/navigator/govern.py`, tests. Lives: code src/startd8/navigator/revise_tier.py. Approve?: is every auto-applied revise audited and reversible?. Verify: an auto-applied revise writes a record naming the Lesson, target node, byte-identity guard result, and a revert reference; the record is queryable and the change is git-revertible. Serves: O-3
- **FR-7 — Amends REQ-20 NR-1; additive; consequential loop untouched.** This REQ narrows REQ-20's absolute "never autonomously modifies" to "never autonomously modifies EXCEPT a byte-identity-proven, reversible, above-floor, audited revise"; the default remains human, only the proven-safe class auto-applies, and every product-changing revise is unaffected. Name: The auto-tier amends REQ-20 NR-1 additively leaving the default human and the consequential loop human-gated. Touches: `docs/design/requirements-visualization/REQ-20-lesson-node-and-revises-feedback-edge.md`, `tests/unit/navigator/test_revise_tier.py`. Lives: test tests/unit/navigator/test_revise_tier.py. Approve?: is the amendment additive with the default staying human and product-changing revises gated?. Verify: with no auto-eligible revise, behaviour equals REQ-20 (all revises propose); a product-changing revise is never auto-applied; REQ-20 NR-1 carries the recorded amendment pointer. Serves: O-2, O-3

## Non-requirements

- **NR-1:** Does NOT auto-apply any revise that changes the generated product — byte-identity is the hard gate; consequential (product-changing) revises stay human-gated. The reliability architecture is intact where it matters.
- **NR-2:** Does NOT gate on edit-size / "trivial complexity" — the gate is the objective byte-identity guard + reversibility + confidence, not a human judgment of triviality (which would erode).
- **NR-3:** Does NOT widen the auto-tier beyond the safest byte-identity-provable class in this increment — any widening is a separate, evidenced decision.
- **NR-4:** Does NOT remove the human gate from the consequential loop — the auto-tier is toil-reduction on the hygiene tail; product-changing revises are unaffected.
- **NR-5:** Does NOT auto-apply silently — every auto-apply is audited + reversible (FR-6).
- **NR-6:** Build-blocked (not spec-blocked) on REQ-20 (the `revises` edge + Lesson) landing on `main`. Spec-ready now.
