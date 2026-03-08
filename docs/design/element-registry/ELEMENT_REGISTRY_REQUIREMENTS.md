# Element Registry — Pipeline-Wide Requirements

Persistent, indexed element store enabling cross-phase, cross-task, and cross-run element identity, reuse, and quality tracking across the capability delivery pipeline.

> **Status:** DRAFT
> **Date:** 2026-03-07
> **Scope:** Pipeline-wide (Artisan 8-phase, Prime Contractor, Plan Ingestion, Forward Manifest)
> **Depends on:** [REQ-MP-11xx (Micro-Prime Element Registry)](../micro-prime/REQ-MP-11xx_ELEMENT_REGISTRY.md), [Forward Manifest](../../forward_manifest.py), [Mottainai Design Principle](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md)
> **Supersedes:** None (REQ-MP-11xx remains the micro-prime-specific detail; this document defines the pipeline-wide scope)

---

## 1. Motivation

### 1.1 The Element Is the Natural Unit of the Pipeline

The capability delivery pipeline operates at three granularities:

| Granularity | Example | Where Tracked Today |
|-------------|---------|---------------------|
| **Feature/Task** | PI-001: "Implement JSON logger" | `FeatureSpec`, `SeedTask`, task queues |
| **File** | `src/emailservice/logger.py` | `ForwardFileSpec`, `target_files`, resume cache |
| **Element** | `getJSONLogger()` function | `ForwardElementSpec` — created but not indexed, not persisted, not reusable |

Files are containers. Tasks are work units. **Elements are the semantic unit** — the function, class, or constant that carries meaning. Yet the pipeline tracks elements only at creation time (plan ingestion) and consumption time (micro-prime generation). Between those points, element identity is lost:

- No phase can answer "has this element been generated before?"
- No phase can answer "what quality score did this element receive?"
- No phase can answer "did this element survive review?"
- No handoff carries element-level provenance

### 1.2 Relationship to REQ-MP-11xx

[REQ-MP-11xx](../micro-prime/REQ-MP-11xx_ELEMENT_REGISTRY.md) defines the element registry's core data model and micro-prime integration (REQ-MP-1100 through REQ-MP-1109). Those requirements remain the authoritative specification for the registry's storage layer, engine integration, and CLI interface.

**This document extends** the element registry's scope to cover:
- All 8 artisan phases (not just IMPLEMENT)
- The prime contractor feature loop
- Plan ingestion element creation
- Cross-run Kaizen metrics
- Warm Up reconciliation
- Quality gate integration

### 1.3 Design Principle Alignment

| Principle | How Element Registry Serves It |
|-----------|-------------------------------|
| **Mottainai** | Rules 1 (inventory), 2 (forward), 4 (register), 5 (deterministic over stochastic) — the registry IS the element-level inventory and forwarding mechanism |
| **Kaizen** | Per-element success/failure/repair metrics enable cross-run analysis: which element patterns fail most? Which templates work? Which prompts produce reusable code? |
| **Warm Up** | During toolchain transitions, the registry provides ground truth: "these elements exist and passed review" — backup tools can query before regenerating |

---

## 2. Requirements Summary

Requirements prefixed `ER-` are pipeline-wide. Requirements prefixed `REQ-MP-11xx` are micro-prime-specific and defined in [the micro-prime document](../micro-prime/REQ-MP-11xx_ELEMENT_REGISTRY.md).

| ID | Title | Priority | Phase(s) | Status |
|---|---|---|---|---|
| ER-001 | Element Identity Standard | P0 | All | planned |
| ER-002 | Registry as Pipeline Service | P0 | All | planned |
| ER-003 | Plan Ingestion Element Population | P0 | Plan Ingestion | planned |
| ER-004 | PLAN Phase Element Inventory | P1 | PLAN | planned |
| ER-005 | SCAFFOLD Phase Registry Pre-Fill | P1 | SCAFFOLD | planned |
| ER-006 | DESIGN Phase Element-Level Contracts | P1 | DESIGN | planned |
| ER-007 | IMPLEMENT Phase Registry Integration | P0 | IMPLEMENT | planned |
| ER-008 | INTEGRATE Phase Element Provenance | P1 | INTEGRATE | planned |
| ER-009 | TEST Phase Element-Level Validation | P1 | TEST | planned |
| ER-010 | REVIEW Phase Element-Level Scoring | P2 | REVIEW | planned |
| ER-011 | FINALIZE Phase Element Manifest | P1 | FINALIZE | planned |
| ER-012 | Prime Contractor Element Loop | P0 | Prime | planned |
| ER-013 | Handoff Element State | P1 | Handoff | planned |
| ER-014 | Cross-Run Kaizen Metrics | P2 | Post-Run | planned |
| ER-015 | Warm Up Registry Reconciliation | P2 | Transition | planned |
| ER-016 | Element Quality Gates | P1 | Gates | planned |
| ER-017 | Pipeline Contract Propagation | P1 | Contract | planned |
| ER-018 | Element Lineage and Provenance | P2 | All | planned |

---

## 3. Requirements Detail

### ER-001: Element Identity Standard

