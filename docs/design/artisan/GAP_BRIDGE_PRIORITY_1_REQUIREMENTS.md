# Gap Bridge Priority 1: High-Impact, Low-Effort Artisan Improvements

**Version:** 1.0.0
**Created:** 2026-02-26
**Status:** Draft
**Parent:** [ARTISAN_FEATURE_COVERAGE_GAP_ANALYSIS.md](ARTISAN_FEATURE_COVERAGE_GAP_ANALYSIS.md)
**Covers:** Three actionable gaps that are high-value and low-effort relative to their impact.

---

## 1. Goal

Close three specific gaps identified in the Artisan feature coverage audit that have disproportionate
value-to-effort ratios:

1. **REQ-GAP1-A** — Surface Forward Manifest contract violations in the REVIEW phase LLM prompt
2. **REQ-GAP1-B** — Inject Forward Manifest contracts into the Prime Contractor's spec prompt  
3. **REQ-GAP1-C** — Add call graph blast radius as a sixth complexity dimension in Plan Ingestion

---

## 2. GAP1-A: Surface FM Violations in Review Prompt

### 2.1 Problem

`ReviewPhaseHandler` already calls `validate_forward_manifest` (line 9945 of `context_seed_handlers.py`)
and collects `fm_violations`. However, **these violations are not surfaced to the lead agent's review
prompt**. The reviewer LLM sees no mention of contract violations; they only appear in output metadata.
This means the LLM cannot act on them to produce a contextual review that calls out the specific
structural defect.

### 2.2 Requirement (REQ-GAP1-A-001)

**Requirement:** When `validate_forward_manifest` returns one or more `error`-severity violations,
the REVIEW prompt must include a `## Forward Manifest Contract Violations` section enumerating them.

**Implementation:**

- After calling `validate_forward_manifest(forward_manifest, registry)` in `ReviewPhaseHandler.execute()`,
  if `fm_violations` is non-empty, format a text block using the `ContractViolation` fields:
  `contract_id`, `violation_type`, `expected`, `actual`, `file_path`, `severity`.
- Append this section to the review prompt **before** the code content is shown, so it frames
  what the reviewer should look for.
- Format:

  ```
  ## Forward Manifest Contract Violations
  The following structural contracts were violated by the generated code.
  These are BLOCKING issues that MUST be called out in the review.

  - [ERROR] contract_id=FM-001 | type=missing_function | expected=getJSONLogger | actual=None | file=logger.py
  - [ERROR] contract_id=FM-002 | type=wrong_base_class | expected=IService | actual=None | file=service.py
  ```

- `warning`-severity violations should be included as `[WARN]` but not labeled BLOCKING.
- When no violations exist, the section is omitted entirely.

**Files to modify:**

- `src/startd8/contractors/context_seed_handlers.py` — `ReviewPhaseHandler.execute()` — after
  `fm_violations` is collected, build the violation text and pass it to the review prompt builder.
- `src/startd8/contractors/context_seed_handlers.py` — `_build_review_prompt()` or
  `ReviewPhaseHandler._build_review_prompt()` — add `forward_contract_violations` as an input
  parameter and insert the new section.

**Verification:**

- Unit test: mock `validate_forward_manifest` to return one `ContractViolation(severity="error")`.
  Assert the review prompt includes `## Forward Manifest Contract Violations` and the violation text.
- Regression: when `forward_manifest` is `None`, assert the section does not appear and no error occurs.

---

## 3. GAP1-B: Prime Contractor Spec Prompt — Forward Manifest Injection

### 3.1 Problem

`PrimeContractorWorkflow.load_seed_context()` correctly extracts `forward_manifest` and stores it
as `self.seed_forward_manifest` (line 1135 of `prime_contractor.py`). However, `LeadContractorWorkflow._build_spec_prompt()` does not read or render `forward_contracts` from the context. The contracts sit
in `gen_context["forward_contracts"]` (set by `PipelineContextStrategy`) but are never consumed.

This matches `REQ-PC-FM-006` from `Phase_4_Prime_Contractor_Forward_Manifest_Requirements.md`.

### 3.2 Requirement (REQ-GAP1-B-001)

**Requirement:** `LeadContractorWorkflow._build_spec_prompt()` must include a dedicated
`## Interface Contract Bindings` section when `context["forward_contracts"]` is non-empty.

**Implementation (Option A — Dedicated Section, recommended):**

- In `_build_spec_prompt()` (in `lead_contractor_workflow.py`), pop `forward_contracts` from
  the context dict passed in.
- If the value is a non-empty string or list, render it as a new section placed **after** domain
  constraints and **before** requirements text:

  ```
  ## Interface Contract Bindings
  The following interface contracts are MANDATORY. The generated code MUST satisfy all BINDING
  entries. Non-compliance will be detected during review and cause the draft to fail.

  {forward_contracts}
  ```

- If the context has no `forward_contracts` key or its value is falsy, omit the section entirely.

**Prompt Template (YAML):**

Add a `forward_contracts_section` key to `lead_contractor.yaml` in the `spec` section:

```yaml
forward_contracts_section: |
  ## Interface Contract Bindings
  The following interface contracts are MANDATORY. The generated code MUST satisfy all BINDING
  entries. Non-compliance will be detected during automated review.

  {forward_contracts}
```

**Files to modify:**

- `src/startd8/contractors/prime_contractor.py` — verify `forward_manifest` is included in the
  `config["context"]` block passed to `lead.run()` (if not already done via `REQ-PC-FM-003`).
- `src/startd8/workflows/builtin/lead_contractor_workflow.py` — `_build_spec_prompt()` — add
  the new section rendering logic and corresponding YAML template key lookup with fallback.
