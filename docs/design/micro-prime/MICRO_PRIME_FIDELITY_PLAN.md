# Micro-Prime Fidelity — Implementation Plan

**Version:** 0.3 (distillation pass) · **Pairs with:** `MICRO_PRIME_FIDELITY_REQUIREMENTS.md` (v0.3)
**Date:** 2026-06-04

> **v0.3 deltas (see requirements §0.1):** Phase 1 wiring **already landed uncommitted** (context+merge,
> `engine.py:2571-2575`) — but **without the cap**, so Phase 1 reduces to *the cap + budget-non-regression
> test + measurement*. Phase 2 computes the signal in a **single existing pass** (no 4th `file_specs` walk,
> no spread into the ON-HOLD Artisan chunk extractor). **Phase 4 is CONTINGENT** (FR-MPF-4 demoted — build
> only if the measured residual shows a class injection can't fix). Two accidental-complexity items (D-1
> duplicate constraint sections, D-2 the second budget engine) are **deferred debt**, not in scope.

> Two levers on one axis (trust the cheapest tier): **inject** (FR-MPF-1, completes FR-CAR-5b/8a) then
> **route** (FR-MPF-2/3/4). Sequenced inject-first behind a measurement gate (FR-MPF-5). Everything reuses
> established seams — `_collect_upstream_interfaces`, the `MicroPrimeContext` thread, `TaskComplexitySignals`.
>
> **v0.2 planning-pass corrections** (see requirements §0): (1) the field-set block must be **self-bounded**
> — `domain_constraints` is **never** truncated (`_REMOVABLE` excludes it), so an oversized block evicts the
> few-shot/sibling/design-doc sections and overflows 1024; cap it ourselves. (2) FR-MPF-3 emits a
> **MODERATE floor**, not COMPLEX (avoid over-provisioning). (3) OQ-5 verified: decomposed sub-elements
> **already inherit** the merged constraints — no extra wiring, add a regression test. (4) OQ-3/4 resolved:
> convention-strict via `artifact_types_addressed`; override short-circuits the classifier upstream.

## Seam map

| Concern | Existing seam (file:line) | Change | FR |
|---|---|---|---|
| Authority source (lead path) | `prime_contractor.py:4443-4584` `_collect_upstream_interfaces`; set at `:4439-4441` as `gen_context["upstream_interfaces"]` | reuse as-is (no change) | MPF-1 |
| Micro-prime context | `micro_prime/context.py:11` `MicroPrimeContext` (`frozen=True`); `:54-91` `from_prime` | add defaulted field; read `gen_context["upstream_interfaces"]` | MPF-1 |
| Constraint merge | `micro_prime/engine.py:2557-2579` `process_file_with_context` (today appends only `convention_guidance`) | also append the new field | MPF-1 |
| Prompt render | `micro_prime/prompt_builder.py:164-361` `_build_element_prompt_core`; `:1260-1357` `_build_file_whole_prompt` | render in the existing house-style section | MPF-1 |
| Decomposer | `micro_prime/decomposer.py` → `engine.py:_generate_sub_elements` | **verified covered** (sub-elements read `_current_domain_constraints`) — regression test only (OQ-5) | MPF-1 |
| Complexity signals | `complexity/models.py:52-83` `TaskComplexitySignals` | add `manifest_element_count: int = 0` | MPF-2 |
| Signal derivation | `complexity/signals.py` `extract_signals_from_feature` (already receives `manifest`) | sum `len(spec.elements)` over target file_specs | MPF-2 |
| Routing config | `complexity/models.py:139-164` `ComplexityRoutingConfig` | add `manifest_element_simple_max: int` | MPF-3 |
| Classifier | `complexity/classifier.py:158-299` `_classify_tier_core` (SIMPLE-eligibility ~261-271) | add element-count guard to SIMPLE conjunction; emit reason | MPF-3 |
| House-style signal | Kaizen `CAUSE_TO_SUGGESTION` + FR-CAR-9 per-tier telemetry; `CANONICAL_LAYOUT` ownership | feed convention-strict flag to classifier | MPF-4 |

## Phases

### Phase 1 — Inject field-set authority into micro-prime (FR-MPF-1) — *do first*
1. ✅ **DONE (uncommitted)** — **`MicroPrimeContext.upstream_interfaces`** (`context.py:33`) + `from_prime`
   forward (`:92`). Field is defaulted (frozen-safe). (Was the v0.2 plan step; already in the tree.)
2. ✅ **DONE (uncommitted)** — **Merge** in `process_file_with_context` (`engine.py:2571-2575`):
   `upstream_interfaces` then `convention_guidance` appended to `domain_constraints` (correct order).
