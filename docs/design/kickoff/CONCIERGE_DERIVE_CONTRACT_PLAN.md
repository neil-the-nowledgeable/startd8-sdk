# Concierge `derive-contract` — Implementation Plan

**Version:** 0.2 (Post-CRP R1 — all 9 S-suggestions accepted and folded in)
**Date:** 2026-06-15
**Status:** Draft — for review before implementation
**Requirements:** [`CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md`](CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md) v0.2

> The planning pass read the emitter/IR (`manifest_extraction/`), the navig8 source models
> (`startd8_work.legal`), and the hand-derived `navig8/prisma/schema.prisma`. Verdict: **most of
> the derivation is deterministic and the emit half + drift primitives are reused as-is**; the
> only net-new code is a Pydantic introspector + the IR mapping, and the only *ambiguous* rules
> (M2M joins, pipeline-artifact exclusion) are resolved by an explicit marker + flag-for-human.

---

## 1. Architecture: three layers, two reused

```
[1 NET-NEW]  PydanticModelIntrospector   models → normalized field/enum/relation facts
[2 NET-NEW]  EntityGraph mapper          facts → manifest_extraction.EntityGraph
[3 REUSE  ]  render_prisma_schema(graph) → schema.prisma            (prisma_emitter, unchanged)
[4 REUSE  ]  parity_against_live(graph, live) → drift               (--check, unchanged)
[  SAFE   ]  apply_write_plan / CLI                                 (Concierge safe-writer, OQ-7)
```

The contract direction is reversed from `generate backend`, but the **back half is identical** —
derive-contract feeds the same `EntityGraph` the markdown path feeds, into the same emitter.

## 2. Steps

### Step 1 — `PydanticModelIntrospector` (net-new, ~200 LOC)
Runtime introspection (OQ-2 resolved: AST alone is insufficient — Pydantic needs `model_fields`
for `is_required`/defaults). Per `BaseModel`:
- `model_fields` → name, annotation, required, default;
- unwrap `Optional[T]`/`List[T]`/`Dict[K,V]` via `typing.get_args`/`get_origin`;
- classify each field: scalar / enum (`issubclass(ann, Enum)`) / nested `BaseModel` / `List[BaseModel]`
  / `List[scalar]` / `Dict` / marked-join;
- detect & **drop** `@computed_field`/`@property` (not stored);
- collect `Enum` classes (values, with hyphen→underscore normalization + a note).
**Containment (FR-DC-14, R1-S1/S2 — was prose, now a control):** introspect in a **subprocess with
a scrubbed env** (no inherited secrets), **bounded timeout**, documented network-egress posture;
the report records what was imported. **Fail-closed:** an import-time exception/timeout or a
*partial* import **aborts with no contract emitted** — never map the subset that imported.

### Step 2 — EntityGraph mapper (net-new, ~300 LOC)
Map introspected facts → `EntityGraph` (entities/fields/enums/fk_parents/joins/uniques).
**Canonical ordering (R1-S7/FR-DC-2):** capture declaration order from `model_fields`, with a
documented stable tiebreak for entity discovery + enum value sets, so output is byte-identical
regardless of import order (precondition of the FR-DC-2 guarantee). The deterministic rules
(verified against navig8):

| Model-side signal | Contract result | Determinism |
|---|---|---|
| explicit `id: str` field present | `<entity>Key` + `@@unique([parentFk, key])` + synth cuid PK | **deterministic** |
| no `id` field | cuid PK only (root/value object: DecisionTree, Citation) | **deterministic** |
| parent has `List[ChildModel]` | child gets `<parent>Id` FK + parent reverse list (1:N) | **deterministic** |
| field is nested `BaseModel` / `Optional[BaseModel]` | `<model>Id` FK (optional mirrors Optional) | **deterministic** |
| `List[scalar]` / `Dict[...]` / nested dict | `Json?` | **deterministic** |
| `@computed_field` / `@property` | excluded (not a column) | **deterministic** |
| Python `Enum` | Prisma `enum`; hyphenated values → underscore + note | **deterministic** |
| `List[str]` of foreign ids (e.g. `screens`) ↔ reciprocal list | **M2M join model** (navig8 `ScreeningLink`) | **NOT deterministic → marker (Step 4) or flag** |
| house meta-fields absent | add `id/ownerId/source/confirmed/createdAt/updatedAt` per SDK convention | deterministic |

