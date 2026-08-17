# Standard — the det-doc-kit `$0` PROJECTOR pattern

**Date:** 2026-08-17 · **Type:** extracted standard (Hansei / `/reflective-retrospective`) · **Status:** proved-once
**Proved by:** REQ-29 — `src/startd8/plan_codegen/` (the det-plan projector), shipped `35e75c89`, hardened `33606c12`.
**Governs:** every future det-doc-kit **projector** (the `det-crp`, `det-handoff`, `det-howto`, `det-ledger` generators).
**Grounded in:** the working code + `PILOT_REPORT_REQ-29-det-plan-projector.md`, not aspiration.

> **One line:** a det-doc-kit projector is a `$0`, LLM-free, pure function of an upstream authored doc, shaped as a
> **5-part mirror of `backend_codegen`**, whose "never-inferred" is only as real as the *authored fields it can trace
> to*, accepted by the **golden-diff method**, and whose SARIF is **imported, never vendored**.

## Why this is a standard now (Mottainai — don't re-derive it)

REQ-29 built the **first** projector in the det-doc-kit family. The next four members (`det-crp`, `det-handoff`,
`det-howto`, `det-ledger`) will each need a projector. Rather than re-derive the shape from `backend_codegen`
each time (and re-hit the same two traps below), this codifies what the first build *actually proved*.

## The 5-part shape (mirror `backend_codegen`, essentials-only)

Each clause cites the REQ-29 file that proved it. A new projector `det-<doc>` fills the same five slots:

| Part | REQ-29 instance | Rule |
|------|-----------------|------|
| **1. `projector.py`** | `plan_codegen/projector.py` — `project_plan(req_text, *, req_path, strategy)` | A **pure function** of the upstream doc: no network, no LLM, no `Date.now()`/`random`. Every output field derives from an authored input field. Returns a typed model (`models.py`), not a dict. |
| **2. `render.py`** | `plan_codegen/render.py` — `render_plan(plan)` | **Idempotent** render of the model → the doc text; carries a `GENERATED_MARKER`; **no timestamps** (byte-identity depends on it — `test_render_has_no_timestamp`). |
| **3. `conformance.py`** | `plan_codegen/conformance.py` — `validate_plan` + `findings_to_sarif` | Validates the output against the format §-conformance + liveness; emits findings as SARIF **by importing** `coverage_map/findings_sarif` (`conformance.py:14`) — **never vendor a copy** (charter §5). |
| **4. `provider.py`** | `plan_codegen/provider.py` — `DetPlanProjectorProvider` | A `DeterministicFileProvider`: `owns()` = marker present; `is_in_sync()` = re-project from source and compare bytes. Silent-degradation paths **log at DEBUG** (`get_logger(__name__)`) so a non-skip is diagnosable. |
| **5. CLI + entry-point** | `generate plan` in `cli_generate.py`; `det-plan-projector = …` in `pyproject.toml` | `startd8 generate <doc>` drives it; the provider registers under `startd8.contractors.deterministic_providers`. A **CliRunner test** must exercise the exit-code contract (write / stdout / skip / `--check` drift / SARIF). |

## The two load-bearing invariants the pilot proved

### I-1 — "never-inferred" is only as real as the authored fields you can trace to
`$0`/never-inferred is **not** a property you assert; it is a property of the **source grammar**. REQ-29's
`dependsOn` derives *only* from an authored `Depends:` FR field — and the pilot found **det-req has no parsed
`Depends:` field**, so `dependsOn` is honestly *empty* and the build-order DAG is 100% **human-residue** (the
charter's human-gated tail). **Rule for the next projector:** before claiming a field is `$0`-derivable, grep the
source grammar for the field it would trace to. If the field doesn't exist, the output is either honestly empty
(and the delta is human-residue) or the derivation is an *inference* you must not make. Never invent the edge.

### I-2 — SDK owns the projector; the kit owns the format
The format grammar (`SCHEMA_det-<doc>-0.1.md`) lives in the kit and is **cited, not restated** by the projector
(charter §2). The projector is SDK-side, registered like `backend_codegen`. Keep the split: a projector change
never edits the grammar except through the **fold-back** (below).

## The acceptance method — the golden-diff (reusable for every projector)

The pilot's core method, now standard: **project the `$0` output, then diff it against a hand-authored instance
of the same doc.** For each delta (something the human artifact has that the projection lacks), disposition it:

- **fold-into-grammar** — the projector *should* derive it → revise the format/projector (e.g. REQ-29 G-1/G-2/G-3).
- **human-residue** — genuine judgment the source doesn't encode (strategic ordering, planning discoveries, the
  CRP log) → leave it as the human's to add. This is the charter's human-gated tail; do **not** fold it.

The delta *is* the deliverable. A projector with no hand-authored artifact to diff against (a pure demand-clearing
cell) is accepted by **§-conformance + zero findings** instead (REQ-16/17).

## Dormant inventory (Phase 2.5) — the honest denominator

| Touch | Evidence | Status |
|-------|----------|--------|
| `project_plan` / `render_plan` / `validate_plan` / `findings_to_sarif` | `cli_generate.py:1038-1073` | wired |
| `DetPlanProjectorProvider` | `pyproject.toml:197` entry-point; discovered=True | wired (registry, not a Python import) |
| `DetPlanProjectorProvider.is_in_sync` **skip-path** | 0 end-to-end prime runs; only unit-tested | **unexercised** → CEP validation seed |
| all other public symbols (8) | grepped call sites | wired |

## Lessons (Phase 5)

- **L-1 (the surprise → a lesson):** *"$0 by construction" is a claim about the source grammar's fields, not the
  projector's cleverness.* Detection: grep the source grammar for every field the projector claims to trace to;
  a missing field means the output is honestly empty or you're about to infer. Recovery: fold the missing field
  into the source grammar (a cross-kit request), or mark the output human-residue. (REQ-29 G-1.)
- **L-2:** *A deterministic-file provider's silent-`False` is invisible unless it logs* — the generic skip-hook
  only logs on a raised exception, so a swallowed-return needs its own DEBUG line (HTH Phase-2 fix).

## Yokoten (Phase 6) — spread + feed forward

- **Spread:** this standard is the input to the next `/reflective-requirements` for `det-crp-kit` /
  `det-handoff-kit`. Each builds the same 5-part shape; each runs its own golden-diff; each audits I-1 against its
  own source grammar first.
- **Feed the forward loop:** the `det-crp` projector's source grammar is the CRP focus + Appendix-A/B/C review-log
  — audit *those* fields for I-1 before claiming `$0`.
- **Convergence note:** the SDK-owns-projector / kit-owns-format split (I-2) independently matches
  `backend_codegen`'s provider pattern — cite, don't re-fork.

*proved-once — one projector (det-plan) establishes the shape; it becomes a full standard when a second projector
(det-crp/det-handoff) adopts it without friction (the `/reflective-adoption` gate).*
