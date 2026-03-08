# REQ-MP-11xx: Element Registry — Persistent Cross-Task Element Reuse

Provide a persistent, index-addressable store for generated element code keyed by Forward Manifest element ID (`flcm-*`). Enable cross-task reuse, pipeline resume at element granularity, and deterministic pre-fill of skeleton stubs from prior generations.

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** DRAFT
> **Date:** 2026-03-07
> **Depends on:** REQ-MP-5xx (Routing & Integration), REQ-MP-10xx (Simple → Trivial Decomposer)
> **Modifies:** `micro_prime/engine.py`, `micro_prime/prime_adapter.py`, `forward_manifest.py`, `forward_manifest_extractor.py`
> **Motivated by:** [Forward Manifest Element Registry Gap Review](../../reviews/forward-manifest-element-registry-gap-2026-03-07.md), [Mottainai Design Principle](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md)
> **Pipeline-wide scope:** [Element Registry Pipeline Requirements](../element-registry/ELEMENT_REGISTRY_REQUIREMENTS.md) — extends these micro-prime-specific requirements to all artisan phases, prime contractor, Kaizen, and Warm Up

---

## 1. Problem Statement

### 1.1 Elements Are Created But Not Indexed

The Forward Manifest creates element specs with structured IDs (`flcm-fn-*`, `flcm-cls-*`, `flcm-ast-*`) during plan ingestion. These specs are stored in a nested structure (`ForwardManifest.file_specs[path].elements[]`) with no secondary index. Retrieving an element by ID requires O(n) scan across all file specs and their element lists.

### 1.2 Generated Code Is Not Persisted by Element ID

The micro-prime engine's `_success_cache` (`engine.py`) is an in-memory `dict[str, Optional[str]]` keyed by fingerprint, not by element ID. Generated code is lost on pipeline restart. The artisan resume cache (`.startd8/state/`) persists at task/file granularity, not element granularity.

### 1.3 Cross-Task Element Reuse Is Not Possible

When multiple tasks share the same element (e.g., PI-001 and PI-002 both need `getJSONLogger`), each task generates it independently. The Phase 0 file-copy mechanism (REQ-MP-1000–1002) addresses byte-identical **files** but not shared **elements** across different files.

### 1.4 Features Without `api_signatures` Have No Element Specs

When a feature has no `api_signatures` and no existing source files, the DeterministicExtractor produces zero ForwardElementSpecs. The micro-prime engine receives an empty elements list and has nothing to decompose. Cloud fallback generates the whole file blind.

### 1.5 Mottainai Violations

| Rule | Violation |
|------|-----------|
| 1. Inventory before generating | No element-level inventory; micro-prime cannot check "has this been generated?" |
| 2. Forward, don't regenerate | Generated element code not forwarded to subsequent tasks needing the same element |
| 4. Register what you produce | Element-level results not registered by element ID |
| 5. Prefer deterministic over stochastic | Reuse of prior generation is deterministic; re-generation via LLM is stochastic |

### 1.6 Observed Waste (Run 004)

| Feature Pair | Shared Element | Waste |
|---|---|---|
| PI-001 / PI-002 | `getJSONLogger`, `add_fields` | PI-002 re-generates both ($0.094) |
| PI-003 / PI-006 | `initStackdriverProfiling` | PI-006 re-generates ($0.187) |

---

## 2. Requirements Summary

| ID | Title | Priority | Status |
|---|---|---|---|
| REQ-MP-1100 | Element Registry Core | P0 | implemented |
| REQ-MP-1101 | Manifest Element Index | P0 | implemented |
| REQ-MP-1102 | Engine Registry Integration | P0 | implemented |
| REQ-MP-1103 | Adapter Registry Integration | P1 | implemented |
| REQ-MP-1104 | Skeleton-Derived Element Specs | P1 | implemented |
| REQ-MP-1105 | Cross-Task Element Lookup | P1 | implemented |
| REQ-MP-1106 | DeterministicFileAssembler Pre-Fill | P2 | implemented |
| REQ-MP-1107 | Element Registry Observability | P2 | implemented |
| REQ-MP-1108 | Registry Staleness and Invalidation | P2 | implemented |
| REQ-MP-1109 | Element Registry CLI Report | P3 | implemented |

---

## 3. Requirements Detail

### REQ-MP-1100: Element Registry Core

