# Persona Format & Ingestion Implementation Plan

**Version:** 1.1 (Post-CRP — convergent review R1/R2 applied)
**Date:** 2026-07-02
**Tracks requirements:** `PERSONA_FORMAT_AND_INGESTION_REQUIREMENTS.md` v0.3
**Status:** Planned (pre-implementation)

---

## 0.5 CRP R1/R2 deltas (v1.1)

> 13 plan suggestions applied. These amend the sections below; read together. Dispositions in
> Appendix A.

- **Interfaces / return type (R1-S1).** `ingest(format, source_text) -> IngestResult` (single
  contract): `IngestResult` carries `roster`, `yaml_text` (with the FR-7 header prepended), and
  `warnings` (from `AdaptResult`). §1's `-> Roster` row and §4's `(roster, yaml_text)` are reconciled
  to this one shape. Adapters return `AdaptResult{roster, warnings}` (req FR-3).
- **Error taxonomy / exceptions (R2-S2, req FR-9).** `RosterError` = structural/schema (FR-2);
  `AdapterError` = unknown format / malformed source / **round-trip-gate reparse failure inside
  `ingest`** (a reparse failure is an *adapter bug*, wrapped as `AdapterError`, never a bare
  `RosterError`); content findings = typed advisory list. §2/§3/§4 raise accordingly; the §4 CLI maps
  each to a distinct message + **exit code (R2-S1 plan / req FR-6)**.
- **Registry trust/isolation (R1-S2).** §3 `discover()`: a raising entry point is **skipped-and-
  warned** (never aborts discovery); **built-in wins** a name collision; `--format` is the sole trust
  gate (arbitrary third-party code runs at discover/adapt).
- **Strict parser (R1-S4/R2-S4).** §2: give `protocol_version` real semantics (major-reject /
  minor-warn, req FR-2); derive the per-persona allow-set from `PersonaBrief` fields; and add the
  **shipped-template golden** — the literal `_KICKOFF_FILES` template + Concierge-projected bytes must
  parse clean under `parse_roster`, run in **N0 alongside the M0 byte-identity test** (reconcile
  allow-set vs frozen bytes within N0).
- **Soft-vs-blocking (R1-S7).** §4 gate: `validate_roster` findings **abort `ingest`** (block at
  import), matching req FR-3.
- **Determinism vs header (R1-S5).** §4/§6: FR-7 header records a **basename/normalized** source
  token; §6 determinism test asserts byte-identity on the roster **body** across differing absolute
  paths.
- **role-rubric input guard + lazy-load (R1-S6/R2-F4).** §3: the adapter rejects a malformed
  `reviewer_roles.yaml` (missing `key/label/rubric`) with a clear `AdapterError`; and it is
  **lazily loaded** (asserted: importing `stakeholder_panel` / `load_roster` does not import the
  adapter — check `sys.modules`).
- **Doc-sync (R2-S3).** §5/§6: a test asserts `ROSTER_SCHEMA.md` field list == `PersonaBrief` fields
  == FR-2 allow-set (build fails on divergence).
