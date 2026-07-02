# Persona Format & Ingestion Requirements

**Version:** 0.3 (Post-CRP — convergent review R1/R2 applied)
**Date:** 2026-07-02
**Status:** Draft
**Extends:** `STAKEHOLDER_PANEL_REQUIREMENTS.md` v0.3 (FR-1/FR-2 roster, OQ-1 grammar decision)
**Companion plan:** `PERSONA_FORMAT_AND_INGESTION_PLAN.md` v1.1

> **v0.3 (CRP):** dual-document convergent review (R1+R2) applied — 12 requirements suggestions folded
> in. Highlights: the round-trip gate is **structural-only, not semantic** (FR-3/FR-5); `protocol_version`
> forward-compat is now defined (FR-2); a caller-visible **error taxonomy** was added (FR-9); soft
> findings **block at ingest** but only warn at load (FR-3); header provenance is stated **advisory,
> not load-bearing** (FR-7). Full dispositions in Appendix A/B.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2, after surveying the SDK's parse/extract infra.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| "Formalize the template" is substantial work | Template **plumbing is already complete** — the roster is in `_KICKOFF_FILES` (`writes.py:41`), download-derived, byte-identity-guarded (M0) | **FR-1 narrowed** to a *schema reference doc*; the real formalization is the strict parser (FR-2) |
| We might reuse `manifest_extraction` to parse the roster | Engine is **welded to the app-codegen/Prisma grammar** — not reusable; only its `Status/SourceRef/ExtractionRecord` dataclasses are liftable | **FR-8 firmed**; roster stays out of the grammar (reaffirms panel OQ-1); provenance dataclasses declined for v1 |
| Strict vs. permissive validation is a hard conflict | Clean split available: **strict on document structure** (unknown-key typo guard) + **coerce field elements** + soft-report content | **FR-2 firmed** (OQ-2 resolved) |
| A new adapter-registry mechanism is needed | The **entry-point idiom** (`providers/registry.py:131`) is the established rail | **FR-4 firmed** — mirror it, don't invent (OQ-3 resolved) |
| The pilot script can be reused directly | It hand-writes YAML and is benchmark-named | **FR-5 firmed**: emit through `Roster` (re-validated), generalize to a `role-rubric` **format family** |
| Ingestion may need auto-detect / per-field provenance | Explicit adapter + a generated **header** suffices; a **round-trip gate** is the quality bar | **FR-7 firmed** header-only (OQ-6); **NR-4** auto-detect out; OQ-7 → round-trip gate in |

**Resolved open questions:**
- **OQ-1 → Stays in `stakeholder_panel/roster.py`** (not moved to `kickoff_inputs/`) — copy the
  *contract*, keep the panel self-contained.
- **OQ-2 → Strict document structure, coerced field elements, soft content reporting.**
- **OQ-3 → `adapt(text: str) -> Roster`; group `startd8.stakeholder_panel.roster_adapters`.**
- **OQ-4 → `role-rubric` adapter lives in SDK core** (generic format family, not benchmark-specific).
- **OQ-5 → `startd8 panel import`** subcommand (panel CLI is the writer surface).
- **OQ-6 → Header-level provenance only**; `manifest_extraction` dataclasses left unlifted.
- **OQ-7 → Yes — ingestion round-trip-gates** (emit roster → reparse via FR-2 before accepting).

---

## 1. Problem Statement

The Stakeholder Panel (M0–M3) ships a persona **roster** format (`stakeholders.yaml`) — the
`PersonaBrief`/`Roster` contract in `stakeholder_panel/models.py`, projected as a template by
Concierge `instantiate-kickoff` and loaded by `stakeholder_panel/roster.py`. The Summer-2026 pilot
proved a second demand: an **external** persona format (`reviewer_roles.yaml`:
`key/label/lens/rubric/coverage/out_of_scope`) was converted into a roster by a **one-off argparse
script** living outside the SDK, untested, hand-writing YAML rather than round-tripping through
`Roster`.

Two gaps follow: (a) the native roster format is *packaged* but not *formalized* — it has no strict
canonical parser gate (unlike the sibling `kickoff_inputs` value YAMLs), so a typo'd roster is
silently coerced rather than loudly rejected; and (b) there is no in-SDK, reusable, testable path to
**ingest** an external persona format into a validated roster — every new source format would spawn
another one-off script.

