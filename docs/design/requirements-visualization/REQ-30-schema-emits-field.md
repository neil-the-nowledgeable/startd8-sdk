# Schema `Emits:` Field + `serialization_gaps` Fact-Lint (theme #3) — Requirements

**Project:** startd8-sdk (cross-repo: dev-os `det-req-kit` — the grammar host)   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`SYNTHESIS_crp-theme-metabolization-four-investigations.md`** (§2 the schema #3 fact/candidate row, §3 the ranked backlog) · **`REQ-32-draft-time-firing-wire.md`** (the seam these lints fire through — the hard dependency) · `REQ-25-liveness-layer-hypothesis-cells.md` (the fact-rung/judgment-rung discipline this obeys) · `REQ-22/23` (the fact-cell precedent this continues) · `SCHEMA_det-plan-0.1.md` (§5/§10 — the artifact-manifest rollup) · the open `Depends:` grammar tail (G-1 — the same batch)
**Inherits standards:** det-req-kit · NAMING_CONVENTION / DIDL · REQ-06 (govern) · REQ-07 FR-7 (the precision gate — never cry wolf) · Mottainai (own a format, cite a generator) · KAIZEN (don't discard lessons)
**Audience:** requirement author / reviewer / det-req-kit owner / det-plan projector
**Trust boundary:** local; advisory (candidate/gap), never blocking, never auto-applies; the fact-lint extends an existing exit-unchanged advisory tier; the field is an optional additive grammar slot
**Data classification:** internal

> **Readable handle:** `feature/det-req-emits-field-names-serialized-artifacts-79047ab7`
> **Semantic name:** *The det-req-kit grammar names a serialized artifact by adding an optional Emits field that records the artifact its schema and its schema version parallel to Touches and Lives joining the LIVES-STOP set and by firing a serialization-gaps fact-lint in the extractor that flags an emit-shaped requirement carrying no Emits field at all while parking the version and round-trip judgment candidates behind the precision gate all advisory reuse-only firing through the draft-time seam and rolling an iteration Emits up to a plan-level artifact manifest.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-30`

## 0. Why this exists — a serialized artifact should name its schema at draft time

The CRP review corpus's third-largest recurring theme — **schema/types/serialization**, 323 accepted rows
re-derived review after review — collapses to one shape: *an FR that emits a serialized artifact keeps failing
to name (a) its schema, (b) its `schema_version`, and (c) its round-trip proof.* Reviewers re-discover the same
gap every round. This REQ metabolizes it into **grammar** (the shift-left move): a new optional `Emits:` field
so the draft already declares the artifact's contract, plus a `serialization_gaps` **fact-lint** so an emit-shaped
FR that carries no `Emits:` surfaces at authoring time — before review runs.

**This REQ fires THROUGH `REQ-32`'s draft-time firing seam** (the single wire every metabolized theme queues at)
— the lint is one additive predicate in `det-req-kit/extract.py::collect_findings`, not a new engine. It is the
same class of grammar-field addition as the open **`Depends:` field (G-1)** and its sibling **`REQ-31`
(`Lifecycle:`)**; the three should land as ONE cross-repo det-req-kit grammar-field batch. It is a continuation
of the already-shipped REQ-22/23/25 fact-cell series, not a speculative new path.

## Design decisions

- **A field + a fact-lint, not an engine (reuse REQ-32's seam).** The `Emits:` field parallels `Touches:`/`Lives:`/
  `Serves:` and joins the `_LIVES_STOP` set so `Lives:` terminates at it; the lint is one predicate in
  `collect_findings` at the same exit-unchanged advisory tier as the shipped `user_outcome_verify_advisory`.
- **Fact ships, judgment parks (REQ-25 / REQ-07 FR-7).** The FACT-rung (an emit-shaped FR with NO `Emits:` at all)
  is a structural presence check — it cannot cry wolf, so it ships as a GAP-class advisory. The CANDIDATE tier
  (has `Emits:` but no `version=`; or no round-trip clause in `Verify:`) is precision-gated and parked-by-default,
  reusing REQ-25's `JudgmentRung`/`is_unparked`/`measure_precision` machinery verbatim — this is REUSE, not new.
- **Deliberately NOT metabolized (hypothesis cells, review-only).** "bare string should be a closed type" (S-D) and
  "fallback should be first-class" (S-E) stay review-only — they need implementation-semantics judgment the det-req
  can't see structurally; forcing them into a lint would cry wolf (the disciplined stop, REQ-25 NR-3).
- **det-plan inherits it, no new plan machinery.** An iteration whose FRs carry `Emits:` rolls those up into a
  plan-level artifact manifest (`SCHEMA_det-plan-0.1 §5/§10`) — a projection of existing field data, not a new
  plan mechanism.
- **The kit owns the format; the SDK cites the generator (Mottainai).** The `Emits:` field + fact-lint live in
  dev-os `det-req-kit` (`SCHEMA.md §5` + `extract.py`); landing them is the kit-owner's go (cross-repo).

## Overview

Add an optional FR field `Emits: <artifact-ref> schema=<schema-ref> version=<schemaVersionField|n/a>` parsed to
`fr.emits[]` (`{artifact, schema?, version?}`), parallel to `Touches:`/`Lives:`/`Serves:` and joining the
`_LIVES_STOP` set. Fire a `serialization_gaps` fact-lint in `extract.py::collect_findings`: the FACT-rung flags an
emit-shaped FR (prose tell: `.json`/`.jsonl`/`manifest`/`report`/`model_dump`/`serialize`/`persist`) that carries
NO `Emits:` field at all; the CANDIDATE tier (has `Emits:` but no `version=`, or no round-trip clause in `Verify:`)
is parked behind the REQ-07 precision gate. Both fire through REQ-32's seam, at the exit-unchanged advisory tier.
An iteration's `Emits:` rolls up to a det-plan artifact manifest. Additive, advisory, reuse-only, byte-identical.

## Objectives

- **O-1:** A serialized artifact declares its contract at draft time — target: an FR carrying `Emits: <artifact> schema=<ref> version=<field>` parses to `fr.emits[]`, parallel to `Touches:`, and `Lives:` terminates at a following `Emits:`.
- **O-2:** An un-declared emit is a loud fact, a weak declaration is a parked candidate — target: an emit-shaped FR with no `Emits:` surfaces the `serialization_gaps` FACT-rung (GAP-class advisory); a missing `version=`/round-trip stays a precision-gated candidate, never a GAP.
- **O-3:** Reuse-only, additive, honest, inherited by the plan — target: the lint is one predicate through REQ-32's seam reusing REQ-25's parking machinery; the judgment cells (bare-string, fallback) stay review-only; an iteration's `Emits:` rolls up to a det-plan artifact manifest with no new plan machinery; byte-identical.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | The candidate tier cries wolf (the weak-verify 2-of-2 false-positive class) | FR-3: only the FACT-rung fires by default; the version/round-trip candidate parks behind the REQ-07 precision gate and ships only as a dismissible candidate | high |
| scope | Building a new serialization engine instead of one additive predicate | NR-2/FR-5: reuse `collect_findings`, REQ-25's parking machinery, and REQ-32's seam — one predicate, no new engine | high |
| dependency | The draft-time firing seam is not yet wired (REQ-32) | FR-5: the lint fires THROUGH REQ-32's seam; REQ-32 is the named prerequisite, not re-invented here | high |
| integrity | The lint blocks a build or edits a draft | NR-1/NR-3: the finding is advisory (candidate/gap), exit code unchanged, never auto-applied | high |
| quality | The FACT-rung mis-classifies non-emitting prose as emit-shaped | FR-2: the emit tell is a closed lexical set (`.json`/`manifest`/`model_dump`/…); a false trigger is dismissible and the tier is advisory | medium |

## Functional requirements

- **FR-1 — The optional `Emits:` field.** The det-req grammar gains an optional FR field `Emits: <artifact-ref> schema=<schema-ref> version=<schemaVersionField|n/a>` parsed to `fr.emits[]` as `{artifact, schema?, version?}`, parallel to `Touches:`/`Lives:`/`Serves:`, and added to the `_LIVES_STOP` set so a `Lives:` locator terminates at a following `Emits:` regardless of field order. Name: The det-req grammar adds an optional Emits field parsed to a per-requirement artifact-schema-version list joining the lives-stop set. Touches: `dev-os/det-req-kit/SCHEMA.md`, `dev-os/det-req-kit/extract.py`, tests. Lives: code dev-os/det-req-kit/extract.py. Approve?: does an FR carrying Emits parse to fr.emits and does Lives stop at a following Emits?. Verify: an FR with `Emits: report.json schema=ReportModel version=schema_version` parses to `fr.emits[0] == {artifact: report.json, schema: ReportModel, version: schema_version}`; a `Lives:` locator preceding `Emits:` terminates at it; an FR with no `Emits:` yields an empty `fr.emits`. Serves: O-1
- **FR-2 — `serialization_gaps` FACT-rung (an emit-shaped FR with no `Emits:`).** The extractor fires a `serialization_gaps` fact-lint whose FACT-rung flags an emit-shaped FR — one whose prose carries a serialization tell (`.json`/`.jsonl`/`manifest`/`report`/`model_dump`/`serialize`/`persist`) — that carries NO `Emits:` field at all, as a GAP-class exit-unchanged advisory finding; an emit-shaped FR that declares `Emits:` yields none. Name: The extractor fires a serialization-gaps fact-rung flagging an emit-shaped requirement carrying no Emits field. Touches: `dev-os/det-req-kit/extract.py`, tests. Lives: code dev-os/det-req-kit/extract.py. Approve?: does an emit-shaped FR with no Emits field surface a serialization-gaps fact finding?. Verify: an FR whose prose names `model_dump`/`.json`/`manifest` with no `Emits:` yields a `serialization_gaps` finding; the same FR carrying an `Emits:` yields none; the process exit code is unchanged either way. Serves: O-2
- **FR-3 — Version + round-trip CANDIDATE parks behind the precision gate.** The `serialization_gaps` CANDIDATE tier — an FR that HAS `Emits:` but no `version=`, or that names an artifact with no round-trip clause in its `Verify:` — is declared but NOT executed by default; it runs only when it clears the REQ-07 FR-7 precision threshold on a labeled fixture set, reusing REQ-25's `JudgmentRung`/`is_unparked`/`measure_precision`, and even then ships only as a dismissible candidate, never a GAP. Name: The version and round-trip candidate parks behind the precision gate reusing the REQ-25 machinery and never ships as a gap. Touches: `dev-os/det-req-kit/extract.py`, tests. Lives: code dev-os/det-req-kit/extract.py. Approve?: does the version-round-trip candidate stay parked until it clears precision and ship only as a candidate?. Verify: an `Emits:` with no `version=` yields no default finding; enabling the parked candidate tier surfaces it as an evidence-citing candidate, never a GAP; the parking reuses REQ-25's `is_unparked`/`measure_precision` with no new machinery. Serves: O-3
- **FR-4 — det-plan inherits `Emits:` as an artifact manifest.** An iteration whose FRs carry `Emits:` rolls those up into a plan-level artifact manifest (`SCHEMA_det-plan-0.1 §5/§10`) — a projection of the FRs' existing `emits[]` data, adding no new det-plan machinery. Name: A det-plan iteration rolls its requirements Emits up to a plan-level artifact manifest with no new plan machinery. Touches: `docs/design/requirements-visualization/SCHEMA_det-plan-0.1.md`, `src/startd8/plan_codegen/projector.py`, tests. Lives: code src/startd8/plan_codegen/projector.py. Approve?: does an iteration whose FRs carry Emits project a plan-level artifact manifest?. Verify: projecting a det-req whose FRs carry `Emits:` yields a det-plan whose iteration lists an artifact manifest deriving from the FRs' `emits[]`; a req with no `Emits:` projects an empty manifest; no new plan field is introduced. Serves: O-3
- **FR-5 — Fires through REQ-32's seam, reuse-only, additive, byte-identical.** The lint is a single additive predicate that fires THROUGH `REQ-32`'s draft-time firing seam in `collect_findings` (reusing the census/catalog/advisory tier, no new engine); the judgment cells (bare-string→typed, fallback-first-class) stay review-only; and the extractor's existing findings + exit contract and the navigator's byte-identical renders are unchanged. Name: The serialization lint is one additive predicate firing through the REQ-32 seam reuse-only leaving existing contracts byte-identical. Touches: `dev-os/det-req-kit/tests/test_serialization_gaps.py`, `dev-os/det-req-kit/extract.py`. Lives: test dev-os/det-req-kit/tests/test_serialization_gaps.py. Approve?: is the lint one predicate through the REQ-32 seam reuse-only and byte-identical?. Verify: the lint fires via REQ-32's `collect_findings` seam with no new engine; the bare-string and fallback cells execute nothing; the extractor's pre-existing findings and exit codes are unchanged and `test_no_profile_is_byte_identical` passes unedited. Serves: O-2, O-3

## Non-requirements

- **NR-1:** Does NOT auto-apply a fix or auto-edit a draft — a `serialization_gaps` finding is advisory; a human resolves it (propose-don't-dispose).
- **NR-2:** Does NOT build a new serialization/schema engine — the field is an additive grammar slot and the lint is one predicate reusing `collect_findings`, REQ-25's parking machinery, and REQ-32's seam.
- **NR-3:** Does NOT block a build or change the extractor's exit code — the fact-lint rides the existing exit-unchanged advisory tier.
- **NR-4:** Does NOT metabolize the hypothesis cells — "bare string should be a closed type" (S-D) and "fallback should be first-class" (S-E) stay review-only; they need implementation-semantics judgment a det-req can't see structurally.
- **NR-5:** Does NOT un-park the version/round-trip candidate — that is gated on a labeled-fixture precision pass (REQ-07 FR-7), tracked per theme, out of scope here.
- **NR-6:** Does NOT own the draft-time firing seam — that is `REQ-32`; this REQ authors the theme predicate that fires through it. The `Emits:` field + fact-lint host live in dev-os `det-req-kit`; landing them is the kit-owner's call (cross-repo), batched with the open `Depends:` field and `REQ-31`.