- **Sequencing (R2-S1/R2-S5).** §7: state validation responsibility across **N1/N2** (adapter
  validates at its boundary *and* `ingest` re-gates = documented defense-in-depth; N1 is *not*
  independently ship-able as a writer without N2's gate); **N3 retirement gated on a parity test**
  (SDK `role-rubric` output ≡ the one-off `reviewer_roles_to_roster.py`, or a documented intentional
  diff) before redirecting the benchmark script.
- **Clobber guard (R1-S8).** §4: `import` warns + requires confirmation when `--out` lacks a
  `GENERATED` header even under `--force`.
- **Deferred (R1-S3, in part).** The transitional warn-only strict-mode flag is **not** built (feature
  unreleased, no external rosters) — see requirements Appendix B. The audit + golden half **is** in N0.

## 0. Grounding: what the infra survey established

- **`manifest_extraction/` engine is NOT reusable** — hard-wired to the buildable-app grammar
  (imports `backend_codegen`/`view_codegen`/`languages.prisma_parser`; `EntityGraph` is a Prisma IR;
  the candidate/round-trip file set is a fixed literal). Do **not** enroll the roster (reaffirms panel
  OQ-1). Its **`Status`/`SourceRef`/`ExtractionRecord`** dataclasses (`models.py`) are the only
  liftable pieces — and we decline to lift them for v1 (see OQ-6).
- **`kickoff_inputs/` is the rail to mirror.** Uniform contract: `parse_X(text) -> frozen Manifest`,
  a `domain:` discriminator, **loud-fail `ValueError` on non-mapping root / wrong domain / unknown
  top-level key** (`conventions.py:117`, `business_targets.py:100`). No registry — dispatch is the
  literal `round_trips` dict in `extract.py`, which we do not touch.
- **`concierge/derive/` is NOT reusable** — Pydantic→Prisma relational derivation; a roster has no
  entities. Only its "unratified candidate + report, CLI-sole-writer" *ceremony* transfers as an idea.
- **No adapter registry exists**, but the **entry-point idiom does** — `providers/registry.py:131`,
  `workflows/registry.py:155`, `secrets/registry.py:55` all use `importlib.metadata.entry_points(group=…)`
  with an old-Python fallback. Mirror it; do not invent a mechanism.
- **Template plumbing is done** — the roster is already in `_KICKOFF_FILES` (`writes.py:41`),
  download-manifest-derived, and inside the byte-identity test. "Formalize" ≠ new plumbing.
- **The gap is validation rigor + ingestion**: `Roster.from_dict` is permissive/coercive
  (`models.py:40,123`) — no typo guard — whereas the pilot converter (`reviewer_roles_to_roster.py`)
  is an untested out-of-SDK script that hand-writes YAML instead of round-tripping `Roster`.

## 1. Module layout

| File | Responsibility | Requirements |
|------|----------------|--------------|
| `stakeholder_panel/roster.py` (extend) | `parse_roster(text)` — strict structural gate (peer to `kickoff_inputs`), then delegate to `Roster.from_dict` + `validate_roster`. `load_roster` adopts it. | FR-2 |
| `stakeholder_panel/adapters/__init__.py` | Adapter protocol (`name`, `adapt(text)->Roster`) + registry (`discover()`, `get_adapter()`, `available()`) — copied from `providers/registry.py` | FR-3, FR-4 |
| `stakeholder_panel/adapters/role_rubric.py` | The generic `role-rubric` adapter (promoted `convert()`), emitting a **validated** `Roster` | FR-5 |
| `stakeholder_panel/ingest.py` | `ingest(format_name, source_text) -> Roster`: run adapter → serialize → **reparse via `parse_roster` (round-trip gate)** → return; stamp provenance | FR-3, FR-6, FR-7, OQ-7 |
| `cli_panel.py` (extend) | `startd8 panel import --format <name> <src> [--out] [--force]` | FR-6 |
| `docs/design/stakeholder-panel/ROSTER_SCHEMA.md` | Authoritative persona-format schema reference | FR-1 |
| `pyproject.toml` | entry-point group `startd8.stakeholder_panel.roster_adapters` with `role-rubric` | FR-4, FR-5 |

## 2. FR-2 — strict roster parser (resolves OQ-1/OQ-2)

- **OQ-1 → stays in `stakeholder_panel/roster.py`** (not moved to `kickoff_inputs/`): keeps the panel
  self-contained (M0 principle); we copy the *contract*, not the package. `manifest_extraction`'s
  `round_trips` dict is untouched (the roster is not an app manifest).
- **OQ-2 → strict document structure, coerced field elements.** `parse_roster(text)`:
  1. `yaml.safe_load` → must be a mapping (else `RosterError`).
  2. `domain` must equal `"stakeholders"` (discriminator, else `RosterError`).
  3. Reject **unknown top-level keys** (allow-set: `domain`, `provenance_default`, `personas`,
     `protocol_version`) and **unknown per-persona keys** (allow-set = `PersonaBrief` fields) — the
     typo guard.
  4. Then `Roster.from_dict` (unchanged coercion of element types) + return.
  `load_roster` calls `parse_roster` (so structural strictness is the default); `validate_roster`
  still does the **soft field-level** reporting (unique ids, required fields, non-empty briefs).
  `assess_roster` already catches `RosterError` → reports `invalid` gracefully (no change needed).
- Back-compat: valid rosters (template + pilot output) use only known keys, so nothing breaks; the
  M0 "permissive" note in the panel requirements is updated.

## 3. FR-3/FR-4/FR-5 — adapter + registry (resolves OQ-3/OQ-4)

- **OQ-3 → adapter = `adapt(text: str) -> Roster`** (mirrors `parse_X(text)`; text not path/dict, so
  the CLI owns file I/O). Entry-point group **`startd8.stakeholder_panel.roster_adapters`**
  (namespaced like `startd8.contractors.deterministic_providers`).
- **OQ-4 → `role-rubric` lives in SDK core** as a built-in adapter — the
  `key/label/lens/rubric/coverage/out_of_scope` shape is a generic format family, not benchmark-
  specific. Named `role-rubric`.
- Registry mirrors `providers/registry.py`: module-level cache, `discover()` (entry points + built-ins),
  `get_adapter(name)` (→ clear error listing `available()` on miss), `register()` for tests.
- `role_rubric.adapt` = the pilot `convert()` mapping, but building `PersonaBrief`/`Roster` objects
  directly and returning the `Roster` (no `yaml.safe_dump`); the CLI serializes once, at the end.

## 4. FR-6/FR-7 — ingestion + surface (resolves OQ-5/OQ-6/OQ-7)

- **OQ-5 → `startd8 panel import`** subcommand (panel CLI is the writer surface, NR-7/OQ-7 of the
  panel spec). Signature: `--format <name>` (required), `SOURCE` path (arg), `--out` (default
  `docs/kickoff/inputs/stakeholders.yaml` under `--project`), `--force` (refuse clobber otherwise).
- **`ingest(format_name, source_text)`** (in `ingest.py`): `get_adapter(name).adapt(text)` → `Roster`
  → `yaml.safe_dump(roster.to_dict())` → **`parse_roster(dumped)` + `validate_roster`** (OQ-7
  round-trip gate: an adapter that emits a bad roster fails loudly here, not at panel-load time) →
  return `(roster, yaml_text)`.
- **OQ-6 → header-level provenance only** (FR-7). Prepend `# GENERATED from <source> via <format>
  adapter — edit the source, re-run import`. No per-field `ExtractionRecord` (ingestion maps a whole
  structured file, not prose; per-field traceability is overkill). `manifest_extraction/models.py`
  stays unlifted.
- **OQ-7 → yes, round-trip gate** (above).

## 5. FR-1 — schema reference

Write `ROSTER_SCHEMA.md`: the `PersonaBrief` fields (role_id rules, display_name, goals, constraints,
known_positions, out_of_scope, answers_for) + `Roster` envelope (`domain`, `provenance_default`,
`personas`) + the strict-parse rules (FR-2) + "how to target this from an external tool." Cross-link
from the template header and `reviewer_roles.yaml`'s "panel-consumable" note.

## 6. Test plan

- `parse_roster`: strict rejects unknown top-level key, unknown persona key, wrong `domain`, non-
  mapping root; accepts the shipped template + a valid roster; still coerces scalar→list fields.
- registry: `discover()` finds the built-in `role-rubric`; `get_adapter("nope")` errors with the
  available list; `register()` works for a fake adapter.
- `role-rubric` adapter: converts a `reviewer_roles.yaml` fixture → validated `Roster` with the exact
  field mapping (incl. `out_of_scope` pass-through and `answers_for` = rubric names); round-trips
  through `parse_roster` cleanly.
- `ingest`: round-trip gate rejects an adapter that emits an invalid roster; provenance header
  present; deterministic output (same input → byte-identical roster).
- CLI: `panel import --format role-rubric <fixture> --out <tmp>` writes a valid roster; `--force`
  clobber guard; unknown `--format` lists adapters; then `panel list <tmp-project>` succeeds ($0).
- Regression: existing M0–M3 roster/panel tests still green (strict parse must not break valid input).

## 7. Sequencing

- **N0** — `parse_roster` strict gate + `ROSTER_SCHEMA.md` (formalization; no new deps). Updates the
  panel spec's "permissive" note. Ship-able alone.
- **N1** — adapter protocol + registry + `role-rubric` built-in + entry point (ingestion core, no CLI).
- **N2** — `ingest.py` round-trip gate + `startd8 panel import` CLI + provenance header.
- **N3** — (optional) retire/redirect the benchmarking one-off script to call `startd8 panel import`;
  add a fixture from `reviewer_roles.yaml`.

Each increment branch-first, tested, lint-clean before the next.

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
| R1-S1 | Reconcile `ingest` return type (`->Roster` vs tuple) | R1 | Applied → §0.5: `ingest -> IngestResult{roster, yaml_text, warnings}` | 2026-07-02 |
| R1-S2 | Registry trust/isolation (failure-isolation, precedence, trust boundary) | R1 | Applied → §0.5 + §3 | 2026-07-02 |
| R1-S3 (part) | Back-compat audit before strict `load_roster` | R1 | Applied-in-part → shipped-template audit+golden in N0 (§0.5/§2). Transitional flag deferred (see B). | 2026-07-02 |
| R1-S4 | Assign `protocol_version` semantics or drop | R1 | Applied → §2 forward-compat (major-reject/minor-warn) | 2026-07-02 |
| R1-S5 | Determinism vs path-bearing header | R1 | Applied → §4/§6 normalized basename token; body-only determinism test | 2026-07-02 |
| R1-S6 | role-rubric input-shape guard | R1 | Applied → §3 adapter rejects malformed source | 2026-07-02 |
| R1-S7 | Round-trip gate rejects on soft findings | R1 | Applied → §4 gate blocks at ingest | 2026-07-02 |
| R1-S8 | Warn on clobber of hand-authored roster | R1 | Applied → §4 GENERATED-header clobber guard | 2026-07-02 |
| R2-S1 | Pin N1/N2 validation-location | R2 | Applied → §0.5/§7 defense-in-depth documented | 2026-07-02 |
| R2-S2 | Exception hierarchy across §2/§3/§4 | R2 | Applied → §0.5 (RosterError vs AdapterError; gate failure = adapter bug) | 2026-07-02 |
| R2-S3 | Doc-sync test for ROSTER_SCHEMA.md | R2 | Applied → §5/§6 field-set equality test | 2026-07-02 |
| R2-S4 | Golden: shipped template parses under new gate (M0 byte-identity collision) | R2 | Applied → §2/§6, run in N0 | 2026-07-02 |
| R2-S5 | Gate N3 retirement on adapter-vs-one-off parity | R2 | Applied → §7 N3 parity test | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S3 (part) | Transitional warn-only strict-mode / env flag | R1 | Deferred, not v1 (mirrors requirements Appendix B): the panel is unreleased/unmerged, so no external on-disk rosters exist to protect — only the SDK's own template + pilot output, reconciled in N0. Revisit only if strict-parse ships after real downstream rosters exist. | 2026-07-02 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 16:10:00 UTC
- **Scope**: Plan-side review — module layout (§1), strict parser (§2), adapter+registry (§3), ingestion surface (§4), test plan (§6), sequencing (§7). Focus per orchestrator brief: strict/permissive reconciliation, round-trip gate, adapter-registry trust, provenance, forward-compat.

**Executive summary**

- §1 module table declares `ingest(...) -> Roster` but §4 says `return (roster, yaml_text)` — a self-contradiction in the plan's core interface.
- §3 registry mirrors `providers/registry.py` but inherits **none of the trust reasoning**: third-party adapter entry points execute arbitrary code at `discover()`; no failure-isolation, name-collision precedence, or trust boundary is stated.
- §2 makes `load_roster` strict-by-default with a bare "nothing breaks" assertion and no audit of already-on-disk rosters or deprecation window — a silent break risk for M0/M1/M2 consumers.
- §2 admits `protocol_version` into the allow-set but never assigns it semantics — the format looks versioned but the strict guard makes it un-evolvable.
- §6's "byte-identical output" determinism test collides with FR-7's header, which embeds `<source>` (a path) — determinism breaks across machines/working dirs.

**Numbered suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | high | Reconcile the `ingest` return type: §1 module-layout row says `ingest(format_name, source_text) -> Roster`; §4 says "return `(roster, yaml_text)`". Pick one signature and make the CLI (§4) and provenance-header prepend consistent with it (the header must be added to `yaml_text`, so the tuple form is likely correct — but say so once). | A contradicted signature in the plan will produce a mismatched implementation + tests; the header-stamping step needs the serialized text, which the `-> Roster` form doesn't return. | §1 (`ingest.py` row) and §4 (ingest bullet) | Type-check the signature against callers; test asserts the returned yaml_text carries the FR-7 header. |
| R1-S2 | Security | high | Add a trust/isolation spec for the FR-4 registry (§3): (a) **failure isolation** — a broken/raising third-party entry point must be skipped-and-warned, not abort `discover()` for all adapters; (b) **name-collision precedence** — define whether a built-in (`role-rubric`) or an entry-point of the same name wins; (c) acknowledge that entry points **execute arbitrary third-party code** at discover/adapt time and that named-`--format` invocation (NR-4) is the only trust gate. | `providers/registry.py` is mirrored for mechanism but its entry points are SDK-authored/trusted; a downstream roster adapter is not. One malformed entry point currently could break discovery of the built-in adapter, and a shadowing name is undefined behavior. | §3 (registry bullet "discover() (entry points + built-ins)") | Tests: a raising entry point is skipped with a warning and built-ins still resolve; a duplicate-named entry point resolves per the documented precedence. |
| R1-S3 | Risks | high | Before making `load_roster` strict-by-default (§2), add a back-compat step: audit existing on-disk rosters (template + pilot + any downstream `stakeholders.yaml`) for now-illegal keys, and provide a migration/deprecation path (e.g. a transitional warn-only mode or `STARTD8_ROSTER_STRICT` flag) rather than an immediate hard `RosterError`. | §2's "valid rosters use only known keys, so nothing breaks" is an unverified assertion; `assess_roster` degrades gracefully but `load_roster` will now *raise*, so any real roster with a stray key (comment-key, prior provenance field) breaks panel load with no migration window. | §2 (back-compat bullet) and §7 (N0) | Regression test over a corpus of real rosters; test a warn-only transitional mode if adopted. |
| R1-S4 | Data | medium | Assign `protocol_version` real semantics in §2 step 3 or drop it from the allow-set: define the current version value, and the older-SDK-reads-newer-version policy (reject vs warn vs relax-key-strictness). Right now it is admitted but never read. | An allow-listed-but-ignored version field is a forward-compat trap: it signals evolvability the strict unknown-key guard forbids. Decide now, cheaply, since the allow-set is being written anyway. | §2 (step 3 allow-set: `protocol_version`) | Test: roster with current `protocol_version` parses; roster with a newer version is handled per policy. |
| R1-S5 | Validation | medium | Fix the determinism claim in §6: FR-7's header embeds `<source>`; if `<source>` is a filesystem path the output is **not** byte-identical across machines/working dirs. Specify that the header records a **normalized/basename** source token (or that determinism is asserted on the roster body excluding the header). | §6 asserts "same input → byte-identical roster" while §4 prepends a path-bearing header — the two cannot both hold for absolute paths. | §6 (ingest test bullet) and §4 (OQ-6 header) | Test: same source under two different absolute paths yields byte-identical roster bodies (header normalized). |
| R1-S6 | Interfaces | medium | Add a `role-rubric` version/shape guard to §3: the adapter should reject a `reviewer_roles.yaml` that is missing expected keys (`key/label/lens/rubric/coverage/out_of_scope`) or of an unexpected shape, with a clear error, rather than silently producing a thin roster. The strict gate is on the *output* roster; nothing validates the *input* format. | Ingestion validates the emitted roster (FR-3) but the source-side has no schema check; a malformed `reviewer_roles.yaml` maps to an under-populated-but-structurally-valid roster that passes the round-trip gate. | §3 (`role_rubric.adapt` bullet) | Test: a `reviewer_roles.yaml` missing `rubric` yields a clear adapter error, not a silent empty `known_positions`. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Risks | medium | Clarify in §4 whether the round-trip gate **rejects** on soft `validate_roster` findings. §4 runs `parse_roster(dumped) + validate_roster` as the gate, but §2 defines `validate_roster` as soft-reporting; state explicitly whether a duplicate-id or empty-brief finding aborts `ingest` (recommended: yes, at import time) or is merely printed. | If soft, the gate lets semantically-broken rosters through and only surfaces them as advisory text — undermining the "fail loudly at import time" goal. This is the plan-side twin of requirements R1-F3. | §4 (ingest bullet, round-trip gate) | Test: ingest of a source producing duplicate `role_id`s fails (or warns) per the documented decision. |
| R1-S8 | Ops | low | §4/§6: the default `--out docs/kickoff/inputs/stakeholders.yaml` is the exact file the panel loads and one a user may have hand-authored. Beyond the `--force` clobber guard, note the interaction: `import` overwrites hand edits (one-way, NR-5), and FR-7's "edit the source, re-run import" assumes the roster is disposable. Recommend `import` warn when the target lacks a GENERATED header (i.e. looks hand-authored) even under `--force`. | Prevents silent loss of a hand-authored roster when someone runs `import` against the default path. | §4 (`--out` default) and §6 (CLI test) | Test: `import` onto a header-less existing file warns/requires an extra confirmation; onto a GENERATED file proceeds. |

**Endorsements & Disagreements**

- No prior untriaged rounds exist (R1 is the first round in both documents), so there is nothing to endorse or dispute yet.

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 16:40:00 UTC
- **Scope**: Second-round plan review. Avoiding R1-S1..S8. Per orchestrator brief: **sequencing/dependency realism** across N0→N3 (§7), **testability of the strict-parse cases and registry failure-isolation** (§6), the **error-taxonomy** the plan's exception surface lacks (§2/§3/§4), `ROSTER_SCHEMA.md` as a **drift liability** (§5), and whether the **shipped template is guaranteed to pass its own new gate** (§2/§6/§0).

**Executive summary**

- **N1/N2 validation-location is under-sequenced.** §7 N1 ships the `role-rubric` adapter "returning a validated `Roster`", but §4's round-trip gate is N2 — so either N1 validates (duplicating N2's gate) or N1 ships an adapter that can emit un-gated rosters. The plan never says which, yet claims N1 is a coherent increment.
- **No exception hierarchy.** §2 raises `RosterError`, §3's `get_adapter` raises a "clear error", `role_rubric.adapt` may raise, and §4's gate re-raises `RosterError` from the *reparse* — conflating "adapter bug" with "malformed roster." The CLI (§4) has no distinct surface for these.
- **`ROSTER_SCHEMA.md` (§5) is hand-written** and restates `PersonaBrief` fields + the FR-2 allow-set with no §6 sync test — guaranteed drift.
- **The shipped template is not asserted to pass the new strict gate.** §6 says "accepts the shipped template" but the M0 byte-identity guard freezes those exact bytes; if the template carries any key now outside the allow-set, N0 breaks the byte-identity test — an untracked cross-increment regression.
- **N3 can silently change benchmark inputs.** Retiring `reviewer_roles_to_roster.py` (§7 N3) with no parity test means the SDK adapter's output may differ from the one-off's, altering what the benchmark ingests.