This document specifies (1) formalizing the native roster template with a strict parser peer to
`kickoff_inputs`, and (2) a pluggable persona-format **ingestion adapter** capability. It also settles
the requester's "if useful" question: **which existing SDK parsing/extraction infra to reuse vs.
build fresh.**

| Component | Current State | Gap |
|-----------|--------------|-----|
| Native roster template | Packaged + projected + byte-identity-guarded (M0) | No strict parser gate; `Roster.from_dict` is permissive (coerces, ignores unknown top-level keys) — no typo guard |
| External format ingestion | One-off script in `benchmarking/` repo (`reviewer_roles_to_roster.py`) | Not in SDK, untested, bypasses `Roster` validation; each new format = another script |
| Format-adapter plumbing | None | No adapter contract, no registry — no way to register/discover persona-format adapters |
| Reuse of extraction infra | Ad hoc | Unclear which of `manifest_extraction` / `kickoff_inputs` / `concierge/derive` to lean on |

---

## 2. Requirements

### A. Formalize the native roster format

- **FR-1 — Canonical persona-format schema (doc, drift-guarded).** The `PersonaBrief`/`Roster` shape
  is the *single canonical* persona format. Template **plumbing already exists** (M0: packaged,
  projected, download-derived, byte-identity-guarded), so FR-1 is scoped to an **authoritative schema
  reference** (`ROSTER_SCHEMA.md`) any external tool can target. **(v0.3, R2-F2/R2-S3)** The doc's
  field set must be **generated from, or a build-checked test asserted against, the `PersonaBrief`/
  `Roster` model and the FR-2 allow-set** — never free-authored — so it cannot silently drift from the
  code (a hand-written doc that lies makes external tools emit rosters the FR-2 gate then rejects).
  Cross-linked from the template header and `reviewer_roles.yaml`.
- **FR-2 — Strict roster parser gate.** Add a strict canonical parser (`parse_roster`) for
  `stakeholders.yaml`, mirroring the `kickoff_inputs.parse_conventions` *contract* (kept in
  `stakeholder_panel/roster.py`, not moved). It loud-fails (`RosterError`) on a non-mapping root, a
  wrong/absent `domain:` discriminator, and **unknown top-level or per-persona keys** (typo guard).
  Reconciled split: **strict on document structure**, **coerce field element types** (unchanged
  `Roster.from_dict`), **soft-report content** via `validate_roster` (unique ids / required fields /
  non-empty briefs). `load_roster` adopts `parse_roster`.
  - **(v0.3, R1-F7)** The per-persona allow-set is **derived programmatically** from the
    `PersonaBrief` fields (not hand-enumerated), so adding a field cannot desync the guard.
  - **(v0.3, R1-F2/R1-S4) Forward-compat:** `protocol_version` is read, not merely allow-listed. A
    roster whose **major** `protocol_version` exceeds the SDK's is rejected (`RosterError`); a
    **same-major, higher-minor** roster relaxes the unknown-top-level-key guard to a **warning** (so
    an additive minor-version key does not hard-fail an older SDK). The strict typo guard applies only
    within the SDK's own major. (Mirrors the panel/VIPP `protocol_is_future` posture.)
  - **(v0.3, R2-F3/R2-S4) Panel-interaction acceptance criteria:** strict-by-default is a *behavior
    change* — a roster with a previously-tolerated stray key now flips `assess_roster` from `valid`
    to `invalid`; this is documented, not framed as a no-op. **Invariant:** the SDK's own shipped M0
    template bytes and the Concierge-projected roster **must parse clean under `parse_roster`** (a
    self-consistency golden run in N0 *alongside* the M0 byte-identity test, since that test freezes
    those exact bytes — the allow-set and the shipped bytes are reconciled within N0). The migration
    window is light (unreleased feature, no external rosters yet — see Appendix B on the deferred
    transitional flag).

### B. External persona-format ingestion

