# Element Registry — Implementation Plan

Concrete, step-by-step implementation plan for [ELEMENT_REGISTRY_REQUIREMENTS.md](./ELEMENT_REGISTRY_REQUIREMENTS.md). Each step specifies exact files, insertion points, data models, and test expectations.

> **Date:** 2026-03-07
> **Prerequisites:** None (greenfield — no existing element registry code)
> **Test strategy:** Each step includes unit tests; integration test at end of each phase
> **Branch strategy:** `feat/element-registry-phase-{N}` per phase

---

## Overview

**Purpose:** Introduce a persistent, cross-task Element Registry that caches generated code elements (functions, classes, constants) across pipeline phases and runs. The registry replaces 15 ad-hoc element-ID generation sites with a single deterministic scheme, enables cross-task dependency resolution (e.g., a service importing a logger defined in a prior task), and feeds Kaizen with lineage data for continuous improvement.

**Objectives:**
- Eliminate duplicate element generation and inconsistent ID formats across the forward manifest pipeline
- Enable the IMPLEMENT phase, Prime Contractor, and Micro Prime to resolve cross-task element references at generation time
- Provide element lineage tracking from plan ingestion through code generation for post-mortem analysis

**Goals:**
- Phase 1 (P0): Core registry + IMPLEMENT + Prime integration — minimum viable cross-task reuse
- Phase 2 (P1): Full pipeline integration across all 8 phases, handoff module, and quality gates
- Phase 3 (P2): Intelligence layer — Kaizen feedback, warm-up cache seeding, and element lineage

## Functional Requirements

See [ELEMENT_REGISTRY_REQUIREMENTS.md](./ELEMENT_REGISTRY_REQUIREMENTS.md) for the full requirements specification (ER-001 through ER-020). Key functional requirements:

- **ER-001:** Deterministic element ID generation via `make_element_id()`
- **ER-002:** `ElementRegistry` in-memory store with `register()`, `lookup()`, `resolve_ref()`, `snapshot()`
- **ER-003:** IMPLEMENT phase integration — registry-aware `build_supplementary_sections()`
- **ER-004:** Prime Contractor integration — pre-populate registry from forward manifest before task dispatch
- **ER-005:** Micro Prime integration — chunk-level element resolution via registry
- **ER-006 to ER-010:** Pipeline phase integration (extractor, design, review, handoff, quality gates)
- **ER-011 to ER-015:** Persistence, versioning, garbage collection, conflict resolution
- **ER-016 to ER-020:** Kaizen feedback, warm-up seeding, lineage tracking, observability

---

## Phase 1: Foundation (P0 — Core Registry + IMPLEMENT + Prime)

Phase 1 delivers a working element registry that caches generated elements and enables cross-task reuse in both the micro-prime engine and prime contractor. This is the minimum viable product.

### Step 1.1: `make_element_id()` Utility (ER-001)

**Goal:** Single function for deterministic element ID generation, replacing 15 ad-hoc sites.

**New file:** `src/startd8/element_id.py`

```python
"""Deterministic element ID generation for the Forward Manifest pipeline."""

def make_element_id(
    kind: str,
    name: str,
    file_path: str | None = None,
    parent_class: str | None = None,
    line: int | None = None,
) -> str:
    """Generate a stable, unique element ID.

    Format: flcm-{kind}-{name}
    With file scope: flcm-{kind}-{normalized_path}-{name}
    With parent class: flcm-{kind}-{normalized_path}-{parent_class}-{name}
    With line (AST): flcm-{kind}-{normalized_path}-{line}-{name}

    Args:
        kind: Element kind abbreviation (fn, cls, const, imp, inf, ast, skel, etc.)
        name: Element name (function/class/constant name)
        file_path: Optional relative file path for scoping
        parent_class: Optional parent class for method disambiguation
        line: Optional line number for AST-derived elements
    """
```

