# Pipeline Safety Gate Requirements

**Source:** PI-012 + PI-013 artisan run failure analysis
**Date:** 2026-02-23
**Cost of failure:** $0.74, 6m22s — 7 phases of pipeline work lost with no manifest

---

## Context

The PI-012 + PI-013 artisan run exposed three systemic gaps that allowed failures to cascade through the pipeline. Each gap maps to a violation of one or more established design principles:

- **[Context Correctness by Design](../../design-princples/CONTEXT_CORRECTNESS_BY_DESIGN.md)** (CCD) — design-time context must be available before LLM generation
- **[Context Correctness by Construction](../../design-princples/CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)** (CCC) — runtime boundary validation at phase transitions
- **[Mottainai](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md)** — aversion to wasteful loss of invested computation

The immediate fix (adding `@staticmethod` to `_count_gate3b_by_severity`, commit `f29dd81`) addresses the symptom. This document captures the 13 formal requirements that address the systemic gaps.

### Root Cause Chain

```
DESIGN hallucinates module import (context_strategies.py doesn't exist)
  → IMPLEMENT generates code with bad import (no module inventory in prompt)
    → Gate 4 detects truncation but only warns (warning-only contract)
      → INTEGRATE merges truncated code over existing production files
        → TEST fails on import errors (cascading)
          → REVIEW passes (separate concern)
            → FINALIZE crashes on missing @staticmethod → TypeError
              → No manifest produced. 7 phases of work lost.
```

---

## Principle Mapping

Each gap is mapped to the design principles it violates.

| Gap | by Design | by Construction | Mottainai |
|-----|-----------|----------------|-----------|
| **A: FINALIZE crash** | — | No per-task error guard at FINALIZE boundary | 7 phases of work lost with no final artifact (serialize-and-forget) |
| **B: Truncation overwrites** | — | Warning-only contract at Gate 4; no blocking escalation at INTEGRATE | Existing production code overwritten by truncated generation |
| **C: Module hallucination** | IMPLEMENT lacks module inventory context (SCAFFOLD discovered structure but didn't forward it) | No import validation at INTEGRATE boundary | SCAFFOLD data computed but not forwarded (compute-but-don't-forward) |

---

## Gap Analysis: Cap-Dev-Pipe Phase Placement

### Gap A: FINALIZE Crash — Missing `@staticmethod`

**What failed:** `_count_gate3b_by_severity()` was called without `self` but lacked `@staticmethod` → `TypeError` killed FINALIZE. No manifest was written. All 7 phases of work ($0.74) produced no final artifact.

**Phase trace:**

| Phase | What Happened | What Should Happen |
|-------|--------------|-------------------|
| FINALIZE | TypeError on `_count_gate3b_by_severity()` kills entire phase | **AR-813**: Per-task error guard — single task crash doesn't kill manifest |
| FINALIZE | No partial output on crash | **AR-815**: Partial manifest with `incomplete: true` flag |
| (cross-cutting) | Missing `@staticmethod` not caught statically | **AR-814**: Static method audit via mypy/lint |

### Gap B: Truncation Overwrites Existing Code

**What failed:** 3 files had truncation detected at confidence >= 0.5. Gate 4 logged warnings but did not block. INTEGRATE merged truncated code over existing production files, destroying working code.

**Phase trace:**

| Phase | What Happened | What Should Happen |
|-------|--------------|-------------------|
| IMPLEMENT (Gate 4) | Truncation detected, warning logged, task proceeds | **AR-816**: Set `truncation_blocked: true` on generation result |
| IMPLEMENT (Gate 4) | Contract YAML declares truncation as `severity: warning` | **AR-817**: Upgrade to `severity: blocking` when `truncation_blocked: true` |
| INTEGRATE | Truncated file merged despite being < 70% of existing file size | **AR-818**: Size regression hard block (< 70% + truncation >= 0.5 → reject) |
| INTEGRATE | No compound gate for truncation + existing file | **AR-819**: Stricter threshold (0.5 vs 0.7) when target exists |
| INTEGRATE | No telemetry on rejection | **AR-820**: OTel span event with truncation metadata |

### Gap C: Module Hallucination — `context_strategies.py`

