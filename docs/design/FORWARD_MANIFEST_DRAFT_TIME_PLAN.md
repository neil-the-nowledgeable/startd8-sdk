# Forward Manifest at Draft Time — Implementation Plan

**Version:** 1.2 (R2 impl-audit correction — phantom-API tasks obsoleted)
**Date:** 2026-05-30
**Pairs with:** `FORWARD_MANIFEST_DRAFT_TIME_REQUIREMENTS.md` (v0.4)

> **⚠ R2 correction (2026-05-30).** This plan is load-bearing on a method that does not
> exist: `forward_manifest.validate_implementation()` (referenced in §1 row "Reviewer's
> contract enforcement", §2/§3 prose, and tasks **`t-validate-impl-read`** and
> **`t-contract-symmetry`**). It never existed — `reviewer.py:270`'s
> `getattr(forward_manifest, "validate_implementation", None)` always returned `None`, so
> enforcement was a dormant no-op. The shipped repair (commits `a9210da8`, `1d03be02`) uses
> `_validate_against_manifest` → `forward_manifest_validator._validate_file_spec` over a
> single-file `ManifestRegistry`, Python-only and single-target. **Tasks
> `t-validate-impl-read` (the PR-blocking "read the method body" gate) and
> `t-contract-symmetry` (asserting `validate_implementation(synth) == []`) are OBSOLETE** —
> the real symmetry test lives in `tests/unit/implementation_engine/test_reviewer.py`. See
> REQUIREMENTS FR-3 (rewritten) and Appendix C round R2.

Grounded in a deep read of `spec_builder.py`, `forward_manifest.py`,
`forward_manifest_extractor.py`, and `reviewer.py`. The headline finding from planning:
**the wiring is already half-built.**

---

## 1. What actually exists (with `file:line`)

| Primitive | Location | Behavior | Reuse |
|-----------|----------|----------|-------|
| Section priority model | `implementation_engine/spec_builder.py:1172-1360` and `implementation_engine/budget.py:217-296` | Sections assembled as `(priority, label, text)` tuples in `prioritized`; **P0 never dropped** (truncated only if alone over budget); P3→P2→P1 evicted in order on overrun | **Append the forward-manifest section to `prioritized` at P0** |
| Existing P0 sections | `spec_builder.py:1171,1176,1201,1257,1265` | `context`, `project_context`, `kaizen_security`, `security_guidance`, `coding_standards` | (Adding our section here) |
| Forward-manifest section **already built but unwired** | `spec_builder.py:1113-1139` | `forward_contracts` + `forward_element_specs` are popped from context and assembled into a `forward_contracts_section` string — **never added to `prioritized`** | **The structural defect**: add the missing line |
| Budget enforcement | `budget.py:217` `enforce_prompt_budget(prioritized, TOTAL_SPEC_BUDGET_TOKENS, …)` called at `spec_builder.py:1376` | Priority-ordered eviction; P0 protected | Reused as-is |
| Per-task file_specs | `forward_manifest.py:473-489` `file_specs_for_task(self, task_id, target_files)` | **Filters by `target_files` and ignores `task_id`** (reserved) | Call from spec_builder with `context.get("target_files")` |
| ForwardFileSpec schema | `forward_manifest.py:276-299` | Fields: `file`, `elements[]`, `imports[]`, `dependencies`, `language` | Render fields into the section |
| ForwardElementSpec kinds | `forward_manifest.py:111-234` (`ElementKind` from `code_manifest`) | `function`, `async_function`, `class`, `method`, `async_method`, `property`, **`constant`**, `variable` — **no `default_export`** | Model `next.config.mjs` as `kind=CONSTANT, name="config"` |
| YAML prompt templates | `prompts/__init__.py` + `spec_builder.py:126-132 get_template`; format at `:1399 template.format(**format_kwargs)`; kwargs assembled `:1388-1398` | Add `{forward_manifest_section}` placeholder + add the text to `format_kwargs` | Standard extension pattern |
| Reviewer's contract enforcement | `reviewer.py:255-294` `_validate_against_manifest` → `forward_manifest.validate_implementation()` at `:270`; violations rendered as a "Constraint Verification Checklist" `:301-339` | Consumes the **same** `ForwardFileSpec`/`InterfaceContract` shape | **Single-source contract guaranteed** (FR-3) |
| Source precedence | `forward_manifest_extractor.py:63-69` `_SOURCE_PRECEDENCE` | human-yaml > proto/reference > deterministic > source-AST | **Slot framework defaults at "deterministic" tier** — plan-declared overrides win for free. **Collision rule (R1-S4):** when the deterministic extractor produces `elements=[]` for a path that also matches a `FRAMEWORK_CONFIG_DEFAULTS` entry, the convention's non-empty spec MUST win — empty deterministic output is treated as "no contribution," not as "successful empty contract." Without this rule the silent-poison failure mode (whichever tier-equivalent source runs second wins) is possible. Override granularity is **full-source per file**, not per-element merge (mirrors REQUIREMENTS FR-6). |
| Path-pattern registry pattern | `forward_manifest.py:748` `path_language_hints_from_file_specs` | Existing path-pattern → defaults mapping | Mirror its shape for `FRAMEWORK_CONFIG_DEFAULTS` |
| Spec-builder unit tests | `tests/unit/implementation_engine/test_spec_builder.py` | Entry: `build_spec_prompt()`; prompt-text assertions | Add a section-presence test for Fix 1 + a Fix 2 fixture |

