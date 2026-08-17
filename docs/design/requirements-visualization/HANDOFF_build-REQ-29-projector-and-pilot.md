# Handoff: build the det-plan projector (REQ-29) and pilot it on five REQs

**Date:** 2026-08-17 · **From:** emeritus/direction session · **Base:** `main @ 7d95132f`
**For:** a build session · **Spec:** `REQ-29-det-plan-projector.md` (8 FRs) · **Format:** `SCHEMA_det-plan-0.1.md` · **Governs:** `CHARTER_det-doc-kit-family.md`
**Prerequisite status:** ✅ build-ready — `det_req.parse_fr_lines`, `contractors/queue.py`, `navigator/realization.py`, `coverage_map/findings_sarif.py` all present; the format (`SCHEMA_det-plan-0.1`) is authored; the plan schema target is `det-req-kit §9`.

## What you're building

The `$0` REQ→PLAN projector — the "generate plan" analog of "generate backend." `startd8 generate plan
--requirements <req>` reads a det-req and deterministically projects a `det-plan/0.1` document. It is a **pure
function of the requirement** (no LLM), a registered deterministic provider (mirror `backend_codegen`'s
`PydanticSQLModelProvider`). Then you **pilot it golden-first** on five REQs and fold the friction back into the
grammar.

## Two load-bearing rules (read before you start)

1. **`$0` / never-inferred.** Every field derives from the req: iterations ← FR grouping · `targetFiles` ← the
   FRs' Touches refs · `dependsOn` ← the req's *authored* dependency topology (acyclic via `queue.py`, **never
   invent an edge**) · `gate` ← the FRs' Verify clauses · `costClass` ← the realization regime. No LLM call.
2. **Build the kit essentials-only (charter §5 — the audit-hardened checklist).** If you create a dev-os
   `det-plan-kit/` dir: `SCHEMA.md` · `plan.schema.json` · `extract.py` (validate + plan-liveness gate that
   **imports** `findings_sarif`, does **NOT** vendor a copy) · `templates/` · `examples/` · `tests/`. **NO
   `new.py`, NO finding→plan-stub, NO process/`_HANSEI` docs in the dir** — det-plan is a *derived* doc; its
   projector IS its generator.

## The pilot matrix — run the projector on exactly these five

| # | Pilot REQ | Cell | Golden / expected | What it proves |
|---|-----------|------|-------------------|----------------|
| 1 | **REQ-08** (9 FRs) | **golden-parity** ⭐ | diff vs **`PLAN-nl-programming-pipeline-provenance.md`** | the quality bar (moderate size) + the primary friction source |
| 2 | **REQ-01** (19 FRs) | **golden-parity / stress** ⭐ | diff vs **`PLAN-01-sdk-node-home.md`** | quality bar at scale — batching + dependency topology |
| 3 | **REQ-03** | **negative-gate** | projects **NOTHING** (solo/NONE-kind) | the solo-vs-gap gate (FR-3) |
| 4 | **REQ-16** (4 FRs) | **demand-clearing** | a **conformant** `det-plan/0.1` | small companionless, low blast radius |
| 5 | **REQ-17** (4 FRs) | **demand-clearing** | a **conformant** `det-plan/0.1` | second demand case |

*(Do NOT pilot cross-repo REQs (REQ-seat) this iteration — correct-absence; iter-1 stays SDK-internal.)*

## The golden-diff method (the point of the whole pilot)

For **REQ-08 and REQ-01**: project the plan, then **diff the `$0` projection against the hand-authored PLAN**.
The projection will NOT match the human plan exactly — **the delta is the deliverable.** For each thing the
human PLAN has that the projection missed (e.g. a "Reference audit (phantoms)" section, a smarter FR-batching,
a per-iteration note), decide: *is this something the projector should derive?* If yes → it is **friction that
folds back into `det-plan/0.1`** (revise the grammar/projector); if it's genuine human judgment (a strategic
ordering choice) → leave it as the human's to add (charter: the ordering strategy is the human-gated residue).
Record every delta and its disposition. **This is the `/reflective-adoption` half — the human plans are the
ground truth that reveals what the projector is missing.**