**What failed:** LLM imported `context_strategies.py` which doesn't exist in the project. SCAFFOLD had walked the directory tree and knew the project structure, but this knowledge was not forwarded to IMPLEMENT. No import validation occurred at INTEGRATE.

**Phase trace:**

| Phase | What Happened | What Should Happen |
|-------|--------------|-------------------|
| SCAFFOLD | Directory tree walked, target files identified | **AR-821**: Extract module inventory (`__init__.py` presence → package names) |
| DESIGN/IMPLEMENT | LLM has no project module context, hallucinates imports | **AR-822**: Inject `scaffold.module_inventory` into generation prompt |
| INTEGRATE | File with bad imports merged without validation | **AR-823**: Parse imports, reject unresolvable first-party imports |
| (contract) | No declared propagation for module inventory | **AR-824**: Add to contract YAML enrichment section |
| INTEGRATE | No telemetry on import validation | **AR-825**: OTel span attribute for unresolved imports |

---

## Requirements

### Layer 1: FINALIZE Resilience (AR-813–815)

**Principles:** by Construction (runtime boundary validation), Mottainai (7 phases of work lost)
**Cap-Dev-Pipe Phase:** FINALIZE

#### AR-813: Per-Task Error Guard in FINALIZE

**Status:** planned
**Principle:** by Construction
**Cross-ref:** AR-165 (Gate 3 compatibility), OT-507 (span error handling)
**Mottainai Gap:** 30 (per-validator results lost)

`_build_finalize_summary()` wraps per-task processing in try/except. A single task's Gate 3b error does not crash the manifest for all tasks. Failed tasks are recorded with their error in the manifest; successful tasks produce complete entries.

**Acceptance criteria:**

1. Each task in the FINALIZE loop is wrapped in an individual try/except block.
2. A task-level exception (e.g., `TypeError` in `_count_gate3b_by_severity`) does not propagate to the outer loop.
3. Failed tasks are recorded in the manifest with `error: str` and `success: false`.
4. Successful tasks are recorded normally regardless of other tasks' failures.
5. Pattern is consistent with existing per-task error guards in IMPLEMENT, TEST, and REVIEW phases.

#### AR-814: Static Method Audit

**Status:** planned (P0)
**Principle:** by Construction
**Cross-ref:** — (structural type correctness)

All non-`self`-using methods in phase handlers must be decorated `@staticmethod`. A mypy `--strict` configuration or a dedicated lint rule catches missing decorators at CI time rather than at FINALIZE runtime.

**Acceptance criteria:**

1. All methods in `context_seed_handlers.py` phase handler classes that do not reference `self` are decorated with `@staticmethod`.
2. CI pipeline includes a check (mypy strict mode or custom lint rule) that flags instance methods not using `self`.
3. The `_count_gate3b_by_severity` method specifically is verified as `@staticmethod`.

#### AR-815: Partial Manifest on FINALIZE Failure

**Status:** planned
**Principle:** Mottainai
**Cross-ref:** AR-161 (manifest), AR-906 (FINALIZE diagnostics)
**Mottainai Gap:** 37 (serialize-and-forget — FINALIZE crash destroys manifest)

If FINALIZE crashes after processing N of M tasks, write a partial `generation-manifest.json` with what was collected plus an `incomplete: true` flag and the error details. This ensures that the value of completed phases is not lost.

**Acceptance criteria:**

1. On unhandled exception in FINALIZE, a `generation-manifest.json` is written before the exception propagates.
2. The partial manifest includes all tasks processed before the crash.
3. The partial manifest has `incomplete: true` and `error: str` at the top level.
4. Downstream tooling can distinguish partial from complete manifests via the `incomplete` flag.

---

### Layer 2: Truncation Enforcement (AR-816–820)

**Principles:** by Construction (contract enforcement), Mottainai (existing code destroyed)
**Cap-Dev-Pipe Phases:** IMPLEMENT (Gate 4) → INTEGRATE

#### AR-816: Gate 4 Truncation Escalation

**Status:** planned
**Principle:** by Construction
**Cross-ref:** AR-175 (truncation guard), AR-908 (integrity at output time)
**Mottainai Gap:** 32 (truncation confidence not in manifest)

When Gate 4 detects truncation with confidence >= 0.5, mark the task's generation result with `truncation_blocked: true`. INTEGRATE reads this flag and **skips** the file (does not merge to `project_root`).