**Constraints:**
- Normalize `file_path`: strip leading `./`, replace `/` with `-`, replace `.` with `-`
- Deterministic: same inputs always produce same output
- No timestamp, no run ID, no random component

**Modifications to `src/startd8/forward_manifest_extractor.py`:**

Update all 15 ID generation sites (lines 458, 501, 572, 595, 624, 645, 761, 787, 804, 991, 1012, 1031, 1053, 1533, 1565) to call `make_element_id()` instead of inline f-strings.

Example — line 458 (class extraction):
```python
# Before:
contract_id = f"flcm-{abbrev}-{class_name}"

# After:
from startd8.element_id import make_element_id
contract_id = make_element_id(kind=abbrev, name=class_name)
```

Example — line 1533 (AST reconciliation):
```python
# Before:
f"flcm-ast-{relpath}:{element.span.start_line}:{element.fqn}"

# After:
make_element_id(kind="ast", name=element.fqn, file_path=relpath, line=element.span.start_line)
```

**Tests:** `tests/unit/test_element_id.py`
- Determinism: same inputs → same ID
- Uniqueness: different parent_class → different ID
- Path normalization: `./src/foo.py` and `src/foo.py` → same ID
- Round-trip: ID format parseable back to components

**Estimated lines:** ~60 (module) + ~80 (tests) + ~40 (extractor updates)

---

### Step 1.2: `ElementRegistry` Core (ER-002 + REQ-MP-1100)

**Goal:** Persistent, index-addressable element store at the top-level package.

**New file:** `src/startd8/element_registry.py`

```python
"""Element Registry — persistent element store for the capability delivery pipeline."""

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

SCHEMA_VERSION = "1.0.0"


@dataclass
class PhaseRecord:
    """Record of an element's status at a specific pipeline phase."""
    phase: str
    status: str
    timestamp: str = ""
    run_id: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class ElementEntry:
    """A single element tracked by the registry."""
    element_id: str
    code: Optional[str] = None
    source_task: str = ""
    checksum: str = ""
    generated_at: str = ""
    generator: str = ""
    file_path: str = ""
    tier: str = ""
    kind: str = ""
    name: str = ""
    schema_version: str = SCHEMA_VERSION
    phase_history: list[PhaseRecord] = field(default_factory=list)
    context_checksum: str = ""


@dataclass
class RegistrySummary:
    """Aggregate statistics for reporting."""
    total_elements: int = 0
    by_tier: dict[str, int] = field(default_factory=dict)
    by_generator: dict[str, int] = field(default_factory=dict)
    by_phase_status: dict[str, int] = field(default_factory=dict)
    cross_task_reuses: int = 0
    cost_saved_usd: float = 0.0


class ElementRegistry:
    """Persistent element store for the capability delivery pipeline.

    Thread-safe via a lock on index mutations. File I/O failures
    degrade gracefully (log warning, fall through).

    Args:
        state_dir: Root directory for element storage.
                   Defaults to `.startd8/state`.
    """

    def __init__(self, state_dir: Path | str | None = None) -> None: ...
    def get(self, element_id: str) -> Optional[ElementEntry]: ...
    def put(self, entry: ElementEntry) -> None: ...
    def has(self, element_id: str) -> bool: ...
    def elements_for_file(self, file_path: str) -> list[ElementEntry]: ...
    def remove(self, element_id: str) -> bool: ...
    def clear(self) -> None: ...
    def set_phase_status(self, element_id: str, phase: str, status: str,
                         metadata: dict | None = None) -> None: ...
    def get_phase_status(self, element_id: str, phase: str) -> Optional[str]: ...
    def elements_by_status(self, phase: str, status: str) -> list[ElementEntry]: ...
    def element_history(self, element_id: str) -> list[PhaseRecord]: ...
    def summary(self) -> RegistrySummary: ...
```

**Storage layout:**
```
{state_dir}/elements/
├── index.json              # {element_id: safe_filename}
├── {safe_filename}.json    # ElementEntry serialized
└── ...
```

