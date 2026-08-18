# Standard — the det-doc-kit `$0` PROJECTOR pattern

**Date:** 2026-08-17 · **Type:** extracted standard (Hansei / `/reflective-retrospective`) · **Status:** **ADOPTED** — a second projector (det-handoff) was built against it with no new friction
**Proved by:** REQ-29 — `src/startd8/plan_codegen/` (the det-plan projector), shipped `35e75c89`, hardened `33606c12`.
**Hardened by:** a `/reflective-adoption` **cold-adopter dry-run** (2026-08-17) that tried to build the det-crp projector
from this doc alone and found the gaps §0/§Part-6 below close.
**Adopted by:** `src/startd8/handoff_codegen/` (the det-handoff projector, `5ba7eb48`) — the real second-projector build.
Because the dry-run had already folded its gaps back, the real build hit **no new shape→build-spec gaps**; it surfaced
only two *refinements* (the shared header extraction + the doc-type-specific gate signal), folded below. This is the
`/reflective-adoption` gate **passed**.
**Governs:** every future det-doc-kit **projector** — `det-handoff` (`$0` REQ+ledger→HANDOFF), `det-howto`, `det-ledger`.
**Does NOT govern:** `det-crp` — it is a **thin format+lint kit whose generator already exists** (the `new-cnvrg-rvw-prmpt` compiler); the review-log is human-*accreted*, not projected. See `SCHEMA_det-crp-0.1.md §9`. (Cold-adopter dry-run finding: not every det-doc-kit member is a projector.)
**Grounded in:** the working code + `PILOT_REPORT_REQ-29-det-plan-projector.md`, not aspiration.

> **One line:** a det-doc-kit projector is a `$0`, LLM-free, pure function of an upstream authored doc, shaped as a
> **5-part mirror of `backend_codegen`** + the **6th honesty part** (gate · maturity · DIDL · back-ref), whose
> "never-inferred" is only as real as the *authored fields it can trace to*, accepted by the **golden-diff method**,
> and whose SARIF is **imported, never vendored**.

## Why this is a standard now (Mottainai — don't re-derive it)

REQ-29 built the **first** projector in the det-doc-kit family. The **projector** members (`det-handoff`,
`det-howto`, `det-ledger`) will each need one; `det-crp` will **not** (its `$0` generator, the
`new-cnvrg-rvw-prmpt` compiler, already runs — the dry-run corrected this). Rather than re-derive the shape from
`backend_codegen` each time (and re-hit the same traps below), this codifies what the first build *actually proved*.

## §0. Preconditions — STEP 0 before any code (cold-adopter dry-run, GAP-A/B)

A cold adopter who skipped these hit a wall immediately. Do them **first**, in order:

1. **The target format grammar must already exist.** Part 3 validates against `SCHEMA_det-<doc>-0.1.md` §-conformance;
   the kit owns that grammar (I-2). If it doesn't exist yet, **author it first** (charter §9 sequencing) — you cannot
   project into a format that isn't specified. *(det-plan had `SCHEMA_det-plan-0.1` authored before REQ-29; det-crp does
   **not** yet — so det-crp is format-blocked until its SCHEMA lands.)*