### Step 3 — Emit (reuse, ~0 LOC)
`render_prisma_schema(graph)` unchanged. The contract + the derivation report (every rule applied,
every exclusion, every flagged ambiguity — FR-DC-7/8) are the output.

### Step 4 — Ambiguity resolution: markers split by owner + flag-for-human (FR-DC-12, R1-S5/S6)
Two cases, **two mechanisms** (different natural owners), **flag-for-human** when unmarked:
- M2M join (field-local): unmarked `List[str]`-of-ids ⇒ emit `Json?` **and flag** "could be an M2M
  join — mark to confirm"; a minimal **model-side** `Field(json_schema_extra={...})` hint makes it
  a join (refactor-stable on the field).
- exclusion (project curation): a **contract-side sidecar** keyed by FQ class name — a model file
  with zero DB imports can still drive exclusion. Computed fields auto-excluded; pipeline-artifact
  names (`*Verification`/`*Challenge`/`*Sceptic`/`*Arbiter`) **flagged, not auto-dropped**.
- **Orphaned markers (R1-S6):** a marker whose target field/class no longer exists is **reported**,
  never silently ignored (else an orphaned exclusion re-includes an artifact).

### Step 5 — Drift mode `--check` (reuse, ~50 LOC)
Reuse `parity_against_live(graph, live_text)` + the round-trip gate (`prisma_emitter`).
`derive-contract --check`: introspect → map → diff against the live `schema.prisma`, non-zero exit
on drift. **Ratified-ambiguity exclusion (R1-S8):** items the deriver can only *flag* (the M2M the
human ratified into the live contract as `ScreeningLink`) are **excluded from the drift set** — the
re-derivation emits `Json?`+flag, so a naive diff would report perpetual false drift and train
operators to ignore the signal. Drift fires only on genuine model changes. This is the durable
value of mechanizing F-5, so it ships in v1.

### Step 6 — Surfaces (reuse the Concierge pattern)
- `handle_concierge_tool("derive-contract", project_root, models=..., ...)` → preview (the
  proposed contract + report), **never writes** (FR-C3/C3a). Add to the action enum in both MCP
  server files (parity).
- CLI `startd8 concierge derive-contract [ROOT] --models <pkg/paths> [--apply] [--force] [--check]`
  — sole writer (OQ-7), preview-by-default, safe-writer enforces no-clobber/confinement.
- **Candidate, not ratified (R1-S4/FR-DC-7c):** the emitted `schema.prisma` carries a
  `derived-by: derive-contract; status: unratified` provenance header so it is *not*
  byte-indistinguishable from a ratified contract; `--apply` writes a candidate and does **not**
  constitute ratification (a cascade guard may warn if run against an `unratified` contract).

### Step 7 — Tests
- Introspector unit tests against the navig8 models (`tree_models`/`register_models`/`models`).
- **Golden test (two-sided — R1-S3/R1-F5, the circular-bar fix):** freeze an expected
  `{flagged_items}` set; assert **(a)** non-flagged output is AST-equal to the navig8 oracle **AND
  (b)** the deriver's flagged set equals the expected set. A deriver that over- or under-flags must
  fail (a self-derived modulo set would let it pass).
- **Negative golden case (R1-S9):** an unmarked `List[str]`-of-ids field must produce the M2M-join
  flag (with alternatives), not a silent `Json?` — proves the flag-for-human path actually fires.
- **Determinism test (R1-S7):** derive twice in fresh interpreters with shuffled import order;
  assert byte-identical output.
- **Containment test (R1-S1):** a model module with a top-level side effect (sentinel write / socket)
  runs under the subprocess containment, not the host env; timeout aborts cleanly.
