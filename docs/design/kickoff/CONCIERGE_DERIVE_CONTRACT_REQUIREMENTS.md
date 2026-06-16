# Concierge `derive-contract` — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-15
**Status:** Draft
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
- **FR-DC-2 — $0, deterministic, no LLM.** Derivation is AST/introspection + a deterministic
  transform, not generation. No model calls. Same inputs → byte-identical output.

### Input & introspection

- **FR-DC-3 — Input is the project's Pydantic models.** The action takes a target (a module, a
  package, or a declared list of model classes) and introspects the `BaseModel` subclasses into an
  intermediate representation (IR). *(Assumption: Pydantic v2; SQLModel/dataclasses out of v1.)*
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

- **FR-DC-7 — Emit contract + derivation report.** Output is (a) the candidate `schema.prisma`
  and (b) a **derivation report** naming every transform applied, every exclusion, and every
  **ambiguity flagged** (FR-DC-8). The report is the Architect's review surface (FR-DC-1).
- **FR-DC-8 — Flag ambiguity, never guess silently.** Where introspection cannot decide
  (is `List[str]` a `Json` column or a relation? which field is the semantic id? is this entity
  storage-bearing?), the action **flags it for the human** with its best guess + the alternatives,
  rather than committing a silent choice.
- **FR-DC-9 — No clobber; validate the result.** Never overwrites an existing `schema.prisma`
  without `--force` (safe-writer). The emitted contract is validated by re-running
  `startd8 wireframe` against it (compose, FR-C10) so a malformed derivation is caught.

### Added by the planning pass

- **FR-DC-10 — Runtime introspection; importable env (OQ-2).** Derivation introspects the models
  **at runtime** (`model_fields` — static AST can't see `is_required`/defaults/computed fields), so
  the action **imports the target package** and requires the project's dependencies importable.
  The report records the imported model set. Module-import side effects are a documented constraint
  (see OQ-DC-3 for the import-safety question).
- **FR-DC-11 — `--check` drift mode (promoted from OQ-7).** Re-derive the IR from the models and
  diff against the live `schema.prisma` via the existing `parity_against_live`/`semantic_diff`
  primitives; non-zero exit on drift. This is the durable value of mechanizing F-5 (catch
  model↔contract drift over time), so it ships in v1.
- **FR-DC-12 — Explicit markers for the non-deterministic derivations.** The two ambiguous cases —
  M2M joins (FR-DC-5) and pipeline-artifact exclusion (FR-DC-6) — are resolved by an **opt-in
  marker** the model author sets (shape TBD — OQ-DC-2), with **flag-for-human** (FR-DC-8) as the
  safe default when unmarked. Markers MUST NOT require polluting domain models with DB concerns
  beyond a minimal hint.
- **FR-DC-13 — Model-set selection (OQ-6).** The user points the action at the entities to include
  (a package/module path or declared list). Exclusion is primarily *non-selection* + automatic
  computed-field filtering (FR-DC-6); the action never silently pulls in or drops entities.

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

> OQ-1…OQ-8 were **resolved** by the planning pass — see §0. The remaining questions are new ones
> the planning pass surfaced, carried for the CRP / implementation pass:

- **OQ-DC-1 — Golden-test fidelity.** A re-derivation won't byte-match the hand-written navig8
  contract (the flagged M2M `ScreeningLink`, the `SequenceConfig` Json bag, house-field ordering).
  Is "matches modulo flagged-ambiguity items" the right acceptance bar (FR-DC-12)?
- **OQ-DC-2 — Marker shape (FR-DC-12).** How does a model author mark an M2M join / an excludable
  artifact — `Field(json_schema_extra={"prisma": …})`, a `model_config` key, a sidecar YAML, or a
  decorator? Constraint: keep domain models free of DB concerns beyond a minimal hint.
- **OQ-DC-3 — Import safety (FR-DC-10).** Runtime introspection executes the target's module code.
  Subprocess isolation / sandbox, or document "only point it at code you trust" (it is the team's
  own models)? Security-relevant — flag for CRP.
- **OQ-DC-4 — Model-set selection ergonomics (FR-DC-13).** `--models app.models` (package) vs a
  glob vs scan-for-`BaseModel`-subclasses-under-a-root; inheritance/imported-model handling.

---

*v0.2 — Post-planning self-reflective update. OQ-1 resolved FEASIBLE (reuse `EntityGraph` +
`render_prisma_schema`, no new IR — the load-bearing win); 1 rule corrected (M2M joins are
marker-driven, not deterministic — FR-DC-5/FR-DC-12); 3 requirements added (FR-DC-10 runtime
import, FR-DC-11 `--check` drift, FR-DC-13 model-selection); exclusions reframed (FR-DC-6). All 8
original OQs resolved; 4 new implementation-pass OQs seeded. Net-new code bounded (~550 LOC
introspector+mapper); emit + drift + safe-writer reused. The reflective loop earned its keep by
falsifying the "trace → join" determinism claim before any code was written.*