**Numbered suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | medium | Pin down **where roster validation lives across the N1→N2 boundary** (§7): if the `role-rubric` adapter (N1) must "return a validated `Roster`", state whether it calls `validate_roster` itself (N1) — in which case N2's `ingest` round-trip gate is a *second* check and their relationship (defense-in-depth vs redundant) must be documented — or whether N1 ships un-gated and is therefore *not* independently ship-able as §7 implies only N0 is. | §7 asserts increment boundaries but the validation responsibility straddles N1 and N2; an implementer will either double-validate or leave an N1 gap. This is a sequencing-realism issue R1 did not touch. | §7 (N1 and N2 bullets); §3 (`role_rubric.adapt` "returning the `Roster`") | Test: N1's adapter output is validated at the adapter boundary *and* re-gated by N2's `ingest`; document the two layers explicitly. |
| R2-S2 | Interfaces | high | Define the plan's **exception hierarchy** in §2/§3/§4: `RosterError` for structural/schema faults; a distinct registry/adapter error (unknown format, source malformed); and make clear that §4's round-trip-gate failure — currently a re-raised `RosterError` from the reparse — is *semantically* an adapter-bug, not a user-roster fault, and should be surfaced as such (e.g. wrapped as an `IngestError`/`AdapterError`). The §4 CLI must map these to distinct messages/exit codes. | The plan reuses one error type for structural rejection *and* for gate rejection of an adapter's output, so the CLI cannot tell the user "fix your source" vs "the adapter is broken." Plan-side twin of R2-F1. | §2 (`RosterError`), §3 (`get_adapter` error), §4 (round-trip gate) | Test: reparse-failure inside `ingest` surfaces as an adapter-attributed error distinct from a user-supplied malformed roster's `RosterError`. |
| R2-S3 | Validation | medium | Add a **doc-sync test** to §6 (and note it in §5): assert `ROSTER_SCHEMA.md`'s enumerated field set equals `PersonaBrief` fields and the §2 allow-set, failing the build on divergence. Right now §5 hand-authors the schema and §6 has no test that keeps it honest. | A hand-written schema doc silently drifts from the model; external tools targeting the doc then emit rosters the strict gate rejects. Plan-side of R2-F2. | §5 (`ROSTER_SCHEMA.md`) and §6 (test plan) | Test: doc field list == `PersonaBrief` fields == allow-set. |
| R2-S4 | Validation | high | Add an explicit **golden** to §6: the *exact* `_KICKOFF_FILES` template bytes (`writes.py:41`) and the Concierge-projected roster parse clean under the **new** `parse_roster`. Call out the M0 interaction: because byte-identity freezes those bytes, if the template contains any key now outside the FR-2 allow-set, N0 simultaneously breaks the M0 byte-identity test — so the allow-set and the shipped bytes must be reconciled *within* N0. | §6's "accepts the shipped template" is generic; the real risk is a cross-increment collision between the new strict gate and the frozen M0 bytes. Making the shipped template a self-passing golden closes it. | §6 (`parse_roster` test bullet); §2 (back-compat bullet); §0 (`writes.py:41`) | Test: parse the literal template/download bytes under `parse_roster` → clean; run alongside the existing M0 byte-identity test in N0. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S5 | Risks | medium | Gate the N3 retirement (§7) on a **parity test**: before redirecting/retiring `reviewer_roles_to_roster.py`, assert the SDK `role-rubric` adapter's output on the *real* `reviewer_roles.yaml` is equivalent (semantically, or "the benchmark still ingests it") to the one-off's output. | N3 swaps the producer of a benchmark input; without a parity check the SDK adapter may map fields differently (see R1-F5's unresolved `rubric` split) and silently change what the benchmark consumes. Sequencing realism: N3 depends on N1's mapping being *proven* equivalent, not merely present. | §7 (N3 bullet); §6 (add fixture-parity test) | Test: `adapter(reviewer_roles.yaml)` vs `reviewer_roles_to_roster.py` output — assert equivalence (or a documented, intentional diff) before retirement. |

