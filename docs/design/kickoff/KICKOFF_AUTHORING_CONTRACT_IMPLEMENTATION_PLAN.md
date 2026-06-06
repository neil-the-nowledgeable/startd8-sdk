# Kickoff Authoring Contract — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-05
**Subject:** [`KICKOFF_AUTHORING_CONTRACT.md`](KICKOFF_AUTHORING_CONTRACT.md) v0.2 (grammar v0.2)
**Tracker:** [`KICKOFF_AUTHORING_CONTRACT_NEXT_STEPS.md`](KICKOFF_AUTHORING_CONTRACT_NEXT_STEPS.md)
(lanes A–F; this plan sequences the remaining lanes into buildable phases)
**Status of lane A (the build):** **DONE** — `src/startd8/manifest_extraction/` shipped to main
(`f4457d43`/`6791ecca`): grammars §2.0–§2.7 executable, FR-WPI-4 round-trip, EMIT wiring,
`wireframe --from-run`, piloted on the real strtd8 docs (6/6 parser-clean, DIFF clean,
`ready`×3, 16/80).

---

## 0. What "implementing the contract" still means

The grammars are code. What remains is making the contract **operational end-to-end**:
authors can check conformance before extraction (K1), the implementation honors every §2.0
conformance rule — two are currently missing (K2), the teaching surfaces can't drift (K3),
the generator gaps the flags point at get closed so flagged values become extractable (K4),
and the contract evolves deliberately (K5/K6).

## Phase K1 — `startd8 kickoff check` (lint mode; contract OQ-2, tracker C6)

The author's pre-flight: run extraction as a dry-run, render the conformance report, write
nothing. **Thin CLI over the shipped module** — no new extraction logic.

