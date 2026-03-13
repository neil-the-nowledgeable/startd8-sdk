# Simple → Trivial Decomposer — Feasibility Analysis

**Date:** 2026-03-07  
**Context:** Extending Micro Prime and the Moderate Decomposer to enable more deterministic assembly without LLM assistance.  
**Related:** [MODERATE_DECOMPOSER_IMPLEMENTATION_PLAN.md](./MODERATE_DECOMPOSER_IMPLEMENTATION_PLAN.md), [DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md](../scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md)

---

## 1. Executive Summary

A **Simple → Trivial decomposer** is **feasible and high-value** for a bounded set of patterns. It would sit between classification and `_handle_simple`, attempting to decompose SIMPLE elements into TRIVIAL sub-elements that each match existing templates. When decomposition succeeds, assembly is deterministic (string concatenation) and **zero LLM cost**.

**Key insight:** The Moderate Decomposer already proves the pattern: MODERATE → SIMPLE/TRIVIAL sub-elements, with deterministic sub-elements (e.g. `class_shell`) and assembly. A Simple Decomposer applies the same pattern one tier lower: SIMPLE → TRIVIAL sub-elements.

---

## 2. Current Architecture

### 2.1 Tier Flow

```
TRIVIAL  → template_registry.is_trivial() → render template → splice → done (0 LLM)
SIMPLE   → _handle_simple() → Ollama → repair → verify → splice (LLM cost)
MODERATE → _handle_moderate() → decompose → sub-elements (SIMPLE/TRIVIAL) → assemble
COMPLEX  → escalate
```

### 2.2 TRIVIAL Templates (templates.py)

| Template | Match Condition | Render |
|----------|-----------------|--------|
| `config_constant` | CONSTANT/VARIABLE + CONFIG_KEY contract | `name = value` |
| `app_instance` | CONSTANT/VARIABLE named app/server/api + framework import | `app = Flask(__name__)` |
| `type_alias` | TYPE_ALIAS + type_annotation | `Name = Alias` |
| `property_getter` | PROPERTY | `return self._name` |
| `dunder_method` | name in `__init__`, `__repr__`, `__str__`, `__eq__`, `__hash__` | Param store, `__dict__`, etc. |
| `typed_constant_default` | CONSTANT/VARIABLE + known type annotation | `name = 0`, `[]`, `{}`, etc. |

### 2.3 Moderate Decomposer (MODERATE → SIMPLE/TRIVIAL)

- **ClassDecomposeStrategy:** class_shell (deterministic) + **init** + class_attrs
- **FunctionChainStrategy:** helpers + dispatch body
- Sub-elements must classify as SIMPLE or TRIVIAL
- `SubElement.deterministic=True` → extract from skeleton, no LLM
- Assembly: `class_compose`, `function_chain` — string concatenation

### 2.4 Deterministic File Assembly (DFA)

- **Input:** ForwardManifest, ForwardFileSpec
- **Output:** Skeleton .py files with stubs (`raise NotImplementedError`)
- **Zero LLM cost**
- Runs in SCAFFOLD phase before DESIGN/IMPLEMENT

---

## 3. Simple → Trivial Decomposer Concept

### 3.1 Goal

For elements classified **SIMPLE**, attempt to decompose into **TRIVIAL** sub-elements that each match a template. If all sub-elements are TRIVIAL, assemble deterministically — **no Ollama call**.

### 3.2 Why SIMPLE Elements Might Be Decomposable

SIMPLE elements are SIMPLE because `complexity_score <= -1` but they **did not match** any template. Reasons a template might not match:

1. **Element is a class** — templates match individual methods/constants, not the class itself. The class element is MODERATE (class +2). But methods like `__init__`, `__repr__` are separate elements and can be TRIVIAL.
2. **Element is a function** with a body that could be split into template-like parts (e.g. validation + return).
3. **Template match is too strict** — e.g. `__init__` with `*args` doesn't match `dunder_method`; a relaxed or composite template could.
4. **Composite pattern** — a SIMPLE element that is "class with **init** + **repr**" as a single manifest entry (unusual) could be split.

### 3.3 Decomposition Strategies (Candidate)

| Strategy | Applicability | Sub-elements | Assembly |
|----------|---------------|--------------|----------|
| **ClassBoilerplateStrategy** | SIMPLE class whose methods are separate elements, each TRIVIAL | class_shell (deterministic) + method bodies (each template) | Same as ClassDecomposeStrategy |
| **DunderComboStrategy** | SIMPLE function/method that is "init + repr" or similar combo | One sub per dunder; each must match template | Concatenate method bodies |
| **ConstantGroupStrategy** | SIMPLE constant group (multiple constants in one spec?) | One sub per constant | Concatenate assignments |
| **RelaxedTemplateStrategy** | SIMPLE due to minor template mismatch (e.g. optional param) | Expand template registry with relaxed match | Single render |

The **ClassBoilerplateStrategy** overlaps with Moderate Decomposer's ClassDecomposeStrategy. The difference: ClassDecompose handles **MODERATE** classes. A Simple Decomposer would handle **SIMPLE** classes — e.g. a class that scores SIMPLE (unusual, since class_def adds +2) or a class-like aggregate.

**More realistic:** The highest-value case is **expanding the template registry** so more elements become TRIVIAL directly, rather than decomposing SIMPLE into TRIVIAL. But decomposition still helps when:

- A **single manifest element** represents multiple logical pieces (e.g. a combined **init**/**repr** generator)
- The **classifier** pushes something to SIMPLE that could be expressed as template composition

---

## 4. Feasibility Assessment

### 4.1 High Feasibility

| Area | Rationale |
|------|-----------|
| **Architecture** | Same pattern as Moderate Decomposer: `can_decompose()` → `decompose()` → `plan` → sub-elements → `assemble()`. Engine integration: add `_handle_simple_pre_decompose()` or branch in `_handle_simple` to try SimpleDecomposer first. |
| **Assembly** | Deterministic string concatenation. Reuse `ClassDecomposeStrategy.assemble()` logic for class-like cases. For function bodies: concatenate template renders. |
| **Template reuse** | Sub-elements are `ForwardElementSpec` instances. Pass each to `template_registry.is_trivial()` and `try_template_match()`. If all match, render all, assemble. |
| **DeterministicFileAssembler alignment** | DFA creates structure; Micro Prime fills bodies. A Simple Decomposer increases the fraction of bodies filled without LLM. No conflict — complementary. |

### 4.2 Medium Feasibility (Requires Design)

| Area | Challenge | Mitigation |
|------|------------|------------|
| **Identifying decomposable SIMPLE** | SIMPLE is a broad bucket. Need heuristics: "class with only dunder methods", "function with N template-like clauses". | Start with class-only: if element is CLASS and all child elements (from file_spec) are TRIVIAL, treat the class as "decomposable" — class_shell + child bodies. |
| **Sub-element construction** | Synthetic specs for sub-elements. Moderate Decomposer already has `_build_synthetic_spec` (Phase 3). Reuse. | Same pattern: build `ForwardElementSpec` for each sub-element, verify each is TRIVIAL. |
| **Confidence / rejection** | Avoid decomposing when templates might produce wrong code. | Confidence threshold (like Moderate Decomposer). Reject if any sub-element would not match a template. |

### 4.3 Lower Feasibility / Edge Cases

| Area | Challenge |
|------|------------|
| **Function body decomposition** | A SIMPLE function body is opaque — we don't have "clauses" like MODERATE function chain. Would need docstring parsing (like FunctionChainStrategy) to split. Risk: over-decomposition. |
| **Template expansion vs decomposition** | Many "SIMPLE but decomposable" cases might be better solved by **adding templates** (e.g. `__init__` with optional params, `__init__` with validation stub). Cheaper than a new decomposer. |

---

## 5. Integration with Deterministic File Assembly

### 5.1 Data Flow (Proposed)

```
Plan Ingestion → FLCM → SCAFFOLD
  ├── Directory creation
  ├── DeterministicFileAssembler  [DFA] → skeleton .py with stubs
  └── ScaffoldPhaseOutput

DESIGN → IMPLEMENT (Micro Prime)
  For each element in manifest:
    TRIVIAL → template → splice
    SIMPLE  → SimpleDecomposer.try_decompose()
      ├── decomposable? → TRIVIAL sub-elements → template each → assemble → splice (0 LLM)
      └── not decomposable? → _handle_simple (Ollama)
    MODERATE → ModerateDecomposer (existing)
    COMPLEX → escalate
```

### 5.2 DFA + Simple Decomposer Synergy

- **DFA** produces skeletons with `raise NotImplementedError` stubs. Structure (classes, methods, signatures) is fixed.
- **Simple Decomposer** fills stubs when the element can be expressed as template composition. No LLM.
- **Result:** More elements completed in IMPLEMENT phase with zero LLM cost.

### 5.3 Requirements Alignment

From [DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md](../scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md):

- **NFR-001 (Zero LLM Cost):** Simple Decomposer, when it succeeds, uses only templates — zero LLM.
- **FR-005 (Stub Bodies):** DFA creates stubs; Simple Decomposer replaces them with template output when applicable.
- **§8 Future Enhancement:** Plan ingestion prompt enrichment would produce richer `ForwardElementSpec` entries. Richer specs → more template matches → more TRIVIAL sub-elements.

---

## 6. Recommended Implementation Path

### Phase 0: Identical-Copy File Duplication (Highest Value, Zero LLM)

**Scope:** Tasks whose description explicitly specifies duplication of a predecessor's output (e.g., "Identical copy of the emailservice logger.py", "Duplicated identically from the shared logger pattern").

**Problem observed:** In run-004 (Online Boutique), PI-001 and PI-002 both specify the same shared JSON logger. PI-002's description says "Identical copy of the emailservice logger.py" and `depends_on: [PI-001]`. Yet the pipeline runs the full spec→draft→review cycle independently for PI-002, producing a functionally divergent implementation ($0.10, different timestamp format, different log level, extra imports). The LLM has no way to produce a byte-identical copy because it never sees PI-001's output.

**Why this belongs here:** The document's thesis is "expand deterministic assembly without LLM calls." File duplication is the most extreme case — not just zero Ollama cost, but zero cloud cost and zero prompt engineering. The output is correct by construction (byte-identical to the source).

**Detection (plan ingestion or prime contractor task classification):**

1. Scan `task_description` for duplication signals: `"identical copy"`, `"duplicated identically"`, `"exact copy"`, `"same as {file}"`, `"mirror of"`
2. Require `depends_on` to contain exactly one predecessor (the source task)
3. Require the predecessor to target a single file (unambiguous copy source)
4. If all conditions met → classify as `strategy: file_copy` with `copy_source: {predecessor_id}`

**Execution:**

1. Wait for predecessor task to complete (already guaranteed by `depends_on` scheduling)
2. Read predecessor's generated output file from disk
3. Write to the current task's `target_files[0]` path
4. No spec phase, no draft phase, no review phase

**Validation:**

- Byte-identical: `hashlib.sha256(source).hexdigest() == hashlib.sha256(target).hexdigest()`
- If source task failed → copy task also fails (no independent fallback)
- If source file doesn't exist on disk → fail with clear error referencing predecessor

**Cost/correctness comparison:**

| Approach | Cost | Correctness | Time |
|---|---|---|---|
| LLM regeneration (current) | ~$0.10 | Divergent (proven in run-004) | ~15s |
| File copy | $0.00 | Identical by definition | <1s |

**Edge case — modified copies:** If a task says "Copy of X **with these modifications**," that is NOT a file-copy task. It should instead inject the source file into the prompt as reference material. Detection: duplication signal + modification signal ("with changes", "adapted for", "modified to") → `strategy: copy_and_modify` (inject predecessor output into spec/draft prompt, still uses LLM).

**Generalization:** Any microservices project with shared utilities (loggers, health checks, config loaders, middleware) will have this duplication pattern. Detecting it early avoids both cost and divergence risk across the entire plan.

**Metrics:** `prime.file_copy_tasks`, `prime.file_copy_cost_saved_usd` (predecessor's actual cost × copy count).

### Phase 1: Class-Boilerplate Simple Decomposer (Highest Value)

**Scope:** SIMPLE class elements whose methods are separate manifest elements and **all** match templates.

**Logic:**

1. `element.kind == CLASS`
2. Get child elements from `file_spec` with `parent_class == element.name`
3. For each child: `template_registry.is_trivial(child, ...)`
4. If **all** children are TRIVIAL → decomposable
5. Plan: `class_shell` (deterministic from skeleton) + one sub per child (each `deterministic=True` with template render)
6. Assembly: reuse `ClassDecomposeStrategy.assemble()`

**Note:** This overlaps with Moderate Decomposer's ClassDecomposeStrategy. The difference: ClassDecompose handles **MODERATE** classes. A SIMPLE class (rare: class_def +2 usually pushes to MODERATE) would be handled here. Alternatively, **unify**: if a MODERATE class has all-TRIVIAL methods, ClassDecompose could mark all sub-elements as deterministic (template) instead of calling `_handle_simple`. That would achieve the same goal without a separate Simple Decomposer.

### Phase 2: Template Registry Expansion

Before building a full Simple Decomposer, **expand templates** to cover more cases:

- `__init__` with optional params (`Param.default is not None`)
- `__init__` with `*args`/`**kwargs` (stub: `pass` or store in `self._extra`)
- Simple validation pattern: `if not x: raise ValueError(...)`

Each new template converts SIMPLE → TRIVIAL directly, no decomposition needed.

### Phase 3: Function-Body Decomposition (If Justified)

Only if data shows many SIMPLE functions with docstring clauses that map to templates. Would require:

- Docstring clause parsing (like FunctionChainStrategy)
- Mapping clauses to template types (validation, formatting, etc.)
- Higher risk of wrong code — need confidence threshold.

---

## 7. Conclusion

| Question | Answer |
|----------|--------|
| **Is a Simple → Trivial decomposer feasible?** | Yes, for a bounded set of patterns (class boilerplate, template composition). |
| **Does it support deterministic assembly?** | Yes. Assembly is string concatenation of template outputs — same as Moderate Decomposer. |
| **Does it enable more tasks without LLM?** | Yes. Each successfully decomposed SIMPLE element avoids one Ollama call. |
| **How does it relate to DFA?** | Complementary. DFA creates structure; Simple Decomposer fills more bodies deterministically. |
| **Is identical-copy duplication feasible?** | Yes. Highest-value zero-LLM strategy. Detects "identical copy" language + `depends_on` predecessor, copies file instead of regenerating. Proven need: PI-001/PI-002 divergence in run-004. |
| **Recommended first step?** | (0) Implement file-copy detection for identical-copy tasks (zero cost, zero risk of divergence); then (a) extend Moderate Decomposer so that when all sub-elements are TRIVIAL, use templates instead of `_handle_simple`; or (b) expand template registry. All three increase deterministic completion before adding a dedicated Simple Decomposer. |

---

## 8. Open Questions

1. **Unify vs separate:** Should "SIMPLE class with all-TRIVIAL methods" be handled by extending Moderate Decomposer (treat TRIVIAL sub-elements as deterministic/template) or by a separate Simple Decomposer?
2. **Classifier interaction:** If we add a Simple Decomposer, should the classifier have a "decomposable_simple" signal for dry-run reports (like MODERATE's `DECOMPOSABLE`)?
3. **Metrics:** Should we add `micro_prime.simple_decomposed_count` and `simple_decomposition_rejected` for observability?

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **Architecture**: 7 suggestions applied (R1-S1, R2-S1, R3-S1, R3-S2, R4-S1, R5-S1)
- **Interfaces**: 5 suggestions applied (R1-S2, R2-S2, R3-S6, R4-S2, R5-S2)
- **Data**: 4 suggestions applied (R1-S3, R2-S3, R3-S3, R5-S3)
- **Risks**: 5 suggestions applied (R1-S4, R2-S4, R3-S4, R4-S4, R5-S4)
- **Validation**: 4 suggestions applied (R1-S5, R3-S5, R4-S5, R5-S5)
- **Ops**: 5 suggestions applied (R1-S6, R2-S6, R3-S7, R4-S6, R5-S6)
- **Security**: 4 suggestions applied (R1-S7, R2-S7, R4-S7, R5-S7)

### Areas Needing Further Review

(All 7 areas have reached the threshold of 3 accepted suggestions.)

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Define explicit decision order and exclusivity | Codex | To be implemented in architecture and data flow | 2026-03-07 |
| R1-S2 | Add config switch and threshold for SimpleDecomposer | Codex | To be added to config object | 2026-03-07 |
| R1-S3 | Specify deterministic ordering source for child elements | Codex | To be implemented reading from manifest_order | 2026-03-07 |
| R1-S4 | Add a "template safety gate" to verify exact signature | Codex | Implement strict validation before decomposition | 2026-03-07 |
| R1-S5 | Add minimal validation matrix for positive/negative cases | Codex | To be added to test suite | 2026-03-07 |
| R1-S6 | Define telemetry/forensic logging for SimpleDecomposer | Codex | Implement metrics logging | 2026-03-07 |
| R1-S7 | Require explicit allowlist for RelaxedTemplateStrategy | Codex | Disabled by default | 2026-03-07 |
| R2-S1 | Clarify leaf-only constraint: decomposed elements not re-fed to decomposer | Antigravity | Add explicit "leaf-only" rule in Section 4.1; unit test ensures no recursion | 2026-03-07 |
| R2-S2 | Define `SimpleDecomposer.try_decompose(element, file_spec)` signature | Antigravity | Return `Optional[DecompositionPlan]`; document in Section 6 Phase 1 | 2026-03-07 |
| R2-S3 | Add `decomposition_source` field to ForwardElementSpec | Antigravity | Values: "simple", "moderate", "copy"; extend R2-S3 per R3 endorsement | 2026-03-07 |
| R2-S4 | Safeguard against decomposing SIMPLE elements with complex decorators | Antigravity | Add gate in Section 4.3; negative test forces `_handle_simple` for decorated class | 2026-03-07 |
| R2-S6 | Add `--dry-run-simple-decompose` CLI flag | Antigravity | Combine with R3-S7 into `--dry-run-deterministic` per R3 endorsement | 2026-03-07 |
| R2-S7 | Sanitize method/class names before template concatenation | Antigravity | Security test with malicious manifest element names | 2026-03-07 |
| R3-S1 | Add Phase 0: Identical-Copy File Duplication strategy | Claude | Integrated in Section 6 Phase 0; detection + execution + validation | 2026-03-07 |
| R3-S2 | Define strategy enum for classifier/engine dispatch | Claude | `file_copy`, `copy_and_modify`, `template`, `llm_simple`, `llm_moderate`, `escalate` | 2026-03-07 |
| R3-S3 | Add `copy_source_task_id` and `copy_source_file` to task schema | Claude | Populate during plan ingestion; consume by prime contractor | 2026-03-07 |
| R3-S4 | Add post-assembly file-level validation gate | Claude | No skeleton markers, no duplicate defs, spec compliance; Section 5 | 2026-03-07 |
| R3-S5 | Define success criteria as `deterministic_elements/total_elements` percentage | Claude | Target 40% Phase 0+1, 60% Phase 0+1+2; add to Section 7 or Success Metrics | 2026-03-07 |
| R3-S6 | Define `copy_and_modify` strategy interface | Claude | Inject predecessor output as `{reference_implementation}` in spec/draft prompts | 2026-03-07 |
| R3-S7 | Add `--dry-run-copy-detection` CLI flag | Claude | Combine with R2-S6 into `--dry-run-deterministic` | 2026-03-07 |
| R4-S1 | Require all-or-nothing decomposition; no partial splices | Codex | Assemble in memory; splice only if all sub-elements pass; Section 4.1, 5.1 | 2026-03-07 |
| R4-S2 | Define render contract for templates (body-only vs full def, indentation) | Codex | Section 4.1 or 3.3; snapshot test for class with 2 methods | 2026-03-07 |
| R4-S4 | Add skeleton-signature mismatch gate | Codex | Reject if DFA stub differs from ForwardElementSpec; Section 4.2 | 2026-03-07 |
| R4-S5 | Add idempotence tests: two passes produce identical output | Codex | Run twice, diff output; assert no changes on pass 2 | 2026-03-07 |
| R4-S6 | Emit rejection-reason taxonomy and top-N counts per run | Codex | `no_template_match`, `skeleton_mismatch`, `unsafe_decorator`, `render_contract_violation` | 2026-03-07 |
| R4-S7 | Require safe literal serialization in templates (repr/JSON) | Codex | Forbid raw string injection from manifest; security test with malicious defaults | 2026-03-07 |
| R5-S1 | Add "template-first short-circuit" to bypass decomposer | Codex | Fast-path implementation to skip unnecessary logic | 2026-03-07 |
| R5-S2 | Add `--simple-decomposer-report` flag | Codex | Output a JSON report of metrics | 2026-03-07 |
| R5-S3 | Add `template_coverage` map indicating successful matches | Codex | Help direct further template efforts | 2026-03-07 |
| R5-S4 | Add no-regression constraint for empty template output | Codex | Prevent blank template bodies overwriting useful stubs | 2026-03-07 |
| R5-S5 | Introduce quick win tests across 5 representative simple cases | Codex | Baseline testing for simple regressions | 2026-03-07 |
| R5-S6 | Add a cost-savings estimate tracking LLM calls avoided | Codex | Extrapolate savings against fixed call cost metrics | 2026-03-07 |
| R5-S7 | Block whitespace and non-identifier chars on sub-element name | Codex | Fast security guard during generation | 2026-03-07 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R2-S5 | Specify integration test pipeline with 50+ simple components | Antigravity | The "50+" threshold is arbitrary for a feasibility document. A scalable integration test is valuable, but a fixed component count over-specifies. Prefer "integration test with known corpus" without a numeric threshold; implementers can size the corpus based on available fixtures. | 2026-03-07 |
| R4-S3 | Add DFA-origin anchor (skeleton_anchor_id) on ForwardElementSpec | Codex | DFA schema changes and anchor emission are outside this feasibility doc's scope. The suggestion is valid for implementation but requires DFA to emit anchors; this doc focuses on feasibility of the Simple Decomposer concept. Defer to implementation phase when DFA and Micro Prime integration is designed. | 2026-03-07 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: Codex
- **Date**: 2026-03-07
- **Scope**: Feasibility document review for Simple → Trivial decomposer; initial CRP pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|---|---|---|---|---|---|---|
| R1-S1 | Architecture | high | Define the exact decision order and exclusivity between `_handle_simple`, SimpleDecomposer, and ModerateDecomposer, including the “no double-decompose” invariant and fallback behavior. | The flow in §5.1 is conceptual; without an explicit ordering contract and exclusivity rule, later implementations can accidentally double-route or bypass `_handle_simple`. | Section 5.1 (Data Flow) and Section 6 Phase 1 logic. | Unit test for routing: a SIMPLE element that is decomposable is handled once; a non-decomposable SIMPLE goes to `_handle_simple`. |
| R1-S2 | Interfaces | medium | Add a config switch and threshold for SimpleDecomposer (e.g., `micro_prime.enable_simple_decomposer`, `simple_decomposer.confidence_threshold`) with defaults. | Without an interface contract, rollout and regression isolation are hard; feature-gated deployment reduces risk. | Section 6 (Recommended Implementation Path) and Section 8 (Open Questions). | Config-driven test: with flag off, SIMPLE always routes to `_handle_simple`; with flag on, decomposable SIMPLE avoids LLM. |
| R1-S3 | Data | medium | Specify a deterministic ordering source for child elements during class decomposition (e.g., `manifest_order` or `source_index`) and require stable ordering in `ForwardFileSpec`. | Deterministic assembly depends on a stable sub-element order; relying on unordered collections risks non-deterministic output. | Section 4.2 (Sub-element construction) and Section 6 Phase 1. | Add a test that shuffles input order but still produces the same assembled output. |
| R1-S4 | Risks | high | Add a “template safety gate” that verifies sub-elements match signatures exactly (param names/count/defaults) before decomposition; otherwise fall back to LLM. | Relaxed matching and synthetic specs risk producing incorrect code while appearing “deterministic.” A strict gate reduces false positives. | Section 4.2 (Confidence / rejection) and Section 6 Phase 2. | Negative test: a child with mismatched param defaults must fail decomposition and call `_handle_simple`. |
| R1-S5 | Validation | medium | Add a minimal validation matrix for SimpleDecomposer (positive, negative, and mixed cases) plus an integration test that checks no LLM calls on decomposed SIMPLE. | The doc proposes new flow but doesn’t define concrete validation scope; a small matrix catches regressions early. | New “Validation” subsection after Section 6 or add to Section 6 Phase 1. | Test matrix: class with all TRIVIAL methods (decompose), one non-TRIVIAL (reject), and mixed ordering (stable output). |
| R1-S6 | Ops | low | Define telemetry/forensic logging: `simple_decompose_attempted`, `simple_decompose_success`, `simple_decompose_rejected`, and reject reasons. | Visibility is required to justify the feature’s value and to detect regressions or mis-matches. | Section 8 (Open Questions) or Section 4.1 (High Feasibility). | Verify counters increment correctly in unit tests for success vs reject paths. |
| R1-S7 | Security | low | Require an explicit allowlist for RelaxedTemplateStrategy and default it to disabled in production configs. | Relaxed templates broaden match surface; a safe default reduces risk of unreviewed codegen changes. | Section 3.3 (Strategies) and Section 6 Phase 2. | Config test: relaxed templates are not applied unless the allowlist is explicitly set. |

#### Review Round R2

- **Reviewer**: Antigravity
- **Date**: 2026-03-07 15:07:43 UTC
- **Scope**: Targeted coverage for unresolved areas via depth and edge cases

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | Clarify if Simple Decomposer can be invoked iteratively or only once per element. | A SIMPLE element may decompose into parts that themselves could be processed, though TRIVIAL is a leaf node. We need an explicit "leaf-only" constraint or recursion rules. | Section 4.1 (Architecture) | Unit test ensuring decomposed elements are not fed back into the decomposer. |
| R2-S2 | Interfaces | medium | Define the signature of `SimpleDecomposer.try_decompose(element: ForwardElementSpec, file_spec: ForwardFileSpec) -> Optional[List[SubElement]]`. | Makes the integration points clear, ensuring it is interchangeable with `ModerateDecomposer` interfaces where possible. | Section 6 (Phase 1) | Check implementation matches defined signature. |
| R2-S3 | Data | medium | Expand `ForwardElementSpec` to explicitly track `decomposition_source="simple" \| "moderate"`. | Helps downstream validation and tracking know exactly which engine decomposed an element without inferring it. | Section 5.1 (Data Flow) | Verify field exists and is populated correctly in JSON manifest. |
| R2-S4 | Risks | high | Add a safeguard against decomposing SIMPLE elements that contain complex decorators or meta-programming. | Decorators often imply cross-cutting behavior that simple string templates cannot accurately stub. | Section 4.3 (Lower Feasibility) | Create a negative test where a decorated SIMPLE class is forced to `_handle_simple`. |
| R2-S5 | Validation | high | Specify an integration test pipeline running Micro Prime with Simple Decomposer enabled across a known set of 50+ simple components. | A single matrix test is good, but a broader regression suite ensures the decomposed outputs compile and pass standard lit tests. | Section 6 (Phase 1) | Execute lit tests on generated stubs. |
| R2-S6 | Ops | medium | Expose a dry-run flag `--dry-run-simple-decompose` for the CLI. | Allows developers to audit which elements would be deterministic without invoking Micro Prime. | Section 5 (Integration with DFA) | CLI test confirming output matches expected static files without LLM. |
| R2-S7 | Security | low | Sanitize method/class names before concatenating into templates. | Prevent injection of arbitrary python code if a malformed `ForwardManifest` is ingested. | Section 4.2 (Sub-element construction) | Security test with maliciously crafted manifest element names. |

#### Review Round R3

- **Reviewer**: Claude (Kaizen post-fix analysis context)
- **Date**: 2026-03-07
- **Scope**: Expand deterministic assembly surface based on run-004 kaizen findings; strengthen requirements for production readiness

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|---|---|---|---|---|---|---|
| R3-S1 | Architecture | critical | Add Phase 0: Identical-Copy File Duplication strategy that detects "identical copy" / "duplicated identically" language in task descriptions + `depends_on` predecessor and copies the file instead of LLM regeneration. | Proven need from run-004: PI-001 and PI-002 diverged despite "identical copy" spec. LLM regeneration is both more expensive ($0.10) and less correct (divergent output) than a byte-identical file copy. This is the highest-value zero-LLM strategy possible — it eliminates an entire class of cross-feature consistency bugs. | New Section 6 Phase 0 (before Phase 1). | Integration test: task with "identical copy" description + `depends_on` predecessor → file is byte-identical to source; no LLM calls made; cost is $0.00. Negative test: task with "adapted copy" language is NOT routed to file-copy. |
| R3-S2 | Architecture | high | Define a strategy enum (`file_copy`, `copy_and_modify`, `template`, `llm_simple`, `llm_moderate`, `escalate`) that the classifier emits and the engine dispatches on. | Currently, routing decisions are scattered across `_handle_simple`, `_handle_moderate`, template checks, and the proposed SimpleDecomposer. A unified strategy enum makes the decision tree explicit, testable, and extensible (e.g., adding `file_copy` without touching existing routing). | Section 2.1 (Tier Flow) or new subsection. | Unit test: each strategy value maps to exactly one handler; no strategy is handled by two paths. |
| R3-S3 | Data | high | Add `copy_source_task_id: Optional[str]` and `copy_source_file: Optional[str]` fields to the task/feature schema so the copy strategy can reference the predecessor's output without re-parsing the description. | NLP-based detection of "identical copy" in task descriptions is fragile. Once detected during plan ingestion, the structured fields should carry the intent forward so the prime contractor doesn't need to re-infer it. | Section 5.1 (Data Flow) and plan ingestion task schema. | Verify fields are populated during ingestion and consumed by prime contractor; verify absent fields don't trigger copy path. |
| R3-S4 | Risks | high | Add post-assembly file-level validation gate: (1) no `[STARTD8-SKELETON]` markers remain, (2) no nested duplicate function definitions, (3) file implements spec's required functions/classes. | PI-004 and PI-006 ship broken skeletons that pass element-level `verification_verdict: "pass"` because the repair pipeline validates elements in isolation. A file-level gate after splice would catch these. This is complementary to the Simple Decomposer — it catches failures in ALL tiers. | New subsection in Section 5 or Section 4.2. | Test: assembled file with `[STARTD8-SKELETON]` marker → gate rejects; assembled file with nested duplicate def → gate rejects; clean file → gate passes. |
| R3-S5 | Validation | medium | Define success criteria for the deterministic assembly surface as a percentage: track `deterministic_elements / total_elements` per run and set a target (e.g., 40% for Phase 0+1, 60% for Phase 0+1+2). | Without a measurable target, it's unclear whether each phase delivers sufficient value to justify the next. The kaizen system already captures `micro_prime.total_elements` and `successful_elements`; adding `deterministic_elements` completes the picture. | Section 7 (Conclusion) or new "Success Metrics" section. | Kaizen metrics include `deterministic_elements` count; post-run report shows ratio. |
| R3-S6 | Interfaces | medium | Define the `copy_and_modify` strategy interface: inject predecessor output as `{reference_implementation}` slot in the spec/draft prompts so the LLM adapts rather than recreates. | "Copy with modifications" tasks (e.g., "same logger but for Python 2 compatibility") are adjacent to file-copy and should not fall back to blind regeneration. The predecessor's output should be visible in the prompt. | Section 6 Phase 0 (Edge case subsection). | Integration test: modified-copy task's spec prompt contains the predecessor's generated code verbatim. |
| R3-S7 | Ops | medium | Add `--dry-run-copy-detection` CLI flag that scans plan tasks and reports which would be routed to file-copy vs LLM, with estimated cost savings. | Allows operators to audit copy detection before committing to a run, similar to R2-S6's `--dry-run-simple-decompose`. Cost savings projection builds confidence in the strategy. | Section 5 (Integration with DFA). | CLI test: flag produces report listing copy tasks, source tasks, and projected savings. |

**Endorsements (from prior rounds):**

- **R1-S1** (decision order/exclusivity): Strongly endorsed — the addition of `file_copy` as Phase 0 makes explicit routing even more critical. Without it, a copy task could accidentally enter `_handle_simple`.
- **R2-S3** (`decomposition_source` tracking): Endorsed — extend to include `"copy"` as a valid source value.
- **R2-S6** (dry-run flag): Endorsed — combine with R3-S7 into a unified `--dry-run-deterministic` flag covering both copy detection and simple decomposition.

#### Review Round R4

- **Reviewer**: Codex
- **Date**: 2026-03-07
- **Scope**: Gap-hunting pass focused on splice determinism, render contracts, and safety guards

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|---|---|---|---|---|---|---|
| R4-S1 | Architecture | high | Require an all-or-nothing decomposition plan: assemble in memory, then splice only if **all** sub-elements render and pass verification; otherwise fall back to `_handle_simple` without partial writes. | Partial splices would leave mixed template and stub output, making repair/verification ambiguous and hard to recover. | Section 4.1 (Assembly) and Section 5.1 (Data Flow). | Test where one sub-element fails template match → no file changes and `_handle_simple` is invoked. |
| R4-S2 | Interfaces | medium | Define a render contract for templates used by SimpleDecomposer (body-only vs full `def` block, indentation policy, trailing newline rules). | String concatenation is underspecified; inconsistent render modes will break indentation and class layout. | Section 4.1 (Assembly) or Section 3.3 (Strategies). | Snapshot test for a class with 2 methods ensuring correct indentation and blank-line spacing. |
| R4-S3 | Data | medium | Add a DFA-origin anchor on `ForwardElementSpec` (e.g., `skeleton_anchor_id` or `stub_span`) and require splicing by anchor rather than name-only matching. | Name-only lookup can collide across scopes or miss renamed stubs; anchors make splicing deterministic and resilient to same-name elements. | Section 5.1 (Data Flow) and Section 4.2 (Sub-element construction). | Unit test with two same-named methods in different classes uses distinct anchors and splices correctly. |
| R4-S4 | Risks | high | Add a skeleton-signature mismatch gate: if the DFA stub signature differs from the `ForwardElementSpec` signature, reject decomposition and fall back. | Template matches can still be wrong if the manifest is stale or if DFA generation diverged; this guard prevents silent mis-splices. | Section 4.2 (Confidence / rejection). | Negative test with mismatched param name/order forces `_handle_simple` fallback. |
| R4-S5 | Validation | medium | Add idempotence tests: running SimpleDecomposer twice should produce identical output and no additional splices. | Deterministic assembly should be stable across reruns; idempotence catches hidden state or non-deterministic ordering. | Section 6 (Validation) or new “Validation” subsection. | Run two passes and `diff` output; assert no changes on pass 2. |
| R4-S6 | Ops | low | Emit a rejection-reason taxonomy (e.g., `no_template_match`, `skeleton_mismatch`, `unsafe_decorator`, `render_contract_violation`) and report top-N counts per run. | Fine-grained rejection data is needed to prioritize template expansion and improve decomposition heuristics. | Section 8 (Open Questions) or Section 4.1 (High Feasibility). | Unit test confirms counters increment for each rejection path. |
| R4-S7 | Security | low | Require safe literal serialization in templates (e.g., `repr`/JSON for string defaults and docstrings) and forbid raw string injection from manifest fields. | Prevents malformed or malicious manifest values from injecting code via unescaped quotes or newlines. | Section 4.2 (Sub-element construction) or Section 3.3 (Strategies). | Security test with malicious default string ensures output is properly escaped. |

#### Review Round R5

- **Reviewer**: Codex
- **Date**: 2026-03-07
- **Scope**: Low-hanging fruit and quick wins to increase deterministic coverage and operator value

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|---|---|---|---|---|---|---|
| R5-S1 | Architecture | medium | Add a “template-first short-circuit” in `_handle_simple`: if `template_registry.is_trivial()` matches, render immediately without invoking SimpleDecomposer. | This is a low-effort fast path that increases deterministic completions without new decomposition logic. It also reduces work when a new template is added later. | Section 5.1 (Data Flow) and Section 6 Phase 2. | Unit test: SIMPLE element that matches a new template bypasses SimpleDecomposer and LLM. |
| R5-S2 | Interfaces | low | Add a `--simple-decomposer-report` flag that outputs a per-run summary (attempted, succeeded, rejected + top reasons) to a stable path like `.startd8/reports/simple-decomposer.json`. | Quick win for adoption: makes it easy to see value without digging through logs and avoids adding a full observability stack. | Section 5 (Integration) or Section 8 (Open Questions). | CLI test: flag emits JSON with expected keys and counts. |
| R5-S3 | Data | medium | Add a `template_coverage` map in the report: counts per template type used during SimpleDecomposer (e.g., `dunder_method: 12`). | This is low-effort and immediately informs which templates yield the most benefit and where to expand next. | Section 5.2 (Synergy) or Section 8. | Unit test: decompositions using two templates produce correct counts. |
| R5-S4 | Risks | medium | Add a “no-regression” constraint: if SimpleDecomposer output is identical to the DFA stub (no real implementation added), treat it as a reject and fall back to LLM. | Prevents false positives where template render emits empty or placeholder bodies, which would silently reduce quality. | Section 4.2 (Confidence / rejection). | Test: template render that equals stub triggers fallback. |
| R5-S5 | Validation | low | Add a “quick win” test pack with 5 representative SIMPLE cases (init, repr, constant group, property getter, type alias) to validate deterministic coverage gains. | Small, fast tests provide immediate signal without waiting for large integration runs. | Section 6 (Validation) or new “Validation” subsection. | Run in CI and assert 0 LLM calls for the 5 cases. |
| R5-S6 | Ops | low | Add a cost-savings estimate to the report: `llm_calls_avoided` and `usd_saved_estimate` using a configurable per-call rate. | This is a simple calculation that makes the benefit visible and justifies follow-on investment. | Section 7 (Conclusion) or Section 8 (Open Questions). | Unit test: given counts and rate, compute expected savings. |
| R5-S7 | Security | low | Add a quick static guard: reject decomposition if any sub-element name contains whitespace or non-identifier characters before template rendering. | Very small change that blocks obvious injection vectors with minimal complexity. | Section 4.2 (Sub-element construction). | Security test with invalid identifier rejects decomposition. |

#### Review Round R6

- **Reviewer**: Antigravity
- **Date**: 2026-03-07
- **Scope**: Final pass focused on gap-hunting, effort-to-value quick wins, and telemetry synergy (Phase 2b).

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|---|---|---|---|---|---|---|
| R6-S1 | Architecture | high | Run `ast.parse` on the assembled output snippet prior to writing to disk as a final syntax gate. | Catches edge cases in string concatenation blindly producing syntactically invalid Python (bad indentation, rogue characters). An instant syntax guarantee with zero LLM fallback if syntax error is detected. | Section 5 (Integration with Deterministic File Assembly) | Deliberately mangle a template format and verify the assembly cleanly catches the AST parse failure. |
| R6-S2 | Interfaces | medium | Allow defining string-based templates as pure Python `.py.jinja` files or decorated python functions instead of hardcoded strings. | Developers can use IDE tooling (linting, type hints, highlighting) on the templates. Enhances velocity and dramatically reduces human error when authoring new templates. | Section 3.3 (Decomposition Strategies) | Review standard template ingestion path from module directory loading. |
| R6-S3 | Data | medium | Introduce a baseline deterministic template for `Pydantic` models and `.dataclass` items. | Modern microservices are intensely data-driven. Automatically converting a schema manifest to an explicit Pydantic model is rigid, zero LLM, and incredibly high coverage for many boilerplate entities. | Section 6, Phase 2 (Template Registry Expansion) | Create a dummy spec mimicking a typical structured API model and generate it perfectly without an LLM. |
| R6-S4 | Risks | low | Pass the specific template rejection reason (e.g. `param_mismatch`, `unsafe_decorator`) back into the context for `_handle_simple` when retreating to the LLM. | Pre-injecting the deterministic failure reason focuses the LLM on generating precisely what failed (e.g., if it failed due to a missing optional param template, the LLM generates just that with absolute accuracy). | Section 4.2 (Confidence / rejection) | Read output of `_handle_simple` prompt to ensure failure metadata is propagated. |
| R6-S5 | Validation | low | Develop a simple historical replay tool using Git history of the last 5 merged codebase PRs. | Instantly calculates the true deterministic ratio from historical truth without full framework execution. Very cheap way to prioritize which new templates yield immediate payoff. | Section 6 (Validation) | Replay a known commit that added a Pydantic model and prove `llms_avoided=1`. |
| R6-S6 | Ops | low | Emit `assembly.strategy={template\|copy\|llm_simple}` as an OpenTelemetry attribute onto the respective span dynamically. | You are already collecting telemetry; piggybacking structural completion state on OTel spans creates a free Grafana dashboard of deterministic savings per run. | Section 6 or Section 8 (Metrics) | Query Zipkin or Prometheus backend for `assembly.strategy` distribution. |
| R6-S7 | Security | high | Implement strict path normalization `os.path.abspath(os.path.join(workspace, path)).startswith(workspace)` for Phase 0 duplicate `copy_source`. | Zero-LLM tasks could be hijacked from malicious/buggy payloads to traverse outside scopes like `../../etc/passwd` to a target path without review. | Section 6, Phase 0 (Integration) | Negative test: A task payload path with `../` returns a blocking traversal rejection. |