- **FR-3 — Ingestion adapter contract + round-trip gate.** Define a persona-format **adapter**:
  `adapt(text: str) -> AdaptResult` where `AdaptResult` carries the `Roster` **plus a `warnings:
  list[str]` channel** (empty in v1). **(v0.3, R1-F6/OQ-9)** Reserving the warnings channel now means a
  future *lossy* adapter can surface dropped fields without a breaking signature change to every
  registered adapter. Adapters emit through the `Roster` contract (never hand-written YAML).
  Ingestion (`ingest()`) then **round-trip-gates** (OQ-7): serialize → reparse via strict
  `parse_roster` + `validate_roster`.
  - **(v0.3, R1-F1) The gate is structural/schema only, NOT semantic.** A field-swapped-but-valid
    roster (e.g. `lens` mapped to `constraints`) passes the round-trip cleanly. Correctness of an
    adapter's *mapping* is therefore a first-class acceptance criterion of **FR-5** (golden per-adapter
    field-by-field tests), never "caught by the gate."
  - **(v0.3, R1-F3/R1-S7) Soft findings BLOCK at ingest, warn at load.** `validate_roster` findings
    (duplicate `role_id`, empty brief) **abort `ingest`** (import time is the right place to fail);
    the same findings are merely *reported* by `assess_roster`/panel load. One rule, two surfaces.
  - Ingestion is **one-way** (external → roster).
- **FR-4 — Pluggable adapter registry (trust-bounded).** Adapters are discoverable via the entry-point
  group **`startd8.stakeholder_panel.roster_adapters`**, mirroring `providers/registry.py`. Provide
  `discover()`, `get_adapter(name)` (missing ⇒ error listing `available()`), `register()` for tests.
  **(v0.3, R1-S2)** Trust/isolation is specified: (a) **failure isolation** — a broken/raising
  third-party entry point is **skipped-and-warned**, never aborting `discover()` for the others;
  (b) **name-collision precedence** — a **built-in wins** over a same-named entry point (documented,
  not undefined); (c) an entry-point adapter **executes arbitrary third-party code** at
  discover/adapt time — the **named `--format` invocation (NR-4) is the only trust gate**, stated
  plainly.
- **FR-5 — First built-in adapter (role-rubric), lazy + mapping-pinned.** Promote the pilot converter
  into a **generic** `role-rubric` adapter (the `key/label/lens/rubric/coverage/out_of_scope` shape),
  named for the *format family*, shipped in SDK core but **lazily loaded** (entry-point resolved on
  `get_adapter`, **not** imported by `stakeholder_panel/__init__` or on the `load_roster`/
  `assess_roster` hot path — R2-F4). It builds `PersonaBrief`/`Roster` objects directly and returns a
  validated `Roster` (no raw `yaml.safe_dump`).
  - **(v0.3, R1-F5) Pinned mapping (testable split):** `key→role_id`, `label→display_name`,
    `lens→goals`, **`rubric[].name`→`answers_for`** (routing keys) + **`"{name}: {description}"`
    →`known_positions`** (statements), `coverage→constraints`, `out_of_scope→out_of_scope`. Asserted
    field-by-field against a golden `reviewer_roles.yaml` fixture.
  - **(v0.3, R1-S6) Input-shape guard:** the adapter **rejects a malformed source** (missing
    `key`/`label`/`rubric`, wrong shape) with a clear adapter error, rather than silently emitting a
    thin/under-populated roster.
- **FR-6 — Ingestion surface (CLI, scriptable).** `startd8 panel import --format <name> <source>
  [--out <path>] [--force]` runs the named adapter, round-trip-gates (FR-3), writes the roster
  (default `docs/kickoff/inputs/stakeholders.yaml` under `--project`) — CLI-as-sole-writer.
  - **(v0.3, R2-F5) Exit-code contract:** distinct non-zero codes for unknown-format, adapter/source
    failure, round-trip-gate rejection, and clobber-refusal; `0` on success — so `import` is
    CI-gateable, not pass/fail-opaque.
  - **(v0.3, R1-S8) Hand-authored clobber guard:** the default `--out` is the file the panel loads;
    `import` **warns (and requires confirmation) when the target lacks a `GENERATED` header** (looks
    hand-authored) even under `--force`, to prevent silent loss of a hand-edited roster.