**Endorsements** (prior untriaged R1 items this reviewer independently agrees with):
- R1-S1 — the `ingest` return-type contradiction (`-> Roster` vs `(roster, yaml_text)`) is a genuine blocker; my R2-S2 assumes the tuple form so the header can be stamped onto the serialized text.
- R1-S2 — registry trust/isolation: third-party entry points execute arbitrary code at `discover()`. My R2-S2 taxonomy complements it (how failures are *typed*), but R1-S2's *isolation* (one bad adapter must not break discovery) is the load-bearing half.
- R1-S5 — the determinism-vs-path-header collision is concrete and correct; it should be triaged together with R2-S4 (both concern what bytes the golden/determinism tests assert over).

---

## Requirements Coverage Matrix — R1

Analysis only (informs orchestrator triage). Maps each requirement/non-requirement to the plan section(s) that address it.

| Requirement | Plan Section(s) / Task | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (schema reference doc) | §1 (`ROSTER_SCHEMA.md` row), §5, §7 N0 | Covered | — |
| FR-2 (strict roster parser gate) | §1 (`roster.py` row), §2, §7 N0 | Partial | `protocol_version` semantics undefined (R1-S4/R1-F2); per-persona allow-set drift risk (R1-F7); no back-compat audit for strict `load_roster` (R1-S3). |
| FR-3 (adapter contract + round-trip gate) | §1 (`ingest.py` row), §3, §4, §7 N1/N2 | Partial | Gate is structural-only, not semantic (R1-F1); soft-vs-blocking validation undefined (R1-F3/R1-S7); `ingest` return type contradicted (R1-S1). |
| FR-4 (pluggable adapter registry) | §1 (`adapters/__init__.py` row), §3, §7 N1 | Partial | No failure isolation / name-collision precedence / trust-boundary spec for third-party entry points (R1-S2). |
| FR-5 (role-rubric built-in adapter) | §1 (`role_rubric.py` row), §3, §6, §7 N1 | Partial | `rubric→known_positions+answers_for` split has no acceptance criterion (R1-F5); no input-format shape guard (R1-S6). |
| FR-6 (CLI ingestion surface) | §1 (`cli_panel.py` row), §4, §6, §7 N2 | Partial | Default `--out` clobber-of-hand-authored interaction (R1-S8). |
| FR-7 (ingested-roster provenance header) | §4, §5, §7 N2 | Partial | Header is advisory-not-load-bearing but framed as durable (R1-F4); breaks §6 byte-identity determinism (R1-S5). |
| FR-8 (reuse decision) | §0 (grounding survey) | Covered | — |
| NR-1..NR-3 (no grammar / no NLP / no derive) | §0, §2 | Covered | — |
| NR-4 (no auto-detect) | §4 (`--format` required) | Covered | Note: `--format` is also the only trust gate for arbitrary adapter code (R1-S2). |
| NR-5 (one-way only) | §4 | Covered | Interaction with default-path overwrite flagged (R1-S8). |
| NR-6 (no new template plumbing) | §0, §7 | Covered | — |
| NR-7 (no downstream coupling) | §3 (format-family naming) | Covered | — |
| OQ-8 (retire one-off script) | §7 N3 (optional) | Covered | Deferred by design. |
| OQ-9 (lossy ingestion) | Requirements §4 (deferred) | Partial | Deferral constrains the FR-3 adapter signature now — reserve a diagnostics channel (R1-F6). |

