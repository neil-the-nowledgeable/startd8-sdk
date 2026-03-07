# Kaizen-Mottainai Audit: Forward Manifest Data Waste Chain

**Date**: 2026-03-06
**Auditor**: Claude Opus 4.6 (agent-assisted)
**Scope**: Runs 003-004 of cap-dev-pipe (online-boutique-demo, Python, Prime route)
**Trigger**: 3/7 generated files rated PARTIAL on structural equivalence despite pipeline PASS verdict
**Method**: End-to-end data trace from plan authoring through code generation, evaluated against Mottainai Design Principle application rules

---

## 1. Audit Purpose and Reuse Intent

This document records the **investigation method** used to identify Mottainai violations in the Forward-Looking Code Manifest (FLCM) extraction and injection pipeline. The method is designed to be repeatable after any pipeline run where generated code diverges from reference implementations.

The audit answers: **Where in the pipeline was invested upstream data discarded, and what was the measurable consequence?**

---

## 2. Prerequisites

Before starting this audit you need:

| Artifact | Where to Find | Purpose |
|----------|---------------|---------|
| Generated files | `pipeline-output/{project}/run-NNN/plan-ingestion/generated/` | The code the pipeline produced |
| Reference implementation | Configured reference path (e.g., `~/Documents/dev/micro-service-demo/...`) | Ground truth for structural comparison |
| Forward manifest (in seed) | `pipeline-output/{project}/run-NNN/plan-ingestion/prime-context-seed.json` → `forward_manifest` key | Contracts and file specs extracted by the pipeline |
| Kaizen artifacts | `pipeline-output/{project}/run-NNN/` → `kaizen-metrics.json`, `kaizen-suggestions.json`, `prime-postmortem-report.json`, `kaizen-trends.json`, `kaizen-correlation.json` | Feedback loop data |
| Kaizen prompts | `pipeline-output/{project}/run-NNN/plan-ingestion/kaizen-prompts/standalone/{task-id}/` | Actual prompts sent to LLM |
| Mottainai Design Principle | `startd8-sdk/docs/design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md` | The 6 application rules and known gap inventory |
| Forward Manifest design doc | `startd8-sdk/docs/design/forward-manifest/04_FORWARD_MANIFEST.md` | Schema capabilities vs actual usage |
| Extractor source | `startd8-sdk/src/startd8/forward_manifest_extractor.py` | Where extraction logic lives |
| Context resolution source | `startd8-sdk/src/startd8/contractors/context_resolution.py` | Where contracts are injected into Lead Contractor prompts |
| Prompt builder source | `startd8-sdk/src/startd8/micro_prime/prompt_builder.py` | Where ForwardElementSpec is consumed (Micro Prime path) |
| Prime contractor source | `startd8-sdk/src/startd8/contractors/prime_contractor.py` | Where gen_context is built and forwarded |

---

## 3. Audit Procedure

### Phase 1: Quality Evaluation (Establish the Gap)

**Goal**: Determine which generated files diverge from the reference and characterize the divergence.

**Steps**:

1. **List generated files** for the run:
   ```
   Glob: pipeline-output/{project}/run-NNN/plan-ingestion/generated/**/*.py
   ```

2. **Read each generated file and its reference counterpart** side by side. For each file, assess:
   - **Structural equivalence**: Same classes, functions, methods, module-level structure?
   - **Functional completeness**: Real implementation or `[STARTD8-SKELETON]` stub?
   - **API/contract fidelity**: Correct gRPC methods, protobuf types, health check patterns?
   - **Dependency alignment**: Same imports, same libraries?
   - **Behavioral correctness**: Same signal handling, env vars, server lifecycle, logging patterns?

3. **Rate each file**: PASS / PARTIAL / FAIL with specific divergences noted.

4. **For PARTIAL files, identify the specific implementation differences** — these are the audit targets. Record them as concrete code comparisons (reference line N vs generated line M).

**Output**: Quality scorecard with specific divergence descriptions per PARTIAL/FAIL file.

### Phase 2: Kaizen Data Review (Check the Feedback Loop)

**Goal**: Determine whether the Kaizen system detected the quality gaps and whether its feedback mechanisms are functional.

**Steps**:

1. **Read post-mortem reports** for each run:
   ```
   Read: pipeline-output/{project}/run-NNN/plan-ingestion/prime-postmortem-report.json
   Read: pipeline-output/{project}/run-NNN/plan-ingestion/prime-postmortem-summary.md
   ```
   Check: Does `aggregate_score` / `verdict` reflect quality, or only success?