**Acceptance criteria:**

1. Gate 4 truncation detection sets `truncation_blocked: true` on the generation result when confidence >= 0.5.
2. The `truncation_blocked` flag is persisted in the generation result (survives checkpoint/resume).
3. INTEGRATE checks `truncation_blocked` before merging each task's files.
4. Files with `truncation_blocked: true` are not copied to `project_root`.
5. Skipped files are logged with truncation confidence and the reason for rejection.

#### AR-817: Contract YAML Severity Upgrade

**Status:** planned
**Principle:** by Construction
**Cross-ref:** AR-175 (truncation guard)

`artisan-pipeline.contract.yaml` IMPLEMENT exit: change `truncation_flags` from `severity: warning` to `severity: blocking` for tasks where `truncation_blocked: true`.

**Acceptance criteria:**

1. `artisan-pipeline.contract.yaml` IMPLEMENT exit section is amended to declare truncation as blocking when the task carries `truncation_blocked: true`.
2. Contract validation at the IMPLEMENT→INTEGRATE boundary enforces the blocking severity.
3. A task with `truncation_blocked: true` that reaches the IMPLEMENT exit gate triggers a blocking violation (not a warning).

#### AR-818: Size Regression Hard Block

**Status:** planned
**Principle:** Mottainai
**Cross-ref:** AR-175 (truncation guard), REQ-EFE-020, REQ-CCD-501 (mode conflict)
**Mottainai Gap:** 38 (overwrite existing assets)

When a generated file is < 70% of the existing file's size AND truncation confidence >= 0.5, INTEGRATE MUST reject the file. Currently `integration_engine.py` writes anyway at low confidence.

**Acceptance criteria:**

1. INTEGRATE computes the size ratio `generated_size / existing_size` for each target file that exists on disk.
2. When `size_ratio < 0.7` AND `truncation_confidence >= 0.5`, the file is rejected (not merged).
3. Rejected files are logged with both the size ratio and truncation confidence.
4. The existing file is preserved unmodified on rejection.
5. The task's integration result records `rejected_files` with reasons.

#### AR-819: Truncation + Existing File Compound Gate

**Status:** planned
**Principle:** by Construction
**Cross-ref:** AR-175 (truncation guard), REQ-EFE-020

When both (a) truncation is detected at any confidence and (b) the target file exists on disk, the INTEGRATE phase applies the stricter threshold (0.5 instead of 0.7 for rejection).

**Acceptance criteria:**

1. INTEGRATE detects whether each target file exists on disk before merge.
2. For files where the target exists, truncation rejection threshold is lowered from 0.7 to 0.5.
3. For files where the target does not exist (new files), the standard threshold (0.7) applies.
4. The applied threshold is logged alongside the truncation confidence for observability.

#### AR-820: Truncation Rejection OTel Event

**Status:** planned
**Principle:** by Construction (observable contracts — CCC Layer 1 principle 6)
**Cross-ref:** OT-300 (per-task spans)

When INTEGRATE rejects a file due to truncation, emit a span event with diagnostic metadata.

**Acceptance criteria:**

1. A span event is emitted on each truncation-based file rejection.
2. The event includes attributes: `truncation.confidence` (float), `truncation.action` ("rejected" or "allowed"), `file.size_ratio` (float), `file.existing_size` (int), `file.generated_size` (int).
3. The event is attached to the per-task INTEGRATE span.

---

### Layer 3: Module Resolution Fidelity (AR-821–825)

**Principles:** by Design (design-time context), by Construction (runtime validation), Mottainai (SCAFFOLD data not forwarded)
**Cap-Dev-Pipe Phases:** SCAFFOLD → DESIGN/IMPLEMENT → INTEGRATE

#### AR-821: SCAFFOLD Module Inventory

**Status:** planned
**Principle:** by Design + Mottainai
**Cross-ref:** AR-903 (metadata forwarding)
**Mottainai Gap:** 39 (compute-but-don't-forward — SCAFFOLD discovers structure but doesn't forward module names)

SCAFFOLD phase collects the list of importable Python modules under `project_root/src/` (package names from `__init__.py` presence). Stored as `scaffold.module_inventory: list[str]`.

**Acceptance criteria:**