---

## 2. Why the failure persists despite half-built wiring

The smoking gun is `spec_builder.py:1113-1139`. The forward-manifest section text **is
constructed** from `forward_contracts` and `forward_element_specs` popped off `context`,
but the resulting `forward_contracts_section` is **not appended to the `prioritized`
list** that `enforce_prompt_budget` evicts from and the template renders from. So even
when the extractor produces a non-empty spec, the drafter prompt does not include it
(at least not at a priority-protected position).

The fix at this seam is a small set of code changes; the **risk** is making sure the
section appears in the right place in the template and is genuinely P0.

---

## 3. Dependency / consumer semantics — confirmed

- **Single-source contract (FR-3, confirmed).** `reviewer.py` calls
  `forward_manifest.validate_implementation()` on the same `ForwardManifest`. Whatever
  the spec_builder renders into the prompt **is** what the reviewer will enforce.
  **Verification is structural, not by code-reading:** pre-Increment-0 task
  `t-validate-impl-read` (R1-S1) reads the method body and produces a one-page note
  pinning the (kind, name, type) shape it consumes; Increment-0 task
  `t-contract-symmetry` (R1-S7) asserts by execution that an "ideal implementation"
  matching the rendered section produces zero violations. R2 (validate_implementation
  body unread) is mitigated by both tasks together; the prose-only mitigation in
  v1.0's §7 R2 has been promoted to a hard pre-Increment-0 gate.
