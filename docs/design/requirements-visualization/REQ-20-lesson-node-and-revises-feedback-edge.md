# Lesson Node + Human-Gated `revises` Feedback Edge (retrospective bookend, increment 1) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`RESEARCH_retrospective-bookend-as-ir-feedback-edge.md` (the design + OQ-R1..6)** · `REQ-19` (the determinism-regression that is this increment's input) · `REQ-16` (the edge object `revises` reuses) · `REQ-17` (`approve` — the human gate)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern) · REQ-08 (the Stage projection pattern — `category`+`attributes`, no fork)
**Audience:** operator / SDK contributors
**Trust boundary:** local repo, read-only; no network; no LLM; **never autonomously modifies an upstream node**
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-models-a-construction-outcome-as-a3f7fd48`
> **Semantic name:** *SDK navigator models a construction outcome as a grounded Lesson node that derives from the outcome and carries a human-gated revises feedback edge proposing a revision to the offending upstream contract node, closing the retrospective PDCA loop at the IR level without ever autonomously modifying the contract.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-20`

## 0. Why this exists — the smallest proof the learning loop closes

The RESEARCH note argues the NLPS's RETROSPECTIVE bookend should be **IR structure, not automation**: the
IR grounds, traces, and gates reflection, and **the human closes the loop.** This REQ is the smallest
end-to-end proof of that — it takes REQ-19's **determinism-regression** (a node planned deterministic but
realized `llm`) and turns it into a **grounded `Lesson` node** that `derives-from` the regression and carries
a **human-gated `revises` feedback edge** proposing a revision to the offending contract node. Forward
`derived-from` (REQ-16) + backward `revises` **closes PDCA at the IR level** — and the loop is *visible*
(Mieruka) and *gated* (propose-don't-dispose) exactly where the DATA MODEL bookend already gates the front.

It is deliberately narrow: **one** outcome type (the REQ-19 regression), modeled as **one** Lesson with
**one** revises edge, human-gated. The general Kaizen lesson-contract bridge is the follow-on (NR-2).

## Design decisions

- **Propose, don't dispose.** A Lesson **proposes** a revision; the human **disposes** (`approve`, REQ-17).
  The `revises` edge is inert until the Lesson's status is `accepted`. The IR **never** autonomously modifies
  an upstream node — the contract boundary stays human-gated (the reliability invariant, applied to the back).
- **Lesson = projection over Node (Kagami, no fork).** A Lesson is a `Node` with `category="lesson"` +
  typed `attributes` — exactly REQ-08's Stage pattern. **No new Node field / dataclass.**
- **`revises` = a relation value, not a new edge structure.** It reuses REQ-16's derivation edge object with
  `relation="revises"` (backward), so no structural change — a feedback edge is a derivation edge pointing
  upstream with a revise relation.

## Overview

Project a `Lesson` as a `Node` (`category="lesson"` + attributes); ground it with a REQ-16 `derived-from`
edge to its outcome (the REQ-19 regression) as its `lives`; give it a `revises` edge (`relation="revises"`,
backward) to the offending contract node; carry a `proposed|accepted|rejected` status so the revise stays
inert until human-accepted; provide `build_lesson_from_regression` as the end-to-end proof; and render the
Lesson + its two backward edges through the existing renderers. Additive, byte-identical, no new Node field,
no autonomous revision.

## Objectives

- **O-1:** REQ-19's determinism regression becomes a grounded Lesson with a `revises` edge to the offending contract — target: `build_lesson_from_regression` yields a `proposed` Lesson that `derives-from` the regression and `revises` the contract node named in it.
- **O-2:** Propose-don't-dispose — target: the `revises` edge is inert until `accepted`; no code path applies it without an accepted status; a rejected Lesson is retained with its rationale.
- **O-3:** Additive + visible — target: no new Node field, byte-identical render, and the Lesson + its backward edges render through the existing tree/graph renderers (Mieruka).

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| security/integrity | The IR autonomously modifies a contract from a lesson (re-automating the human-gated step) | FR-4/NR-1: the `revises` edge is a PROPOSAL, inert until `accepted` via human `approve`; no apply-without-accept code path exists | high |
| quality | An ungrounded Lesson (cruft) proposes a revision | FR-2: a Lesson without a `derived-from` grounding + `lives` is invalid/flagged — a belief is cruft until grounded (invariant 4) | high |
| scope | Building the general Kaizen lesson-contract bridge or auto loop-termination | NR-2/NR-4: one outcome type (REQ-19 regression), one Lesson; the human gate is the terminator | medium |
| quality | `revises` treated as a forward/containment edge and mis-traversed | FR-3: `relation="revises"` is backward and distinct from `derived-from`/`children`; traversal + render distinguish it | medium |
| dependency | Needs REQ-19's regression finding + REQ-16's edge | NR-5: spec-ready; build-blocked until REQ-19 + REQ-16 are on `main` (REQ-16 landed; REQ-19 pending) | high |

## Functional requirements

- **FR-1 — Lesson as a Node projection (Kagami, no fork).** A Lesson is a `Node` with `category="lesson"` and typed `attributes` (the interpretation), adding no field to `Node` — the REQ-08 Stage pattern. Name: A Lesson is projected as a Node using category lesson plus attributes without changing the Node model. Touches: `src/startd8/navigator/sources_retrospective.py`, `tests/unit/navigator/test_retrospective.py`. Lives: code src/startd8/navigator/sources_retrospective.py. Approve?: is a Lesson a projection over Node with zero Node field changes?. Verify: a built Lesson has `category=="lesson"` and `node_field_names()` is unchanged. Serves: O-3
- **FR-2 — A Lesson is grounded or it is invalid.** A Lesson carries a REQ-16 `derived-from` edge to its outcome and `lives` evidence pointing at that outcome; a Lesson with neither is invalid and flagged by `govern` — a belief is cruft until grounded. Name: A Lesson must derive from and cite its grounding outcome or it is flagged as an ungrounded belief. Touches: `src/startd8/navigator/sources_retrospective.py`, `src/startd8/navigator/govern.py`, tests. Lives: code src/startd8/navigator/sources_retrospective.py. Approve?: is an ungrounded Lesson rejected or flagged?. Verify: a Lesson built from a regression finding has a `derived-from` edge to it and `lives` citing it; a Lesson with no grounding yields a named `govern` finding. Serves: O-1
- **FR-3 — The `revises` feedback edge (backward, a relation value).** A Lesson carries a `revises` edge — REQ-16's edge object with `relation="revises"` pointing at the upstream node it proposes to modify — backward and distinct from forward `derived-from` and containment `children`, with no new edge structure. Name: A Lesson carries a backward revises edge as a relation value on the existing derivation edge distinct from derived-from and children. Touches: `src/startd8/navigator/models.py`, `src/startd8/navigator/sources_retrospective.py`, tests. Lives: code src/startd8/navigator/sources_retrospective.py. Approve?: is revises a backward relation value distinct from derived-from without a new edge structure?. Verify: a Lesson's revises edge has `relation=="revises"` and a `from_key` naming the upstream contract node, and traversal distinguishes it from `derived-from`. Serves: O-1
- **FR-4 — Propose, don't dispose (the human gate).** A Lesson carries a status `proposed|accepted|rejected` defaulting to `proposed`; its `revises` edge is inert until `accepted` (crossing into the contract requires the human `approve` gate, REQ-17); a `rejected` Lesson is retained with its rationale, not deleted. Name: A Lesson defaults to proposed and its revises edge stays inert until human-accepted with rejected lessons retained. Touches: `src/startd8/navigator/sources_retrospective.py`, `tests/unit/navigator/test_retrospective.py`. Lives: code src/startd8/navigator/sources_retrospective.py. Approve?: does a revises edge stay inert until an accepted status, with rejected lessons retained?. Verify: a new Lesson defaults to `proposed`; no code path applies its revise while `proposed`; a `rejected` Lesson is retained with a `rationale` attribute. Serves: O-2
- **FR-5 — End-to-end proof: regression to Lesson.** `build_lesson_from_regression` takes a REQ-19 determinism-regression finding and produces a `proposed` Lesson that `derives-from` the regression and `revises` the offending contract node named in it — the smallest proof the loop closes at the IR level. Name: Building a Lesson from a determinism regression yields a proposed grounded Lesson that revises the offending contract node. Touches: `src/startd8/navigator/sources_retrospective.py`, `tests/unit/navigator/test_retrospective.py`. Lives: code src/startd8/navigator/sources_retrospective.py. Approve?: does a regression finding produce a proposed Lesson revising the offending contract?. Verify: feeding a determinism-regression finding to `build_lesson_from_regression` yields a `proposed` Lesson with a `derived-from` edge to the regression and a `revises` edge to the contract node named in the finding. Serves: O-1
- **FR-6 — Render the loop (Mieruka).** The Lesson and its two backward edges (`derived-from` outcome, `revises` contract) render through the existing tree/graph renderers with the feedback edge visibly distinguished — no new HTML shell. Name: The Lesson and its backward derived-from and revises edges render through the existing renderers with the feedback edge distinguished. Touches: `src/startd8/navigator/render_graph.py`, `src/startd8/navigator/cli_navigator.py`, tests. Lives: code src/startd8/navigator/render_graph.py. Approve?: do a Lesson's backward edges render, distinguishing the feedback edge, with no new shell?. Verify: a graph render of a Lesson shows its `derived-from` and `revises` edges with `revises` visibly distinguished from `derived-from`; no new HTML shell is introduced. Serves: O-3
- **FR-7 — Additive, byte-identical, no autonomous revision.** All additive: no new Node field (Lesson = `category`+`attributes`; `revises` = a relation value), existing domain renders byte-identical, and no code path modifies an upstream node from a `revises` edge without an `accepted` status. Name: The Lesson and revises edge are additive byte-identical and never apply a revision without an accepted status. Touches: `tests/unit/navigator/test_retrospective.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_retrospective.py. Approve?: is the increment additive byte-identical and incapable of autonomous revision?. Verify: `node_field_names()` is unchanged; `test_no_profile_is_byte_identical` passes unedited; a negative test proves no path applies a `revises` change while the Lesson is `proposed` or `rejected`. Serves: O-2, O-3

## Non-requirements

- **NR-1:** Does NOT autonomously modify an upstream node — the `revises` edge is a PROPOSAL; applying it requires a human `accepted` status (the DATA MODEL bookend gate). The IR holds the proposal; the human closes the loop. **(Amended by REQ-21:** a narrow, byte-identity-proven, reversible, above-confidence-floor, audited auto-tier may apply a revise *without* human accept — the **default remains human**, and every **product-changing** revise stays gated. The exception is a mechanical guard, not a triviality judgment.**)**
- **NR-2:** Does NOT build the general Kaizen lesson-contract bridge (OQ-R4) — this increment models ONE outcome type (the REQ-19 determinism regression); lifting `kaizen-suggestions` / other outcomes is the follow-on.
- **NR-3:** Does NOT add a Node field or a new dataclass — Lesson = `category`+`attributes` (Kagami); `revises` = a relation value on REQ-16's edge (no new edge structure).
- **NR-4:** Does NOT automate loop termination (OQ-R5) — the human accept/reject gate is the terminator; no auto-fire of revisions.
- **NR-5:** Build-blocked (not spec-blocked) on REQ-19 (the regression input) and REQ-16 (the edge — landed). Spec-ready now; the narrow first increment of the RETROSPECTIVE bookend.
