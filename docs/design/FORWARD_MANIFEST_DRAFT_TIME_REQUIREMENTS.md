# Forward Manifest at Draft Time — Requirements

**Version:** 0.6 (FR-2 structured diagnostic implemented — completes the MVP FR set)
**Date:** 2026-05-30
**Status:** R1 CRP applied; R2 audit corrected the FR-3 phantom-API premise and FR-3 fully
implemented (`ForwardManifest.validate_implementation()`); **FR-2's structured
`forward_manifest.section.empty` diagnostic — previously the one unimplemented MVP requirement —
is now implemented + tested**
**Component:** startd8 SDK — `implementation_engine/spec_builder.py` + `forward_manifest_extractor.py`
**Triggered by:** `RUN_003_FORWARD_MANIFEST_GAP_POSTMORTEM.md`

> Convert the Forward Manifest from a **post-hoc validator** into a **draft-time guide**,
> and make sure the most common framework-config target files have a non-empty contract by
> default. Two scopes that compose into one capability.

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 and v0.2 after a deep read of `spec_builder.py`,
> `forward_manifest.py`, `forward_manifest_extractor.py`, and `reviewer.py` (see
> `FORWARD_MANIFEST_DRAFT_TIME_PLAN.md`). 8 corrections; the headline is that **Fix 1 is
> mostly already built** — the bug is simply a missing append.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Fix 1 needs a new P0 section to be designed and inserted | The forward-manifest section is **already constructed** at `spec_builder.py:1113-1139`; it is just **not appended to the `prioritized` list**. Fix 1 is one append + one template wire-up | **FR-1** narrows: append + wire, not design |
| spec_builder needs a `task_id` to look up file_specs | `file_specs_for_task(self, task_id, target_files)` **ignores `task_id`** (reserved); `target_files` is already in `context` (`spec_builder.py:1168`) | No new mapping work — OQ-2 resolved |
| Prompt templating may be ad hoc | Standard pattern: YAML template (`prompts/__init__.py`) + `template.format(**format_kwargs)` at `:1399`; add one `{forward_manifest_section}` placeholder + one kwarg | OQ-3 resolved |
| Reviewer/spec contract drift is a real risk | ⚠ **SUPERSEDED (R2-F1) → CLOSED (R2-F2):** this row claimed `reviewer.py:270` calls `forward_manifest.validate_implementation()`. That method never existed (dormant `getattr(..., None)` → no-op). **R2-F2 made it real**: `ForwardManifest.validate_implementation()` is now implemented (multi-file Python + task-scoped contracts). See **FR-3**. | ~~FR-3 satisfied by construction~~ → FR-3 **rewritten**; real method now exists and the reviewer is a thin adapter over it |
| `ElementKind` already supports `default_export` | It does **not**. Kinds: `function`, `async_function`, `class`, `method`, `async_method`, `property`, **`constant`**, `variable` | **FR-5 / Fix 2** must model `next.config.mjs` as `CONSTANT name="config"`; defer a `DEFAULT_EXPORT` kind as a scoped follow-up |
| Merge semantics for plan-declared vs convention need bespoke logic | `_SOURCE_PRECEDENCE` (`forward_manifest_extractor.py:63-69`) already orders sources (human-yaml > proto/reference > deterministic > source-AST); slot framework defaults at **"deterministic"** tier and plan-declared overrides win for free | **FR-6** simplifies to "slot at deterministic precedence"; OQ-7 resolved |
| Path-pattern registry needs new design | Mirror `path_language_hints_from_file_specs` (`forward_manifest.py:748`) | OQ-8 resolved |
| The regression test needs an LLM call | A fixture can run `build_spec_prompt()` directly and assert section presence (LLM-free) | **FR-9** simplified (no real draft needed for the structural assertion) |

**Resolved open questions:**
- **OQ-1 → P0**, via appending to `prioritized` at `spec_builder.py:1113-1139` end.
- **OQ-2 → No `task_id` derivation needed;** `target_files` from `context` is sufficient.
- **OQ-3 → YAML template + `format_kwargs`** (one new placeholder + one kwarg).
- **OQ-4 → Reviewer enforces the same `ForwardFileSpec`/`InterfaceContract`.** ⚠ **Corrected (R2-F1) → implemented (R2-F2):** the original `validate_implementation()` was a phantom (dormant no-op). It is now a **real** method on `ForwardManifest` — single-source by construction (the reviewer calls it; it validates the same `ForwardFileSpec.elements[]` and task-scoped `InterfaceContract`s). See FR-3.
- **OQ-5 → Use `CONSTANT name="config"`** for `next.config.mjs`; do not stretch scope by adding a new `ElementKind`.
- **OQ-6 → Starter set (pinned per R1-S3 / R1-F7):** `next.config.{js,mjs,ts}`, `tsconfig.json`, `package.json`, `prisma/schema.prisma`, `vite.config.{js,ts,mjs,cjs}`, `jest.config.{js,ts,mjs,cjs,json}`, `tailwind.config.{js,ts,mjs,cjs}`.
- **OQ-7 → `_SOURCE_PRECEDENCE` already handles merge** — framework defaults at "deterministic" tier; plan-declared wins.
- **OQ-8 → Mirror `path_language_hints_from_file_specs`** pattern.
- **OQ-9 → `tests/unit/implementation_engine/test_spec_builder.py`** for unit; integration regression fixture is LLM-free (just assert prompt contents).

---

## 1. Problem Statement