- **FR-7 — Ingested-roster provenance (advisory header).** An ingested roster carries a generated
  header (`# GENERATED from <source> via <format> adapter — edit the source, re-run import`).
  **(v0.3, R1-F4) This is explicitly *advisory, not load-bearing*:** a YAML comment is stripped by
  `yaml.safe_load`, not preserved across re-serialization, trivially editable, and invisible to
  programmatic consumers. It is a human breadcrumb, not tamper-evidence or machine lineage. **(v0.3,
  R1-S5)** The header records a **normalized/basename** source token (not an absolute path) so the
  emitted roster **body is byte-deterministic across machines/working dirs**. Header-level only — no
  per-field `ExtractionRecord`.

### C. Reuse decision + error model

- **FR-8 — Reuse the right rails, avoid the wrong ones.** The capability **reuses**: the
  `kickoff_inputs` per-domain `parse_X(text)->Manifest` + `domain:`-discriminator + loud-fail
  contract (FR-2), and the `providers/registry.py` entry-point idiom (FR-4). It **does not** enroll
  the roster into the `manifest_extraction` grammar or reuse `concierge/derive` — both are welded to
  the buildable-app **relational/Prisma** grammar and would wrongly drag the roster into app codegen
  + round-trip-to-schema validation (reaffirms panel OQ-1).
- **FR-9 — Caller-visible error taxonomy (v0.3, R2-F1/R2-S2).** The three failure surfaces must be
  **distinctly catchable**, not collapsed into one opaque error: (1) **`RosterError`** — the roster
  *document* is structurally/schema-invalid (FR-2); (2) an **`AdapterError`** (or format error) — the
  *source* is malformed or the `--format` is unknown (FR-4/FR-5); (3) **content findings** from
  `validate_roster` — a typed advisory list (dup ids, empty briefs). Critically, a **round-trip-gate
  reparse failure inside `ingest` is semantically an *adapter bug*, not a user-roster fault**, and is
  surfaced as such (wrapped, e.g. `AdapterError`, not a bare re-raised `RosterError`). The FR-6 CLI
  maps these to distinct messages + exit codes.

---

## 3. Non-Requirements

- **NR-1 — Not a manifest-extraction grammar kind.** Reaffirms panel OQ-1: the roster is a plain
  value input the panel reads; it is not an app-codegen manifest and `manifest_extraction/` is not
  touched.
- **NR-2 — No prose/NLP extraction.** Personas come from *structured* YAML (native) or a *structured*
  external format via an adapter — never NL-extracted from freeform markdown.
- **NR-3 — No reuse of `concierge/derive`.** That path introspects Pydantic → Prisma entities; a
  persona roster has no entities/relations to derive.
- **NR-4 — No format auto-detection.** The caller names the adapter (`--format`); the SDK does not
  guess an unknown file's format.
- **NR-5 — One-way only.** No external ⇐ roster writeback or bidirectional sync; the source format
  stays the upstream authority.
- **NR-6 — No new template plumbing.** Packaging/projection/download/byte-identity (M0, `writes.py`)
  are reused unchanged.
- **NR-7 — No SDK coupling to a downstream format.** The built-in adapter targets the *role-rubric
  format family*, not any one project's file.

---

## 4. Open Questions

*(OQ-1 through OQ-7 resolved by the planning pass — see §0.)*

- **OQ-8 (deferred)** — Should the benchmarking one-off `reviewer_roles_to_roster.py` be retired in
  favor of `startd8 panel import --format role-rubric` (N3), or kept as a thin shim that calls the
  SDK? Cosmetic; resolve when N2 lands.
- **OQ-9 → Partly resolved (R1-F6).** The *decision* (drop/warn/stash) stays deferred, but the
  *interface affordance* is reserved **now**: `adapt` returns `AdaptResult{roster, warnings}` (FR-3),
  so a future lossy adapter has a diagnostics channel without a breaking protocol change. v1
  `role-rubric` is lossless (empty warnings).

---

*v0.2 — Post-planning self-reflective update. 1 requirement narrowed (FR-1), 6 firmed, 7 OQs resolved.*