- Drift test: mutate a model, assert `--check` reports it; assert **zero** drift on the ratified M2M.
- Disclosure/no-write: the MCP path writes nothing (FR-C3a conformance, as for the other actions).

## 3. Step → Requirement trace

| Step | Requirements |
|------|--------------|
| 1 Introspector | FR-DC-3, FR-DC-2 ($0), FR-DC-10 (importable-env, new) |
| 2 Mapper | FR-DC-4, FR-DC-5 |
| 3 Emit | FR-DC-4, FR-DC-7 |
| 4 Markers/flag | FR-DC-6, FR-DC-8 |
| 5 Drift | FR-DC-11 (--check, promoted from OQ-7) |
| 6 Surfaces | FR-DC-1, FR-C3/C3a/C14, OQ-7 |
| 7 Tests | all |

## 4. Open Questions (for CRP)

- **OQ-DC-1 — Golden-test fidelity.** How close can a re-derivation get to the hand-written navig8
  contract? The flagged items (M2M `ScreeningLink`, the `SequenceConfig` Json bag, house-field
  ordering) won't match byte-for-byte. Is "matches modulo flagged items" the acceptance bar?
- **OQ-DC-2 — Marker shape.** How does a model author mark an M2M join / an excludable artifact —
  a `Field(json_schema_extra={"prisma": ...})`, a `model_config` key, a sidecar YAML, or a
  decorator? (Wants to avoid polluting domain models with contract concerns.)
- **OQ-DC-3 — Import safety.** Runtime import executes the target's module code. Sandbox? subprocess
  isolation? Or document "only point it at code you trust" (consistent with it being the team's own
  models)? Security-relevant — flag for CRP.
- **OQ-DC-4 — Model-set selection ergonomics.** `--models app.models` (package), a glob, or scan
  for `BaseModel` subclasses under a root? Inheritance/imported-model handling.

---

*Plan 0.1 — post-exploration. Net-new surface is bounded (~550 LOC introspector+mapper); emit +
drift + safe-writer are reused. The only non-deterministic derivations (M2M joins, artifact
exclusion) are handled by opt-in markers + flag-for-human, never silent guesses.*

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

> R1 triage (2026-06-16): all 9 S-suggestions ACCEPTED. Strong adversarial review (caught the
> one-sided golden bar, the uncontained import, the unenforceable ratification gate); no noise.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Import containment (subprocess/scrubbed-env/timeout) | R1 | → Step 1 + FR-DC-14 | 2026-06-16 |
| R1-S2 | Partial/failed import aborts | R1 | → Step 1 fail-closed + FR-DC-14 | 2026-06-16 |
| R1-S3 | Two-sided golden bar | R1 | → Step 7 + OQ-DC-1 | 2026-06-16 |
| R1-S4 | `--apply` → candidate + provenance, not cascade input | R1 | → Step 6 + FR-DC-7c/9 | 2026-06-16 |
| R1-S5 | Split marker (model-side hint / sidecar exclusion) | R1 | → Step 4 + FR-DC-12 | 2026-06-16 |
| R1-S6 | Orphaned-marker detection | R1 | → Step 4 + FR-DC-12 | 2026-06-16 |
| R1-S7 | Canonical deterministic ordering | R1 | → Step 2 + FR-DC-2 | 2026-06-16 |
| R1-S8 | `--check` excludes ratified-flagged items | R1 | → Step 5 + FR-DC-11 | 2026-06-16 |
| R1-S9 | Negative golden case (flag fires) | R1 | → Step 7 | 2026-06-16 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | R1 | All R1 suggestions accepted — see Appendix A. | 2026-06-16 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-16

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-16 01:09:15 UTC
- **Scope**: Plan-side review (S-prefix). Weighted per the sponsor focus file: import safety (OQ-DC-3, Step 1/§4), marker shape (OQ-DC-2, Step 4/§4), golden-test fidelity (OQ-DC-1, Step 7/§4), assist-posture integrity (Step 6). Adversarial pass + Requirements Coverage Matrix appended after this round.

##### Executive summary