The Forward Manifest carries `file_specs` (elements, imports, dependencies, language) per
target file. Today it is consumed only by `reviewer.py` and `engine.py` — *after* code is
drafted. The `spec_builder.py` / `drafter.py` path does **not** read it, so the drafter
generates blind against the contract it will be reviewed against. Run-003 PI-003
(`Next.js config`) failed this way: drafter emitted `export class next.config { … }`
because nothing in the spec prompt told it the file is a default-export object.

Compounding gap: the `forward_manifest_extractor` produced an **empty** spec for
`next.config.mjs` (`elements:[]`, `imports:[]`). For framework configuration files whose
shape is conventional (Next.js config, `tsconfig.json`, `package.json`, etc.), plans
typically don't enumerate internals — and there is no framework-conventions awareness in
the extractor to fill the gap.

| Component | Current State | Gap |
|-----------|--------------|-----|
| `spec_builder.py` consumes `file_specs` | ❌ no | **Fix 1**: inject `ForwardFileSpec` for the feature's target files as a P0 section |
| `drafter.py` consumes `file_specs` | ❌ no (downstream of spec_builder) | Inherits Fix 1 — receives the section via the spec |
| Extractor fills `next.config.mjs`, `tsconfig.json`, `package.json`, … | ❌ empty | **Fix 2**: framework-conventions registry |
| Reviewer consumes `file_specs` | ✅ yes | (No change — but contract injected at draft time must be the contract reviewer enforces) |
| Postmortem classifies `SyntaxError` | ❌ "Root cause: unknown" | Out of scope here — separate fix (see postmortem §3 Fix 3) |

### Critical distinction (preserve throughout)

- **Fix 1 — Consumer wiring:** `spec_builder.py` reads `ForwardManifest.file_specs_for_task(task_id)` (or equivalent) and renders the file_specs into the spec prompt as P0. Pure consumer change. No new data.
- **Fix 2 — Producer defaults:** `forward_manifest_extractor.py` consults a small framework-conventions registry so canonical config paths get non-empty `ForwardFileSpec`s by default. Pure producer change. No new consumer.

Fix 1 alone improves any feature whose plan **does** declare elements. Fix 1 + Fix 2 together cover the framework-config blind spot that broke PI-003.

---

## 2. Requirements

### MVP

- **FR-1 spec_builder injects per-target-file `ForwardFileSpec` as P0.** The
  forward-manifest section text — **already constructed** at `spec_builder.py:1113-1139`
  from `forward_contracts` + `forward_element_specs` — MUST be **appended to the
  `prioritized` list at P0** and wired through the spec template via a new
  `{forward_manifest_section}` placeholder + `format_kwargs` entry. The section contains
  the `ForwardFileSpec` for each target file (elements, imports, dependencies, language)
  plus any associated `InterfaceContract`s. *(Discovery: the section is already built;
  the structural bug is the missing append.)*
- **FR-1a Render-position ordering (R1-F2).** The `{forward_manifest_section}`
  placeholder MUST be rendered **inside the budget-enforced section sequence** — i.e.
  the section's substring index in the final rendered prompt MUST be **less than** the
  substring index of any surviving P3/P2/P1 section text. Presence is necessary but not
  sufficient: a P0 section rendered after a P3 block still satisfies presence but
  defeats the budget guarantee's intent (the section can be visually deprioritized by
  the LLM or clipped by downstream token clamping). The template position is part of
  the contract, not just an implementation detail.
- **FR-2 Graceful degradation + structured diagnostic (R1-F5).** If a target file has no
  `ForwardFileSpec` entry, or the spec is empty, the prompt MUST still build (no crash).
  When this fallback fires, the code MUST emit a **structured log event** with:
  - event name: `forward_manifest.section.empty`
  - severity: `INFO` (not WARN — this is expected for many feature/file combinations and
    should not page; `DEBUG` would be invisible to the postmortem classifier)
  - structured fields: `{target_files: list[str], reason: "missing_entry" | "empty_elements" | "no_target_files"}`

  The structured shape is the postmortem classifier's hook (Fix 3 — out of scope here
  but consumes this event).

  **Status: IMPLEMENTED (2026-05-30).** Previously this MVP requirement was unimplemented — the
  spec_builder appended the section when present (FR-1) but had no `else` branch, so the
  empty/missing case built silently with no diagnostic. Now `spec_builder.build_spec_prompt`
  emits `logger.info("forward_manifest.section.empty", extra={"event": …, "target_files": […],
  "reason": …})` on the empty branch, with `reason` ∈ {`no_target_files`, `missing_entry`,
  `empty_elements`}. Covered by `test_spec_builder.py::TestForwardManifestEmptyDiagnostic`
  (one test per reason + a no-event-when-present guard). Fix 3 (the classifier that *consumes*
  this event + `convention_provenance`) remains a separate effort.