*v0.3 — Post-CRP convergent review (R1+R2, dual-document). Applied 12 requirements suggestions across
FR-1..FR-7 and added **FR-9** (error taxonomy): round-trip gate rescoped to structural-only (R1-F1),
`protocol_version` forward-compat defined (R1-F2), soft-findings-block-at-ingest (R1-F3), header
advisory-not-load-bearing + normalized (R1-F4/R1-S5), pinned role-rubric mapping + input guard
(R1-F5/R1-S6), diagnostics channel reserved (R1-F6), allow-set + schema-doc drift guards (R1-F7/R2-F2),
registry trust/isolation (R1-S2), panel-interaction golden (R2-F3), adapter lazy-load (R2-F4), CLI
exit codes (R2-F5). One accepted-in-part (R1-S3 transitional flag deferred — Appendix B). Full
dispositions in Appendix A/B. Companion plan: `PERSONA_FORMAT_AND_INGESTION_PLAN.md` v1.1.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Round-trip gate is structural-only, not semantic; adapter-mapping tests first-class | R1 | Applied → FR-3 rescope + FR-5 golden mapping tests | 2026-07-02 |
| R1-F2 | Define `protocol_version` forward-compat vs strict unknown-key | R1 | Applied → FR-2 forward-compat (major reject / minor warn) | 2026-07-02 |
| R1-F3 | Resolve FR-2/FR-3 soft-vs-blocking contradiction | R1 | Applied → FR-3: soft findings block at ingest, warn at load | 2026-07-02 |
| R1-F4 | State header provenance advisory-not-load-bearing | R1 | Applied → FR-7 advisory framing | 2026-07-02 |
| R1-F5 | Acceptance criterion for `rubric→known_positions+answers_for` split | R1 | Applied → FR-5 pinned mapping (names→answers_for, "name: desc"→known_positions) | 2026-07-02 |
| R1-F6 | Reserve a diagnostics channel in `adapt` now (lossy-future) | R1 | Applied → FR-3 `AdaptResult{roster, warnings}`; OQ-9 partly resolved | 2026-07-02 |
| R1-F7 | Derive per-persona allow-set programmatically from `PersonaBrief` | R1 | Applied → FR-2 allow-set derivation | 2026-07-02 |
| R2-F1 | Caller-visible error taxonomy (3 failure classes) | R2 | Applied → new FR-9 | 2026-07-02 |
| R2-F2 | `ROSTER_SCHEMA.md` generated/checked vs model (doc-sync) | R2 | Applied → FR-1 drift guard | 2026-07-02 |
| R2-F3 | FR-2 panel-interaction consequences + shipped-template golden | R2 | Applied → FR-2 acceptance criteria | 2026-07-02 |
| R2-F4 | Bound adapter coupling — lazy/entry-point load, off hot path | R2 | Applied → FR-5 lazy-load | 2026-07-02 |
| R2-F5 | CLI exit-code contract per failure mode | R2 | Applied → FR-6 exit codes | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S3 (part) | Transitional warn-only mode / `STARTD8_ROSTER_STRICT` flag before strict-by-default | R1 | Deferred, not v1. The audit + shipped-template golden half is **applied** (FR-2, plan N0). The migration-window flag is unwarranted now: the panel (M0–M3) is **unreleased and unmerged**, so there are **no external on-disk rosters** to protect — only the SDK's own template + the pilot output, both reconciled in N0. Revisit only if strict-parse ships *after* real downstream rosters exist. | 2026-07-02 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 16:10:00 UTC
- **Scope**: Requirements-side review of the persona-format formalization + external-format ingestion capability. Focus per orchestrator brief: strict/permissive reconciliation (FR-2), round-trip gate sufficiency (FR-3), adapter registry trust (FR-4), provenance honesty (FR-7), lossy/forward-compat (OQ-9, protocol_version).

**Executive summary**

- FR-3's "a buggy adapter fails loudly at import time" **over-claims**: serialize→reparse catches structural/schema bugs but is blind to semantic mis-mapping (a field-swapped-but-valid roster passes the gate). This is the single riskiest sentence in the doc.
- FR-2's strict unknown-key rejection is in direct tension with the `protocol_version` key it admits — a future minor-version roster that adds a key will loud-fail on an older SDK, i.e. the format is **not actually forward-compatible** despite carrying a version field.
- FR-2 (validate_roster is "soft-report") and FR-3 (validate_roster is part of the accept/reject gate) **contradict** on whether soft findings (dup ids, empty briefs) block ingestion.
- FR-7 header provenance is advisory-only but is described as if load-bearing; a YAML comment is stripped by `yaml.safe_load` and by any re-serialization, and is invisible to every programmatic consumer.
- FR-5's `rubric → known_positions + answers_for` fan-out has no acceptance criterion for how one list splits across two fields — untestable as written.
- OQ-9 (lossy) is deferred, but the deferral silently constrains the FR-3 `adapt(text)->Roster` signature today (no channel for drop/warn diagnostics).