**Priority:** P0 | **Status:** implemented

Persistent, index-addressable store for generated element code.

**Module:** `src/startd8/micro_prime/element_registry.py`

**Data model:**

```python
@dataclass
class ElementEntry:
    element_id: str          # flcm-fn-getJSONLogger
    code: str                # Generated function/class body
    source_task: str         # PI-001 (task that first generated it)
    checksum: str            # SHA-256 of code
    generated_at: str        # ISO-8601 timestamp
    generator: str           # "ollama:startd8-coder" or "anthropic:claude-sonnet-..."
    file_path: str           # src/emailservice/logger.py (origin file)
    tier: str                # TRIVIAL / SIMPLE / MODERATE / COMPLEX
```

**Interface:**

```python
class ElementRegistry:
    def __init__(self, state_dir: Path) -> None:
        """Initialize with storage at state_dir/elements/."""

    def get(self, element_id: str) -> Optional[ElementEntry]:
        """O(1) lookup by flcm-* ID. Returns None if not registered."""

    def put(self, entry: ElementEntry) -> None:
        """Store element entry. Overwrites existing entry for same ID."""

    def has(self, element_id: str) -> bool:
        """Check existence without loading full entry."""

    def elements_for_file(self, file_path: str) -> list[ElementEntry]:
        """Return all entries whose file_path matches."""

    def remove(self, element_id: str) -> bool:
        """Remove entry. Returns True if existed."""

    def clear(self) -> None:
        """Remove all entries. Used for clean builds."""
```

**Storage layout:**

```
.startd8/state/elements/
├── index.json              # {element_id: filename} for O(1) lookup
├── flcm-fn-getJSONLogger.json
├── flcm-cls-CustomJsonFormatter.json
└── ...
```

**Constraints:**

- Must use `from startd8.logging_config import get_logger` (not `logging.getLogger()`).
- File I/O failures must not abort generation — log warning and fall through to normal generation path (Mottainai Rule 3: degrade gracefully).
- Entry JSON must include a `schema_version` field for forward compatibility.
- Path normalization: element IDs containing `/` or `:` (e.g., `flcm-ast-src/foo.py:10:bar`) must be hashed for safe filenames.

**Acceptance criteria:**

- `put()` followed by `get()` returns the same entry.
- `get()` on non-existent ID returns `None` (no exception).
- Registry survives process restart (persisted to disk).
- Concurrent writes to different IDs do not corrupt index.

---

### REQ-MP-1101: Manifest Element Index

**Priority:** P0 | **Status:** implemented

Add O(1) element lookup by ID to `ForwardManifest`.

**Module:** `src/startd8/forward_manifest.py`

**Changes:**

```python
class ForwardManifest(BaseModel):
    # Existing fields unchanged

    def get_element_by_id(self, element_id: str) -> Optional[ForwardElementSpec]:
        """O(1) lookup by flcm-* ID. Builds lazy index on first call."""

    def get_elements_by_name(self, name: str) -> list[ForwardElementSpec]:
        """Return all elements matching name (across files)."""

    @cached_property
    def _element_id_index(self) -> dict[str, ForwardElementSpec]:
        """Build index from all file_specs.elements on first access."""
```

**Constraints:**

- Lazy index: built on first call to `get_element_by_id()`, not at construction time.
- `_element_id_index` uses `lru_cache` or `cached_property` pattern — must not copy ForwardElementSpec objects (shallow reference only).
- `get_elements_by_name()` returns list because name is not unique across files (e.g., `__init__` in multiple classes).
- If `ForwardElementSpec` gains an `id` field (currently implicit from contracts), use that; otherwise derive from `(file_path, parent_class, name)` tuple.

**Acceptance criteria:**

- `get_element_by_id("flcm-fn-getJSONLogger")` returns the spec in O(1) after first call.
- Second call does not rebuild the index.
- Unknown ID returns `None`.

---

### REQ-MP-1102: Engine Registry Integration

**Priority:** P0 | **Status:** implemented

Wire `ElementRegistry` into `MicroPrimeEngine` for cache-through on generation.

**Module:** `src/startd8/micro_prime/engine.py`

**Changes:**