**Priority:** P0 | **Phase(s):** All

Define a stable, unique, pipeline-wide element identity scheme.

**Problem:** Element IDs are currently generated in 13+ sites across `forward_manifest_extractor.py` using ad-hoc patterns (`flcm-fn-*`, `flcm-cls-*`, `flcm-ast-*`, `flcm-skel-*`). No specification ensures:
- Uniqueness across tasks, files, and runs
- Stability across re-ingestion of the same plan
- Traceability from creation through generation to review

**Specification:**

```
Element ID format:  flcm-{kind}-{scope}-{name}

  kind:   fn | cls | const | ep | inf | imp | ast | skel | msg | svc
  scope:  Relative file path (normalized, `/` → `-`)
  name:   Element name (function/class/constant name)

Examples:
  flcm-fn-src-emailservice-logger-py-getJSONLogger
  flcm-cls-src-emailservice-formatter-py-CustomJsonFormatter
  flcm-ast-src-emailservice-logger-py-12-add_fields
```

**Constraints:**
- IDs must be deterministic: same plan + same source produces same ID
- IDs must survive plan re-ingestion (not depend on ingestion timestamp or run ID)
- ID collisions (same name in different classes in the same file) resolved by including `parent_class` in scope
- All 13+ existing ID generation sites must be updated to use a single `make_element_id()` utility

**Relationship to REQ-MP-11xx:** REQ-MP-1100 defines `ElementEntry.element_id` — this requirement standardizes how those IDs are created pipeline-wide.

**Acceptance criteria:**
- `make_element_id()` produces identical output for identical inputs across runs
- No two distinct elements in a manifest share an ID
- All existing `flcm-*` generation sites delegate to `make_element_id()`

---

### ER-002: Registry as Pipeline Service

**Priority:** P0 | **Phase(s):** All

The element registry must be a shared service accessible to all pipeline phases and workflows, not embedded in micro-prime.

**Problem:** REQ-MP-1100 places `ElementRegistry` in `src/startd8/micro_prime/element_registry.py`. This couples a pipeline-wide capability to a specific code generation engine. Artisan phases, prime contractor, and plan ingestion all need element access but should not import from `micro_prime/`.

**Specification:**

```
Module: src/startd8/element_registry.py  (top-level package)

Initialization:
  - Created by the pipeline orchestrator (artisan runner, prime contractor)
  - Passed as a dependency to phases, handlers, and generators
  - Singleton per pipeline run; shared across all phases
```

**Interface (extends REQ-MP-1100):**

```python
class ElementRegistry:
    # Core CRUD (from REQ-MP-1100)
    def get(self, element_id: str) -> Optional[ElementEntry]: ...
    def put(self, entry: ElementEntry) -> None: ...
    def has(self, element_id: str) -> bool: ...
    def elements_for_file(self, file_path: str) -> list[ElementEntry]: ...
    def remove(self, element_id: str) -> bool: ...
    def clear(self) -> None: ...

    # Pipeline-wide extensions
    def set_phase_status(self, element_id: str, phase: str, status: str,
                         metadata: dict | None = None) -> None:
        """Record element's status at a specific pipeline phase."""

    def get_phase_status(self, element_id: str, phase: str) -> Optional[str]:
        """Query element's status at a specific phase."""

    def elements_by_status(self, phase: str, status: str) -> list[ElementEntry]:
        """Return all elements with given status at given phase."""

    def element_history(self, element_id: str) -> list[PhaseRecord]:
        """Return chronological history of phase transitions."""

    def summary(self) -> RegistrySummary:
        """Aggregate statistics for reporting and Kaizen."""
```

**Storage layout (extends REQ-MP-1100):**

```
.startd8/state/elements/
├── index.json                         # {element_id: filename}
├── flcm-fn-...-getJSONLogger.json     # ElementEntry + phase history
├── flcm-cls-...-CustomJsonFormatter.json
└── _metrics/                          # Kaizen aggregates
    └── run-{timestamp}.json           # Per-run summary
```