- `src/startd8/workflows/builtin/prompts/lead_contractor.yaml` — add `forward_contracts_section`
  key to the spec prompts section.

**Verification:**

- Unit test: call `_build_spec_prompt()` with `context={"forward_contracts": "[BINDING] function=foo"}`.
  Assert spec string contains `## Interface Contract Bindings` and the binding text.
- Integration test: run Prime Contractor with a seed containing `forward_manifest`; assert spec prompt
  in walkthrough output includes the bindings section.
- Regression: run without `forward_manifest`; assert no section, no crash.

---

## 4. GAP1-C: Plan Ingestion — Call Graph Complexity Dimension

### 4.1 Problem

`_heuristic_assess_complexity()` in `plan_ingestion_workflow.py` scores each feature across 5
dimensions. Phase 6 call graph data (`ManifestRegistry.blast_radius()`, `dead_candidates()`,
`callers_of()`) is available at plan ingestion time but contributes nothing to the complexity score.

Features that modify heavily-called functions can be misclassified as "low complexity" because
they touch few files, even though their blast radius is enormous.

This matches `CG-PI-1`, `CG-PI-2`, `CG-PI-3`, `CG-PI-4` from
`CODE_MANIFEST_PHASE6_PIPELINE_REQUIREMENTS.md`.

### 4.2 Requirements

#### REQ-GAP1-C-001: `call_graph_impact` as a Sixth Complexity Dimension

**Requirement:** When a `ManifestRegistry` with call graph data (`mode="bytecode"`) is available,
compute a `call_graph_impact` score for each feature and incorporate it into the complexity total.

**Implementation:**

- In `_heuristic_assess_complexity()`, after existing 5-dimension scoring, add:

  ```python
  # Phase 6 CG-PI-1: call graph impact
  if registry is not None:
      target_fqns = _extract_feature_target_fqns(feature, registry)
      if target_fqns:
          max_fqn, max_radius = registry.max_blast_radius(target_fqns)
          cg_score = min(max_radius / 20.0, 1.0)  # normalize: 20+ callers = max score
          scores["call_graph_impact"] = cg_score
  ```

- The `max_blast_radius()` method must be added to `ManifestRegistry` (see Priority 2 doc for
  the full extension set; this method is already covered in Phase 6 core).

**Note:** `max_blast_radius()` is specified in `CODE_MANIFEST_PHASE6_PIPELINE_REQUIREMENTS.md`
Section 10.1 and should already be implemented as part of Phase 6 core. Verify availability
before wiring.

#### REQ-GAP1-C-002: `affected_callers` Annotation on Features

**Requirement:** Annotate each `ParsedFeature` with `affected_callers: list[str]` — the union
of `callers_of(fqn)` for all target FQNs. Store in feature metadata for downstream use.

**Implementation:**

- After computing blast radius, populate:

  ```python
  feature.metadata["affected_callers"] = list(
      set().union(*(registry.callers_of(fqn) for fqn in target_fqns))
  )
  ```

- Drives future task scheduler ordering to serialize features with overlapping blast radii.

#### REQ-GAP1-C-003: High-Blast-Radius Warning

**Requirement:** When `max_radius > 20` (configurable via `blast_radius_warning_threshold` in
artisan config), annotate the feature with `high_impact: true` and emit a WARNING log.

**Implementation:**

```python
threshold = self.config.get("blast_radius_warning_threshold", 20)
if max_radius > threshold:
    feature.metadata["high_impact"] = True
    logger.warning(
        "CG-PI-3: Feature %s has blast radius %d (> %d threshold). High integration risk.",
        feature.feature_id, max_radius, threshold,
    )
```

#### REQ-GAP1-C-004: Dead Code Feature Detection

**Requirement:** If all target FQNs of a feature appear in `registry.dead_candidates()`, annotate
`feature.metadata["targets_dead_code"] = True` and log at INFO.

**Verification:**

- Unit test: mock registry with known blast radii; assert `call_graph_impact` in feature complexity
  score, and score is higher than baseline without call graph.
- Unit test: feature targeting a function with 25 callers; assert `high_impact: true` annotation
  and WARNING log.
- Unit test: feature targeting functions all in `dead_candidates()`; assert `targets_dead_code` annotation.
- Regression: plan ingestion with `mode="static"` manifests (no call graph); assert 5-dimension scoring
  is identical to pre-change behavior.

---

## 5. Proposed Changes Summary

| File | Change | REQ |
|------|--------|-----|
| `src/startd8/contractors/context_seed_handlers.py` | Build violation text from `fm_violations`; inject into review prompt via `_build_review_prompt()` | GAP1-A |
| `src/startd8/workflows/builtin/lead_contractor_workflow.py` | Add `forward_contracts` section to `_build_spec_prompt()` | GAP1-B |
| `src/startd8/workflows/builtin/prompts/lead_contractor.yaml` | Add `forward_contracts_section` prompt template key | GAP1-B |
| `src/startd8/contractors/prime_contractor.py` | Verify `forward_contracts` flows into `config["context"]` for `lead.run()` | GAP1-B |
| `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | Add `call_graph_impact` 6th dimension + annotations to `_heuristic_assess_complexity()` | GAP1-C |

---

## 6. Verification Plan

1. **GAP1-A unit test** — Mock validator, assert violations appear in review prompt text.
2. **GAP1-B unit test** — Call `_build_spec_prompt` with `forward_contracts` in context, assert section in spec string.
3. **GAP1-B integration** — Run Prime with FM seed, inspect walkthrough spec prompt.
4. **GAP1-C unit test** — Mock registry with `blast_radius` returning 25, assert `high_impact=True` + 6th score dimension.
5. **All regression** — Run without Forward Manifest / without call graph; assert no behavioral change, no crash.