1. `MicroPrimeEngine.__init__()` accepts optional `element_registry: Optional[ElementRegistry] = None`.
2. Before generating an element, check `element_registry.get(element_id)`. If found and checksum matches the current skeleton context, use the cached code — skip Ollama call entirely.
3. After successful generation (element passes verification), call `element_registry.put(entry)`.
4. The in-memory `_success_cache` remains for intra-run deduplication; `ElementRegistry` provides cross-run and cross-task persistence.

**Cache hierarchy:**

```
1. In-memory _success_cache (fingerprint → code)     # intra-run, fastest
2. ElementRegistry (element_id → ElementEntry)        # cross-run, persisted
3. Ollama / cloud fallback                            # generation, slowest
```

**Constraints:**

- Registry lookup must not slow down the hot path. If registry I/O takes >100ms, log a warning and skip (fall through to generation).
- The `element_id` used for registry lookup must match the `flcm-*` ID from the ForwardElementSpec. If the element has no manifest ID (e.g., created via skeleton AST without plan ingestion), derive a stable ID from `(file_path, parent_class, name)`.
- Stale entries (code generated against a different skeleton or different interface contract) must not be blindly reused. REQ-MP-1108 defines the invalidation rules.

**Acceptance criteria:**

- Element generated in task A is retrieved from registry in task B (cross-task reuse).
- Registry miss falls through to normal generation without error.
- Registry entry includes `generator` field distinguishing Ollama vs cloud origin.

---

### REQ-MP-1103: Adapter Registry Integration

**Priority:** P1 | **Status:** implemented

Wire `ElementRegistry` into `MicroPrimeCodeGenerator` (prime adapter) for cross-feature element reuse.

**Module:** `src/startd8/micro_prime/prime_adapter.py`

**Changes:**

1. `MicroPrimeCodeGenerator.__init__()` accepts optional `element_registry`.
2. Pass registry to `MicroPrimeEngine` on construction.
3. After post-assembly validation (`_detect_assembly_defect`), if a file passes all checks, register each element's generated code in the registry.
4. Log `prime.element_registry_hit` / `prime.element_registry_miss` counts in generation metadata.

**Acceptance criteria:**

- Multi-feature pipeline run: second feature reuses elements from first feature's generation.
- Metadata includes registry hit/miss counts.

---

### REQ-MP-1104: Skeleton-Derived Element Specs

**Priority:** P1 | **Status:** implemented

Create `ForwardElementSpec` entries from skeleton AST when `api_signatures` is empty.

**Module:** `src/startd8/forward_manifest_extractor.py` or new `src/startd8/micro_prime/skeleton_spec_extractor.py`

**Mechanism:**

After `DeterministicFileAssembler` creates a skeleton (or after cloud fallback writes a complete file), parse its AST and create `ForwardElementSpec` entries for each `def`/`class` containing `raise NotImplementedError`.

**ID format:** `flcm-skel-{relpath}:{line}:{name}` (distinct from `flcm-ast-*` which comes from existing source files).

**Trigger:** Feature has zero ForwardElementSpecs after plan ingestion AND a skeleton or generated file exists on disk.

**Constraints:**

- Must not overwrite specs from higher-precedence sources (`deterministic`, `human-yaml`, `proto`). Use precedence `_SOURCE_PRECEDENCE["skeleton"] = -1` (below `source-ast`).
- Only create specs for stubs (`raise NotImplementedError`), not for already-implemented bodies.
- Specs include `parent_class`, `kind` (FUNCTION/CLASS/CONSTANT), and `signature` extracted from AST.

**Acceptance criteria:**

- Feature with no `api_signatures` gets element specs after skeleton generation.
- Specs have valid `flcm-skel-*` IDs.
- Micro-prime engine can decompose the feature using skeleton-derived specs.

---

### REQ-MP-1105: Cross-Task Element Lookup

**Priority:** P1 | **Status:** implemented

Enable the prime contractor to check if an element needed by the current task was already generated by a previous task.

**Module:** `src/startd8/contractors/prime_contractor.py`

**Mechanism:**

Before calling `code_generator.generate()`, iterate the current feature's ForwardElementSpecs. For each, check `element_registry.has(element_id)`. If **all** elements are in the registry, the feature can be assembled deterministically from cached code — no LLM call needed.

**Decision tree:**

```
For each ForwardElementSpec in feature.file_specs:
  ├── element_registry.has(id)?
  │    ├── YES + checksum valid → use cached code
  │    └── YES + checksum stale → invalidate, generate fresh
  └── NO → generate via normal path

If ALL elements hit cache:
  └── Assemble from cache → GenerationResult(cost=0.0, strategy="element_reuse")

If SOME elements hit cache:
  └── Pre-fill skeleton stubs with cached code, generate remaining via Ollama/cloud
```

