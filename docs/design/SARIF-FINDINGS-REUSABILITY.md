# SARIF & the cross-language semantic layer — reusability map + convergence plan

**Project:** startd8-sdk · coverage_map / cross-language semantic validation
**Status:** analysis + first slice shipped · **re-verified against code 2026-08-16 (6 corrections)**   **Date:** 2026-08-15
**Slice landed:** `coverage_map/findings_sarif.py::render_sarif_from_findings` (generic sibling of
the coverage `render_sarif`) + `tests/unit/languages/test_findings_sarif.py`. Since: `startd8 validate`
CLI (#473) wires the 5 SemanticIssue validators; `validators/rule_catalog.py` (#475) is the SemanticIssue
rule authority. Before routing the *other* producers, §2 + §4 were re-verified — see §0.5.

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

## 0.5 Verification audit (2026-08-16) — corrections before routing

Re-grounded every §2 row against current code before routing the non-SemanticIssue producers. The
line-carrying typed producers held; **six claims were wrong or stale** and change the routing order:

| # | Doc claimed | Actual (verified) | Consequence |
|---|---|---|---|
| C1 | *Security gate → `GateFinding` drop-in* | **`GateFinding`/`GateFileEntry` are a dormant schema** — defined + exported, **never constructed**. The live gate path is dict-based (`security_prime/gate_metrics.py`); real security findings are `SecurityFinding` from `query_prime/security/*.py`. | Route **`SecurityFinding`**, not `GateFinding`. Drop the GateFinding row. |
| C2 | *`ContractViolation` → partial (no line)* | The renderer's rule-id chain (`check/check_type/rule_id/check_id/category`) **does not read `violation_type`** → ContractViolation is **skipped outright**, not merely line-less. | Needs a **rule-id alias** (add `violation_type` to the chain, or adapt), not just a line. |
| C3 | *observability issues → has file, no line* | The issue dict is `{check, severity, message}` with **no file** — `file_path` is on the parent `*ValidationResult`. | Skipped as-is; route via **parent→issue file-stamping**. |
| C4 | *`DiskComplianceResult.semantic_issues` → normalize first* | Dominant shape `{category, severity, message}` with **no file** (~30 sites); only 3 sites add file+line; one site appends a **bare `str`**. | Mostly skipped; low priority, needs real normalization. |
| C5 | *repair `{Syntax,Lint,Import}Diagnostic` → file+line, sev ⚠* | Base + Syntax/Import/Lint carry **no `severity` field** (degrade to `warning`); **`ImportDiagnostic` has no line**; many more subclasses now exist (`Semantic`, `Contract`, `Convention`, …). | Drop-in but severity always `warning`; broaden beyond 3 subclasses. |
| C6 | *`TodoEntry.category` = rule* | `category` ∈ `{A,B,C}` is a **resolvability class, not a rule name**; no `severity`, no `message` field. | Routing yields opaque ruleIds `A/B/C`; use a **synthetic rule id** (`todo_unresolved`) instead. |

**Net:** the code is current; the *doc's claims about it* had drifted. Only **`SecurityFinding`** and
**`cross_file Finding`** are genuinely drop-in today. See the corrected §2 table and §4 plan.

### The RULE_CATALOG dimension (net-new since this doc)
`validators/rule_catalog.py` (#475) is the authority **only** for the SemanticIssue producers. Routing
each new producer raises the question "does it get its own per-producer catalog?" — answered by whether
it already carries an enumerable rule vocabulary:

| Producer | Rule vocabulary | Catalog seed |
|---|---|---|
| observability issues | **`OBS-*` ids (~46, already namespaced)** via `_issue(check_id,…)` | **strong** → `PRODUCER="startd8-obs"` |
| `SecurityFinding` | **`SecurityCheckType` enum** (4 values) | **strong** → `PRODUCER="query-security"` |
| cross_file `Finding` | `check_id` + `_REMEDIATION` map (de-facto set) | medium |
| repair Diagnostics | `category` string-literal set (`syntax\|import\|lint\|test\|size`+subclass) | medium |
| ContractViolation | `contract.category` enum + ad-hoc `violation_type` | weak |
| TodoEntry / semantic_issues | `{A,B,C}` class / inline literals | none (synthetic id) |

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

*(Corrected 2026-08-16 — see §0.5. rule-id field / file field named per row.)*

| Use case | Producer (path:line) | rule-id ← | file ← | line | sev | SARIF-ready |
|---|---|---|---|:--:|:--:|---|
| **Cross-lang semantic validation** ⭐ | `validators/*_semantic_checks.py::SemanticIssue` | `check` | `file_path` | ✅ | ✅ | **drop-in — DONE (via `validate`)** |
| Security findings | `query_prime/models.py:164::SecurityFinding` | `check_type` (enum→`.value`) | `file_path`(opt) | ✅ | ✅ | **drop-in — route this (not GateFinding)** |
| ~~Security gate~~ | ~~`security_prime/gate_models.py::GateFinding`~~ | — | — | — | — | **DORMANT — never constructed (C1); skip** |
| Cross-file validation | `validators/cross_file_verifier.py:49::Finding` | `check_id` | `source_file` | ❌ (`locus`) | ✅ | **drop-in, file-level** (no region) |
| Repair | `repair/models.py:51::Diagnostic` (+subclasses) | `category` | `file` | Syntax/Lint ✅, Import ❌ | ❌ field → `warning` | drop-in; sev degrades (C5) |
| TODO / test scan | `validators/todo_scanner.py:123::TodoEntry` | `category`={A,B,C}→**use synthetic id** | `file_path` | ✅ | — | needs synthetic rule + degrade (C6) |
| Contract compliance | `forward_manifest_validator.py:27::ContractViolation` | **`violation_type` — renderer doesn't read it** | `file_path`(opt) | ❌ | ✅ | **SKIPPED (C2)** — needs rule-id alias |
| O11y artifact gen/validation | `observability/artifact_generator.py`, `validators/observability_artifact_validators.py:98` | `check` (`OBS-*`) | **parent `*ValidationResult.file_path`** | ❌ | ✅ | needs parent→issue file-stamp (C3) |
| Disk compliance | `forward_manifest_validator.py:352::DiskComplianceResult.semantic_issues` | `category` | **mostly absent** | ~ | ✅ | mostly skipped — normalize (C4) |
| Truncation | `truncation_detection.py:32::TruncationResult` | — | ❌ | ❌ | — | not a per-file finding (NR-2) |

`render_sarif_from_findings` consumes the drop-in rows (rule-id via `check`/`check_type`/`check_id`/
`category`; file via `file_path`/`file`/`source_file`) and **honestly skips + counts** anything lacking a
rule id or file. **Note (C2):** `violation_type` is *not* in that rule-id chain — ContractViolation is
skipped until aliased or the chain is extended.

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
2. **Adopt cheapest-first (corrected order, 2026-08-16 — with the exact change each needs):**

   | Order | Producer | What routing needs | Catalog |
   |---|---|---|---|
   | ✅ done | SemanticIssue | — (via `validate`) | `startd8-semantic` |
   | **1** | **`SecurityFinding`** | genuine drop-in — collect from `query_prime/security/*.py` + render. Optional-file findings self-skip. | seed `query-security` from `SecurityCheckType` |
   | **2** | **cross_file `Finding`** | drop-in, file-level (no region) — collect + render | seed from `_REMEDIATION` map |
   | **3** | repair `Diagnostic`s | drop-in; accept sev→`warning`; cover all subclasses, not 3 | `category` set |
   | **4** | observability issues | **parent→issue file-stamp** (`_ValidationResult.file_path` onto each `_issue`) | strong: `startd8-obs` from `OBS-*` |
   | **5** | `TodoEntry` | **synthetic rule id** (`todo_unresolved`); category→a `properties` tag | synthetic |
   | **6** | `ContractViolation` | **add `violation_type` to the renderer's rule-id chain** (or adapt); still no line | weak |
   | — | ~~GateFinding~~ | **skip — dormant schema (C1)** | — |
   | — | `semantic_issues` / TruncationResult | defer (C4) / exclude (NR-2) | — |

   Where a producer's file lives on a **parent** (observability; the GateFinding pattern that turned out
   dormant), the adapter walks parent→children and stamps `file` — do NOT push that into the renderer.
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