- **FR-3 Single-source contract via a real `validate_implementation()` method (R1-F1;
  R2-F1 phantom-API correction; R2-F2 implementation).** The contract `spec_builder`
  injects MUST be the **same contract** `reviewer.py` enforces post-hoc — so the drafter
  sees what it will be reviewed against, end-to-end. This is now realized by a real,
  canonical method **on the manifest itself**: `ForwardManifest.validate_implementation()`.

  **History (R2-F1 — phantom API, now closed).** The v0.2 planning discovery (see §0 row 4
  and OQ-4) asserted that `reviewer.py:270` invokes
  `forward_manifest.validate_implementation()` and declared FR-3 *"satisfied by
  construction."* That method **never existed** — the call was a dormant
  `getattr(forward_manifest, "validate_implementation", None)` returning `None`, so post-hoc
  enforcement was a silent **no-op** (the deeper RUN_003 cause). An interim repair
  (`a9210da8`/`1d03be02`) wired a single-file, file-specs-only validator into
  `reviewer._validate_against_manifest`. **R2-F2 closes the gap fully** by making the
  originally-specified method real and complete.

  **Real method — `ForwardManifest.validate_implementation(implementation, target_files,
  *, task_id=None, include_contracts=True) -> List[ContractViolation]`.** It:
  1. Accepts a single drafted blob **or** a `{path: source}` mapping, and splits a
     multi-file blob via `extract_multi_file_code` (the lead-contractor pattern).
  2. Builds a Python `ManifestRegistry` via `generate_file_manifest(source=…)` — **no temp
     files** — skipping files that fail to parse (a syntax error is caught separately and
     must not masquerade as `missing_element`).
  3. Runs the complete `forward_manifest_validator.validate_forward_manifest` over a
     **scoped** sub-manifest: `file_specs` ∩ `target_files` (Python only), and — when a
     `task_id` is supplied — interface **contracts** scoped via `contracts_for_task`
     (function/class/import/formula). This is the first time the post-hoc path enforces
     `contracts`, not just element specs.
  `reviewer._validate_against_manifest` is now a thin adapter that calls this method and maps
  `ContractViolation` → the review's dict shape; `review_draft`/`engine.py` thread `task_id`
  (from `request.context`).

  **Enforcement scope (stated precisely).** Element-level `file_specs` validation now covers
  **all Python target files** of a draft (multi-file, attributed per file — no cross-file
  false positives). Interface **contracts** are enforced when a `task_id` is available;
  without one, contracts are **skipped** (the relevant subset can't be determined safely, and
  validating project-wide against a single draft's registry would false-flag symbols defined
  in undrafted files). **Non-Python files** are not element-validated (the structural
  validator is Python-AST-based) — config-file *shape* is still guided at draft time by FR-1/
  FR-5; runtime element enforcement for JS/TS configs is a separate (non-AST) follow-up.

  **Acceptance criterion:** (a) a present element yields zero violations and an absent one a
  `missing_*` violation, asserted against a **real** `ForwardManifest`
  (`test_reviewer.py`); (b) a two-Python-file blob validates each file's spec independently
  and attributes a violation to the correct file (no cross-file false positive); (c) a
  `task_id`-scoped `function_name` contract is enforced and is skipped without a `task_id`;
  (d) non-`.py` files and parse-error files degrade to `[]`
  (`tests/unit/test_forward_manifest_validate_implementation.py`). Asserted by execution.
- **FR-4 Token budget respected.** Adding the P0 section MUST stay within
  `TOTAL_SPEC_BUDGET_TOKENS` (4096). On budget pressure, lower-priority (P1–P3) sections
  are pruned, not P0. *(Assumption: `budget.enforce_prompt_budget` already does
  priority-ordered eviction.)*
- **FR-5 Framework-conventions registry.** `forward_manifest_extractor.py` MUST consult a
  small, auditable **framework-conventions registry** keyed by filename pattern,
  **mirroring the existing `path_language_hints_from_file_specs`** pattern
  (`forward_manifest.py:748`). When a target path matches a registered pattern, the
  extractor populates a default `ForwardFileSpec` using **existing `ElementKind`s** —
  e.g. `next.config.{mjs,js,ts}` → `elements=[ForwardElementSpec(kind=CONSTANT,
  name="config", type_annotation="NextConfig")]` (matches the
  `export const config = …; export default config` pattern). Adding a `DEFAULT_EXPORT`
  `ElementKind` is deferred as a scoped follow-up; this requirement does **not** depend
  on it.

  **Pure default-export files (R1-F3).** For files whose canonical shape is a default
  export of an object literal with **no named binding** (e.g.
  `tailwind.config.{js,ts,mjs}`, certain `vite.config.ts` patterns,
  `jest.config.{js,ts}` exporting an unnamed config object), the convention MAY model
  an anonymous `CONSTANT` with a sentinel name such as `default` (e.g.
  `ForwardElementSpec(kind=CONSTANT, name="default", type_annotation="<ConfigType>")`).
  This is **explicitly an approximation** pending the deferred `DEFAULT_EXPORT`
  `ElementKind`. The approximation is acceptable because (a) the reviewer's
  `validate_implementation()` matches on `(kind, name)` tuples and the convention's
  output is what gets enforced — so the symmetry is preserved even if the name is a
  sentinel; and (b) the alternative (omitting these files from the starter set) leaves
  exactly the canonical-config blind spot Fix 2 exists to close. The
  `tailwind.config.*` starter-set entry (FR-7) depends on this rule.
