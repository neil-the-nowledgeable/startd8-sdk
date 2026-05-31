# RUN-007 Partial-Delivery Remediation — Requirements

**Version:** 0.3 (Post-CRP — triage applied)
**Date:** 2026-05-31
**Status:** Draft (ready for implementation)
**Source incident:** `docs/design/RUN_007_PARTIAL_DELIVERY_POSTMORTEM.md` — prime-contractor run-007 reported 16/16 PASS (0.94) but delivered 9/16 empty-class stubs (`export class <stem> {}`) at $0.00 cost.
**Scope decided with user:** Fix 1 (P0) + Fix 2/C-1 (P1, detector in disk validator) + Gap B (P1). Fix 3 (verification ledger) OUT OF SCOPE.

> **Triage update (v0.3).** A 6-round Convergent Review (Appendix C) surfaced ~26 anchored, code-verified findings; triage **accepted** all but one (R2-F1/R2-S1, *narrowed*). The merge made six material corrections to v0.2, each verified against source:
> 1. **The empty-spec predicate is wrong.** `kind != CLASS` (OQ-5) treats empty `STRUCT`/`INTERFACE`/`ENUM`/`TYPE_ALIAS`/`DEFAULT_EXPORT` as implementable. Replaced with a **positive fillability** classifier (FR-1, R3-F1). OQ-5 superseded.
> 2. **FR-5 would not have worked.** An empty `{}` body has zero stub markers → `stub_penalty` stays 1.0 → `compute_disk_quality_score` returns ~0.94 (the exact symptom). The detector must **set `ast_valid=False`/`contract_compliance=0.0` and force FAIL**, not feed the stub channel (FR-5, R3-F2 — confirmed at `forward_manifest_validator.py:568`).
> 3. **The emitter list undercounts.** Go (`go_file_assembler.py:204`, plus a `package main` *silent-empty* second shape) and the Python DFA are additional emitters; reframed FR-1 around the **decision** at one shared gate (R1-F1, R5-F1).
> 4. **OQ-3/OQ-4 resolve against the design:** the dollar budget likely does *not* reach the micro-prime escalation site (FR-4 re-homed/guarded, R1-F2); `validate_disk_compliance` is Python-only AST (FR-5 detector is net-new in the non-Python path, reusing `NodeLanguageProfile.validate_syntax`, R1-F3/R6-F2).
> 5. **Escalation can be theater / can silently bypass.** File-whole eligibility needs stub markers a clean empty class lacks (dedicated entrypoint, R3-F3); escalation must be fed the seed description/AC, not the empty spec (R5-F3); Step 2↔4 must co-land (R5-S1).
> 6. **New requirements:** per-target success + terminal-outcome contract (FR-9, R6-F3/F4) and stale-context cleanup (FR-10, R6-F1).

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the actual emission path and falsified two assumptions baked into v0.1 (and into the postmortem's own attribution). Five corrections:

| v0.1 / postmortem assumption | Planning discovery | Impact |
|------------------------------|--------------------|--------|
| The stub is a distinct "basename skeleton **fallback template**" | It is an **unfilled skeleton shipped as final output**. SIMPLE tier sets `skeleton_fill` mode (`prime_adapter._generate_skeletons` → `element_tiers[f]={tier:SIMPLE}`) then skips the fill LLM call ($0.00). The skeleton *is* the deliverable when nothing fills it. | **Reframes FR-1/FR-2:** the fix is "never ship an **unfilled** skeleton as final output," not "remove a fallback template." |
| One emitter site (assemblers) produces `class <stem>` across languages | The emitter is **language-different.** Java/C# assemblers DO emit `public class <stem> {}` directly on empty elements (`java_file_assembler.py:253`, `csharp_file_assembler.py:337`). The **Node** assembler does **not** (it prepends a `// [STARTD8-SKELETON]` sentinel the on-disk stub lacks; with empty elements it emits sentinel-only). The Node stub comes from an **upstream synthetic CLASS element named after the file stem.** | **FR-1 must target the common decision (ship-unfilled-skeleton), plus the two assembler sites, plus the upstream synthesizer — not "all assemblers".** |
| "Zero implementable elements" needs a new definition | Already defined: `engine.py:1336` — `implementable = [e for e in elements if e.kind != ElementKind.CLASS]`. A **CLASS-only spec has zero implementable elements** — exactly the stub trigger. | **OQ-5 resolved.** FR-1/FR-2/FR-7 share this exact predicate; no new definition needed. |
| The complexity classifier independently mis-routes to SIMPLE | `_generate_skeletons` **stamps `tier:SIMPLE` on every file it produces a skeleton for** (line ~2060), regardless of content. The SIMPLE label is partly an *artifact of skeleton emission*, not only the classifier. | **Strengthens FR-7:** the SIMPLE-requires-spec guard must sit at the skeleton-emission/classification boundary, not only in `classify_tier`. |
| `MissingTemplateError` / refusal path may exist | No such error type exists today. Refusal must be **created**; a refused feature surfaces as `success=False` in `prime-result.json` history. | **OQ-6 resolved:** FR-2 includes defining the error type + the refusal→`success=False` wiring. |

**Resolved open questions:**
- **OQ-1 → Partially resolved.** Emitter is language-split: Java/C# = assembler empty-branch; Node = an upstream synthetic stem-named CLASS element (exact synthesizer line still to pin during implementation — it is in seed/spec construction, *not* the Node assembler and *not* `prompt_builder.py:511`, which carries a constructor the on-disk stub lacks).
- **OQ-5 → Resolved.** "Zero implementable elements" = `[e for e in elements if e.kind != CLASS] == []` (a CLASS-only or empty spec).
- **OQ-6 → Resolved.** No refusal path exists; create `MissingTemplateError`; refusal → `success=False`.
- **OQ-2 → Partially.** A file-whole LLM path exists (`engine._get_system_prompt("file_whole")`) and Keiyaku `EscalationHandoff` exists; FR-2 wires SIMPLE-no-elements → file-whole.
- **OQ-3 → Open.** Whether the cost budget reaches the micro-prime escalation site (vs orchestration-only) needs one more read; FR-4 depends on it.
- **OQ-4 → Open.** Whether the disk validator already holds a per-file structural parse to reuse for FR-5 — to confirm at implementation.

> **Mujō framing (session note).** This incident is itself an impermanence failure: the pipeline emitted a durable signal (`succeeded:16`) that did not carry the truth, so every reader inherits its blind spot. The deferred Fix 3 (single truthful ledger) is the Mujō remedy; FR-5's verdict-feeding detector is the interim "emit a true signal" step.

---

## 1. Problem Statement

The micro-prime SIMPLE tier emits a type named after the file basename (`export class value-model {}`) when a feature has no registry template **and** no declared implementable elements. The file is syntactically valid, costs $0.00 (no LLM call), and is marked successful. 9/16 run-007 files were such stubs. Three independent defects compound:

| ID | Component | Current state | Gap |
|----|-----------|---------------|-----|
| A | File assemblers + upstream synthesizer | Synthesize `class <stem> {}` on empty spec | Ships non-functional code as success |
| B | `complexity/classifier.py` | Routes full routes/schemas to no-LLM SIMPLE | Feeds Gap A; SIMPLE+empty-spec is contradictory |
| C-1 | `forward_manifest_validator.py` disk validator | Blind to clean-syntax empty stubs | Scores stubs as healthy |
| ~~C-2~~ | disk validator | ~~tsconfig false FAIL~~ | **Closed by JSONC merge (e427c7b1)** |
| ~~diag~~ | `prime_postmortem.py` | ~~unknown/unknown/(none)~~ | **Closed by NR-10 disk-error surfacing** |
| D | success counts | 3 disagree | OUT OF SCOPE (defer w/ Plan Batch Orchestration) |

---

## 2. Requirements

### FR-0 — Positive fillability predicate (shared foundation) — *new in v0.3 (R3-F1)*
A single shared predicate `is_fillable(element)` (NOT the v0.2 negative `kind != CLASS`) classifies elements:
- **Fillable** (data/behaviour-bearing): `FUNCTION`, `METHOD`, `ASYNC_FUNCTION`/`ASYNC_METHOD`, `PROPERTY`, `CONSTANT`, `VARIABLE`, framework-derived `DEFAULT_EXPORT`, and `INTERFACE`/`ENUM`/`STRUCT` **that carry members/values**.
- **Not fillable** (structural-only): empty `CLASS`, empty `STRUCT`/`INTERFACE`/`ENUM`, and `TYPE_ALIAS`.

A spec is an **empty-fillable spec** when it has zero fillable elements. This predicate is the input to FR-1/FR-2/FR-7 (replaces OQ-5). *Acceptance:* a unit matrix over CLASS/STRUCT/marker-INTERFACE/empty-ENUM/TYPE_ALIAS/DEFAULT_EXPORT — only data-bearing or registry `DEFAULT_EXPORT`/`CONSTANT` count as fillable.

### FR-1 — No unfilled skeleton (or silently-empty file) may be shipped as final output
A feature with an **empty-fillable spec** (FR-0) and **no `FRAMEWORK_CONFIG_DEFAULTS` match** MUST NOT have a stem-named type — or an effectively-empty file — shipped as its final output. The fix is enforced at **one shared gate** in `prime_adapter._generate_skeletons` (R1-S2), not per-assembler. The emitter sites are **non-exhaustive examples** the gate must cover (R1-F1, R5-F1):
- Java/C# assemblers (`java_file_assembler.py:253`, `csharp_file_assembler.py:337`) — `public class <stem> {}`.
- Go assembler (`go_file_assembler.py:204`) — `type <Stem> struct {}` for `package != "main"`; **and** the `package == "main"` *silent-empty* shape (emits nothing → ships effectively empty, validator `empty_file`).
- Node upstream synthesizer — synthetic stem-named CLASS element placed in `file_spec.elements` during seed/spec construction.
- Python `DeterministicFileAssembler` — `from __future__`-only stub.

### FR-2 — Escalate-or-refuse on empty-fillable spec
When the FR-1 gate fires (empty-fillable spec, no registry match), micro-prime MUST:
1. **Escalate once** via a **dedicated empty-spec escalation entrypoint** — NOT the normal `_is_file_ollama_whole_eligible` path, which requires skeleton stub markers a clean empty class lacks (R3-F3/R3-S2). The escalation MUST be fed **materially richer input** — the seed feature **`description`** (`seeds/models.py:107`; the Prime seed has **no** `acceptance_criteria` field — Step 0) — not the same empty spec; if that description is thin/empty, the correct outcome is **immediate refusal** (under-specified seed), not vacuous escalation (R5-F3).
2. If escalation still yields an empty/stub artifact (per the shared FR-5 predicate), **refuse** with a new structured `MissingTemplateError`. The refusal MUST be **caught** (never crash the batch — R2-F3), recorded as `success=False` with a **distinct `root_cause`/`pipeline_stage`** (e.g. `root_cause=empty_spec_refusal`, `pipeline_stage=micro_prime_escalation`, R1-F6).
The legitimate registry path MUST be preserved: a `FRAMEWORK_CONFIG_DEFAULTS` match **never escalates**, even when the collision rule left it CLASS-only (FR-7 tie-break, R5-F2).

### FR-3 — Escalation terminates (no loop, idempotent)
Escalation fires **at most once** per target, counting any existing `file_whole_primary`/`file_whole_escalation_retry` attempts toward the budget (R3-S2). "Empty/stub after escalation" MUST be decided by a **deterministic, cross-language predicate** (Python: `utils.ast_checks.is_stub_only_body`; TS/Go: explicit equivalents), with a defined **partial-fill** rule (real content + residual stub → choose ship-if-any-real-content **or** refuse-if-any-stub, and test it) (R1-F4). The escalate-once flag MUST **persist across checkpoint/resume** so a resumed run does not re-escalate (R1-S6).

### FR-4 — Budget & provider boundary → structured refusal *(OQ-3 resolved at Step 0)*
**Step 0 confirmed the dollar budget does NOT reach the micro-prime escalation site** (only `token_budget=4096` is passed in; no cost signal — `prime_adapter.py:2666`). The budget is owned by the **orchestration layer** (`prime_contractor.py`: `max_cost_usd` / `self.total_cost_usd`, checked at `:3634` and `:4963`). Therefore FR-4 is enforced **at orchestration**: before dispatching an escalation, if `total_cost_usd (+ estimated escalation cost) >= max_cost_usd`, the feature is **refused** (FR-2.2), not escalated and not stubbed. The same structured refusal applies to every no-generation boundary: budget would exceed the cap, provider/fallback unavailable, escalation disabled (R3-F4). Document behaviour at the exact cap boundary (spend == cap). No path may write a skeleton or silently skip.

### FR-5 — Empty-stub detector in the disk validator (Fix 2 / C-1) — hard verdict
`forward_manifest_validator.py` gains a semantic check, in the **non-Python validation path** (`_validate_non_python_file`; OQ-4 resolved negative — no Python-AST reuse for `.ts`/`.go`, R1-F3). It flags a file when: a **single top-level type whose name == the assembler-derived stem** (PascalCase/hyphen-strip aware — `value-model.ts` → `ValueModel`, R1-F3), with an **empty body** — where "empty" includes whitespace-only, comments-only (`// TODO`), and bare `throw`/`panic` (R2-F2) — and **no other declared top-level symbols**.
On match the detector MUST set **`ast_valid=False` (or `contract_compliance=0.0`)** and force the **FAIL** verdict — NOT merely increment `stubs_remaining`. *(Verified: `compute_disk_quality_score` short-circuits to 0.0 only on `ast_valid=False` (`:568`); an empty `{}` body has zero stub markers, so the stub channel leaves the score ~0.94 — the exact run-007 symptom, R3-F2.)* The **same predicate** (`is_empty_stem_type_artifact`) is shared with the FR-2.2 post-escalation check (R3-F3). JS/TS syntax MUST reuse `NodeLanguageProfile.validate_syntax(code, filename_hint=file_path)` rather than the `_validate_js_file` `.js`-tempfile duplicate (R6-F2/R4-S2).

### FR-6 — Detector must not false-flag legitimately-minimal files
The FR-5 false-positive exemption matrix MUST land **before** the hard-FAIL effect is enabled (R3-S5) and MUST cover: barrel/re-export files (`export * from`), empty `index.ts`, marker interfaces, **`.d.ts` ambient declarations** (`Path.suffix` treats `foo.d.ts` as `.ts`), empty enums, config-object modules, and any file with real content beyond the empty stem-named type.

### FR-7 — Empty-fillable spec is not SIMPLE (Gap B) — authority resolved
An **empty-fillable spec** (FR-0) with **no registry match** MUST NOT be treated as SIMPLE. The **skeleton-emission boundary** (`prime_adapter._generate_skeletons`, ~line 2064 — the source of the run-007 SIMPLE label) is **authoritative** for the escalate decision (R1-F5). `classify_tier()` cannot independently enforce this unless `TaskComplexitySignals` is extended with a fillability field — so either extend the signal **or** document that 7(a) is advisory and the emission boundary is the gate. A **registry CLASS-only tie-break** applies: `apply_framework_defaults` only fills paths whose element list is empty (non-empty plan-declared list wins), so a registry path that also carries a stray plan-declared CLASS element stays CLASS-only — it MUST be treated as "registry path → never escalate" (R5-F2). This is why the registry clause is **kept**, not removed (narrows R2-F1).

### FR-8 — Regression reproduction (by-construction AND detector)
Tests MUST reproduce the run-007 shapes and assert each output is **real content OR a structured refusal** — never a stem-stub and never a silently-empty file (R5-F1). Coverage MUST include: the 9 `.ts`/`.tsx` shapes; the Go `package main` silent-empty shape (R5-S2); mixed-success features (one file generated, one refused → feature `success=False`); stale-context retry; and budget/provider-impossibility cases. Additionally, a **detector-regression lock** (R5-F4): feed each of the 9 stub shapes **directly** to `validate_disk_compliance` and assert FAIL, independent of the generation-side assertions — so a later refactor cannot silently re-blind the verdict.

### FR-9 — Per-target success + terminal-outcome contract — *new in v0.3 (R6-F3/F4)*
Any refused/skipped target MUST make the **feature-level** `GenerationResult.success = False`, even when other targets in the same feature generated successfully (today `MicroPrimeCodeGenerator.generate` returns success on `effective_file_count > 0` — the smaller replay of run-007). Each requested target MUST carry **exactly one** terminal outcome in metadata/history: `generated` | `delegated` | `refused` | `skipped`. (This is the local invariant that makes `MissingTemplateError` meaningful without the deferred Fix 3 single-ledger.)

### FR-10 — Stale skeleton-fill context cleanup — *new in v0.3 (R6-F1/R4-S1)*
When the FR-1 gate decides "do not emit; escalate/refuse," it MUST clear any stale `context["skeleton_sources"][file_path]` and `context["element_tiers"][file_path]` (e.g. a prior `{tier:SIMPLE, source:dfa_skeleton}`). `_generate_skeletons` mutates context in place; without cleanup a retry/resume or caller-provided context can re-enter the exact no-LLM SIMPLE skeleton-fill path the fix is closing.

---

## 3. Non-Requirements
- Does NOT unify the three success counts (Fix 3 / Gap D) — deferred.
- Does NOT improve plan-ingestion complexity-signal derivation (the heuristic `estimated_loc`/`blast_radius` source) — FR-7 mitigates at classification time only.
- Does NOT expand `FRAMEWORK_CONFIG_DEFAULTS` (registry sprawl is the anti-pattern being removed).
- Does NOT change C-2 / the blind diagnostic (already closed by prior merges).

---

## 4. Open Questions (post-planning status)
- **OQ-1 → Partial.** Emitter is language-split: Java/C# assembler empty-branch (`java_file_assembler.py:253`, `csharp_file_assembler.py:337`); Node = upstream synthetic stem-named CLASS element in seed/spec construction (exact line to pin at implementation; ruled out: Node assembler — has sentinel; `prompt_builder.py:511` — has constructor).
- **OQ-2 → Partial.** File-whole path exists (`engine._get_system_prompt("file_whole")`); Keiyaku `EscalationHandoff` exists. FR-2 wires SIMPLE-no-elements → file-whole; exact wiring to confirm at implementation.
- **OQ-1 → RESOLVED (Step 0).** Synthesizer = `seeds/element_deriver.py::derive_elements_for_file`, **T0 block (lines 84–108)** — wired live via `seeds/builder.py:233` (`enrich_forward_manifest`). It **unconditionally** emits a stem-named `CLASS` element (`name = PurePosixPath(file_path).stem`, **unsanitized** → `value-model` is an invalid JS identifier — a secondary bug); methods are only added at **T2 if `contracts` exist**. Empirically confirmed: `derive_elements_for_file('lib/value-model.ts', contracts=None)` → exactly one `CLASS name='value-model'`, no methods → the run-007 stub. The **FR-0 fillability predicate + Step-2 shared gate** neutralise it (CLASS-only = empty-fillable); optionally also guard the deriver T0.
- **OQ-3 → RESOLVED NO (Step 0).** Budget does not reach the micro-prime escalation site (only `token_budget=4096`, `prime_adapter.py:2666`); it is owned by orchestration (`prime_contractor.py` `max_cost_usd`/`total_cost_usd`, `:3634`/`:4963`). FR-4 enforced at orchestration (updated above).
- **OQ-4 → RESOLVED NO (Step 0).** `validate_disk_compliance:392` routes non-`.py` to `_validate_non_python_file`; `ast.parse` only at `:406` for `.py`. The FR-5 detector is net-new in the non-Python path (reusing `NodeLanguageProfile.validate_syntax`), not a reuse (R1-S4/R1-F3).
- **OQ-5 → SUPERSEDED.** The `kind != CLASS` predicate is wrong (treats empty STRUCT/INTERFACE/ENUM/TYPE_ALIAS/DEFAULT_EXPORT as implementable). Replaced by **FR-0 positive fillability** (R3-F1).
- **OQ-6 → RESOLVED.** No `MissingTemplateError` exists; create it; refusal surfaces as `success=False` with distinct root_cause/stage (FR-2.2, FR-9).
- **Escalation input (R5-S4) → RESOLVED (Step 0).** The Prime seed carries a required `description` (`seeds/models.py:107`) — the escalation input. There is **no `acceptance_criteria`** in the Prime seed model (AC exists only in the **dormant Artisan** path, `artisan_phases/plan_deconstruction.py`). FR-2.1 narrows "seed description / AC" → **seed `description`**; a thin/empty description → immediate refusal (not vacuous escalation).

---

*v0.3 — Post-CRP triage. 6-round Convergent Review; ~26 F-suggestions triaged (25 accepted, R2-F1 narrowed). Added FR-0 (positive fillability), FR-9 (per-target success/outcome), FR-10 (stale-context cleanup); materially reframed FR-1 (shared gate, non-exhaustive emitters incl. Go/Python), FR-2 (dedicated entrypoint, richer escalation input, caught refusal), FR-4 (budget reach + provider boundary), FR-5 (hard FAIL via ast_valid, not stub channel; Node-profile reuse), FR-7 (authority + registry tie-break), FR-8 (real-content-or-refusal + detector lock). OQ-5 superseded; OQ-3/OQ-4 answered by review. Dispositions in Appendix A/B.*

---

## 5. Implementation Plan

The step-by-step plan lives in a companion document: **`docs/design/RUN_007_REMEDIATION_PLAN.md`** (8 steps, each FR → step, smallest-blast-radius-first; OQ-3/OQ-4 scheduled as Step 0 before code).

---

## Appendix A — Accepted Suggestions

> Triaged 2026-05-31 (v0.3). Round history preserved in Appendix C (cross-model memory — do not strip).

| ID | Disposition | Merged into |
|----|-------------|-------------|
| R1-F1 | ACCEPTED | FR-1 (decision-framed, non-exhaustive emitter list + Go/Python) |
| R1-F2 | ACCEPTED | FR-4 (budget reach acceptance criterion / orchestration re-home); OQ-3 |
| R1-F3 | ACCEPTED | FR-5 (non-Python path; assembler-derived stem name; OQ-4 negative) |
| R1-F4 | ACCEPTED | FR-3 (deterministic cross-language stub predicate + partial-fill rule) |
| R1-F5 | ACCEPTED | FR-7 (emission boundary authoritative; classify_tier needs signal) |
| R1-F6 | ACCEPTED | FR-2.2 (distinct root_cause/pipeline_stage on refusal) |
| R2-F2 | ACCEPTED | FR-5 ("empty body" includes whitespace/comments/throw) |
| R2-F3 | ACCEPTED | FR-2.2 (refusal caught, must not crash batch) |
| R3-F1 | ACCEPTED | **FR-0** (positive fillability replaces `kind != CLASS`); OQ-5 superseded |
| R3-F2 | ACCEPTED (critical) | FR-5 (hard FAIL via `ast_valid=False`/`contract_compliance=0.0`, not stub channel) |
| R3-F3 | ACCEPTED | FR-2.1/FR-5 (shared `is_empty_stem_type_artifact` predicate) |
| R3-F4 | ACCEPTED | FR-4 (provider/budget boundary → same structured refusal) |
| R5-F1 | ACCEPTED | FR-1/FR-8 (Go `package main` silent-empty second shape) |
| R5-F2 | ACCEPTED | FR-7 (registry CLASS-only tie-break — basis for narrowing R2-F1) |
| R5-F3 | ACCEPTED | FR-2.1 (escalation fed seed description/AC, else immediate refusal) |
| R5-F4 | ACCEPTED | FR-8 (detector-regression lock: 9 shapes direct to validator) |
| R6-F1 | ACCEPTED | **FR-10** (stale skeleton_sources/element_tiers cleanup) |
| R6-F2 | ACCEPTED | FR-5 (reuse `NodeLanguageProfile.validate_syntax`) |
| R6-F3 | ACCEPTED | **FR-9** (per-target refusal → feature `success=False`) |
| R6-F4 | ACCEPTED | **FR-9** (per-target terminal-outcome contract) |

## Appendix B — Rejected / Narrowed Suggestions (with rationale)

| ID | Disposition | Rationale |
|----|-------------|-----------|
| R2-F1 | **NARROWED** (not fully accepted) | Proposed *removing* the `AND no registry match` clause entirely, arguing `apply_framework_defaults` always adds non-CLASS elements so registry matches are never empty-fillable. R5-F2 refuted this with the **collision rule**: `apply_framework_defaults` only fills paths whose element list is empty, so a registry path carrying a stray plan-declared CLASS element stays CLASS-only and would be wrongly escalated. **Resolution:** keep the registry clause as an explicit "registry path → never escalate" tie-break (FR-7), rather than relying on fillability alone. Multiple rounds (R3, R5, R6) independently reached this narrowing. |

## Appendix C — Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-05-31

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-05-31 17:20:00 UTC
- **Scope**: Requirements robustness, testability, and accidental complexity — grounded in reads of the actual emission/validation code (assemblers, `_generate_skeletons`, `classify_tier`, `engine.py`, `forward_manifest_validator.py`). Companion plan suggestions are in the plan file's Appendix C (R1-S*).

**Executive summary (top requirement gaps):**

- **FR-1's "three sites" is factually short.** A 4th deterministic emitter exists: `go_file_assembler.py:201-204` emits `type <Stem> struct {}` on empty elements; the Python `DeterministicFileAssembler` ships a `from __future__`-only stub. The requirement should target the *decision* (ship-unfilled-skeleton), not an enumerated site list that silently undercovers languages.
- **FR-4 may be unimplementable as written.** No dollar cost-cap is visible at the micro-prime escalation site (only recursion + token budgets). FR-4 needs an acceptance criterion that proves the budget signal reaches the decision, or it must be re-homed to the orchestration layer.
- **FR-5 contradicts the code it relies on.** "Language-agnostic … reuse existing parse" — but `validate_disk_compliance` only AST-parses Python and routes every non-`.py` file to `_validate_non_python_file`. The run-007 stubs are `.ts`. The detector and its parse are net-new for the stub languages.
- **FR-2/FR-3 "empty/stub" is undefined for partial fills and non-Python.** The escalate-vs-refuse decision needs a deterministic, cross-language stub predicate and an explicit partial-fill rule.
- **FR-7 dual-boundary authority is unspecified.** `classify_tier` reads `TaskComplexitySignals` (no element-kind field); the SIMPLE label that caused run-007 came from the skeleton-emission stamp. The requirement must name the authoritative boundary and the signal each needs.
- **Observability gap:** a refusal (`MissingTemplateError`) needs a distinct root_cause/pipeline_stage or the postmortem stays blind to it.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | Reframe FR-1 around the **decision** "no deterministic assembler may ship an unfilled skeleton as final output when the spec has zero implementable elements and there is no registry match," and list the assembler sites as *non-exhaustive examples*. Add Go (`go_file_assembler.py:201`) and the Python `DeterministicFileAssembler` empty case explicitly. | FR-1's numbered "three sites … not interchangeable" reads as exhaustive but omits the Go struct emitter and the Python `from __future__` stub; an enumerated list invites the same defect in the next language. | FR-1 body (list "applies at the following sites (non-exhaustive)") | Verify by code audit: every deterministic assembler's empty-elements branch is gated by the shared predicate |
| R1-F2 | Risks | critical | FR-4 must add an acceptance criterion: *"A test demonstrates the cost-budget signal is observable at the micro-prime escalation decision; if it is not, FR-4 is enforced at the orchestration layer that owns the budget."* Cite OQ-3 as a blocking dependency. | Code read shows `micro_prime/engine.py` carries only recursion (`policy.check_budget`) + token budgets; `prime_adapter` only *records* `element_escalation_cost`. Without this criterion FR-4 can pass review yet be unbuildable. | FR-4 body; cross-reference OQ-3 | unit/integration: budget-exhausted fixture observed at escalation site → refusal asserted |
| R1-F3 | Validation | high | FR-5 must state that the detector lives in the **non-Python validation path** (`_validate_non_python_file`) with a light per-language structural check, and that OQ-4 ("reuse existing parse") is resolved **negative** for TS/Go (Python-only AST). Also pin "name == file stem" to the **assembler-derived** type name (PascalCase/hyphen-strip), since each assembler transforms the stem differently. | `validate_disk_compliance` returns `_validate_non_python_file` for non-`.py`; the stub language is TS. A naive `name == stem` check fails because Go upper-cases the first letter and `value-model` is not even a legal class identifier. | FR-5 body; resolve OQ-4 | unit: `export class ValueModel {}` for `value-model.ts` flagged; Python AST path unchanged |
| R1-F4 | Validation | high | FR-2/FR-3 must define "**empty/stub** after escalation" testably and cross-language: reuse `utils.ast_checks.is_stub_only_body` for Python and specify the TS/Go equivalent; and resolve the **partial-fill** case (real content + a residual stub) — choose ship-if-any-real-content **or** refuse-if-any-stub and make it an acceptance criterion. | The focus file flags partial fill as the ambiguous case; without a deterministic predicate the escalate-vs-refuse branch is non-reproducible across languages. | New sentence in FR-2 (2) and FR-3 | unit: partial-fill fixture → single deterministic verdict; matrix over Python/TS/Go |
| R1-F5 | Interfaces | high | FR-7 must name the **authoritative boundary** and the data each needs. Today `classify_tier()` consumes `TaskComplexitySignals` (no element-kind/implementable field), so FR-7(a) is unenforceable there without extending the signal contract; the effective SIMPLE label came from the `_generate_skeletons` stamp (~line 2064). State that the emission boundary is authoritative and that `classify_tier` enforcement requires a new signal field (or drop 7(a)). | "Guard at BOTH boundaries" is contradictory if one boundary lacks the input to decide; this is the ordering hazard the focus file raises. | FR-7 body | unit: assert which boundary sets the escalation flag for a CLASS-only spec; classifier guard only active when signal carries the field |
| R1-F6 | Ops | medium | FR-2 should require `MissingTemplateError` refusals to carry a **distinct `root_cause` + `pipeline_stage`** (e.g. `root_cause=empty_spec_refusal`, `pipeline_stage=micro_prime_escalation`) recorded alongside `success=False`, so the postmortem attributes refusals instead of folding them into the existing disagreeing counts. | The focus file (Q6) notes the deferred Fix 3 leaves three counts disagreeing; a typed refusal with its own attribution is the interim "emit a true signal" step (consistent with the doc's Mujō framing) and is cheap to add when the error type is created. | FR-2 body (refusal recording) | unit: refused feature → postmortem shows distinct root_cause/stage, not unknown |

**Disagreements / cautions on existing requirement text** (untriaged, for orchestrator weighting):
- FR-1 — the phrase "they are not interchangeable" plus a closed list of three sites reads as exhaustive; I'd argue it should be explicitly non-exhaustive (see R1-F1) so triage doesn't treat Go/Python coverage as out of scope.

#### Review Round R2 — gemini-3-1-pro — 2026-05-31

- **Reviewer**: gemini-3-1-pro
- **Date**: 2026-05-31 17:35:00 UTC
- **Scope**: Accidental complexity reduction, edge-case robustness, and control flow safety.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Architecture | high | Remove the `AND no FRAMEWORK_CONFIG_DEFAULTS match` clause from FR-2 and FR-7. | `forward_manifest_extractor.py:apply_framework_defaults` populates registry-matched files with `DEFAULT_EXPORT` or `CONSTANT` elements. These are not `CLASS` elements, so `implementable_elements` is already non-empty. The clause is logically redundant and creates a false dependency. | FR-2 and FR-7 | Verify by code audit: registry matches have `implementable_elements_count > 0`. |
| R2-F2 | Validation | high | FR-5 must explicitly define "empty body" to include bodies containing only whitespace, comments (e.g., `// TODO`), or basic throw statements. | Without this, the LLM can trivially bypass the detector by emitting `export class ValueModel { // implement me }`. | FR-5 body | unit: `export class ValueModel { // TODO }` is flagged as a stub. |
| R2-F3 | Risks | high | FR-2 must explicitly state that the refusal (`MissingTemplateError`) MUST NOT crash the batch. It must be caught by the orchestrator (or `prime_adapter`) and cleanly converted into a `success=False` result. | If the exception bubbles up uncaught, a single-file refusal will crash the entire `PrimeContractor` batch. | FR-2 body | unit: `MissingTemplateError` raised -> batch continues, file marked `success=False`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: Agree FR-1 should target the decision, not an exhaustive list of sites.
- R1-F2: Agree FR-4 needs an acceptance criterion for budget signal visibility.
- R1-F3: Agree FR-5 must state the detector lives in the non-Python validation path.
- R1-F4: Agree "empty/stub" needs a deterministic, cross-language predicate.
- R1-F5: Agree FR-7 must name the authoritative boundary.
- R1-F6: Agree `MissingTemplateError` needs a distinct `root_cause` and `pipeline_stage`.

#### Review Round R3 — gpt-5.5 — 2026-05-31

- **Reviewer**: gpt-5.5
- **Date**: 2026-05-31 17:45:00 UTC
- **Scope**: New-agent, code-grounded requirements pass. Focus: places where prior suggestions are directionally right but still allow an empty/stem skeleton to be classified as success, scored too softly, or skipped without a structured refusal.

##### Sponsor focus-ask answers

1. **Escalate-once-then-refuse:** Partial. R1/R2 added idempotency and exception-surfacing, but FR-2 still needs a shared post-escalation predicate because current non-Python file-whole validation only checks language stub markers/skeleton markers and would not reject a clean `export class ValueModel {}`.
2. **Cost-budget interaction:** Partial. R1-F2 covers whether the budget reaches the site; FR-4 still needs the exact-boundary rule: if estimated escalation cost would make spend `> cap`, refuse before dispatch; if spend would equal the cap exactly, the docs must say whether that is allowed.
3. **Language-split emitter:** Partial. R1-F1/R2-F1 broaden sites, but the deeper issue is that `[kind != CLASS]` treats `INTERFACE`, `ENUM`, `STRUCT`, and `TYPE_ALIAS` as implementable. That is too broad for languages where empty marker/shape declarations may be legitimate and too weak for empty stem structs.
4. **Disk-validator detector:** Partial. R2-F2 covers comments/throws; FR-5 still underspecifies score severity. Today a single `stubs_remaining` only reduces the score by 0.02 of total composite weight, so the new empty-stem detector needs a hard FAIL/floor, not only stub counting.
5. **FR-7 dual-boundary guard:** Partial. R1-F5 names authority; R3-F1 tightens the actual signal contract so both boundaries use the same positive fillability classification.
6. **`MissingTemplateError` surfacing:** Mostly addressed by R1-F6/R2-F3. Add the no-provider/no-budget path to the same refusal contract so "could not escalate" is not recorded as an ordinary bypass skip.
7. **Legitimate $0.00 registry path:** R2-F1 is plausible if framework defaults always add non-CLASS elements. Preserve it by testing registry-derived `DEFAULT_EXPORT`/`CONSTANT` as fillable, while excluding structural-only empty declarations from the general fillability predicate.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Architecture | high | Replace the current definition of "zero implementable elements" (`[e for e in elements if e.kind != CLASS] == []`) with a **positive fillability contract**: executable/data-bearing kinds (`FUNCTION`, `METHOD`, `ASYNC_*`, `PROPERTY`, `CONSTANT`, `VARIABLE`, `DEFAULT_EXPORT` from framework defaults) count as implementable; structural-only kinds (`CLASS`, and empty `INTERFACE`/`ENUM`/`STRUCT`/`TYPE_ALIAS` unless they have members/values) do not. | FR-1 and FR-7 quote `engine.py:1336`, but `ElementKind` now includes `INTERFACE`, `ENUM`, `STRUCT`, `TYPE_ALIAS`, and `DEFAULT_EXPORT`. `kind != CLASS` is a Python-era negative test that classifies empty marker declarations and empty Go structs as implementable, undermining the empty-spec guard while risking false positives on legitimate marker files. | FR-1, FR-2, FR-7 shared predicate text | Unit matrix: CLASS-only, STRUCT-only, marker INTERFACE, empty ENUM, TYPE_ALIAS-only, DEFAULT_EXPORT registry config; only the real registry/default-export and data-bearing cases bypass escalation |
| R3-F2 | Validation | high | FR-5 must define a **hard score/verdict effect** for the empty-stem-type detector: when matched, emit a semantic issue with `severity=error`, force the FAIL verdict, and cap `disk_quality_score` at a documented low ceiling (e.g. `<= 0.3`) rather than relying on ordinary `stubs_remaining` weighting. | The current scoring formula makes `stubs_remaining=1` a tiny penalty (`stub_penalty = 0.9`, weighted at 0.2), so a syntactically clean empty class can still score near perfect unless FR-5 overrides the composite. The requirement says "drives it low" but does not define how. | FR-5 body | Test: `export class ValueModel {}` yields FAIL and disk score at/below the documented ceiling; a normal TODO stub still follows ordinary stub counting |
| R3-F3 | Interfaces | high | FR-2 and FR-5 should require a **single shared `is_empty_stem_type_artifact(file_path, content, language)` predicate** used both after file-whole escalation and in disk validation. The post-escalation validator must reject the same empty-stem artifact that the disk validator rejects. | `_validate_file_whole_result` accepts non-Python output when syntax is valid, stub patterns are absent, and skeleton markers are absent; a clean `export class ValueModel {}` has no language stub marker. Without sharing the detector, escalation can "succeed" with the exact artifact FR-5 later fails, or disk can fail a file the generation path marked success. | FR-2 item 2 + FR-5 | Test: file-whole returns exact empty stem class/struct/interface; generation refuses before writing and disk validator independently fails the same content |
| R3-F4 | Ops | medium | FR-4 must define the **exact budget/provider boundary**: if escalation is impossible because the provider/fallback is unavailable, disabled, or the estimated call would exceed the cap, the outcome is the same structured refusal (`MissingTemplateError`, `success=False`, root_cause/stage), not a bypass skip or partial success. | The code has multiple no-generation branches (no skeleton → bypass, non-Python fallback, escalation disabled). The requirement only says "budget exhausted" and "refusal is free"; it does not cover provider unavailable or "would cross cap" at the boundary, so a run can still avoid writing a stub but fail to surface a user-actionable refusal. | FR-4 + FR-2 refusal recording | Unit matrix: budget equal cap, budget would exceed cap, fallback unavailable, escalation disabled; all produce the documented result without writing a skeleton |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):

- R1-F4: The partial-fill verdict must be deterministic; R3-F3 makes the same predicate reusable across generation and disk validation.
- R1-F5: The skeleton-emission boundary should be authoritative; R3-F1 defines the signal it should consume.
- R2-F3: MissingTemplateError must not crash the batch; R3-F4 extends that to provider/budget impossibility.

**Disagreements** (prior untriaged items this reviewer would reject or narrow):

- R2-F1: Narrow, not reject. Removing the registry clause is fine only if FR-2/FR-7 adopt a positive fillability contract that still treats framework `DEFAULT_EXPORT`/`CONSTANT` defaults as implementable.

#### Review Round R5 — claude-opus-4-8-1m — 2026-05-31

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-31 18:10:00 UTC
- **Scope**: Fifth pass (renumbered from a concurrent R4 to preserve round monotonicity — a parallel gpt-5.5 R4 landed in this file simultaneously). R1/R2/R3/R4 already covered the Go emitter, budget reach (OQ-3), validator Python-only (OQ-4), FR-7 authority, partial-fill predicate, refusal attribution, redundant-registry clause, comment-stub evasion, `ElementKind` breadth (R3-F1), and score-severity (R3-F2). I endorse those below and add only genuinely-uncovered second-order findings, grounded in fresh reads of the Go `package=="main"` carve-out, `apply_framework_defaults` collision rule, and the file-whole escalation input.

##### Focus-area answers (only the residual gaps R1–R3 did not close)

**Focus 3 (residual) — Go has a SECOND failure mode the requirements never model.**
- **Summary answer:** Yes — a `package main` empty-spec Go file emits NO struct at all and ships effectively empty; FR-8's "never `class <stem>`" assertion cannot catch it.
- **Rationale:** `go_file_assembler.py:202-204` gates the empty-struct emit on `package != "main"`. For `package main` with empty elements, the file is import-only/blank → trips the validator's `empty_file` guard (`forward_manifest_validator.py:782`, `error="empty_file"`). So the run-007 defect bifurcates in Go: stem-struct (non-main) vs silent-empty (main). FR-8 must assert "real content OR structured refusal," not merely "not a stem-stub."
- **Suggested improvements:** R5-F1.

**Focus 7 (residual) — the `apply_framework_defaults` COLLISION RULE breaks the pure `implementable_count==0` guard that R2-F1/R3-F1 lean on.**
- **Summary answer:** Yes — a registry-matched file that also carries a plan-declared CLASS element keeps the CLASS and is NOT filled with the non-CLASS default, so it is simultaneously registry-matched AND CLASS-only → the pure positive-fillability guard would wrongly escalate it.
- **Rationale:** `apply_framework_defaults` only fills paths whose deterministic list is EMPTY ("a non-empty deterministic/plan-declared list always wins"). R2-F1/R3-F1 assume registry files always arrive with a non-CLASS default; the collision rule is the exception. A narrowed registry tie-break is still required.
- **Suggested improvements:** R5-F2.

##### Requirements suggestions (F-prefix, R5 — new only)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Risks | high | FR-1/FR-8 must model the **Go `package == "main"` second failure mode**: empty-spec main packages emit NO struct (`go_file_assembler.py:202-204`) and ship as an effectively-empty file (validator `empty_file`, `:782`), which FR-8's "never `class <stem>`" assertion will not catch. FR-8 must assert "real content OR structured refusal." | The defect has a non-stem-stub Go shape the requirements don't enumerate; a `package main` empty spec is neither a stem-stub nor real content. | FR-1 note + FR-8 acceptance clause | unit: Go `package main`, empty elements → structured refusal, not a silently-empty file marked success |
| R5-F2 | Data | high | Add a **registry CLASS-only tie-break** to FR-2/FR-7: `apply_framework_defaults` only fills paths whose element list is EMPTY (collision rule: "a non-empty plan-declared list always wins"), so a registry-matched file that also has a plan-declared CLASS element is CLASS-only AND registry-matched — the pure `implementable_count==0`/positive-fillability guard (R2-F1, R3-F1) would wrongly escalate it. Keep a narrowed "registry path → never escalate" check for this case. | Removing the registry clause entirely (R2-F1) or relying solely on fillability (R3-F1) re-breaks this real edge case. | FR-2/FR-7 condition (CLASS-only-registry tie-break) | unit: `next.config.mjs` with a stray plan-declared CLASS element → treated as registry path, not escalated |
| R5-F3 | Validation | medium | FR-2 must require file-whole escalation to be fed **materially richer input than the empty spec** (seed feature description / acceptance criteria), not the same zero-implementable-element spec that produced the stub — else the escalation LLM regenerates an empty/stub and immediately refuses, making "escalation" theater that hides an under-specified seed. | FR-2 says "using the seed's spec/context," but the spec IS the empty one; without richer context the escalate step adds latency/cost with no chance of success. | FR-2 step 1 (specify escalation input contract) | unit: escalation prompt for an empty-spec feature contains the feature description/AC (asserted non-empty); empty-context escalation is rejected at construction |
| R5-F4 | Validation | medium | FR-8 must add a **detector-regression guard**: assert the FR-5 disk-validator detector itself still FAILs each of the 9 run-007 shapes (fed directly to the validator), independent of the generation-side escalate/refuse assertions. | FR-8 currently locks only the by-construction fix; if a later refactor silences the detector, the Mujō "emit a true signal" interim regresses silently with no test catching it. | FR-8 body (add direct-to-validator assertions) | unit: feed each of the 9 stub shapes to `validate_disk_compliance` → all 9 produce FAIL / score below ceiling |

**Endorsements** (R5 reviewer agrees with these untriaged prior items):
- R1-F1 / R2-F1 / R3-F1: decision-framing + positive fillability are the right direction (with the R5-F2 collision caveat).
- R1-F11-equivalent / R3-F2: the detector must hard-fail/cap the score, not rely on `stub_penalty` — confirmed in source: an empty `{}` body has zero stub markers, so `stub_penalty` stays 1.0 and the file scores ~0.94 (the exact run-007 symptom). R3-F2's documented low ceiling is the correct remedy.
- R3-F3: a single shared empty-stem predicate across generation and disk validation prevents the "escalation succeeds with the artifact disk later fails" split.
- R3-F4 / R2-F3: provider/budget-impossibility and uncaught-exception must both resolve to the same structured refusal.
- R1-F4 / R1-F5 / R1-F6: cross-language stub predicate, FR-7 authority, refusal attribution — all high-value.

#### Review Round R6 — gpt-5.5 — 2026-05-31

- **Reviewer**: gpt-5.5
- **Date**: 2026-05-31 17:55:00 UTC
- **Scope**: New-agent requirements pass after R1-R3. Focus: stale context, per-target success semantics, and duplicated JS/TS validation that can undermine the intended user-visible refusal behavior.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | Risks | high | FR-2/FR-7 should require empty-spec refusal/escalation to **remove stale skeleton-fill context**: for any refused/escalated target, `skeleton_sources[file_path]` and `element_tiers[file_path]` must not retain a previous `tier:SIMPLE` / `dfa_skeleton` entry. | The current plan focuses on not writing a new skeleton, but `_generate_skeletons` mutates context in place. A retry or caller-provided context can preserve stale skeleton-fill state and re-enter the exact no-LLM SIMPLE path even after the guard decides not to emit. | FR-2 and FR-7 | Test: context preloaded with stale skeleton and SIMPLE tier; empty-spec guard fires; generated context no longer contains those entries |
| R6-F2 | Validation | high | FR-5/FR-6 should require the disk validator to reuse the existing Node language profile for JS/TS/TSX syntax (`NodeLanguageProfile.validate_syntax(..., filename_hint=file_path)`) rather than the local `_validate_js_file` `node --check` duplicate. | `forward_manifest_validator._validate_js_file` currently writes TypeScript/TSX to a `.js` temp file and hardcodes `_count_stubs_text(content, ".js")`. `languages/nodejs.py` already contains the lower-complexity TS/TSX path (`tsc --noEmit`, JSX handling, toolchain-noise handling). Reuse reduces accidental complexity and makes FR-6 false-positive tests meaningful. | FR-5 and FR-6 | Unit: `.ts`, `.tsx`, `.jsx`, `.js`, and `.d.ts` fixtures validate through the profile-aware path; stub counting uses the actual suffix |
| R6-F3 | Ops | high | FR-2 must state that any empty-spec refusal makes the feature-level `GenerationResult.success` false, even when other target files were generated successfully. | `MicroPrimeCodeGenerator.generate` currently returns success when `effective_file_count > 0`. That can still tell the end user "success" for a partially delivered feature. This is the local invariant needed to prevent a replay of RUN-007 without taking on the full deferred single-ledger Fix 3. | FR-2 refusal recording + FR-8 regression reproduction | Test: two-target feature with one generated file and one refused empty-spec file -> feature result `success=False`, generated file retained, refusal metadata present |
| R6-F4 | Interfaces | medium | Add a minimal per-target terminal outcome contract for this remediation (`generated`, `delegated`, `refused`, `skipped`) and require each target file to have exactly one outcome in metadata/history. | The requirement already needs `success=False`, root cause, and pipeline stage. A small terminal-outcome contract gives users actionable diagnostics without absorbing the larger success-ledger project, and it removes ambiguous branch-specific logging from the lead-contractor path. | FR-2 or a new acceptance criterion under FR-8 | Unit: every requested target has exactly one terminal outcome; refused targets include `MissingTemplateError` metadata; no target is both generated and refused |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F6: Refusal needs root cause/stage; R4-F4 adds the smallest useful per-target status contract.
- R3-F3: The generation and disk validators should share artifact detection; R4-F2 extends the same reuse principle to existing Node syntax validation.
- R3-F4: Provider/budget impossibility should refuse; R4-F3 clarifies that refusal must drive the feature-level success boolean.

**Disagreements** (prior untriaged items this reviewer would reject or narrow):
- R2-F1: Narrow. Removing the registry clause is only safe when stale context is cleared (R4-F1) and the positive fillability contract from R3-F1 is adopted.

#### Review Round R7 — composer-2.5 — 2026-05-31

- **Reviewer**: composer-2.5
- **Date**: 2026-05-31 18:30:00 UTC
- **Scope**: Seventh requirements pass. R1–R6 covered downstream emitters, fillability, co-landing, stale context, per-target success, and Go-main/registry collision. This pass pins the upstream synthesizer and closes accounting/stub-pattern gaps in the requirements text.

##### Sponsor focus-ask answers (residual only)

**Focus 3 — emitter completeness:** Partial → now pinable. The "Node upstream synthesizer" is `seeds/element_deriver.py` T0 (`decomposition_source: element_deriver_t0`), cross-language not Node-only. FR-1 site (2) should name it; guarding only assemblers leaves the synthetic CLASS in the spec.

**Focus 1 — terminate/refuse:** Partial. R1/R3/R5 cover escalation loops; add that **zero element_results must not count as 100% fill rate** in effective-file accounting (`prime_adapter._validate_and_finalize_files`).

**Focus 4 — detector false positives / severity:** Partial. R3-F2 covers score floor; add that **`.ts`/`.tsx` stub-pattern counting is currently broken** (`_STUB_EXT_TO_LANG` omits them), so FR-5 cannot rely on ordinary `stubs_remaining` for TypeScript even after syntax validation is fixed.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-F1 | Architecture | high | FR-1 site (2) must name **`seeds/element_deriver.py:derive_elements_for_file` T0** (via `enrich_forward_manifest`) as the upstream stem→CLASS synthesizer and resolve **OQ-1** accordingly. Require an upstream guard: do not inject T0 stem CLASS when no T2 methods/contracts and no registry default apply. | The requirements leave site (2) unpinned; code shows element_deriver always adds `{kind: class, name: stem}` for empty non-Python file_specs. Downstream-only FR-1 fixes preserve accidental complexity (N consumers re-deriving the same empty-spec rule). | FR-1 bullet (2); OQ-1 in §4 | Audit: empty `.ts` file_spec post-enrichment; OQ-1 closed with file:line; guard test per R6-S2 |
| R7-F2 | Validation | high | FR-2/FR-8 must require that **zero fillable elements → zero effective credit**: a file with `len(element_results)==0` or no `FileResult` must not increment effective fill rate (no `total==0 → rate=1.0` shortcut) and must not alone make the feature successful. | `_validate_and_finalize_files` defaults empty totals to 100% fill and counts `fr is None` as effective — a local success invariant missing from requirements though related to R6-F3/R4-S3. | FR-2 refusal recording + FR-8 acceptance criteria | Test: skeleton-only empty-spec target → not counted effective; two-target mixed feature → `success=False` |
| R7-F3 | Validation | medium | FR-5 must state that TypeScript stub-pattern counting requires **`.ts`, `.tsx`, `.jsx` in the validator's language-extension map** (or equivalent registry lookup), not only the dedicated empty-stem detector. Ordinary `stubs_remaining` is zero for `.ts` today. | `_STUB_EXT_TO_LANG` maps `.js`/`.mjs`/`.cjs` only; run-007 shapes are `.ts`. Without this, FR-5's interim signal under-reports non-stem TODO/throw stubs in TypeScript. | FR-5 body + FR-6 negative cases | unit: `.ts` with `throw new Error("TODO")` → `stubs_remaining > 0`; empty stem class → dedicated detector FAIL |
| R7-F4 | Architecture | medium | Add a **Non-Requirements note** (or FR-1 scope boundary): Vue `.vue` empty-spec files skip deterministic skeleton (`_generate_skeletons` passthrough-only) and follow a different bypass path — out of scope for this remediation unless a run reproduces the defect on `.vue`. | Focus file asked about Vue; code shows `.vue` without existing content skips skeleton emission and uses element pipeline/bypass rules distinct from the `.ts` run-007 path. Documenting exclusion prevents scope creep while recording the audit result. | §3 Non-Requirements | Document-only; optional `.vue` empty-spec smoke test marked informational |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R5-F1 / R5-S2: Go `package main` silent-empty mode must be in FR-8, not only "never stem-stub."
- R5-F2 / R5-S3: Registry CLASS-only collision tie-break remains mandatory.
- R5-F3 / R5-S4: Escalation input must include feature description/AC, not empty spec alone.
- R3-F3: Shared empty-stem predicate across generation and disk validation.
- R6-F1 / R6-F3: Stale context cleanup + per-target success boolean.

**Disagreements** (prior untriaged items this reviewer would reject or narrow):
- R2-F1: Reject wholesale registry-clause removal; R5-F2 collision rule + R7-F1 upstream deriver guard both require a narrowed registry tie-break.

*(CRP review rounds append here)*