**Numbered suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | Rescope FR-3's failure claim: state that the round-trip gate catches **structural/schema** faults only and does **not** detect semantic mis-mapping (e.g. `lens` routed to `constraints` instead of `goals`); make per-adapter semantic-mapping tests a first-class acceptance criterion of FR-5, not an afterthought of the gate. | FR-3 asserts "a buggy adapter fails loudly at import time, not at panel-load time" — but a structurally-valid-yet-semantically-wrong roster passes serialize→reparse cleanly. The claim invites false confidence that the gate is a correctness check. | FR-3 (sentence "so a buggy adapter fails loudly at import time"); add cross-ref to FR-5 | Unit test: an adapter that swaps two field mappings still passes `parse_roster`+`validate_roster` (proving the gate is insufficient) and is only caught by the FR-5 mapping test. |
| R1-F2 | Risks | high | Specify forward-compat semantics for `protocol_version`: define whether an older SDK reading a roster with an unknown-but-newer `protocol_version` should (a) reject, (b) warn-and-strict, or (c) relax the unknown-top-level-key guard to a warning. As written, strict unknown-key rejection makes the version field cosmetic — a legitimately forward-compatible roster will loud-fail. | FR-2 hard-rejects unknown top-level keys while the plan's allow-set admits `protocol_version`; the two policies cannot coexist for real forward evolution. A format that carries a version but cannot tolerate any additive key is not versioned. | FR-2 (the "unknown top-level or per-persona keys (typo guard)" clause) | Test: a roster with `protocol_version: 2` and one extra additive top-level key is handled per the chosen policy (not an unconditional `RosterError`). |
| R1-F3 | Interfaces | medium | Resolve the FR-2/FR-3 contradiction on validation hardness: FR-2 says `validate_roster` "soft-reports" content issues, but FR-3 folds `validate_roster` into the accept/reject round-trip gate. State explicitly which soft findings (duplicate `role_id`, empty brief) **block** ingestion vs merely warn. | An adapter emitting duplicate `role_id`s currently passes the gate under a literal reading of FR-2 ("soft"), defeating FR-3's purpose. Implementers will guess. | FR-3 ("reparse via the FR-2 strict `parse_roster` + `validate_roster` before accepting") vs FR-2 ("soft-report content") | Test: ingest of a role-rubric source with duplicate keys either fails import (if blocking) or emits a documented warning — behavior must match the spec. |
| R1-F4 | Security | medium | State plainly that FR-7 header provenance is **advisory, not load-bearing**: it is stripped by `yaml.safe_load`, not preserved across any re-serialization, trivially editable, and invisible to programmatic consumers. If tamper-evidence or machine-readable lineage is wanted, specify a data-field path (e.g. `provenance_default`) and relate it to the panel's existing brief-hash provenance. | FR-7 says the header makes a roster "distinguishable from a hand-authored roster and regeneratable" — this implies a durability the comment does not have. Honest framing prevents downstream tools from trusting it. | FR-7 (whole bullet) | Test: parse→re-serialize a roster and assert the header comment is gone (documents the advisory nature); if a data-field provenance is added, assert it survives round-trip. |
| R1-F5 | Validation | medium | Give FR-5 an acceptance criterion for the one-to-two `rubric → known_positions + answers_for` fan-out: define exactly what content lands in `known_positions` vs `answers_for` (e.g. `answers_for` = rubric *names/keys*, `known_positions` = rubric *statements*), so the mapping is testable and not implementer-dependent. | FR-5 lists `rubric→known_positions+answers_for` with no rule for the split; two implementers will diverge and both "pass" a loose test. | FR-5 (mapping list, `rubric→known_positions`+`answers_for`) | Test: golden `reviewer_roles.yaml` fixture → exact expected `known_positions` and `answers_for` values asserted field-by-field. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F6 | Architecture | medium | Even though OQ-9 (lossy ingestion) is deferred, reserve a diagnostics channel in the FR-3 adapter contract **now** — e.g. `adapt(text) -> Roster` returning (or accepting) an optional warnings sink — so a future lossy adapter can surface dropped fields without a breaking signature change to every already-registered adapter. | Deferring the *decision* is fine; deferring the *interface affordance* is not — v1 locks `adapt(text)->Roster` with no warning path, so v2's drop/warn/stash choice forces a protocol break across all third-party adapters. | OQ-9; and FR-3 adapter signature | Test: adapter protocol includes an (optional, ignorable in v1) diagnostics return; a lossy stub emits a warning without altering the required `Roster` return. |
| R1-F7 | Data | low | FR-2's per-persona allow-set is specified as "= `PersonaBrief` fields"; require it be derived **programmatically** from the dataclass/model fields, not hand-enumerated, so adding a `PersonaBrief` field cannot silently desync the typo guard (a new legitimate field would be rejected as "unknown"). | A hand-listed allow-set is a latent drift bug: the strict gate would reject valid rosters the moment `PersonaBrief` gains a field. | FR-2 ("unknown per-persona keys (allow-set = `PersonaBrief` fields)") | Test: add a temporary field to `PersonaBrief`; a roster using it parses without a code edit to the allow-set. |

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 16:40:00 UTC
- **Scope**: Second-round requirements review. Deliberately avoiding R1-F1..F7. Per orchestrator brief, pushing on angles R1 underweighted: (a) an **error taxonomy** across the three distinct failure surfaces, (b) `ROSTER_SCHEMA.md` (FR-1) as a **drift/maintenance liability**, (c) the **interaction of strict FR-2 with the broader stakeholder-panel spec** (`assess_roster` reported states, the shipped M0 template as a self-passing golden), and (d) the **role-rubric adapter's placement/coupling** to the panel hot path.