- `src/startd8/cli_kickoff.py`: `kickoff_app` Typer group (the start of the kickoff CLI
  family alongside `ROLE_KIT_CLI_REQUIREMENTS.md`'s kits); register beside `generate`/`assist`
  in `cli.py`.
- `startd8 kickoff check <doc.md>... [--project ROOT] [--json]`:
  `extract_manifests(docs, live_schema_text=<project contract if present>)` → render
  per-manifest conformance: `extracted / defaulted / not_extracted(reason)` counts + the
  friction-loop worklist (§3: every `not_extracted` row IS the co-work TODO). Advisory exit 0;
  `--strict` exits 1 when any `not_extracted` is a *conformance* failure (vs generator-gap) —
  the CI posture authors asked for, distinct from the wireframe's no-gating rule because this
  is an authoring tool, not the acceptance gate.
- Output reuses `report_to_markdown`; `--json` emits `report_to_json` to stdout.
- **Acceptance:** running it on `strtd8/docs/kickoff/REQUIREMENTS_v0.5-draft.md` lists exactly
  the pilot's known non-conformances (the `links … to nothing` sentence, the AiCall slash-row)
  as the worklist, and nothing else as conformance-class.

## Phase K2 — Conformance completeness (close the §2.0 gaps the build audit found)

Three contract rules the shipped extractor does NOT yet honor — all small, all in
`manifest_extraction/`:

1. **Collision pre-flight (R1-G4-i).** Two pages/views deriving the same slug/file-stem must
   flag BOTH `not_extracted(collision)` — today the emitted manifest dies in its own FR-WPI-4
   round-trip as a `RoundTripError`, i.e. an *author* error miscategorized as an *extraction
   bug*. Add the pre-flight in `extractors.py` (pages: derived slugs + page-name stems; views:
   derived idents/routes) before emission. Test: two `Page` rows kebabing identically ⇒ both
   flagged, manifest still emitted without them (partial-conformance posture), no exception.
2. **Reserved-name guard (R1-G4-iv).** Entity/field names colliding with the generators'
   reserved set (the `metadata` crash class, Python keywords) flag at extraction, citing the
   backend reserved-name guard. Source the reserved set from `backend_codegen` (import the
   guard's constant; if private, promote per the no-private-imports rule). Test: a `Metadata`
   entity / `metadata` field ⇒ flagged with the citation.
3. **Env-keys agreement check (§2.7).** *(Tracker correction: this does NOT "work today" —
   the shipped extractor flags `env keys` generator-gap without parsing entries.)* Parse the
   cell's `KEY (qualifier…) · KEY (default X)` micro-grammar; when the package includes
   `inputs/build-preferences.yaml` (now committed under `templates/inputs/`), compare declared
   defaults and flag disagreement (`not_extracted(two-surfaces-disagree)` + both sources in
   the record). Test: fixture with `COST_BUDGET_USD (default 10.00)` vs a build-preferences
   value of `5.00` ⇒ disagreement row.

## Phase K3 — Teaching-surface alignment (tracker B4–B5; pure drift protection, do anytime)

Mark every vocabulary list in `templates/REQUIREMENTS_TEMPLATE.md`,
`templates/HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md`, `templates/REQUIREMENTS_AND_PLAN_FORMAT.md`
as a **non-normative snapshot citing the contract §-ref** (§5 single-owner rule), and surface
the v0.2 additions authors must know (one-field-per-row, `links to many`, board's `Group by:`,
the view `Route:` override). ~30 minutes of edits; the recorded dominant failure mode
(vocabulary drift, 8 instances) says do it before the next authoring session.

## Phase K4 — Generator-gap closures (tracker D7–D9; each flips a flag to extractable)

Independent, schedule by appetite; each ends by deleting a `not_extracted(generator-gap)`
case from the extractor and its test:

| Gap | Where | Flipped flag |
|---|---|---|
| Completeness `nudge`/`predicate`/`confirmed`/`href` | `backend_codegen/derived.py` manifest schema (+ `render_completeness`) | §2.4 nudge two-row rule → one extracted row |
| `AppManifest` `port` / `env keys` / `sqlite mode` | `scaffold_codegen/manifest.py` + renderers (`.env.example`, Dockerfile EXPOSE, WAL pragmas) | §2.7 subset rule → full table extractable |
| detail-compose/workspace `Shows:` prose (spike F3) | `view_codegen` relations/panels enrichment (track against REQ-VIEW) + a constrained Relations/Panels line format in contract v0.3 | view shells → full relations |

## Phase K5 — Contract v0.3 (the pilot's grammar feedback; needs an owner decision each)

- **AI-assist `Route` column** — pilot evidence: routes are NOT name-derivable (their
  `/enrich-metrics` ≠ `quantify_metrics`); today extraction emits `defaulted` and promotion
  diffs. An optional `Route` column in §2.5 makes authored routes extractable. Recommend: add.
- **`Formats:` home** — export-package formats are required-to-conform but have no manifest
  field; either a `view_codegen` field (K4) or drop the requirement to optional.
- **Exclude-category vocabulary** — "connection records"/"join tables" shipped; decide whether
  more category words enter the closed set or literal entity names stay the rule.
- Each lands as a CRP-triaged contract edit + a `GRAMMAR_VERSION` bump with the §6-OQ-1
  back-compat rule (old docs extract identically).

## Phase K6 — Versioning + corpus (tracker E10; event-driven)

`GRAMMAR_VERSION = "authoring-contract-v0.2"` is pinned in `manifest_extraction/models.py` and
stamped into every report. When the controlled corpus ships: the version becomes a corpus-
snapshot reference, synonyms feed surface-form canonicalization (flag-never-merge), and clean
round-trips emit determinism samples (FR-WPI-11). **No machinery built before the corpus.**

## Sequencing

| Phase | Effort | Blocked by | Why this order |
|---|---|---|---|
| K1 lint CLI | small | nothing | authors need the pre-flight NOW (strtd8 co-work pass pending) |
| K2 conformance gaps | small ×3 | nothing | the extractor currently violates its own contract on collisions |
| K3 templates | trivial | nothing | drift protection before the next authoring session |
| K4 generator gaps | small–medium each | nothing (independent) | each removes a standing flag |
| K5 contract v0.3 | CRP cycle | pilot feedback settled | owner decisions, not code |
| K6 corpus | trivial | corpus ships | §4b alignment is advisory until then |

**Recommended first slice: K1 + K2 together** — one PR, ~a day: the lint command plus the
conformance fixes it would expose, acceptance-tested against the real strtd8 doc.

## Out of scope (owned elsewhere)

Lane F (strtd8 retrofit + their entity-table fidelity) — team-paced, their repo. P7 Prisma
writer (greenfield DRAFT mode) — wiring plan. FR-X1 five-class pre-flight — kickoff master
spec; `kickoff check` is its Group-F slice and the natural seed, but the other four classes
need their own pass.
