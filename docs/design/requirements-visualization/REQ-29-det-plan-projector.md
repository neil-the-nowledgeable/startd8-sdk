# The $0 REQ→PLAN Projector (det-plan-kit's generator) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`SCHEMA_det-plan-0.1.md` (the format this projects)** · `CHARTER_det-doc-kit-family.md` (the abstraction) · `det-req-kit/SCHEMA.md §9` (the plan schema) · `REQ-18/19` (the realization regime → costClass)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern) · the charter's 7 invariants
**Audience:** operator / SDK contributors / the corpus's own authors (the pilot consumer)
**Trust boundary:** local, read-only over a det-req; no network; **no LLM ($0)**; the projector is a pure function of the requirement
**Data classification:** internal
**Method:** authored via `/reflective-instantiation` (downward — realize the abstraction's empty cell) informed by `/reflective-adoption` (the pilot fold-back, FR-7).

> **Readable handle:** `feature/sdk-navigator-realizes-the-det-doc-kit-family-s-5ed48db9`
> **Semantic name:** *SDK navigator realizes the det-doc-kit family's plan-projector cell by deterministically projecting a det-req's FRs Touches authored dependencies and Verify clauses into a det-plan 0.1 document at zero LLM cost, never inferring a dependency the requirement did not declare, firing only on a plan-owed requirement, starting the projected plan at maturity 0.1, and emitting its conformance and plan-liveness findings as SARIF, piloted on the corpus's own companionless requirements.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-29`

## 0. Why this exists — the realized cell (reflective-instantiation)

**Product space** (`$0 doc-projector = DOC-TYPE × {FORMAT-kit, PROJECTOR}`): every doc between the two human
bookends is a `$0` projection of an upstream structured doc. **The cell this realizes:** `(plan, PROJECTOR)` —
the `$0` REQ→PLAN generator, the "generate plan" analog of "generate backend." **Adjudicated natural-next:** the
abstraction predicts it (`SCHEMA_det-plan-0.1` *cites but does not define* the projector; `det-req-kit §9` holds
the target `plan{}`), the demand is grounded (26 companionless requirements-visualization REQs), and the sibling
to mirror exists (`backend_codegen`'s deterministic provider). **The correct-absence that bounds it:**
`(req, PROJECTOR)` stays empty *by design* — a requirement is a SOURCE (the front human bookend); a `$0` projector
there would be autonomous intent-generation, which the charter forbids. **The projector is `$0` by construction:**
all its inputs (FRs, Touches, authored acyclic deps, Verify, realization regime) already live in the det-req, so
it never LLM-infers anything (`det-req-kit §9`'s "never inferred", satisfied structurally).

## Design decisions

- **The kit owns the format; the projector is SDK-side** (charter §2). `SCHEMA_det-plan-0.1` owns `det-plan/0.1`;
  this projector is a deterministic provider registered under `startd8.contractors.deterministic_providers` and
  driven by `startd8 generate plan` — exactly as `backend_codegen`'s `PydanticSQLModelProvider` is.
- **Reuse, don't build:** `det_req.parse_fr_lines` (the FRs), `queue.py` (acyclic ordering + cycle detection),
  `realization.py` (the regime → `costClass`), `coverage_map/findings_sarif.py` (the SARIF emit).
- **Honor the family invariants:** solo-vs-gap · anti-inflation (projected plan = `0.1`) · plan-liveness · SARIF.

## Overview

`startd8 generate plan --requirements <req>` reads a det-req and projects a `det-plan/0.1` document: group its FRs
into iterations, derive `targetFiles` from `Touches`, `dependsOn` from the authored dependency topology (acyclic
via `queue.py`, never inferred), `gate` from the FRs' Verify clauses, and `costClass` from the realization regime;
fire ONLY on a plan-owed REQ (not a solo-by-design one); stamp the projected plan `maturity: 0.1`; and emit its
conformance + plan-liveness findings as SARIF. `$0`, additive, byte-identical to the shipped surfaces. Piloted on
the corpus's own 26 companionless REQs, with friction folded back into `det-plan/0.1` (FR-7).

## Objectives

- **O-1:** A det-req projects into a conformant det-plan/0.1 at `$0` — target: `generate plan --requirements <req>` emits a `det-plan/0.1` whose iterations/deps/gates derive from the req's FRs/Touches/topology/Verify, with no LLM call.
- **O-2:** Never-inferred + honest — target: the projector invents no dependency the req did not declare (acyclic), fires only on a plan-owed REQ, and stamps `maturity: 0.1`.
- **O-3:** Wired to the loop + piloted — target: the projector emits SARIF findings and is proven on the 26 companionless REQs, folding friction back into the grammar.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| integrity | The projector INVENTS a dependency or an LLM-infers order (violating "never inferred") | FR-2: pure function of the req; `dependsOn` derives only from authored deps; `queue.py` acyclic; no LLM call | high |
| integrity | It projects a ceremony plan for a solo-by-design REQ | FR-3: fires ONLY on a plan-owed REQ (the `plan deferred` marker); a `NONE`/solo REQ yields nothing | high |
| quality | A projected plan claims maturity it hasn't earned | FR-4: stamped `0.1`; anti-inflation | high |
| quality | A weak req projects a weak plan | FR-7 pilot: the cold-adopter test surfaces req-quality friction → folds back into `det-plan/0.1` (and rewards better reqs) | medium |
| dependency | Needs the format + the reuse modules | NR-4: `SCHEMA_det-plan-0.1` authored; `det_req`/`queue`/`realization`/`findings_sarif` all present |  medium |

## Functional requirements

- **FR-1 — Project a det-req into a det-plan/0.1.** `generate plan --requirements <req>` reads the det-req (via `det_req.parse_fr_lines`) and emits a `det-plan/0.1` document whose iterations group its FRs, whose `targetFiles` derive from the FRs' Touches refs, whose `gate` per iteration derives from the FRs' Verify clauses, and whose `costClass` derives from the realization regime. Name: The generate-plan command projects a det-req into a conformant det-plan document deriving iterations targetFiles gates and costClass from the requirement. Touches: `src/startd8/plan_codegen/projector.py`, `src/startd8/cli.py`, tests. Lives: code src/startd8/plan_codegen/projector.py. Approve?: does generate-plan emit a det-plan/0.1 whose fields derive from the req?. Verify: `generate plan --requirements <fixture-req>` emits a `det-plan/0.1` whose iterations reference the req's FRs, whose targetFiles equal the FRs' Touches refs, and whose per-iteration gate equals the FRs' Verify clauses. Serves: O-1
- **FR-2 — $0 and never-inferred.** The projector is a pure function of the det-req — no LLM call — and derives `dependsOn` only from the req's authored dependency topology (acyclic via `queue.py` cycle detection); it never invents a dependency the requirement did not declare. Name: The projector is a pure LLM-free function that derives dependencies only from the requirement's authored acyclic topology. Touches: `src/startd8/plan_codegen/projector.py`, `src/startd8/contractors/queue.py`, tests. Lives: code src/startd8/plan_codegen/projector.py. Approve?: is the projector LLM-free and never-inferring beyond the req's authored deps?. Verify: the projector makes no network/LLM call; `dependsOn` edges each trace to an authored req dependency; a req with a dependency cycle is rejected by `queue.py` with a named error. Serves: O-2
- **FR-3 — Solo-vs-gap gate.** The projector fires ONLY on a plan-owed REQ (one carrying the `plan deferred`/`plan follows` marker); a `NONE`/solo-by-design REQ produces no plan — do not invent ceremony (charter §6.4; reflective-pairs G-5). Name: The projector fires only on a plan-owed requirement and produces nothing for a solo-by-design one. Touches: `src/startd8/plan_codegen/projector.py`, tests. Lives: code src/startd8/plan_codegen/projector.py. Approve?: does the projector skip a solo-by-design REQ and fire only on a plan-owed one?. Verify: a REQ with a `plan deferred` marker projects a plan; a solo-by-design REQ (no such marker) projects nothing and reports skipped. Serves: O-2
- **FR-4 — Anti-inflation maturity.** A projected plan self-declares `maturity: 0.1` and carries no post-CRP evidence it has not earned (the anti-inflation ladder). Name: A projected plan is stamped maturity 0.1 and claims no unearned hardening evidence. Touches: `src/startd8/plan_codegen/projector.py`, tests. Lives: code src/startd8/plan_codegen/projector.py. Approve?: is a freshly projected plan stamped 0.1 with no unearned evidence?. Verify: a projected plan's header reads `maturity: 0.1`; it carries no `§0.1`/`§0.2`/CRP evidence markers. Serves: O-2
- **FR-5 — Plan-liveness + SARIF emit.** The projector validates the output against `det-plan/0.1` (LIVE `pairsWith`, acyclic deps, no FR-less iteration, no invented dep) and emits its conformance + plan-liveness findings as SARIF via `coverage_map/findings_sarif.py` (charter invariant 6), counting LIVE pairs only. Name: The projector validates the plan and emits its conformance and plan-liveness findings as SARIF counting live pairs only. Touches: `src/startd8/plan_codegen/projector.py`, `src/startd8/coverage_map/findings_sarif.py`, tests. Lives: code src/startd8/plan_codegen/projector.py. Approve?: does the projector validate the plan and emit SARIF findings?. Verify: a projected plan with a phantom `pairsWith` or a cyclic dep yields a SARIF finding; a clean projection yields none; the finding routes through `findings_sarif`. Serves: O-3
- **FR-6 — CLI + deterministic-provider registration.** `startd8 generate plan --requirements <req> [--out]` drives the projector, registered under the `startd8.contractors.deterministic_providers` entry-point group like `backend_codegen`; the kit (`SCHEMA_det-plan-0.1`) owns the format, this provider is the cited generator. Name: A generate-plan CLI subcommand registers the projector as a deterministic provider mirroring backend_codegen. Touches: `src/startd8/cli.py`, `src/startd8/plan_codegen/provider.py`, `pyproject.toml`, tests. Lives: code src/startd8/plan_codegen/provider.py. Approve?: is the projector a registered deterministic provider driven by generate-plan?. Verify: `startd8 generate plan --requirements <req>` runs; the provider is discoverable under `startd8.contractors.deterministic_providers`; `--help` lists `generate plan`. Serves: O-1
- **FR-7 — Pilot on the corpus's own companionless REQs (reflective-adoption fold-back).** Project plans for the 26 companionless requirements-visualization REQs as the cold-adopter test; any friction (a req whose Touches/deps/Verify do not project cleanly) is folded back into `det-plan/0.1` and recorded — the `/reflective-adoption` half of the method. Name: The projector is piloted on the corpus's 26 companionless REQs with projection friction folded back into the grammar. Touches: `tests/unit/plan_codegen/test_projector_pilot.py`, `docs/design/requirements-visualization/SCHEMA_det-plan-0.1.md`. Lives: test tests/unit/plan_codegen/test_projector_pilot.py. Approve?: is the projector piloted on the real companionless REQs with friction folded back?. Verify: the projector produces a conformant `det-plan/0.1` for each of the plan-owed companionless REQs, or records the specific projection friction and the `det-plan/0.1` clause it revises. Serves: O-3
- **FR-8 — Additive, byte-identical.** The projector is additive — a new `generate plan` subcommand + a new provider; the existing `generate {frontend,backend,scaffold,views}` and the shipped renders are byte-identical, and every projected plan conforms to `SCHEMA_det-plan-0.1` §10. Name: The projector is additive leaving the existing generators and renders byte-identical with every plan schema-conformant. Touches: `tests/unit/plan_codegen/test_projector.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/plan_codegen/test_projector.py. Approve?: is the projector additive byte-identical and its output schema-conformant?. Verify: the existing generate subcommands are unchanged; `test_no_profile_is_byte_identical` passes unedited; every projected plan validates against `det-plan/0.1` §10 conformance. Serves: O-3

## Non-requirements

- **NR-1:** Does NOT author requirement content or infer intent — a requirement is a SOURCE (the correct-absence cell); the projector consumes a det-req, it never generates one.
- **NR-2:** Does NOT invent dependencies or ordering — `dependsOn` derives only from the req's authored deps; `queue.py` guarantees acyclic; no LLM heuristic ordering.
- **NR-3:** Does NOT project a plan for a solo-by-design REQ (FR-3) — no ceremony plans.
- **NR-4:** Build-ready — `SCHEMA_det-plan-0.1` (the format) is authored; `det_req`/`queue`/`realization`/`findings_sarif` all present; the plan schema target is `det-req-kit §9`.
- **NR-5:** The kit (in dev-os) owns the `det-plan/0.1` format; this REQ builds the SDK-side projector only — the dev-os `det-plan-kit/` dir adoption is the cross-repo follow-up (charter §8).