## Build order (the 8 FRs)

1. **FR-1** — `plan_codegen/projector.py`: parse the req (`det_req.parse_fr_lines`) → project the `det-plan/0.1`
   fields (iterations/targetFiles/gate/costClass) per `SCHEMA_det-plan-0.1 §2`.
2. **FR-2** — `$0`/never-inferred: pure function; `dependsOn` from authored deps only; `queue.py` for acyclic +
   cycle rejection.
3. **FR-3** — solo-vs-gap: fire ONLY on a `plan deferred`/`plan follows` REQ; a solo/NONE REQ (REQ-03) → nothing.
4. **FR-4** — stamp `maturity: 0.1` (anti-inflation; no unearned CRP evidence).
5. **FR-5** — validate output against `det-plan/0.1 §10` + emit conformance/plan-liveness findings as SARIF
   (**import** `coverage_map/findings_sarif`), count LIVE pairs only.
6. **FR-6** — `plan_codegen/provider.py` + `startd8 generate plan` in `cli.py`; register under
   `startd8.contractors.deterministic_providers` in `pyproject.toml`.
7. **FR-7** — run the five-pilot matrix above; record the golden deltas as `det-plan/0.1` friction.
8. **FR-8** — additive: existing `generate {frontend,backend,scaffold,views}` unchanged;
   `test_no_profile_is_byte_identical` unedited; every projected plan validates against §10.

## Hard exit criteria

- **`$0`:** no network/LLM call in the projector; a test asserts it.
- **Never-inferred:** every `dependsOn` edge traces to an authored req dependency; a cyclic req is rejected by
  `queue.py` with a named error.
- **Golden pilots run:** REQ-08 + REQ-01 project, diff against their PLANs, deltas recorded + dispositioned.
- **Negative gate:** REQ-03 projects nothing (asserted).
- **Demand:** REQ-16 + REQ-17 each produce a `det-plan/0.1` that passes §10 conformance.
- **Reuse-not-vendor:** the SARIF path **imports** `findings_sarif`; no vendored copy.
- **Additive / byte-identical:** the existing generators + renders are unchanged.

## Gotchas (this repo)

- **det-req single-line FR parser** — keys on `Name:`/`Touches:`/`Lives:`/`Verify:`/`Serves:`; don't be tripped
  by prose that mentions those tokens.
- **Concurrency** — `main` moves between turns; build in a worktree; cherry-pick + FF if it diverged; pin
  `PYTHONPATH=<wt>/src`; stage own files only.
- **DIDL** — any new spec/plan carries `name_forms`-consistent handle/ref; validate parse-count == named-FR count.
- **`| tail`/`| head` mask exit codes** — check `$?` directly on ruff/pytest.

## What to hand back

The projector + the five-pilot run report: the two **golden-diff deltas** (what the projection missed vs the
human PLAN, and each delta's disposition — folded-into-grammar or human-residue), the negative-gate confirmation,
the two demand conformance results, and any `det-plan/0.1` grammar revisions the fold-back produced. That report
is the `/reflective-adoption` output — the pilot's friction, hardened back into the format.

## Pointers
- Spec: `REQ-29-det-plan-projector.md` · Format: `SCHEMA_det-plan-0.1.md` · Charter: `CHARTER_det-doc-kit-family.md` (§5 checklist)
- Golden PLANs: `PLAN-nl-programming-pipeline-provenance.md`, `PLAN-01-sdk-node-home.md`
- Reuse: `navigator/det_req.py` · `contractors/queue.py` · `navigator/realization.py` · `coverage_map/findings_sarif.py`
- Sibling to mirror: `backend_codegen/provider.py` (`PydanticSQLModelProvider`, the deterministic-provider pattern)
- Roadmap: `NEXT_STEPS_det-doc-kit-family-effort.md`
