# Contract Leverage & Consolidation — Requirements

**Version:** 0.3 (Plan fold-back — load-bearing OQs resolved)
**Date:** 2026-06-12
**Status:** Draft
**Lens:** *Essential vs. accidental complexity.* The goal is **not to add contract usage** — the SDK
already leverages contracts heavily — but to **consolidate fragmented contract machinery** and close
the one real gap (semantic validation), shedding accrued accidental complexity in the process.

---

## 0.1 Deeper investigation (v0.2) — the root cause and the keystone

> A second pass traced the `api_signatures` data flow and found a single **root cause** that both
> *explains* the asymmetry (AC-1) and *unlocks* its fix with a net complexity **reduction**.

**Finding 1 — `api_signatures` is the upstream SOURCE, not a projection.** `feature.api_signatures`
(raw signature strings in the seed) is parsed by `forward_manifest_extractor._extract_api_signatures`
(`forward_manifest_extractor.py:722`) **into** the `InterfaceContract` / `ForwardElementSpec`. So the
contract is the *derived, structured* form; `api_signatures` is the *raw input*.

**Finding 2 — that one raw artifact is parsed/rendered in ~4 places, by two different regexes.**
- extractor regex → `InterfaceContract`/`ForwardElementSpec` (rich; generation P0). ✓ structured
- embedded as **prose** into `task_description` (`consumption_map`: *"consumed as prose, not
  structured"*) — a second generation copy, **de-structured**.
- `semantic_compliance/signature_check._NAME_RE` **re-parses the raw strings again** for the
  deterministic missing-symbol backstop.
- raw list → the LLM rubric.
This is a structured → prose → **re-structured** round-trip: classic accidental complexity (duplicated
parse logic, one fact in four representations).

**Finding 3 (root cause) — the forward manifest is NEVER persisted.** It is threaded **in-memory**
into the post-mortem (`prime_postmortem.py:1605/2499` take it as a parameter); there is no
`forward-manifest.json`. The **Semantic Compliance Reviewer is a *detached* service** that reads the
seed *file*, so it **cannot reach the extracted contract** — which is exactly **why** it falls back to
raw `api_signatures`. *The generation↔validation asymmetry (AC-1) is a symptom of non-persistence, not
a design decision.*

**The keystone (a small addition that enables three deletions).** Persist the forward manifest as the
single canonical contract artifact for the run (`forward-manifest.json`). Reachability then lets EVERY
consumer read **one** artifact, which retires the duplications:
- **E1** — SCR `signature_check` uses the manifest's `api_sig`-sourced `ForwardElementSpec.name`s →
  **delete `_NAME_RE`** (parity-gated). `ForwardElementSpec` already covers the same kinds.
- **E2** — SCR reviewer rubric uses `InterfaceContract.binding_text` → **drop raw `api_signatures`**
  (symmetric with generation; behavior-test-gated).
- **E3 (adjacent, generation)** — drop the **prose embedding** of `api_signatures` in
  `task_description`; the P0 structured `InterfaceContract` binding is strictly richer.
- Net: `api_signatures` collapses to an **extractor-input-only** field; **−1 regex parser, −2 raw
  consumptions, −1 prose round-trip**, all consumers unified on one persisted artifact. *Persisting is
  not added complexity — it removes the forcing function (non-reachability) that created the
  duplication.*

**Refined essential model:** parse `api_signatures` **once** (extractor) → **one persisted forward
manifest** → read by generation, structural validation, post-mortem, and the SCR alike. No consumer
re-parses `api_signatures`.

---

## 0. The essential model (the north star)

A feature has **one contract**: the interface it must satisfy (elements, signatures, field-sets,
endpoints, and where they live). The irreducible flow is three steps:

```
        derive once            inject once             validate once
schema ┐                  ┌──> generation prompt ──┐
design ┼─> CONTRACT ─────►┤                          ├──> structural + semantic check
AST    ┘  (one artifact)  └──> (the model builds to it)   (did it build to the contract?)
```

Everything beyond *derive → inject → validate against the same contract* is candidate accidental
complexity. **The test for any change: does it move us toward this single flow, or add a parallel one?**

---

## 1. Current state (honest, from the code map)

### 1.1 Prompt generation **already leverages contracts well** — proactively
- `InterfaceContract` (binding_text) is injected at **spec-time P0** as *"## Interface Contract
  Bindings (must enforce)"* + *"## Expected Code Elements"* (`spec_builder.py:1165-1176`); the drafter
  also gets `forward_contracts` at P1. This is **proactive** (the model is told to build to the
  contract), not reactive. `FieldSetAuthority` (Prisma) is also P0; `structural_verify` and
  `engine._semantic_verify` (in-run) and `validate_forward_manifest` (post-merge) all check against
  the contract.
- **Verdict:** generation is *not* the gap. We leverage contracts in prompts substantially.

### 1.2 Semantic validation has a real **asymmetry** (the one genuine gap)
- The LLM **Semantic Compliance Reviewer** validates against **free-text `requirement_text` +
  `api_signatures`** (`reviewer.py:106-107`; `LoadedRequirement` carries no contract). It **re-derives
  intent from prose** for the very thing the generator was already *bound* to via the typed contract.
- **Verdict:** the contract is under-leveraged **here**. Generation targets the contract; the
  sophisticated (LLM) validation targets prose. Asymmetric, and the source of avoidable false PASS/FAIL.

---

## 2. Pre-existing accidental complexity (catalog, to shed opportunistically)

| # | Accidental complexity | Evidence (file:line) | Essence it obscures |
|---|----------------------|----------------------|---------------------|
| **AC-1** | **Generation↔validation asymmetry** — generator bound to `InterfaceContract`; LLM reviewer checks prose | `spec_builder.py:1165` (bound) vs `reviewer.py:106-107` (prose) | "validate against the contract you generated to" |
| **AC-2** | **≥3 parallel encodings of "expected signature"**: `InterfaceContract.function_name`/`signature`, `ForwardElementSpec.signature`, and the reviewer's separate `api_signatures` (seed `ctx`) | `forward_manifest.py:66,111`; `requirement_loader.py:107` | one signature, one source |
| **AC-3** | **Security guidance derived 3 independent ways** (kaizen-split, `security_contract` DB guidance, drafter `framework_imports` detection) — can contradict | `spec_builder.py:1275-1292,1349-1356`; `drafter.py:257-279` | one security_contract, rendered once |
| **AC-4** | **3 quality-hint streams** (`kaizen_hints`, `run_quality_hints`, seed `quality_hints`) — separate keys, no unified section/budget/dedup | `spec_builder.py:1275,1386,1422` | one "guidance" section |
| **AC-5** | **No single prompt-context assembly point** — spec & draft each re-render `upstream_interfaces`/`project_knowledge` independently; stale-risk between spec & draft | `spec_builder.py:1255` vs `drafter.py:968` | assemble contract+hints once; both consume |
| **AC-6** | **Semantic validation fragmented across 4+ mechanisms** with overlaps: duplicate-detection in 3 places, import-validation in 3 places, contract-compliance checked twice | `semantic_checks.py`; `forward_manifest_validator.py` L1/L11/L12/contract | one "code-vs-contract" verdict path |
| **AC-7** | **`binding_text` stored + re-computed** from structured fields (state that can drift) | `forward_manifest.py:728` | computed property, not stored state |
| **AC-8** | **`parser_tier` severity calibration duplicated** in `ForwardManifest` + the validator | `forward_manifest.py:608`; `forward_manifest_validator.py:89` | one calibration |

> Note: the **3 contract *models*** (`InterfaceContract` = design-derived, `FieldSetAuthority` =
> schema-derived, `ForwardElementSpec` = AST-derived) are **NOT** redundant — they have different
> *sources/provenance* and are essential. The accidental complexity is in their **consumption**
> (scattered injection + the validation asymmetry), not their existence. **Do not merge the models.**

---

## 3. Requirements (consolidation-biased)

### A. The keystone + three gated eliminations (the headline, refined in v0.2)
- **FR-CL-1 (keystone — persist the contract).** The forward manifest MUST be **persisted to the run
  dir** (`forward-manifest.json`) as the single canonical contract artifact. The post-mortem and the
  detached SCR MUST read **that artifact** (the post-mortem may keep its in-memory param as a fast
  path, but the persisted form is the contract-of-record). This is the reachability fix that makes
  AC-1 solvable; it adds one file and removes the forcing function for the `api_signatures`
  duplication. **No new contract *type/model* — only persistence of the existing one.**
  *(v0.3: OQ-3 resolved — `ForwardManifest`/`InterfaceContract`/`ForwardElementSpec` are frozen Pydantic
  v2 models that round-trip cleanly via `model_dump_json`/`model_validate_json`; only `_*_index`
  `PrivateAttr`s are excluded and rebuilt lazily. **FR-CL-1 is trivial, no pre-work.** OQ-4 resolved —
  canonical write location is the **run/seed output dir** the detached SCR globs (`prime-context-seed*.json`),
  NOT `.startd8/`; the post-mortem falls back to that same path.)*
- **FR-CL-2 (E2 — reviewer reads the contract).** The SCR reviewer rubric MUST validate against the
  feature's `InterfaceContract.binding_text` (+ `ForwardElementSpec`s) from the persisted manifest,
  with `requirement_text` as *supporting* context — not the sole basis. **Gate:** a behavior test on a
  known corpus (verdicts must not regress on the Run-029 missing-symbol case).
  *(v0.3.1 — **IMPLEMENTED.** The rubric renders `INTERFACE CONTRACT BINDINGS` (binding_text from the
  feature's deterministic contracts) as the structured authority and drops the raw `API SIGNATURES`
  line when a manifest is present; `requirement_text` stays as behaviour context (OQ-1). Falls back to
  api_signatures prose with no manifest (FR-CC-1). The Run-029 *missing-symbol* gate is held by the
  WI-3 deterministic backstop regardless of the rubric; the LLM-verdict corpus regression test needs a
  live API key — deferred to a keyed run.)*
- **FR-CL-3 (E1 — one parser).** The SCR `signature_check` MUST use the manifest's `api_sig`-sourced
  `ForwardElementSpec.name`s and **`_NAME_RE` MUST be deleted**. **Gate:** a parity test —
  `{e.name for e in api_sig_sourced_specs} == required_symbol_names(api_signatures)` over a corpus;
  ship the deletion only when parity holds (preserve the "required deliverable" semantics, i.e. filter
  to `api_sig`-sourced elements, not all manifest elements).
  *(v0.3: OQ-5 resolved with a caveat — there is **no provenance/source tag** on `ForwardElementSpec`.
  api_sig-sourced **class/function/method** specs carry `source_contract_id` (`extractor.py:781,890`);
  **variable/constant specs do NOT** (`extractor.py:794-799`). So the parity set must be derived by
  walking `InterfaceContract`s with `source_reference=="deterministic"` and collecting their element
  names via the contract→element index — not by filtering specs on a tag. If variables break parity,
  narrow E1 to functions/classes/methods and keep `_NAME_RE`'s variable arm rather than add a model
  field (weigh against AG-1).)*
  *(v0.3.1 — **IMPLEMENTED as NARROWED E1.** The parity test (over the real extractor) confirmed
  parity holds for **functions/classes** but NOT variables/constants: variable `api_signatures`
  produce untagged elements with **no deterministic contract** (OQ-5), so the manifest cannot
  represent them as required symbols. Per the decision rule, `_NAME_RE` is **retained** — the SCR now
  takes function/class names from the manifest contracts (`required_symbol_names_from_contracts`) and
  keeps only the **variable residual** + no-manifest fallback on the regex. Net: the SCR no longer
  re-derives function/class names from raw `api_signatures`; the regex is the lone allowlisted
  re-parser (feeds FR-CL-3c's guard). Full deletion of `_NAME_RE` is NOT achievable without tagging
  variable provenance in the extractor — out of scope (AG-1).)*
- **FR-CL-3b (E3 — drop the prose round-trip).** Remove the prose embedding of `api_signatures` in
  `task_description` (the P0 structured `InterfaceContract` binding is strictly richer). **Gate:**
  golden-prompt diff shows only the prose block removed; structured binding unchanged.
  *(v0.3: location corrected — the prose fusion happens **upstream in the design/seed stage**
  (`consumption_map.py:72-76`), **not** in `spec_builder.py` as v0.2 implied. The edit/gate relocate to
  the consumption-map layer. If that fused prose has consumers beyond the generation prompt, reclassify
  E3 as a separate generation-side slice (lower value than E1/E2, which fix the SCR asymmetry directly).)*
  *(v0.3.1 — **IMPLEMENTED.** Precise site: `plan_ingestion_enrichment._enrich_api_signatures` appended
  a `## API Signatures` ```` ```python ```` block to `task_description` AND populated the structured
  `ctx["api_signatures"]`. Verified the structured path is a complete carrier for **generation**:
  `spec_builder` reads only `forward_contracts`/`forward_element_specs` (never raw api_signatures), and
  `context_resolution._format_forward_element_specs` renders functions/classes **and**
  variables/constants — so OQ-5's provenance gap (which blocks E1's SCR filtering) does **not** apply to
  generation rendering. Removed the prose append; kept the structured-field population. Density metrics
  (`_compute_density_snapshot`, `compute_task_density.has_code_examples`) updated to count the structured
  `api_signatures` so they don't read as a regression. Unit-gated (4 affected tests updated, 0 new
  failures). The real-run **golden-prompt** diff (token reduction, no quality regression) needs a keyed
  pipeline run — deferred before merge to main.)*
- **FR-CL-3c (anti-regression).** After E1/E2/E3, **no consumer re-parses `api_signatures`** — it is an
  extractor input only. A test/grep guard SHOULD assert no `api_signatures` regex parse outside the
  extractor.
  *(v0.3.1 — **IMPLEMENTED, scoped to the SCR.** Guard: `signature_check.py` is the only module in
  `semantic_compliance/` that imports `re`. **Scope correction:** the literal "outside the extractor" is
  too broad — `plan_ingestion_micro_ingest._parse_api_signature` and `micro_prime` element-gen parse
  api_signatures *upstream* to build the manifest the SCR now consumes; they are not the SCR↔generation
  asymmetry the consolidation closed. The guard is scoped to the SCR and names the upstream parsers.)*

### B. Shed adjacent accidental complexity (opportunistic, while in these files)
- **FR-CL-4.** *(DEFERRED — planning downgrade.)* `binding_text` is a **stored, serialized Pydantic
  field** (`forward_manifest.py:90`), not derived state — converting it to a computed property changes
  model serialization/round-trip. NOT a one-liner; defer to a deliberate model change, not an
  opportunistic edit. (AC-7 stands as a known smell.)
- **FR-CL-5.** De-duplicate the `parser_tier` severity calibration to one helper (AC-8) — the only true
  small, safe consolidation.
  *(v0.3.1 — **AC-8 premise corrected; shipped as a clarity/testability refactor.** The calibration was
  **not** duplicated: `forward_manifest.py:608` is a *skip-on-None* (unsupported-language) check, not
  severity logic; the `advisory→warning` mapping lives only at `validator.py:96`. Extracted it into a
  named, unit-tested `severity_for_parser_tier()` (single home for the load-bearing FR-5 rule) rather
  than manufacture a cross-file "dedup" that would only add indirection.)*
- **FR-CL-6.** *(direction, not this pass)* A single **generation-context assembler** that renders
  contract facets + the **one** unified guidance section (folding the 3 hint streams, AC-4, and the
  3-way security derivation, AC-3) once, consumed by both spec and draft (AC-5).

### C. Anti-goals (explicit — to avoid adding accidental complexity)
- **AG-1.** Do **NOT** add a new "contract" type/model. There are already 8; the problem is consumption.
- **AG-2.** Do **NOT** add a new enricher or a new semantic validator. Consolidate, don't multiply.
- **AG-3.** Do **NOT** inject the ContextCore *propagation* `ContextContract` into generation prompts —
  it governs phase context plumbing, not code semantics; that would be a category error (it belongs in
  preflight/boundary validation, where it already is).
- **AG-4.** Do **NOT** make any of this a hard dependency or change behavior when contracts are absent.

---

## 4. Prioritized low-hanging fruit (v0.2 — sequenced)

| Rank | Item | Tag | Effort | Touches |
|------|------|-----|--------|---------|
| **1 — keystone** | **FR-CL-1** persist `forward-manifest.json` | **[enabler; small add that unlocks 3 deletes]** | Small | `prime_contractor` (write), `prime_postmortem`/SCR (read) |
| **2 — eliminations (gated)** | **FR-CL-3 (E1)** delete `_NAME_RE`; **FR-CL-2 (E2)** reviewer reads contract; **FR-CL-3b (E3)** drop prose round-trip | **[reduces complexity + adds leverage]** | Bounded | `semantic_compliance/{signature_check,reviewer,prompts,requirement_loader}`; `spec_builder` (E3) |
| **3 — true one-liner** | **FR-CL-5** `parser_tier` dedup | **[reduces complexity]** | Tiny | `forward_manifest.py` + validator |
| **deferred** | **FR-CL-4** binding_text→property (serialization change); **FR-CL-6** single generation-context assembler | **[reduces complexity, larger]** | Real slices | model change; `spec_builder`+`drafter`+`prime_contractor` |

**Sequencing matters:** #1 (persist) is the *enabler* — without it #2's eliminations have nowhere to
read the contract from. Each E1/E2/E3 ships **only when its gate passes** (parity / behavior /
golden-prompt). **FR-CL-6** (the ~7 enrichers → one assembler) remains the biggest *architectural*
win but is its own slice, explicitly to *remove* machinery, never add — sequence it last.

---

## 5. Open Questions

> **Resolved in the v0.2 deeper pass:** ~~OQ-2~~ — `api_signatures` is the **upstream SOURCE** the
> extractor parses *into* the contract (`forward_manifest_extractor.py:722`), not a projection; so the
> fix is to make the *derived* contract the single representation and treat `api_signatures` as
> extractor-input-only (FR-CL-3c).

- **OQ-1.** Does the contract let the reviewer **drop** reliance on `requirement_text` for the
  signature/element checks (pure simplification), or must prose stay for behavior the contract can't
  express? (Resolve in the E2 build; likely: contract for *structure*, prose for *behavior*.)
- ~~**OQ-3 (load-bearing).**~~ **RESOLVED (v0.3):** clean Pydantic round-trip; no un-serializable state
  (`_*_index` are `PrivateAttr`, auto-excluded/rebuilt). `binding_text` is a stored field. **FR-CL-1 trivial.**
- ~~**OQ-4.**~~ **RESOLVED (v0.3):** the detached SCR globs the **run/seed output dir** for
  `prime-context-seed*.json` (`requirement_loader._select_seed_file`); write `forward-manifest.json`
  there (NOT `.startd8/`) for reachability; post-mortem falls back to the same dir.
- ~~**OQ-5.**~~ **RESOLVED (v0.3, with caveat):** no provenance tag on `ForwardElementSpec`; api_sig
  class/function/method specs carry `source_contract_id`, **variables do not**. Derive the parity set
  via `InterfaceContract`s with `source_reference=="deterministic"`; handle variables explicitly (narrow
  E1 if they break parity). See FR-CL-3 note.

---

*v0.2 — Deeper investigation. Root cause found: the forward manifest is **never persisted**, so the
detached Semantic Reviewer can't reach it and falls back to raw `api_signatures` — the asymmetry (AC-1)
is a symptom of non-persistence. The refined plan is a **keystone + 3 gated deletions**: persist the
one contract artifact (FR-CL-1), then retire the duplicate regex parser (E1), the reviewer's raw-string
input (E2), and the prose round-trip (E3) — `−1 parser, −2 raw consumptions, −1 round-trip`, all
consumers unified on one artifact. Net complexity strongly **down**. `api_signatures` becomes
extractor-input-only. The big assembler refactor (FR-CL-6) stays a separate complexity-reducing slice.
Anti-goals: no new contract type/enricher/validator; persistence ≠ a new model.*

*v0.3 — Plan fold-back. The implementation plan
(`CONTRACT_LEVERAGE_AND_CONTRACTS_ADOPTION_PLAN_v0.1.md`) resolved the three load-bearing OQs: OQ-3
(clean Pydantic round-trip → FR-CL-1 trivial), OQ-4 (write next to the seed in the run output dir, not
`.startd8/`), OQ-5 (no provenance tag — derive the api_sig set via `source_contract_id` on deterministic
contracts; variables untagged). E3's prose embedding was relocated from `spec_builder` to
`consumption_map` (design/seed stage). Spine unchanged: keystone + 3 gated deletions.*