- **End-to-end example with Fix 1 + Fix 2:**
  1. Extractor: `FRAMEWORK_CONFIG_DEFAULTS["next.config.{js,mjs,ts}"]` →
     `ForwardFileSpec(file="next.config.mjs", elements=[ForwardElementSpec(kind=CONSTANT, name="config", type_annotation="NextConfig")], language="nodejs")`.
  2. spec_builder: rendered into P0 section ("File `next.config.mjs` — expected: a
     CONSTANT `config` (type `NextConfig`); export the default").
  3. Drafter: emits `export const config = { … }; export default config;` (or
     equivalent).
  4. Reviewer: `validate_implementation()` finds `CONSTANT` named `config` → ✅.
  5. Integration syntax check: passes (it would have caught only the pathological
     `export class next.config { … }` we saw in run-003 PI-003).

---

## 4. Components

- **NEW (`spec_builder.py`):** append the existing `forward_contracts_section` to
  `prioritized` at **P0**, and add `{forward_manifest_section}` placeholder + the text
  into `format_kwargs` so the YAML template renders it. Tiny diff — the structural fix
  is one append + one placeholder wire-up.
- **NEW (`forward_manifest_extractor.py`):** add `FRAMEWORK_CONFIG_DEFAULTS: dict[pattern,
  ForwardFileSpec]` (module-level), and a small helper that fills missing/empty
  `file_specs` for matching paths inside `DeterministicExtractor.extract()` **after**
  feature-text extraction. Slotted at the "deterministic" tier of `_SOURCE_PRECEDENCE`
  so plan-declared elements naturally win.
- **NEW (tests):** unit test asserting the P0 section is present in the spec prompt and
  not evicted under budget pressure; extractor test asserting `next.config.mjs` →
  non-empty default; integration regression that reproduces PI-003 without an LLM call.
- **NO CHANGE:** `reviewer.py`, `engine.py`, seed schema, workflow stages,
  `prompts/contractor_prompts.yaml` *structure* (just one new fragment).

---

## 5. Iterative delivery (revised by planning)

- **Increment 0 — Fix 1: append + template wire-up.** `spec_builder.py:1113-1139`
  section text added to `prioritized` at P0 + `format_kwargs` placeholder. Tiny diff;
  immediately helps any feature whose plan declares elements. **Independently shippable
  and verifiable.**
- **Increment 1 — Fix 2: framework-conventions registry.**
  `FRAMEWORK_CONFIG_DEFAULTS` + `DeterministicExtractor` seam. Starter set: 4–6 paths.
  Combined with Inc 0, closes the run-003 PI-003 failure mode.
- **Increment 2 — Hardening: regression + audit.** Cross-pattern tests, plan-declared
  override tests (precedence), and a "convention used" marker on emitted specs so the
  postmortem (when Fix 3 from the postmortem ships) can attribute drafter failures.

---

## 6. Task decomposition

| Task | Description | Complexity | Increment | FRs |
|------|-------------|------------|-----------|-----|
| **t-validate-impl-read** *(R1-S1)* | **Pre-Increment-0 gate.** Read `forward_manifest.validate_implementation()` (referenced at `reviewer.py:270`) and produce `docs/design/notes/VALIDATE_IMPLEMENTATION_SHAPE.md`: a one-page note enumerating the (kind, name, type) tuples it consumes from each `ForwardFileSpec.elements[]`, including any match-by-exact-name vs match-by-kind quirks. **Blocks Increment-0 PR open** — CI lints presence of the file as a prerequisite. Without this note, FR-3 is structurally an assumption. | SIMPLE | pre-0 | FR-3 (gate) |
| **t-consumption-map-audit** *(R1-S8)* | **Pre-Increment-0 gate.** Read `src/startd8/implementation_engine/consumption_map.py` and produce `docs/design/notes/CONSUMPTION_MAP_AUDIT.md`: either "read; no coupling with `forward_manifest` found" OR "coupling found at `<file:line>`, mitigation: `<…>`". Five-minute task — documented as an artifact so it isn't silently skipped under PR pressure. | SIMPLE | pre-0 | (R5 mitigation) |
| **t-nfr1-golden** *(R1-S5)* | **Pre-Increment-0 capture (sequencing-critical).** Establish the byte-identical baseline for NFR-1 **before** any `spec_builder.py` diff lands. Curate `tests/regression/no_forward_manifest/*.yaml` with N ≥ 3 fixtures (no `forward_manifest.file_specs`). Run `pytest --record-golden` on the **pre-change commit** (or its merge base) to produce committed `*.sha256` files. Subsequent `--check` runs fail on any drift. Without this captured pre-Fix-1, the baseline already contains Fix 1's output and NFR-1 cannot be falsified. | SIMPLE | pre-0 | NFR-1, FR-8 |
| t-spec-append | `spec_builder.py:1113-1139`: append `forward_contracts_section` to `prioritized` at **P0**; add `{forward_manifest_section}` placeholder + `format_kwargs` wire-up | SIMPLE | 0 | FR-1, FR-4 |
| t-spec-test *(strengthened by R1-S2)* | Unit test in `test_spec_builder.py`: prompt contains the section AND **template render-position ordering is correct** — after `enforce_prompt_budget`, assert `rendered_prompt.index(forward_manifest_section) < rendered_prompt.index(<any surviving P3/P2/P1 section text>)`. Oversize P3/P2/P1 sections to force eviction; assert the forward-manifest text survives at the protected position. Presence alone is necessary but not sufficient — position is part of the contract (FR-1a). | SIMPLE | 0 | FR-1, FR-1a, FR-4, NFR-1, NFR-2 |
| **t-contract-symmetry** *(R1-S7)* | Unit test in `test_spec_builder.py` (or `test_forward_manifest_contract.py`): construct a `ForwardManifest` for `next.config.mjs`, render the spec section, then synthesize an "ideal implementation" matching the rendered shape and assert `validate_implementation(synth_impl) == []` (zero violations). This is the **execution-level verification** of FR-3; it depends on `t-validate-impl-read`'s note to know exactly what the reviewer consumes. | MODERATE | 0 | FR-3, NFR-3 |
| t-fwd-registry *(amended by R1-S4)* | `forward_manifest_extractor.py`: add `FRAMEWORK_CONFIG_DEFAULTS` (module constant or sibling file); helper `apply_framework_defaults(file_specs)`; hook into `DeterministicExtractor.extract()` post-feature-text; integrate with `_SOURCE_PRECEDENCE` at the deterministic tier. **Collision rule:** when the deterministic extractor returns `ForwardFileSpec(elements=[])` for a path that matches a registry entry, the convention's non-empty spec MUST win; empty deterministic output is "no contribution," not "empty success." Implementation: in `apply_framework_defaults`, if the matched path already has a `ForwardFileSpec` with `elements=[]`, replace it with the convention's spec. | MODERATE | 1 | FR-5, FR-6, FR-7 |
| t-registry-content *(pinned per R1-S3 + Tailwind per R1-F7)* | Starter set, with **exact extension lists** (no shell-style wildcards): `next.config.{js,mjs,ts}`, `tsconfig.json`, `package.json`, `prisma/schema.prisma`, `vite.config.{js,ts,mjs,cjs}`, `jest.config.{js,ts,mjs,cjs,json}`, `tailwind.config.{js,ts,mjs,cjs}`. Anchoring: **filename-only** (no path prefix). Documented in registry comments; explicit listing acts as the contract. | SIMPLE | 1 | FR-7 |
| t-extractor-test *(extended for R1-S4)* | Extractor unit tests: (a) empty input → defaults fill matching paths; (b) plan-declared elements override defaults (full-source replace, no merge); (c) **deterministic-empty collision:** deterministic extractor returns `ForwardFileSpec(elements=[])` for `next.config.mjs`; convention non-empty; assert convention's elements survive; (d) pure default-export path: `tailwind.config.js` resolves to sentinel `CONSTANT name="default"` per FR-5. | SIMPLE | 1 | FR-5, FR-6, FR-7, NFR-1 |
| t-pi-003-regression *(split per R1-F8)* | End-to-end fixture that constructs a minimal seed targeting `next.config.mjs`, runs `build_spec_prompt`, with two **independent** pytest cases: **(FR-9a)** plan-declared `file_specs` present → section appears for the target file (asserts Fix 1 active; failure attributes to `t-spec-append`); **(FR-9b)** extractor-only seed (no plan-declared elements) → section is non-empty via `FRAMEWORK_CONFIG_DEFAULTS` (asserts Fix 2 active; failure attributes to `t-fwd-registry` / `t-registry-content`). LLM-free. | MODERATE | 2 | FR-9, FR-9a, FR-9b |
| t-convention-marker *(schema specified per R1-S6)* | Mark file_specs filled by conventions with a provenance field `convention_provenance: {source: "framework-conventions", pattern: <pattern>, version: <registry-version>}` attached to each `ForwardFileSpec` populated by the registry. Carrier field added to the dataclass (or as a sibling dict keyed by file path). Schema **specified now** (not deferred) so Fix 3 (postmortem classifier) can consume it without re-design. | SIMPLE | 2 | FR-7 (provenance) — assists postmortem Fix 3 |

Suggested build order: **pre-0 gates** (`t-validate-impl-read`, `t-consumption-map-audit`, `t-nfr1-golden`) → Increment 0 (`t-spec-append`, `t-spec-test`, `t-contract-symmetry`) → Increment 1 (`t-fwd-registry`, `t-registry-content`, `t-extractor-test`) → Increment 2 (`t-pi-003-regression`, `t-convention-marker`). Each increment remains independently shippable per FR-10; pre-0 gates are one-shot prerequisites whose artifacts live in `docs/design/notes/`.

---

## 7. Risks

- **R1 — Template position vs. budget protection.** P0 protection is on the
  `prioritized` list. If the template renders `{forward_manifest_section}` at a position
  the budget can't enforce, the section could still drop or be visually deprioritized
  by the LLM. **Mitigation (strengthened by R1-S2):** the test (`t-spec-test`)
  explicitly oversizes P3/P2/P1 sections and asserts both **presence and
  render-position ordering** — `prompt.index(forward_manifest_section)` must be less
  than `prompt.index(any surviving lower-priority section)`. Position is now part of
  the contract (FR-1a), not just an implementation detail.
- **R2 — `validate_implementation()` not directly read.** The reviewer calls
  `forward_manifest.validate_implementation()` (referenced at `reviewer.py:270`) but the
  method body wasn't sighted in the planning read. **Mitigation (promoted to task per
  R1-S1 + R1-S7):** pre-Increment-0 task `t-validate-impl-read` produces a written note
  enumerating the (kind, name, type) tuples the method consumes; Increment-0 task
  `t-contract-symmetry` executes the structural assertion that an "ideal
  implementation" matching the rendered section produces zero violations. The
  prose-only mitigation in v1.0 has been replaced by a CI-enforced artifact gate +
  execution-level test.