2. **Read Kaizen metrics**:
   ```
   Read: pipeline-output/{project}/run-NNN/plan-ingestion/kaizen-metrics.json
   ```
   Check: `success_rate`, `escalation_rate`, `top_root_causes`. Are quality divergences visible?

3. **Read Kaizen suggestions**:
   ```
   Read: pipeline-output/{project}/run-NNN/plan-ingestion/kaizen-suggestions.json
   ```
   Check: Are suggestions populated? Do they address the divergences found in Phase 1?

4. **Read cross-run trends and correlation**:
   ```
   Read: pipeline-output/{project}/run-NNN/kaizen-trends.json
   Read: pipeline-output/{project}/run-NNN/kaizen-correlation.json
   ```
   Check: Sufficient data points? Prompt-outcome correlation computed?

5. **Read captured prompts** for PARTIAL tasks:
   ```
   Read: pipeline-output/{project}/run-NNN/plan-ingestion/kaizen-prompts/standalone/{task-id}/spec_user_prompt.md
   Read: pipeline-output/{project}/run-NNN/plan-ingestion/kaizen-prompts/standalone/{task-id}/draft_user_prompt.md
   Read: pipeline-output/{project}/run-NNN/plan-ingestion/kaizen-prompts/standalone/{task-id}/metadata.json
   ```
   Check: What context did the LLM actually receive? What was missing?

**Output**: Kaizen system health assessment — is the feedback loop producing actionable signal?

### Phase 3: Forward Manifest Contract Audit (Trace What Was Extracted)

**Goal**: Determine what contracts the FLCM extractor produced and whether they carry sufficient detail.

**Steps**:

1. **Extract forward manifest from context seed**:
   ```
   Grep: "contract_id|binding_text" in prime-context-seed.json
   ```
   List all contracts applicable to the PARTIAL tasks. Note which `ContractCategory` values are represented.

2. **Check for absent categories**: The FLCM schema supports 8 categories: `FUNCTION_NAME`, `CLASS_NAME`, `API_ENDPOINT`, `CONFIG_KEY`, `IMPORT_PATH`, `FORMULA`, `RENDER_PATTERN`, `INFRASTRUCTURE`. Count contracts per category. Categories with zero contracts are potential waste points.

3. **Compare contracts to the design doc worked example** (`04_FORWARD_MANIFEST.md` Section 10). The worked example shows the contracts that WOULD prevent the specific defect class. Are those contracts present? If not, why?

4. **Check `file_specs`**: For each PARTIAL task's target file, check whether the `ForwardFileSpec` has complete elements:
   ```python
   # Extract from seed JSON:
   file_specs.get("src/emailservice/logger.py", {}).get("elements", [])
   ```
   Check: Are all classes/functions from `api_signatures` represented? Are signatures, bases, decorators preserved?

**Output**: Contract completeness matrix — what the schema supports, what the extractor produced, what's missing.

### Phase 4: Upstream Data Trace (Find Where Detail Was Lost)

**Goal**: Trace the specific data transformations where rich upstream detail was discarded.

This is the core Mottainai audit. For each PARTIAL task, follow the data through every pipeline boundary.

**Steps**:

1. **Plan → ParsedFeature**: Read the plan file. Verify `api_signatures` carry the detail (class names with bases, full parameter lists, return types). Usually preserved — plan ingestion is faithful here.

2. **ParsedFeature → Extractor**: This is the critical boundary. Run the extractor functions against the actual `api_signatures` to see what survives:
   ```python
   from startd8.forward_manifest_extractor import _extract_function_name, _parse_python_signature

   for sig in feature.api_signatures:
       fname = _extract_function_name(sig)
       parsed = _parse_python_signature(sig)
       print(f"INPUT:  {sig!r}")
       print(f"  func_name:  {fname!r}")
       print(f"  parsed_sig: {parsed}")
   ```

   **What to look for**:
   - Does `_extract_function_name` preserve class names and base classes, or strip them?
   - Does `_parse_python_signature` handle `"Class X(Base)"` syntax, or return `None`?
   - Which `InterfaceContract` fields are populated vs left as `None`?
   - Does `compute_binding_text()` include signatures and annotations, or only bare names?

3. **Extractor → ForwardManifest → Context Seed**: Verify the contracts and file_specs in the serialized seed match what the extractor produced. Check for serialization loss.

4. **Context Seed → gen_context (Lead Contractor path)**: Trace how `context_resolution.py` reads the forward manifest and what it injects:
   ```
   Grep: "forward_manifest|binding_constraints" in context_resolution.py
   ```
   **What to look for**:
   - Does it call `binding_constraints_for_task()` (text strings only)?
   - Does it also call `file_specs_for_task()` (element data with signatures)?
   - Where does it inject: `domain_constraints`? `forward_contracts`? Both?

