# Lifecycle `Lifecycle:` Field + `lifecycle_gaps` Fact-Lint (theme #6) — Requirements

**Project:** startd8-sdk (cross-repo: dev-os `det-req-kit` — the grammar host)   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`SYNTHESIS_crp-theme-metabolization-four-investigations.md`** (§2 the lifecycle #6 fact/candidate row, §3 the ranked backlog) · **`REQ-32-draft-time-firing-wire.md`** (the seam these lints fire through — the hard dependency) · `REQ-25-liveness-layer-hypothesis-cells.md` (the fact-rung/judgment-rung discipline this obeys) · `REQ-22/23` (the fact-cell precedent this continues) · `SCHEMA_det-plan-0.1.md` (§2/§10 — the resume/checkpoint gate rollup) · the shipped `src/startd8/contractors/checkpoint.py` + `.startd8/state/` 3-layer resume validation (the process grounding) · the open `Depends:` grammar tail (G-1 — the same batch)
**Inherits standards:** det-req-kit · NAMING_CONVENTION / DIDL · REQ-06 (govern) · REQ-07 FR-7 (the precision gate — never cry wolf) · Mottainai (own a format, cite a generator) · KAIZEN (don't discard lessons)
**Audience:** requirement author / reviewer / det-req-kit owner / det-plan projector
**Trust boundary:** local; advisory (candidate/gap), never blocking, never auto-applies; the fact-lint extends an existing exit-unchanged advisory tier; the field is an optional additive grammar slot
**Data classification:** internal

> **Readable handle:** `feature/det-req-lifecycle-field-names-durable-state-addfb69f`
> **Semantic name:** *The det-req-kit grammar names durable state and a resumable process by adding an optional Lifecycle field that records the states the resume path and the idempotency key parallel to Touches and Lives joining the LIVES-STOP set and by firing a lifecycle-gaps fact-lint in the extractor that flags a persist-or-resume-shaped requirement carrying no Lifecycle field at all while parking the idempotent and invalid-transition judgment candidates behind the precision gate all advisory reuse-only firing through the draft-time seam and carrying an iteration resume gate grounded in the shipped checkpoint and state resume machinery.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-31`

## 0. Why this exists — durable state should declare its lifecycle at draft time

The CRP review corpus's sixth recurring theme — **state/lifecycle/resume-retry**, 218 accepted rows re-derived
review after review — collapses to one shape: *an FR that owns durable state or a resumable process keeps failing
to declare its states, its resume path, and its idempotency.* Reviewers re-discover the same gap every round. This
REQ metabolizes it into **grammar**: a new optional `Lifecycle:` field so the draft already declares the state
machine and resume contract, plus a `lifecycle_gaps` **fact-lint** so a persist/resume-shaped FR that carries no
`Lifecycle:` surfaces at authoring time — before review runs.

**This REQ fires THROUGH `REQ-32`'s draft-time firing seam** (the single wire every metabolized theme queues at)
— the lint is one additive predicate in `det-req-kit/extract.py::collect_findings`, not a new engine. It is the
same class of grammar-field addition as the open **`Depends:` field (G-1)** and its sibling **`REQ-30`
(`Emits:`)**; the three should land as ONE cross-repo det-req-kit grammar-field batch. It continues the shipped
REQ-22/23/25 fact-cell series, not a speculative new path.

**det-plan is the stronger home for the PROCESS half.** An iteration whose FRs declare `resume=` carries a
resume/checkpoint gate — and that gate is **grounded, not invented**: the SDK already ships
`src/startd8/contractors/checkpoint.py` + resume caching to `.startd8/state/` with 3-layer resume validation
(schema version → source checksum → per-task file hash). The det-plan process rollup projects the FRs' declared
lifecycle onto that shipped machinery; it does not author a new resume engine. This clears the kit's
"grounded, not invented" bar.

## Design decisions

- **A field + a fact-lint, not an engine (reuse REQ-32's seam).** The `Lifecycle:` field parallels `Touches:`/
  `Lives:`/`Serves:` and joins the `_LIVES_STOP` set so `Lives:` terminates at it; the lint is one predicate in
  `collect_findings` at the same exit-unchanged advisory tier as the shipped `user_outcome_verify_advisory`.
- **Fact ships, judgment parks (REQ-25 / REQ-07 FR-7).** The FACT-rung (a persist/resume-shaped FR with NO
  `Lifecycle:` at all) is a structural presence check — it cannot cry wolf, so it ships as a GAP-class advisory.
  The CANDIDATE tier (has `Lifecycle:` but no `idempotent=` while prose mentions retry; or `states=` with no
  invalid-transition clause in `Verify:`) is precision-gated and parked-by-default, reusing REQ-25's
  `JudgmentRung`/`is_unparked`/`measure_precision` machinery verbatim — REUSE, not new.
- **`persist=atomic` is an OFFERED slot whose ABSENCE is not flagged (the disciplined stop, REQ-25 NR-3).** The
  field grammar offers a `persist=` slot, but atomicity/lost-update and rollback/GC/TTL (L-D, L-E) stay
  review-only — they need implementation-semantics judgment a det-req can't see structurally; flagging the
  absence of `persist=atomic` would cry wolf.
- **det-plan grounds the process half in shipped machinery.** The resume/checkpoint gate an iteration carries is a
  projection onto `checkpoint.py` + `.startd8/state/`'s 3-layer resume validation — grounded, not a new engine.
- **The kit owns the format; the SDK cites the generator (Mottainai).** The `Lifecycle:` field + fact-lint live in
  dev-os `det-req-kit` (`SCHEMA.md §5` + `extract.py`); the process rollup lives in det-plan `§2/§10`.

## Overview

Add an optional FR field `Lifecycle: states=<a|b|c> resume=<checkpoint-ref|none> idempotent=<yes|no|key:<field>>`
parsed to `fr.lifecycle[]` (`{states?, resume?, idempotent?, persist?}`), parallel to `Touches:`/`Lives:`/`Serves:`
and joining the `_LIVES_STOP` set. Fire a `lifecycle_gaps` fact-lint in `extract.py::collect_findings`: the
FACT-rung flags a persist/resume-shaped FR (tell: `persist`/`checkpoint`/`resume`/`retry`/`state machine`/`store`/
`ledger`/`--resume`) that carries NO `Lifecycle:` field at all; the CANDIDATE tier (has `Lifecycle:` but no
`idempotent=` while prose mentions retry; or `states=` with no invalid-transition clause in `Verify:`) parks behind
the REQ-07 precision gate. `persist=atomic` is offered but its ABSENCE is not flagged. Both fire through REQ-32's
seam. An iteration whose FRs declare `resume=` carries a resume/checkpoint gate grounded in the shipped
`checkpoint.py` + `.startd8/state/` 3-layer resume validation. Additive, advisory, reuse-only, byte-identical.

## Objectives

- **O-1:** A durable-state or resumable process declares its lifecycle at draft time — target: an FR carrying `Lifecycle: states=<…> resume=<…> idempotent=<…>` parses to `fr.lifecycle[]`, parallel to `Touches:`, and `Lives:` terminates at a following `Lifecycle:`.
- **O-2:** An un-declared lifecycle is a loud fact, a weak declaration is a parked candidate — target: a persist/resume-shaped FR with no `Lifecycle:` surfaces the `lifecycle_gaps` FACT-rung (GAP-class advisory); a missing `idempotent=` under retry or a missing invalid-transition `Verify:` stays a precision-gated candidate, never a GAP.
- **O-3:** Reuse-only, additive, honest, with the process half grounded in shipped machinery — target: the lint is one predicate through REQ-32's seam reusing REQ-25's parking machinery; atomicity/rollback stay review-only; an iteration's `resume=` carries a resume gate grounded in `checkpoint.py` + `.startd8/state/`; byte-identical.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | The candidate tier cries wolf (the weak-verify 2-of-2 false-positive class) | FR-3: only the FACT-rung fires by default; the idempotent/invalid-transition candidate parks behind the REQ-07 precision gate and ships only as a dismissible candidate | high |
| scope | Building a new lifecycle/resume engine instead of one additive predicate | NR-2/FR-5: reuse `collect_findings`, REQ-25's parking machinery, REQ-32's seam, and the SHIPPED `checkpoint.py` — one predicate, no new engine | high |
| dependency | The draft-time firing seam is not yet wired (REQ-32) | FR-5: the lint fires THROUGH REQ-32's seam; REQ-32 is the named prerequisite, not re-invented here | high |
| integrity | The lint blocks a build or edits a draft | NR-1/NR-3: the finding is advisory (candidate/gap), exit code unchanged, never auto-applied | high |
| quality | Flagging the absence of `persist=atomic` (an implementation-semantics judgment) cries wolf | NR-4: `persist=` is an OFFERED slot; its absence is deliberately NOT flagged — atomicity/rollback stay review-only (REQ-25 NR-3) | medium |

## Functional requirements

- **FR-1 — The optional `Lifecycle:` field.** The det-req grammar gains an optional FR field `Lifecycle: states=<a|b|c> resume=<checkpoint-ref|none> idempotent=<yes|no|key:<field>>` parsed to `fr.lifecycle[]` as `{states?, resume?, idempotent?, persist?}`, parallel to `Touches:`/`Lives:`/`Serves:`, and added to the `_LIVES_STOP` set so a `Lives:` locator terminates at a following `Lifecycle:` regardless of field order. Name: The det-req grammar adds an optional Lifecycle field parsed to a per-requirement states-resume-idempotent-persist record joining the lives-stop set. Touches: `dev-os/det-req-kit/SCHEMA.md`, `dev-os/det-req-kit/extract.py`, tests. Lives: code dev-os/det-req-kit/extract.py. Approve?: does an FR carrying Lifecycle parse to fr.lifecycle and does Lives stop at a following Lifecycle?. Verify: an FR with `Lifecycle: states=idle|running|done resume=checkpoint.py idempotent=key:task_id` parses to `fr.lifecycle[0]` carrying those states, resume ref, and idempotent key; a `Lives:` locator preceding `Lifecycle:` terminates at it; an FR with no `Lifecycle:` yields an empty `fr.lifecycle`. Serves: O-1
- **FR-2 — `lifecycle_gaps` FACT-rung (a persist/resume-shaped FR with no `Lifecycle:`).** The extractor fires a `lifecycle_gaps` fact-lint whose FACT-rung flags a persist/resume-shaped FR — one whose prose carries a lifecycle tell (`persist`/`checkpoint`/`resume`/`retry`/`state machine`/`store`/`ledger`/`--resume`) — that carries NO `Lifecycle:` field at all, as a GAP-class exit-unchanged advisory finding; a persist/resume-shaped FR that declares `Lifecycle:` yields none. Name: The extractor fires a lifecycle-gaps fact-rung flagging a persist-or-resume-shaped requirement carrying no Lifecycle field. Touches: `dev-os/det-req-kit/extract.py`, tests. Lives: code dev-os/det-req-kit/extract.py. Approve?: does a persist-or-resume-shaped FR with no Lifecycle field surface a lifecycle-gaps fact finding?. Verify: an FR whose prose names `checkpoint`/`resume`/`--resume` with no `Lifecycle:` yields a `lifecycle_gaps` finding; the same FR carrying a `Lifecycle:` yields none; the process exit code is unchanged either way. Serves: O-2
- **FR-3 — Idempotent + invalid-transition CANDIDATE parks behind the precision gate.** The `lifecycle_gaps` CANDIDATE tier — an FR that HAS `Lifecycle:` but no `idempotent=` while its prose mentions retry, or that declares `states=` with no invalid-transition clause in its `Verify:` — is declared but NOT executed by default; it runs only when it clears the REQ-07 FR-7 precision threshold on a labeled fixture set, reusing REQ-25's `JudgmentRung`/`is_unparked`/`measure_precision`, and even then ships only as a dismissible candidate, never a GAP. Name: The idempotent and invalid-transition candidate parks behind the precision gate reusing the REQ-25 machinery and never ships as a gap. Touches: `dev-os/det-req-kit/extract.py`, tests. Lives: code dev-os/det-req-kit/extract.py. Approve?: does the idempotent-invalid-transition candidate stay parked until it clears precision and ship only as a candidate?. Verify: a `Lifecycle:` with retry prose but no `idempotent=` yields no default finding; enabling the parked candidate tier surfaces it as an evidence-citing candidate, never a GAP; the parking reuses REQ-25's `is_unparked`/`measure_precision` with no new machinery. Serves: O-3
- **FR-4 — det-plan carries a resume gate grounded in shipped machinery.** An iteration whose FRs declare `resume=` carries a resume/checkpoint gate (`SCHEMA_det-plan-0.1 §2/§10`) that is a projection onto the SHIPPED `src/startd8/contractors/checkpoint.py` + `.startd8/state/` 3-layer resume validation (schema version → source checksum → per-task file hash) — grounded, not a new resume engine. Name: A det-plan iteration whose requirements declare resume carries a resume gate grounded in the shipped checkpoint and state machinery. Touches: `docs/design/requirements-visualization/SCHEMA_det-plan-0.1.md`, `src/startd8/plan_codegen/projector.py`, `src/startd8/contractors/checkpoint.py`, tests. Lives: code src/startd8/plan_codegen/projector.py. Approve?: does an iteration whose FRs declare resume project a resume gate grounded in checkpoint.py?. Verify: projecting a det-req whose FRs carry `resume=` yields a det-plan iteration carrying a resume/checkpoint gate referencing `checkpoint.py` + `.startd8/state/`; a req with no `resume=` projects no resume gate; no new resume engine is authored. Serves: O-3
- **FR-5 — Fires through REQ-32's seam, reuse-only, additive, byte-identical.** The lint is a single additive predicate that fires THROUGH `REQ-32`'s draft-time firing seam in `collect_findings` (reusing the census/catalog/advisory tier, no new engine); atomicity/lost-update (L-D) and rollback/GC/TTL (L-E) stay review-only with `persist=atomic`'s absence deliberately un-flagged; and the extractor's existing findings + exit contract and the navigator's byte-identical renders are unchanged. Name: The lifecycle lint is one additive predicate firing through the REQ-32 seam reuse-only leaving existing contracts byte-identical. Touches: `dev-os/det-req-kit/tests/test_lifecycle_gaps.py`, `dev-os/det-req-kit/extract.py`. Lives: test dev-os/det-req-kit/tests/test_lifecycle_gaps.py. Approve?: is the lint one predicate through the REQ-32 seam reuse-only and byte-identical?. Verify: the lint fires via REQ-32's `collect_findings` seam with no new engine; the atomicity and rollback cells execute nothing and `persist=atomic`'s absence yields no finding; the extractor's pre-existing findings and exit codes are unchanged and `test_no_profile_is_byte_identical` passes unedited. Serves: O-2, O-3

## Non-requirements

- **NR-1:** Does NOT auto-apply a fix or auto-edit a draft — a `lifecycle_gaps` finding is advisory; a human resolves it (propose-don't-dispose).
- **NR-2:** Does NOT build a new lifecycle/resume engine — the field is an additive grammar slot and the lint is one predicate reusing `collect_findings`, REQ-25's parking machinery, REQ-32's seam, and the shipped `checkpoint.py` + `.startd8/state/` resume validation.
- **NR-3:** Does NOT block a build or change the extractor's exit code — the fact-lint rides the existing exit-unchanged advisory tier.
- **NR-4:** Does NOT metabolize atomicity/lost-update (L-D) or rollback/GC/TTL (L-E) — `persist=atomic` is OFFERED as a slot but its ABSENCE is not flagged (the disciplined stop, REQ-25 NR-3); these need implementation-semantics judgment a det-req can't see structurally.
- **NR-5:** Does NOT un-park the idempotent/invalid-transition candidate — that is gated on a labeled-fixture precision pass (REQ-07 FR-7), tracked per theme, out of scope here.
- **NR-6:** Does NOT own the draft-time firing seam — that is `REQ-32`; this REQ authors the theme predicate that fires through it. The `Lifecycle:` field + fact-lint host live in dev-os `det-req-kit`; the process rollup lives in det-plan; landing them is the respective owner's call (cross-repo), batched with the open `Depends:` field and `REQ-30`.