**Key implementation details:**
- `_lock = threading.Lock()` for index mutation safety (concurrent wave execution)
- `_safe_filename(element_id)`: hash IDs containing `/` or `:` for filesystem safety
- `_load_index()` / `_save_index()`: lazy load on first access, write-through on mutation
- `_load_entry(element_id)` / `_save_entry(entry)`: individual JSON files
- All I/O wrapped in try/except with logger.warning on failure (Mottainai Rule 3)

**Tests:** `tests/unit/test_element_registry.py`
- `put()` → `get()` round-trip
- `get()` on missing ID → `None`
- Restart persistence: create registry, put, create new instance with same dir, get
- Concurrent writes to different IDs (threading test)
- `set_phase_status` / `get_phase_status` round-trip
- `elements_for_file()` returns correct subset
- `summary()` counts match actual entries
- I/O failure graceful degradation (mock Path.write_text to raise)

**Estimated lines:** ~300 (module) + ~200 (tests)

---

### Step 1.3: ForwardManifest Element Index (REQ-MP-1101)

**Goal:** O(1) element lookup by ID on ForwardManifest.

**Modified file:** `src/startd8/forward_manifest.py`

**Changes to `ForwardManifest` class (after line ~314):**

```python
class ForwardManifest(BaseModel):
    # ... existing fields ...

    # Lazy element index — not serialized
    _element_id_index: dict[str, ForwardElementSpec] | None = None

    def get_element_by_id(self, element_id: str) -> Optional[ForwardElementSpec]:
        """O(1) lookup by flcm-* ID. Builds lazy index on first call."""
        if self._element_id_index is None:
            self._build_element_index()
        return self._element_id_index.get(element_id)

    def get_elements_by_name(self, name: str) -> list[ForwardElementSpec]:
        """Return all elements matching name (across files)."""
        results = []
        for fs in self.file_specs.values():
            for e in fs.elements:
                if e.name == name:
                    results.append(e)
        return results

    def all_elements(self) -> list[tuple[str, ForwardElementSpec]]:
        """Return (file_path, element) pairs for all elements."""
        results = []
        for path, fs in self.file_specs.items():
            for e in fs.elements:
                results.append((path, e))
        return results

    def _build_element_index(self) -> None:
        """Build lazy index from all file_specs.elements."""
        self._element_id_index = {}
        for fs in self.file_specs.values():
            for e in fs.elements:
                if e.source_contract_id:
                    self._element_id_index[e.source_contract_id] = e
```

**Note:** Pydantic v2 with `model_config = ConfigDict(...)` on the parent — need to handle `_element_id_index` as a private attribute using `PrivateAttr` or `__init__` override.

**Tests:** Extend `tests/unit/test_forward_manifest.py`
- `get_element_by_id()` returns correct spec
- Second call doesn't rebuild index (verify via mock/spy)
- Unknown ID → `None`
- `all_elements()` returns complete list

**Estimated lines:** ~40 (manifest changes) + ~40 (tests)

---

### Step 1.4: Plan Ingestion Registry Population (ER-003)

**Goal:** Populate registry with all manifest elements after extraction.

**Modified file:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

**Insertion point:** After `ForwardManifestExtractor.extract()` returns the manifest (in the EMIT or TRANSFORM phase), iterate elements and register:

```python
def _populate_element_registry(
    registry: ElementRegistry,
    manifest: ForwardManifest,
    run_id: str,
) -> int:
    """Register all manifest elements in the element registry.

    Returns the number of elements registered.
    """
    count = 0
    for file_path, element in manifest.all_elements():
        element_id = element.source_contract_id
        if not element_id:
            continue
        entry = ElementEntry(
            element_id=element_id,
            file_path=file_path,
            kind=element.kind.value,
            name=element.name,
        )
        registry.put(entry)
        registry.set_phase_status(
            element_id, "plan_ingestion", "specified",
            metadata={"run_id": run_id},
        )
        count += 1
    logger.info(
        "Element registry: populated %d elements from manifest",
        count,
    )
    return count
```