5. **gen_context → Prompt**: Read the captured Kaizen prompt for the PARTIAL task. Search for any trace of the forward manifest data. Does the prompt contain:
   - Contract binding text? (should be present)
   - ForwardElementSpec data (signatures, bases)? (likely absent for Lead Contractor)
   - design_doc_sections? (should be present but check detail level)

6. **Compare Micro Prime path**: Check `prompt_builder.py` to see whether it consumes `ForwardElementSpec` data that the Lead Contractor path does not. This reveals asymmetric consumption — data available to one generation path but not the other.

**Output**: Per-boundary data trace showing what entered, what exited, and what was lost. Each loss point maps to a Mottainai application rule violation.

### Phase 5: Cross-Run Behavioral Comparison (Measure Non-Determinism)

**Goal**: Determine whether the same plan/requirements produce consistent implementations across runs.

**Steps**:

1. **Read the same file from multiple runs**:
   ```
   Read: pipeline-output/.../run-003/.../generated/src/emailservice/logger.py
   Read: pipeline-output/.../run-004/.../generated/src/emailservice/logger.py
   ```

2. **Diff the implementations**: Focus on the behavioral choices the LLM made differently:
   - Different libraries or APIs for the same function
   - Different patterns for the same requirement (e.g., timestamp formatting)
   - Different structural organization (module-level vs class-level)

3. **For each divergence, ask**: Was there a contract that COULD have constrained this? If the forward manifest had a `FORMULA` contract for timestamp handling, would both runs have produced the same code?

**Output**: Non-determinism inventory — where the LLM made arbitrary choices that a contract could have bound.

### Phase 6: Classification and Remediation (Map to Mottainai Rules)

**Goal**: Classify each finding against the 6 Mottainai application rules and the 3 anti-patterns.

**Mottainai Application Rules**:
1. Inventory before generating
2. Forward, don't regenerate
3. Degrade gracefully
4. Register what you produce
5. Prefer deterministic over stochastic
6. Measure the gap

**Anti-Patterns** (from Artisan Internal Audit):
- **Serialize-and-forget**: Rich data produced, only subset serialized
- **Compute-but-don't-forward**: Data computed in one phase, never read by the phase that needs it
- **Inject-but-don't-validate**: Deterministic data injected but no post-generation check

For each finding:
1. State the data that was available upstream
2. State the boundary where it was lost
3. State the consequence (which PARTIAL/FAIL verdict it caused)
4. Map to Mottainai rule(s) violated
5. Map to anti-pattern
6. Propose fix with estimated effort

**Output**: Post-mortem document (see `design/RUN4_POSTMORTEM_PARTIAL_QUALITY.md` for the template produced by this audit).

---

## 4. Findings from This Audit (2026-03-06)

### 4.1 Summary

| Phase | Key Finding |
|-------|-------------|
| Phase 1 | 3 PARTIAL, 2 FAIL out of 7 files. Pipeline reported PASS (1.0 score). |
| Phase 2 | Kaizen feedback loop non-functional: no quality signal, no suggestions, no correlation data. |
| Phase 3 | 68 contracts extracted, all structural (names + imports). Zero FORMULA, RENDER_PATTERN, CONFIG_KEY contracts. 3/8 schema categories unused. |
| Phase 4 | Three data loss boundaries identified: (a) class signatures fail to parse, (b) binding_text strips annotations, (c) Lead Contractor path ignores ForwardElementSpec. |
| Phase 5 | Same plan produced 3 different timestamp implementations across 2 runs. |
| Phase 6 | 6 findings mapped to Mottainai rules 2, 5, 6 and all 3 anti-patterns. |

### 4.2 Detailed Findings

#### F1: Class Signature Parse Failure (Serialize-and-Forget)

**Boundary**: `_extract_api_signatures()` → `_extract_function_name()` + `_parse_python_signature()`

**Data available**: `"Class CustomJsonFormatter(jsonlogger.JsonFormatter)"`
- Base class: `jsonlogger.JsonFormatter`
- Class name: `CustomJsonFormatter`
- Implicit: this is a class, not a function

**Data after extraction**:
- `_extract_function_name()` → `"Class CustomJsonFormatter"` (includes "Class " prefix, base class stripped at parenthesis)
- `_parse_python_signature()` → `None` (wraps as `def Class CustomJsonFormatter(jsonlogger.JsonFormatter): pass` — invalid Python syntax)
- No `ForwardElementSpec` created (guard: `if parsed_sig and feature.target_files`)
- Contract category: `FUNCTION_NAME` (should be `CLASS_NAME`)
- Contract fields `class_name`, `base_class`: `None`