**Executive summary**

- The requirements create **three distinct failure surfaces** — FR-2's `RosterError` (structural), FR-4/FR-6's unknown-format/adapter error, and FR-3's round-trip-gate reparse failure — but never define a **taxonomy**. A caller (CLI, `assess_roster`, downstream) cannot programmatically distinguish "your *source* is malformed" from "the *adapter* is buggy" from "the roster loads but has content warnings." R1-F3 flagged the soft-vs-blocking *hardness*; the missing *type distinction* is orthogonal and unaddressed.
- FR-1's hand-written `ROSTER_SCHEMA.md` **duplicates** the `PersonaBrief` field list and the FR-2 allow-set with no sync mechanism — it will drift and begin to lie. R1-F7 asked the *runtime* allow-set be derived from the dataclass; the *doc* has the same defect and no coverage.
- FR-2 **changes the panel's observable behavior**: a roster with a typo'd key that previously loaded and reported `valid` via `assess_roster` now reports `invalid`. The requirement frames strictness as a no-op ("nothing breaks") and never states that the SDK's **own shipped template** must be a golden that passes the new gate.
- FR-5 places the role-rubric adapter "in SDK core" without bounding its **coupling** — nothing stops it (and its YAML/adapter deps) from being pulled into the panel's `load_roster` hot path, which never needs ingestion.