- **Step 1's import constraint is one sentence of prose for a critical security boundary** ("runs in an env where the target package imports cleanly… Side-effect risk is documented") — no containment design, no failure-mode handling.
- **Step 7's golden test is one-sided** — "matches modulo flagged-ambiguity items" can pass a mis-flagging deriver because the modulo set is self-derived.
- **Step 6's `--apply` writes the cascade's input artifact** with no staging/provenance gate between derivation and ratification.
- **Step 4 leaves marker shape fully open** and uses one mechanism for two cases with different natural owners.
- **Step 2's determinism table assumes stable ordering** that the plan never specifies (import order, `model_fields` order).
- **Step 5 `--check` will false-positive on ratified ambiguities** the deriver can only flag, not derive — undermining its stated durable value.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | critical | Step 1: add an import-containment design substep — run introspection in a subprocess with a scrubbed env (no inherited secrets), bounded timeout, and an explicit network-egress posture; the report records the containment used. | Step 1's "Constraint (new, FR-DC-10)" documents that "importing the models executes module code" but ships no control. A general Concierge action will be pointed at less-trusted brownfield repos; top-level import code runs with operator privileges. | Step 1, after the FR-DC-10 constraint paragraph | Integration test: a model module with a top-level side effect (sentinel-file write / socket open) executes under containment, not against the host env; timeout aborts cleanly. |
| R1-S2 | Risks | high | Step 1/Step 2: specify that a failed or partial import aborts the run (non-zero exit, no contract emitted) rather than mapping whatever subset imported. | The plan's import-set recording implies best-effort import; a partial model set silently produces a wrong-but-plausible contract (missing entities/relations). | Step 1 constraint paragraph; Step 2 entry conditions | Test: one model in the set raises on import → run aborts, emits no `schema.prisma`. |
| R1-S3 | Validation | high | Step 7 golden test: make the acceptance bar two-sided — freeze an expected flagged-item set and assert (a) non-flagged output is AST-equal to the navig8 oracle AND (b) the deriver's flagged set equals the expected set. | "assert it matches… modulo the flagged-ambiguity items" subtracts a modulo set computed from the output under test, so a deriver that over- or under-flags still passes — the exact silent divergence OQ-DC-1 worries about. | Step 7, "Golden test" bullet | Mutate the deriver to over-flag one field; the strengthened golden test must fail. |
| R1-S4 | Architecture | high | Step 6: `--apply` should write to a staging/candidate path (or write the canonical path only with a "derived/unratified" provenance header), not silently produce the artifact the cascade consumes. | Step 6 makes the CLI "sole writer, preview-by-default," but once written, `schema.prisma` is byte-indistinguishable from a ratified contract and the cascade reads it by path — the ratification gate is unenforceable prose. | Step 6 CLI bullet | Test: after `--apply`, the artifact carries the provenance marker / lands in staging; a cascade-guard can detect "unratified". |
| R1-S5 | Interfaces | medium | Step 4: resolve the marker shape as two mechanisms — model-side `Field(json_schema_extra)` for the field-local M2M-join hint, contract-side sidecar (FQ-class-keyed) for artifact exclusion. | Step 4 lists four candidate shapes for both cases uniformly (OQ-DC-2). Exclusion is a project-curation decision that should not touch domain models; M2M intent is field-local. | Step 4, M2M + exclusion bullets | Acceptance: exclusion works with zero DB imports in model files; M2M hint survives a field rename. |
| R1-S6 | Ops | medium | Step 4/Step 7: require the deriver to detect and report orphaned markers (a marker whose target field/class no longer exists after a refactor). | Markers "survive refactors and stay discoverable" (focus file) is unaddressed; an orphaned exclusion marker silently re-includes a pipeline artifact. | Step 4 marker handling | Test: rename a marked class; run reports the orphaned marker rather than ignoring it. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Data | high | Step 2/Step 3: mandate a canonical deterministic ordering for entity discovery, field emission, and enum value sets (capture declaration order from `model_fields`; stable tiebreak), and state it as a precondition of the FR-DC-2 byte-identical guarantee. | The Step 2 rules table is "deterministic" only if ordering is fixed; subclass discovery and `model_fields`/set iteration can vary by import order, breaking both FR-DC-2 and the Step 7 golden test intermittently. | Step 2 preamble; Step 3 | Run derivation twice in fresh interpreters with shuffled import order; assert byte-identical `schema.prisma`. |
| R1-S8 | Risks | medium | Step 5 `--check`: define how drift is computed for items the deriver can only *flag* (M2M) when the live contract holds the human-ratified resolution — exclude ratified flagged items from the drift set or `--check` reports perpetual false drift. | Step 5 reuses `parity_against_live` against a live contract that legitimately contains `ScreeningLink`; the re-derivation emits `Json?`+flag, so a naive diff always reports drift, training operators to ignore the signal and defeating Step 5's "durable value." | Step 5 body | Run `--check` against the live navig8 contract; assert zero drift on the ratified M2M, drift only on genuine model changes. |
| R1-S9 | Validation | low | Step 7: add a negative golden case — a model that *should* trigger a flag (an unmarked `List[str]`-of-ids) and assert the deriver flags rather than silently emits `Json?` without the flag. | Step 7 tests the happy re-derivation but not that the flag-for-human path actually fires; a silent `Json?` with no flag is the assist-posture failure (the human never sees the ambiguity). | Step 7, new test bullet | Test: unmarked id-list field → report contains the M2M-join flag with alternatives. |