2. **Name the upstream authored source(s), and confirm each is authored — not generated.** The projector is a pure
   function of its source. Before building, answer: *what exact doc(s) are the source, and are they human-authored?*
   - A source that is itself an LLM/compiler output (e.g. det-crp's review-log is produced by the
     `new-cnvrg-rvw-prmpt` compiler, embedded as an Appendix-A/B/C section — not a standalone authored file)
     **violates the premise** and means the doc-type is likely *not a projector at all* (det-crp became a thin
     format+lint kit citing the compiler — the dry-run's biggest correction).
   - **A source may be TWO authored inputs, not one** (det-handoff fold-back): a *primary doc* + a *state/ledger*
     (det-handoff = the `REQ` + the delivery `ledger`; det-plan was one `REQ`). Both must be authored/accreted for the
     projection to stay `$0`. *(det-plan's source was one `REQ-*.md`; det-handoff's is `REQ + SESSION_LEDGER`; det-crp's
     is compiler-generated → not a projector. Resolve which case you're in before writing `projector.py`.)*
3. **Locate a hand-authored golden instance** to run the acceptance golden-diff against (below), or confirm the cell is
   demand-clearing (no golden → accept on conformance alone).

## The 5-part shape (mirror `backend_codegen`, essentials-only)

Each clause cites the REQ-29 file that proved it. A new projector `det-<doc>` fills the same five slots:

| Part | REQ-29 instance | Rule |
|------|-----------------|------|
| **1. `projector.py`** | `plan_codegen/projector.py` — `project_plan(req_text, *, req_path, strategy)` | A **pure function** of the upstream doc: no network, no LLM, no `Date.now()`/`random`. Every output field derives from an authored input field. Returns a typed model (`models.py`), not a dict. |
| **2. `render.py`** | `plan_codegen/render.py` — `render_plan(plan)` | **Idempotent** render of the model → the doc text; carries a `GENERATED_MARKER`; **no timestamps** (byte-identity depends on it — `test_render_has_no_timestamp`). |
| **3. `conformance.py`** | `plan_codegen/conformance.py` — `validate_plan` + `findings_to_sarif` | Validates the output against the format §-conformance + liveness; emits findings as SARIF **by importing** `coverage_map/findings_sarif` (`conformance.py:14`) — **never vendor a copy** (charter §5). |
| **4. `provider.py`** | `plan_codegen/provider.py` — `DetPlanProjectorProvider` | A `DeterministicFileProvider`: `owns()` = marker present; `is_in_sync()` = re-project from source and compare bytes. Silent-degradation paths **log at DEBUG** (`get_logger(__name__)`) so a non-skip is diagnosable. |
| **5. CLI + entry-point** | `generate plan` in `cli_generate.py`; `det-plan-projector = …` in `pyproject.toml` | `startd8 generate <doc>` drives it; the provider registers under `startd8.contractors.deterministic_providers`. A **CliRunner test** must exercise the exit-code contract (write / stdout / skip / `--check` drift / SARIF). |

## Part 6 — the honesty behaviors (the charter invariants the shape must carry)

> **Cold-adopter dry-run finding (GAP-C/D/E/F):** the 5-part shape above captures the *mechanics* but the first
> draft of this standard **dropped three charter invariants that det-plan actually implemented** — a cold adopter
> following only the shape would ship a projector missing the gate and the maturity stamp and not know it. These are
> not optional; they are charter §6 invariants that manifest as projector *behavior*. Every projector carries them:

| Behavior | REQ-29 instance | Rule (charter ref) |
|----------|-----------------|--------------------|
| **6a. Solo-vs-gap gate** | `is_plan_owed()` → `NotPlanOwedError`; a solo REQ projects **nothing**, reported skipped, exit 0 | Fire **only** when a companion is *owed*; never invent ceremony for a solo-by-design source (charter §6.4). **The gate *signal* is doc-type-specific** (det-handoff adoption finding): det-plan reads a REQ **marker** (`plan deferred`); det-handoff reads **ledger state** (delivered + no open follow-on → not owed). Identify your signal per doc-type. |
| **6b. Anti-inflation maturity** | render stamps `maturity: 0.1`; `validate_*` rejects an inflated stamp | A *projected* artifact starts at the lowest rung and never claims unearned hardening (charter inv-3). |
| **6c. DIDL naming** | `naming.name_forms(...)` → the projected doc's `name`/`handle`/`ref` | Every projected artifact carries a semantic name + readable handle + canonical ref; no integer-only names (charter inv-5). |
| **6d. Source back-reference** | the render embeds `pairsWith: <source>`; the provider re-resolves the source from it | The rendered doc MUST embed a resolvable pointer to its source, or `provider.is_in_sync` can't re-project to compare. |

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
- **Feed the forward loop:** the real *second projector* is **det-handoff** (`$0` REQ+ledger→HANDOFF). Before building
  it, do §0: author `SCHEMA_det-handoff-0.1.md`, and name its single authored source (the REQ + the ledger state — audit
  which fields are authored vs generated per I-1). **`det-crp` is NOT that test** — the cold-adopter dry-run found its
  generator already exists; it became a thin format+lint kit instead (`SCHEMA_det-crp-0.1.md`, authored 2026-08-17,
  cites the compiler, no projector).
- **Convergence note:** the SDK-owns-projector / kit-owns-format split (I-2) independently matches
  `backend_codegen`'s provider pattern — cite, don't re-fork.

## Adoption ledger

| Adoption | Kind | Result | Friction folded back |
|----------|------|--------|----------------------|
| REQ-29 five-pilot (format, iter-1) | across req *instances* (same corpus) | format hardened | G-1/G-2/G-3 → `SCHEMA_det-plan-0.1 §2/§3` |
| Cold-adopter dry-run → det-crp (2026-08-17) | simulated, single-agent | standard hardened **+ premise corrected** | GAP-A/B → §0; GAP-C/D/E/F → Part 6; **det-crp is not a projector** → `SCHEMA_det-crp-0.1.md` (thin format+lint kit, generator cited) |
| `SCHEMA_det-handoff-0.1` authored (2026-08-17) | format for the second projector | format ready | dual-source note (§0.1) → standard §0.2 step 2 |
| **det-handoff projector built** (`5ba7eb48`) | the real second-*projector* adoption (`$0` REQ+ledger→HANDOFF) | **PASSED — standard transferred, 0 new shape-gaps** | 2 refinements: (a) shared `req_header` extracted (1st projector inlined it) → `plan_codegen` migrated too; (b) the solo-vs-gap *signal* is doc-type-specific (det-plan = REQ marker, det-handoff = ledger state) → §Part-6a note |

*ADOPTED — det-plan established the shape, a cold-adopter dry-run closed the shape→build-spec gap, and the det-handoff
projector (`5ba7eb48`) was then **built against this doc with zero new shape-gaps** — the `/reflective-adoption` gate
passed. Remaining honesty caveat: both adoptions were **single-agent** (I carried context the doc might still assume);
the strongest possible signal is an **independent** adopter building the third projector (det-howto / det-ledger) from
this doc cold. Until then: adopted-once, not yet independently replicated.*
