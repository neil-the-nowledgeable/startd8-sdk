# Concierge `derive-contract` — Requirements

**Version:** 0.3 (Post-CRP — R1 triaged, all 19 suggestions accepted and folded in)
**Date:** 2026-06-16
**Status:** Draft — security/validation-hardened; cleared to implement
**Plan:** [`CONCIERGE_DERIVE_CONTRACT_PLAN.md`](CONCIERGE_DERIVE_CONTRACT_PLAN.md)
**Parent:** [`CONCIERGE_MCP_REQUIREMENTS.md`](CONCIERGE_MCP_REQUIREMENTS.md) v0.4 (FR-C8, the deferred
action this expands); [`CONCIERGE_FRICTION_LOG_NAVIG8.md`](CONCIERGE_FRICTION_LOG_NAVIG8.md) (F-5,
the motivating friction)
**Worked example:** `~/Documents/dev/navig8/prisma/schema.prisma` — derived **by hand** from
`startd8_work.legal` Pydantic models this session; the rules below are reverse-engineered from
that hand-pass.
**Reuse target:** `manifest_extraction/prisma_emitter.render_prisma_schema(graph)` — the emit half.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the emitter/IR, the navig8 source models, and the hand-derived contract.
> It resolved all 8 open questions and corrected ~4 requirements (>30% — the loop working). The
> biggest result is positive: the load-bearing OQ-1 is FEASIBLE, so no new IR is needed.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Unclear whether `EntityGraph` (built for the markdown path) can represent Pydantic models (OQ-1) | **FEASIBLE — no adapter.** Every field the emitter *reads* has a Pydantic source; doc-specific fields (`heading_path`/`row_index`/`notes`/`human_only`) are simply ignored. | FR-DC-4 firmed: reuse `EntityGraph` + `render_prisma_schema` as-is; no new IR. |
| Introspection mechanism open (OQ-2) | **Runtime import, not static AST** — Pydantic needs `model_fields` for `is_required`/defaults/computed-field detection; AST alone is insufficient. | New **FR-DC-10**: the action imports the target models, so the project's deps must be importable; module-import side effects are documented. |
| "cross-entity trace → join model" listed as a deterministic rule (FR-DC-5) | **NOT deterministic.** A `List[str]` of ids is ambiguous (loose refs vs Json vs M2M join); navig8's `ScreeningLink` needed hand judgment. | FR-DC-5 corrected: M2M joins are **marker-driven + flagged**, not auto-derived. New **FR-DC-12** (marker mechanism). |
| Exclusions framed as "rules" (FR-DC-6) | **Mostly model-selection + auto computed-field filter.** Which entities are storage-bearing is the human's pick (IntakePacket isn't even in the model set); only `@computed_field` is auto-excluded. Pipeline-artifact names are *flagged*, not dropped. | FR-DC-6 reframed; new **FR-DC-13** (model-set selection). |
| `--check` drift mode floated as OQ-7 | **FEASIBLE, reuse `parity_against_live`/`semantic_diff` as-is** (~50 LOC). It is the *durable* value of mechanizing F-5. | Promoted to **FR-DC-11** (a requirement, not an option). |
| id-detection / 1:N / nested-ref / Dict→Json / enum rules (OQ-3/4/5) | **Deterministic**, verified against navig8: explicit `id:str`→`<entity>Key`+`@@unique`; no-id→cuid; parent `List[Child]`→child FK; nested `BaseModel`→FK; `List[scalar]`/`Dict`→`Json`; `Enum`→prisma enum + hyphen-normalize. | FR-DC-5 kept for these; confidence raised. |

**Resolved open questions:**
- **OQ-1 → reuse EntityGraph** (feasible, no adapter). **OQ-2 → runtime import** (FR-DC-10).
  **OQ-3 → deterministic for 1:N/nested-ref; M2M needs a marker** (FR-DC-12). **OQ-4 → deterministic**
  (explicit `id:str` present → key; absent → cuid). **OQ-5 → model-selection + computed-field
  auto-exclude; artifacts flagged** (FR-DC-13). **OQ-6 → model-set selection becomes FR-DC-13.**
  **OQ-7 → promoted to FR-DC-11.** **OQ-8 → v1 is a fuller slice than feared** — deterministic rules
  cover most of navig8; only M2M + artifact-exclusion need markers/flags.
