# SARIF & the cross-language semantic layer — reusability map + convergence plan

**Project:** startd8-sdk · coverage_map / cross-language semantic validation
**Status:** analysis + first slice shipped   **Date:** 2026-08-15
**Slice landed:** `coverage_map/findings_sarif.py::render_sarif_from_findings` (generic sibling of
the coverage `render_sarif`) + `tests/unit/languages/test_findings_sarif.py` (22 tests).

> **Semantic name:** *Reuse the SARIF renderer as a universal cross-language findings sink, and the
> coverage/precision three-tier pattern as cross-language traceability engines.*

---

## 0. Grounding (what actually exists)

The "SARIF capability added as part of coverage mapping" is **`coverage_map/engine.py::render_sarif`**
(on `origin/main` via PR #471). Its decisive property: it is a **pure function of a report dict** —
it reads only `report["pattern_domains"]` (→ `rules[]`) and `report["per_file_hyp"]` (→ `results[]`),
never re-loading the crosswalk. That is a clean seam.

But note *what* it renders: a **coverage** report — "which OTel §5 domain does this file *touch*". All
its results are `level:"note"`, **file-level (no line region)**, one per file×pattern. It is a
*domain-touch* renderer, not yet a *finding* renderer. This distinction drives the whole plan.

### Three distinct reusable assets (do not conflate)

| Asset | What it is | Where | Reuse surface |
|---|---|---|---|
| **A. SARIF renderer** | report/finding → SARIF 2.1.0 | `engine.render_sarif` | universal *findings sink* |
| **B. Coverage engine** | `CoverageAdapter` (4-field per-lang delta) + `Detector` (collision-safe import/annotation match) | `engine.py` | cross-language *"does this corpus touch capability X"* |
| **C. Precision pattern** | domain → contract-IDL + its SDK parser → operation set | `precision.py` | cross-language *"enumerate the operations a contract declares"* |

---

## 1. The decisive finding — a universal finding shape already exists

All five language semantic validators emit **one shared model**,
`validators/semantic_checks.py::SemanticIssue`:

```python
@dataclass(frozen=True)
class SemanticIssue:
    check: str                 # → SARIF ruleId
    severity: str              # → SARIF level (error/warning)
    message: str               # → message.text
    line: Optional[int]        # → region.startLine
    file_path: Optional[str]   # → artifactLocation.uri
```

Go / Java / Node / C# / Python all `_stamp_file_path()` and return `List[SemanticIssue]` carrying
**file + rule + severity + line** — a *richer* SARIF payload than coverage produces today (real line
regions, real severities). `query_prime.models.SecurityFinding` and `security_prime.gate_models.GateFinding`
carry the same fields under `check_type`. So the reuse is nearly free: one renderer that duck-types
`check`/`check_type` consumes all of them.

---

## 2. Producer inventory (grounded)

Fragmentation is the real blocker: **~5 near-universal finding shapes with no shared base.**

| Use case | Producer (file) | Shape | file | line | sev | SARIF-ready |
|---|---|:--:|:--:|:--:|:--:|---|
| **Cross-lang semantic validation** ⭐ | `validators/{,go_,java_,nodejs_,csharp_}semantic_checks.py` | `SemanticIssue` | ✅ | ✅ | ✅ | **drop-in (done)** |
| Security artifact gen/validation | `query_prime/models.py::SecurityFinding` | typed (enum `check_type`) | ✅ | ✅ | ✅ | **drop-in** |
| Security gate | `security_prime/gate_models.py::GateFinding` | typed | ⚠ parent `GateFileEntry` | ✅ | ✅ | drop-in per-file |
| TODO / test-definition scan | `validators/todo_scanner.py::TodoEntry` | typed | ✅ | ✅ | — | rule=`category` |
| Repair | `repair/models.py::{Syntax,Lint,Import}Diagnostic` | typed | ✅ | ✅ | ⚠ | drop-in |
| Cross-file validation | `validators/cross_file_verifier.py::Finding` | typed | ✅ | ❌ (`locus`) | ✅ | partial (locus≠line) |
| Contract compliance | `forward_manifest_validator.py::ContractViolation` | typed | ✅ | ❌ | ✅ | partial (no line) |
| Disk compliance | `…::DiskComplianceResult.semantic_issues` | **untyped `List[dict]`** | ~ | ~ | ✅ | normalize first |
| O11y artifact gen/validation | `observability/artifact_generator.py`, `validators/observability_artifact_validators.py` | `issues: List[dict]` | ✅ | ❌ | ✅ | partial (no line) |
| Truncation | `truncation_detection.py::TruncationResult` | doc-level | ❌ | ❌ | — | not a per-file finding |

`render_sarif_from_findings` already consumes the ✅ rows (via `check`/`check_type`/`check_id`/
`category` + `file_path`/`file`/`source_file`) and **honestly skips + counts** anything lacking a
rule id or file (`invocations[0].properties.skipped`).

---

## 3. Assets B & C across the other use cases you named

- **Requirement definition / declaration** — `navigator/det_req.py` parses `FR-xxx` bullets
  (`Touches:`/`Verify:`); `plan_ingestion_models.py::ParsedFeature.api_signatures` holds operation
  names — but requirement→operation binding is **human-authored**. **Asset C** (`extract_precision`)
  can auto-bind declared FRs to the operations a repo's IDL actually enumerates → a *"does the code
  declare what the requirement promised"* traceability check, itself emitted as SARIF via Asset A.
- **Generation** — `backend_codegen/{crud_generator, openapi_client_renderer, context_grpc_client_renderer}`
  and `test_emitter.py` already iterate **per-operation** off the same three parsers precision wires.
  Precision is the read-only *census twin* of what codegen does write-side (same parsers — Mottainai holds).
- **Testing definition / generation** — `test_emitter.py` emits per-model/route/service tests.
  Precision's operation set is the natural **completeness oracle**: *N* IDL operations, *M* with
  contract tests → the untested `N−M` render as SARIF `note`s.
- **O11y artifact gen** — the real gap: `observability/artifact_generator.py` derives artifacts
  **per-service** from `onboarding-metadata.json`, not per-operation, not IDL-driven. Feeding it
  precision's enumeration lets it emit a span/metric/panel **per endpoint/rpc/model**; the coverage
  SARIF is already OTel-§5-semconv-keyed, so the loop closes.
- **Business-user onboarding artifact gen** — reads `onboarding-metadata.json` (service-level),
  same gap/opportunity as o11y; lowest priority.

---

## 4. Recommended shape

1. **Add** `render_sarif_from_findings(findings, *, tool_name, …)` keyed on the `SemanticIssue`
   shape. **DONE** — `coverage_map/findings_sarif.py`. Pure, duck-typed, degrade-not-drop.
2. **Adopt cheapest-first:** `SemanticIssue` (5 langs, done) → `SecurityFinding` / `GateFinding`
   (drop-in) → `TodoEntry` / repair `Diagnostic`s → partials (`ContractViolation` needs a line;
   `observability issues` need typing; `cross_file Finding.locus`→line).
3. **Follow-up (not done, deliberately):** fold coverage's `render_sarif` onto this generic core so
   there is one SARIF emitter. It is a **merged, tested** path, so this must be a *behaviour-preserving*
   refactor gated by a **parity/characterization test** (byte-identical SARIF for a fixed coverage
   report before/after). Until that guard exists, the two coexist — coverage's renderer is untouched.

This converges ~7 fragmented finding producers on a single GitHub-code-scanning / IDE-consumable sink
— the "collapse N shapes to one source of truth" move `/complexity-distiller` would name here.

## 5. Non-goals / guardrails

- **NR-1** — do not refactor coverage `render_sarif` without a parity test (§4.3).
- **NR-2** — do not force `TruncationResult` (doc-level, no location) into per-file SARIF.
- **NR-3** — no new IDL/finding parser; wire existing producers (Mottainai).
- **NR-4** — a finding without rule id or file is skipped **and counted**, never emitted invalid,
  never silently dropped.

---

### Appendix A — Accepted
### Appendix B — Rejected
### Appendix C — Incoming review rounds