**Also modified:** Pipeline runner scripts that create the workflow — they need to create `ElementRegistry` and pass it through.

**Tests:** `tests/unit/test_element_registry_population.py`
- Mock manifest with 5 elements across 2 files → registry has 5 entries
- All entries have phase status `("plan_ingestion", "specified")`
- Elements without `source_contract_id` are skipped

**Estimated lines:** ~50 (workflow changes) + ~40 (tests)

---

### Step 1.5: MicroPrimeEngine Registry Integration (ER-007 / REQ-MP-1102)

**Goal:** Cache-through on element generation — check registry before generating, persist on success.

**Modified file:** `src/startd8/micro_prime/engine.py`

**Changes to `MicroPrimeEngine.__init__()` (line ~235):**

```python
def __init__(
    self,
    config: Optional[MicroPrimeConfig] = None,
    template_registry: Optional[TemplateRegistry] = None,
    metrics_collector: Optional[MetricsCollector] = None,
    element_registry: Optional["ElementRegistry"] = None,  # NEW
) -> None:
    # ... existing init ...
    self._element_registry = element_registry
```

**Changes to `process_element()` (line ~290):**

Before classification/generation, add registry lookup:

```python
def process_element(self, element, file_spec, skeleton, contracts=None, ...):
    element_id = getattr(element, 'source_contract_id', None)

    # Registry cache check (ER-007)
    if self._element_registry and element_id:
        cached = self._element_registry.get(element_id)
        if cached and cached.code:
            # Validate staleness via context checksum
            current_checksum = self._element_context_checksum(element, contracts)
            if cached.context_checksum == current_checksum:
                logger.info("Element registry HIT: %s", element_id)
                # Return success result with cached code
                return self._build_cache_hit_result(element, cached)
            else:
                logger.debug("Element registry STALE: %s", element_id)

    # ... existing classification + generation logic ...

    # After successful generation (before return):
    if self._element_registry and element_id and result.success and result.code:
        self._register_element(element_id, element, result, contracts)

    return result
```

**New helper methods:**

```python
def _element_context_checksum(
    self, element: ForwardElementSpec,
    contracts: list[InterfaceContract] | None,
) -> str:
    """Hash element's structural context for staleness detection."""
    parts = [element.name, element.kind.value, ...]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()

def _register_element(
    self, element_id: str, element: ForwardElementSpec,
    result: ElementResult, contracts: list | None,
) -> None:
    """Register a successfully generated element."""
    entry = ElementEntry(
        element_id=element_id,
        code=result.code,
        source_task="",  # set by caller
        checksum=hashlib.sha256(result.code.encode()).hexdigest(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        generator=self._config.model_name or "ollama:unknown",
        file_path=...,
        tier=result.tier.value if result.tier else "",
        context_checksum=self._element_context_checksum(element, contracts),
    )
    self._element_registry.put(entry)
    self._element_registry.set_phase_status(
        element_id, "implement", "generated",
    )

def _build_cache_hit_result(
    self, element: ForwardElementSpec, cached: ElementEntry,
) -> ElementResult:
    """Build an ElementResult from a registry cache hit."""
    return ElementResult(
        element_name=element.name,
        file_path=cached.file_path,
        tier=TierClassification(cached.tier) if cached.tier else TierClassification.SIMPLE,
        success=True,
        code=cached.code,
        repair_steps_applied=[],
        repair_attribution=None,
        repair_recovered=False,
        escalation=None,
        decomposition_metadata={"source": "element_registry"},
    )
```

**Tests:** Extend `tests/unit/micro_prime/test_engine.py`
- Registry hit → skip generation, return cached code
- Registry miss → generate, then entry exists in registry
- Stale entry (changed checksum) → regenerate
- No registry (None) → existing behavior unchanged
- Registry I/O failure → graceful fallthrough to generation