**Constraints:**

- "All elements from cache" assembly must still pass `_detect_assembly_defect()`.
- Element reuse must respect interface contract changes: if the element's `InterfaceContract` changed since the cached generation, invalidate (REQ-MP-1108).

**Acceptance criteria:**

- Feature where all elements exist in registry: assembled at $0.00, no LLM calls.
- Feature where 2/3 elements exist: 2 pre-filled, 1 generated. Cost reflects only the generated element.
- Metadata includes `elements_from_cache` and `elements_generated` counts.

---

### REQ-MP-1106: DeterministicFileAssembler Pre-Fill

**Priority:** P2 | **Status:** implemented

When creating skeleton files, check the element registry and pre-fill stubs with cached code instead of `raise NotImplementedError`.

**Module:** `src/startd8/utils/file_assembler.py`

**Mechanism:**

During `render_file()`, for each element in the ForwardFileSpec, check `element_registry.get(element_id)`. If found, emit the cached implementation instead of `raise NotImplementedError`.

**Result:** Files produced by SCAFFOLD may already be partially or fully implemented, reducing the work required in IMPLEMENT.

**Constraints:**

- Pre-filled code must pass `ast.parse()` in the context of the full skeleton. If it doesn't (e.g., imports changed), fall back to `raise NotImplementedError` for that element.
- Pre-filled elements must be marked in the skeleton with a comment: `# [ELEMENT-REGISTRY: {element_id}]` for traceability.
- The micro-prime engine must recognize pre-filled elements and skip them (don't re-generate code that's already present and valid).

**Acceptance criteria:**

- Skeleton rendered with 3 elements, 2 in registry: 2 pre-filled, 1 stub.
- Pre-filled skeleton passes `ast.parse()`.
- IMPLEMENT phase skips pre-filled elements.

---

### REQ-MP-1107: Element Registry Observability

**Priority:** P2 | **Status:** implemented

Emit OTel metrics and structured logs for registry operations.

**Metrics:**

| Metric | Type | Description |
|---|---|---|
| `micro_prime.element_registry.hits` | Counter | Registry lookups that returned a cached entry |
| `micro_prime.element_registry.misses` | Counter | Registry lookups that returned None |
| `micro_prime.element_registry.puts` | Counter | New entries written to registry |
| `micro_prime.element_registry.invalidations` | Counter | Entries invalidated due to staleness |
| `micro_prime.element_registry.size` | Gauge | Total entries in registry |
| `micro_prime.element_registry.reuse_cost_saved_usd` | Counter | Estimated cost saved by reuse (based on avg cloud cost per element) |

**Span attributes:**

- `element.registry_hit: bool` on each element processing span.
- `element.registry_source_task: str` when reusing cached code.

**Kaizen integration:**

- Registry hit/miss ratio per run in `kaizen-metrics.json`.
- `ollama_net_value_ratio` metric: elements where Ollama output survived to final / total elements (per sub-run 5 recommendation).

---

### REQ-MP-1108: Registry Staleness and Invalidation

**Priority:** P2 | **Status:** implemented

Define when a cached element entry is stale and must be regenerated.

**Invalidation triggers:**

| Trigger | Detection | Action |
|---|---|---|
| Interface contract changed | Compare `InterfaceContract.checksum` at lookup time | Invalidate entry, regenerate |
| Skeleton signature changed | Compare element signature (params, return type) | Invalidate entry, regenerate |
| Element spec modifiers changed | Compare `modifiers` list on ForwardElementSpec | Invalidate entry, regenerate |
| Manual invalidation | `--clean-element-cache` CLI flag | Clear all entries |
| TTL expiry (optional) | Configurable `element_registry.ttl_hours` (default: unlimited) | Invalidate entry, regenerate |

**Checksum computation:**

```python
def _element_context_checksum(element: ForwardElementSpec, contracts: list[InterfaceContract]) -> str:
    """Hash the element's structural context for staleness detection."""
    parts = [
        element.name,
        element.kind,
        element.signature or "",
        element.parent_class or "",
        *(c.checksum for c in contracts if c.applicable_element_ids and element.name in c.applicable_element_ids),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()
```