1. SCAFFOLD scans `project_root/src/` (and project root if no `src/` exists) for directories containing `__init__.py`.
2. Package names are computed as dotted module paths relative to the package root.
3. Results are stored in `context["scaffold"]["module_inventory"]` as `list[str]`.
4. The scan adds zero LLM cost (purely filesystem-based, reusing the directory walk SCAFFOLD already performs).
5. An empty project produces an empty list (not an error).

#### AR-822: Module Inventory Injection in IMPLEMENT Prompts

**Status:** planned
**Principle:** by Design (CCD Rule D4: "manifest before prompt")
**Cross-ref:** AR-130 (chunk execution)
**Mottainai Gap:** 10 (onboarding not in gen context)

When `scaffold.module_inventory` is available, inject it into the code generation prompt: "The following modules exist in this project: {modules}. Import from these modules, not invented ones."

**Acceptance criteria:**

1. `ImplementPhaseHandler` reads `context["scaffold"]["module_inventory"]` during prompt construction.
2. When present and non-empty, the module list is included in the code generation prompt.
3. The prompt instruction explicitly tells the LLM to import only from listed modules.
4. When absent or empty, prompt construction proceeds without the module list (graceful degradation).

#### AR-823: Import Validation at INTEGRATE

**Status:** planned
**Principle:** by Construction
**Cross-ref:** AR-175 (truncation guard)

Before merging a Python file, parse its `import`/`from` statements and check that each first-party import resolves to an existing module (stdlib + project modules from scaffold inventory). Reject files with unresolvable first-party imports.

**Acceptance criteria:**

1. INTEGRATE parses `import` and `from ... import` statements from each generated `.py` file using `ast.parse`.
2. Each import is classified as: stdlib, third-party (from project dependencies), or first-party (from project modules).
3. First-party imports are validated against `scaffold.module_inventory`.
4. Files with unresolvable first-party imports are rejected (not merged).
5. Rejected files are logged with the list of unresolved imports.
6. Stdlib and third-party imports are not validated (assumed correct).

#### AR-824: Contract YAML Module Inventory Propagation

**Status:** planned
**Principle:** by Construction (CCC — declared propagation chain with boundary validation)
**Cross-ref:** REQ-CCD-600 (contract amendment)

Add `scaffold.module_inventory` to the IMPLEMENT phase's enrichment section in `artisan-pipeline.contract.yaml` with `severity: warning` and `source_phase: scaffold`.

**Acceptance criteria:**

1. `artisan-pipeline.contract.yaml` IMPLEMENT entry section includes `scaffold.module_inventory` in its enrichment requirements.
2. The enrichment entry specifies `severity: warning` (missing inventory degrades gracefully, does not block).
3. The enrichment entry specifies `source_phase: scaffold` for traceability.
4. Contract validation at the SCAFFOLD→DESIGN→IMPLEMENT boundary checks for the presence of `scaffold.module_inventory`.

#### AR-825: Module Resolution OTel Span Attribute

**Status:** planned
**Principle:** by Construction (observable contracts)
**Cross-ref:** OT-300 (per-task spans)

Per-task span in INTEGRATE includes import validation diagnostics.

**Acceptance criteria:**

1. The per-task INTEGRATE span includes `task.import_validation.unresolved_count` (int) attribute.
2. The per-task INTEGRATE span includes `task.import_validation.unresolved_modules` (string, comma-separated) attribute.
3. Attributes are set to 0 / empty string for tasks with no import validation issues.

---

## Cap-Dev-Pipe Phase Placement

```
PLAN ──→ SCAFFOLD ──→ DESIGN ──→ IMPLEMENT ──→ INTEGRATE ──→ TEST ──→ REVIEW ──→ FINALIZE
           │                        │              │                              │
           │                        │              │                              ├─ AR-813: per-task error guard
           │                        │              │                              ├─ AR-814: static method audit
           │                        │              │                              └─ AR-815: partial manifest
           │                        │              │
           │                        │              ├─ AR-816: truncation_blocked flag honored
           │                        │              ├─ AR-818: size regression hard block
           │                        │              ├─ AR-819: compound gate (trunc + existing)
           │                        │              ├─ AR-820: rejection OTel event
           │                        │              ├─ AR-823: import validation before merge
           │                        │              └─ AR-825: import validation OTel attribute
           │                        │
           │                        ├─ AR-816: Gate 4 sets truncation_blocked flag
           │                        ├─ AR-817: contract YAML severity upgrade
           │                        └─ AR-822: module inventory in prompt
           │
           ├─ AR-821: module inventory collection
           └─ AR-824: contract YAML propagation chain
```