**Constraints:**
- Must use `from startd8.logging_config import get_logger`
- Must not depend on `micro_prime/` — micro-prime imports from here, not vice versa
- Must support concurrent phase access (IMPLEMENT generates while TEST validates prior task's elements)
- REQ-MP-1100's `ElementEntry` dataclass is the base; extended with `phase_history: list[PhaseRecord]`

**Acceptance criteria:**
- `ElementRegistry` importable from `startd8.element_registry` (no micro_prime dependency)
- Artisan phases and prime contractor can share a single registry instance
- Phase status survives process restart

---

### ER-003: Plan Ingestion Element Population

**Priority:** P0 | **Phase(s):** Plan Ingestion

Plan ingestion must populate the element registry with all known elements at pipeline entry.

**Problem:** Plan ingestion creates `ForwardElementSpec` entries scattered across `file_specs` with no registry awareness. The registry starts empty and is only populated during IMPLEMENT when code is generated. Upstream phases (PLAN, SCAFFOLD, DESIGN) cannot query element state.

**Mechanism:**

After `ForwardManifestExtractor.extract()` completes:
1. Iterate all `ForwardFileSpec.elements` in the manifest
2. For each `ForwardElementSpec`, create an `ElementEntry` with `code=None`, `status="specified"`
3. Call `registry.put(entry)` and `registry.set_phase_status(id, "plan_ingestion", "specified")`

This establishes the element inventory before any generation occurs (Mottainai Rule 1).

**Sources of elements at plan ingestion:**

| Source | ID Pattern | When Created |
|--------|-----------|--------------|
| `api_signatures` | `flcm-fn-*`, `flcm-cls-*` | Feature has explicit signatures |
| AST reconciliation | `flcm-ast-*` | `project_root` + existing source |
| Proto extractor | `flcm-cls-svc-*`, `flcm-ep-rpc-*` | `.proto` files present |
| Skeleton derivation (REQ-MP-1104) | `flcm-skel-*` | No api_signatures + skeleton exists |

**Acceptance criteria:**
- After plan ingestion, `registry.summary().total_elements` equals the count of all `ForwardElementSpec` across all `ForwardFileSpec`
- Every element has phase status `("plan_ingestion", "specified")`
- Elements from all 4 sources are registered

---

### ER-004: PLAN Phase Element Inventory

**Priority:** P1 | **Phase(s):** PLAN

The PLAN phase must query the registry to inform task decomposition.

**Problem:** Plan deconstruction breaks features into tasks without knowing which elements already exist in the registry from prior runs. A task that requires 5 elements might find 3 already generated and passing review — the task could be reduced or skipped.

**Mechanism:**

During `plan_deconstruction.py`:
1. For each task's target files, query `registry.elements_for_file(path)`
2. Classify elements as: `generated` (has code), `specified` (no code yet), `unknown` (not in manifest)
3. Include element inventory in task metadata: `{"elements_available": 3, "elements_needed": 5, "elements_total": 5}`
4. If all elements for a task are `generated` with passing quality, mark task as `skip_candidate`

**Acceptance criteria:**
- Task metadata includes element availability counts
- Tasks where all elements are registry hits are flagged as skip candidates
- Logging: `"Task PI-001: 3/5 elements available in registry"`

---

### ER-005: SCAFFOLD Phase Registry Pre-Fill

**Priority:** P1 | **Phase(s):** SCAFFOLD

Extends REQ-MP-1106 (DeterministicFileAssembler Pre-Fill) to be a first-class SCAFFOLD capability.

**Problem:** SCAFFOLD currently renders all elements as `raise NotImplementedError` stubs. If the registry contains validated code for some elements, the skeleton is unnecessarily empty.

**Mechanism:**

During `DeterministicFileAssembler.render_file()`:
1. For each element in `ForwardFileSpec.elements`, check `registry.get(element_id)`
2. If found and `registry.get_phase_status(element_id, "review") == "passed"`:
   - Emit cached implementation with `# [ELEMENT-REGISTRY: {element_id}]` traceability comment
   - Set `registry.set_phase_status(element_id, "scaffold", "pre_filled")`
3. If found but not review-passing: emit stub (regeneration warranted)
4. If not found: emit `raise NotImplementedError` stub
5. Update `registry.set_phase_status(element_id, "scaffold", "stub")` for non-pre-filled

**Acceptance criteria:**
- Skeleton with 5 elements, 2 review-passing in registry: 2 pre-filled, 3 stubs
- Pre-filled skeleton passes `ast.parse()`
- IMPLEMENT phase recognizes and skips pre-filled elements

---

### ER-006: DESIGN Phase Element-Level Contracts

**Priority:** P1 | **Phase(s):** DESIGN

DESIGN should produce and register element-level design constraints.

**Problem:** DESIGN produces a monolithic design document. The document describes element-level decisions (function signatures, class hierarchies, behavioral specs) but these are embedded in prose. No structured element-level design data reaches IMPLEMENT or REVIEW.

**Mechanism:**

After design document generation:
1. Parse design document for element-level decisions using `_extract_referenced_elements()` (already exists in `design_support.py`)
2. For each referenced element, update registry:
   - `registry.set_phase_status(element_id, "design", "designed")`
   - Store design constraints as metadata: `{"signature": "...", "behavioral_spec": "...", "imports": [...]}`
3. Elements mentioned in design but not in manifest: create new entries with `status="design_discovered"`

**Integration with Gap 19 (serialize-and-forget):** Instead of discarding `DesignSection` data, persist element-level extractions in the registry. This is the natural structured companion to the prose design document.

**Acceptance criteria:**
- After DESIGN, elements referenced in design documents have phase status `("design", "designed")`
- Design constraints (signature, behavioral spec) persisted in registry metadata
- Elements discovered during DESIGN that weren't in the manifest are registered

---

### ER-007: IMPLEMENT Phase Registry Integration

**Priority:** P0 | **Phase(s):** IMPLEMENT

This requirement is the pipeline-wide framing of REQ-MP-1102 (Engine Registry Integration) and REQ-MP-1103 (Adapter Registry Integration).

**Mechanism:**

1. Before generation: `registry.get(element_id)` — skip if valid cache hit
2. After generation: `registry.put(entry)` with generated code
3. Phase status: `registry.set_phase_status(element_id, "implement", "generated")`
4. On generation failure: `registry.set_phase_status(element_id, "implement", "failed", {"error": "..."})`

**Cache hierarchy (from REQ-MP-1102):**

```
1. In-memory _success_cache (fingerprint -> code)    # intra-run
2. ElementRegistry (element_id -> ElementEntry)      # cross-run
3. Ollama / cloud fallback                           # generation
```

**Metrics emitted:**
- `element_registry.implement.hits` — elements reused from registry
- `element_registry.implement.misses` — elements generated fresh
- `element_registry.implement.cost_saved_usd` — estimated savings from reuse

**Acceptance criteria:**
- Same as REQ-MP-1102 and REQ-MP-1103
- Phase status correctly reflects generation outcome

---

### ER-008: INTEGRATE Phase Element Provenance

**Priority:** P1 | **Phase(s):** INTEGRATE

The integration engine should track which elements were merged and their merge outcome.

**Problem:** `IntegrationEngine` operates at file level. When a file merge succeeds, we don't know which elements within the file survived the merge, were modified during repair, or were lost. When pre-merge repair modifies code, the element-level change is invisible.

**Mechanism:**

After `IntegrationEngine.merge_file()`:
1. Parse the merged file's AST to identify surviving elements
2. For each element in the registry associated with that file:
   - If present in merged AST with matching checksum: `("integrate", "merged")`
   - If present but modified (different checksum): `("integrate", "repaired")`, update registry code
   - If absent from merged AST: `("integrate", "lost")` — log warning
3. For pre-merge repair modifications, update the registry entry's code to reflect the repaired version

**Acceptance criteria:**
- After INTEGRATE, each element has a phase status reflecting its merge outcome
- Elements modified by repair have updated code in the registry
- Lost elements (present in generation but absent after merge) are flagged

---

### ER-009: TEST Phase Element-Level Validation

**Priority:** P1 | **Phase(s):** TEST

TEST should validate and score at element granularity, not just file level.

**Problem:** TEST runs validators per file or per task. A file with 5 elements where 4 are correct and 1 has a bad import gets a blanket failure. There's no signal for "which elements are good."

**Mechanism:**

During TEST validation:
1. For each generated file, map validator results back to specific elements where possible:
   - Syntax errors: map to element via line number → AST node
   - Import errors: map to element that declares the bad import
   - Lint errors: map to element via line range
2. Update registry: `("test", "passed")` or `("test", "failed", {"validator": "...", "error": "..."})`
3. Elements that pass all validators: eligible for registry caching in future runs

**Integration with Gap 27 (TEST blind to design):** Element-level design constraints from ER-006 can drive deterministic compliance checks: "does element X have the signature the design specified?"

**Acceptance criteria:**
- Per-element test status recorded in registry
- File-level failures attributed to specific elements where determinable
- Elements passing all validators marked as cache-eligible

---

### ER-010: REVIEW Phase Element-Level Scoring

**Priority:** P2 | **Phase(s):** REVIEW

REVIEW should attribute quality scores to individual elements.

**Problem:** REVIEW produces per-task scores and issue lists. A task with score 72 may have 4 excellent elements and 1 poor element. The poor element drags down the score, but there's no signal for which elements are review-worthy.

**Mechanism:**

After LLM review:
1. Parse review findings for element-specific mentions (function names, class names)
2. Attribute issues to specific elements in the registry
3. Update registry: `("review", "passed", {"score": 85})` or `("review", "issues_found", {"issues": [...]})`
4. Elements that pass review with score >= threshold: mark as `review_validated` — highest cache confidence

**Acceptance criteria:**
- Elements with review-attributed issues have those issues in registry metadata
- Elements with clean reviews are marked `review_validated`
- Registry summary includes per-element review score distribution

---

### ER-011: FINALIZE Phase Element Manifest

**Priority:** P1 | **Phase(s):** FINALIZE

FINALIZE should produce an element-level manifest alongside the existing file-level manifest.

**Problem:** `generation-manifest.json` reports per-task and per-file outcomes. There is no element-level manifest. Downstream tooling (Kaizen analysis, warm-up reconciliation, capability index) cannot reason about individual elements.

**Mechanism:**

During FINALIZE:
1. Query `registry.summary()` for aggregate statistics
2. Include element manifest section in `generation-manifest.json`:

```json
{
  "element_manifest": {
    "schema_version": "1.0.0",
    "total_elements": 42,
    "by_phase_status": {
      "review_validated": 35,
      "test_passed": 38,
      "implement_generated": 40,
      "implement_failed": 2
    },
    "by_tier": {"TRIVIAL": 12, "SIMPLE": 18, "MODERATE": 10, "COMPLEX": 2},
    "by_generator": {"ollama:startd8-coder": 18, "anthropic:claude-sonnet-...": 24},
    "cross_task_reuses": 7,
    "cost_saved_usd": 1.23,
    "elements": [
      {
        "element_id": "flcm-fn-...-getJSONLogger",
        "file_path": "src/emailservice/logger.py",
        "phase_history": [
          {"phase": "plan_ingestion", "status": "specified"},
          {"phase": "implement", "status": "generated", "generator": "ollama:startd8-coder"},
          {"phase": "test", "status": "passed"},
          {"phase": "review", "status": "passed", "score": 88}
        ]
      }
    ]
  }
}
```

**Integration with Gap 30 (per-validator results lost):** Element-level manifest preserves granular diagnostic data that the current task-level manifest discards.

**Acceptance criteria:**
- `generation-manifest.json` includes `element_manifest` section
- Every registered element appears with its full phase history
- Summary statistics match registry state

---

### ER-012: Prime Contractor Element Loop

**Priority:** P0 | **Phase(s):** Prime Contractor

The prime contractor's feature loop should leverage the element registry for cross-feature element reuse.

This is the pipeline-wide framing of REQ-MP-1105 (Cross-Task Element Lookup).

**Problem:** `PrimeContractorWorkflow.develop_feature()` iterates features sequentially. Each feature's code generation is independent. If feature F2 needs element E that feature F1 already generated, F2 regenerates E.

**Mechanism:**

In `PrimeContractorWorkflow.develop_feature()`:
1. Before calling `code_generator.generate()`, query registry for all elements in the feature's `ForwardElementSpec` list
2. Decision tree (from REQ-MP-1105):
   - ALL elements cached + valid → assemble from cache, cost = $0.00
   - SOME elements cached → pre-fill + generate remaining
   - NO elements cached → normal generation path
3. After successful generation + integration, register all elements
4. Log: `"Feature PI-002: 3/5 elements from registry, 2 generated ($0.094)"`

**Prime-specific considerations:**
- Prime processes features in dependency order. Feature F1 completing first means its elements are available to F2
- Wave-based execution: features in the same wave run in parallel — registry must handle concurrent puts
- Pipeline mode vs standalone mode: registry is available in both but populated differently

**Acceptance criteria:**
- Feature with all elements in registry: assembled at $0.00
- Feature with partial cache: cost reflects only generated elements
- Metadata includes `elements_from_cache` / `elements_generated` counts
- Concurrent feature processing does not corrupt registry

---

### ER-013: Handoff Element State

**Priority:** P1 | **Phase(s):** Handoff (Design ↔ Implementation split)

The design-to-implementation handoff should carry element-level state.

**Problem:** `design-handoff.json` carries task-level design results. When the implementation half starts, it has no element-level context about what DESIGN decided, what SCAFFOLD pre-filled, or what elements exist in the registry.

**Mechanism:**

In `write_design_handoff()`:
1. Include element registry snapshot: `registry.summary()` + per-element phase status
2. Include element-design mapping: which elements have design constraints from ER-006

In `load_design_handoff()`:
1. Restore element registry state if the registry on disk is absent or stale
2. Validate element checksums between handoff snapshot and current registry

**Handoff schema addition:**

```json
{
  "element_state": {
    "registry_checksum": "sha256-of-index",
    "element_count": 42,
    "elements_with_design_constraints": 35,
    "elements_pre_filled_in_scaffold": 8
  }
}
```

**Acceptance criteria:**
- Handoff file includes element state section
- Implementation half can verify registry consistency at startup
- Split execution (design-only + implement-only) preserves element state

---

### ER-014: Cross-Run Kaizen Metrics

**Priority:** P2 | **Phase(s):** Post-Run Analysis

The element registry should support Kaizen cross-run analysis.

**Problem:** Today, per-run metrics are file/task-level. Element-level patterns (which elements fail most, which templates produce reusable code, which complexity tiers have the best reuse rates) are invisible.

**Mechanism:**

After each run's FINALIZE:
1. Write `_metrics/run-{timestamp}.json` with:
   - Elements generated vs reused
   - Elements that passed review vs failed
   - Elements repaired (pre-merge or post-merge) vs clean generation
   - Cost saved via reuse
   - Tier distribution of generated elements
   - Generator distribution (Ollama vs cloud per tier)
2. Kaizen analysis tool can diff across runs:
   - Reuse rate trend (should increase over time)
   - Failure rate by element kind (functions vs classes)
   - Repair rate by error category
   - Template coverage (what % of trivial elements matched templates)

**Integration with Kaizen PDCA cycle:**
- **Plan**: Identify element patterns with low reuse or high failure
- **Do**: Adjust templates, prompts, or classifier thresholds
- **Check**: Compare next run's element metrics
- **Act**: Codify improvements that held

**Acceptance criteria:**
- Per-run metrics file written to `_metrics/`
- Metrics include all listed dimensions
- Cross-run diff produces actionable insights

---

### ER-015: Warm Up Registry Reconciliation

**Priority:** P2 | **Phase(s):** Toolchain Transition

The element registry supports Warm Up reconciliation during toolchain transitions.

**Problem:** When the primary LLM tool goes down and a backup tool generates code, the backup may regenerate elements that already exist in the registry. When the primary returns, it needs to reconcile what the backup produced against the registry.

**Mechanism:**

Warm Up Phase 3 (Reconcile):
1. Query registry for all elements with `phase_status != "review_validated"`
2. For elements the backup generated: compare registry code vs backup's generated code
3. Decision tree:
   - Registry code + backup code identical → no action
   - Registry code absent, backup code present → register backup's code with `generator="backup:{tool_name}"`
   - Registry code present, backup code different → flag for human review
4. Produce reconciliation report: elements added, elements conflicting, elements unchanged

**Acceptance criteria:**
- Warm Up reconciliation queries registry for non-validated elements
- Backup-generated elements registered with appropriate provenance
- Conflicting elements flagged (not auto-overwritten)

---

### ER-016: Element Quality Gates

**Priority:** P1 | **Phase(s):** Gate boundaries

Define element-level quality gates at phase boundaries.

**Problem:** Quality gates (Gate 2c, Gate 3, Gate 4, Gate 5) operate at task or file level. Element-level defects are aggregated into task-level verdicts, losing granularity.

**Specification:**

| Gate | Element-Level Check | Action on Failure |
|------|-------------------|-------------------|
| Post-SCAFFOLD | Element stubs match manifest specs | Advisory warning |
| Post-IMPLEMENT | Generated elements match design signatures | Blocking (per-element) |
| Post-INTEGRATE | Elements survived merge (ER-008) | Blocking if element lost |
| Post-TEST | Per-element validator results (ER-009) | Advisory (failing elements logged) |
| Post-REVIEW | Element-level score attribution (ER-010) | Advisory (low-scoring elements flagged) |

**Gate emission:**

```python
GateEmitter.emit_element_gate(
    gate_id="gate-4-element",
    element_id="flcm-fn-...-getJSONLogger",
    phase="implement",
    outcome="PASS",
    evidence=[{"type": "ast_valid", "value": True}, {"type": "signature_match", "value": True}]
)
```

**Acceptance criteria:**
- Element-level gate results emitted via `GateEmitter`
- Gate results include element ID and phase-specific evidence
- Element-level blocking gates prevent progression of individual elements (not entire tasks)

---

### ER-017: Pipeline Contract Propagation

**Priority:** P1 | **Phase(s):** Contract YAML

Add element registry fields to the artisan pipeline contract.

**Specification:**

Add to `artisan-pipeline.contract.yaml`:

```yaml
propagation_chains:
  element_registry:
    description: "Element-level identity, state, and quality tracking"
    fields:
      - name: element_registry
        type: ElementRegistry
        severity: advisory
        description: "Shared element registry instance"
        produced_by: [plan]
        consumed_by: [scaffold, design, implement, integrate, test, review, finalize]
      - name: element_manifest
        type: dict
        severity: advisory
        description: "Element-level manifest for FINALIZE output"
        produced_by: [finalize]
```

**Acceptance criteria:**
- Contract YAML declares element registry propagation chain
- Contract validation tests verify element registry availability at each phase

---

### ER-018: Element Lineage and Provenance

**Priority:** P2 | **Phase(s):** All

Each element's registry entry should maintain a complete lineage record.

**Data model extension:**

```python
@dataclass
class PhaseRecord:
    phase: str              # "plan_ingestion", "scaffold", "implement", etc.
    status: str             # "specified", "pre_filled", "generated", "merged", "passed", etc.
    timestamp: str          # ISO-8601
    run_id: str             # Pipeline run identifier
    metadata: dict          # Phase-specific data (generator, score, error, etc.)

@dataclass
class ElementEntry:
    # ... (from REQ-MP-1100)
    phase_history: list[PhaseRecord] = field(default_factory=list)
    lineage: ElementLineage | None = None

@dataclass
class ElementLineage:
    origin_task: str        # Task that first specified this element
    origin_run: str         # Run that first created the element
    generation_task: str    # Task that generated the code
    generation_run: str     # Run that generated the code
    reuse_count: int        # How many times this element was reused from cache
    reuse_tasks: list[str]  # Which tasks reused it
```

**Acceptance criteria:**
- Every element has a chronological `phase_history`
- Elements reused across tasks have `lineage.reuse_count > 0` and `reuse_tasks` populated
- Lineage survives across runs

---

## 4. Data Flow — Pipeline-Wide

```
Plan Ingestion
  └── ForwardManifest created
        │
        ├── ER-003: Populate ElementRegistry with all ForwardElementSpecs
        │            status = "specified" for each element
        │
        ├── ER-001: All element IDs created via make_element_id()
        │
        ▼
PLAN
  └── Plan deconstruction
        │
        ├── ER-004: Query registry for element availability per task
        │            Log: "Task PI-001: 3/5 elements available"
        │
        ▼
SCAFFOLD
  └── DeterministicFileAssembler
        │
        ├── ER-005: Pre-fill stubs with review-validated registry entries
        │            Log: "Pre-filled 8/42 elements from registry"
        │
        ├── REQ-MP-1104: Derive element specs from skeleton AST if none exist
        │
        ▼
DESIGN
  └── Design document generation
        │
        ├── ER-006: Extract element-level design constraints
        │            Register: ("design", "designed") with signature/spec metadata
        │
        ▼
─── Design Handoff ─── (ER-013: element state in handoff)
        │
        ▼
IMPLEMENT
  └── Per element:
        │
        ├── ER-007 / REQ-MP-1102: Registry check → generate → register
        │     Cache hierarchy: in-memory → registry → Ollama/cloud
        │
        ▼
INTEGRATE
  └── Per file merge:
        │
        ├── ER-008: Track per-element merge outcome
        │            ("merged" / "repaired" / "lost")
        │
        ▼
TEST
  └── Per-element validation:
        │
        ├── ER-009: Map validator results to specific elements
        │            ("passed" / "failed" with validator details)
        │
        ▼
REVIEW
  └── LLM quality review:
        │
        ├── ER-010: Attribute review scores to elements
        │            Review-validated elements → highest cache confidence
        │
        ▼
FINALIZE
  └── Element manifest:
        │
        ├── ER-011: Element-level manifest in generation-manifest.json
        │
        ├── ER-014: Write per-run Kaizen metrics
        │
        ▼
Post-Run / Cross-Run
  └── ER-014: Kaizen analysis across runs
  └── ER-015: Warm Up reconciliation on toolchain transition
```

---

## 5. Relationship to Existing Requirements

| Document | Relationship |
|----------|-------------|
| [REQ-MP-11xx (Micro-Prime)](../micro-prime/REQ-MP-11xx_ELEMENT_REGISTRY.md) | Core data model and engine integration — ER requirements extend scope to pipeline-wide |
| [Mottainai Design Principle](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Element registry closes Mottainai Rules 1, 2, 4, 5 at element granularity |
| [Kaizen Design Principle](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md) | ER-014 enables per-element PDCA improvement cycles |
| [Warm Up Design Principle](../../design-princples/WARM_UP_DESIGN_PRINCIPLE.md) | ER-015 enables element-level reconciliation during toolchain transitions |
| [Pipeline Contract](../../../src/startd8/contractors/contracts/artisan-pipeline.contract.yaml) | ER-017 adds element registry to propagation chains |
| [Forward Manifest Gap Review](../../reviews/forward-manifest-element-registry-gap-2026-03-07.md) | Investigation that motivated these requirements |
| Mottainai Gap 14 (no generation caching) | ER-007/ER-012 close this gap at element granularity |
| Mottainai Gap 17-20 (serialize-and-forget) | ER-006 structures DESIGN output at element level |
| Mottainai Gap 27 (TEST blind to design) | ER-009 + ER-006 enable design-driven element validation |
| Mottainai Gap 30 (per-validator results lost) | ER-011 preserves element-level diagnostics in manifest |

---

## 6. Implementation Phasing

### Phase 1: Foundation (P0 requirements)

| Req | Deliverable | Estimated Lines |
|-----|-------------|-----------------|
| ER-001 | `make_element_id()` utility, update 13 generation sites | ~120 |
| ER-002 | `src/startd8/element_registry.py` (top-level module) | ~350 |
| ER-003 | Plan ingestion → registry population | ~60 |
| ER-007 | IMPLEMENT phase integration (delegates to REQ-MP-1102/1103) | ~80 |
| ER-012 | Prime contractor element loop (delegates to REQ-MP-1105) | ~100 |
| **Phase 1 Total** | | **~710** |

### Phase 2: Pipeline Integration (P1 requirements)

| Req | Deliverable | Estimated Lines |
|-----|-------------|-----------------|
| ER-004 | PLAN element inventory | ~50 |
| ER-005 | SCAFFOLD pre-fill | ~80 |
| ER-006 | DESIGN element-level contracts | ~120 |
| ER-008 | INTEGRATE element provenance | ~100 |
| ER-009 | TEST element-level validation | ~100 |
| ER-011 | FINALIZE element manifest | ~80 |
| ER-013 | Handoff element state | ~60 |
| ER-016 | Element quality gates | ~80 |
| ER-017 | Pipeline contract propagation | ~30 |
| **Phase 2 Total** | | **~700** |

### Phase 3: Intelligence (P2 requirements)

| Req | Deliverable | Estimated Lines |
|-----|-------------|-----------------|
| ER-010 | REVIEW element-level scoring | ~80 |
| ER-014 | Kaizen cross-run metrics | ~120 |
| ER-015 | Warm Up reconciliation | ~100 |
| ER-018 | Element lineage and provenance | ~80 |
| **Phase 3 Total** | | **~380** |

**Grand Total: ~1,790 lines** (including ~960 from REQ-MP-11xx, net new ~830)

---

## 7. Open Questions

1. **Registry scope vs run isolation.** The registry is per-project (`.startd8/state/elements/`), meaning it spans across runs. Should there be a mechanism to "snapshot" the registry state at run start so that a failed run can be rolled back to the pre-run state without losing elements from prior successful runs?

2. **Element identity across languages.** The current ID scheme assumes Python-style elements (functions, classes). For polyglot projects (Go services in Online Boutique), how should elements be identified? Recommendation: language-agnostic `kind` values (`fn`, `cls`, `type`, `const`, `method`) with language-specific suffixes when needed.

3. **Registry sharing across projects.** Could elements from one project's registry be reused in another project that uses similar patterns? Example: a `getJSONLogger` function generated for one microservice might be identical to what another microservice needs. This is out of scope for v1 but worth noting for future consideration.

4. **Element granularity for non-code artifacts.** Should the registry track elements within Dockerfiles, YAML configs, or Grafana dashboards? These have element-level structure (Dockerfile stages, YAML keys, dashboard panels) but don't map to AST constructs. Recommendation: v1 focuses on code elements (functions, classes, constants). Non-code artifacts can be tracked at file level via existing mechanisms.

5. **Registry as micro-prime dependency.** ER-002 moves `ElementRegistry` to top-level `src/startd8/element_registry.py`. This means micro-prime imports from a module outside its package. Is this acceptable, or should the registry live in a shared `utils/` or `core/` package? Recommendation: top-level is correct — the registry is a pipeline service, not a utility.

6. **Element-level checkpoint/resume.** Currently, resuming a failed IMPLEMENT task re-generates all elements, not just the failed ones. Should ER-007 include element-level resume (restart from the 3rd element if elements 1-2 succeeded)? This is partially addressed by the registry cache (elements 1-2 would be cache hits on retry), but explicit per-element checkpoint state (`.startd8/state/task-{id}/element-{fqn}/`) could provide stronger guarantees. Recommendation: registry cache-through (ER-007) handles the common case; explicit element checkpointing is a Phase 3 enhancement if cache-through proves insufficient.

7. **Element-level complexity routing at PLAN time.** ER-004 queries the registry for element availability but doesn't classify element complexity during PLAN. Should complexity signals be computed early (during plan ingestion or PLAN phase) so that task decomposition can factor in element difficulty? This would enable: splitting a task with 3 SIMPLE + 2 COMPLEX elements into two tasks. Recommendation: defer to Phase 2; plan-time complexity requires manifest data that may not be available until SCAFFOLD.

---

## 8. Critical Implementation Files

Files that require modification for element registry integration, organized by implementation phase:

### Phase 1 (Foundation)

| File | Change | Requirement |
|------|--------|-------------|
| `src/startd8/element_registry.py` | **NEW** — Core `ElementRegistry` class, `ElementEntry`, `PhaseRecord` | ER-002 |
| `src/startd8/forward_manifest_extractor.py` | Update 13 ID generation sites to use `make_element_id()` | ER-001 |
| `src/startd8/forward_manifest.py` | Add `get_element_by_id()`, `_element_id_index` (lazy) | REQ-MP-1101 |
| `src/startd8/micro_prime/engine.py` | Wire `ElementRegistry` for cache-through | ER-007 / REQ-MP-1102 |
| `src/startd8/micro_prime/prime_adapter.py` | Pass registry to engine, register on success | ER-007 / REQ-MP-1103 |
| `src/startd8/contractors/prime_contractor.py` | Cross-feature element lookup in feature loop | ER-012 / REQ-MP-1105 |
| `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | Populate registry after manifest extraction | ER-003 |

### Phase 2 (Pipeline Integration)

| File | Change | Requirement |
|------|--------|-------------|
| `src/startd8/contractors/artisan_phases/plan_deconstruction.py` | Query registry for element availability per task | ER-004 |
| `src/startd8/utils/file_assembler.py` | Pre-fill stubs from registry | ER-005 |
| `src/startd8/contractors/context_seed/design_support.py` | Extract element-level design constraints | ER-006 |
| `src/startd8/contractors/context_seed/core.py` | Thread element state through phase handlers | ER-006..ER-010 |
| `src/startd8/contractors/integration_engine.py` | Per-element merge outcome tracking | ER-008 |
| `src/startd8/contractors/artisan_phases/test_construction.py` | Map validator results to elements | ER-009 |
| `src/startd8/contractors/artisan_phases/final_assembly.py` | Element manifest in generation-manifest.json | ER-011 |
| `src/startd8/contractors/handoff.py` | Element state section in handoff | ER-013 |
| `src/startd8/contractors/gate_contracts.py` | `emit_element_gate()` method | ER-016 |
| `src/startd8/contractors/contracts/artisan-pipeline.contract.yaml` | Element registry propagation chain | ER-017 |
| `src/startd8/contractors/context_schema.py` | Add `per_element` keys to PhaseOutput models | ER-008..ER-010 |

### Phase 3 (Intelligence)

| File | Change | Requirement |
|------|--------|-------------|
| `src/startd8/contractors/context_seed/core.py` | Review score attribution to elements | ER-010 |
| `src/startd8/element_registry.py` | Kaizen metrics export, `_metrics/` directory | ER-014 |
| `src/startd8/element_registry.py` | Reconciliation report for Warm Up | ER-015 |
| `src/startd8/element_registry.py` | `ElementLineage` dataclass, `phase_history` | ER-018 |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-07 | Initial version: 18 pipeline-wide requirements (ER-001 through ER-018) extending REQ-MP-11xx scope to all artisan phases, prime contractor, Kaizen, and Warm Up |