- **FR-6 Plan-declared elements override conventions (via existing precedence) —
  full-source override (R1-F6).** Framework defaults are slotted into the existing
  `_SOURCE_PRECEDENCE` (`forward_manifest_extractor.py:63-69`) at the
  **"deterministic"** tier. Human-YAML, proto, and reference-AST sources override
  automatically — **no new merge code required**.

  **Override granularity.** Override is **full-source per file**, not per-element merge.
  That is: when a higher-precedence source (e.g. human-YAML) produces a `ForwardFileSpec`
  for a target file matching a framework pattern, the higher-precedence source's
  **entire element set replaces** the convention's element set for that file — they do
  not union. Rationale: per-element merge introduces ambiguity for the reviewer (which
  source "owns" a partial conflict?) and would require new merge logic that this
  capability explicitly avoids. Authors who want to extend the convention's elements
  must restate the convention's elements alongside their additions.

  **Deterministic-empty vs convention-non-empty collision (R1-S4 partner).** When the
  deterministic extractor produces a `ForwardFileSpec(elements=[])` for a path that
  also matches a `FRAMEWORK_CONFIG_DEFAULTS` entry, the **convention wins** (the empty
  deterministic output does not silently overwrite the non-empty convention). Empty
  output from the same precedence tier is treated as "no contribution," not as
  "successful empty contract." See plan `t-fwd-registry` for the implementation hook
  and `t-extractor-test` for verification.
- **FR-7 Starter set is small and auditable.** The initial registry covers a small,
  documented set of patterns. The registry is plain data, version-stamped, with a clear
  extension procedure.

  **Starter set (resolves R1-F7 inconsistency; pinned per R1-S3):**
  - `next.config.{js,mjs,ts}`
  - `tsconfig.json`
  - `package.json`
  - `prisma/schema.prisma`
  - `vite.config.{js,ts,mjs,cjs}`
  - `jest.config.{js,ts,mjs,cjs,json}`
  - `tailwind.config.{js,ts,mjs,cjs}`

  **Pinned, not glob-wild.** Patterns are filename-anchored (no path prefix), match the
  exact extension list (no `*` wildcard on extension — e.g. `vite.config.bak` does
  **not** match), and are documented as the contract. Adding new extensions is an
  explicit registry change (FR-7's "clear extension procedure").
- **FR-8 No regression.** Features whose plans already declare full file_specs MUST
  receive the same prompt as today (plus the P0 injection from FR-1). Features with no
  forward_manifest data MUST behave exactly as today (no error, no behavior change).
- **FR-9 Regression test reproduces PI-003 (LLM-free) — split into two assertions
  (R1-F8).** A fixture constructs a minimal seed where `next.config.mjs` is a target
  file, runs `build_spec_prompt()` end-to-end, and verifies the structural fix via
  **two independently-runnable assertions**:
  - **FR-9a (Fix 1 active):** the prompt contains a forward-manifest section that
    includes the `ForwardFileSpec` for `next.config.mjs` — given any plan-declared
    `file_specs` entry for that target. Test failure attributes to the spec_builder
    wiring (`t-spec-append`).
  - **FR-9b (Fix 2 active):** for an extractor-only seed (no plan-declared elements),
    the rendered section is **non-empty** because the convention registry populated
    `next.config.mjs`. Test failure attributes to the extractor registry
    (`t-fwd-registry` / `t-registry-content`).

  Splitting is required so a CI failure points at the correct increment — Fix 1 and
  Fix 2 ship independently per FR-10, and their tests must too. **No LLM call required.**
- **FR-10 Iterative delivery.** Ship Fix 1 first (Increment 0), Fix 2 next (Increment 1).
  Each is independently usable. Independent shippability is verified by FR-9a/FR-9b
  running cleanly when only their corresponding increment has landed.

---

## 3. Non-Functional Requirements

- **NFR-1 No regression — byte-identical, golden-file enforced (R1-F4).** Existing
  spec-prompt outputs for features without `forward_manifest` data are byte-identical
  to pre-Fix-1 output. **Test specification:** a curated regression set of **N ≥ 3**
  prior seed fixtures (each with no `forward_manifest.file_specs` data) lives under
  `tests/regression/no_forward_manifest/*.yaml`. The **SHA-256** of
  `build_spec_prompt(seed)` for each fixture MUST equal a committed `*.sha256` golden
  file captured **before the Fix 1 diff lands** (see plan task `t-nfr1-golden` for the
  sequencing constraint). CI runs in `--check` mode and fails on any drift. "Byte-
  identical" is unfalsifiable in practice without this harness; the golden-file scheme
  turns it into a hard gate.
- **NFR-2 Token budget.** `TOTAL_SPEC_BUDGET_TOKENS` is never exceeded; P0 stays in.
- **NFR-3 Determinism.** Same seed → same spec prompt → same drafter input.
- **NFR-4 Zero LLM cost.** Fix 2's registry is pure rule-based; the extractor's LLM cost
  does not change.
- **NFR-5 Auditable registry.** The framework-conventions registry is human-readable
  (YAML or a small Python dict module), version-stamped, with a comment per entry.

---

## 4. Non-Requirements

- Does **not** modify `reviewer.py` or `engine.py` (their existing post-hoc consumption stays).
- Does **not** change the seed schema or any workflow stage boundary.
- Does **not** address the **postmortem/Kaizen classifier** (Fix 3 in the postmortem) — separate effort.
- Does **not** introduce intra-run parallelism or batch orchestration (separate effort).
- Does **not** ship an exhaustive framework registry — starter set only; expansion is iterative.

---

## 5. Iterative delivery increments (assumption — refine in planning)

- **Increment 0 — Fix 1 only: spec_builder injection.** Add a P0 forward-manifest section
  to the spec prompt, sourced from `ForwardFileSpec`. Useful immediately for any plan
  that declares elements/imports. Zero new data; pure consumer wiring. *Lowest risk; high
  leverage on the structural gap.*
- **Increment 1 — Fix 2: framework-conventions registry.** Add the extractor's pattern
  registry + a starter set. Combined with Increment 0, closes the run-003 PI-003 failure
  mode for canonical configs.
- **Increment 2 — Hardening: regression suite + audit.** Expand the regression to cover
  every starter-set pattern + a few negative cases (plan-declared overrides win); add a
  "convention used" marker so the postmortem (when Fix 3 ships) can attribute failures.

---

## 6. Open Questions

*All v0.1 open questions (OQ-1 … OQ-9) were resolved during planning — see §0.* None
remain open for the MVP. **Two carry-over risks** are tracked in the plan (`§7 Risks`):
**R2** verify `forward_manifest.validate_implementation()` is what `reviewer.py:270`
actually invokes (single-source contract), and **R1** the test must oversize lower
priorities to confirm P0 protection is real for the new section.

---

*v0.2 — Post-planning self-reflective update. Headline: planning found that the
forward-manifest section is **already constructed** at `spec_builder.py:1113-1139` but
**never appended to `prioritized`** — so Fix 1 is a tiny diff, not new design. Corrected
**FR-1** (append + wire), **FR-5** (use existing `CONSTANT` kind; no `DEFAULT_EXPORT`
yet), **FR-6** (slot at the existing `_SOURCE_PRECEDENCE` deterministic tier — no new
merge logic), and **FR-9** (LLM-free fixture). Resolved all 9 open questions. Paired with
`FORWARD_MANIFEST_DRAFT_TIME_PLAN.md` v1.0.*

*v0.3 — R1 CRP triage applied. All 8 R1 suggestions (R1-F1..R1-F8) ACCEPTed: FR-1a
added (render-position ordering), FR-2 specifies structured log event, FR-3 binds a
byte-equivalent acceptance criterion, FR-5 covers pure default-export files, FR-6 pins
override granularity (full-source, not per-element merge) + deterministic-empty
collision rule, FR-7 starter set explicit + Tailwind added, FR-9 split into FR-9a/FR-9b
for clean fault attribution, NFR-1 specifies SHA-256 golden-file harness. Dispositions
persisted in Appendix A (not stripped). Paired with `FORWARD_MANIFEST_DRAFT_TIME_PLAN.md`
v1.1.*

*v0.4 — R2 implementation-vs-requirements audit (post-ship). One high-severity correction:
**FR-3's "single-source contract" was built on a phantom API.** The v0.2 planning pass
mis-read a dormant `getattr(forward_manifest, "validate_implementation", None)` as a live
method call and declared FR-3 "satisfied by construction"; the method never existed and
post-hoc enforcement was a no-op (the deeper RUN_003 cause). FR-3 rewritten; §0 row 4 +
OQ-4 marked superseded. Dispositions in Appendix A / round R2 in Appendix C.*

*v0.5 — FR-3 gap fully closed (R2-F2). The phantom is now **real**:
`ForwardManifest.validate_implementation(implementation, target_files, *, task_id,
include_contracts)` is implemented as the canonical single-source enforcement method —
splits multi-file blobs (`extract_multi_file_code`), builds a Python `ManifestRegistry`
(`generate_file_manifest(source=…)`, no temp files, parse-error files skipped), and runs
the complete `validate_forward_manifest` over a scoped sub-manifest (file_specs ∩
target_files; contracts via `contracts_for_task` when a `task_id` is supplied).
`reviewer._validate_against_manifest` is now a thin adapter; `review_draft`/`engine.py`
thread `task_id`. This closes three gaps at once: phantom→real, single-file→multi-file,
file_specs-only→**+interface contracts**. New tests:
`tests/unit/test_forward_manifest_validate_implementation.py` (12) +
`test_reviewer.py::test_flcm_contract_validation_detects_missing_element` (real manifest).
The plan's `t-validate-impl-read` / `t-contract-symmetry` remain obsolete as written (they
target the phantom signature), but the real method's behavior is now covered by the tests
above.*