**Estimated lines:** ~100 (engine changes) + ~80 (tests)

---

### Step 1.6: MicroPrimeCodeGenerator Registry Integration (ER-007 / REQ-MP-1103)

**Goal:** Pass registry to engine, log hit/miss counts.

**Modified file:** `src/startd8/micro_prime/prime_adapter.py`

**Changes to `MicroPrimeCodeGenerator.__init__()` (line ~217):**

```python
def __init__(
    self,
    config: Optional[MicroPrimeConfig] = None,
    fallback: Optional[CodeGenerator] = None,
    manifest: Optional[ForwardManifest] = None,
    skeletons: Optional[dict[str, str]] = None,
    output_dir: Optional[Path] = None,
    cloud_agent_spec: Optional[str] = None,
    element_registry: Optional["ElementRegistry"] = None,  # NEW
) -> None:
    # ... existing init ...
    self._element_registry = element_registry
    # Pass to engine
    self._engine = MicroPrimeEngine(
        config=self._config,
        element_registry=element_registry,  # NEW
    )
```

**Changes to `generate()` (line ~236):**

After generation completes, log registry statistics:

```python
# At end of generate(), before return:
if self._element_registry:
    summary = self._element_registry.summary()
    gen_result = gen_result._replace(
        metadata={
            **(gen_result.metadata or {}),
            "element_registry_hits": ...,
            "element_registry_misses": ...,
        },
    )
```

**Tests:** Extend `tests/unit/micro_prime/test_prime_adapter.py`
- Registry passed through to engine
- Generation metadata includes registry hit/miss counts

**Estimated lines:** ~40 (adapter changes) + ~40 (tests)

---

### Step 1.7: Prime Contractor Element Loop (ER-012)

**Goal:** Wire registry into PrimeContractorWorkflow for cross-feature reuse.

**Modified file:** `src/startd8/contractors/prime_contractor.py`

**Changes to `PrimeContractorWorkflow.__init__()` or factory:**

Accept optional `element_registry` parameter. Store as `self._element_registry`.

**Changes to `develop_feature()` (line ~2650):**

Before the `code_generator.generate()` call (around line ~2704), add element pre-check:

```python
# Element registry pre-check (ER-012)
elements_from_cache = 0
elements_total = 0
if self._element_registry and self._forward_manifest:
    for path in feature.target_files or []:
        file_spec = self._forward_manifest.file_specs.get(path)
        if file_spec:
            for elem in file_spec.elements:
                elements_total += 1
                eid = elem.source_contract_id
                if eid and self._element_registry.has(eid):
                    cached = self._element_registry.get(eid)
                    if cached and cached.code:
                        elements_from_cache += 1
    if elements_total > 0:
        logger.info(
            "Feature '%s': %d/%d elements available in registry",
            feature.name, elements_from_cache, elements_total,
        )
```

Pass the registry to `MicroPrimeCodeGenerator` when constructing code generators.

**Changes to runner scripts:**

`scripts/run_prime_workflow.py` and `.cap-dev-pipe/run-prime-contractor.sh`:
- Create `ElementRegistry(state_dir=output_dir / ".startd8" / "state")`
- Pass to `PrimeContractorWorkflow`

**Tests:** Extend `tests/unit/contractors/test_prime_contractor.py`
- Feature with all elements in registry → elements_from_cache == total
- Feature with no elements → normal flow
- Registry None → no crash

**Estimated lines:** ~80 (prime changes) + ~60 (tests)

---

### Step 1.8: Phase 1 Integration Test

**New file:** `tests/integration/test_element_registry_integration.py`