3. ✅ **DONE** — renders via the existing `domain_constraints` → `# Domain constraints` path in
   `_build_element_prompt_core` (`:307-311`) and the file-whole path. *(See D-1: this path duplicates
   `# Constraints:`; consolidation is deferred debt, not this change.)*
   **➜ 3a. REMAINING — the actual work (the v0.2 cap correction the landed wiring skipped):** add the
   **self-bounding cap** at the merge — `_truncate_to_budget` will NOT trim `domain_constraints`, so an
   uncapped block evicts few-shot/sibling/design-doc and can still overflow 1024. Cap the rendered
   `upstream_interfaces` (referenced-entity scope is already applied upstream; add a hard char cap +
   enum/field-names-only fallback). This is the one non-trivial piece of Phase 1.
4. **Decomposer (OQ-5 — verified covered, regression-test only)**: decomposed SIMPLE sub-elements **already**
   inherit the merged constraints — `_generate_sub_elements`→`_handle_simple`→`_generate_with_retry`
   (engine.py:4361/4372) reads `self._current_domain_constraints`, set once in `process_file:2257`. **No
   extra wiring.** Add a regression test asserting a decomposed sub-element's prompt contains the field-set
   block. Document the standalone `process_element()` path (leaves `_current_domain_constraints=None`,
   engine.py:1823-26) as an explicit **non-goal** — `convention_guidance` is identically absent there.
5. **Self-bound the block (OQ-1 inverted — load-bearing)**: `domain_constraints` is **never** truncated by
   `_truncate_to_budget` (`_REMOVABLE` = few-shot → sibling stubs → design-doc only, prompt_builder.py:
   1115-1167). So the trimmer will **not** protect the 1024 budget — the field-set block must cap **itself**:
   (a) referenced-entity scope (reuse lead-path scoping); (b) a hard char/token cap on the rendered block;
   (c) enum-names + field-names-only fallback when capped. Test: with the block present, the skeleton +
   few-shot are NOT evicted at the default budget.
6. **Tests**: (a) `from_prime` forwards a non-empty `upstream_interfaces`; (b) a schema-referencing element's
   rendered prompt contains the entity field set; (c) a non-schema element renders no spurious block;
   (d) budget-fit under the small input budget; (e) decomposed sub-element inheritance.
7. **Measure** (gate for Phase 3/4): micro-prime structural adherence lift on the RUN-028/RUN-032 +
   Controlled-Corpus `false_pass_risk` fixtures. Record baseline (today) vs injected. *Exit 1:* field-set
   block present in the micro-prime prompt **and** measured non-trivial lift on the field-invention class.

### Phase 2 — Surface-area signal (FR-MPF-2)
8. **`TaskComplexitySignals`** (`models.py`): add `manifest_element_count: int = 0` (safe default → no
   behavior change until Phase 3 reads it).
9. **`extract_signals_from_feature`** (`signals.py`): compute the sum `len(getattr(spec, "elements", []) or
   [])` **inside the existing `has_fillable_elements` loop** (`:245-256`, which already iterates
   `file_specs[tf].elements`) — **no 4th pass** over `file_specs`. Derive **only here**, on the active
   feature path; do **not** touch the ON-HOLD Artisan-chunk extractor (`:~480-630`). Guard
   `AttributeError`/`TypeError`; manifest may be `None`. *Exit 2:* signal populated in one pass; serialized
   into the forensic `to_dict`.

### Phase 3 — Surface-aware routing guard (FR-MPF-3)
10. **`ComplexityRoutingConfig`** (`models.py`): add `manifest_element_simple_max: int` with an **initially
    permissive** default (calibrated in OQ-2; start high enough to be a no-op, then tighten under Phase 5).
11. **`_classify_tier_core`** (`classifier.py`): when `signals.manifest_element_count >
    cfg.manifest_element_simple_max`, emit an **explicit MODERATE floor** (not COMPLEX, not the default
    fall-through which is COMPLEX at :299) with reason `manifest_element_count {n} > {max}`. Place it
    **after** the COMPLEX-trigger block (a real COMPLEX trigger still wins) and **before** SIMPLE
    eligibility. Do **not** reuse the `has_fillable_elements is False`→COMPLEX shape (that's for
    *under*-specified specs; this is *over*-specified → MODERATE). `complexity_tier_override` needs no
    handling here — it short-circuits the classifier upstream (OQ-4). *Exit 3:* a high-element file
    classifies **MODERATE** (not SIMPLE, not COMPLEX); a single-element trivial still SIMPLE; an empty
    framework spec still SIMPLE; RUN_007 Zod-mirror fixture no longer routes SIMPLE.