*v0.6 — FR-2 structured diagnostic implemented, completing the MVP FR set. The
`forward_manifest.section.empty` INFO event (fields `{event, target_files, reason}`,
`reason` ∈ `no_target_files`/`missing_entry`/`empty_elements`) is emitted on
`spec_builder.build_spec_prompt`'s empty/missing branch — previously this MVP requirement was
silently unimplemented (section appended when present via FR-1, but no `else` diagnostic). This
is the postmortem-classifier hook (Fix 3, still a separate effort, now unblocked). Tests:
`test_spec_builder.py::TestForwardManifestEmptyDiagnostic` (3 reasons + no-event-when-present).*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}` for requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Add byte-equivalent acceptance criterion to FR-3 with a unit test asserting shape-equivalence vs `validate_implementation()`'s consumed (kind, name, type) tuples | R1 / claude-opus-4-7-1m | Applied to **FR-3** prose: explicit acceptance criterion added; verification deferred to plan `t-contract-symmetry` (R1-S7) which executes the symmetry assertion. | 2026-05-29 |
| R1-F2 | Add FR-1a constraining template render-position: section index must be before any surviving P3/P2/P1 section text | R1 / claude-opus-4-7-1m | Applied as **FR-1a** (new requirement). Verification deferred to plan `t-spec-test` strengthened by R1-S2. Documents that presence ≠ position-protection. | 2026-05-29 |
| R1-F3 | Clarify FR-5 for pure-default-export files (no named binding) — sentinel `CONSTANT name="default"` pending `DEFAULT_EXPORT` kind | R1 / claude-opus-4-7-1m | Applied to **FR-5** prose: new "Pure default-export files" subsection acknowledges approximation, cites symmetry rationale, and links to `tailwind.config.*` starter-set entry (FR-7). | 2026-05-29 |
| R1-F4 | Tighten NFR-1 with concrete SHA-256 golden-file regression set (N ≥ 3) captured pre-Fix-1 | R1 / claude-opus-4-7-1m | Applied to **NFR-1**: test specification, fixture directory, hash mode, and pre-Fix-1 capture sequencing pinned. Plan task `t-nfr1-golden` (R1-S5) implements the harness with required sequencing. | 2026-05-29 |
| R1-F5 | Specify FR-2's diagnostic contract: event name, severity, structured fields | R1 / claude-opus-4-7-1m | Applied to **FR-2**: event `forward_manifest.section.empty` at INFO severity with structured fields `{target_files, reason}`. Reason chose INFO not DEBUG so postmortem classifier (Fix 3) can subscribe without losing visibility. | 2026-05-29 |
| R1-F6 | FR-6 should specify per-element merge vs full-source override granularity | R1 / claude-opus-4-7-1m | Applied to **FR-6**: full-source override (no per-element merge in MVP); also pinned deterministic-empty vs convention-non-empty collision rule (convention wins) — pairs with R1-S4. | 2026-05-29 |
| R1-F7 | Resolve Tailwind inconsistency between FR-7 prose and OQ-6 starter set | R1 / claude-opus-4-7-1m | Applied to **FR-7** + **OQ-6**: Tailwind kept in scope; `tailwind.config.{js,ts,mjs,cjs}` added to the pinned starter set. Modeled per the FR-5 pure-default-export rule. | 2026-05-29 |
| R1-F8 | Split FR-9 into FR-9a and FR-9b so failures attribute cleanly to Fix 1 vs Fix 2 | R1 / claude-opus-4-7-1m | Applied to **FR-9**: split into FR-9a (Fix 1 active) and FR-9b (Fix 2 active). Independent runnability supports FR-10's independent shippability per increment. | 2026-05-29 |
| R2-F1 | Correct FR-3: `forward_manifest.validate_implementation()` is a phantom method — post-hoc enforcement was a dormant no-op (`getattr(..., None)` → `None` → `[]`). Rewrite FR-3 to the real `_validate_against_manifest` → `_validate_file_spec` path; state the single-blob / Python-only enforcement scope. | R2 / opus-4.8-1m (impl-vs-req audit) | Applied to **FR-3** (rewritten), **§0 row 4** + **OQ-4** (superseded). Real path verified in code (commits `a9210da8`, `1d03be02`). Paired plan tasks `t-validate-impl-read` / `t-contract-symmetry` flagged obsolete. | 2026-05-30 |
| R2-F2 | Fully close the FR-3 gap: make the originally-specified `ForwardManifest.validate_implementation()` **real** rather than documenting it away — multi-file split, Python registry (no temp files, skip parse-error files), and `validate_forward_manifest` over a scoped sub-manifest (file_specs ∩ target_files + task-scoped contracts). Rewire the reviewer as a thin adapter; thread `task_id`. | R2 / opus-4.8-1m | **Implemented** in `forward_manifest.py` (method), `reviewer.py` (adapter + `task_id`), `engine.py` (`task_id` from context). Closes phantom→real, single→multi-file, +contracts. Tests: `test_forward_manifest_validate_implementation.py` (12) + real-manifest reviewer test. | 2026-05-30 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet — all R1 suggestions accepted) |  |  |  |  |

### Substantially-Addressed Tracker (R1)

Topics that subsequent rounds should **not** re-litigate without new information — they were considered and resolved in R1 triage:

- **Template render-position vs P0 protection** — Covered by FR-1a (requirement) + plan `t-spec-test` strengthened ordering assertion (R1-S2).
- **Single-source contract verification mechanism** — Covered by FR-3 acceptance criterion + plan `t-validate-impl-read` (R1-S1) + `t-contract-symmetry` (R1-S7).
- **Pure default-export file modeling under existing `ElementKind`** — Covered by FR-5 pure-default-export subsection (approximation via sentinel `CONSTANT name="default"`; `DEFAULT_EXPORT` kind explicitly deferred).
- **NFR-1 testability** — Covered by NFR-1 golden-file specification + plan `t-nfr1-golden` with pre-Fix-1 capture sequencing.
- **FR-2 diagnostic surface for postmortem classifier** — Covered by FR-2 event name / severity / field schema.
- **FR-6 override granularity (replace vs merge) + deterministic-empty collision** — Covered by FR-6 full-source rule + collision rule (convention wins).
- **FR-7 starter set pinning + Tailwind inclusion** — Covered by FR-7 explicit list + OQ-6 update.
- **FR-9 independent fault attribution per increment** — Covered by FR-9a / FR-9b split.

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-7-1m — 2026-05-29

> **Status: TRIAGED 2026-05-29 — all 8 suggestions ACCEPTED.** Dispositions recorded in Appendix A. Substantially-Addressed tracker updated. Do not re-propose these in a later round without new information.

- **Reviewer**: claude-opus-4-7-1m
- **Date**: 2026-05-29 23:00:00 UTC
- **Scope**: Requirements review — testability of FR-3/NFR-1, ambiguity in FR-5/FR-7, completeness of FR-2/FR-6 acceptance criteria, and gaps surfaced by paired plan risks R1/R2.

**Executive summary**

- FR-3's "single-source contract" is the centerpiece but has no explicit acceptance criterion that ties it to a verification step on `validate_implementation()` — plan R2 flags the same gap.
- FR-1 says the section MUST be at P0 in `prioritized`, but does not constrain where in the rendered template the placeholder lives — Risk R1 is real and the requirement is silent on it.
- FR-5's `CONSTANT name="config"` modeling is an approximation for `next.config.mjs`; the requirement does not state how it handles pure-default-export files (e.g., `tsconfig.json` JSON, `vite.config.ts` with `export default defineConfig(...)`).
- FR-7's "starter set" enumerates Tailwind in prose but omits it from the OQ-6 list — internal inconsistency that affects scope.
- NFR-1 "byte-identical" is strong but lacks a measurable test specification — risks silently weakening on review.
- FR-2 ("graceful degradation") does not specify the diagnostic surface (log channel, structured event, severity) — undertestable.
- FR-6 lacks acceptance criteria for "override" — what counts as plan-declared elements winning over framework defaults (full-spec replacement vs. per-element merge)?
- FR-9 conflates two assertions but does not specify ordering invariants (the section must be present *and* P0-protected) — the assertion structure could be sharpened.
- Out-of-scope #3 (postmortem classifier) is referenced as future Fix 3 but `t-convention-marker` (a plan task) is justified by it — confirm requirements explicitly enable the provenance field.
- No requirement constrains the template-rendering order of P0 sections — could create silent dependencies on prompt position.

**Numbered suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | Add an explicit acceptance criterion to FR-3 that the contract injected into the spec prompt is **byte-equivalent to the rendered output of `forward_manifest.validate_implementation()`'s expected element set** for the same target file. Require a unit test that reads `validate_implementation()` and asserts the kinds/names/types it consumes equal those rendered by the spec section. | The plan flags R2 (validate_implementation body not read). Without a testable criterion, FR-3 is an assumption, not a contract. The reviewer is the consumer of the contract; the requirement should bind the producer side to the consumer's actual expectations. | §2 MVP, FR-3 | Add a test in `test_spec_builder.py` (or a dedicated `test_forward_manifest_contract.py`) that imports both the section renderer and `validate_implementation` and asserts shape equivalence on a fixture manifest. |
| R1-F2 | Interfaces | high | Add **FR-1a (or amend FR-1)**: the `{forward_manifest_section}` placeholder MUST be rendered *inside* the budget-enforced section sequence (i.e., its template position MUST be consistent with `prioritized` ordering), not as a stray block elsewhere in the YAML template. Acceptance: the rendered prompt's substring index of the forward-manifest section is before any P3/P2/P1 section text. | Plan Risk R1 explicitly worries that the template placement could defeat the budget guarantee. The requirement should make this guarantee, not delegate it entirely to a test. | §2 MVP, after FR-1 (or as FR-1a) | Add assertion in `t-spec-test` that compares `prompt.index(forward_manifest_section)` against indices of lower-priority sections to confirm budget-aware ordering. |
| R1-F3 | Data | medium | Clarify FR-5 with an explicit treatment of **pure default-export files**: state that for files whose canonical shape is a default export of an object literal with no named binding (e.g., some `vite.config.ts`, `tailwind.config.js` patterns), the convention MAY model an anonymous `CONSTANT` (e.g., `name="default"` or `name="<module>"`) and the requirement explicitly acknowledges this is an approximation pending `DEFAULT_EXPORT` follow-on. Without this, R3 follow-on could leave a gap of files the convention does not faithfully model. | FR-5 currently only addresses `next.config.mjs` (which is `export const config = …; export default config` — both names exist). Pure default-export configs are common and the requirement is silent. Reviewer's `validate_implementation()` may not find a match if the binding name doesn't exist. | §2 MVP, FR-5 second paragraph | Documented in FR-5; verified via extractor unit test that asserts the convention output for at least one pure-default-export pattern produces a kind/name reviewer can accept. |
| R1-F4 | Validation | medium | Tighten NFR-1 ("byte-identical") with a concrete test specification: for a curated regression set of N (>=3) prior seed fixtures with no `forward_manifest` data, the SHA-256 of the generated spec prompt MUST be unchanged versus the pre-Fix-1 baseline (captured as a golden file). Without this, "byte-identical" is unfalsifiable in practice. | "Byte-identical" sounds testable but is operationally vague (which inputs? captured how?). A golden-file regression with hash comparison turns it into a hard gate. | §3 NFR-1 | CI step compares hash of `build_spec_prompt(seed)` for fixtures `regression/no_forward_manifest/*.yaml` against committed `*.sha256` files; fails on any drift. |
| R1-F5 | Risks | medium | Specify FR-2's diagnostic contract: state the log severity (e.g., `INFO`/`DEBUG`), the log key/event name (e.g., `forward_manifest.section.empty`), and the structured fields (target_files, reason). Otherwise "a diagnostic is logged" is untestable and gives no postmortem hook. | FR-2 promises a diagnostic but the postmortem (the originator of this work) relies on structured logs to attribute root causes. An unstructured log line is invisible to classifiers. | §2 MVP, FR-2 | Test that calls `build_spec_prompt` on a seed with no file_specs and asserts a specific log event is emitted at the named severity with the expected fields. |
| R1-F6 | Architecture | medium | FR-6 should specify the **granularity of override**: when plan-declared elements exist for a target file matching a framework pattern, do plan-declared elements **replace** the convention's element set entirely, or do they **merge** (plan-declared union convention defaults)? `_SOURCE_PRECEDENCE` orders sources but does not by itself answer per-element merge semantics. | The precedence model resolves source-level conflicts, but elements are sets. If a plan declares one element for `next.config.mjs` (say, an additional constant), should the convention's `config` constant survive or be dropped? FR-6 should state the rule and FR-7's starter-set tests should cover it. | §2 MVP, FR-6 | Add an extractor unit test for the partial-plan-declared case: plan declares element A; convention provides {config}; assert observed outcome matches the documented rule (replace vs. merge). |
| R1-F7 | Interfaces | low | FR-7 prose mentions **Tailwind** ("Next.js, TypeScript, Node `package.json`, Prisma, Vite, Jest, Tailwind") but the OQ-6 resolved starter set (and the plan's `t-registry-content`) omits Tailwind. Either add `tailwind.config.{js,ts,mjs}` to the starter set or remove Tailwind from FR-7 prose. | Plan ↔ requirements inconsistency; reviewer of the plan won't know whether Tailwind is in or out. Internal consistency matters for scope-lock. | §2 MVP, FR-7 | N/A — editorial; resolve before implementation. |
| R1-F8 | Ops | low | FR-9's two assertions (Fix 1 active = section present; Fix 2 active = section non-empty via registry) should be **independently runnable** so a CI failure can point at the correct Fix. Recommend splitting into FR-9a (section present for any plan-declared file_specs target) and FR-9b (convention-populated section non-empty for an extractor-only seed). | If the test is one combined assertion, a failure could be misattributed (e.g., extractor change blamed for a spec_builder regression). Independent assertions = clean fault attribution and let the increments ship truly independently per FR-10. | §2 MVP, FR-9 | Split into two pytest cases sharing a fixture factory; each case has a single failure mode. |

**Endorsements**: (none — R1 is the first round; no prior untriaged suggestions.)

**Disagreements**: (none — first round.)

#### Review Round R2 — opus-4.8-1m (implementation-vs-requirements audit) — 2026-05-30

> **Status: TRIAGED 2026-05-30 — R2-F1 ACCEPTED & applied** (disposition in Appendix A).
> Unlike R1 (a forward-looking requirements review), R2 audits the **shipped code** against
> the requirements to find where the spec and reality diverged.

- **Reviewer**: opus-4.8-1m
- **Scope**: Post-ship audit of FR-3's "single-source contract" centerpiece against the
  actual `reviewer.py` / `forward_manifest_validator.py` implementation.

**Executive summary**

- **FR-3 was based on a phantom method.** The requirement and the paired plan are
  load-bearing on `forward_manifest.validate_implementation()`. That method does not exist
  and never did. `grep -rn validate_implementation src/` returns a single hit: a comment in
  `reviewer.py` *explaining that it never existed*. The v0.2 planning pass mistook a dormant
  `getattr(forward_manifest, "validate_implementation", None)` (which always returns `None`)
  for a live call, and concluded FR-3 was "satisfied by construction." In reality post-hoc
  enforcement was a **silent no-op** — arguably a more serious instance of the same
  RUN_003 failure mode the capability set out to fix (a contract that is *specified* but not
  *enforced*).
- **Enforcement scope is narrower than draft-time injection and was never specified.** The
  repaired enforcement validates **one Python file per review** (single `implementation`
  blob); multi-file and non-Python targets degrade to a no-op. FR-1 injects the contract for
  *all* target files, so draft-time and review-time coverage are asymmetric.

**Numbered suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Validation | high | Rewrite FR-3 to remove every reference to the phantom `validate_implementation()`; describe the real `_validate_against_manifest` → `_validate_file_spec` single-file-`ManifestRegistry` path; state the single-blob / Python-only enforcement scope explicitly; re-point the acceptance criterion at the real `test_reviewer.py` test. Mark §0 row 4 and OQ-4 superseded. Flag the paired plan's `t-validate-impl-read` / `t-contract-symmetry` as obsolete. | A requirement and a PR-blocking plan gate built on a non-existent API cannot be satisfied as written, and they conceal that enforcement was dormant. The spec must describe the code that actually ships. | FR-3, §0, OQ-4, plan note | Code: `grep validate_implementation` finds only the comment; `test_reviewer.py` exercises the real path. |
| R2-F2 | Architecture | high | Rather than only documenting the phantom away, **fully close the gap**: implement the originally-specified `ForwardManifest.validate_implementation()` as the canonical single-source enforcement method (multi-file split via `extract_multi_file_code`, Python `ManifestRegistry` with parse-error files skipped, `validate_forward_manifest` over a scoped sub-manifest = file_specs ∩ target_files + task-scoped contracts). Rewire `_validate_against_manifest` as a thin adapter; thread `task_id` through `review_draft`/`engine.py`. This removes the single-file-only and contracts-not-validated limitations the interim repair carried. | The user-facing value of FR-3 is *enforcement that matches what the drafter saw*. The interim repair enforced only single-file element specs; multi-file drafts and interface contracts went unchecked. A real method on the manifest (where the contract lives) is true single-source and unlocks multi-file + contract enforcement. | FR-3, `forward_manifest.py`, `reviewer.py`, `engine.py` | `test_forward_manifest_validate_implementation.py`: multi-file per-file attribution, contract scoping by `task_id`, non-py/parse-error degrade-to-empty; reviewer test uses a real manifest. |

**Endorsements**: (none.)
**Disagreements**: (none.) R2-F2 supersedes the "tracked as a follow-up" note in R2-F1's FR-3 text — the multi-file gap it deferred is now closed in the same pass.