*(No endorsements/disagreements — R1 is the first round; Appendix C had no prior untriaged items.)*

---

## Requirements Coverage Matrix — R1

Analysis only (no triage). Maps each requirement to the plan step(s) addressing it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-DC-1 (5th action, MCP preview-only, CLI sole writer, ratification posture) | Step 6 | Partial | Ratification posture is asserted but not made enforceable; `--apply` writes the cascade's input with no staging/provenance gate (R1-S4, R1-F6/F7). |
| FR-DC-2 ($0, deterministic, byte-identical) | Step 2, Step 3 | Partial | Determinism guarantee assumes an ordering the plan never specifies (R1-S7, R1-F9). |
| FR-DC-3 (input = Pydantic models, IR) | Step 1 | Partial | Inherited/imported/transitive `BaseModel` subclass handling unstated (R1-F8); overlaps OQ-DC-4. |
| FR-DC-4 (produce EntityGraph IR; reuse emitter) | Step 2, Step 3 | Full | OQ-1 resolved feasible; emit half reused as-is. |
| FR-DC-5 (transform rules) | Step 2 | Full | Deterministic rules verified against navig8; M2M correctly carved out to FR-DC-12. |
| FR-DC-6 (explicit exclusions, never silent) | Step 4 | Partial | Marker mechanism for exclusion unresolved (R1-S5/R1-F3); orphaned-marker detection missing (R1-S6/R1-F4). |
| FR-DC-7 (emit contract + derivation report) | Step 3 | Partial | No provenance/"unratified" marker on the emitted contract (R1-F6/R1-S4). |
| FR-DC-8 (flag ambiguity, never guess) | Step 4 | Partial | No test that the flag actually fires on an unmarked id-list (R1-S9). |
| FR-DC-9 (no clobber; validate via wireframe) | Step 6, Step 7 | Partial | Re-validation via `wireframe` is named in the requirement but not called out as a Step (only no-clobber is); staging gate missing (R1-S4). |
| FR-DC-10 (runtime import; importable env) | Step 1 | Partial | Threat model / containment / partial-import failure mode unspecified (R1-S1, R1-S2, R1-F1, R1-F2). |
| FR-DC-11 (`--check` drift mode) | Step 5 | Partial | False-positive drift on ratified-but-only-flaggable items undefined (R1-S8, R1-F10). |
| FR-DC-12 (markers for non-deterministic derivations) | Step 4 | Partial | Marker shape open (OQ-DC-2); split-by-case + refactor-survival criteria missing (R1-S5/S6, R1-F3/F4). |
| FR-DC-13 (model-set selection) | Step 6 | Partial | Selection ergonomics open (OQ-DC-4); transitive-inclusion guard unstated (R1-F8). |