- **R3 — Missing `DEFAULT_EXPORT` kind.** `ElementKind` has no first-class
  default-export concept. **Mitigation:** model Next.js config via `CONSTANT name="config"`
  (matches the `export const config = …; export default config` pattern). Pure
  default-export files (e.g. `tailwind.config.*`) use the sentinel `CONSTANT
  name="default"` documented in REQUIREMENTS FR-5; `t-extractor-test` case (d)
  verifies this. If a target later genuinely needs *only* `export default <obj>` with
  no name aliasing, add a `DEFAULT_EXPORT` kind as a separate, scoped change — do not
  stretch this scope.
- **R4 — Registry sprawl.** Frameworks proliferate. **Mitigation:** starter set caps the
  scope; the registry is small, auditable plain data; expansion is explicitly iterative
  (FR-7). The pinned-extension rule (R1-S3) — exact extension lists, not shell
  wildcards — limits silent scope expansion via globs.
- **R5 — Hidden coupling between `consumption_map.py` and these paths.** (promoted to
  task per R1-S8) `consumption_map.py` is named like a consumer but doesn't reference
  `forward_manifest` today. **Mitigation:** pre-Increment-0 task `t-consumption-map-audit`
  produces a written note (`docs/design/notes/CONSUMPTION_MAP_AUDIT.md`) confirming
  either no coupling or a specific mitigation. Prose mitigations get skipped under PR
  pressure; an artifact does not.
- **R6 — Override granularity ambiguity (new, surfaced by R1-F6).** Without an explicit
  rule, "plan-declared overrides convention" is ambiguous between full-source replace
  and per-element merge. **Mitigation:** REQUIREMENTS FR-6 now pins **full-source
  override** (no per-element merge in MVP). `t-extractor-test` case (b) verifies this.
  Per-element merge can be added later as a separate, scoped change if a real need
  emerges.
- **R7 — Deterministic-empty silent-poison (new, surfaced by R1-S4).** Without an
  explicit collision rule, a deterministic extractor returning `elements=[]` at the
  same precedence tier as the convention could silently overwrite the convention's
  non-empty spec depending on iteration order. **Mitigation:** §1 source-precedence row
  + `t-fwd-registry` implement the rule "convention wins over deterministic-empty";
  `t-extractor-test` case (c) verifies this. This is the canonical silent failure mode
  for the design and is now closed by construction.

---