---

## Traceability

| Requirement | Mottainai Gap | CCD Req | AR Cross-Ref | OTel Cross-Ref | Principle |
|-------------|--------------|---------|--------------|----------------|-----------|
| AR-813 | Gap 30 (per-validator results lost) | — | AR-165 (Gate 3 compatibility) | OT-507 (span error handling) | by Construction |
| AR-814 | — | — | — | — | by Construction |
| AR-815 | Gap 37 (serialize-and-forget) | — | AR-161 (manifest), AR-906 (FINALIZE diagnostics) | — | Mottainai |
| AR-816 | Gap 32 (truncation confidence not in manifest) | — | AR-175 (truncation guard), AR-908 (integrity at output time) | — | by Construction |
| AR-817 | — | — | AR-175 | — | by Construction |
| AR-818 | Gap 38 (overwrite existing assets) | REQ-CCD-501 (mode conflict) | AR-175, REQ-EFE-020 | — | Mottainai |
| AR-819 | — | — | AR-175, REQ-EFE-020 | — | by Construction |
| AR-820 | — | — | — | OT-300 (per-task spans) | by Construction |
| AR-821 | Gap 39 (scaffold data not forwarded) | — | AR-903 (metadata forwarding) | — | by Design + Mottainai |
| AR-822 | Gap 10 (onboarding not in gen context) | REQ-CCD-302 (manifest in prompt) | AR-130 (chunk execution) | — | by Design |
| AR-823 | — | — | AR-175 | — | by Construction |
| AR-824 | — | REQ-CCD-600 (contract amendment) | — | — | by Construction |
| AR-825 | — | — | — | OT-300 (per-task spans) | by Construction |

---

## Implementation Priority

| Phase | Requirements | Rationale |
|-------|-------------|-----------|
| **P0: Immediate** (blocks next run) | AR-813, AR-814 | FINALIZE crash prevention — without this, every future run risks losing its manifest |
| **P1: High** (prevents data loss) | AR-816, AR-817, AR-818, AR-819 | Truncation enforcement — prevents destructive overwrites of existing code |
| **P2: Medium** (prevents hallucination) | AR-821, AR-822, AR-823, AR-824 | Module resolution — prevents LLM from importing non-existent modules |
| **P3: Observability** | AR-815, AR-820, AR-825 | Partial manifest, OTel events — value extraction and visibility |

---

## Mottainai Gaps

These three failures add to the [Mottainai gap inventory](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md):

| Gap | Category | Description | Cost |
|-----|----------|-------------|------|
| **Gap 37** | Serialize-and-forget | FINALIZE crash destroys manifest — 7 phases of pipeline work produce no final artifact | Full pipeline cost ($0.74 in this run) |
| **Gap 38** | Overwrite existing assets | Truncated code overwrites working production code — existing invested code destroyed | Existing code value + regeneration cost |
| **Gap 39** | Compute-but-don't-forward | SCAFFOLD discovers project structure but module names not forwarded to IMPLEMENT — LLM hallucinates imports | Wasted IMPLEMENT + TEST cost for tasks with bad imports |

---

## Related Documents

| Document | Relationship |
|----------|-------------|
| [ARTISAN_REQUIREMENTS.md](ARTISAN_REQUIREMENTS.md) | Parent requirements document — AR-813..AR-825 registered in Layer 8 |
| [Mottainai Design Principle](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Gaps 37-39 added to the gap inventory |
| [Context Correctness by Design](../../design-princples/CONTEXT_CORRECTNESS_BY_DESIGN.md) | CCD rules violated by Gap C (module hallucination) |
| [Context Correctness by Construction](../../design-princples/CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) | CCC rules violated by all three gaps |
| [artisan-pipeline.contract.yaml](../../contractors/contracts/artisan-pipeline.contract.yaml) | Contract amendments for AR-817, AR-824 |
| [ARTISAN_WORKFLOW_ISSUES_CATALOG.md](../../ARTISAN_WORKFLOW_ISSUES_CATALOG.md) | PI-012/PI-013 issue catalog entries |
