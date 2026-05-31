# Multi-Language Manifest Validation — Requirements

**Version:** 0.3 (CRP Round R1 triaged & applied — all 10 F-suggestions accepted)
**Date:** 2026-05-30
**Status:** Post-exploration (v0.2) + independent CRP Round R1 — all 10 F-suggestions ACCEPTED and
merged; OQ-5/OQ-6 resolved. Reviewed against the languages/ parsers + `code_manifest` + `forward_manifest_validator`
**Component:** startd8 SDK — `utils/code_manifest.py`, `languages/*_parser.py`,
`forward_manifest.py` (`validate_implementation`), `forward_manifest_validator.py`
**Goal:** Make `ForwardManifest.validate_implementation`'s registry-building **language-agnostic**:
any language that cannot use the Python AST gets element-level contract enforcement via the best
available parser already in the repo, so the draft→review contract is symmetric across languages.
Closes the two deferred gaps: a real `DEFAULT_EXPORT` `ElementKind` and JS/TS config enforcement.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between the naive v0.1 view ("we need to build/integrate parsers for each
> language and feed them into the registry") and v0.2, after reading `languages/` + `code_manifest`.

| v0.1 Assumption | Exploration Discovery | Impact |
|-----------------|----------------------|--------|
| We must build/integrate language parsers | **They already exist:** `parse_csharp_source`, `parse_go_source`, `parse_java_source`, `parse_nodejs_source`, `parse_vue_sfc_script_elements` — each returns `kind`+`name` elements | Scope = **adapter + dispatch**, not parser construction (FR-1/FR-2) |
| All parsers are AST-grade | **Fidelity tiers:** C# = tree-sitter, Java = javalang (both AST-grade); **Go + Node/JS/TS = regex-only** | A regex miss → a false `missing_element`. Severity MUST be calibrated per parser confidence (FR-5) — the central new requirement |
| `DEFAULT_EXPORT` is just an enum value to add | `NodeElement` has **no** default-export field/kind (it regex-matches `export default class` but doesn't model the construct) | DEFAULT_EXPORT needs a **parser enhancement** in `nodejs_parser`, not only an enum member (FR-3/FR-4) |
| Extend `generate_file_manifest` to dispatch | It is **Python-AST-specific and used in 9 files** | Add a **new** multi-language builder; leave `generate_file_manifest` as the Python path (FR-1, NFR-1) |
| `ElementKind` covers the languages | Missing `interface`, `enum`, `struct`, `record`, `field`, `default_export` (parsers emit these `kind` strings) | Need a kind-mapping policy: expand the enum vs map-to-nearest (FR-3, OQ-1) |
| Only `validate_implementation` needs this | `lead_contractor_workflow._review_draft` builds the **same** registry with the same `extract_multi_file_code` + `generate_file_manifest` pattern (Python-only) | The builder is reused by both; subsumes the earlier "lead-contractor consolidation" follow-up (FR-7) |
| Validation = "element present?" | `_validate_file_spec` matches on **name** (kind only labels the violation) and also checks **imports** | Adapter must populate `name` reliably + imports per language; kind fidelity is secondary but drives `DEFAULT_EXPORT` (FR-2) |

**Resolved open questions:**
- **OQ-1 → Expand `ElementKind` additively** with `DEFAULT_EXPORT` (required) and the language-native
  kinds the parsers already emit (`INTERFACE`, `ENUM`, `STRUCT`, `RECORD`, `FIELD`) so the adapter is
  lossless and no language kind silently collapses. Additive = backward-compatible (NFR-2).
- **OQ-2 → Dispatch by a small `extension → parser-adapter` registry** (the per-language parsers are
  standalone module functions, not `LanguageProfile` methods, and the profile protocol exposes no
  parse hook). Keep it colocated with the builder; route Python to the existing `generate_file_manifest`.
- **OQ-3 → Confidence tiers gate severity (FR-5).** AST-grade (Python AST, C# tree-sitter, Java
  javalang) → `missing_element` is an **error** (authoritative). Regex-grade (Go, Node/JS/TS) →
  `missing_element` is a **warning** (advisory; a regex blind spot must not block a review). When a
  parser falls back from AST to regex (C# tree-sitter unavailable), it drops to the regex tier.
- **OQ-4 → Reuse for `lead_contractor_workflow` is in-scope (FR-7)** but additive — both call the new
  builder; behavior for Python is unchanged.

---

## 1. Problem Statement

`ForwardManifest.validate_implementation` (the canonical post-generation contract enforcer, FR-3 of
`FORWARD_MANIFEST_DRAFT_TIME_REQUIREMENTS.md`) builds its `ManifestRegistry` with
`generate_file_manifest`, which parses **Python only**. For every other language it skips the file,
so element/import contract enforcement is **Python-exclusive**. The drafter is shown the contract
for any language (draft-time injection), but at review time only `.py` files are actually checked —
an asymmetry that let the PI-003 `next.config.mjs` shape failure through to a syntax error.

| Language | Draft-time contract (FR-1 inject) | Review-time enforcement today | Parser available |
|----------|-----------------------------------|-------------------------------|------------------|
| Python | ✅ | ✅ (`generate_file_manifest`, AST) | ast (stdlib) |
| C# | ✅ | ❌ skipped | `parse_csharp_source` (tree-sitter) |
| Java | ✅ | ❌ skipped | `parse_java_source` (javalang) |
| Go | ✅ | ❌ skipped | `parse_go_source` (regex) |
| JS/TS/Node | ✅ | ❌ skipped | `parse_nodejs_source` (regex) |
| Vue SFC | ✅ | ❌ skipped | `parse_vue_sfc_script_elements` (regex) |

**Goal:** close the asymmetry — element/import enforcement for every language with a parser, via the
best available parser, with severity calibrated to parser confidence so we never trade Python's
false-negative-free enforcement for false positives elsewhere.

---

## 2. Functional Requirements

- **FR-1 Multi-language manifest builder.** Add a builder (e.g.
  `build_multilang_file_manifest(rel_path, source) -> FileManifest`) that dispatches by file
  extension/language: Python → existing `generate_file_manifest`; C#/Java/Go/Node(JS/TS/JSX/TSX)/Vue
  → the corresponding `parse_*_source` adapted into a `FileManifest` (FR-2). Unknown/unsupported
  extensions return an **empty-but-valid** `FileManifest` (degrade, never raise). *Acceptance:* a
  fixture per supported language yields a `FileManifest` whose `elements` names match the source's
  declared symbols.

- **FR-2 Element + import adapter.** Map each language-native element type
  (`CSharpElement`/`GoElement`/`JavaElement`/`NodeElement`) → the common `Element` (`kind`, `name`,
  `fqn`, `span`, and `signature` where the parser provides it), and populate `FileManifest.imports`
  from the per-language import parsers (`parse_*_imports` where they exist). The mapping is
  **lossless on `name`** (the validator's primary match key) and maps `kind` via FR-3. Parent/child
  nesting (methods under classes) is preserved so `_flatten_elements` finds nested names.

  **Mandatory `Signature` for callable kinds (R1-F1 — critical).** `code_manifest.py:230`
  (`Element._validate_kind_fields`) **raises `ValueError`** when a `FUNCTION`/`ASYNC_FUNCTION`/
  `METHOD`/`ASYNC_METHOD`/`PROPERTY` element has `signature is None`. So the adapter MUST synthesize a
  non-null `Signature` for every callable element — at minimum an empty `Signature` (no params,
  `return_annotation=None`), populated from the parser's raw signature where cheaply available (Go
  exposes params + `return_type`; Java exposes a param list). This is *construction* fidelity, not
  enforcement (see OQ-5). *Acceptance (added):* constructing `Element(kind=FUNCTION, signature=None)`
  raises; the adapter never does so for any fixture — every callable element it emits carries a
  `Signature`.

  **Per-language import coverage (R1-F8).** `_validate_file_spec` checks `spec.imports` against
  `file_manifest.imports`, so a language whose adapter yields **no** imports would false-flag
  `missing_import` if a contract declares imports for it. The §1 table MUST record, per language,
  whether an import parser exists (`parse_java_imports`, `parse_go_imports`, `parse_nodejs`… —
  verify on disk); where none exists, the adapter yields an **empty** import list AND contract
  authors are warned not to declare `imports` for that language until an import parser lands.
  *Acceptance:* a per-language fixture asserts `imports` is populated where a parser exists.

- **FR-3 `ElementKind` expansion (additive) + explicit non-colliding kind-map (R1-F5).** Add only
  the kinds that do **not** already exist: `DEFAULT_EXPORT` (required for FR-4), `INTERFACE`, `ENUM`,
  `STRUCT`, `RECORD`, `FIELD`. **`TYPE_ALIAS` already exists** in `ElementKind` — do NOT re-add it
  (duplicate-member risk). Ship a single documented `kind`-string → `ElementKind` map that is
  **total** (every string the five parsers emit has exactly one target) and **non-colliding** (no
  string maps twice, no enum value defined twice):

  | parser `kind` string | → `ElementKind` |
  |----------------------|-----------------|
  | `function`, `const_function` | `FUNCTION` |
  | `method` | `METHOD`; `constructor` → `METHOD` |
  | `class` | `CLASS` |
  | `interface` | `INTERFACE` (new) · `enum` → `ENUM` (new) · `struct` → `STRUCT` (new) · `record` → `RECORD` (new) |
  | `field` | `FIELD` (new) · `constant` → `CONSTANT` · `variable`/`property` → `VARIABLE`/`PROPERTY` |
  | `type_alias` | `TYPE_ALIAS` (**already exists** — map, don't add) |
  | (node default export) | `DEFAULT_EXPORT` (new, via FR-4) |

  *Acceptance:* a test asserts each parser's emitted `kind` set ⊆ map keys, every map value ∈
  `ElementKind`, and no `ElementKind` member is defined twice (no `KeyError`, no silent drop, no dup).

- **FR-4 Real default-export support (closes gap 1 + 2).** `nodejs_parser` (and Vue script parsing)
  MUST emit a `DEFAULT_EXPORT` element for `export default <expr>` / `module.exports = <expr>`,
  carrying the bound name when one exists (`const config = …; export default config` → name
  `config`) or a sentinel (`default`) for anonymous default exports (`export default defineConfig(…)`).
  The framework-conventions registry (Fix 2, `forward_manifest_extractor`) switches its config
  entries from the sentinel `CONSTANT name="default"` to `DEFAULT_EXPORT`, so the injected contract
  and the extracted element match exactly. *Acceptance:* `next.config.mjs` / `tailwind.config.js`
  fixtures yield a `DEFAULT_EXPORT` element; the framework-default for those paths is `DEFAULT_EXPORT`;
  a drafted default-export config validates clean while a `export class config` draft yields a
  violation.

  **Migration window for the registry switch (R1-F6).** Changing the framework-conventions registry
  from `CONSTANT name="default"` to `DEFAULT_EXPORT` alters a **shipped extraction path** — a
  half-applied switch (extraction emits `DEFAULT_EXPORT` but in-flight contracts still carry
  `CONSTANT name="default"`, or vice-versa) would spuriously flag `missing_element` on every config
  file. Resolve with a **clean cutover**: switch contract-emission (the framework registry) and the
  node extractor in the **same change**, and have the validator treat `DEFAULT_EXPORT` and the legacy
  sentinel `CONSTANT name="default"` as **equivalent for matching** during a documented transition
  (or assert no pre-switch contracts persist). *Acceptance:* a contract carrying the old sentinel
  still validates against a `DEFAULT_EXPORT`-extracted element (equivalence), OR the doc states a
  clean cutover and a test asserts no persisted contract uses the old sentinel.

- **FR-5 Parser-confidence severity calibration (the crux).** Element/import violations are severity-
  calibrated to how much we trust the parser that produced the manifest.

  **Tier is a property of the *parse result*, not the language (R1-F4).** *Authoritative* = the
  parse used an AST-grade backend (Python `ast`, C# tree-sitter, Java javalang). *Advisory* = the
  parse used a regex backend (Go, Node/JS/TS, Vue) **or an AST parser that fell back to regex at
  runtime** (e.g. tree-sitter unavailable for that C# file). The builder stamps the tier on each
  parse, so a tree-sitter-unavailable C# file is correctly advisory for that parse.

  **Wiring seam (R1-F2 — the missing interface).** `_validate_file_spec` today hardcodes
  `severity="error"` (`forward_manifest_validator.py:78/97/117`). The tier MUST reach the validator:
  stamp the parse tier onto the `FileManifest` (e.g. `FileManifest.parser_tier`) and have
  `_validate_file_spec` emit `severity="error"` for authoritative and `severity="warning"` for
  advisory. (Chosen seam: manifest-carried tier, since the validator already receives the manifest.)

  **Blocking predicate (R1-F3).** "Never blocks" is defined against the consumer: the reviewer's
  blocking set is `[v for v in violations if v.severity == "error"]` (`reviewer.py`), so a `warning`
  is excluded from blocking by construction. The requirement asserts this predicate explicitly.

  **Provenance on the violation (R1-F9).** Advisory violations MUST carry a `tier`/`confidence`
  field on the `ContractViolation` payload (not just the `severity` label), so the Fix-3/Kaizen
  classifier can *discount* a regex blind spot rather than misattribute it as a real defect. (Note:
  §4 excludes `ForwardFileSpec`/`InterfaceContract` schema changes; `ContractViolation` is a separate
  type and is explicitly **in scope** for this additive field.)

  *Acceptance:* (a) an advisory-tier missing element yields `ContractViolation.severity=="warning"`
  with `tier=="advisory"`; an authoritative-tier miss yields `"error"`; (b) a blob with only advisory
  warnings passes the reviewer gate (zero blocking, non-zero warnings); (c) simulating tree-sitter
  import failure downgrades a C# miss from `error` to `warning` (per-parse tiering); (d) a Fix-3
  fixture confirms an advisory violation is discounted.

- **FR-6 `validate_implementation` uses the builder.** Replace the Python-only path (and the current
  non-`.py` skip) in `forward_manifest.validate_implementation` with FR-1's builder. Parse-error
  files are still skipped (no false `missing_element` for unparseable code, per the existing rule).
  Non-supported languages degrade to no-op exactly as today. *Acceptance:* a multi-file blob mixing
  `.py` + `.ts` + `.go` validates each file against its spec, attributing violations per file with
  the FR-5 severity.

- **FR-7 Shared builder (subsumes lead-contractor consolidation).** `lead_contractor_workflow._review_draft`'s
  inline `generate_file_manifest` registry-building adopts the same FR-1 builder, so multi-language
  enforcement is consistent across both the implementation-engine reviewer and the prime/primary
  contractor review gate. Additive: Python behavior unchanged. **Regression guard (R1-F10):** FR-7
  routes a *shipped* gate through new code, so for an all-Python draft the shared builder MUST
  produce a `ManifestRegistry` **byte/structure-identical** to the current inline
  `generate_file_manifest` path. *Acceptance:* a golden-master test compares the registry built via
  the old inline path vs the new builder on a Python-only multi-file blob and asserts equal
  `elements`/`imports`; plus the lead/primary review path enforces a non-Python file's contract via
  the shared builder.

- **FR-8 Iterative, independently-shippable delivery.** Ships per-language: the builder + adapter +
  `ElementKind` expansion + severity tiers land first (enabling all AST-grade languages), then the
  `DEFAULT_EXPORT`/Node enhancement, then advisory-tier languages. Each increment is green on its own.

---

## 3. Non-Functional Requirements

- **NFR-1 No regression for Python.** The Python path remains `generate_file_manifest` unchanged;
  the new builder only *dispatches* to it. Existing `FileManifest` consumers (9 call sites) are
  untouched. Verified by the existing manifest/validation suites staying green.
- **NFR-2 Additive schema.** `ElementKind` additions are append-only; serialization of existing
  manifests round-trips unchanged.
- **NFR-3 No new heavy dependencies by default.** Use parsers already vendored/optional in the repo
  (tree-sitter for C#, javalang for Java, regex for Go/Node). A parser's absence degrades that
  language to its regex fallback or to advisory/no-op — never a hard failure (mirrors the existing
  `try: import javalang / tree_sitter` fallbacks).
- **NFR-4 Determinism + zero LLM cost.** Extraction is pure static parsing; no model calls.
- **NFR-5 Diagnosability.** When the builder falls back a tier (AST→regex) or skips an unsupported
  language, it logs a structured INFO event (language, path, tier/skip-reason) — consistent with the
  FR-2 `forward_manifest.section.empty` diagnostic style.

---

## 4. Non-Requirements

- Does **not** build new language parsers from scratch — it adapts the existing ones (only the
  `nodejs_parser` default-export *enhancement* of FR-4 is new parsing logic).
- Does **not** replace the per-language **syntax** validators (`node --check`, `validate_disk_compliance`);
  those stay for syntax/disk checks. This adds **element** extraction alongside them.
- Does **not** do type-checking, signature/return-type, or semantic contract enforcement for
  non-Python languages (name + kind + import presence only; signature enforcement is a later stretch).
- Does **not** change `ForwardFileSpec`/`InterfaceContract` schemas. (The `ContractViolation` type
  is **separate** and IS in scope for the additive `tier`/`confidence` field — FR-5/R1-F9.)
- Does **not** introduce a runtime dependency on language toolchains being installed (NFR-3).

---

## 5. Phased Delivery — ✅ ALL COMPLETE (2026-05-30, branch `feat/multilang-manifest-validation`)

| Phase | Scope | Gate | Status |
|-------|-------|------|--------|
| **P1** | FR-3 `ElementKind` expansion + the `kind`-string→`ElementKind` map | suite green; map covers all parser kinds | ✅ `09d8b7a9` |
| **P2** | FR-1 builder + FR-2 adapter for the **authoritative** tier (C#, Java) + FR-5 tiers | per-language adapter tests; C#/Java files enforce at `error` | ✅ `18fc2644` |
| **P3** | FR-2 adapter for the **advisory** tier (Go, Node/JS/TS, Vue) at `warning` severity | advisory-tier files enforce at `warning`, no false blocks | ✅ `eb854e7e` |
| **P4** | FR-4 `DEFAULT_EXPORT` node-parser enhancement + framework-registry switch | `next.config`/`tailwind` fixtures validate clean / catch wrong-shape | ✅ `f4b03a96` |
| **P5** | FR-6 wire into `validate_implementation`; FR-7 wire into lead/primary review | mixed-language multi-file blob enforces per file | ✅ `966845ff` |
| **review** | `/code-review --fix`: C# imports (R1-F8), per-parse tiers (R1-F4), never-raise builder (FR-1), DRY | findings applied + tested | ✅ `dec375ed` |

Each phase shipped as a separate commit, green independently (FR-8). New modules:
`src/startd8/languages/manifest_adapter.py`. Tests:
`tests/unit/languages/test_manifest_kind_map.py`, `…/test_multilang_manifest_builder.py`,
plus `TestMultiLanguageEnforcement` in `tests/unit/test_forward_manifest_validate_implementation.py`.
Net effect: `ForwardManifest.validate_implementation` + the lead/primary review path enforce
element + import contracts across Python/C#/Java (authoritative → `error`) and Go/Node/Vue
(advisory → `warning`); `DEFAULT_EXPORT` closes the original PI-003 config-shape gap.

---

## 6. Open Questions

*OQ-1…OQ-4 resolved in §0; OQ-5/OQ-6 resolved by CRP R1 (below).* None remain open.

- **OQ-5 → RESOLVED: synthesize a minimal `Signature` at construction; defer *enforcement* (R1-F1).**
  "Store raw / defer" was **unimplementable** — `Element._validate_kind_fields` (`code_manifest.py:230`)
  raises if a callable element has `signature is None`. So the adapter MUST construct a `Signature`
  for every callable (empty params + `return_annotation=None` minimum, populated from the parser's raw
  signature where cheap — Go has params+return_type, Java has params). Enforcement is still deferred:
  leaving `return_annotation=None` makes `_validate_function_name`'s return-type check no-op, so no
  uneven signature enforcement ships. Structured signature/return-type contracts remain the §4 stretch.
- **OQ-6 → RESOLVED: surface advisory misses as `warning` AND feed diagnostics — tagged with
  `tier`/`confidence` (R1-F7 + R1-F9).** Not suppressed (that would starve the Fix-3 classifier) and
  not log-only (that hides real misses from reviewers). The `tier="advisory"` field on the
  `ContractViolation` (FR-5) lets every consumer — reviewer, human, Fix-3 — discount a regex blind
  spot instead of misattributing it. Authoritative-tier misses still surface as `error`. *(This
  supersedes the v0.2 "diagnostics-only" leaning — the independent review showed a tagged warning is
  strictly more informative than suppression, with the false-positive risk handled by the tag, not by
  hiding.)*

---

*v0.3 — CRP Round R1 (independent review) triaged: all 10 F-suggestions ACCEPTED and merged.
Headline fixes: **R1-F1 (critical)** the adapter MUST synthesize a `Signature` for callable elements
(`Element` rejects `signature=None`) — OQ-5's "defer" was unimplementable, now resolved to
"synthesize-minimal, defer-enforcement"; **R1-F2 (critical)** FR-5 had no tier→severity wiring seam —
now stamped on `FileManifest` and read by `_validate_file_spec`; **R1-F4** tier is per-*parse* (AST
fallback → advisory), not static per-language; **R1-F3** the blocking predicate is named (only
`error` blocks); **R1-F9** advisory violations carry a `tier`/`confidence` field so Fix-3 discounts
regex blind spots; **R1-F5** explicit non-colliding kind-map (`TYPE_ALIAS` already exists — don't
re-add); **R1-F6** clean-cutover migration window for the `DEFAULT_EXPORT` registry switch; **R1-F10**
golden-master guard that the shared builder is byte-identical to the inline path for Python; **R1-F8**
per-language import-coverage matrix; **R1-F7** OQ-6 resolved (surface warning + diagnostics, tagged).
Dispositions in Appendix A; round R1 in Appendix C.*

*v0.2 — Post-exploration self-reflective update. The headline correction: the language parsers
already exist (5 of them), so this is an **adapter + dispatch + severity-calibration** capability,
not parser construction. The central new requirement is **FR-5 confidence tiers** — Go/Node parsers
are regex-based, so their "missing element" must be advisory, never blocking. `DEFAULT_EXPORT` needs a
real `nodejs_parser` enhancement (FR-4), not just an enum value. The builder subsumes the earlier
lead-contractor consolidation follow-up (FR-7). 7 v0.1 assumptions corrected; 4 OQs resolved.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}` for this requirements doc).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Adapter MUST synthesize a `Signature` for callable elements (`Element` rejects `signature=None`) | R1 / opus-4.8-1m | Applied to **FR-2** (mandatory-Signature clause + acceptance) and **OQ-5** (resolved: synthesize-minimal, defer enforcement). | 2026-05-30 |
| R1-F2 | Specify the FR-5 tier→severity wiring seam (`_validate_file_spec` hardcodes `error`) | R1 / opus-4.8-1m | Applied to **FR-5**: tier stamped on `FileManifest.parser_tier`, read by `_validate_file_spec`. | 2026-05-30 |
| R1-F3 | Name the blocking predicate so `warning` "never blocks" is testable | R1 / opus-4.8-1m | Applied to **FR-5**: blocking set = `severity=="error"` (reviewer.py); acceptance (b). | 2026-05-30 |
| R1-F4 | Tier is per-*parse* (AST fallback→regex→advisory), not static per-language | R1 / opus-4.8-1m | Applied to **FR-5**: tier is a property of the parse result; acceptance (c) simulates tree-sitter failure. | 2026-05-30 |
| R1-F5 | Idempotent/non-colliding kind-map; `TYPE_ALIAS` already exists — don't re-add | R1 / opus-4.8-1m | Applied to **FR-3**: explicit total/non-colliding mapping table; only new kinds added. | 2026-05-30 |
| R1-F6 | Define the migration window for the `DEFAULT_EXPORT` registry switch | R1 / opus-4.8-1m | Applied to **FR-4**: clean cutover + legacy-sentinel equivalence during transition; acceptance. | 2026-05-30 |
| R1-F7 | Resolve OQ-6 with a decision criterion + name the Fix-3 consumer | R1 / opus-4.8-1m | Applied to **OQ-6** (resolved: surface warning + diagnostics, tagged). | 2026-05-30 |
| R1-F8 | Document the per-language import-coverage matrix | R1 / opus-4.8-1m | Applied to **FR-2**: import-coverage clause + §1 table note; empty list where no parser. | 2026-05-30 |
| R1-F9 | Add a `tier`/`confidence` field to `ContractViolation` (severity alone is lossy for Fix-3) | R1 / opus-4.8-1m | Applied to **FR-5** + **§4** (ContractViolation is separate from the excluded schemas → in scope). | 2026-05-30 |
| R1-F10 | Golden-master guard: shared builder == inline path for all-Python (FR-7 routes a shipped gate) | R1 / opus-4.8-1m | Applied to **FR-7**: byte/structure-identical registry acceptance. | 2026-05-30 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-05-30

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-30 19:50:00 UTC
- **Scope**: Single-document requirements review. Sponsor-weighted toward FR-5 severity calibration, ElementKind/kind-mapping (FR-3), OQ-5 signature fidelity, OQ-6 advisory suppression, and adapter blast-radius (FR-1/FR-6/FR-7). Suggestions verified against `code_manifest.py`, `forward_manifest_validator.py`, and the four `languages/*_parser.py` modules on disk.

**Executive summary (top risks / gaps):**

- **BLOCKING — `Element` model validator rejects callable elements with no `Signature`.** `code_manifest.py:230` raises `ValueError` if a `FUNCTION/ASYNC_FUNCTION/METHOD/ASYNC_METHOD/PROPERTY` element has `signature is None`. OQ-5's "store raw / defer" leaning is therefore **not viable as written** — the adapter MUST synthesize at least a stub `Signature` for every callable or `Element()` construction throws. FR-2 omits this acceptance criterion entirely.
- **FR-5 has no wiring seam.** `_validate_file_spec` (validator.py:78/97/117) **hardcodes `severity="error"`** for `missing_file`/`missing_element`/`missing_import`. The requirements say advisory-tier emits `warning` but never specify how the per-file confidence tier reaches the validator. This is the crux requirement with an unspecified interface — a traceability gap.
- **Vue parser path is misnamed.** Parser lives in `languages/vue_sfc.py` (`parse_vue_sfc_script_elements`), not a `vue_parser.py`; there is no `go`/`nodejs` parser exposing `parse_*_imports` for all five langs — FR-2's "`parse_*_imports` where they exist" is appropriately hedged but the per-language import-coverage matrix is undocumented.
- **`DEFAULT_EXPORT` framework-registry switch (FR-4) is a behavior change to a shipped path** but is filed under "additive"; mismatch risk between already-emitted contracts using `CONSTANT name="default"` and newly-extracted `DEFAULT_EXPORT` during the transition window is not addressed.
- **OQ-6 left genuinely open** with no decision criterion; downstream Fix-3 classifier dependency means "suppress entirely" could silently degrade a consumer.
- **NodeElement emits `kind` strings (`const_function`, `interface`, `type_alias`)** confirmed on disk; FR-3 map is right but `type_alias` already exists as `ElementKind.TYPE_ALIAS` — the map must not double-add.
- **No acceptance criterion ties FR-5 `warning` to non-blocking behavior** at the gate level — "never blocks" is asserted but the scoring/gate consumer of `warning` severity is not identified.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | critical | Add an FR-2 acceptance criterion: the adapter MUST construct a non-null `Signature` (stub acceptable: empty params + raw signature string preserved in a `raw`/`return_annotation` field) for every callable-kind `Element`, because `code_manifest.py:230` raises `ValueError` when `signature is None` for `FUNCTION/METHOD/PROPERTY` kinds. | OQ-5's "store raw/defer" is unimplementable as written — `Element` construction throws for every Go/Java/C# function. This is the single highest-value gap. | FR-2 acceptance line; add a note to OQ-5 | Unit test: build an `Element(kind=FUNCTION, signature=None)` and confirm it raises; assert adapter never does this for any fixture | 
| R1-F2 | Validation | critical | Specify the **mechanism** by which FR-5 confidence tier reaches `_validate_file_spec` (which today hardcodes `severity="error"` at validator.py:78/97/117). Options: (a) stamp tier onto `FileManifest`/`Element` and have the validator read it; (b) carry a per-path tier map into `validate_implementation`. State the chosen seam. | FR-5 is named "the crux" but the spec gives no interface for tier→severity; an implementer cannot satisfy it without inventing the seam. | FR-5 body + a new "Severity wiring" sub-bullet | Test: an advisory-tier missing element yields a `ContractViolation.severity == "warning"`, authoritative yields `"error"` | 
| R1-F3 | Validation | high | Define what consumes a `warning`-severity violation such that it "never blocks." Identify the gate/scoring path (e.g. `forward_manifest_validator.py:455` counts `error` violations) and assert `warning` is excluded from the blocking count. | "Surfaced, never blocks" (FR-5) is untestable without naming the blocking predicate; otherwise a downstream consumer could still treat `warning` as fatal. | FR-5 acceptance criterion | Test: a blob with only advisory `warning` violations passes the gate (non-zero warnings, zero blocking) | 
| R1-F4 | Risks | high | Add an FR-5 sub-requirement for **per-parse** (not just per-language static) tier demotion: when an AST parser (C# tree-sitter, Java javalang) actually falls back to regex at runtime, the emitted elements for *that parse* drop to advisory. §0/OQ-3 mentions this but FR-5's tier list is presented as static per-language. | Sponsor focus area 1: a tree-sitter-unavailable C# parse is regex-grade for that file and must not block; static per-language tiering would wrongly keep it authoritative. | FR-5 body — make tier a property of the parse result, not the language | Test: simulate tree-sitter import failure; C# missing element downgrades from `error` to `warning` | 
| R1-F5 | Data | high | FR-3 must state that the kind-map is **idempotent / non-colliding**: `type_alias` already maps to existing `ElementKind.TYPE_ALIAS`; do not re-add. Enumerate the full parser→enum table (incl. NodeElement's `const_function`, `interface`, `type_alias`; Go `struct`; Java `record`/`enum`; C# kinds) and assert every emitted string has exactly one target. | FR-3 acceptance ("no KeyError, no silent drop") is met by the map but the doc lists `INTERFACE/ENUM/STRUCT/RECORD/FIELD` as *new* without checking which already exist — `TYPE_ALIAS` exists; risk of a duplicate enum member or a shadowed map entry. | FR-3 — add the explicit mapping table | Test: assert each parser's emitted `kind` set ⊆ map keys, and map values ∈ `ElementKind`; assert no enum value defined twice | 
| R1-F6 | Risks | high | FR-4: specify the **migration window** for the framework-conventions registry switch (`CONSTANT name="default"` → `DEFAULT_EXPORT`). Either switch contract-emission and extraction atomically, or accept both during a transition and document it; otherwise in-flight contracts emitted pre-switch will mismatch post-switch extraction. | FR-4 calls this "additive" but it changes a shipped extraction path (sponsor focus 5 / blast radius); a half-applied switch produces spurious `missing_element` for every config file. | FR-4 acceptance + NFR-1 cross-ref | Test: a contract emitted with the old sentinel still validates against a `DEFAULT_EXPORT`-extracted element (or doc states clean-cutover and asserts no old contracts persist) | 
| R1-F7 | Ops | medium | OQ-6: replace the open question with a decision criterion. Recommend advisory misses **surface as `warning` AND feed diagnostics**, gated behind the NFR-5 structured log, with an explicit statement that Fix-3's classifier reads the warning stream (not the suppressed/log-only path). | Sponsor focus 4: "suppress entirely" risks silently starving the Fix-3 classifier of signal; "log only" hides real misses from reviewers. The doc must pick one and name the consumer. | OQ-6 — convert to a resolved decision with rationale | Test: an advisory miss appears in both the violation list (as `warning`) and the NFR-5 INFO log; Fix-3 fixture sees it | 
| R1-F8 | Interfaces | medium | FR-1/FR-2: document the **import-coverage matrix** — which languages expose a `parse_*_imports` and what `FileManifest.imports` is for languages that do not (empty list vs absent). Currently "where they exist" is unverifiable per-language. | `_validate_file_spec` checks `spec.imports` against `file_manifest.imports`; a language with no import parser will silently produce zero imports → false `missing_import` if a contract declares imports for it. | FR-2 — add a per-language import-support row to the §1 table | Test: per-language fixture asserts `imports` is populated where a parser exists and contracts do not assert imports for languages lacking one | 

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Risks | high | Adversarial: FR-5's "advisory `warning` never blocks" can still **mislead the Kaizen/Fix-3 classifier into a wrong root-cause** (sponsor focus 1 final question). Add a requirement that advisory-tier violations carry a `confidence`/`tier` field on the `ContractViolation` so downstream classifiers can discount them, not just a severity label. | A `warning` with no provenance is indistinguishable from a genuine low-severity authoritative warning; Fix-3 may attribute a regex blind spot as a real defect. Severity alone is lossy. | FR-5 — add `tier`/`confidence` to the violation payload (note: §4 says no `ForwardFileSpec`/`InterfaceContract` schema change — `ContractViolation` is a different type, confirm it's not excluded) | Test: an advisory violation exposes `tier="advisory"`; a Fix-3 fixture confirms it is discounted | 
| R1-F10 | Architecture | medium | Adversarial on FR-7 blast radius: `lead_contractor_workflow._review_draft` is a **shipped** path. Add an explicit NFR/acceptance that for an all-Python draft, the shared builder produces a byte-identical `ManifestRegistry` to the current inline `generate_file_manifest` path (regression guard), since FR-7 routes a live gate through new code. | "Additive: Python behavior unchanged" is asserted but FR-7 changes the call path for every existing Python review; a subtle dispatch difference silently changes review outcomes on shipped runs. | FR-7 acceptance + NFR-1 | Test: golden-master comparison of registry built via old inline path vs new builder on a Python-only multi-file blob; assert equal elements/imports | 

**Endorsements & Disagreements:** None — this is round R1; Appendix C had no prior untriaged suggestions.