Store `context_checksum` in `ElementEntry`. At lookup time, recompute and compare.

**Acceptance criteria:**

- Element with unchanged context: registry hit.
- Element with changed signature: registry miss (invalidated).
- `--clean-element-cache`: all entries removed.

---

### REQ-MP-1109: Element Registry CLI Report

**Priority:** P3 | **Status:** implemented

CLI command or flag to inspect registry contents.

**Interface:**

```bash
# List all registered elements
startd8 element-registry list

# Show details for specific element
startd8 element-registry show flcm-fn-getJSONLogger

# Report reuse statistics
startd8 element-registry stats

# Clear registry
startd8 element-registry clear
```

**Report format (JSON):**

```json
{
  "total_entries": 42,
  "entries_by_tier": {"TRIVIAL": 12, "SIMPLE": 18, "MODERATE": 10, "COMPLEX": 2},
  "entries_by_generator": {"ollama:startd8-coder": 18, "anthropic:claude-sonnet-...": 24},
  "cross_task_reuses": 7,
  "estimated_cost_saved_usd": 1.23
}
```

---

## 4. Data Flow

```
Plan Ingestion
  └── ForwardManifest with element specs (from api_signatures, AST, proto)
        │
        ├── REQ-MP-1101: Manifest Element Index (lazy O(1) lookup)
        │
        ▼
SCAFFOLD
  └── DeterministicFileAssembler
        │
        ├── REQ-MP-1106: Check ElementRegistry for pre-fill
        │     ├── HIT → emit cached code instead of stub
        │     └── MISS → emit raise NotImplementedError
        │
        ├── REQ-MP-1104: If no element specs, derive from skeleton AST
        │
        ▼
IMPLEMENT (Micro-Prime Engine)
  └── Per element:
        │
        ├── 1. In-memory _success_cache check (intra-run)
        │
        ├── 2. REQ-MP-1102: ElementRegistry check (cross-run)
        │     ├── HIT + valid checksum → use cached code, skip generation
        │     └── MISS or stale → generate via Ollama/cloud
        │
        ├── 3. Generate → verify → splice
        │
        └── 4. REQ-MP-1102: ElementRegistry.put() on success
              └── Persisted for future tasks and runs

Prime Contractor
  └── Per feature:
        │
        ├── REQ-MP-1105: Check all elements against registry
        │     ├── ALL HIT → assemble from cache ($0.00)
        │     ├── PARTIAL → pre-fill + generate remaining
        │     └── ALL MISS → normal generation path
        │
        └── REQ-MP-1103: Register generated elements on success
```

---

## 5. Relationship to Existing Requirements

| Existing | Relationship |
|----------|-------------|
| REQ-MP-10xx (Simple → Trivial) | Phase 0 file-copy is file-level; Element Registry is element-level. Complementary. |
| REQ-MP-1007 (Post-Assembly Validation) | Registry entries must pass validation before being cached. |
| REQ-MP-5xx (Routing & Integration) | Registry lookup is a new routing decision point: cache-hit → skip generation. |
| REQ-MP-9xx (Moderate Decomposer) | Decomposed sub-elements can be registered individually. |
| Mottainai Gap 14 | Element Registry subsumes file-level caching with finer granularity. |
| Mottainai Rule 1 | Registry IS the element-level inventory. |
| Mottainai Rule 4 | `put()` IS registration. |

---

## 6. Implementation Estimate

| Requirement | New/Modified Code | Tests | Estimated Lines |
|---|---|---|---|
| REQ-MP-1100 (Core) | New: `element_registry.py` | `test_element_registry.py` | ~250 |
| REQ-MP-1101 (Manifest Index) | Modified: `forward_manifest.py` | Extend existing tests | ~40 |
| REQ-MP-1102 (Engine Integration) | Modified: `engine.py` | Extend `test_engine.py` | ~80 |
| REQ-MP-1103 (Adapter Integration) | Modified: `prime_adapter.py` | Extend `test_adapters.py` | ~60 |
| REQ-MP-1104 (Skeleton Specs) | New or modified: `forward_manifest_extractor.py` | New test file | ~150 |
| REQ-MP-1105 (Cross-Task Lookup) | Modified: `prime_contractor.py` | Extend contractor tests | ~100 |
| REQ-MP-1106 (DFA Pre-Fill) | Modified: `file_assembler.py` | Extend assembler tests | ~80 |
| REQ-MP-1107 (Observability) | Modified: `element_registry.py`, `engine.py` | Metric assertion tests | ~60 |
| REQ-MP-1108 (Staleness) | Modified: `element_registry.py` | Invalidation tests | ~80 |
| REQ-MP-1109 (CLI Report) | New: CLI command or flag | CLI integration test | ~60 |
| **Total** | | | **~960** |