**Consequence**: The most important structural element in the logger (what base class to extend) vanishes from the manifest. The LLM must infer it from requirements text.

**Rule violated**: R2 (Forward, don't regenerate)

#### F2: Binding Text Strips Annotations (Serialize-and-Forget)

**Boundary**: `compute_binding_text()` (and `_compute_binding_text_from_kwargs()`)

**Data available** (in `ForwardElementSpec.signature`):
```
getJSONLogger(name: str) -> logging.Logger
add_fields(self, log_record, record, message_dict) -> None
```

**Data in binding_text**:
```
[BINDING] | function=getJSONLogger | Function getJSONLogger from API signature
[BINDING] | function=add_fields | Function add_fields from API signature
```

Parameter types, return annotations, and parameter count — all lost. The `FUNCTION_NAME` branch of `compute_binding_text` only outputs `function={name}`.

**Consequence**: Lead Contractor receives contract text indistinguishable from a function name list. No structural prescription.

**Rule violated**: R2 (Forward, don't regenerate)

#### F3: ForwardElementSpec Not Consumed by Lead Contractor (Compute-but-Don't-Forward)

**Boundary**: `context_resolution.py` → Lead Contractor `gen_context`

**Data available** (in `ForwardManifest.file_specs`):
```
src/emailservice/logger.py:
  add_fields(self, log_record, record, message_dict) → None
  getJSONLogger(name: str) → logging.Logger
```

**Data injected into Lead Contractor**: Only `binding_constraints_for_task()` output (text strings). `file_specs_for_task()` is never called for the Lead Contractor path.

**Compare Micro Prime path**: `prompt_builder.py` receives `ForwardElementSpec` objects with full signatures, bases, and decorators. Uses them for element-level body generation prompts.

**Consequence**: Two consumption paths with asymmetric data access. Tasks generated via Lead Contractor (PI-001 through PI-003) receive degraded contract data. Tasks that go through Micro Prime element decomposition receive full structural specs.

**Rule violated**: R2 (Forward, don't regenerate)

#### F4: design_doc_sections Advisory Not Prescriptive (Inject-but-Don't-Validate)

**Boundary**: `prime_contractor.py` line 2574 → `gen_context["design_doc_sections"]`

**Data available**:
```python
["CustomJsonFormatter with add_fields override",
 "getJSONLogger factory function",
 "stdout handler with JSON format string"]
```

**How it's consumed**: Injected into the prompt as advisory context. No post-generation validation that the output honored these sections.

The third section — "stdout handler with JSON format string" — hints at `CustomJsonFormatter('%(timestamp)s %(severity)s %(name)s %(message)s')` but doesn't spell it out. The LLM treats it as a suggestion.

**Rule violated**: R5 (Prefer deterministic over stochastic)

#### F5: Requirements Contradict Reference (Upstream Quality)

**Boundary**: Plan authoring (human)

PI-001/PI-002 requirements: `timestamp — ISO-8601 formatted time`
Reference implementation: `log_record['timestamp'] = record.created` (float epoch)

Not a Mottainai violation per se — the waste origin is requirements quality. But it amplifies the other violations: even if contracts were perfectly extracted, the requirements text would still direct the LLM to produce ISO-8601 timestamps.

A reference AST analyzer producing a `FORMULA` contract would surface this conflict at extraction time.

#### F6: Kaizen Measures Success Not Quality (Inject-but-Don't-Validate)

**Boundary**: Post-mortem generation → `kaizen-metrics.json`

Both runs reported `aggregate_score: 1.0`, `verdict: PASS`. The pipeline's quality gate measures generation success (code compiles, review score adequate) — not structural equivalence against reference.

`kaizen-suggestions.json`: empty for both runs. `kaizen-correlation.json`: zero data points (path bug + insufficient runs). The entire Kaizen feedback loop produced no actionable output.

**Rule violated**: R6 (Measure the gap)

### 4.3 Mottainai Violation Classification

| Finding | Anti-Pattern | Rule(s) | Source Module | Fix Effort |
|---------|-------------|---------|---------------|------------|
| F1 | Serialize-and-forget | R2 | `forward_manifest_extractor.py:_extract_function_name`, `_parse_python_signature` | Low: add class-pattern detection |
| F2 | Serialize-and-forget | R2 | `forward_manifest.py:compute_binding_text` | Low: include signature in text |
| F3 | Compute-but-don't-forward | R2 | `context_resolution.py` | Medium: add file_specs injection |
| F4 | Inject-but-don't-validate | R5 | `prime_contractor.py` | Medium: enrich design_doc_sections |
| F5 | N/A (upstream) | -- | Plan requirements | Low: reconciliation check |
| F6 | Inject-but-don't-validate | R6 | Kaizen post-mortem | Medium: add quality evaluation |

---

## 5. Checklist for Future Audits

Use this checklist when running this audit against a new pipeline run:

- [ ] **Phase 1**: Read all generated files. Read all reference files. Rate each: PASS / PARTIAL / FAIL. Record specific divergences for PARTIAL files.
- [ ] **Phase 2**: Read kaizen-metrics.json, kaizen-suggestions.json, prime-postmortem-report.json, kaizen-trends.json, kaizen-correlation.json. Assess: does the feedback loop detect quality gaps?
- [ ] **Phase 3**: Extract forward manifest from prime-context-seed.json. Count contracts per `ContractCategory`. Identify unused categories. Compare against Section 10 worked example.
- [ ] **Phase 4**: For each PARTIAL task, run `_extract_function_name` and `_parse_python_signature` against the actual `api_signatures`. Trace data through `context_resolution.py` injection. Read captured Kaizen prompt. Identify loss boundaries.
- [ ] **Phase 5**: If multiple runs exist, diff generated files for the same task. Count non-deterministic implementation choices. Identify which could be bound by contracts.
- [ ] **Phase 6**: Classify each finding: anti-pattern, Mottainai rule, source module, fix effort. Write post-mortem.

---

## 6. Key Investigation Commands

### Extract forward manifest contracts for a task
```bash
python3 -c "
import json
with open('pipeline-output/.../prime-context-seed.json') as f:
    seed = json.load(f)
fm = seed.get('forward_manifest', {})
contracts = fm.get('contracts', [])
task_contracts = [c for c in contracts if 'PI-001' in c.get('applicable_task_ids', [])]
for c in task_contracts:
    print(f'{c[\"contract_id\"]}: {c[\"binding_text\"]}')
"
```

### Trace extractor behavior on actual signatures
```bash
cd startd8-sdk && python3 -c "
from startd8.forward_manifest_extractor import _extract_function_name, _parse_python_signature
sigs = [
    'Class CustomJsonFormatter(jsonlogger.JsonFormatter)',
    'def add_fields(self, log_record, record, message_dict) -> None',
    'def getJSONLogger(name: str) -> logging.Logger',
]
for sig in sigs:
    fname = _extract_function_name(sig)
    parsed = _parse_python_signature(sig)
    print(f'INPUT:  {sig!r}')
    print(f'  func_name:  {fname!r}')
    print(f'  parsed_sig: {parsed}')
"
```

### Check ForwardFileSpec element completeness
```bash
python3 -c "
import json
with open('pipeline-output/.../prime-context-seed.json') as f:
    seed = json.load(f)
file_specs = seed.get('forward_manifest', {}).get('file_specs', {})
for path, spec in file_specs.items():
    elems = spec.get('elements', [])
    print(f'{path}: {len(elems)} elements')
    for e in elems:
        sig = e.get('signature', {})
        ret = sig.get('return_annotation', 'None') if sig else 'N/A'
        print(f'  {e[\"kind\"]}: {e[\"name\"]} -> {ret}')
"
```

### Count contracts by category
```bash
python3 -c "
import json
from collections import Counter
with open('pipeline-output/.../prime-context-seed.json') as f:
    seed = json.load(f)
contracts = seed.get('forward_manifest', {}).get('contracts', [])
counts = Counter(c.get('category', 'unknown') for c in contracts)
for cat, n in counts.most_common():
    print(f'  {cat}: {n}')
print(f'Total: {len(contracts)}')
"
```

---

## 7. Relationship to Other Documents

| Document | Relationship |
|----------|-------------|
| `MOTTAINAI_DESIGN_PRINCIPLE.md` | The principle and 39 known gaps this audit evaluates against |
| `04_FORWARD_MANIFEST.md` | FLCM design spec — Section 10 worked example shows contracts that would prevent the defects found |
| `RUN4_POSTMORTEM_PARTIAL_QUALITY.md` (cap-dev-pipe) | The post-mortem produced by this audit instance |
| `KAIZEN_PRIME_REQUIREMENTS.md` | Kaizen system requirements — gaps F5/F6 show the feedback loop is non-functional |
| `KAIZEN_DATA_ANALYSIS_GUIDE.md` | Guide for interpreting the Kaizen artifacts read in Phase 2 |