End-to-end test:
1. Create a `ForwardManifest` with 3 elements across 2 files
2. Create `ElementRegistry` with temp dir
3. Run `_populate_element_registry()` → 3 entries with status `specified`
4. Mock `MicroPrimeEngine` to generate code for 2 elements
5. Verify registry has 2 entries with code, 1 with `code=None`
6. Create a second "task" that needs element 1 → registry HIT, no generation
7. Verify summary shows `cross_task_reuses: 1`

**Estimated lines:** ~120

---

### Phase 1 Summary

| Step | Deliverable | New Files | Modified Files | Est. Lines |
|------|------------|-----------|----------------|------------|
| 1.1 | `make_element_id()` | `element_id.py`, test | `forward_manifest_extractor.py` | ~180 |
| 1.2 | `ElementRegistry` | `element_registry.py`, test | — | ~500 |
| 1.3 | Manifest index | — | `forward_manifest.py`, test | ~80 |
| 1.4 | Plan ingestion population | — | `plan_ingestion_workflow.py`, test | ~90 |
| 1.5 | Engine integration | — | `engine.py`, test | ~180 |
| 1.6 | Adapter integration | — | `prime_adapter.py`, test | ~80 |
| 1.7 | Prime contractor loop | — | `prime_contractor.py`, runner scripts, test | ~140 |
| 1.8 | Integration test | test | — | ~120 |
| **Total** | | **3 new** | **6 modified** | **~1,370** |

**Verification gate:** All existing tests pass + new tests pass + integration test demonstrates cross-task element reuse at $0.00 cost.

---

## Phase 2: Pipeline Integration (P1 — All 8 Phases + Handoff + Gates)

Phase 2 threads the element registry through every artisan phase. Each step is independently deployable.

### Step 2.1: PLAN Phase Element Inventory (ER-004)

**Modified file:** `src/startd8/contractors/artisan_phases/plan_deconstruction.py`

**Change:** After task creation, query registry for element availability per task. Add element counts to task metadata.

**Insertion point:** In the task creation loop, after `WorkItem` is constructed.

```python
if element_registry:
    available = 0
    total = 0
    for path in task.target_files or []:
        for entry in element_registry.elements_for_file(path):
            total += 1
            if entry.code:
                available += 1
    task.metadata["elements_available"] = available
    task.metadata["elements_total"] = total
    if total > 0 and available == total:
        task.metadata["skip_candidate"] = True
        logger.info("Task %s: all %d elements available in registry", task.id, total)
```

**Tests:** ~40 lines
**Est. total:** ~50 code + ~40 tests = ~90

---

### Step 2.2: SCAFFOLD Phase Registry Pre-Fill (ER-005)

**Modified file:** `src/startd8/utils/file_assembler.py` (or wherever `DeterministicFileAssembler.render_file()` lives)

**Change:** Before emitting `raise NotImplementedError` stubs, check registry for review-validated code.

**Tests:** ~50 lines
**Est. total:** ~80 code + ~50 tests = ~130

---

### Step 2.3: DESIGN Phase Element Contracts (ER-006)

**Modified file:** `src/startd8/contractors/context_seed/design_support.py`

**Change:** After design document generation, use existing `_extract_referenced_elements()` to map element references back to registry entries. Update phase status to `("design", "designed")` with metadata.

**Tests:** ~40 lines
**Est. total:** ~80 code + ~40 tests = ~120

---

### Step 2.4: INTEGRATE Phase Element Provenance (ER-008)

**Modified file:** `src/startd8/contractors/integration_engine.py`

**Change:** After `merge_file()`, parse merged file AST and update registry entries with merge outcome (`merged` / `repaired` / `lost`).

**Insertion point:** After `_manifest_pre_merge_diff()` returns, use the `ManifestDiff` to identify element-level outcomes.

**Tests:** ~60 lines
**Est. total:** ~100 code + ~60 tests = ~160

---

### Step 2.5: TEST Phase Element Validation (ER-009)

**Modified files:** `src/startd8/contractors/artisan_phases/test_construction.py`, `src/startd8/contractors/context_seed/core.py` (TestPhaseHandler)

