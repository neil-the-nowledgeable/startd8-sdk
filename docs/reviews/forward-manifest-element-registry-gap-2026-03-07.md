# Review: ForwardManifest Element Registry Gap

**Date:** 2026-03-07
**Scope:** ForwardElementSpec creation, persistence, and retrieval — Mottainai compliance assessment
**Trigger:** Post-fix run analysis (Run 004 Sub-Run 5) revealed cross-task element duplication and missing index-based retrieval for deterministically assembled files

---

## Question Under Review

How closely does the pipeline follow the [Mottainai Design Principle](../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) when it comes to:

1. Identifying elements shared among separate tasks
2. Persisting those that have been identified
3. Programmatically retrieving them by index for deterministic assembly

---

## Finding: Structural Gap Confirmed

Elements are ID'd early via the forward manifest, but they are **not persisted in a way that supports index-based retrieval**, especially for deterministically assembled files. The gap exists at three levels: creation coverage, persistence structure, and cross-task sharing.

---

## 1. Where ForwardElementSpecs Are Created

| Source | ID Pattern | Trigger | Coverage |
|--------|-----------|---------|----------|
| `api_signatures` | `flcm-fn-{name}`, `flcm-cls-{name}` | Feature has explicit signatures | Only when plan author writes them |
| AST reconciliation | `flcm-ast-{relpath}:{line}:{fqn}` | `project_root` provided + existing source files | Only for edit-mode / existing files |
| Proto extractor | `flcm-cls-svc-*`, `flcm-ep-rpc-*` | `.proto` files present | Proto-based projects only |
| Behavioral contracts | `flcm-fml-*`, `flcm-pat-*`, `flcm-cfg-*` | AST analysis of existing code | Contracts, not element specs |

**ID prefix definitions:** `forward_manifest_extractor.py:57-66` (`_CATEGORY_ABBREV` dict)

**ID generation sites:**

| Location | Lines | ID Format | Trigger |
|---|---|---|---|
| `_extract_api_signatures` (CLASS) | 458 | `flcm-cls-{class_name}` | api_signatures contains class signature |
| `_extract_api_signatures` (FUNCTION) | 501 | `flcm-fn-{func_name}` | api_signatures contains function signature |
| `_extract_runtime_dependencies` | 572 | `flcm-imp-{dep}` | feature.runtime_dependencies not empty |
| `_extract_protocol` | 595 | `flcm-inf-{protocol}` | feature.protocol != "none" |
| `_extract_shared_files` (SHARED) | 624 | `flcm-imp-shared-{stem}` | filepath appears in 2+ features |
| `_extract_shared_files` (UTIL) | 645 | `flcm-{cat}-util-{name}` | filepath matches _UTILITY_FILE_PATTERNS |
| `_extract_behavioral_contracts` (FORMULA) | 991 | `flcm-fml-{id_tag}-{stem}-{field}` | AST analysis finds formula patterns |
| `_extract_behavioral_contracts` (PATTERN) | 1012 | `flcm-pat-{id_tag}-{stem}-{name}-{hash}` | AST analysis finds render patterns |
| `_extract_behavioral_contracts` (CONFIG) | 1031 | `flcm-cfg-{id_tag}-{env_var}` | AST analysis finds config access |
| `_extract_behavioral_contracts` (INFRA) | 1053 | `flcm-inf-{id_tag}-{short_name}` | AST analysis finds infra patterns |
| `SourceReconciler._reconcile_file` (AST) | 1533, 1565 | `flcm-ast-{relpath}:{line}:{fqn}` | AST from existing source files |
| ProtoExtractor (SERVICE) | 761 | `flcm-cls-svc-{name}` | .proto file contains service |
| ProtoExtractor (RPC) | 787 | `flcm-ep-rpc-{name}` | .proto service contains rpc |
| ProtoExtractor (MESSAGE) | 804 | `flcm-cls-msg-{name}` | .proto file contains message |

### Gap: Features Without `api_signatures`

When a feature has **no `api_signatures` AND no existing source files**, the DeterministicExtractor produces **zero ForwardElementSpecs** for that feature. The manifest's `file_specs` dict will have an entry for the file path, but its `elements` list is empty. The micro-prime engine then has nothing to decompose.

This is the common case for features described in natural language (e.g., "Implement a shared JSON logger for emailservice") without explicit function/class signatures in the plan.

---

## 2. Persistence Structure — No Secondary Index

The ForwardManifest stores elements in a nested structure with no secondary index:

```
ForwardManifest (forward_manifest.py:288-314)
  ├── contracts: list[InterfaceContract]           # filtered by applicable_task_ids
  └── file_specs: dict[str, ForwardFileSpec]       # keyed by file path
       └── elements: list[ForwardElementSpec]      # flat list, no ID index
            └── sorted by (parent_class, name)     # deterministic order, not indexed
```

### What exists for retrieval

```python
# ForwardManifest helper methods (forward_manifest.py:316-336)
def contracts_for_task(self, task_id: str) -> list[InterfaceContract]:
    """Filters InterfaceContracts by task_id — NOT element specs."""

def file_specs_for_task(self, task_id: str, target_files: list[str]) -> dict[str, ForwardFileSpec]:
    """Returns file specs by path — still requires list scan for elements."""
```

### What's missing

1. **No element ID index** — Looking up an element by its `flcm-fn-*` ID requires O(n) scan across all file_specs and their element lists. There is no `manifest.get_element_by_id("flcm-fn-getJSONLogger")`.

2. **No cross-task element registry** — When PI-001 and PI-002 both need `getJSONLogger`, there's no mechanism that says "this element was already generated for PI-001, reuse it for PI-002." The file-copy detection (Phase 0, `copy_detection.py`) addresses the **file-level** case but not the **element-level** case.

3. **No persistence of generated element code by ID** — The `_success_cache` in `engine.py` is an in-memory `dict[str, Optional[str]]` (fingerprint -> code), not persisted to disk. If a pipeline run restarts, all element-level cache is lost. The artisan resume cache persists at the **task/file level** (`.startd8/state/`), not at the element level.

4. **Skeleton stubs have no element ID backlink** — `DeterministicFileAssembler` creates skeletons from ForwardFileSpecs, and micro-prime fills stubs. But the splice matches by **function name** (`splice_body_into_skeleton` searches for `def {name}`), not by element ID. No round-trip from skeleton stub back to manifest element.

---

## 3. Cross-Task Element Sharing — Not Possible

### Flow analysis

```
Plan Ingestion
  ├── Features WITH api_signatures → ForwardElementSpecs created         ✅
  ├── Features WITHOUT api_signatures → NO element specs                 ❌
  │     (micro-prime gets an empty elements list)
  │     (cloud fallback generates the whole file blind)
  └── Shared elements across tasks → NOT tracked                         ❌

SCAFFOLD (DeterministicFileAssembler)
  ├── Creates skeleton from ForwardFileSpec.elements                      ✅
  ├── But elements list may be empty (no api_signatures)                  ❌
  └── Skeleton stubs have no element ID backlink                          ❌

IMPLEMENT (Micro-Prime)
  ├── Fills stubs from elements list                                      ✅
  ├── Caches by fingerprint (in-memory only)                              ❌
  ├── Cannot retrieve prior element generation by ID                      ❌
  └── Cross-task element sharing: not possible                            ❌
```

### Concrete examples of waste (Run 004)

**PI-001 / PI-002 (identical logger)**: Both tasks generate `getJSONLogger` and `add_fields` independently. Even with file-copy implemented, this only works when the **entire file** is identical. If PI-002 needed the same `getJSONLogger` but in a file with different imports or an additional function, file-copy wouldn't apply but element-level reuse would.

**PI-003 / PI-006 (gRPC servers)**: Both implement `initStackdriverProfiling` — same function, same spec. Each task generates it independently via cloud fallback. An element-level cache keyed by `flcm-fn-initStackdriverProfiling` could have reused the first generation.

---

## 4. Mottainai Rules Violated

| Rule | Violation | Evidence |
|------|-----------|----------|
| **1. Inventory before generating** | No element-level inventory exists. Micro-prime cannot check "has this element been generated before?" | `_success_cache` is in-memory, not persisted |
| **2. Forward, don't regenerate** | Generated element code is not forwarded to subsequent tasks that need the same element | PI-001/PI-002 both generate `getJSONLogger` independently |
| **4. Register what you produce** | Element-level generation results are not registered by element ID | Only task/file-level registration in `.startd8/state/` |
| **5. Prefer deterministic over stochastic** | When an element's code was already generated, re-generating it via LLM is stochastic where reuse would be deterministic | PI-003/PI-006 both generate `initStackdriverProfiling` |

---

## 5. Relationship to Existing Gaps

This review intersects with several documented Mottainai gaps:

| Gap | Relationship |
|-----|-------------|
| **Gap 14** (No generation result caching in prime) | File-level symptom of the same element-level problem |
| **Gap 9** (Seed enrichment discarded at queue boundary) | Element specs could carry enrichment forward if they were indexed |
| **Gap 15** (Source artifact types not registered) | Source file elements aren't registered for reuse |
| **Phase 0 file-copy** (implemented) | Addresses file-level duplication but not element-level |
| **Simple -> Trivial Decomposer** (designed) | Would benefit from element ID index for template matching |

---

## 6. Recommendation: Element Registry

The missing piece is a persistent, index-addressable element store.

### Proposed interface

```python
class ElementRegistry:
    """Persistent store for generated element code, keyed by element ID.

    Storage: .startd8/state/elements/{element_id_hash}.json
    """

    def get(self, element_id: str) -> Optional[ElementEntry]:
        """Retrieve previously generated code by flcm-* ID. O(1)."""

    def put(self, element_id: str, code: str, source_task: str,
            checksum: str) -> None:
        """Store generated code with provenance and integrity."""

    def has(self, element_id: str) -> bool:
        """Check if element has been generated."""

    def elements_for_file(self, file_path: str) -> list[ElementEntry]:
        """Return all elements whose target file matches."""

@dataclass
class ElementEntry:
    element_id: str          # flcm-fn-getJSONLogger
    code: str                # Generated function body
    source_task: str         # PI-001 (which task first generated it)
    checksum: str            # SHA-256 of code
    generated_at: str        # ISO timestamp
    generator: str           # "ollama:startd8-coder" or "anthropic:claude-sonnet-..."
```

### What this enables

1. **Cross-task element reuse** — PI-002 checks registry before generating `getJSONLogger`; if PI-001 already produced it, reuse at $0.00
2. **O(1) lookup by element ID** — Direct file access via hashed element ID, not O(n) manifest scan
3. **Persistent cache** — Survives pipeline restarts, supports `--resume`
4. **Provenance tracking** — Know which task generated each element and when
5. **Element-level deterministic assembly** — DeterministicFileAssembler can check the registry before creating stubs

### Integration points

| Component | Change |
|-----------|--------|
| `engine.py` (`_success_cache`) | Write to ElementRegistry on generation success; check registry before generating |
| `prime_adapter.py` | Check registry before delegating to fallback |
| `DeterministicFileAssembler` | Query registry to pre-fill stubs instead of `raise NotImplementedError` |
| `ForwardManifest` | Add `get_element_by_id()` helper method for O(1) lookup with lazy index |
| `plan_ingestion_workflow.py` | Populate element specs from skeleton AST when `api_signatures` is empty |

### Also needed: element spec creation for features without `api_signatures`

The registry solves persistence and retrieval, but upstream, features without `api_signatures` still produce no element specs. Two approaches:

1. **Skeleton-derived specs**: After `DeterministicFileAssembler` creates a skeleton, parse its AST and create `ForwardElementSpec` entries for each `def`/`class` with `raise NotImplementedError`. This closes the loop: skeleton stubs -> element specs -> micro-prime decomposition.

2. **LLM-assisted spec extraction**: During plan ingestion's TRANSFORM phase, extract function/class signatures from the task description using a lightweight LLM call. Store as `api_signatures` on the feature. This is stochastic but runs once per feature, not once per element.

---

## 7. Priority Assessment

| Item | Impact | Effort | Priority |
|------|--------|--------|----------|
| `ForwardManifest.get_element_by_id()` lazy index | Enables all downstream work | Low (~30 lines) | **P0** |
| ElementRegistry persistence layer | Cross-task reuse, resume support | Medium (~200 lines) | **P1** |
| Engine/adapter registry integration | Actual reuse at generation time | Medium (~100 lines) | **P1** |
| Skeleton-derived element specs | Element specs for features without api_signatures | Medium (~150 lines) | **P1** |
| DeterministicFileAssembler registry pre-fill | Zero-LLM stub filling from prior generations | Low-Medium (~80 lines) | **P2** |

---

## 8. Conclusion

The user's suspicion is confirmed: **elements are identified early via the forward manifest, but not persisted or indexed in a way that supports programmatic retrieval for cross-task reuse or deterministic assembly.** The file-copy implementation (Phase 0) addresses one symptom (byte-identical files), but the structural gap — no persistent, indexed element registry — remains. This is a Mottainai violation that causes measurable waste in every multi-task pipeline run where tasks share common elements.