---

## 7. Verification Strategy

| Requirement | Verification Method |
|---|---|
| REQ-MP-1100 | Unit test: put/get/has/remove round-trip; restart persistence; concurrent writes |
| REQ-MP-1101 | Unit test: O(1) lookup by ID; lazy index build; unknown ID returns None |
| REQ-MP-1102 | Integration test: element generated in run A, retrieved from registry in run B |
| REQ-MP-1103 | Integration test: multi-feature pipeline, second feature reuses first's elements |
| REQ-MP-1104 | Unit test: skeleton with stubs → ForwardElementSpecs created with flcm-skel-* IDs |
| REQ-MP-1105 | Integration test: all-cache-hit feature assembled at $0.00; partial-hit pre-fills |
| REQ-MP-1106 | Unit test: skeleton rendered with pre-filled elements from registry |
| REQ-MP-1107 | Unit test: OTel counters increment on hit/miss/put |
| REQ-MP-1108 | Unit test: changed signature → invalidation; unchanged → hit |
| REQ-MP-1109 | CLI test: list/show/stats/clear subcommands produce expected output |

---

## 8. Open Questions

1. **Element ID stability**: Should element IDs be derived from `(file_path, parent_class, name)` or from the `flcm-*` contract ID? The former is stable across plan changes; the latter ties to the specific plan ingestion run. Recommendation: use `flcm-*` ID when available, derive from `(file_path, parent_class, name)` as fallback.

2. **Registry scope**: Should the registry be per-project (`.startd8/state/elements/`) or per-run (inside `pipeline-output/`)? Per-project enables cross-run reuse but risks staleness. Per-run is clean but loses cross-run benefit. Recommendation: per-project with staleness checks (REQ-MP-1108).

3. **Code vs body**: Should the registry store the full function definition (`def foo(): ...`) or just the body (lines inside the `def`)? The engine splices bodies into skeletons, so body-only aligns with current architecture. But cross-task reuse may need the full definition when the skeleton differs. Recommendation: store full definition, extract body at splice time.

4. **Registry size management**: For large projects with hundreds of elements, should there be a max-entries cap or LRU eviction? Recommendation: no cap initially; add LRU if `.startd8/state/elements/` exceeds a configurable size threshold.

---

## 9. Pipeline-Wide Scope

This document defines the micro-prime-specific element registry requirements (REQ-MP-1100 through REQ-MP-1109). The element registry's scope extends beyond micro-prime to serve the entire capability delivery pipeline.

See [Element Registry Pipeline Requirements](../element-registry/ELEMENT_REGISTRY_REQUIREMENTS.md) for:

| Scope | Requirements | What It Adds |
|-------|-------------|-------------|
| Element identity standard | ER-001 | Single `make_element_id()` utility replacing 13+ ad-hoc ID generation sites |
| Registry as pipeline service | ER-002 | Top-level `src/startd8/element_registry.py` (not embedded in micro_prime/) |
| All 8 artisan phases | ER-003..ER-011 | Per-phase element tracking (inventory, pre-fill, design constraints, merge provenance, validation, scoring, manifest) |
| Prime contractor | ER-012 | Cross-feature element reuse in the feature loop |
| Design handoff | ER-013 | Element state in the design↔implementation split |
| Kaizen metrics | ER-014 | Cross-run per-element improvement tracking |
| Warm Up reconciliation | ER-015 | Element-level reconciliation during toolchain transitions |
| Quality gates | ER-016 | Element-level gate emission at phase boundaries |
| Pipeline contract | ER-017 | Element registry in `artisan-pipeline.contract.yaml` propagation chains |
| Lineage/provenance | ER-018 | Full phase history and cross-task reuse tracking |

The REQ-MP-11xx requirements defined in this document are the **implementation foundation** — the core `ElementRegistry` class, storage layout, and engine integration. The ER-xxx requirements are the **pipeline integration** — how every phase consumes and contributes to the registry.