## 8. Discoveries (feed REQUIREMENTS §0)

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Fix 1 needs a new P0 section to be designed and inserted | The forward-manifest section is **already constructed** at `spec_builder.py:1113-1139`; it is just **not appended to `prioritized`**. Fix 1 is a tiny diff, not new design | **FR-1** narrows to "append + wire" |
| spec_builder needs `task_id` to look up file_specs | `file_specs_for_task(task_id, target_files)` ignores `task_id`; `target_files` is already in `context` (`spec_builder.py:1168`) | OQ-2 resolved — no new mapping work |
| Prompt templating may be ad hoc | Standard pattern: YAML template + `format(**format_kwargs)`; one placeholder + one kwarg suffices | OQ-3 resolved |
| Reviewer/spec contract drift is a risk | Reviewer calls `forward_manifest.validate_implementation()` on the **same** manifest — single source | OQ-4 resolved; FR-3 satisfied by construction |
| `ElementKind` includes a default-export concept | It does **not** — kinds are function/class/method/property/constant/variable | **FR-5 (Fix 2)** must model `next.config.mjs` as `CONSTANT name="config"`; defer a `DEFAULT_EXPORT` kind |
| Merge semantics for plan-declared vs convention need bespoke logic | `_SOURCE_PRECEDENCE` already handles it: framework defaults sit at "deterministic"; human-YAML overrides win for free | OQ-7 resolved — no new merge code |
| Path-pattern registry needs new design | Mirror `path_language_hints_from_file_specs` (`forward_manifest.py:748`) | OQ-8 resolved |
| Regression test needs an LLM call | A fixture can run `build_spec_prompt()` directly and assert section presence (LLM-free) | FR-9 simplified; t-pi-003-regression is MODERATE not COMPLEX |

---

*Plan 1.0 — paired with REQUIREMENTS v0.2. Implementation begins only after requirements
are confirmed and optional Convergent Review is done.*