### Phase 4 — House-style-strict routing (FR-MPF-4) — ⏸ CONTINGENT (do NOT build until the residual demands it)
> **v0.3: deferred.** FR-MPF-4 demoted to a contingency — build only if Phase 1's measurement (Phase 5)
> surfaces a convention-strict class whose adherence stays below threshold *after* injection. No such
> evidence exists today (RUN-032's classes are covered by 8b + FR-MPF-1). Steps retained for when triggered:
12. **Convention-strict flag (OQ-3 resolved)**: `CANONICAL_LAYOUT` ownership is **not** readable from
    `manifest.file_specs` pre-gen. Source the flag from (a) **preventive** — map
    `SeedTask.artifact_types_addressed` to a `CANONICAL_LAYOUT` kind (e.g. `pydantic-models`→`app/models.py`)
    at classify time from seed metadata; (b) **reactive** — the FR-CAR-9 Kaizen per-tier convention-violation
    signal. Add a `convention_strict: bool` signal (mirror the `security_sensitive` elevation shape).
13. **Routing rule**: "SIMPLE + convention_strict → not micro-prime" **unless** the FR-MPF-1 injection has
    measured adherence ≥ `cfg.injection_adherence_min` for that class. *Exit 4:* a convention-strict target
    routes off the cheap tier until injection efficacy is demonstrated, then earns it back.

### Phase 5 — Measurement gate + ramp (FR-MPF-5)
14. Define the structural-adherence metric + class granularity + N (OQ-6). Hold FR-MPF-3/4 thresholds at
    permissive/advisory until Phase 1's lift is measured; tighten on the **residual** failures. State the
    numeric flip precondition (mirror FR-CAR-11). *Exit 5:* thresholds move only behind recorded measurement.

## Verification
- **Unit**: `from_prime` forwarding; prompt contains field set for a schema element; budget truncation;
  signal derivation from manifest; classifier element-count guard (both directions); override precedence.
- **Integration**: RUN_007 Zod-mirror / React-form fixtures no longer route SIMPLE (FR-MPF-3); RUN-011
  field-invention fixture, regenerated on the micro-prime tier *with* injection, no longer invents fields
  (FR-MPF-1 efficacy).
- **Regression**: existing SIMPLE/TRIVIAL routing on a known-good corpus is unchanged while
  `manifest_element_simple_max` is at its permissive default (Phase 3 is a no-op until calibrated).
- **Cost guard**: confirm Phase 3/4 do not over-elevate trivials to expensive tiers (sample cost delta on a
  representative batch).
- **Cross-tier**: micro-prime adherence lift recorded before/after Phase 1 (the FR-MPF-5 gate input).

## Risks / open
- **Token starvation (OQ-1 — now a hard design constraint, not a risk)**: `domain_constraints` is **never**
  truncated, so the block MUST self-cap (step 5) — otherwise it evicts the skeleton/few-shot and overflows
  1024. This is the single non-trivial part of Phase 1; everything else is wiring. Budget-non-regression
  test is the gate.
- **Decomposer bypass (OQ-5 — RESOLVED)**: verified that decomposed sub-elements inherit the merged
  constraints; kept as a **regression test**, not an open risk.
- **Premature route-away**: tightening FR-MPF-3/4 before Phase 1 measurement pushes cheap-capable work to
  expensive tiers (cost regression). FR-MPF-5 exists to prevent this; keep Phase 3 default **permissive**
  (no-op) until OQ-2 calibration. Note the MODERATE-floor choice (step 11) already bounds the cost blast of
  a mis-tuned threshold (MODERATE, not COMPLEX).
- **Convention-strict detectability (OQ-3 — RESOLVED, degraded-mode noted)**: preventive via
  `artifact_types_addressed`→kind; where the kind can't be inferred pre-gen, FR-MPF-4 degrades to the
  reactive Kaizen path — acceptable but weaker.
- **OQ-6 still open**: the injection-efficacy metric (class granularity + N) gating FR-MPF-4/5 must be
  defined before FR-MPF-4 flips from advisory.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

Append-only. Reviewers add to Appendix C; the orchestrator records dispositions in A / B. Do not delete A/B.

### Reviewer Instructions (for humans + models)
- **Before suggesting**: scan Appendix A and B; do not re-suggest applied or rejected items.
- **When proposing**: append a `#### Review Round R{n}` block under Appendix C with IDs `R{n}-S{k}` (plan) /
  `R{n}-F{k}` (requirements).
- **When validating (orchestrator)**: append a row to Appendix A or B referencing the suggestion ID.
- **If rejecting**: record the specific rationale.

### Appendix A: Applied Suggestions
| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) | | | | |

### Appendix B: Rejected Suggestions (with Rationale)
| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) | | | | |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
_(awaiting first review round)_

---

## Requirements Coverage Matrix

| Requirement | Plan Step(s) | Coverage |
|---|---|---|
| FR-MPF-1 (field-set authority → micro-prime) | Phase 1 (1–7) | Covered |
| FR-MPF-2 (surface-area signal) | Phase 2 (8–9) | Covered |
| FR-MPF-3 (surface-aware routing guard) | Phase 3 (10–11) | Covered |
| FR-MPF-4 (house-style-strict route-away) | Phase 4 (12–13) | ⏸ **Contingent** — not built unless Phase-1 residual demands; design retained (preventive via `artifact_types_addressed`, reactive via Kaizen) |
| FR-MPF-5 (inject-first measurement gate) | Phase 1 step 7; Phase 5 (14) | Covered |
| FR-MPF-6 (deterministic, reuse) | all phases | Covered |