**Change:** After validators run, map errors to elements via line numbers. Update registry with per-element pass/fail.

**Tests:** ~50 lines
**Est. total:** ~80 code + ~50 tests = ~130

---

### Step 2.6: FINALIZE Phase Element Manifest (ER-011)

**Modified file:** `src/startd8/contractors/artisan_phases/final_assembly.py`

**Change:** Query `registry.summary()` and emit `element_manifest` section in `generation-manifest.json`.

**Tests:** ~40 lines
**Est. total:** ~60 code + ~40 tests = ~100

---

### Step 2.7: Handoff Element State (ER-013)

**Modified file:** `src/startd8/contractors/handoff.py`

**Changes to `write_design_handoff()` (called by design half):**
- Add `element_state` section with registry summary

**Changes to `load_design_handoff()` (called by implementation half):**
- Validate registry consistency against handoff snapshot

**Tests:** ~40 lines
**Est. total:** ~60 code + ~40 tests = ~100

---

### Step 2.8: Element Quality Gates (ER-016)

**Modified file:** `src/startd8/contractors/gate_contracts.py`

**Change:** Add `emit_element_gate()` class method to `GateEmitter`.

```python
@classmethod
def emit_element_gate(
    cls,
    gate_id: str,
    element_id: str,
    phase: str,
    outcome: str,
    evidence: list[dict] | None = None,
    severity: str = "advisory",
) -> None:
    """Emit an element-level quality gate result."""
```

Wire into IMPLEMENT, INTEGRATE, TEST phases where element-level outcomes are determined.

**Tests:** ~40 lines
**Est. total:** ~60 code + ~40 tests = ~100

---

### Step 2.9: Pipeline Contract Propagation (ER-017)

**Modified file:** `src/startd8/contractors/contracts/artisan-pipeline.contract.yaml`

**Change:** Add `element_registry` to propagation chains (advisory severity).

**Modified file:** `src/startd8/contractors/context_schema.py`

**Change:** Add optional `element_registry` field to phase context models where needed.

**Tests:** Contract validation tests
**Est. total:** ~30 YAML + ~30 schema + ~30 tests = ~90

---

### Step 2.10: Phase 2 Integration Test

**New file:** `tests/integration/test_element_registry_pipeline.py`

Full 8-phase walkthrough with mock LLM:
1. Plan ingestion → registry populated
2. PLAN → element inventory in task metadata
3. SCAFFOLD → pre-fill from registry (second run)
4. DESIGN → design constraints registered
5. IMPLEMENT → generation with registry cache
6. INTEGRATE → merge provenance tracked
7. TEST → per-element validation
8. FINALIZE → element manifest in output

**Est. total:** ~200

---

### Phase 2 Summary

| Step | ER Req | Phase | Est. Lines |
|------|--------|-------|------------|
| 2.1 | ER-004 | PLAN | ~90 |
| 2.2 | ER-005 | SCAFFOLD | ~130 |
| 2.3 | ER-006 | DESIGN | ~120 |
| 2.4 | ER-008 | INTEGRATE | ~160 |
| 2.5 | ER-009 | TEST | ~130 |
| 2.6 | ER-011 | FINALIZE | ~100 |
| 2.7 | ER-013 | Handoff | ~100 |
| 2.8 | ER-016 | Gates | ~100 |
| 2.9 | ER-017 | Contract | ~90 |
| 2.10 | — | Integration test | ~200 |
| **Total** | | | **~1,220** |

---

## Phase 3: Intelligence (P2 — Kaizen + Warm Up + Lineage)

### Step 3.1: REVIEW Phase Element Scoring (ER-010)

**Modified file:** `src/startd8/contractors/context_seed/core.py` (ReviewPhaseHandler)

Parse review findings for element-specific mentions. Attribute issues and scores to registry entries.

**Est. total:** ~80 code + ~50 tests = ~130

---