**Numbered suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Interfaces | high | Define a caller-visible **error taxonomy** distinguishing the three failure classes: (1) `RosterError` — the roster document is structurally/schema invalid (FR-2); (2) an **adapter/format error** — the *source* file is malformed or the `--format` is unknown (FR-4/FR-6); (3) **content findings** from `validate_roster` — loads but has soft issues (dup ids, empty briefs). Require these be separately catchable/reportable (distinct exception types or a typed result), because FR-3 currently reuses `RosterError` for a *gate* failure, conflating "adapter bug" with "user's roster malformed." | Without a taxonomy, `assess_roster`, the FR-6 CLI, and any downstream tool collapse "bad input," "buggy adapter," and "advisory warning" into one opaque failure — undebuggable and untestable. This is distinct from R1-F3 (which is about *whether* soft findings block) — this is about *which error type* the caller receives. | New sub-bullet under FR-3, cross-linked from FR-2 and FR-6 | Test: an unknown `--format`, a malformed source, and a structurally-invalid emitted roster each surface a *distinguishable* error type/code; a soft finding surfaces as a distinct advisory. |
| R2-F2 | Validation | medium | FR-1: require `ROSTER_SCHEMA.md`'s documented field set to be **generated from, or checked against, the `PersonaBrief`/`Roster` model** (a doc-sync test), not free-authored. As written it hand-restates the dataclass fields *and* the FR-2 allow-set in prose. | A hand-written schema doc is a maintenance liability that silently diverges from the code it claims to document — the moment `PersonaBrief` changes, the doc lies and external tools targeting it emit rosters the FR-2 gate rejects. This extends R1-F7's drift argument from the runtime allow-set to the human-facing contract. | FR-1 ("authoritative schema reference (`ROSTER_SCHEMA.md`)") | Test: assert the field names enumerated in `ROSTER_SCHEMA.md` == `PersonaBrief` fields == FR-2 allow-set (fail the build on divergence). |
| R2-F3 | Architecture | high | FR-2: state the **panel-interaction consequences** of strict-by-default as first-class acceptance criteria: (1) `assess_roster` now reports `invalid` (not `valid`) for rosters carrying a previously-tolerated stray/typo key — a behavioral change to the panel's assess surface and any Concierge `assess` wiring that consumes it; and (2) an **invariant** that the SDK's own shipped M0 template and the Concierge-projected roster **must parse clean** under the new `parse_roster` (a self-consistency golden). | FR-2 asserts "assess_roster already degrades a RosterError to invalid" as if benign, but that *is* the behavior change: states flip from valid→invalid for existing rosters, and nothing guarantees the SDK's own template satisfies its own new gate. Distinct from R1-S3 (which covers *arbitrary downstream* on-disk rosters + a migration window) — this covers the SDK's *own* artifacts and the `assess_roster` state semantics. | FR-2 (the `assess_roster` clause) and §1 problem statement | Test: (a) a roster with a stray key transitions `valid`→`invalid` in `assess_roster` (documented); (b) the exact shipped template bytes parse clean under `parse_roster`. |
| R2-F4 | Architecture | medium | FR-5: bound the adapter's coupling — state that the `role-rubric` adapter (and any adapter deps) must be **lazily/entry-point loaded**, not eagerly imported by `stakeholder_panel/__init__` or on the `load_roster`/`assess_roster` path. "Lives in SDK core" should mean *shipped in the package*, not *imported at panel load*. | Ingestion is a one-time authoring step; roster *loading* is the hot path. Bundling adapter code into the panel's import graph adds weight and couples panel load to ingestion machinery it never uses — the entry-point idiom (FR-4) already enables lazy resolution, so this is free if stated. | FR-5 ("living in SDK core") | Test: importing `stakeholder_panel` / calling `load_roster` does **not** import the adapter module (assert via `sys.modules`); the adapter loads only on `get_adapter("role-rubric")`. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F5 | Interfaces | medium | FR-6: specify the CLI's **exit-code contract** — distinct non-zero codes (or clearly distinguishable messages) for unknown-format, adapter/source failure, round-trip-gate rejection, and clobber-refusal — so `import` is scriptable/CI-gateable rather than pass/fail-opaque. This is the CLI-surface projection of the R2-F1 taxonomy. | FR-6 promises "a clear error listing registered adapters" for one case only; the other three failure modes have no stated surface, so a CI job cannot branch on *why* an import failed. | FR-6 (whole bullet) | Test: each failure mode yields a documented, distinct non-zero exit code; success yields 0. |

**Endorsements** (prior untriaged R1 items this reviewer independently agrees with):
- R1-F1 — the strongest item in R1: the round-trip gate is structurally blind to semantic mis-mapping. My R2-F1 (taxonomy) and R2-F3 (panel interaction) both presume this is accepted.
- R1-F3 — the soft-vs-blocking contradiction is real and blocks a testable `ingest`; it is the *hardness* half of the same gap my R2-F1 addresses on the *type* axis.
- R1-F7 — programmatic allow-set derivation; R2-F2 extends the identical drift argument to the FR-1 schema doc, so the two should be triaged together.