---

## Requirements Coverage Matrix — R2

Analysis only (informs orchestrator triage). Re-examined against R2's angles: sequencing realism, error taxonomy, doc-drift, the shipped-template golden, and adapter coupling. Only rows where R2 adds a *new* gap are annotated; others carry R1's disposition.

| Requirement | Plan Section(s) / Task | Coverage | R2-added gaps (beyond R1) |
| ---- | ---- | ---- | ---- |
| FR-1 (schema reference doc) | §1, §5, §7 N0 | Partial | Was "Covered" in R1; downgraded — hand-written doc has no sync test and will drift from `PersonaBrief`/allow-set (R2-F2 / R2-S3). |
| FR-2 (strict roster parser gate) | §1, §2, §7 N0 | Partial | Panel-interaction unaddressed: `assess_roster` state flips valid→invalid; shipped template not asserted to pass its own new gate (M0 byte-identity collision) (R2-F3 / R2-S4). |
| FR-3 (adapter contract + round-trip gate) | §1, §3, §4, §7 N1/N2 | Partial | No error taxonomy — gate reparse failure conflated with user-roster `RosterError` (R2-F1 / R2-S2); N1/N2 validation-location under-sequenced (R2-S1). |
| FR-4 (pluggable adapter registry) | §1, §3, §7 N1 | Partial | (R1-S2 stands) plus taxonomy of registry/adapter errors (R2-F1 / R2-S2). |
| FR-5 (role-rubric built-in adapter) | §1, §3, §6, §7 N1 | Partial | Adapter coupling/lazy-load to the panel hot path unbounded (R2-F4); N3 parity not proven before retirement (R2-S5). |
| FR-6 (CLI ingestion surface) | §1, §4, §6, §7 N2 | Partial | CLI exit-code contract undefined for the non-"unknown-format" failure modes (R2-F5). |
| FR-7 (ingested-roster provenance header) | §4, §5, §7 N2 | Partial | (R1-F4 / R1-S5 stand.) |
| FR-8 (reuse decision) | §0 | Covered | — |
| NR-1..NR-7 | §0, §2, §3, §4, §7 | Covered | — |
| OQ-8 (retire one-off script) | §7 N3 | Partial | Retirement should be gated on an adapter-vs-one-off parity test (R2-S5). |
| OQ-9 (lossy ingestion) | Requirements §4 (deferred) | Partial | (R1-F6 stands — reserve diagnostics channel.) |