### Step 3.2: Cross-Run Kaizen Metrics (ER-014)

**Modified file:** `src/startd8/element_registry.py`

Add `write_run_metrics(run_id)` method. Writes to `_metrics/run-{timestamp}.json` after FINALIZE.

Add `compare_runs(run_a, run_b)` for Kaizen diff analysis.

**Est. total:** ~100 code + ~60 tests = ~160

---

### Step 3.3: Warm Up Reconciliation (ER-015)

**New method on `ElementRegistry`:**

```python
def reconcile(self, backup_files: dict[str, str], backup_tool: str) -> ReconciliationReport:
    """Compare registry state against backup-generated files.

    Returns report of: added, conflicting, unchanged elements.
    """
```

**Est. total:** ~80 code + ~50 tests = ~130

---

### Step 3.4: Element Lineage (ER-018)

**Modified file:** `src/startd8/element_registry.py`

Add `ElementLineage` dataclass. Populate `lineage` on `ElementEntry` during `put()` and cross-task reuse.

**Est. total:** ~60 code + ~40 tests = ~100

---

### Phase 3 Summary

| Step | ER Req | Est. Lines |
|------|--------|------------|
| 3.1 | ER-010 | ~130 |
| 3.2 | ER-014 | ~160 |
| 3.3 | ER-015 | ~130 |
| 3.4 | ER-018 | ~100 |
| **Total** | | **~520** |

---

## Execution Order and Dependencies

```
Phase 1 (can start immediately):
  Step 1.1 (element_id)
    └── Step 1.2 (registry core)  ← depends on 1.1 for ID format
          ├── Step 1.3 (manifest index)  ← independent of 1.2
          ├── Step 1.4 (plan ingestion)  ← depends on 1.2
          ├── Step 1.5 (engine)          ← depends on 1.2
          │     └── Step 1.6 (adapter)   ← depends on 1.5
          │           └── Step 1.7 (prime) ← depends on 1.6
          └── Step 1.8 (integration test) ← depends on all above

Phase 2 (after Phase 1 complete):
  Steps 2.1–2.9 are INDEPENDENT of each other
  (all depend on Phase 1 registry being available)
  Step 2.10 (integration test) depends on all 2.1–2.9

Phase 3 (after Phase 2 complete):
  Steps 3.1–3.4 are INDEPENDENT of each other
```

**Parallelization opportunity:** Steps 1.3, 1.4, 1.5 can be developed in parallel after 1.2. Steps 2.1–2.9 can all be developed in parallel.

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Registry I/O slows hot path | Generation latency | 100ms timeout on registry reads; fall through to generation (REQ-MP-1102) |
| Concurrent writes corrupt index | Data loss | `threading.Lock` on index mutations; per-entry files are atomic |
| Stale cache produces wrong code | Code quality | Context checksum invalidation (REQ-MP-1108); registry entries always re-validated at TEST |
| 15-site `make_element_id` migration breaks existing IDs | Manifest compat | Run old+new ID generation in parallel during migration; verify no regressions via snapshot test |
| Registry grows unbounded | Disk space | P3: optional LRU eviction; P1: `--clean-element-cache` CLI flag |
| Test suite regressions from new constructor params | CI failures | All new params are `Optional` with `None` default; existing tests pass without changes |

---

## Success Metrics

| Metric | Phase 1 Target | Phase 2 Target | Phase 3 Target |
|--------|---------------|---------------|---------------|
| Cross-task element reuse rate | >0% (prove it works) | >20% on repeat runs | Trending upward per Kaizen |
| Cost saved per multi-task run | Measurable ($0.10+) | Significant ($1.00+) | Optimized via Kaizen |
| Registry operations < 100ms | Yes | Yes | Yes |
| Zero existing test regressions | Yes | Yes | Yes |
| Element-level manifest in FINALIZE | — | Yes | Yes |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-07 | Initial plan: 3 phases, 22 steps, ~3,100 estimated lines |