- **New open questions for CRP:** golden-test fidelity (OQ-DC-1), marker shape (OQ-DC-2), import
  safety/sandboxing (OQ-DC-3), model-set selection ergonomics (OQ-DC-4) — see the plan §4.

---

## 1. Problem Statement

The Concierge ships four actions (`survey`/`assess`/`instantiate-kickoff`/`log-friction`).
`derive-contract` is the fifth, deferred (FR-C8) because it is net-new AST work. It exists to
close friction **F-5**: kickoff assumes the `schema.prisma` contract is *authored fresh* as the
front DATA-MODEL bookend, but **brownfield** projects already have stable, validated domain
models (navig8 had attorney-pipeline-validated Pydantic models). For those, the contract must be
*derived from code* — the reverse of `generate backend` (contract → code). Today that derivation
is done by hand (I did navig8's), which is slow and risks the hand-written contract silently
**drifting** from the proven models.

### Gap table

| Component | Current state | Gap |
|-----------|--------------|-----|
| Contract authoring | `generate backend` consumes a `schema.prisma`; assumes it exists | No path *to* a contract from existing models |
| Models→contract | Hand-derived (navig8); rules live only in a human's head + commit msg | Not mechanized; drift risk; not repeatable |
| Emit half | `prisma_emitter.render_prisma_schema(EntityGraph)` exists ($0) | Consumes the *markdown-doc* IR; no Pydantic front-end produces that IR |
| Architect ratification | The contract is the human DATA-MODEL bookend | No artifact enumerating what a derivation *changed/excluded* for review |

---

## 2. Requirements

### Surface & posture

- **FR-DC-1 — Fifth Concierge action, same envelope.** `derive-contract` joins the
  `startd8_concierge` action enum and the `startd8 concierge` CLI. **MCP preview-only** (returns
  the proposed contract + report, never writes — FR-C3/C3a); **CLI is the sole writer** (OQ-7),
  preview-by-default, `--apply`/`--force` via the safe-writer. Assist posture (FR-C2): it
  *proposes*; the **Architect ratifies** — derive-contract never marks the contract authoritative.
  **`--apply` writes a *candidate*, not a ratification (R1-F7/R1-S4):** it never by itself makes the
  contract authoritative; ratification is a separate, explicit Architect step. The emitted artifact
  carries the FR-DC-7 provenance marker so downstream can tell candidate from ratified.
- **FR-DC-2 — $0, deterministic, byte-identical (R1-S7/R1-F9).** Derivation is introspection + a
  deterministic transform, not generation; no model calls. Byte-identity is only guaranteed with a
  **canonical ordering**, which is a hard precondition: entity discovery, field emission, and enum
  value sets use a defined stable order (declaration order from `model_fields`; a documented
  tiebreak), independent of import order or dict/set iteration. Re-running in a fresh interpreter
  with shuffled import order MUST produce identical output.

### Input & introspection

- **FR-DC-3 — Input is the project's Pydantic models; explicit selection only (R1-F8).** The action
  takes a target (a module, a package, or a declared list of model classes) and introspects the
  `BaseModel` subclasses into an IR. It emits **only the explicitly-selected models** — a model
  merely *imported* by the selected package (`from other import Foo`), or an abstract/base class, is
  **not** silently included (consistent with FR-DC-13's "never silently pulls in entities"). *(Assumption: Pydantic v2; SQLModel/dataclasses out of v1.)*
- **FR-DC-4 — Produce the emit-half IR.** Introspection yields an `EntityGraph` (the
  `manifest_extraction` IR: entities, fields, enums, fk_parents, joins, uniques) so the existing
  `render_prisma_schema` emits the `.prisma`. *(Assumption to verify: that IR — built for the
  markdown path — can faithfully represent Pydantic-derived models; see OQ-1.)*

### Derivation rules (reverse-engineered from the navig8 hand-pass)

- **FR-DC-5 — The transform rules.** Apply deterministically, each recorded in the report:
  - semantic string id field → `<entity>Key` + `@@unique([parent, key])`, with a synthesized cuid row PK;
  - `Dict`/`List[...]`/nested-object fields with no relation → `Json`;
  - a list/set that encodes a cross-entity trace → an M2M **join model** (navig8 `ScreeningLink`)
    — **but this is not deterministic** (a `List[str]` of ids is ambiguous); it is marker-driven
    (FR-DC-12) and flagged when unmarked (FR-DC-8), never auto-guessed;
  - Python `Enum` → Prisma `enum`; **hyphenated enum *values* → underscore** + a loader-normalization note (hyphens are illegal Prisma identifiers);
  - builtin/reserved-name fields renamed (navig8 `type` → `nodeType`);
  - `@computed_field`/`@property` → **not** stored columns (stay computed);
  - house meta-fields (`id`/`createdAt`/`updatedAt`/…) added per the SDK convention if absent.
- **FR-DC-6 — Exclusions are explicit, not silent.** Entities/fields excluded from the contract
  (no-storage entities, verification/pipeline artifacts, computed fields) are **listed in the
  report with a reason**, never dropped invisibly. *(navig8 excluded `IntakePacket` + the
  verification artifacts by hand.)*

### Output, ratification, integrity

- **FR-DC-7 — Emit contract + derivation report + provenance marker.** Output is (a) the candidate
  `schema.prisma`, (b) a **derivation report** naming every transform applied, every exclusion, and
  every **ambiguity flagged** (FR-DC-8), and **(c) a machine-readable provenance header in the
  emitted contract (R1-F6/R1-S4)** — `derived-by: derive-contract; status: unratified` — so the
  artifact is *not* byte-indistinguishable from a hand-authored ratified contract and a downstream
  cascade guard can detect "unratified." The report is the Architect's review surface (FR-DC-1).
- **FR-DC-8 — Flag ambiguity, never guess silently.** Where introspection cannot decide
  (is `List[str]` a `Json` column or a relation? which field is the semantic id? is this entity
  storage-bearing?), the action **flags it for the human** with its best guess + the alternatives,
  rather than committing a silent choice.
- **FR-DC-9 — No clobber; validate; candidate-not-ratified.** Never overwrites an existing
  `schema.prisma` without `--force` (safe-writer). The emitted contract is validated by re-running
  `startd8 wireframe` against it (compose, FR-C10) so a malformed derivation is caught. The written
  artifact is a **candidate** carrying the FR-DC-7 provenance marker; `--apply` does not constitute
  ratification (FR-DC-1) — a cascade guard may warn if run against an `unratified`-marked contract.

### Added by the planning pass

- **FR-DC-10 — Runtime introspection; importable env (OQ-2).** Derivation introspects the models
  **at runtime** (`model_fields` — static AST can't see `is_required`/defaults/computed fields), so
  the action **imports the target package** and requires the project's dependencies importable.
  The report records the imported model set. Module-import side effects are a documented constraint
  (see OQ-DC-3 for the import-safety question).
- **FR-DC-11 — `--check` drift mode (promoted from OQ-7).** Re-derive the IR from the models and
  diff against the live `schema.prisma` via the existing `parity_against_live`/`semantic_diff`
  primitives; non-zero exit on drift. This is the durable value of mechanizing F-5 (catch
  model↔contract drift over time), so it ships in v1. **Ratified-ambiguity exclusion (R1-S8/R1-F10):**
  for items the deriver can only *flag*, not derive (an M2M join the human ratified into the live
  contract as e.g. `ScreeningLink`), `--check` MUST NOT report perpetual false drift — the ratified
  resolution of a flagged item is excluded from the drift set; drift is reported only for genuine
  model changes.
- **FR-DC-12 — Explicit markers for the non-deterministic derivations — split by owner
  (R1-S5/R1-F3).** The two ambiguous cases have different natural homes, so two mechanisms:
  - **M2M join hint** — field-local, so a minimal **model-side** `Field(json_schema_extra={...})`
    hint is acceptable (the signal lives on the `List[str]`-of-ids field; refactor-stable there).
  - **Artifact exclusion** — a project-curation decision that must **not** touch domain models:
    a **contract-side sidecar** keyed by fully-qualified class name (a model file with zero
    DB-specific imports can still drive exclusion).
  **Flag-for-human** (FR-DC-8) is the safe default when unmarked. **Orphaned-marker detection
  (R1-S6/R1-F4):** a marker whose target field/class no longer exists after a refactor MUST be
  reported, not silently ignored (else an orphaned exclusion marker re-includes an artifact).
- **FR-DC-13 — Model-set selection (OQ-6).** The user points the action at the entities to include
  (a package/module path or declared list). Exclusion is primarily *non-selection* + automatic
  computed-field filtering (FR-DC-6); the action never silently pulls in or drops entities.
- **FR-DC-14 — Import threat model + containment (R1-F1/R1-S1 — the security requirement).**
  Runtime introspection (FR-DC-10) *executes the target package's top-level module code and its
  transitive deps' import code* with the operator's privileges — the analogue of the write-path's
  OQ-7, and `derive-contract` is a *general* Concierge action that may be pointed at less-trusted
  cloned/brownfield repos, so "only point it at code you trust" is necessary but **not sufficient**
  on its own. Required:
  - **Trust boundary stated:** the operator-supplied package is trusted-by-assertion; the report
    records what was imported.
  - **Default containment:** introspect in a **subprocess with a scrubbed environment** (no
    inherited secrets), a **bounded timeout**, and an explicit network-egress posture (documented
    in-scope-risk or blocked).
  - **Fail-closed on import (R1-F2/R1-S2):** an import-time exception or timeout, or a **partial**
    import, **aborts the run with no contract emitted** — never map whatever subset imported (a
    partial model set silently produces a wrong-but-plausible contract).

---

## 3. Non-Requirements

- **Not a general ORM/migration tool.** Pydantic v2 in; not SQLAlchemy/Django/SQLModel/dataclasses
  in v1.
- **Not multi-language.** Python only.
- **Not semantic authorship.** It mechanizes the *structural* derivation; the human DATA-MODEL
  bookend (what the contract should *mean*, which entities matter) stays human — derive-contract
  proposes, the Architect decides.
- **Not relation invention.** It only derives relations the models actually express; it does not
  infer foreign keys the models don't encode.
- **Not a `generate backend` replacement.** It produces the *input* to that cascade, once.

## 4. Open Questions

> OQ-1…OQ-8 resolved by the planning pass (§0). OQ-DC-1/2/3 **resolved by CRP R1** (below); OQ-DC-4
> remains a small implementation-pass ergonomics call.

- **OQ-DC-1 — RESOLVED (CRP R1): two-sided golden bar.** "Matches modulo flagged items" is unsound
  (the modulo set is computed from the output under test, so a mis-flagging deriver still passes).
  The bar is now two-sided (R1-S3/R1-F5): freeze an expected `{flagged_items}` set and assert
  **(a)** the non-flagged output is AST-equal to the navig8 oracle **AND (b)** the deriver's flagged
  set equals the expected set. Divergence in either direction fails. (Plan Step 7.)
- **OQ-DC-2 — RESOLVED (CRP R1): split by owner** → FR-DC-12. Model-side `Field(json_schema_extra)`
  for the field-local M2M hint; contract-side sidecar (FQ-class-keyed) for artifact exclusion.
- **OQ-DC-3 — RESOLVED (CRP R1): containment, not just documentation** → FR-DC-14 (subprocess +
  scrubbed env + timeout + fail-closed-on-partial-import). "Trust your own code" is necessary but
  insufficient for a general action.
- **OQ-DC-4 — Open (small).** Model-set selection ergonomics: `--models app.models` (package) vs a
  glob vs scan-for-`BaseModel`-subclasses-under-a-root. FR-DC-3 settles the *semantics*
  (explicit-only, no transitive); this is the surface-syntax call for the implementation pass.

---

*v0.2 — Post-planning self-reflective update. OQ-1 resolved FEASIBLE (reuse `EntityGraph` +
`render_prisma_schema`, no new IR — the load-bearing win); 1 rule corrected (M2M joins are
marker-driven, not deterministic — FR-DC-5/FR-DC-12); 3 requirements added (FR-DC-10 runtime
import, FR-DC-11 `--check` drift, FR-DC-13 model-selection); exclusions reframed (FR-DC-6). All 8
original OQs resolved; 4 new implementation-pass OQs seeded. Net-new code bounded (~550 LOC
introspector+mapper); emit + drift + safe-writer reused. The reflective loop earned its keep by
falsifying the "trace → join" determinism claim before any code was written.*

*v0.3 — Post-CRP (R1, claude-opus-4-8-1m, all 19 suggestions accepted). New **FR-DC-14** (import
threat model + containment — the security hole: runtime import had a documented hazard but zero
control). Hardened: FR-DC-2 (canonical ordering for byte-identity), FR-DC-3 (explicit-only
selection, no transitive subclasses), FR-DC-7 (provenance marker `unratified`), FR-DC-9/FR-DC-1
(`--apply` ≠ ratification), FR-DC-11 (no false drift on ratified-flagged items), FR-DC-12 (markers
split by owner + orphaned-marker detection). OQ-DC-1 resolved to a two-sided golden bar (the
circular-acceptance fix), OQ-DC-2/3 resolved. The CRP earned its keep on the one-sided golden
test + the uncontained runtime import — two silent-wrong-but-plausible paths the internal loop
had left open.*

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

> R1 triage (2026-06-16): all 10 F-suggestions ACCEPTED — a focused, high-quality review; no noise.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Import threat model + containment | R1 | → **FR-DC-14** (subprocess/scrubbed-env/timeout) | 2026-06-16 |
| R1-F2 | Partial/failed import aborts (no contract) | R1 | → FR-DC-14 fail-closed clause | 2026-06-16 |
| R1-F3 | Split marker by owner (model-side hint / sidecar exclusion) | R1 | → FR-DC-12 | 2026-06-16 |
| R1-F4 | Marker refactor-survival + orphaned-marker detection | R1 | → FR-DC-12 | 2026-06-16 |
| R1-F5 | Two-sided golden bar | R1 | → OQ-DC-1 resolution + plan Step 7 | 2026-06-16 |
| R1-F6 | `unratified` provenance header on emitted contract | R1 | → FR-DC-7(c) | 2026-06-16 |
| R1-F7 | `--apply` ≠ ratification (explicit) | R1 | → FR-DC-1 + FR-DC-9 | 2026-06-16 |
| R1-F8 | Explicit-only selection (no transitive subclasses) | R1 | → FR-DC-3 | 2026-06-16 |
| R1-F9 | Canonical deterministic ordering for byte-identity | R1 | → FR-DC-2 | 2026-06-16 |
| R1-F10 | `--check` excludes ratified-flagged items from drift | R1 | → FR-DC-11 | 2026-06-16 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-16

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-16 01:09:15 UTC
- **Scope**: Requirements-side review (F-prefix). Weighted per the sponsor focus file on the four CRP open questions: import safety (OQ-DC-3/FR-DC-10), marker shape (OQ-DC-2/FR-DC-12), golden-test fidelity (OQ-DC-1), and assist-posture integrity (FR-DC-1). Adversarial pass included.

##### Executive summary

- **Import safety is under-specified (critical):** FR-DC-10 *documents* the runtime-import hazard but specifies no containment control; "documented constraint" ≠ a control.
- **The golden-test bar can hide divergence:** OQ-DC-1's "matches modulo flagged items" subtracts a modulo set derived from the output under test — a mis-flagging deriver still passes.
- **Assist-posture has one enforceability hole:** `--apply` (FR-DC-9) writes a real `schema.prisma` to the cascade's input path with no "derived/unratified" marker; ratification (FR-DC-1) is advisory prose.
- **Marker shape needs splitting:** M2M-join intent lives on a field; artifact exclusion is a project-curation decision that should not touch the model at all.
- **FR-DC-2 determinism is falsifiable as written:** discovery/field ordering can be import-order dependent; no canonical ordering is mandated.
- **Two silent-wrong-but-plausible paths found (adversarial):** partial-import emitting a subset contract; `--check` reporting perpetual false drift on ratified M2M resolutions.

##### Sponsor focus-file asks (addressed first)

**Ask 1 — Import safety (OQ-DC-3 / FR-DC-10): is runtime import acceptable; what is the threat model?**
- **Summary answer:** Partial — runtime import is acceptable *only* with an explicit, written threat model and a default-deny posture on *which* package is imported; "only point it at code you trust" is necessary but not sufficient as currently stated.
- **Rationale:** FR-DC-10 ("requires the project's dependencies importable… Module-import side effects are a documented constraint") names the hazard but stops at *documenting* it. The exposure is that `--models app.models` transitively imports arbitrary third-party deps whose top-level code runs with the operator's full privileges (filesystem, network, env/secrets). The "team's own models" framing (FR-DC-3 assumption) holds for navig8 but the action is a general Concierge surface (FR-DC-1) that will be pointed at less-trusted brownfield repos. This is the analogue of write-path OQ-7 and deserves the same rigor.
- **Assumptions / conditions:** The action ships as a general Concierge action, not a navig8-only script; operators may run it on cloned/untrusted repos.
- **Suggested improvements:** Add **FR-DC-14 (Import threat model)**: (a) the trust boundary (operator-supplied package = trusted-by-assertion), (b) the default containment (import in a subprocess with no inherited secrets / a scrubbed env; network egress documented as in-scope-risk or blocked), (c) a hard requirement that import-time exceptions/timeouts surface as a derivation error, never a silent partial model set. See F1, F2, F8.

**Ask 2 — Marker shape (OQ-DC-2 / FR-DC-12).**
- **Summary answer:** Depends — prefer a **contract-side sidecar** for exclusion; allow a *minimal* model-side `Field(json_schema_extra=...)` hint only for the M2M-join case where the signal genuinely lives on the field.
- **Rationale:** FR-DC-12 mandates "MUST NOT require polluting domain models with DB concerns beyond a minimal hint," but the two marked cases have different natural homes. M2M-join intent is a property of a specific `List[str]`-of-ids field and is refactor-stable when attached there; artifact *exclusion* is a project-level curation decision (which models are storage-bearing) that does not belong on the model. One uniform mechanism will be wrong for one of them.
- **Assumptions / conditions:** Pydantic v2 (FR-DC-3); a sidecar can be keyed by fully-qualified class name.
- **Suggested improvements:** Split FR-DC-12's "shape TBD" into two decisions; add acceptance criteria for marker *discoverability* and *refactor survival* (F3, F4).

**Ask 3 — Golden-test fidelity / acceptance bar (OQ-DC-1).**
- **Summary answer:** No — "matches modulo flagged items" is not sound as written; it can hide real divergence unless the flagged-item *set* is itself asserted against an independent oracle.
- **Rationale:** If the comparison subtracts whatever the deriver flagged, a deriver that wrongly flags (or wrongly fails to flag) an item still "passes," because the modulo set comes from the output under test, not an oracle. That is exactly the silent-wrong-but-plausible failure the sponsor asked to find.
- **Assumptions / conditions:** The navig8 hand-derived contract is the oracle.
- **Suggested improvements:** Make the bar two-sided (F5): freeze an expected `{flagged_items}` set and assert (1) emitted-non-flagged ≡ oracle-non-flagged (AST-equal), AND (2) emitted-flagged-set ≡ expected-flagged-set. Divergence in either direction fails.

**Ask 4 — Assist-posture integrity under a richer output.**
- **Summary answer:** Mostly sound, with one real hole: nothing prevents the `--apply`-written `schema.prisma` from being immediately consumed by the cascade before the Architect ratifies — ratification (FR-DC-1) is never made enforceable.
- **Rationale:** FR-DC-1 says "the Architect ratifies — derive-contract never marks the contract authoritative," but FR-DC-9 lets `--apply`/`--force` write a real `schema.prisma` to the canonical path that `generate backend`/`wireframe` read. No requirement makes the written artifact carry a "derived, unratified" marker or live in a staging path. The gate is prose, not a tool-checkable constraint.
- **Assumptions / conditions:** The cascade consumes `schema.prisma` by path with no provenance check.
- **Suggested improvements:** F6/F7 below — a derivation-provenance header in the emitted contract, and an explicit requirement that `--apply` does not by itself satisfy ratification.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | critical | Add FR-DC-14 defining the import threat model: trust boundary, default containment (subprocess + scrubbed env / documented network posture), and that import-time failure/timeout is a hard error. | FR-DC-10 documents the side-effect hazard but specifies no containment; "documented constraint" is not a control. Runtime import runs arbitrary transitive top-level code with operator privileges. | New FR under "Added by the planning pass", referenced from OQ-DC-3 | Threat-model doc reviewed; test that a model module with a top-level side effect (writes a sentinel file / opens a socket) runs under the declared containment, not the host env. |
| R1-F2 | Risks | high | FR-DC-10 must require that a partial/failed import aborts derivation rather than emitting a contract from the subset that imported. | "requires the project's dependencies importable" leaves the failure mode unstated; a partial import silently drops entities, producing a wrong-but-plausible contract. | FR-DC-10 body | Test: make one model in the set raise on import; assert derive-contract exits non-zero and emits no contract. |
| R1-F3 | Interfaces | high | FR-DC-12: separate the marker into (a) M2M-join hint (model-side `Field(json_schema_extra)` acceptable) vs (b) artifact exclusion (contract-side sidecar, keyed by FQ class name). | The two marked cases have different natural owners; one uniform mechanism pollutes models for the exclusion case (a project-curation decision, not a field property). | FR-DC-12, expand "shape TBD" | Acceptance: a model file with zero DB-specific imports can still drive exclusion via the sidecar. |
| R1-F4 | Validation | medium | FR-DC-12: add acceptance criteria that markers survive a field/class rename and are discoverable (deriver reports orphaned markers). | "survives refactors and stays discoverable" is in the focus file but not the requirement; an orphaned exclusion marker (model renamed) would silently re-include an artifact. | FR-DC-12 body | Test: rename a marked field/class; assert the deriver reports the orphaned marker rather than silently ignoring it. |
| R1-F5 | Validation | high | Tighten OQ-DC-1 into a two-sided golden-test bar: freeze an expected flagged-item set; assert non-flagged output is oracle-equal AND the flagged set equals the expected set. | "matches modulo flagged items" with a self-derived modulo set passes a deriver that mis-flags — hides the silent divergence the sponsor flagged. | §4 OQ-DC-1 + a new sentence in FR-DC-12 acceptance | Golden test asserts both halves; mutate the deriver to over-flag one field and confirm the test fails. |
| R1-F6 | Security | high | Require the emitted `schema.prisma` to carry a machine-readable "derived-by derive-contract; unratified" provenance header. | FR-DC-1 asserts non-authoritative posture but emits an artifact byte-indistinguishable from a hand-authored ratified contract; downstream cannot tell. | New FR near FR-DC-7, or FR-DC-7(c) | Test: emitted file contains the provenance marker; a downstream check can detect "unratified". |
| R1-F7 | Security | medium | FR-DC-1/FR-DC-9: state explicitly that `--apply` writes a *candidate* and does NOT constitute ratification; ratification is a separate Architect step. | Ratification is treated as posture but `--apply` writes to the path the cascade reads; nothing stops immediate consumption of an unratified contract. | FR-DC-1 posture clause + FR-DC-9 | Doc review; optionally a guard that warns if the cascade runs against an unratified-marked contract. |
| R1-F8 | Data | medium | FR-DC-3: state behavior for inherited / imported / abstract `BaseModel` subclasses pulled in transitively by the selected package. | "introspects the BaseModel subclasses" is ambiguous when a package imports models from elsewhere; transitive subclasses could silently enter the contract, contradicting FR-DC-13's "never silently pulls in entities." | FR-DC-3 assumption block | Test: a package that `from other import Foo` does not emit `Foo` unless explicitly selected. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Data | high | FR-DC-2 ("Same inputs → byte-identical output") is falsifiable as written: subclass discovery and `model_fields` ordering can be import-order/dict-insertion dependent, and enum value sets from set-typed sources are unordered. Mandate a canonical deterministic ordering. | A determinism guarantee with an unspecified ordering source intermittently fails the FR-DC-2 claim and the F5 golden test, producing flaky "drift" in `--check`. | FR-DC-2 body | Run derivation twice in fresh interpreters with shuffled import order; assert byte-identical output. |
| R1-F10 | Risks | medium | FR-DC-11 `--check`: define semantics when the live `schema.prisma` contains the *ratified* resolution of a flagged ambiguity (e.g. the M2M `ScreeningLink` a human confirmed). `--check` must not report perpetual drift on items it can only flag, not derive. | A re-derivation emits `Json?`+flag for the M2M field while the live contract has the ratified join model — a naive diff reports drift forever, training operators to ignore `--check`. | FR-DC-11 body | Test: against the live navig8 contract (with ScreeningLink), `--check` reports zero drift for the flagged-and-ratified M2M. |

*(No endorsements/disagreements — R1 is the first round; Appendix C had no prior untriaged items.)*