*Plan 1.1 — R1 CRP triage applied. All 8 R1 suggestions (R1-S1..R1-S8) ACCEPTed: three
pre-Increment-0 gates added (`t-validate-impl-read`, `t-consumption-map-audit`,
`t-nfr1-golden`); `t-spec-test` strengthened with render-position ordering;
`t-contract-symmetry` added to Increment 0; `t-registry-content` pinned to exact
extensions + Tailwind; `t-fwd-registry` + §1 source-precedence row pin the
deterministic-empty collision rule; `t-extractor-test` extended with merge-vs-replace
+ collision + sentinel cases; `t-pi-003-regression` split into FR-9a/FR-9b cases;
`t-convention-marker` schema specified up-front. Two new risks R6 (override granularity)
and R7 (deterministic-empty silent-poison) added with their mitigations. Coverage Matrix
updated with R1-triaged column. Dispositions persisted in Appendix A. Paired with
REQUIREMENTS v0.3.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}` for plan).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Add pre-Increment-0 task `t-validate-impl-read` (gated artifact: shape note for `validate_implementation()`) | R1 / claude-opus-4-7-1m | Applied to **§6 Task decomposition** as new pre-0 task; **§7 R2** upgraded from prose mitigation to task-backed gate; **§3** bullet 1 updated to reference both `t-validate-impl-read` and `t-contract-symmetry`. Artifact path: `docs/design/notes/VALIDATE_IMPLEMENTATION_SHAPE.md`. | 2026-05-29 |
| R1-S2 | Strengthen `t-spec-test` to assert template render-position ordering (not just substring presence) | R1 / claude-opus-4-7-1m | Applied to **§6 t-spec-test** description: added ordering assertion `index(forward_manifest_section) < index(any surviving lower-priority section)`; **§7 R1** mitigation strengthened. Pairs with REQUIREMENTS FR-1a (R1-F2) which makes the position a contract. | 2026-05-29 |
| R1-S3 | Pin starter-set globs to exact extension lists with filename anchoring | R1 / claude-opus-4-7-1m | Applied to **§6 t-registry-content**: replaced `vite.config.*` / `jest.config.*` shell globs with `vite.config.{js,ts,mjs,cjs}` / `jest.config.{js,ts,mjs,cjs,json}`; documented filename-only anchoring. REQUIREMENTS FR-7 + OQ-6 updated in parallel. R4 (registry sprawl) mitigation strengthened. | 2026-05-29 |
| R1-S4 | Specify deterministic-empty vs convention-non-empty collision rule (convention wins) | R1 / claude-opus-4-7-1m | Applied to **§1 source-precedence row** (collision rule appended); **§6 t-fwd-registry** description (implementation hook); **§6 t-extractor-test** case (c) added (verification); **§7 R7** added as a new risk fully closed by this rule. REQUIREMENTS FR-6 carries the parallel codification. Canonical silent-poison failure mode now closed by construction. | 2026-05-29 |
| R1-S5 | Add `t-nfr1-golden` task with pre-Fix-1 capture sequencing constraint | R1 / claude-opus-4-7-1m | Applied to **§6 Task decomposition** as new pre-0 task; sequencing-critical (baseline must be captured **before** the `spec_builder.py` diff lands). REQUIREMENTS NFR-1 carries the SHA-256 hash test spec + fixture directory. Without this captured pre-Fix-1, NFR-1 cannot be falsified. | 2026-05-29 |
| R1-S6 | Define `convention_provenance` schema for `t-convention-marker` up front | R1 / claude-opus-4-7-1m | Applied to **§6 t-convention-marker** description: schema `{source: "framework-conventions", pattern, version}` specified now. Carrier field decision (dataclass field vs sibling dict) deferred to implementation but schema is the contract. Fix 3 (postmortem classifier) can now build against a stable shape. | 2026-05-29 |
| R1-S7 | Add `t-contract-symmetry` task to Increment 0 (depends on R1-S1's note) | R1 / claude-opus-4-7-1m | Applied to **§6 Task decomposition** as new Increment-0 task (MODERATE); pairs with `t-validate-impl-read`. **§3** bullet 1 references it. Asserts FR-3 by execution (`validate_implementation(synth_impl_matching_section) == []`), not by reading code. | 2026-05-29 |
| R1-S8 | Convert R5 (consumption_map coupling) from prose mitigation to discrete `t-consumption-map-audit` task | R1 / claude-opus-4-7-1m | Applied to **§6 Task decomposition** as new pre-0 task; **§7 R5** updated to reference the task + artifact path (`docs/design/notes/CONSUMPTION_MAP_AUDIT.md`). Five-minute task survives PR pressure as a committed artifact. | 2026-05-29 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet — all R1 suggestions accepted) |  |  |  |  |

### Substantially-Addressed Tracker (R1)

Topics that subsequent rounds should **not** re-litigate without new information — they were considered and resolved in R1 triage:

- **`validate_implementation()` body never read** — Closed: pre-0 gate `t-validate-impl-read` (R1-S1) + Increment-0 task `t-contract-symmetry` (R1-S7) execute the structural verification.
- **Template render-position vs P0 budget protection** — Closed: `t-spec-test` ordering assertion (R1-S2) + REQUIREMENTS FR-1a (R1-F2).
- **Starter-set globs being shell-style wildcards** — Closed: `t-registry-content` pins exact extensions (R1-S3) + REQUIREMENTS FR-7/OQ-6 updated in parallel.
- **Deterministic-empty vs convention-non-empty silent-poison** — Closed: §1 source-precedence row + `t-fwd-registry` implementation + `t-extractor-test` case (c) (R1-S4) + REQUIREMENTS FR-6 codification + §7 R7 risk added.
- **NFR-1 byte-identical unfalsifiable** — Closed: `t-nfr1-golden` task with pre-Fix-1 capture sequencing (R1-S5) + REQUIREMENTS NFR-1 SHA-256 spec.
- **`convention_provenance` schema deferred (dead-code risk)** — Closed: schema pinned now in `t-convention-marker` description (R1-S6).
- **R5 `consumption_map.py` coupling skippable under PR pressure** — Closed: `t-consumption-map-audit` task with committed artifact (R1-S8).
- **Override granularity (replace vs merge) ambiguity** — Closed: REQUIREMENTS FR-6 pins full-source override + §7 R6 risk added + `t-extractor-test` case (b) verifies.

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-7-1m — 2026-05-29

> **Status: TRIAGED 2026-05-29 — all 8 suggestions ACCEPTED.** Dispositions recorded in Appendix A. Two new risks (R6, R7) added to §7. Substantially-Addressed tracker updated. Do not re-propose these in a later round without new information.

- **Reviewer**: claude-opus-4-7-1m
- **Date**: 2026-05-29 23:00:00 UTC
- **Scope**: Plan review — sequencing of R2 (`validate_implementation` body), template-position protection (R1), starter-set audit (FR-7), `_SOURCE_PRECEDENCE` reuse safety (FR-6), NFR-1 testability, FR coverage completeness.

**Executive summary**

- R2 mitigation ("before code, read that method") is informal — there is no hard pre-Increment-0 task gating the work; FR-3 is structurally an assumption until that read happens.
- R1's mitigation rests entirely on `t-spec-test`; the test asserts presence under oversized lower-priority sections but does not assert **render-position ordering** in the template — a P0 section rendered *after* a P3 section in the template body still satisfies presence but violates the budget guarantee's intent.
- Starter set (`t-registry-content`) is plausible but uses ambiguous globs (e.g., `vite.config.*`, `jest.config.*`) without specifying anchoring / extension scope (`.js|.ts|.mjs|.cjs|.json`?) — runtime matching behavior should be pinned.
- `_SOURCE_PRECEDENCE` deterministic tier is reused for framework defaults, but the plan does not state what happens when the deterministic extractor produces a *worse* spec (e.g., empty `elements`) than the convention — does empty deterministic silently override convention? Needs explicit rule.
- NFR-1 ("byte-identical for non-forward_manifest features") has no plan-level task tying it to a golden-file regression harness.
- `t-convention-marker` is justified by a future Fix 3 but the data shape of the provenance field is undefined — risks an ad-hoc field that the future classifier cannot consume.
- Task coverage: FR-2 (graceful degradation + diagnostic log) is not bound to a plan task. FR-8 (no regression) is implicit in NFR-1 tests but has no dedicated task. FR-10 (independent shippability of increments) lacks a verification step (e.g., a CI matrix that runs Increment 0 alone and asserts behavior).
- R5 ("hidden coupling with `consumption_map.py`") is a pre-Increment-0 read but is not modeled as a task with an output artifact — could be skipped under time pressure.
- Single-source contract end-to-end test (FR-3 + R2) deserves a `t-contract-symmetry` task in Increment 0.

**Numbered suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | Add a hard **pre-Increment-0 task** `t-validate-impl-read` that reads `forward_manifest.validate_implementation()` and produces a one-page note enumerating the (kind, name, type) shape it consumes from each `ForwardFileSpec.elements[]`. Block Increment 0 start until this note exists and is referenced by the test plan. | §7 Risk R2 says "before code, read that method" — but this is not a task in §6 and could be skipped. The whole single-source contract (FR-3) is structurally an assumption until that body is read; if `validate_implementation()` matches by exact-name-and-kind and the convention emits `name="config"` while reviewer expects `name="default"`, Fix 2 silently fails the symmetry test. | §6 Task decomposition, new row before `t-spec-append`; reference in §7 R2 mitigation | The note is an artifact (markdown in repo) reviewed before Increment 0 PR is opened; CI lints presence of the file as a prerequisite. |
| R1-S2 | Risks | high | Strengthen `t-spec-test` to assert **template render-position ordering**, not just substring presence. Specifically: after `enforce_prompt_budget`, assert that the index of the forward-manifest section text in the final rendered prompt is **less than** the index of any P3/P2/P1 section that survived. | §7 R1's mitigation relies on this test, but presence is necessary, not sufficient. If `{forward_manifest_section}` is placed near the end of the YAML template body (e.g., after a "guidance" P3 block), the budget guarantee is moot because the section can be cut by downstream token clamping or simply visually deprioritized by the LLM. | §6 t-spec-test row "Description" column; add ordering assertion to test body | `assert prompt.index(forward_manifest_section) < prompt.index(lowest_priority_surviving_section)`; failing the assertion forces template repositioning before merge. |
| R1-S3 | Data | medium | Pin starter-set globs in `t-registry-content` to **exact extension lists**, not shell-style wildcards. E.g., replace `vite.config.*` with `vite.config.{js,ts,mjs,cjs}` and `jest.config.*` with `jest.config.{js,ts,mjs,cjs,json}`. Document anchoring: filename-only or path-relative? | Ambiguous globs are a footgun: `vite.config.*` could match `vite.config.bak` after editor save. The registry is the contract — explicit beats clever. | §6 `t-registry-content` Description column | Extractor unit test enumerates the matched-vs-not-matched paths for each pattern; explicit listing acts as the spec. |
| R1-S4 | Architecture | high | Specify the **precedence collision rule** for "deterministic empty vs convention non-empty". Add a sub-bullet to §1 (Source precedence row) and §6 `t-fwd-registry`: when the deterministic extractor produces an empty `elements[]` for a target path that also matches a `FRAMEWORK_CONFIG_DEFAULTS` entry, the convention MUST win (do not let empty deterministic "successfully" overwrite a non-empty convention). | The plan asserts plan-declared overrides win "for free" via `_SOURCE_PRECEDENCE`, but does not address the symmetric concern: a deterministic extractor that succeeds with empty output is technically at the same tier as the convention. Whichever runs second wins by default, and that ordering is not spelled out. This is the canonical silent-poison failure mode for this design. | §1 Source precedence row + §6 `t-fwd-registry` extractor hook description | Add an extractor unit test: deterministic extractor returns `ForwardFileSpec(elements=[])` for `next.config.mjs`; convention returns non-empty; assert convention's elements survive. |
| R1-S5 | Validation | medium | Add a `t-nfr1-golden` task to Increment 0 that establishes the **pre-Fix-1 byte-identical baseline** for the no-`forward_manifest` regression set. Without this captured before the diff lands, NFR-1 cannot be falsified after the change. | Capturing the golden file is a one-shot operation that must happen *before* the spec_builder diff, otherwise the baseline already includes Fix 1's output. The plan does not call this out as a sequencing requirement. | §6 Task decomposition, new row before `t-spec-append`; or amend `t-spec-test` to capture baseline as a prerequisite | CI job: `pytest tests/regression/no_forward_manifest --record-golden` produces `*.sha256`; subsequent runs in `--check` mode fail on drift. Run record-golden once on the pre-change commit (or its merge base) and commit the hashes. |
| R1-S6 | Ops | medium | Define the **schema for the "convention used" provenance marker** (`t-convention-marker`) up front, even though Fix 3 (postmortem classifier) ships separately. Minimum: `{source: "framework-conventions", pattern: <pattern>, version: <registry-version>}` attached to each ForwardFileSpec it populated. Specify the carrier field on the dataclass. | If Fix 3 cannot rely on a stable schema, the marker becomes dead code. The plan commits to the marker but defers the design — the cheap fix is to spec the schema now so Increment 2 ships something Fix 3 can actually consume. | §6 `t-convention-marker` row Description column | Unit test on `forward_manifest_extractor` asserts presence and schema of provenance dict on convention-populated specs. |
| R1-S7 | Architecture | medium | Add `t-contract-symmetry` to Increment 0 (depends on R1-S1's `t-validate-impl-read`): a unit test that constructs a `ForwardManifest` for a known target file, renders the spec section, and asserts that calling `validate_implementation()` on a synthetic "ideal implementation" matching the rendered shape produces **zero violations**. | This is the structural verification of FR-3 (single-source contract). Without it, the contract is asserted only by code reading, not by execution. The reviewer's behavior is the ground truth; the spec section must produce an implementation it will accept. | §6 Task decomposition, between `t-spec-test` and `t-fwd-registry`; reference in §3 (Dependency / consumer semantics) bullet 1 | Test asserts: `validate_implementation(synthesized_impl_matching_spec_section) == []` (no violations) for at least the `next.config.mjs` fixture from §3 walkthrough. |
| R1-S8 | Risks | low | Convert R5 ("Hidden coupling with `consumption_map.py`") from a prose mitigation into a discrete pre-Increment-0 task `t-consumption-map-audit` that produces a short note: "read; no coupling found" OR "coupling found at <file:line>, mitigation: <…>". | Prose risks are easy to skip during PR pressure. A 5-minute read documented as an artifact is harder to silently drop. | §6 Task decomposition, new row alongside R1-S1's pre-Increment-0 tasks | Artifact: `docs/design/notes/CONSUMPTION_MAP_AUDIT.md` committed in the same PR as Increment 0. |

**Endorsements**: (none — R1 is the first round; no prior untriaged suggestions.)

**Disagreements**: (none — first round.)

---

## Requirements Coverage Matrix — R1 (R1-triaged 2026-05-29)

Analysis only (not triage in itself). Maps each requirement in `FORWARD_MANIFEST_DRAFT_TIME_REQUIREMENTS.md` (v0.3 post-triage) to plan section(s)/task(s) and assesses coverage. The "Post-R1" column reflects coverage after R1 triage was applied; gaps the matrix flagged are linked to their closing suggestion ID.

| Requirement Section | Plan Step(s) / Task(s) | Coverage (R1 baseline) | Post-R1 status | Gaps |
| ---- | ---- | ---- | ---- | ---- |
| FR-1 (spec_builder injects P0 section) | §4 Components (NEW `spec_builder.py`); §6 `t-spec-append` | Full | Full | — |
| FR-1a (render-position ordering — NEW v0.3) | §6 `t-spec-test` (strengthened); §7 R1 | n/a (new) | Full | Closed by R1-F2 (FR) + R1-S2 (plan). |
| FR-2 (graceful degradation + structured diagnostic log) | §4 Components (implicitly); no dedicated task | Partial | Full | Closed by R1-F5: FR-2 now specifies event name `forward_manifest.section.empty`, severity INFO, fields `{target_files, reason}`. Implementation-side task captured under `t-spec-append` (the fallback path lives at the same seam). |
| FR-3 (single-source contract + acceptance criterion) | §3 bullet 1; §6 `t-validate-impl-read` (NEW pre-0); §6 `t-contract-symmetry` (NEW Inc 0); §7 R2 | Partial | Full | Closed by R1-S1 + R1-S7 + R1-F1: both producer-side note and execution-level symmetry test are now task-gated. |
| FR-4 (token budget respected; P0 stays in) | §4 Components (budget reused as-is); §6 `t-spec-test` (oversizes P3/P2/P1) | Full | Full | — |
| FR-5 (framework-conventions registry, `CONSTANT name="config"`) | §3 E2E walkthrough; §4 Components (NEW extractor); §6 `t-fwd-registry`; §7 R3 mitigation | Full | Full | R1-F3: pure default-export rule added to FR-5 + verified by `t-extractor-test` case (d). |
| FR-6 (plan-declared overrides via `_SOURCE_PRECEDENCE`; full-source granularity; deterministic-empty collision) | §1 Source precedence row (collision rule added); §6 `t-fwd-registry` (implementation hook); §6 `t-extractor-test` cases (b)(c); §7 R6 + R7 (new risks) | Partial | Full | Closed by R1-F6 (granularity = full-source) + R1-S4 (collision rule = convention wins over deterministic-empty). |
| FR-7 (small auditable starter set, pinned extensions) | §6 `t-registry-content` (pinned per R1-S3); FR-7 starter set incl. Tailwind | Partial | Full | Closed by R1-S3 (exact extensions) + R1-F7 (Tailwind added). |
| FR-8 (no regression) | NFR-1 implies; §6 `t-nfr1-golden` (NEW pre-0) | Partial | Full | Closed by R1-S5: golden-file harness is the no-regression verification surface. |
| FR-9 (LLM-free regression — now split into FR-9a/FR-9b) | §6 `t-pi-003-regression` (split per R1-F8) | Full | Full | R1-F8: split clarifies fault attribution per increment; supports FR-10 independent shippability. |
| FR-10 (iterative delivery; Fix 1 first, then Fix 2) | §5 Iterative delivery; §6 Suggested build order; FR-9a/FR-9b independent CI cases | Partial | Full | Closed by FR-9 split (R1-F8): each increment now has a dedicated test case that runs independently. |
| NFR-1 (byte-identical, golden-file enforced) | §6 `t-nfr1-golden` (NEW pre-0); §6 `t-spec-test` | Partial | Full | Closed by R1-F4 + R1-S5: SHA-256 golden harness with pre-Fix-1 capture sequencing. |
| NFR-2 (token budget never exceeded; P0 stays in) | §6 `t-spec-test` | Full | Full | — |
| NFR-3 (determinism: same seed → same prompt) | §6 `t-contract-symmetry` (touches determinism path); §6 `t-nfr1-golden` (golden-hash equality implies determinism) | Partial | Substantially full | The golden-file harness (R1-S5) re-running on the same input would fail any nondeterminism; explicit two-run determinism test remains a low-risk future addition, not a blocker. |
| NFR-4 (zero LLM cost in Fix 2 registry) | §4 Components (registry is plain data) | Full | Full | — |
| NFR-5 (auditable registry; version-stamped) | §6 `t-registry-content` (plain data); §6 `t-convention-marker` (schema includes `version` field); §7 R4 | Partial | Full | Closed by R1-S6: `convention_provenance.version` field pins the version-stamp shape; registry version is now part of the provenance schema, not a deferred decision. |
