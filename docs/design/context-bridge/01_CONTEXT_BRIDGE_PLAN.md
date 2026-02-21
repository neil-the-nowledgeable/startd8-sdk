# Context Bridge — Implementation Plan

## Overview

The Context Bridge is a deterministic adapter that merges Eagle's `ProjectMetadata` (macro project structure) and ContextCore's `ExtractionResult` (micro capability inventory) into a single `context: dict[str, Any]` consumed by startd8-sdk's Artisan Contractor pipeline. It uses zero LLM tokens — purely data transformation.

---

## 1. File-by-File Breakdown

### Files to Create

| File | Purpose |
|---|---|
| `src/hybrid_scaffold/__init__.py` | Package init. Exports `ContextBridge`. |
| `src/hybrid_scaffold/context_bridge.py` | Core `ContextBridge` class with all transformation methods |
| `tests/__init__.py` | Package init |
| `tests/test_context_bridge.py` | Unit tests for all transformation logic |
| `tests/test_context_bridge_integration.py` | Integration tests against real Eagle + Extract |
| `tests/fixtures/sample_project/` | Minimal multi-service Python project for testing |
| `pyproject.toml` | Project config with path-based deps on Eagle and ContextCore |

### Files to Modify

None in external codebases. Eagle, ContextCore, and startd8-sdk are consumed as read-only dependencies.

---

## 2. Dependencies and Imports

### Runtime

| Dependency | Import Path | Notes |
|---|---|---|
| Eagle `models` | `models.ProjectMetadata`, `models.ServiceMetadata` | Eagle has no pyproject.toml — needs editable install or sys.path |
| Eagle `RepoScanner` | `extractors.repo_scanner.RepoScanner` | |
| ContextCore `CapabilityExtractor` | `contextcore.utils.capability_extractor.CapabilityExtractor` | Already has package structure |
| ContextCore `ExtractionResult` | `contextcore.utils.capability_extractor.ExtractionResult` | |

### Standard Library

`pathlib.Path`, `dataclasses.asdict`, `collections.defaultdict`, `typing`, `re`, `datetime`

### Test

`pytest`, `unittest.mock`

---

## 3. Implementation Order

### Phase 1: Scaffolding (30 min)
1. Create directory structure
2. Create `pyproject.toml` with path-based dependencies
3. Create `__init__.py` files

### Phase 2: Eagle Transformation (1.5 hours)
4. Implement `ContextBridge.__init__(project_root, project_id)`
5. Implement `run_eagle()` — wraps `RepoScanner().extract()`
6. Implement `_transform_eagle()` — converts `ProjectMetadata` to `project_structure` dict
7. Write unit tests for `_transform_eagle()`

### Phase 3: ContextCore Transformation (1.5 hours)
8. Implement `run_extract()` — wraps `CapabilityExtractor(path).extract_all()` (NOT `run_extraction()` which writes files)
9. Implement `_transform_extract()` — converts `ExtractionResult` to `capability_map` dict
10. Implement `_build_by_file_index()`
11. Implement `_build_test_coverage_map()`
12. Write unit tests

### Phase 4: Summary Rendering (1 hour)
13. Implement `_render_codebase_summary()`
14. Write unit tests

### Phase 5: Orchestration (30 min)
15. Implement `build_context()` — wires everything together
16. Write unit test with mocked sub-methods

### Phase 6: Integration Tests (1 hour)
17. Create test fixture project
18. Write integration tests against fixture
19. Verify output schema matches design doc

---

## 4. Data Transformation Logic

### Eagle `ProjectMetadata` → `project_structure`

```
ProjectMetadata.project_id             → project_structure["project_id"]
ProjectMetadata.services               → project_structure["services"] (list of dicts)
    ServiceMetadata.name               → service["name"]
    ServiceMetadata.language           → service["language"]
    ServiceMetadata.estimated_loc      → service["estimated_loc"]
    ServiceMetadata.build_system       → service["build_system"]
    ServiceMetadata.has_tests          → service["has_tests"]
    ServiceMetadata.has_dockerfile     → service["has_dockerfile"]
    ServiceMetadata.protocols          → service["protocols"]
    ServiceMetadata.files              → service["files"]
        FileInfo.path                  → file["path"]
        FileInfo.loc                   → file["loc"]
        FileInfo.is_generated          → file["is_generated"]
    DROP: language_confidence, dependency_manifest, dependency_manifest_contents, extraction_source

ProjectMetadata.service_dependencies   → project_structure["service_dependencies"]
    ServiceDependency.from_service     → dep["from"]       *** KEY RENAME ***
    ServiceDependency.to_service       → dep["to"]         *** KEY RENAME ***
    ServiceDependency.protocol         → dep["protocol"]
    ServiceDependency.evidence         → dep["evidence"]

ProjectMetadata.shared_assets          → project_structure["shared_assets"]
    SharedAsset.filename               → asset["filename"]
    SharedAsset.services               → asset["services"]
    SharedAsset.sha256                 → asset["sha256"]
    DROP: SharedAsset.loc

ProjectMetadata.languages()            → project_structure["languages"]
ProjectMetadata.total_loc()            → project_structure["total_loc"]
len(ProjectMetadata.services)          → project_structure["total_services"]
```

### ContextCore `ExtractionResult` → `capability_map`

```
ExtractionResult.project_name          → capability_map["project_name"]
ExtractionResult.total_count()         → capability_map["total_capabilities"]

# by_type: each capability list → list of dicts via vars()
# by_file: grouped by file_path (see section 5)
# test_coverage_map: heuristic mapping (see section 6)
```

---

## 5. by_file Index Construction

Groups capabilities by `file_path`, then by `source_type` within each file:

```
For each capability_type in [cli_commands, classes, functions, api_endpoints]:
    For each capability in that list:
        file_key = capability.file_path
        entry = {"name": ..., "line": capability.line_number, "signature": ...}
        if capability_type in (classes, functions):
            entry["docstring"] = capability.docstring
        by_file[file_key][capability_type].append(entry)
```

Key decisions:
- Tests and doc_sections excluded from by_file (tests go to test_coverage_map)
- Output uses `"line"` key, not `"line_number"`

---

## 6. test_coverage_map Construction

Heuristic mapping — no import analysis in v1:

```
1. Collect all source file paths from cli_commands, classes, functions, api_endpoints
2. For each test in ExtractionResult.tests:
   a. Extract base name: "tests/test_auth.py" → "auth"
   b. Find source files whose basename matches
   c. Map matched source file → append test.name
```

Known limitations:
- Misses integration tests that test multiple modules
- Misses non-standard test file names
- Ambiguous basenames map to multiple source files (acceptable — superset is fine)

---

## 7. codebase_summary Rendering

```
Line 1: "Project: {N} services, {N} languages, {N} total LOC."

Service lines (up to 15, truncate with "... and N more"):
  "  emailservice (Python, 340 LOC, 12 functions, 3 classes, 8 tests)"

Dependency lines:
  "  emailservice → paymentservice (gRPC)"

Entry points:
  "{N} CLI commands, {N} API endpoints, {N} public classes, {N} public functions"
  "Test coverage: {N} test functions"
```

Critical join logic: Eagle file paths are relative to service dir (`main.py`), ContextCore paths are relative to project root (`service_a/main.py`). Must prepend service name when cross-referencing.

---

## 8. Unit Test Plan

### Eagle Transformation
| Test | Verifies |
|---|---|
| `test_transform_eagle_single_service` | Single service produces correct dict |
| `test_transform_eagle_multi_service_multi_language` | Languages deduplication, total_loc sum |
| `test_transform_eagle_service_dependencies_key_rename` | `from_service`/`to_service` → `from`/`to` |
| `test_transform_eagle_shared_assets_drops_loc` | SharedAsset.loc excluded |
| `test_transform_eagle_empty_project` | Zero services → empty lists, zero totals |

### ContextCore Transformation
| Test | Verifies |
|---|---|
| `test_transform_extract_by_type_all_categories` | All 6 types present |
| `test_transform_extract_total_capabilities` | Count matches sum |
| `test_transform_extract_capability_dict_fields` | All fields present in each dict |

### by_file Index
| Test | Verifies |
|---|---|
| `test_by_file_groups_by_filepath` | Same-file capabilities grouped |
| `test_by_file_separates_types` | Classes and functions under separate keys |
| `test_by_file_uses_line_not_line_number` | Key renamed correctly |
| `test_by_file_excludes_tests_and_docs` | Not in by_file |
| `test_by_file_empty_extraction` | Empty input → empty output |

### test_coverage_map
| Test | Verifies |
|---|---|
| `test_coverage_map_convention_match` | `test_auth.py::test_login` → `src/auth.py` |
| `test_coverage_map_no_match` | Unmatched tests excluded |
| `test_coverage_map_multiple_tests_per_file` | Multiple tests → same source file |
| `test_coverage_map_ambiguous_basename` | Both matches included |

### codebase_summary
| Test | Verifies |
|---|---|
| `test_summary_header_line` | Service/language/LOC counts |
| `test_summary_service_lines` | Per-service details |
| `test_summary_large_project_truncation` | >15 services truncated |

### build_context Orchestration
| Test | Verifies |
|---|---|
| `test_build_context_returns_all_keys` | All 3 top-level keys present |
| `test_build_context_does_not_overwrite_existing` | Existing context keys preserved |

---

## 9. Integration Test Plan

Tests marked `@pytest.mark.integration` — run against `tests/fixtures/sample_project/`:

| Test | Verifies |
|---|---|
| `test_full_pipeline_against_fixture` | End-to-end, no exceptions, all keys exist |
| `test_eagle_discovers_fixture_services` | Finds `service_a` and `service_b` |
| `test_extract_discovers_fixture_capabilities` | Finds class, function, test, CLI command |
| `test_by_file_matches_eagle_files` | Every .py file has by_file entry |
| `test_test_coverage_map_links_fixture_tests` | `test_main.py` → `service_a/main.py` |
| `test_codebase_summary_mentions_services` | Summary contains service names |
| `test_output_is_json_serializable` | `json.dumps()` succeeds (no dataclass/Path objects) |

---

## 10. Risks and Unknowns

### Risk 1: Eagle is not installable as a Python package
Eagle has no `pyproject.toml`. Requires either sys.path hack or creating a minimal pyproject.toml for Eagle.
**Recommendation**: Create minimal `pyproject.toml` for Eagle as prerequisite.

### Risk 2: Eagle expects multi-service directory structure
`RepoScanner` treats top-level subdirectories as services. Single-service flat projects return zero services.
**Mitigation**: If zero services, log warning and continue with ContextCore data only.

### Risk 3: Use `extract_all()` not `run_extraction()`
`run_extraction()` writes YAML files to disk (side effects). The bridge should call `CapabilityExtractor(path).extract_all()` directly, which returns `ExtractionResult` in memory.

### Risk 4: ExtractionResult fields are untyped lists
Fields declared as bare `list`, not `list[ExtractedCapability]`. Add runtime type assertions.

### Risk 5: Path prefix mismatch between Eagle and ContextCore
Eagle file paths are relative to service dir; ContextCore paths are relative to project root. Must prepend service name when cross-referencing.

### Risk 6: test_coverage_map heuristic is fragile
Filename convention (`test_auth.py` → `auth.py`) will miss non-standard test naming. Document as known limitation; LLM can refine in Explore phase.

### Risk 7: `decorators` field overloaded in class extraction
ContextCore repurposes `decorators` to store first 10 public method names for classes. Don't label as "decorators" in user-facing output.

### Risk 8: No output schema validation
No Pydantic model validates the output dict. Consider adding one (~30 min extra) to catch schema drift early.

---

## Dependency Graph

```
pyproject.toml + scaffolding
    │
    ▼
_transform_eagle()  ────┐
    │                    │
    ▼                    ▼
run_eagle()        _transform_extract()
                        │
                        ├── _build_by_file_index()
                        │
                        ├── _build_test_coverage_map()
                        │
                        ▼
                   _render_codebase_summary()
                        │
                        ▼
                   build_context()
                        │
                        ▼
                   Unit tests → Fixture → Integration tests
```

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

- **architecture**: 14 suggestions applied (R10-S3, R10-S8, R11-S1, R11-S3, R1-S1, R3-S1, R3-S2, R4-S1, R5-S1, R5-S8, R6-S3, R7-S1, R7-S9, R8-S2)
- **data**: 16 suggestions applied (R10-S1, R10-S2, R10-S6, R11-S2, R11-S6, R1-S4, R2-S1, R2-S3, R5-S2, R5-S9, R6-S7, R7-S2, R8-S1, R8-S6, R9-S2, R9-S6)
- **interfaces**: 13 suggestions applied (R10-S4, R11-S5, R1-S3, R3-S3, R4-S5, R4-S6, R5-S3, R5-S10, R7-S3, R7-S10, R8-S3, R8-S10, R9-S5)
- **ops**: 6 suggestions applied (R10-S10, R1-S7, R4-S7, R4-S8, R8-S8, R9-S3)
- **risks**: 7 suggestions applied (R1-S2, R1-S6, R3-S7, R4-S10, R7-S6, R8-S5, R10-S6)
- **security**: 9 suggestions applied (R1-S9, R3-S8, R3-S9, R4-S3, R4-S4, R5-S5, R6-S2, R7-S4, R8-S7)
- **validation**: 12 suggestions applied (R10-S5, R10-S7, R11-S4, R1-S8, R2-S4, R3-S10, R5-S6, R6-S1, R7-S7, R8-S4, R8-S9, R9-S4)

### Areas Needing Further Review

All areas have reached the substantially addressed threshold.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Add Pydantic output schema validation as a gating step in build_context(). | claude-4 (claude-opus-4-6) | The bridge is the contract boundary between data producers and downstream SDK consumers. Enforcing schema validation here catches malformed dicts at the source rather than allowing silent failures downstream. Risk 8 already acknowledges this gap — promoting it from optional to required is a small investment with high payoff. | 2026-02-20 00:50:30 UTC |
| R1-S2 | Define explicit degraded-mode behavior when Eagle returns zero services. | claude-4 (claude-opus-4-6) | Risk 2 acknowledges zero-service scenarios but the plan never specifies the shape of the output in that case. Downstream consumers likely assume ≥1 service. Defining whether services is an empty list or a synthetic single-service entry, and how codebase_summary renders, prevents undefined behavior. | 2026-02-20 00:50:30 UTC |
| R1-S3 | Specify the exact Eagle API contract including class, method, arguments, and exceptions. | claude-4 (claude-opus-4-6) | The plan references RepoScanner().extract() but the feature doc also mentions Decomposer. Ambiguity in the entry point will cause integration failures. Pinning the exact call signature and wrapping in proper error handling is essential for a reliable integration. | 2026-02-20 00:50:30 UTC |
| R1-S4 | Enforce JSON serializability at transformation time, not just in tests. | claude-4 (claude-opus-4-6) | Relying solely on integration tests to catch Path objects and other non-serializable types means bugs are detected late. Coercing paths to strings and sanitizing during transformation is defense-in-depth and aligns with the principle of failing fast at the source. | 2026-02-20 00:50:30 UTC |
| R1-S6 | Define an explicit path normalization algorithm to reconcile Eagle service-relative paths with ContextCore project-relative paths. | claude-4 (claude-opus-4-6) | This is the highest-risk data correctness issue. Section 7 acknowledges the mismatch but provides no implementation detail. Without a concrete algorithm and dedicated helper function, cross-referencing in by_file and codebase_summary will silently produce incorrect results. This is a critical gap in the plan. | 2026-02-20 00:50:30 UTC |
| R1-S7 | Add structured logging with timing and bridge_metadata to the output dict. | claude-4 (claude-opus-4-6) | The feature doc claims 3-8 second execution. Without instrumentation there's no way to verify or diagnose performance in production. Adding bridge_metadata (elapsed_seconds, generated_at) is low-cost and enables downstream caching decisions and observability. | 2026-02-20 00:50:30 UTC |
| R1-S8 | Add tests for idempotency and that context.update() does not corrupt pre-existing keys. | claude-4 (claude-opus-4-6) | The plan lists test_build_context_does_not_overwrite_existing but provides no implementation detail. Since the integration pattern is context.update(merged), accidentally including keys like workflow_id or project_root could corrupt caller state. Expanding these tests with concrete implementation details is important for correctness. | 2026-02-20 00:50:30 UTC |
| R1-S9 | Use explicit field allowlisting in _transform_eagle() rather than copying all fields and dropping some. | claude-4 (claude-opus-4-6) | Defense in depth against schema drift and sensitive data leakage. The plan already drops dependency_manifest_contents, but using an allowlist approach is inherently safer — new fields added to Eagle's models won't automatically flow into LLM prompts. The cost is minimal and the security benefit is meaningful. | 2026-02-20 00:50:30 UTC |
| R2-S1 | Normalize file paths between Eagle (service-relative) and ContextCore (project-relative). | gemini-3 (gemini-3-pro-preview) | This is the same critical issue as R1-S6. Path misalignment will break by_file cross-referencing and codebase_summary. Accepting both as they reinforce the same gap — the implementation should have a single concrete path normalization strategy. | 2026-02-20 00:50:30 UTC |
| R2-S2 | Implement partial failure handling so one tool's failure doesn't crash the entire bridge. | gemini-3 (gemini-3-pro-preview) | If Eagle fails but ContextCore succeeds, downstream LLM phases can still function with partial data. The plan currently has no error isolation between the two tool invocations. Adding try/except with error flags in the output is a resilience best practice for an adapter layer. | 2026-02-20 00:50:30 UTC |
| R2-S3 | Implement explicit JSON-safe serialization by recursively converting non-primitive types. | gemini-3 (gemini-3-pro-preview) | Same core issue as R1-S4. dataclasses.asdict() does not handle Path objects. Enforcing serializability at transformation time rather than only asserting it in tests is the correct approach. Accepting as reinforcement of R1-S4. | 2026-02-20 00:50:30 UTC |
| R2-S4 | Add a Pydantic output model to validate the context dict schema at runtime. | gemini-3 (gemini-3-pro-preview) | Same as R1-S1. A Pydantic model at the output boundary enforces the contract, catches drift, and provides self-documenting schema. Accepting as reinforcement. | 2026-02-20 00:50:30 UTC |
| R3-S1 | Add formal Protocol/ABC interfaces for Eagle and ContextCore data source adapters to decouple extraction from transformation. | claude-4 (claude-opus-4-6) | This is a critical architecture improvement that directly addresses the tight coupling between ContextBridge and two concrete external dependencies. It enables testability without mocking internals, supports future non-Python extractors (an acknowledged limitation), and follows the Dependency Inversion Principle. Aligns well with previously accepted R1-S1 through R1-S4. | 2026-02-20 00:55:06 UTC |
| R3-S2 | Introduce a Pydantic ContextBridgeResult model to formally type and validate the output dict, making Risk 8 actionable. | claude-4 (claude-opus-4-6) | Risk 8 already identifies the lack of output schema validation. With previously applied suggestions tightening field semantics, a formal schema is now feasible and necessary. This prevents downstream consumers from silently receiving malformed dicts. Overlaps with and reinforces R4-S5. | 2026-02-20 00:55:06 UTC |
| R3-S3 | Define explicit error types and a BridgeResult envelope carrying partial results plus structured diagnostics on source failure. | claude-4 (claude-opus-4-6) | The plan acknowledges partial failure (Risk 2: zero services) but never defines what build_context() returns in failure scenarios. This is critical for ExplorePhaseHandler to make informed decisions. Overlaps with and reinforces R4-S1 which has endorsement. A clear partial-success contract is essential for robustness. | 2026-02-20 00:55:06 UTC |
| R3-S7 | Add Risk 9 for large monorepo performance — implement configurable max_files/max_loc thresholds with early termination. | claude-4 (claude-opus-4-6) | Enterprise monorepos with >10K files are common and the plan's 3-8s estimate is unvalidated at scale. Without guardrails, the bridge could OOM or hang, becoming the pipeline bottleneck. A max_files threshold with truncation warning is a low-cost safeguard. Has 1 endorsement. | 2026-02-20 00:55:06 UTC |
| R3-S8 | Sanitize and validate all file paths from Eagle and ContextCore to prevent path traversal and absolute path leakage into output context. | claude-4 (claude-opus-4-6) | The output context feeds into an LLM agent with tool-use capabilities (file read/write). Unsanitized paths (symlinks, .., absolute paths) represent a real security risk. Path normalization relative to project_root is low-cost and high-impact. Has 1 endorsement and aligns with R4-S3. | 2026-02-20 00:55:06 UTC |
| R3-S9 | Add input validation and size limits on Eagle/ContextCore outputs before transformation to prevent resource exhaustion. | claude-4 (claude-opus-4-6) | External dependencies return untyped data (Risk 4 already acknowledges this). Validating structure and applying size limits before transformation is defensive programming that prevents unbounded memory/time consumption. Complements R3-S7 (large repo limits) and R4-S10 (runtime schema checks). | 2026-02-20 00:55:06 UTC |
| R3-S10 | Add contract tests with golden snapshot and consumer-compatibility test feeding bridge output into ExplorePhaseHandler. | claude-4 (claude-opus-4-6) | The bridge exists solely to serve ExplorePhaseHandler. Without a contract test against the actual consumer, interface drift between the bridge and startd8-sdk will go undetected. A golden snapshot test plus a consumer compatibility test provides high confidence with relatively low implementation cost. | 2026-02-20 00:55:06 UTC |
| R4-S1 | Implement partial success strategy so build_context() returns available data and flags errors in _meta when one source fails. | gemini-3 (gemini-3-pro-preview) | Directly addresses a critical gap — the plan acknowledges Risk 2 but doesn't define the behavior. Has 1 endorsement (R4-F1) and aligns with R3-S3. Essential for pipeline resilience. Merges naturally with the BridgeResult envelope from R3-S3. | 2026-02-20 00:55:06 UTC |
| R4-S3 | Enforce path sanitization — validate all output paths are within project_root, prevent path traversal. | gemini-3 (gemini-3-pro-preview) | Directly aligns with R3-S8. Path sanitization is a security necessity given the output feeds an LLM agent with file access capabilities. Accepting as it reinforces the already-accepted R3-S8. | 2026-02-20 00:55:06 UTC |
| R4-S4 | Truncate docstrings in output to prevent arbitrarily large user content from consuming memory and tokens. | gemini-3 (gemini-3-pro-preview) | Docstrings are user-controlled content with no size bounds. Even at medium severity, this is a practical safeguard that prevents bloated context dicts. Simple to implement (truncate at N chars with ellipsis) and aligns with the overall input validation theme of R3-S9. | 2026-02-20 00:55:06 UTC |
| R4-S5 | Formalize output with Pydantic model and use .model_dump() to generate the output dict. | gemini-3 (gemini-3-pro-preview) | Directly aligns with R3-S2 and makes Risk 8 actionable. Already accepted as R3-S2; this reinforces that decision. A Pydantic model is the right approach for schema enforcement. | 2026-02-20 00:55:06 UTC |
| R4-S6 | Accept a logger instance via __init__ for integration with the parent SDK's logging configuration. | gemini-3 (gemini-3-pro-preview) | Low-effort, high-value change. The bridge runs inside startd8-sdk and should respect its logging configuration rather than configuring its own. Standard dependency injection pattern. | 2026-02-20 00:55:06 UTC |
| R4-S7 | Add execution timeouts to run_eagle() and run_extract() to prevent indefinite blocking. | gemini-3 (gemini-3-pro-preview) | Complements R3-S7 (large repo limits). Even with file count limits, external extractors could hang for other reasons (deadlocks, network dependencies). A 30s timeout is a simple safety net that prevents the entire pipeline from blocking. | 2026-02-20 00:55:06 UTC |
| R4-S8 | Include extractor versions (eagle_version, contextcore_version) in output metadata. | gemini-3 (gemini-3-pro-preview) | Low-cost addition that significantly aids debugging when extraction quality varies across environments. Essential for reproducibility in enterprise CI/CD. Aligns with the _bridge_meta concept without the over-engineering of R3-S4. | 2026-02-20 00:55:06 UTC |
| R4-S10 | Add runtime input schema checks (isinstance/attribute checks) on Eagle/ContextCore return objects before processing. | gemini-3 (gemini-3-pro-preview) | Risk 4 already identifies that ExtractionResult fields are untyped lists. Runtime validation at the boundary with external dependencies catches breaking changes early rather than producing silent garbage. Aligns with R3-S9's input validation gates. | 2026-02-20 00:55:06 UTC |
| R5-S1 | Add explicit error handling and partial-success semantics for build_context() when one upstream tool fails. | claude-4 (claude-opus-4-6) | The plan covers Eagle failure (Risk 2) but not ContextCore failure. Defining partial output shapes and a bridge_warnings field is essential for robustness; this is a genuine gap in the error handling strategy that multiple applied suggestions (R3-S1, R4-S1) make more important to close. | 2026-02-20 01:00:59 UTC |
| R5-S2 | Specify idempotency contract for build_context() ensuring deterministic output ordering across runs. | claude-4 (claude-opus-4-6) | Deterministic output is critical for snapshot tests, cache invalidation, and debugging. The fix (sorted keys in by_file, sorted capabilities by line_number) is low-cost and eliminates a real class of flaky behavior that depends on AST walk order. | 2026-02-20 01:00:59 UTC |
| R5-S3 | Define the contract for by_file keys when Eagle reports files ContextCore didn't analyze and vice versa. | claude-4 (claude-opus-4-6) | Endorsed by 1 reviewer and addresses a real gap at the intersection of R1-S3 and R1-S6. The union strategy with appropriate markers (empty capability lists for Eagle-only files, service:null for orphan files) provides a complete and predictable index. This also relates to the R2-F2 concern (3 endorsements) about orphan files. | 2026-02-20 01:00:59 UTC |
| R5-S5 | Sanitize file_path values from ContextCore to prevent path traversal in by_file keys. | claude-4 (claude-opus-4-6) | Path traversal is a real security concern when downstream phases may use by_file keys for file I/O. The validation (no absolute paths, no '..' in parts) is trivial to implement and provides defense-in-depth alongside R3-S8 and R3-S9. | 2026-02-20 01:00:59 UTC |
| R5-S6 | Add a schema contract test that validates build_context() output against a JSON Schema derived from the feature doc. | claude-4 (claude-opus-4-6) | Risk 8 already identified this need but left it as 'consider.' After 26+ accepted suggestions modifying the output structure, a machine-readable schema test is the most effective way to prevent regression. Adding jsonschema as a test dependency is low-cost and provides high-value contract enforcement. | 2026-02-20 01:00:59 UTC |
| R5-S8 | Specify bridge behavior when project_root contains no analyzable content (both tools return empty results). | claude-4 (claude-opus-4-6) | This is a valid degenerate case that R5-S1's partial-failure handling doesn't fully cover. Adding a bridge_status flag and warning is minimal effort and prevents downstream phases from producing nonsensical LLM prompts with all-zero statistics. Complements R5-S1 naturally. | 2026-02-20 01:00:59 UTC |
| R5-S9 | Add a test validating the codebase_summary cross-join between Eagle services and ContextCore capabilities produces correct per-service counts. | claude-4 (claude-opus-4-6) | The path-prefix join logic (Risk 5) is the most fragile part of the bridge. R1-S3 standardized formats but no existing test verifies the actual join produces correct counts. A targeted test with edge cases (hyphens, special characters) directly validates the critical path. | 2026-02-20 01:00:59 UTC |
| R5-S10 | Define serialization contract ensuring the context dict round-trips losslessly through JSON. | claude-4 (claude-opus-4-6) | The existing test_output_is_json_serializable only checks json.dumps succeeds, not round-trip fidelity. Path objects, sets, and None-vs-missing ambiguity are real issues. Strengthening to a round-trip test and explicitly casting Path→str and set→sorted list in transformation logic is low-cost and prevents subtle bugs. | 2026-02-20 01:00:59 UTC |
| R6-S1 | Enforce POSIX path normalization (forward slashes) for all by_file keys and path values in output. | gemini-3 (gemini-3-pro-preview) | R1-S3 (applied) addressed path format standardization but this makes the POSIX normalization explicit and critical-severity. Cross-platform path inconsistency would silently break all cross-referencing between Eagle and ContextCore data. A simple .replace('\\', '/') normalization is trivial and essential. | 2026-02-20 01:00:59 UTC |
| R6-S2 | Filter sensitive file paths (.env, *.key, *.pem, credentials.json) from context output before it reaches the LLM. | gemini-3 (gemini-3-pro-preview) | Even though only file paths (not contents) are included, exposing sensitive filenames to the LLM creates an information leakage vector. A blocklist-based filter is simple to implement and aligns with the security improvements from R3-S8 and R3-S9. This is a defense-in-depth measure. | 2026-02-20 01:00:59 UTC |
| R6-S3 | Document that ContextBridge is a one-shot snapshot and must be re-instantiated if used in iterative agent loops. | gemini-3 (gemini-3-pro-preview) | This is a critical architectural clarification rather than a code change. If an agent creates new files during a Code→Test→Fix loop, the stale context will cause incorrect behavior. Documenting this as a known limitation in the class docstring and Section 10 is minimal effort with high value for correct usage. | 2026-02-20 01:00:59 UTC |
| R6-S7 | Handle root-level files in codebase_summary join logic that aren't under any service subdirectory. | gemini-3 (gemini-3-pro-preview) | This directly relates to the R2-F2 concern (3 endorsements) about orphan files and the cross-join correctness validated by R5-S9. Files at project root (setup.py, scripts/) will fail the service-prefix join logic. Treating them as root-level without prepending a service name is a necessary fix for correctness. | 2026-02-20 01:00:59 UTC |
| R7-S1 | Add explicit partial failure handling: if Eagle or ContextCore fails independently, populate the successful half and degrade the failed half gracefully. | claude-4 (claude-opus-4-6) | High severity, well-reasoned. With two independent extraction pipelines, a failure in one shouldn't block the other. The sentinel/degraded output pattern is standard for resilient orchestration and the validation approach is concrete. | 2026-02-20 01:07:56 UTC |
| R7-S2 | Cross-reference Eagle's `has_tests` signal with ContextCore's test extraction and surface discrepancies in a `test_coverage_gaps` field. | claude-4 (claude-opus-4-6) | This addresses a real data fidelity gap in polyglot projects where ContextCore (Python-only) will systematically miss non-Python tests that Eagle detects. Surfacing discrepancies helps downstream consumers understand coverage map completeness. | 2026-02-20 01:07:56 UTC |
| R7-S3 | Specify path normalization algorithm (no leading `./`, no trailing `/`, forward slashes) before cross-referencing Eagle and ContextCore paths. | claude-4 (claude-opus-4-6) | This is the implementation detail that makes Risk 5 mitigation actually work. Without normalization, the join between Eagle and ContextCore paths will silently produce orphaned entries due to trivial format differences. | 2026-02-20 01:07:56 UTC |
| R7-S4 | Document that ContextCore extraction must use AST-only parsing and add a security note about the shared-process trust boundary. | claude-4 (claude-opus-4-6) | Medium severity security concern. Since the bridge uses library imports (shared address space) rather than subprocess isolation, verifying that ContextCore never evaluates code is a necessary security boundary documentation. The validation approach (code audit + test) is practical. | 2026-02-20 01:07:56 UTC |
| R7-S6 | Exclude files with `is_generated=true` from the test coverage mapping heuristic. | claude-4 (claude-opus-4-6) | 1 endorsement. Direct second-order effect of accepting R6-S2. Generated files (e.g., protobuf stubs) should not appear in test coverage maps — agents shouldn't suggest writing tests for generated code, and missing test matches for generated files add noise. | 2026-02-20 01:07:56 UTC |
| R7-S7 | Add idempotency test verifying two sequential `build_context()` calls on the same instance return identical results. | claude-4 (claude-opus-4-6) | Cheap to implement and catches a real class of bugs (accumulated state in instance variables). Even with single-threaded usage documented, sequential reuse is a natural pattern that should produce consistent results. | 2026-02-20 01:07:56 UTC |
| R7-S9 | Add fallback summary templates for Eagle-only and ContextCore-only partial failure scenarios. | claude-4 (claude-opus-4-6) | Direct consequence of accepting R7-S1. If partial failure is handled gracefully, the summary renderer must have conditional logic for missing data sources. Without fallback templates, the summary would either crash or produce misleading output. | 2026-02-20 01:07:56 UTC |
| R7-S10 | Specify that `by_type` entries use a uniform schema with all `ExtractedCapability` fields present regardless of source type. | claude-4 (claude-opus-4-6) | R3-F2 resolved None retention but not schema uniformity. Heterogeneous shapes in `by_type` lists complicate downstream consumers. Uniform schema (all fields always present) is simpler to document, validate, and consume, even if some fields are semantically irrelevant for certain types. | 2026-02-20 01:07:56 UTC |
| R8-S1 | Update Plan Section 4 and Section 8 to use `source_service`/`target_service` keys consistent with accepted R1-F1. | claude-4 (claude-opus-4-6) | Direct inconsistency between the plan and an accepted suggestion. The plan's transformation logic and unit tests still reference the old `from`/`to` keys, which will cause implementers to produce incorrect output. | 2026-02-20 01:32:05 UTC |
| R8-S2 | Add partial-input rendering logic to codebase_summary for Eagle-only or ContextCore-only failure cases, and fix the dependency graph. | claude-4 (claude-opus-4-6) | The accepted Risk 2 mitigation creates a legitimate partial-data path, but the summary renderer unconditionally references both data sources. This is a real second-order interaction that will cause runtime errors on partial failure. | 2026-02-20 01:32:05 UTC |
| R8-S3 | Add explicit path normalization step using os.path.relpath() to enforce project-root-relative paths in by_file index. | claude-4 (claude-opus-4-6) | R1-F2 sets the contract but the plan has no enforcement mechanism. If ContextCore returns absolute paths, the entire by_file index breaks. An explicit normalization step is cheap insurance. | 2026-02-20 01:32:05 UTC |
| R8-S4 | Add an idempotency guard to build_context() to prevent undefined behavior on double invocation. | claude-4 (claude-opus-4-6) | R3-F4 documented lifecycle expectations but without enforcement, a coding error calling the bridge twice produces undefined behavior. A simple check-and-skip or check-and-raise is trivial to implement. | 2026-02-20 01:32:05 UTC |
| R8-S5 | Normalize Eagle file paths to project-root-relative in project_structure to enable cross-referencing with capability_map.by_file. | claude-4 (claude-opus-4-6) | This is the core path mismatch problem. Without normalizing Eagle's service-relative paths, downstream consumers cannot look up files from project_structure in by_file. This is essential for the bridge's stated purpose of unified context. | 2026-02-20 01:32:05 UTC |
| R8-S6 | Specify a shared _capability_to_dict() helper for docstring truncation that works for both by_file and by_type without mutating source objects. | claude-4 (claude-opus-4-6) | R4-F2 acceptance creates a truncation requirement that must be applied in two code paths. Without a shared helper, implementers will likely miss one path or accidentally mutate source data. | 2026-02-20 01:32:05 UTC |
| R8-S7 | Ensure subprocess fallback for Eagle uses shell=False with list arguments and validates project_root before invocation. | claude-4 (claude-opus-4-6) | Command injection via unsanitized path arguments is a real security risk when subprocess fallback is used. Using shell=False with list args and path validation is standard security practice. | 2026-02-20 01:32:05 UTC |
| R8-S8 | Add a risk noting that performance estimates assume local SSD and may be 10x slower on network filesystems. | claude-4 (claude-opus-4-6) | The 3-8 second estimate being off by 10x on NFS/EFS could cause premature timeout kills in CI/CD. Documenting the variance costs nothing and prevents misconfigured pipelines. | 2026-02-20 01:32:05 UTC |
| R8-S9 | Add 2-3 additional test fixture projects covering edge cases like flat layout, no tests, and co-located tests. | claude-4 (claude-opus-4-6) | With 46 accepted suggestions adding edge case handling, a single happy-path fixture provides inadequate integration test coverage. Additional fixtures are essential to validate the accepted suggestions' implementations. | 2026-02-20 01:32:05 UTC |
| R8-S10 | Deduplicate capabilities that appear in multiple type lists (e.g., a Click-decorated function in both functions and cli_commands) with a precedence rule. | claude-4 (claude-opus-4-6) | Without deduplication, the by_file index double-counts capabilities, inflating total_capabilities and producing misleading summaries. A simple precedence rule (specific > general) resolves this cleanly. | 2026-02-20 01:32:05 UTC |
| R9-S2 | Normalize Eagle's service-relative file paths to project-root-relative in project_structure output. | gemini-3 (gemini-3-pro-preview) | This is the same core issue as R8-S5 — Eagle's service-relative paths must be normalized for cross-referencing with capability_map. This is critical for the bridge's stated purpose. | 2026-02-20 01:32:05 UTC |
| R9-S3 | Implement the ContextBridgeTimeout logic explicitly in build_context() as specified by accepted R7-F3. | gemini-3 (gemini-3-pro-preview) | R7-F3 was accepted but the plan lacks implementation details for the timeout wrapper. Without explicit implementation steps, this accepted suggestion will be missed during coding. | 2026-02-20 01:32:05 UTC |
| R9-S4 | Synthesize a root service entry when Eagle returns zero services for flat projects. | gemini-3 (gemini-3-pro-preview) | Simply logging a warning and leaving services empty (current Risk 2 mitigation) deprives agents of LOC and language stats for flat repositories. A synthetic root service preserves macro-level information at minimal implementation cost. | 2026-02-20 01:32:05 UTC |
| R9-S5 | Use dataclasses.asdict() instead of vars() for serializing ExtractionResult capability lists. | gemini-3 (gemini-3-pro-preview) | vars() is shallow and fails with __slots__. dataclasses.asdict() is the standard, safe approach for nested dataclass serialization. The plan already imports it in Section 2. | 2026-02-20 01:32:05 UTC |
| R9-S6 | Use getattr(dep, 'evidence', None) for defensive retrieval of the evidence field from ServiceDependency. | gemini-3 (gemini-3-pro-preview) | R4-F1 identified the evidence field mismatch. Regardless of whether the input schema is updated, the bridge code should be robust to the field being absent in installed Eagle versions. This is standard defensive programming. | 2026-02-20 01:32:05 UTC |
| R10-S1 | Update plan Section 4 and Section 8 to use `source_service`/`target_service` instead of `from`/`to`. | claude-4 (claude-opus-4-6) | R1-F1 and R8-F2 were accepted but the plan was never updated. The unit test asserts the wrong output keys. This is a concrete implementation bug. | 2026-02-20 01:39:21 UTC |
| R10-S2 | Update plan Section 5 and Section 8 to reflect the R5-F3 resolution regarding test inclusion in `by_file`. | claude-4 (claude-opus-4-6) | The plan contradicts the accepted R5-F3 suggestion. Section 5 still excludes tests, and the unit test asserts the old behavior. | 2026-02-20 01:39:21 UTC |
| R10-S3 | Add graceful degradation logic in summary rendering when Eagle data is absent, and fix the dependency graph. | claude-4 (claude-opus-4-6) | The partial-failure path (zero Eagle services) produces misleading output ('0 services, 0 languages'). The dependency graph also incorrectly omits the Eagle→summary dependency. | 2026-02-20 01:39:21 UTC |
| R10-S4 | Add missing imports for `ServiceDependency`, `SharedAsset`, and `FileInfo` to Section 2. | claude-4 (claude-opus-4-6) | The transformation logic accesses fields on these types but they're not listed as imports. Implementers following Section 2 alone will miss required imports. | 2026-02-20 01:39:21 UTC |
| R10-S5 | Add unit test for `is_generated` field propagation from Eagle file metadata into `capability_map.by_file` entries. | claude-4 (claude-opus-4-6) | R6-F2 was accepted to add `is_generated` to capability_map, requiring a cross-source join. This is the most error-prone transformation and needs dedicated testing. | 2026-02-20 01:39:21 UTC |
| R10-S6 | Add explicit path normalization step in the plan that converts Eagle's service-relative paths to project-relative paths. | claude-4 (claude-opus-4-6) | Path normalization is acknowledged as critical (Risk 5, R1-F2, R9-F1) but the plan contains no implementation step for it. Section 4 copies paths verbatim. This gap will cause cross-referencing to fail. | 2026-02-20 01:39:21 UTC |
| R10-S7 | Add unit test for docstring truncation at 500-character boundary (R4-F2). | claude-4 (claude-opus-4-6) | R4-F2 was accepted but no test verifies the boundary. Without a test, truncation logic could be removed in a refactor without detection. | 2026-02-20 01:39:21 UTC |
| R10-S8 | Explicitly state that `_build_by_file_index()` runs before `_build_test_coverage_map()` and they share the source path set. | claude-4 (claude-opus-4-6) | The two functions share a data dependency on source file paths. Without specifying execution order and data sharing, the implementation may duplicate work or use inconsistent path sets. | 2026-02-20 01:39:21 UTC |
| R10-S10 | Add `time.perf_counter()` instrumentation to log execution time for Eagle extraction, ContextCore extraction, and total bridge execution. | claude-4 (claude-opus-4-6) | With many accepted suggestions adding complexity, the original 3-8s estimate is likely stale. Basic timing instrumentation is trivial to add and essential for detecting performance regressions. | 2026-02-20 01:39:21 UTC |
| R11-S1 | Synthesize a `_root` or `misc` service for files not assigned to any Eagle service. | gemini-3 (gemini-3-pro-preview) | Directly implements the accepted R2-F2 requirement for handling orphan/root files. Without this, flat projects lose all files from `project_structure`. | 2026-02-20 01:39:21 UTC |
| R11-S2 | Enforce POSIX path separators (`/`) for all paths in the output context dict. | gemini-3 (gemini-3-pro-preview) | Mixed separators break cross-referencing and LLM tokenization. Standardizing on `/` is a trivial normalization with high consistency payoff. | 2026-02-20 01:39:21 UTC |
| R11-S3 | Include `doc_sections` in the `by_file` index. | gemini-3 (gemini-3-pro-preview) | Consistent with R5-F3 resolution to make `by_file` a complete file index. Documentation files appearing empty to agents is a usability gap. | 2026-02-20 01:39:21 UTC |
| R11-S4 | Sort services by `estimated_loc` descending before truncation in `codebase_summary`. | gemini-3 (gemini-3-pro-preview) | Non-deterministic ordering produces different summaries across runs. Sorting by LOC ensures the most significant services appear before truncation. | 2026-02-20 01:39:21 UTC |
| R11-S5 | Implement a fallback getter for `ServiceDependency.evidence` using `getattr(dep, 'evidence', 'Inferred')`. | gemini-3 (gemini-3-pro-preview) | Until Eagle's input schema is updated (R4-F1/R10-F4), the code must handle the missing attribute. This is the pragmatic implementation fix for the schema gap. | 2026-02-20 01:39:21 UTC |
| R11-S6 | Verify whether ContextCore stores methods nested within classes or in the top-level functions list, and iterate accordingly. | gemini-3 (gemini-3-pro-preview) | If methods are nested within class objects and not in the flat `functions` list, the current iteration logic silently drops them. Data completeness issue. | 2026-02-20 01:39:21 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S5 | Introduce a ContextBridgeConfig dataclass to parameterize hardcoded thresholds. | claude-4 (claude-opus-4-6) | This is a v1 bridge with a narrow scope. The hardcoded values (15 services, basename heuristic) are reasonable defaults. Introducing a config object adds abstraction overhead prematurely. If the bridge proves valuable and thresholds need tuning, this can be added in v2. The plan already documents these as known limitations. | 2026-02-20 00:50:30 UTC |
| R1-S10 | Add content-hash caching to avoid redundant re-scans. | claude-4 (claude-opus-4-6) | This is a premature optimization for v1. At 3-8 seconds, the bridge is fast enough. Caching introduces complexity around staleness, invalidation, and state management. The plan should focus on correctness first. If performance becomes an issue, caching can be added later with clear metrics to justify it. | 2026-02-20 00:50:30 UTC |
| R2-S5 | Add dynamic sys.path manipulation via EAGLE_HOME env var as import fallback. | gemini-3 (gemini-3-pro-preview) | The plan already identifies Eagle's lack of pyproject.toml as Risk 1 and recommends creating a minimal pyproject.toml as a prerequisite. That is the cleaner solution. Adding dynamic sys.path manipulation is a maintenance hazard and makes the import behavior environment-dependent and harder to debug. Solve the root cause instead. | 2026-02-20 00:50:30 UTC |
| R2-S6 | Enhance test mapping heuristics to support Go and Ruby test naming conventions. | gemini-3 (gemini-3-pro-preview) | The plan already documents the heuristic as fragile and Python-specific (Risk 6). For v1, the bridge targets a known Python fixture project. Expanding to other language conventions adds complexity without a concrete use case. The LLM can refine coverage mapping in the Explore phase as noted in the plan. | 2026-02-20 00:50:30 UTC |
| R3-S4 | Add versioned schema with namespace prefix, manifest key, and collision detection with force=True kwarg to context.update(). | claude-4 (claude-opus-4-6) | While the bridge metadata idea has merit (and is partly covered by R4-S8 for extractor versions), the full proposal — raising on key collisions, force=True kwarg, namespace documentation — is over-engineered for a v1 internal adapter. R1-S3 already addressed shallow-merge collision risk. Adding _bridge_meta version info is captured more simply by R4-S8. | 2026-02-20 00:55:06 UTC |
| R3-S5 | Add structured logging with timing instrumentation and a diagnostic CLI command. | claude-4 (claude-opus-4-6) | While structured logging with timing is good practice, this adds significant scope (structlog dependency, CLI entry point, pyproject.toml changes) for a deterministic 3-8 second adapter that runs inside a larger SDK which likely has its own logging/observability. Logger injection (R4-S6) and timeouts (R4-S7) address the core operational concerns more proportionally. | 2026-02-20 00:55:06 UTC |
| R3-S6 | Define content-hash-based caching for repeated build_context() calls on unchanged source. | claude-4 (claude-opus-4-6) | Premature optimization for a 3-8 second deterministic transformation. The bridge is called once per ExplorePhase run. Adding a file-tree hashing mechanism with cache files introduces complexity (cache invalidation, stale cache bugs, file I/O) disproportionate to the benefit. Can be added later if profiling identifies it as a bottleneck. | 2026-02-20 00:55:06 UTC |
| R4-S2 | Abstract execution strategy with Executor interface supporting LibraryExecutor and SubprocessExecutor. | gemini-3 (gemini-3-pro-preview) | R3-S1 already introduces adapter Protocol interfaces that decouple extraction from the bridge. Adding a separate Executor abstraction layer on top creates unnecessary indirection. A SubprocessExecutor could be one concrete adapter implementation under R3-S1's design, not a separate abstraction. Risk 1 is better addressed by the pyproject.toml recommendation already in the plan. | 2026-02-20 00:55:06 UTC |
| R4-S9 | Add token budget test asserting codebase_summary stays under 1000 tokens for a 100-service project. | gemini-3 (gemini-3-pro-preview) | The summary already truncates at 15 services, making it naturally bounded. A specific token count test (1000 tokens) is arbitrary without knowing the downstream prompt budget. The truncation logic is already tested via test_summary_large_project_truncation. Character/line length assertions would be more meaningful than token counting, which requires a tokenizer dependency. | 2026-02-20 00:55:06 UTC |
| R5-S4 | Add memory footprint awareness and max_capabilities_per_file truncation for large monorepos. | claude-4 (claude-opus-4-6) | 15-50MB for a large monorepo is manageable for a short-lived pipeline process. Adding truncation logic introduces complexity and data loss that could confuse downstream consumers. The docstring truncation from R4-F2 already addresses the largest per-entry cost. This is premature optimization for a v1 bridge; can be revisited if real memory issues arise. | 2026-02-20 01:00:59 UTC |
| R5-S7 | Define behavior when Eagle and ContextCore report conflicting metadata (e.g., different project names). | claude-4 (claude-opus-4-6) | The bridge is a deterministic data merger, not a reconciliation engine. Both values are already preserved in the output under different keys (project_structure.project_id vs capability_map.project_name). Adding a _validate_consistency() step with heuristic warnings adds complexity for an edge case that downstream consumers can handle themselves. Logging a warning for name mismatches is reasonable but doesn't warrant a new output field and validation step. | 2026-02-20 01:00:59 UTC |
| R6-S4 | Filter generated code (protobufs, etc.) from capability_map using Eagle's is_generated flag. | gemini-3 (gemini-3-pro-preview) | Generated code is part of the project's actual structure and may be relevant for understanding interfaces (e.g., protobuf-generated service stubs). The is_generated flag is already preserved in the output per Section 4, allowing downstream consumers to filter if needed. Silently removing capabilities reduces the bridge's fidelity as a data transformation layer. | 2026-02-20 01:00:59 UTC |
| R6-S5 | Add a helper _ensure_eagle_importable() to handle PYTHONPATH for Eagle imports. | gemini-3 (gemini-3-pro-preview) | Risk 1 already covers this concern and recommends creating a minimal pyproject.toml for Eagle. Adding a runtime sys.path manipulation helper is the fragile approach the plan is trying to avoid. The proper fix (Eagle pyproject.toml) is already documented as a prerequisite. | 2026-02-20 01:00:59 UTC |
| R6-S6 | Refine codebase_summary to count only non-private (non-underscore-prefixed) members. | gemini-3 (gemini-3-pro-preview) | The bridge is a deterministic data transformation, not an opinionated filter. Private members are still real capabilities. Filtering them changes the semantics of 'total_capabilities' and creates inconsistency between by_type (which would include privates) and the summary (which wouldn't). The LLM can interpret the full data during the Explore phase. | 2026-02-20 01:00:59 UTC |
| R7-S5 | Add CI-specific test configuration section with editable install commands and conftest.py setup. | claude-4 (claude-opus-4-6) | This is operational CI configuration detail that belongs in the project's CI pipeline configuration (e.g., `.github/workflows/`), not in an architectural implementation plan. R1-S1 already addressed Eagle packaging. CI setup is a standard DevOps concern that doesn't warrant architectural specification. | 2026-02-20 01:07:56 UTC |
| R7-S8 | Add a language confidence threshold to filter low-confidence language detections from Eagle. | claude-4 (claude-opus-4-6) | Low severity and introduces a policy decision (what threshold?) that may discard useful information. The bridge should faithfully transform Eagle's output; if Eagle reports a language, the bridge should pass it through. Filtering by confidence is a concern for Eagle itself, not the bridge. | 2026-02-20 01:07:56 UTC |
| R9-S1 | Integrate ContextBridge into startd8-sdk source tree instead of a standalone hybrid_scaffold package. | gemini-3 (gemini-3-pro-preview) | This is a significant architectural restructuring that contradicts the plan's design of consuming Eagle, ContextCore, and startd8-sdk as read-only dependencies. The bridge as a standalone adapter maintains clean separation of concerns and allows independent versioning. Deployment packaging can be handled via standard Python packaging without merging codebases. | 2026-02-20 01:32:05 UTC |
| R10-S9 | Sanitize service names and file paths in summary rendering to prevent markdown/prompt injection. | claude-4 (claude-opus-4-6) | Low severity, and the attack vector requires a malicious repo being analyzed — which is outside the current threat model. Service names come from directory names controlled by the developer. Over-engineering for v1. | 2026-02-20 01:39:21 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 00:47:40 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | architecture | critical | Add an output schema validation layer (Pydantic model or TypedDict) for the merged context dict, not as optional but as a gating step in `build_context()`. | Risk 8 acknowledges this gap but defers it. Without schema validation, downstream startd8-sdk phase handlers can silently receive malformed dicts, causing failures far from the source. A ~30 min investment prevents hours of debugging when Eagle or ContextCore schemas drift. The bridge is the contract boundary — it must enforce the contract. | New file `src/hybrid_scaffold/schema.py`; validated at end of `build_context()` before return | Unit test that mutates output and asserts `ValidationError`; integration test confirms real output passes validation |
| R1-S2 | risks | critical | Define an explicit fallback strategy when Eagle returns zero services (single-service or flat-layout projects), including how `project_structure`, `capability_map` cross-references, and `codebase_summary` degrade. | Risk 2 says "log warning and continue with ContextCore data only" but the plan never specifies what `project_structure.services` looks like (empty list? synthetic single-service entry?), nor how `codebase_summary` renders without service data. Downstream phases likely assume ≥1 service. | New subsection "Degraded Mode Behavior" after Section 7; update unit test plan with degraded-mode tests | Tests for zero-service Eagle output producing valid schema; `codebase_summary` test for service-less project |
| R1-S3 | interfaces | high | Specify the exact Eagle API contract: which class/function is called, what arguments it takes, and what exceptions it raises. The plan references `RepoScanner().extract()` but Eagle's actual API may differ (e.g., `Decomposer` orchestrates `RepoScanner`). | The feature doc mentions both `RepoScanner` and `Decomposer`; the plan only references `RepoScanner().extract()`. If the real entry point is `Decomposer.decompose(reference_dir, project_id)`, the integration will fail. Pin the exact call signature and wrap in a try/except with a meaningful error. | Section 2 (Dependencies and Imports) — add concrete call signatures; Section 4 — add error handling in `run_eagle()` | Integration test against fixture validates the exact import path resolves and returns `ProjectMetadata` |
| R1-S4 | data | high | Add explicit JSON serializability enforcement throughout the transformation pipeline, not just as an integration test assertion. Convert `Path` objects to `str`, strip dataclass instances, and handle `None` vs missing keys consistently. | Risk is acknowledged only in integration tests (`test_output_is_json_serializable`), but the transformation code itself has no guards. `dataclasses.asdict()` on `ExtractedCapability` will include all fields; `Path` objects from ContextCore's `file_path` may survive as `PosixPath`. Enforce at transformation time, not just test time. | Inside `_transform_extract()` and `_transform_eagle()` — add `str(path)` coercion; add a `_sanitize_for_json()` utility | Unit test that asserts `json.dumps(output)` succeeds for every transformation function individually |
| R1-S5 | architecture | high | Introduce a `ContextBridgeConfig` dataclass to parameterize behavior (e.g., max services in summary, whether to include file-level detail, test coverage heuristic strategy) rather than hardcoding magic numbers like `15` services truncation and basename-matching logic. | Hardcoded thresholds (15 services, basename heuristic) make the bridge rigid. Different projects will need different summarization strategies. A config object also enables testing edge cases (truncation at 1, at 0) without monkey-patching. | New dataclass in `context_bridge.py`; passed to `__init__` with sensible defaults | Unit tests parameterized across config variations |
| R1-S6 | risks | high | Address the path prefix mismatch (Risk 5) with an explicit resolution algorithm and unit tests. The plan acknowledges the issue but provides no implementation detail for how Eagle service-relative paths get reconciled with ContextCore project-relative paths. | This is the highest-risk data correctness issue. If `by_file` uses project-relative paths but Eagle uses service-relative paths, cross-referencing in `codebase_summary` (e.g., counting functions per service) will silently produce wrong numbers. | New subsection "Path Normalization Strategy" in Section 4; dedicated helper `_normalize_path(eagle_service_name, eagle_file_path) → project_relative_path` | Unit tests with known path fixtures; integration test asserts Eagle files appear in `by_file` keys |
| R1-S7 | ops | medium | Add structured logging (not just `log.warning`) with timing for each phase (`run_eagle`, `run_extract`, transformations). Include the total wall-clock time in the returned context dict as `context["bridge_metadata"]["elapsed_seconds"]`. | The feature doc claims 3-8 seconds. Without instrumentation, there's no way to verify this in production or diagnose slowdowns. Metadata also enables downstream phases to skip re-running the bridge if context is fresh. | Add `bridge_metadata` key to output schema containing `elapsed_seconds`, `eagle_version`, `contextcore_version`, `generated_at` | Integration test asserts `bridge_metadata` exists and `elapsed_seconds > 0` |
| R1-S8 | validation | medium | Add a test for idempotency: calling `build_context()` twice on the same project root should produce identical output (minus timestamps). Also test that `context.update(merged)` doesn't corrupt pre-existing startd8-sdk keys. | The feature doc shows `context.update(merged)` in `ExplorePhaseHandler`. If the bridge accidentally includes keys like `workflow_id` or `project_root`, it will overwrite caller-provided values. The plan's `test_build_context_does_not_overwrite_existing` is listed but has no implementation detail. | Section 8 unit test plan — expand the overwrite test; add idempotency test | Two-call comparison test; test that pre-set `workflow_id` survives `context.update()` |
| R1-S9 | security | medium | Sanitize or truncate `dependency_manifest_contents` before it reaches the context dict. The field is explicitly dropped in the plan's transformation mapping, but if Eagle's schema changes to include it elsewhere, sensitive data (API keys in config files, private registry URLs) could leak into LLM prompts via `codebase_summary`. | Defense in depth: even though the plan drops the field, an allowlist approach (only copy explicitly listed fields) is safer than a denylist (copy everything, drop some). The current mapping implicitly uses an allowlist but doesn't enforce it programmatically. | In `_transform_eagle()` — use explicit field picking rather than `dataclasses.asdict()` with deletions | Unit test that adds an unexpected field to `ServiceMetadata` and asserts it does NOT appear in output |
| R1-S10 | architecture | medium | Define the caching/staleness strategy. If `build_context()` is called in `ExplorePhaseHandler` on every run, and the project hasn't changed, re-scanning is wasted work. Add an optional content-hash check (e.g., hash of file mtimes) to short-circuit when the project hasn't changed. | The feature doc positions this in a pipeline that may run repeatedly during development. Even at 3-8 seconds, unnecessary re-scans add up and create noise in logs. A simple mtime-based fingerprint enables caching without complexity. | New optional method `is_stale(cached_context) → bool` on `ContextBridge`; `build_context()` accepts optional `previous_context` | Unit test with mocked filesystem showing cache hit and cache miss scenarios |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — this is the first review round)

#### Feature Requirements Suggestions

| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Output Schema → `service_dependencies` | Ambiguity | The output schema uses keys `"from"` and `"to"` which are Python reserved words (`from`) and will cause issues if anyone tries to use `**kwargs` unpacking or dataclass field names. | Medium — forces awkward access patterns, potential bugs in downstream consumers | Consider renaming to `"source_service"` / `"target_service"`, or at minimum document that these must be accessed via `dep["from"]` bracket notation only |
| R1-F2 | Output Schema → `capability_map.by_file` | Missing Detail | The example shows `"src/auth.py"` as a key, but doesn't specify whether paths are relative to project root, absolute, or service-relative. Given the known Eagle/ContextCore path mismatch (Risk 5), this is critical to pin down. | High — path format determines whether cross-referencing works at all | Explicitly state: "All paths in `by_file` keys are relative to `project_root`" |
| R1-F3 | Output Schema → `test_coverage_map` | Ambiguity | The spec shows `"src/auth.py": ["test_login", "test_logout"]` — are these test function names or fully qualified `file::function` identifiers? The plan's heuristic appends `test.name` but `ExtractedCapability.name` could be just the function name or include the file. | Medium — downstream consumers need to know whether they can locate tests from the map alone | Specify format as `"file_path::test_name"` or just `"test_name"` and state which |
| R1-F4 | Input Schema → `ExtractionResult` | Missing Detail | `ExtractionResult.tests` entries have `file_path` pointing to the test file, but the spec doesn't clarify how the heuristic should handle test files that aren't in a parallel `tests/` directory (e.g., inline tests, `conftest.py`, or `test_*.py` co-located with source). | Medium — heuristic may produce empty or incorrect coverage maps for non-standard layouts | Add examples of expected behavior for co-located tests and conftest files |
| R1-F5 | Design Decisions → codebase_summary | Missing Detail | The summary is described as "concise markdown" but there's no token budget or size constraint specified. For large projects (50+ services, 1000+ capabilities), the summary could exceed prompt context windows or waste tokens. | Medium — defeats the stated purpose of "saves tokens vs passing raw JSON" | Specify a target token range (e.g., 200-500 tokens) and truncation strategy |
| R1-F6 | Limitations | Missing Constraint | The doc acknowledges "ContextCore extract is Python-only" but doesn't specify what happens to non-Python files in `capability_map`. Are they absent from `by_file`? Present with empty capability lists? This affects whether downstream consumers can distinguish "no capabilities extracted" from "file not analyzed." | Medium — silent absence vs explicit emptiness changes downstream logic | Specify: non-Python files appear in `by_file` only if Eagle reports them, with an empty capability dict and a `"language": "unsupported"` marker |
| R1-F7 | Integration Points → With startd8-sdk | Conflict | The feature doc shows `context.update(merged)` which is a shallow merge. If startd8-sdk's existing context has a `"project_structure"` key from a prior run or another source, it will be silently overwritten. The doc doesn't address merge semantics for repeated calls. | Medium — data loss on re-runs or if another component populates the same keys | Specify whether bridge output should overwrite, deep-merge, or raise on conflict |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Run Eagle against project root → ProjectMetadata | Phase 2 (steps 4-6), Section 4 (Eagle transformation) | Partial | Exact Eagle API call signature unverified (R1-S3); no error handling spec for Eagle failures |
| Run ContextCore extract → ExtractionResult | Phase 3 (step 8), Risk 3 | Full | Correctly identifies `extract_all()` vs `run_extraction()` distinction |
| Merge into context dict compatible with startd8-sdk | Phase 5 (step 15), Section 4 | Partial | No output schema validation (R1-S1); no merge-conflict semantics with existing context (R1-F7) |
| No LLM cost (purely deterministic) | Overview, all phases | Full | Clearly maintained throughout |
| Output: `project_structure` | Section 4 (Eagle mapping) | Full | Field-level mapping is thorough with explicit DROP annotations |
| Output: `capability_map.by_file` | Section 5 | Partial | Path format unspecified (R1-F2); path normalization unimplemented (R1-S6) |
| Output: `capability_map.by_type` | Phase 3 (steps 9), Section 4 | Full | All 6 types covered |
| Output: `capability_map.test_coverage_map` | Section 6 | Partial | Heuristic specified but fragile (Risk 6); output format ambiguous (R1-F3) |
| Output: `codebase_summary` | Section 7, Phase 4 | Partial | No token budget (R1-F5); cross-reference path logic acknowledged but not implemented (Risk 5/R1-S6) |
| Library import for Eagle (recommended) | Section 2 | Partial | No fallback subprocess path implemented despite feature doc recommending one |
| Library import for ContextCore | Section 2 | Full | Correctly identified as existing dependency |
| Integration with ExplorePhaseHandler | Not in plan scope | None | Plan stops at `build_context()` return; no implementation of the `ExplorePhaseHandler.execute()` integration shown. Acceptable if out of scope, but should be stated explicitly. |
| Limitation: Python-only extraction | Risk noted in feature doc | Partial | Plan doesn't specify behavior for non-Python files in capability_map (R1-F6) |
| Limitation: Eagle expects service-per-directory | Risk 2 | Partial | Fallback behavior underspecified (R1-S2) |
| Estimated effort ~1 day | Phase 1-6 timing | Full | Phase timings sum to ~6 hours, consistent with estimate |

#### Review Round R2
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 00:49:10 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Data | Critical | Normalize file paths between Eagle and ContextCore | Eagle paths are relative to service roots; ContextCore paths are relative to project root. Without normalization (prepending service paths to Eagle files or stripping prefixes from ContextCore), the `by_file` index will not align with the `project_structure`, breaking the agent's ability to look up file details. | Section 4 (Data Transformation Logic) | Create a test case with a nested service directory structure and verify path keys match in the final output. |
| R2-S2 | Resilience | High | Implement partial failure handling (Circuit Breaker) | If Eagle fails (e.g., parsing error) but ContextCore succeeds (or vice versa), the bridge should return partial context rather than crashing. The LLM can often function with partial data, but not with zero data. | Section 3, Phase 5 (Orchestration) | Unit test where one runner raises an exception and the output dict still contains the other tool's data + error flags. |
| R2-S3 | Data | High | Implement explicit JSON-safe serialization | `dataclasses.asdict` does not recursively convert `pathlib.Path` objects to strings. Downstream JSON serialization in startd8-sdk will crash. The bridge must recursively walk the final dict and stringify non-primitive types. | Section 5 (Orchestration) | Integration test: `json.dumps(bridge.build_context())` must succeed. |
| R2-S4 | Validation | Medium | Add Pydantic Output Model | Rather than returning a raw `dict`, define a Pydantic model matching the Output Schema. This enforces the contract, validates types at runtime, and prevents silent schema drift. | Section 1 (Files to Create) & Section 4 | Define `ContextSchema` model and call `ContextSchema(**data).model_dump()` at the end of `build_context`. |
| R2-S5 | Ops | Medium | Robust Eagle Import Strategy | Relying on Eagle being "installable" or having a `pyproject.toml` created externally is risky. Add logic to check `EAGLE_HOME` env var and append to `sys.path` dynamically if standard import fails. | Section 3, Phase 2 (Eagle Transformation) | Test in an environment where Eagle is not installed via pip but present in a mock directory. |
| R2-S6 | Data | Low | Enhanced Test Mapping Heuristics | The `test_` prefix heuristic is Python-specific. Eagle detects other languages. Enhance mapping to support `_test` suffixes (Go) and `Spec` suffixes (JS/Ruby) to maximize utility of `test_coverage_map`. | Section 6 (test_coverage_map) | Unit test with `auth_test.go` and `user_spec.rb` filenames. |

#### Feature Requirements Suggestions
| ID | Issue | Description |
|---|---|---|
| R2-F1 | Ambiguity | The Output Schema requires `evidence` in `service_dependencies`. The Input Schema for Eagle's `ServiceDependency` does not explicitly list an `evidence` field (it lists `protocol`). Clarify if `evidence` should be derived (e.g., "Inferred from gRPC import") or if the Input Schema definition was incomplete. |
| R2-F2 | Missing Requirement | The Requirements do not specify behavior for "Hybrid" paths where a file exists in ContextCore (e.g., a script in root) but belongs to no Eagle service. Clarify if these should be added to a "misc" service entry or left as orphans in `capability_map` only. |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
|---|---|---|---|
| **Goal**: Merge Eagle + Extract | Steps 15, 16 | Full | |
| **Goal**: No LLM Cost | Overview | Full | |
| **Schema**: ProjectMetadata Input | Step 6 | Full | |
| **Schema**: ExtractionResult Input | Step 9 | Full | |
| **Schema**: Output Structure | Steps 6, 9, 15 | Partial | Path normalization logic missing (R2-S1). Serialization logic missing (R2-S3). |
| **Design**: by_file index | Step 10 | Full | |
| **Design**: test_coverage_map | Step 11 | Partial | Heuristic is Python-centric (R2-S6). |
| **Design**: codebase_summary | Step 13 | Full | |
| **Integration**: ExplorePhaseHandler | Step 15 | Full | |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 00:51:20 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | architecture | critical | Add a formal interface (Protocol/ABC) for the data source adapters (Eagle, ContextCore) behind `run_eagle()` and `run_extract()`, enabling substitution, testing, and future non-Python extractors | The plan hard-codes two concrete integrations inside `ContextBridge`. If Eagle's import path changes, ContextCore is replaced, or a non-Python extractor is added (acknowledged limitation), the bridge core must be modified. Defining `SourceAdapter` protocols with `extract() → dict` contracts decouples transformation logic from extraction mechanics, simplifies unit testing (no mocking internals), and provides an extension point for the acknowledged Python-only gap without touching bridge code. | New subsection after Section 2 ("Adapter Interfaces") defining `MacroStructureAdapter` and `MicroCapabilityAdapter` protocols; update Section 3 Phase 2/3 to implement concrete adapters | Verify that unit tests for `_transform_eagle` and `_transform_extract` never import Eagle or ContextCore directly; integration tests confirm concrete adapters conform to protocol |
| R3-S2 | architecture | high | Introduce a `ContextBridgeResult` Pydantic model (or TypedDict) that formally types the entire output dict, making Risk 8 actionable rather than aspirational | Risk 8 identifies the lack of output schema validation but defers it as optional. After R1/R2 applied suggestions tightened field semantics (paths, test identifiers, evidence), there are now enough constraints that a schema is necessary to enforce them. Without it, downstream startd8-sdk phases silently receive malformed dicts. The model also serves as the canonical interface contract for consumers. | New Section 4b ("Output Schema Model") between Sections 4 and 5; `build_context()` returns `ContextBridgeResult.model_dump()` after validation; add schema round-trip tests to Section 8 | Add test `test_build_context_output_validates_against_schema` that constructs output and passes it through the Pydantic model; CI fails on any field mismatch |
| R3-S3 | interfaces | high | Define explicit error types and a `BridgeResult` envelope that carries partial results plus structured diagnostics when one source fails | The plan says "if zero services, log warning and continue" (Risk 2) but doesn't define what `build_context()` returns when Eagle fails, ContextCore fails, or both fail. Callers (ExplorePhaseHandler) have no contract for partial-success scenarios. Define `BridgeResult(context: dict, diagnostics: list[Diagnostic], sources_succeeded: set[str])` so downstream can decide whether to proceed or abort. | New subsection in Section 4 ("Error Handling Contract"); update `build_context()` signature; update integration test plan (Section 9) with failure-mode tests | Add tests: `test_build_context_eagle_failure_returns_partial`, `test_build_context_extract_failure_returns_partial`, `test_build_context_both_fail_returns_empty_with_diagnostics` |
| R3-S4 | interfaces | high | Specify the `context.update(merged)` contract as a versioned schema with a namespace prefix or manifest key, preventing silent overwrites and enabling forward-compatible schema evolution | R1-F7 flagged shallow-merge collision risk (applied as R1-S3), but the plan still uses `context.update(merged)`. There's no mechanism for downstream consumers to know which bridge version produced the data, or to handle schema changes across bridge versions. Add `"_bridge_meta": {"version": "1.0", "generated_at": str, "sources": [...]}` and document that the three top-level keys (`project_structure`, `capability_map`, `codebase_summary`) are the bridge's namespace — no other component should write to them. | Add to Output Schema section and Section 7 (build_context); document in Integration Points section | Test that `_bridge_meta` is always present and that `build_context()` raises if target context already contains bridge keys (unless `force=True` kwarg) |
| R3-S5 | ops | high | Add structured logging with timing instrumentation for each extraction and transformation phase, and define a health-check / diagnostic CLI command | The plan estimates "3-8 seconds" but provides no observability. In production, operators need to know: did Eagle hang? Did ContextCore crash silently? Which phase is slow? Add `structlog` or stdlib `logging` with phase timers, and a `context-bridge diagnose <path>` CLI that runs both extractors and reports timing, file counts, and any warnings — critical for debugging in CI/CD where the bridge runs unattended. | New Section 10b ("Observability"); add timing context manager in `build_context()`; add CLI entry point in `pyproject.toml` | Integration test asserts log entries contain `eagle_extraction_ms`, `contextcore_extraction_ms`, `total_ms`; diagnose CLI returns 0 on healthy fixture |
| R3-S6 | ops | high | Define idempotency and caching semantics — repeated `build_context()` calls on unchanged source should be fast-path cacheable | The bridge is called in ExplorePhaseHandler, but nothing prevents it from being called multiple times (retry, re-run, multi-phase). Each call re-scans the entire project (3-8s). Define a content-hash-based cache: hash the project file tree → if unchanged, return cached result. Store cache in `{project_root}/.context_bridge_cache.json` with the tree hash as key. Also ensures idempotency: same input always produces same output. | New Section 10c ("Caching and Idempotency"); add `_compute_tree_hash()` method; add cache hit/miss to structured logs | Test `test_build_context_cached_on_unchanged_tree` runs twice, second call skips extraction; `test_cache_invalidated_on_file_change` modifies a file, verifies re-extraction |
| R3-S7 | risks | high | Add Risk 9: Large monorepo performance — Eagle's `RepoScanner` and ContextCore's AST parser may time out or OOM on repos with >10K files or >500K LOC | The plan targets "3-8 seconds" but this is only validated against a small fixture. For large repos (common in enterprise), Eagle walks every file and ContextCore parses every .py file. Neither has pagination or streaming. Add a configurable `max_files` / `max_loc` threshold with early termination and a warning diagnostic. Without this, the bridge becomes the bottleneck in the Artisan pipeline for exactly the projects that need it most. | Add Risk 9 to Section 10; implement `max_files` parameter in `ContextBridge.__init__()` with default 10,000; add truncation note to `_bridge_meta` | Test with a generated fixture of 15,000 stub files; verify bridge completes within 30s and output contains truncation warning |
| R3-S8 | security | high | Sanitize and validate all file paths from Eagle and ContextCore to prevent path traversal artifacts and ensure no absolute paths or `..` segments leak into the output context | Both Eagle and ContextCore return file paths that are user-controlled (derived from the filesystem). If a repo contains symlinks, `..` segments, or absolute paths, these propagate into `by_file` keys and `project_structure.files`, which downstream LLM prompts may use to read/write files. Add path normalization (`Path.resolve().relative_to(project_root)`) and reject any path that escapes `project_root`. This is especially important since the context dict feeds into an agent that has tool-use capabilities. | Add Section 10d ("Path Sanitization"); add `_sanitize_path()` called in both `_transform_eagle()` and `_build_by_file_index()`; add to unit test plan | Test `test_path_traversal_rejected` with `../../etc/passwd` in file list; `test_absolute_path_normalized`; `test_symlink_resolved` |
| R3-S9 | security | high | Add input validation and size limits on Eagle/ContextCore outputs before transformation to prevent resource exhaustion from malformed or adversarial inputs | The bridge blindly trusts the structure and size of `ProjectMetadata` and `ExtractionResult`. A malformed Eagle output (e.g., a service with 10M files, or circular service dependencies) could cause the transformation to consume unbounded memory or time. Validate: max services count, max files per service, max capabilities per file, no duplicate service names, and that all required fields are present before transformation begins. | New subsection in Section 4 ("Input Validation Gates"); implement `_validate_eagle_output()` and `_validate_extract_output()` called at start of respective transform methods | Test `test_validate_rejects_oversized_service`, `test_validate_rejects_missing_required_fields`, `test_validate_rejects_duplicate_service_names` |
| R3-S10 | validation | high | Add contract tests that pin the output schema against a golden snapshot, and add a compatibility test that feeds bridge output into a mock startd8-sdk ExplorePhaseHandler to verify the consumer accepts it | The current test plan validates internal correctness but never validates that the output actually works with the consumer. Since startd8-sdk is the sole consumer and its phase handlers access specific keys (e.g., `context["project_structure"]["services"]`), a contract test should import the real `ExplorePhaseHandler` (or a minimal stub) and call it with bridge output. This catches interface drift that neither unit nor integration tests would catch in isolation. | Add Section 8b ("Contract Tests") with golden-file snapshot test and consumer-compatibility test; add to CI as a separate test target | `test_output_matches_golden_snapshot` diffs against checked-in JSON; `test_explore_phase_handler_accepts_bridge_output` calls handler with real bridge output and asserts no KeyError/TypeError |

#### Feature Requirements Suggestions

| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Architecture → ContextBridge | Missing Detail | The architecture diagram shows `build_context() → dict[str, Any]` but doesn't specify thread-safety or reentrancy semantics. If multiple Artisan pipelines share a process (e.g., in a web server or test runner), concurrent `build_context()` calls on different project roots could interfere via shared state (e.g., if Eagle or ContextCore use module-level globals). | Medium — concurrency bugs in CI or server deployments | State explicitly that `ContextBridge` instances are not thread-safe, or make them so by ensuring no shared mutable state; document single-threaded usage expectation |
| R3-F2 | Output Schema → `capability_map.by_type` | Ambiguity | `by_type` values are described as `[ExtractedCapability.to_dict()]` but `ExtractedCapability` has no `to_dict()` method defined in the input schema. The plan uses `vars()` in Section 4, which includes all fields including `None` values. Clarify whether `None` fields should be omitted or included as `null` in the output. | Low — affects downstream JSON size and consumer null-handling | Specify: use `vars()` with `None` values retained (consistent with JSON conventions), or explicitly filter them |
| R3-F3 | Design Decisions → test_coverage_map | Missing Detail | The design decision section doesn't specify what happens when ContextCore finds zero tests. Is `test_coverage_map` an empty dict `{}`? Is it omitted from the output? The plan's Section 6 implies it's always present but doesn't state this explicitly. | Low — downstream consumers need to know whether to check for key existence or empty dict | State: `test_coverage_map` is always present; if no tests found, it is `{}` |
| R3-F4 | Integration Points → With startd8-sdk | Missing Detail | The integration example shows the bridge called inside `ExplorePhaseHandler.execute()`, but doesn't specify whether the bridge should be instantiated once per pipeline run or once per phase. If multiple phases need bridge data and the phase handler is re-instantiated, the bridge runs redundantly. | Medium — performance impact on multi-phase pipelines | Clarify: bridge should run once in Explore phase and its output persists in `context` dict for all subsequent phases. Document this lifecycle expectation. |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
|---|---|---|---|
| Problem Statement | Section 1 (Overview) | Full | — |
| Goal: Run Eagle | Section 3 Phase 2, Step 5 (`run_eagle`) | Full | — |
| Goal: Run ContextCore | Section 3 Phase 3, Step 8 (`run_extract`) | Full | — |
| Goal: Merge into context dict | Section 3 Phase 5, Step 15 (`build_context`) | Partial | No error handling contract for partial failures; no schema validation on output |
| Goal: No LLM cost | Section 1 (Overview), Section 10 Risk 3 | Full | — |
| Input Schema: ProjectMetadata | Section 4 (Eagle transformation mapping) | Full | — |
| Input Schema: ExtractionResult | Section 4 (ContextCore transformation mapping) | Full | — |
| Output Schema: project_structure | Section 4 (field mapping) | Full | — |
| Output Schema: capability_map.by_file | Section 5 (by_file construction) | Partial | Path format (relative to what?) addressed by R1-F2 if applied; no path sanitization |
| Output Schema: capability_map.by_type | Section 4 (ContextCore mapping) | Partial | `to_dict()` method undefined; `vars()` behavior with None values unspecified |
| Output Schema: capability_map.test_coverage_map | Section 6 (heuristic) | Partial | Empty-test-suite behavior unspecified; test identifier format partially addressed |
| Output Schema: codebase_summary | Section 7 (rendering) | Partial | No explicit token budget or truncation threshold for very large projects (R1-F5) |
| Design Decision 1: by_file | Section 5 | Full | — |
| Design Decision 2: test_coverage_map | Section 6 | Full | Known limitations documented |
| Design Decision 3: codebase_summary | Section 7 | Partial | Missing size constraints |
| Design Decision 4: Deterministic | Throughout | Full | — |
| Integration: Eagle (library import + fallback) | Section 2, Section 3 Phase 2 | Partial | Fallback subprocess path mentioned in feature doc but absent from plan |
| Integration: ContextCore (library import) | Section 2, Section 3 Phase 3 | Full | — |
| Integration: startd8-sdk (ExplorePhaseHandler) | Not in plan scope | Partial | Plan shows consumer code snippet but no contract test validates compatibility |
| Limitation: Python-only ContextCore | Section 10 Risk 2 (tangential) | Partial | Feature doc limitation about empty capability maps for non-Python files not addressed in plan output schema |
| Limitation: Eagle expects service-per-dir | Section 10 Risk 2 | Full | — |
| Limitation: No semantic analysis | Not explicitly in plan | None | Could add a note that `codebase_summary` should not claim semantic understanding |
| Estimated Effort: ~1 day | Section 3 (phases sum to ~5 hours) | Full | — |
| Dependencies: eagle, contextcore | Section 2 | Full | — |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F2: Path format is foundational — without pinning "relative to project_root", cross-referencing between Eagle and ContextCore data is undefined, and my R3-S8 (path sanitization) depends on this being resolved first.
- R1-F5: Token budget for codebase_summary is important for large projects — directly relates to my R3-S7 (large monorepo risk) and prevents the summary from defeating its own purpose.
- R2-F1: The `evidence` field provenance needs clarification — the plan maps `ServiceDependency.evidence → dep["evidence"]` but if Eagle's input schema doesn't actually have this field, the transform will KeyError at runtime.
- R2-F2: Orphan files (in ContextCore but not in any Eagle service) are a real gap — the by_file index will contain keys that have no corresponding service in project_structure, confusing downstream consumers.

#### Review Round R4

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 00:53:04 UTC
- **Scope**: Architecture-focused review

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Input Schema (Eagle) vs Output Schema | Conflict | The Output Schema requires `service_dependencies[].evidence`, and the Plan maps it from `ServiceDependency.evidence`. However, the Input Schema for `ServiceDependency` does **not** list an `evidence` field. | High — Implementation will fail `AttributeError` or require hallucinating data. | Update Input Schema to include `evidence` or remove it from Output Schema requirements. |
| R4-F2 | Output Schema (Capability Map) | Missing Constraint | The `docstring` field in `capability_map` has no length constraint. Large docstrings (or license headers mistakenly parsed as docstrings) will bloat the context dictionary, consuming tokens even if not in the summary. | Medium — Token waste in downstream phases. | Add requirement: "Docstrings in `capability_map` must be truncated to 500 characters." |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps / Notes |
| :--- | :--- | :--- | :--- |
| **Goal**: Merge Eagle + ContextCore | Steps 15, 16 | Full | |
| **Input**: Eagle `ProjectMetadata` | Steps 4, 5, 6 | **Partial** | Plan assumes `evidence` field exists in Input (see R4-F1). |
| **Input**: ContextCore `ExtractionResult` | Steps 8, 9 | Full | |
| **Output**: `project_structure` | Step 6 | Full | Handles renaming of keys per design. |
| **Output**: `capability_map` | Step 9 | Full | |
| **Output**: `by_file` index | Step 10 | Full | |
| **Output**: `test_coverage_map` | Step 11 | Full | Implements heuristic mapping. |
| **Output**: `codebase_summary` | Step 13 | Full | |
| **Constraint**: No LLM Cost | All Steps | Full | Purely deterministic logic used. |

#### Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | architecture | Critical | Implement "Partial Success" strategy | If Eagle fails (e.g., parse error) but Extract succeeds, or vice versa, the bridge must not crash the whole phase. It should return whatever data it managed to collect and flag errors in a `_meta` key. | `build_context` orchestration logic | Test case simulating Eagle exception; verify `capability_map` still populates. |
| R4-S2 | architecture | High | Abstract the Execution Strategy (Lib vs Subprocess) | Risk 1 (Eagle installability) is high. Hardcoding the library import in `run_eagle` makes the bridge fragile. Define an `Executor` interface with `LibraryExecutor` and `SubprocessExecutor` implementations. | `src/hybrid_scaffold/executors.py` | Integration test forcing `SubprocessExecutor` usage. |
| R4-S3 | security | High | Enforce Path Sanitization | `project_root` is external input. Output paths must be validated to be strictly within `project_root` to prevent path traversal or absolute path confusion in the LLM context. | `_transform_eagle` and `_transform_extract` | Unit test with `../../` paths in mock input data. |
| R4-S4 | security | Medium | Truncate Docstrings in Output | Docstrings are user content and can be arbitrarily large. Storing full text in the JSON context (even if not in summary) wastes memory and tokens if the full JSON is ever serialized to prompt. | `_transform_extract` | Unit test with 10KB docstring verifying truncation. |
| R4-S5 | interfaces | High | Formalize Output with Pydantic | The plan mentions Risk 8 (no validation). Returning a raw `dict` is risky for a core SDK contract. Define a Pydantic model for the Output Schema and use `.model_dump()` to generate the dict. | `src/hybrid_scaffold/schema.py` | Verify output passes `OutputModel.model_validate()`. |
| R4-S6 | interfaces | Low | Inject Logger Instance | The bridge runs inside a larger SDK. It should accept a `logger` in `__init__` to ensure warnings (like "Zero services found") adhere to the parent application's logging configuration. | `ContextBridge.__init__` | Mock logger and verify calls in unit tests. |
| R4-S7 | ops | Medium | Add Execution Timeouts | Parsing large repos can hang. Wrap `run_eagle` and `run_extract` calls with a strict timeout (e.g., 30s) to prevent the `ExplorePhase` from blocking indefinitely. | `run_eagle` / `run_extract` | Test case with a mocked sleeper function. |
| R4-S8 | ops | Medium | Include Extractor Versions in Output | Add `meta: { eagle_version: str, contextcore_version: str }` to the output. Essential for debugging why extraction quality varies across runs or environments. | `build_context` | Check for version keys in output dict. |
| R4-S9 | validation | High | Add Token Budget Test for Summary | The `codebase_summary` is text. We need a test that generates a summary for a massive synthetic project (100 services) and asserts it stays within a safe token limit (e.g., <1000 tokens). | `tests/test_context_bridge.py` | Generate huge mock metadata, check summary length. |
| R4-S10 | risks | Medium | Runtime Input Schema Check | Eagle/ContextCore are external deps. If they update their return objects, the bridge might silently fail or produce garbage. Add runtime `isinstance` or attribute checks on the inputs before processing. | Start of `_transform_*` methods | Test with malformed input objects raising specific errors. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- **R1-F1**: Renaming `from`/`to` is critical to avoid syntax errors in Python consumers.
- **R1-F7**: Defining merge semantics is essential; silent overwrites cause hard-to-debug data loss.
- **R2-F1**: Confirms the gap identified in R4-F1 regarding the missing `evidence` field.

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 00:56:32 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | architecture | high | Add explicit error handling and partial-success semantics for `build_context()` when one upstream tool fails but the other succeeds | The plan's Risk 2 says "if zero services, log warning and continue with ContextCore data only," but there's no symmetric handling: if ContextCore extraction fails (e.g., corrupted AST, permission error), the plan has no strategy. With R3-S1 (thread-safety) and R4-S1 (evidence field fix) both applied, the happy path is solid — but the partial-failure path is undefined. Should `project_structure` be present with `capability_map` absent? Should there be a top-level `"bridge_warnings": list[str]` key so downstream phases know which data is missing? | Section 10 (Risks) — add Risk 9; Section 4 — define partial output shapes; Section 8 — add `test_build_context_eagle_fails` and `test_build_context_extract_fails` | Integration test: kill ContextCore import, verify bridge returns valid partial context with warnings; unit test: mock `run_extract()` to raise, assert `capability_map` is absent but `project_structure` present |
| R5-S2 | data | high | Specify idempotency contract for `build_context()` — repeated calls on the same project root must produce byte-identical output (excluding timestamps) | R3-S1 applied thread-safety concerns, and R1-S7 addressed merge semantics, but neither guarantees determinism across runs. Python `dict` ordering is insertion-ordered since 3.7, but `defaultdict` iteration during `_build_by_file_index()` depends on capability insertion order, which depends on ContextCore's AST walk order. If ContextCore changes file traversal order (e.g., switching from `os.walk` to `pathlib.glob`), the output changes silently, breaking snapshot tests and cache invalidation downstream. | Section 5 (by_file Index) — add explicit sort: `sorted(by_file.keys())` and sort capabilities within each file by `line_number`; Section 8 — add `test_by_file_deterministic_ordering` | Run `build_context()` twice on same fixture, `assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)`; also shuffle input capability list and verify output is identical |
| R5-S3 | interfaces | medium | Define the contract for `capability_map.by_file` keys when Eagle reports files that ContextCore didn't analyze (non-Python files) and vice versa | R1-S3 (applied) addressed path format and R1-S6 (applied) addressed non-Python file markers, but their interaction creates an unstated gap: Eagle's `service.files` may list `go.mod`, `Dockerfile`, `*.proto` files. ContextCore will never extract capabilities from these. The plan doesn't specify whether `by_file` should contain entries for these files (with empty capability lists + the `"language": "unsupported"` marker from R1-S6) or only files ContextCore actually processed. Conversely, ContextCore may find capabilities in files Eagle didn't list (e.g., scripts in project root outside any service dir — the "orphan files" from R2-F2). | Section 5 — add explicit rule: `by_file` contains the **union** of Eagle file paths and ContextCore file paths; Eagle-only files get empty capability lists; ContextCore-only files get a `"service": null` marker | Unit test: fixture with a `.proto` file in Eagle output and a root-level script in ContextCore output; verify both appear in `by_file` with correct markers |
| R5-S4 | risks | high | Address memory footprint for large monorepos — the plan has no size-awareness for the in-memory context dict | R4-F2 (applied) added docstring truncation at 500 chars, but the aggregate risk remains unaddressed. A monorepo with 500 files × 50 capabilities/file = 25,000 capability entries in `by_file` and `by_type`. Each entry carries `name`, `line`, `signature`, `docstring` (500 chars). Rough estimate: 25K × ~600 bytes = ~15MB in the context dict. This dict is passed through every phase handler, potentially serialized to JSON for logging (R1-S7 applied logging), and may be held in memory for the entire pipeline lifetime. For a 100-service monorepo, this could reach 50-100MB. | Section 10 — add Risk 9 (Memory); Section 7 — specify that `codebase_summary` truncation (from R1-S5... wait, R1-S5 was rejected). Instead: add a `max_capabilities_per_file` config param (default 100) that truncates `by_file` entries with a count annotation `"truncated": true, "total_in_file": 250` | Unit test: generate synthetic ExtractionResult with 10K capabilities, measure output dict size, assert < threshold; add `test_by_file_truncation_with_annotation` |
| R5-S5 | security | medium | Sanitize `file_path` values from ContextCore before using them as dict keys in `by_file` | R3-S8 and R3-S9 (both applied) addressed security concerns, but neither covers path traversal in capability data. `ExtractedCapability.file_path` comes from ContextCore's AST parsing which uses `os.path.relpath()`. If a symlink or malicious repo contains paths like `../../etc/passwd`, these become `by_file` keys and are passed to downstream phases that may use them for file I/O. The bridge should validate that all file paths are within `project_root`. | Section 5 — after grouping by file_path, add validation: `assert not os.path.isabs(path) and '..' not in Path(path).parts`; reject or log paths that escape project root | Unit test: inject a capability with `file_path="../../etc/passwd"`, verify it's excluded from `by_file` and logged as a warning |
| R5-S6 | validation | medium | Add schema contract test that validates the output dict against the documented Output Schema from the feature requirements | R1-S8 (applied) added validation tests and Risk 8 mentions "consider adding Pydantic model (~30 min)." But 26 suggestions later, no one has made this concrete. The output schema in the feature doc is the contract with startd8-sdk. Without a machine-readable schema check, any refactoring of the transformation logic could silently break the contract. This is distinct from the unit tests (which test individual transformations) — this is an end-to-end structural assertion. | Section 9 (Integration Tests) — add `test_output_matches_documented_schema` that validates required keys, types, and nesting depth against a JSON Schema derived from the feature doc; Section 2 — add `jsonschema` as test dependency | Create `tests/fixtures/output_schema.json` matching the feature doc's Output Schema; integration test runs `build_context()` and validates against it using `jsonschema.validate()` |
| R5-S7 | ops | medium | Define behavior when Eagle and ContextCore report conflicting metadata for the same project (e.g., different project names, different file counts) | R2-S1 (applied) addressed the `evidence` field mismatch, but there's a broader class of conflicts: Eagle's `ProjectMetadata.project_id` vs ContextCore's `ExtractionResult.project_name` may differ (Eagle uses directory name by default; ContextCore uses `pyproject.toml` name). The plan puts both in the output (`project_structure.project_id` and `capability_map.project_name`) but downstream consumers may assume these are consistent. Similarly, Eagle's file list and ContextCore's file list may disagree on which files exist (e.g., gitignored files, build artifacts). | Section 4 — add a `_validate_consistency()` step after both transforms complete; log warnings for: mismatched project names, files in ContextCore not in any Eagle service, significant LOC discrepancies; add `"consistency_warnings": list[str]` to output | Unit test: construct Eagle output with `project_id="my-project"` and ContextCore output with `project_name="my_project"`, verify warning is emitted and both values preserved |
| R5-S8 | architecture | medium | Specify the bridge's behavior when `project_root` contains no analyzable content (empty directory, binary-only project, or single README) | Risk 2 covers "zero services from Eagle" but not the degenerate case where *both* tools return empty results. With R4-S1 and other fixes applied, the happy path and partial-failure paths are covered, but the "nothing found" path isn't: `project_structure` would have `total_services: 0, total_loc: 0`, `capability_map` would have `total_capabilities: 0`, and `codebase_summary` would read "Project: 0 services, 0 languages, 0 total LOC." This is technically valid but may cause downstream phases to error or produce nonsensical LLM prompts. | Section 10 — document as known behavior; `build_context()` should add `"bridge_warnings": ["No services or capabilities detected"]` and set a `"bridge_status": "empty"` flag; downstream ExplorePhaseHandler should check this and skip or error gracefully | Integration test: run against empty temp directory; verify output is valid, contains warning, and `bridge_status` is `"empty"` |
| R5-S9 | data | medium | The `codebase_summary` cross-join between Eagle services and ContextCore capabilities requires the path-prefix logic from Section 7 to be correct, but no test validates the join itself | Section 7 notes "Must prepend service name when cross-referencing" (the path prefix mismatch from Risk 5). R1-S3 (applied) standardized path format, but the *join logic* that counts "12 functions" per service in the summary requires matching ContextCore's `file_path` (e.g., `service_a/main.py`) against Eagle's service-relative paths (e.g., `main.py` under service `service_a`). If Eagle reports a service named `emailservice` but the directory is `email-service` (hyphen vs no hyphen), the join silently produces zero capability counts for that service. | Section 8 — add `test_summary_service_capability_counts_correct` that verifies function/class counts per service match expected values; Section 7 — add explicit join algorithm documentation with normalization step | Unit test: Eagle service named `email-service` with files `["main.py", "utils.py"]`; ContextCore capabilities with paths `["email-service/main.py", "email-service/utils.py"]`; verify summary line shows correct counts. Add edge case: service name with special characters |
| R5-S10 | interfaces | medium | Define serialization format for the context dict when it crosses process boundaries (e.g., logged to disk per R1-S7, cached between pipeline runs) | R1-S7 (applied) added structured logging and R4-S7/R4-S8 (applied) addressed ops concerns. But the context dict contains Python-specific types that don't round-trip through JSON: `Path` objects (from `project_root`), potential `None` vs missing key ambiguity, and the `set` type if any deduplication (e.g., `languages`) uses sets internally. The integration test `test_output_is_json_serializable` catches `json.dumps()` failures but not round-trip fidelity: `json.loads(json.dumps(ctx))` may silently change types (e.g., tuple → list). | Section 9 — strengthen `test_output_is_json_serializable` to `test_output_json_round_trips_losslessly`: verify `json.loads(json.dumps(output))` equals original output; Section 4 — explicitly cast all `Path` to `str` and all `set` to `sorted(list(...))` in transformation logic | Unit test: build context, round-trip through JSON, deep-compare; also test YAML round-trip if downstream phases use YAML serialization |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: The `"from"` key being a Python reserved word is a genuine usability hazard that will cause real bugs in downstream code using attribute-style access or dataclass unpacking; renaming to `"source_service"/"target_service"` is low-cost and high-value.
- R2-F2: The "orphan files" case (ContextCore finds capabilities in files outside any Eagle service) is a real gap that R5-S3 above partially addresses but R2-F2 frames more precisely from the requirements perspective.
- R1-F3: Test coverage map entry format (`file_path::test_name` vs bare `test_name`) remains ambiguous and affects downstream consumers' ability to locate test files — this is still unresolved in the plan.
- R1-F4: The handling of co-located tests (e.g., `test_*.py` alongside source) directly impacts the heuristic in Section 6 and is not covered by any accepted suggestion.
- R4-F1: The `evidence` field mismatch between Input Schema and Output Schema is a hard blocker — if not resolved, the implementation will fail at runtime.

#### Feature Requirements Suggestions

| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Output Schema → `capability_map.by_file` | Missing Constraint | The schema shows `by_file` keyed by file path with `classes`, `functions`, `api_endpoints` as sub-keys, but doesn't specify whether empty sub-keys should be present. E.g., if `src/utils.py` has functions but no classes, should the output be `{"functions": [...]}` (omit empty) or `{"classes": [], "functions": [...]}` (always present)? This affects downstream code that uses `ctx["capability_map"]["by_file"]["src/utils.py"]["classes"]` — KeyError vs empty list. | Medium — downstream consumers need consistent key presence contract | Specify: all category keys (`classes`, `functions`, `api_endpoints`, `cli_commands`) are always present in each `by_file` entry, defaulting to `[]` |
| R5-F2 | Output Schema → `codebase_summary` | Missing Constraint | The feature doc says the summary is "a concise markdown summary" and provides an example format, but doesn't specify whether it's a stable format that downstream phases can parse, or a human-readable string that may change between versions. If any downstream phase regex-parses the summary (e.g., to extract service count), format changes become breaking. | Medium — unclear contract stability | Clarify: `codebase_summary` is for LLM prompt injection only and must NOT be machine-parsed; any structured data should be read from `project_structure` or `capability_map` directly |
| R5-F3 | Design Decisions → Section 1 (by_file) | Inconsistency with Plan | The feature doc says "When the agent explores an issue, it needs to quickly answer 'what's in this file?'" — but the plan's Section 5 explicitly excludes `tests` and `doc_sections` from `by_file`. If an agent asks "what's in `tests/test_auth.py`?", the answer would be empty despite ContextCore having extracted test capabilities from that file. The design decision's stated goal contradicts the plan's exclusion rule. | Medium — agents cannot look up test file contents via `by_file` | Either include tests/docs in `by_file` (making it a complete file index) or explicitly document that `by_file` is a *source code* index and test files should be looked up via `capability_map.by_type.tests` |
| R5-F4 | Architecture Diagram → Cost/Time | Stale Estimate | The architecture diagram states "Cost: $0.00 | Time: ~3-8 seconds" but with 26 accepted suggestions adding validation, consistency checks, path sanitization, schema validation, truncation logic, and partial-failure handling, the implementation is significantly more complex than originally scoped. The "~1 day" effort estimate in the feature doc likely underestimates the now-expanded scope. | Low — planning accuracy | Update effort estimate to ~2 days to account for validation logic, error handling, and schema contract tests added through review rounds |
| R5-F5 | Output Schema → `project_structure.languages` | Missing Detail | The schema says `"languages": [str]` is "deduplicated" but doesn't specify ordering. Is it alphabetical? By LOC prevalence? By service count? This matters for `codebase_summary` rendering and for downstream phases that might use `languages[0]` as the "primary language." | Low — inconsistent ordering across runs, non-deterministic output | Specify: `languages` sorted alphabetically (deterministic) or by descending total LOC (useful) — pick one and document it |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
|---|---|---|---|
| Goal §1 — Run Eagle against project root | Section 3 Phase 2 (step 5), Section 2 (Eagle imports) | Full | — |
| Goal §2 — Run ContextCore extract | Section 3 Phase 3 (step 8), Section 2 (ContextCore imports) | Full | — |
| Goal §3 — Merge into context dict | Section 3 Phase 5 (step 15), Section 4 | Full | — |
| Goal §4 — No LLM cost | Implicit throughout (no LLM imports) | Full | — |
| Input Schema — ProjectMetadata | Section 4 (Eagle transformation mapping) | Full | `evidence` field on `ServiceDependency` still ambiguous per R4-F1 |
| Input Schema — ExtractionResult | Section 4 (ContextCore transformation mapping) | Full | — |
| Output Schema — `project_structure` | Section 4 | Full | `languages` ordering unspecified (R5-F5) |
| Output Schema — `capability_map.by_file` | Section 5 | Partial | Empty sub-key presence unspecified (R5-F1); test/doc exclusion contradicts design goal (R5-F3) |
| Output Schema — `capability_map.by_type` | Section 4 | Full | `None` handling clarified by R3-F2 (status unclear — not in applied or rejected) |
| Output Schema — `capability_map.test_coverage_map` | Section 6 | Partial | Entry format ambiguity (R1-F3 untriaged); co-located test handling (R1-F4 untriaged) |
| Output Schema — `codebase_summary` | Section 7 | Full | Parseability contract unspecified (R5-F2) |
| Design Decision §1 — by_file for localization | Section 5 | Full | — |
| Design Decision §2 — test_coverage_map | Section 6 | Full | Heuristic limitations documented in Section 6 |
| Design Decision §3 — codebase_summary as LLM-ready | Section 7 | Full | — |
| Design Decision §4 — Deterministic, no LLM | Throughout | Full | — |
| Integration — With Eagle (library + subprocess fallback) | Section 2, Risk 1 | Partial | Subprocess fallback mentioned in feature doc but not implemented in plan — only library import path exists |
| Integration — With ContextCore (library import) | Section 2, Section 3 Phase 3 | Full | — |
| Integration — With startd8-sdk (ExplorePhaseHandler) | Section 3 Phase 5 | Full | Lifecycle clarified by R3-F4 (status unclear) |
| Limitation — Python-only ContextCore | Risk 5, Section 7 | Full | Non-Python file handling in `by_file` addressed by R1-S6 (applied) |
| Limitation — Eagle expects service-per-directory | Risk 2 | Full | — |
| Limitation — No semantic analysis | Implicit | Full | — |
| Estimated Effort — ~1 day | Section 3 | Partial | Likely underestimated given expanded scope (R5-F4) |
| Dependencies — Eagle, ContextCore | Section 2 | Full | Eagle packaging issue documented in Risk 1 |

#### Review Round R6
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 00:58:37 UTC
- **Scope**: Architecture-focused review

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | Output Schema → `codebase_summary` | Ambiguity | The summary requirement mentions counting "public classes/functions", but the `ExtractedCapability` schema lacks a visibility field. Python uses `_` convention, but this isn't specified as the filter criteria. | Medium — Summary may overstate public API surface if private members are counted. | Define "public" in this context as "names not starting with `_`". |
| R6-F2 | Output Schema → `capability_map` | Missing Feature | `project_structure` includes `is_generated` for files, but `capability_map` does not. Agents using the map won't know if a class is auto-generated (and thus shouldn't be edited). | Medium — Agent might try to modify generated code, leading to overwritten changes. | Add `is_generated` boolean to the `capability_map` entry schema, derived from the file's status in Eagle. |

#### Requirements Coverage
| Requirement Section | Plan Step(s) | Coverage | Gaps / Notes |
| :--- | :--- | :--- | :--- |
| **Goal** (Merge Eagle+Extract) | Phase 2, 3, 5 | Full | |
| **Input Schemas** | Phase 2, 3 | Full | |
| **Output Schema** | Phase 4, 5, 7 | Full | Implements key renames (`from`→`from_service`) per R1-F1. |
| **Design: by_file index** | Step 10, Section 5 | Full | |
| **Design: test_coverage_map** | Step 11, Section 6 | Partial | Heuristic (basename match) is prone to collisions in large repos (e.g., `test_utils.py` matching multiple `utils.py`). |
| **Design: codebase_summary** | Step 13, Section 7 | Full | Markdown rendering included. |
| **Architecture** | Step 15 | Full | |
| **Integration** | Step 5, 8 | Partial | Eagle integration relies on `sys.path` hack (Risk 1). |
| **Limitations** | Section 10 | Full | Risks documented. |

#### Review Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | validation | critical | Enforce POSIX path normalization for all keys | Eagle and ContextCore may return OS-specific paths (e.g., `\` on Windows). If `project_structure` uses `\` and `capability_map` uses `/`, `by_file` lookups and cross-referencing will fail entirely. | Section 4 (Data Transformation Logic) & Section 5 | Add test case with backslash paths verifying they convert to forward slashes in all output keys. |
| R6-S2 | security | high | Filter sensitive files from `shared_assets` and `files` | Eagle scans everything. If `.env`, `id_rsa`, or `credentials.json` are present, they are added to the context. This metadata (filenames/paths) is fed to the LLM, posing a leakage risk. | Section 4 (Eagle Transformation) | Add `_is_sensitive(path)` check using a blocklist (`.env`, `*.key`, `*.pem`) in `_transform_eagle`. |
| R6-S3 | architecture | high | Implement "Stale Context" warning or refresh mechanism | The context is a snapshot at T0. If the agent enters a loop (Code → Test → Fix), it creates new files. The `context` dict will not contain them, causing the agent to "forget" files it just made. | Section 10 (Risks) & Docstring of `ContextBridge` | Document that `ContextBridge` is one-shot. If used in a loop, it must be re-instantiated. |
| R6-S4 | data | medium | Filter generated code from `capability_map` using Eagle's `is_generated` | startd8-sdk agents should generally not edit generated code (protobufs, etc.). Including these in the capability map bloats the context and invites incorrect edits. | Section 5 (by_file Index Construction) | In `_transform_extract`, check if `file_path` is marked `is_generated` in Eagle data before adding to map. |
| R6-S5 | ops | medium | Define strict `PYTHONPATH` handling for Eagle | The plan relies on `sys.path` modification or editable installs for Eagle. This is fragile in CI/CD or containerized environments where Eagle might be a submodule or sibling dir. | Phase 1 (Scaffolding) | Add a helper `_ensure_eagle_importable(root_path)` that explicitly checks/adds the expected Eagle path before import. |
| R6-S6 | data | medium | Refine `codebase_summary` to count only non-private members | The plan counts all classes/functions. A summary stating "50 classes" when 40 are `_private` helpers is misleading to the LLM about the API surface. | Section 7 (codebase_summary Rendering) | Update counting logic to exclude names starting with `_`. |
| R6-S7 | data | medium | Handle root-level files in `codebase_summary` join logic | The join logic assumes all ContextCore paths need a service prefix. Files at the project root (e.g. `setup.py`, `scripts/`) extracted by ContextCore will break this logic or be orphaned. | Section 7 (codebase_summary Rendering) | Logic: If path is not in a service subdirectory, treat as root-level and do not prepend service name. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- **R1-F1**: Agree. Using reserved words as keys in Python dicts is bad practice and hampers usage of `**kwargs`.
- **R4-F1**: Agree. The implementation cannot satisfy the Output Schema if the Input Schema lacks the data (evidence field).
- **R4-F2**: Agree. Unbounded docstrings are a major token risk for the context window.

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 01:04:35 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-S1 | architecture | high | Add explicit handling for `build_context()` partial failure orchestration — if Eagle succeeds but ContextCore fails (or vice versa), the plan should specify that the successful half is still populated in the context dict with the failed half set to a well-defined sentinel (e.g., `"project_structure": None` or `"capability_map": {"error": "..."}`) rather than the entire call failing. Currently Risk 2 handles zero-services but there is no equivalent for ContextCore extraction failures (e.g., malformed AST, permission errors on subdirectories). | With 38 suggestions applied hardening individual components, the *interaction* between two independent extraction pipelines under partial failure is unaddressed. A ContextCore crash during `extract_all()` on a single malformed file shouldn't prevent Eagle data from reaching downstream phases. This is a second-order effect: the more robust each component becomes individually, the more important graceful degradation at the orchestration layer. | Section 3 Phase 5 (Orchestration) and Section 10 (Risks) — add Risk 9 for partial failure semantics | Unit test: mock `run_extract()` to raise, verify `build_context()` returns context with `project_structure` populated and `capability_map` set to degraded sentinel; integration test: corrupt a .py file in fixture, verify bridge completes |
| R7-S2 | data | high | The `_build_test_coverage_map` heuristic (Section 6) operates solely on ContextCore's `ExtractionResult.tests`, but Eagle's `ServiceMetadata.has_tests` is a separate signal. There's no reconciliation: Eagle may report `has_tests: true` for a service while ContextCore finds zero test capabilities (e.g., non-Python test files like Jest/Go tests). The plan should cross-reference these signals and surface discrepancies in the output (e.g., a `test_coverage_gaps` field listing services where Eagle sees tests but ContextCore extracted none). | This is a cross-area gap between the Eagle transformation (Section 4) and the test coverage map (Section 6). The multi-language limitation (acknowledged) means the test_coverage_map will systematically under-report for polyglot projects, but no signal alerts downstream consumers that the map is incomplete for specific services. | Section 6 — add reconciliation step after coverage map construction; Output Schema — add optional `test_coverage_gaps: list[str]` listing service names with Eagle `has_tests=true` but zero entries in coverage map | Unit test: Eagle fixture with Go service having `has_tests: true`, ContextCore with no test capabilities for that service → verify service appears in `test_coverage_gaps` |
| R7-S3 | interfaces | medium | The plan's Section 7 identifies the critical path join logic (Eagle paths relative to service dir vs ContextCore paths relative to project root) but doesn't specify what happens when the join *fails* — i.e., a ContextCore capability's `file_path` doesn't match any Eagle service's file list. This is distinct from R2-F2 (orphan files in no service); this is about files that *should* match but don't due to symlinks, case sensitivity, or normalization differences (e.g., `./service_a/main.py` vs `service_a/main.py`). | R5-S1 (applied) addressed consistent key presence in `by_file`, and R1-F2 pinned paths as relative to `project_root`, but the actual join/normalization algorithm that reconciles Eagle and ContextCore path formats is unspecified. Without `Path.resolve()` or equivalent normalization before comparison, the cross-reference will silently produce orphaned entries. | Section 7 (codebase_summary) and a new subsection between Sections 5-6 specifying path normalization — all paths should be `PurePosixPath`-normalized (no leading `./`, no trailing `/`, forward slashes only) before any cross-referencing | Unit test: fixture with `./service_a/main.py` in ContextCore output and `service_a/main.py` in Eagle → verify they resolve to same `by_file` key |
| R7-S4 | security | medium | The plan calls `CapabilityExtractor(path).extract_all()` which performs AST parsing on arbitrary Python files. If the project root contains malicious or adversarial Python files (e.g., in a CI pipeline analyzing untrusted repos), `ast.parse` is safe but `compile()` or `exec()` are not. Verify that ContextCore's extraction path uses *only* `ast.parse` and never evaluates code. If it does import or exec anything, the bridge should document this as a security boundary. | This is a second-order concern surfaced by the combination of R4-S3 (input validation, applied) and the library-import integration decision. Direct library import means the bridge's security posture inherits ContextCore's. Unlike the subprocess fallback (which provides process isolation), the library path shares the address space. | Section 2 (Dependencies) — add a security note documenting that ContextCore extraction must be AST-only; Section 10 (Risks) — add Risk 10 noting the shared-process trust boundary | Code audit of `CapabilityExtractor.extract_all()` confirming only `ast.parse` is used; add integration test that includes a file with `__import__('os').system('echo pwned')` and verify it's parsed but never executed |
| R7-S5 | ops | medium | The plan specifies `@pytest.mark.integration` tests in Section 9 but doesn't address CI pipeline configuration. With library-import dependencies on Eagle (no pyproject.toml per Risk 1) and ContextCore, the integration tests require a specific workspace layout. There's no `conftest.py` or CI configuration showing how `sys.path` or editable installs are managed for the test runner. | Three suggestions have been applied for Eagle packaging (R1-S1, Risk 1 mitigation), but the *test environment* setup is different from the runtime setup. R4-S7 and R4-S8 (applied, ops) presumably address operational concerns, but CI-specific test configuration for a multi-repo dependency graph is a distinct gap. Without it, integration tests will fail in CI even if unit tests pass locally. | New Section 9.1 — CI test configuration specifying: (1) editable install commands for Eagle and ContextCore, (2) conftest.py with path setup, (3) fixture project location relative to repo root | Verify integration tests pass in a clean virtualenv with only the documented install steps |
| R7-S6 | risks | medium | The interaction between R6-S2 (accepted — `is_generated` in capability_map) and the `test_coverage_map` creates an unstated assumption: should generated files be excluded from test coverage mapping? If a generated file (e.g., `service_a/pb2.py`) appears as a source file, the heuristic will try to find `test_pb2.py`, which likely doesn't exist, adding noise to coverage gaps. More importantly, agents shouldn't suggest writing tests for generated code. | This is a second-order effect of accepting R6-S2. The `is_generated` flag was added to prevent agents from editing generated files, but its implications for test_coverage_map and test_coverage_gaps (if R7-S2 is accepted) weren't considered. | Section 6 — add filter step: exclude files where `is_generated=true` from source file set before running the coverage heuristic | Unit test: fixture with a generated file → verify it does not appear as a key in `test_coverage_map` |
| R7-S7 | validation | medium | The unit test plan (Section 8) has no test for idempotency — calling `build_context()` twice on the same `ContextBridge` instance and verifying identical output. Given that R3-F1 (accepted) addressed thread-safety by documenting single-threaded usage, there's still no guarantee that internal state mutation (e.g., accumulated lists, cached results) doesn't cause the second call to produce different or corrupted results. | With R3-S1 and R3-S2 applied (concurrency semantics), the *sequential* reuse case is still untested. If `ContextBridge` caches intermediate results in instance variables but `run_eagle()` appends to them on subsequent calls, the second invocation doubles the data. | Section 8 (Unit Test Plan) — add `test_build_context_idempotent` verifying two sequential calls return identical dicts | Direct test: `bridge = ContextBridge(root); ctx1 = bridge.build_context(); ctx2 = bridge.build_context(); assert ctx1 == ctx2` |
| R7-S8 | data | low | The plan drops `language_confidence` from Eagle's output (Section 4), but `project_structure.languages` is a flat deduplicated list. If Eagle reports a service as "Python" with `language_confidence: 0.3`, it's treated identically to one at `0.95`. For polyglot services where Eagle is uncertain, the bridge could propagate a low-confidence language that misleads downstream phases. | This is a data fidelity concern that becomes relevant when the bridge's output drives LLM prompts. The `codebase_summary` might state "8 services, 3 languages" when one language is a low-confidence guess. No prior suggestion addressed confidence thresholds. | Section 4 (Eagle transformation) — add a confidence threshold (e.g., ≥0.5) below which `language` is reported as `"unknown"` rather than the guessed value; alternatively, include `language_confidence` in the per-service dict | Unit test: service with `language_confidence: 0.2` → verify language reported as `"unknown"` or confidence is included in output |
| R7-S9 | architecture | low | The dependency graph (Section 11) shows `_render_codebase_summary()` depends on the output of both `_transform_eagle()` and `_transform_extract()`, but with partial failure handling (if R7-S1 is accepted), the summary renderer must handle `None`/degraded inputs. The current rendering template (Section 7) assumes both data sources are available — there's no fallback template for Eagle-only or ContextCore-only summaries. | This is a direct second-order consequence of partial failure handling. If the bridge gracefully degrades when one source fails, every downstream consumer of both sources (the summary renderer being the most prominent) needs conditional logic. | Section 7 — add two fallback summary templates: Eagle-only (omit capability counts, note "capability extraction unavailable") and ContextCore-only (omit service structure, note "project structure extraction unavailable") | Unit test: mock Eagle failure → verify summary renders with ContextCore data only and includes degradation notice; and vice versa |
| R7-S10 | interfaces | low | The output schema's `capability_map.by_type` uses `[ExtractedCapability.to_dict()]` which (per R3-F2, accepted) uses `vars()` retaining `None` values. However, `ExtractedCapability.parent` for top-level functions is `None`, and `ExtractedCapability.decorators` for undecorated items is `[]`. Downstream consumers iterating `by_type.functions` will see heterogeneous shapes if some capabilities have `parent: "MyClass"` and others have `parent: null`. The plan should specify whether `by_type` entries include *all* `ExtractedCapability` fields uniformly or only the fields relevant to each `source_type`. | R3-F2 resolved the `None` retention question but didn't address whether the *same schema* applies uniformly across source types. A CLI command's `parent` field is semantically meaningless, while a method's `parent` is critical. Uniform inclusion wastes space; per-type schemas complicate consumers. | Section 4 (ContextCore transformation) — specify that `by_type` entries use a uniform schema (all fields from `ExtractedCapability` present) for simplicity, with a one-line note that consumers should ignore `parent` for top-level items | Add schema contract test: for every entry in every `by_type` list, assert the same set of keys is present |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R6-F1: Valid gap — "public" is used in the summary rendering (Section 7) but never defined against the `ExtractedCapability` schema; the `_` convention filter is the right resolution.
- R6-F2: The `is_generated` flag propagation to `capability_map` is important and has second-order implications I've built on in R7-S6.
- R4-F2: Docstring truncation at 500 chars is a practical safeguard; without it, a single file with a large module docstring could bloat the context dict disproportionately.

#### Feature Requirements Suggestions

| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R7-F1 | Output Schema → `project_structure.services[].files` | Missing Constraint | The output schema includes a `files` array per service with `path`, `loc`, and `is_generated`, but for large services (1000+ files), this array dominates the context dict size. No cap or filtering strategy is specified. Unlike `codebase_summary` (which truncates at 15 services), the files array has no equivalent bound. | Medium — large monorepo services could produce multi-MB context dicts, slowing serialization and consuming memory unnecessarily when most files are never referenced by downstream phases. | Add a configurable `max_files_per_service` parameter (default: 500) with truncation sorted by LOC descending, plus a `files_truncated: bool` flag in the service dict. |
| R7-F2 | Output Schema → `test_coverage_map` | Semantic Ambiguity | The requirement specifies map keys as source file paths and values as test names, but doesn't define the directionality expectation. A source file `src/auth.py` mapped to `["test_login", "test_logout"]` implies these tests *cover* that file, but the heuristic is purely filename-based. The word "coverage" implies execution-based coverage (e.g., `coverage.py`), which this is not. | Low — could mislead downstream consumers or agents into treating this as actual coverage data rather than a naming-convention heuristic. | Rename to `test_association_map` or add explicit documentation: "This is a heuristic filename association, not execution-based coverage. Actual test coverage requires running the test suite." |
| R7-F3 | Integration Points → With startd8-sdk | Missing Constraint | The feature doc shows `context.update(merged)` in `ExplorePhaseHandler` but doesn't specify the contract for what happens if `build_context()` is slow (>8s estimate). No timeout is defined for the bridge call, and if Eagle hangs on a massive repo (e.g., scanning a monorepo with 100K files), the entire Artisan pipeline blocks indefinitely. | Medium — no timeout or cancellation mechanism for a synchronous call in a pipeline that may have SLA expectations. | Specify a configurable timeout (default: 60s) for `build_context()`, with the bridge raising `ContextBridgeTimeout` if exceeded. Document that Eagle's `RepoScanner` is the likely bottleneck for large repos. |
| R7-F4 | Limitations | Missing Limitation | The doc lists three limitations (Python-only extraction, service-per-directory expectation, no semantic analysis) but doesn't mention that `ExtractionResult` captures only *static* capabilities. Dynamically registered routes (e.g., Flask `add_url_rule()` called in a loop), dynamically generated CLI commands (e.g., Click groups built at import time), or monkey-patched classes won't appear in the capability map. | Low — agents may assume the capability map is complete when it systematically misses dynamic registrations common in Python web frameworks. | Add a fourth limitation: "Dynamic registrations (runtime route addition, programmatic CLI commands, monkey-patched classes) are not captured by static AST extraction." |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Problem Statement (Eagle + ContextCore → context dict) | Sections 1-3, Section 15 (build_context) | Full | — |
| Goal 1: Run Eagle against project root | Section 3 Phase 2, Step 5 (run_eagle) | Full | — |
| Goal 2: Run ContextCore extract | Section 3 Phase 3, Step 8 (run_extract) | Full | Risk 3 correctly identifies `extract_all()` vs `run_extraction()` |
| Goal 3: Merge into context dict | Section 3 Phase 5, Step 15 (build_context) | Partial | No partial failure handling if one source fails (R7-S1) |
| Goal 4: No LLM cost | Section 7, Design Decision 4 | Full | — |
| Input Schema: ProjectMetadata | Section 4 (Eagle transformation) | Full | `language_confidence` dropped without threshold consideration (R7-S8) |
| Input Schema: ExtractionResult | Section 4 (ContextCore transformation) | Full | — |
| Output Schema: project_structure | Section 4 | Full | No file count cap (R7-F1) |
| Output Schema: capability_map.by_file | Section 5 | Full | Path normalization unspecified (R7-S3) |
| Output Schema: capability_map.by_type | Section 4 | Partial | Uniform vs per-type field schema unspecified (R7-S10) |
| Output Schema: test_coverage_map | Section 6 | Full | No generated-file exclusion (R7-S6); naming is misleading (R7-F2) |
| Output Schema: codebase_summary | Section 7 | Partial | No fallback template for partial failure (R7-S9) |
| Design Decision 1: by_file for localization | Section 5 | Full | — |
| Design Decision 2: test_coverage_map | Section 6 | Full | No cross-reference with Eagle's `has_tests` (R7-S2) |
| Design Decision 3: codebase_summary as LLM-ready | Section 7 | Full | R5-F2 (applied) clarifies non-parseable contract |
| Design Decision 4: Deterministic, no LLM | Throughout | Full | — |
| Architecture: ContextBridge class | Section 1, Section 3 | Full | — |
| Integration: Eagle (library + subprocess fallback) | Section 2, Risk 1 | Full | — |
| Integration: ContextCore (library import) | Section 2, Risk 3 | Full | Security boundary unaudited (R7-S4) |
| Integration: startd8-sdk ExplorePhaseHandler | Section 3 Phase 5 | Partial | No timeout specified (R7-F3) |
| Limitation: Python-only extraction | Risk 2, Section 6 limitations | Full | Missing dynamic registration limitation (R7-F4) |
| Limitation: Service-per-directory | Risk 2 | Full | — |
| Limitation: No semantic analysis | Section 7 notes | Full | — |
| Estimated Effort: ~1 day | Section 3 timeline | Full | R5-F4 rejected; estimate left to implementer |
| Dependencies: Eagle, ContextCore | Section 2 | Partial | CI/test environment setup unspecified (R7-S5) |

#### Review Round R8

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 01:27:38 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R8-S1 | data | high | Plan Section 4 still maps `ServiceDependency.from_service → dep["from"]` and `to_service → dep["to"]` despite R1-F1 being accepted to rename these to `source_service`/`target_service`. Unit test `test_transform_eagle_service_dependencies_key_rename` in Section 8 also validates the old `from`/`to` keys. Both the transformation logic and tests are inconsistent with the accepted suggestion. | R1-F1 was accepted specifically because `from` is a Python reserved word. The plan's Section 4 and Section 8 were never updated to reflect this, creating a concrete implementation-vs-spec divergence. An implementer following the plan literally will produce output that contradicts the accepted design. | Section 4 (Data Transformation Logic — service_dependencies mapping) and Section 8 (Unit Test Plan — `test_transform_eagle_service_dependencies_key_rename`) | Verify that Section 4 maps to `dep["source_service"]`/`dep["target_service"]` and that the unit test validates these key names. |
| R8-S2 | architecture | high | `_render_codebase_summary()` depends on both Eagle and ContextCore outputs (service counts from Eagle, capability counts from ContextCore), but the dependency graph in Section 11 shows it depending only on `_transform_extract()`. If Eagle fails and the plan follows Risk 2's mitigation (continue with ContextCore only), the summary renderer will receive a null/empty `project_structure` and must handle this gracefully. No partial-input rendering logic is specified. | The accepted Risk 2 mitigation (R1-S2 area) creates a legitimate partial-data path, but the summary renderer's template in Section 7 unconditionally references service counts, dependency lines, and service-level details. This is a second-order interaction between two accepted suggestions — the partial-failure path and the summary format. | Section 7 (codebase_summary Rendering) — add conditional blocks for Eagle-only-failure and ContextCore-only-failure cases. Also update dependency graph to show `_render_codebase_summary()` depends on BOTH `_transform_eagle()` and `_transform_extract()`. | Add unit tests: `test_summary_eagle_failure_contextcore_only` and `test_summary_contextcore_failure_eagle_only` to Section 8. |
| R8-S3 | interfaces | medium | The plan specifies `CapabilityExtractor(path).extract_all()` (Risk 3, Section 2) but ContextCore's `ExtractionResult` uses `file_path` relative to the path passed to the extractor. If `project_root` is passed as an absolute path on one system and relative on another, all `by_file` keys and `test_association_map` keys will differ. R1-F2 was accepted (paths relative to `project_root`) but the plan never specifies a normalization step to enforce this — it relies on ContextCore coincidentally producing relative paths. | This is an unstated assumption about ContextCore's behavior. If ContextCore returns absolute paths (which it may on some invocation paths), the entire `by_file` index breaks. The accepted R1-F2 sets the contract but the plan has no enforcement mechanism. | Section 9 (`_build_by_file_index()`) and Section 10 (`run_extract()`) — add an explicit path normalization step: `os.path.relpath(cap.file_path, project_root)` for every capability before indexing. | Add unit test `test_by_file_normalizes_absolute_paths` with capabilities containing absolute `file_path` values; verify keys are relative. |
| R8-S4 | validation | medium | Section 8's unit test `test_build_context_does_not_overwrite_existing` validates the merge semantics from R1-F7, but the test only checks one direction (existing keys preserved). It doesn't test the reverse: what happens if `build_context()` is called twice on the same context dict? The accepted R3-F4 says the bridge runs once, but there's no guard preventing double invocation. A second call would either duplicate data or silently overwrite the first run's output. | R3-F4 documented lifecycle expectations but didn't specify enforcement. Without an idempotency guard or a "already populated" check, a coding error calling the bridge twice in a pipeline produces undefined behavior — the context could have stale Eagle data with fresh ContextCore data or vice versa. | Section 15 (`build_context()`) — add a check: if `context` already contains `project_structure`, either skip (idempotent) or raise `ContextBridgeError("Context already populated")`. Add unit test `test_build_context_idempotency_guard`. | Unit test calling `build_context()` twice on the same context dict, verifying defined behavior (skip or raise). |
| R8-S5 | risks | medium | Risk 5 identifies the path prefix mismatch (Eagle paths are service-relative, ContextCore paths are project-relative) and Section 7 mentions "must prepend service name when cross-referencing." However, this prepend logic is never specified for `_build_by_file_index()` in Section 5 or `_build_test_coverage_map()` in Section 6. These sections operate solely on ContextCore paths. The cross-reference problem actually manifests when a downstream consumer tries to look up an Eagle file path in `by_file` — the keys won't match because they use different path bases. | The accepted R1-F2 (paths relative to `project_root`) resolves the contract but doesn't address the fact that Eagle's `FileInfo.path` is service-relative. If a downstream phase gets a file path from `project_structure.services[0].files[0].path` (service-relative per Eagle) and tries to look it up in `capability_map.by_file` (project-root-relative per R1-F2), it will fail. Either Eagle paths in `project_structure` must also be normalized to project-root-relative, or a cross-reference mechanism is needed. | Section 4 (Eagle transformation) — when building `service["files"]`, prepend service name to `FileInfo.path` to make all paths project-root-relative. Add unit test `test_eagle_file_paths_are_project_root_relative`. | Integration test: for every file path in `project_structure.services[].files[].path`, verify it exists as a key in `capability_map.by_file` (for Python files). |
| R8-S6 | data | medium | R4-F2 was accepted to truncate docstrings to 500 characters, but the plan's Section 5 (`_build_by_file_index`) shows docstrings included for classes and functions in `by_file`, AND Section 4 shows `by_type` using `vars()` which includes the full docstring. The truncation must be applied in both places — but if truncation happens at the `vars()` level, it mutates the original `ExtractedCapability` objects (since `vars()` returns a reference to the object's `__dict__`). If truncation happens at the output level, it must be done in two separate code paths. | This is a second-order effect of accepting R4-F2 alongside the existing dual-index design (`by_file` + `by_type`). Without specifying WHERE truncation occurs, an implementer might truncate in `by_file` but forget `by_type`, or vice versa, or accidentally mutate the source objects affecting subsequent processing. | Section 4 and Section 5 — specify that docstring truncation happens during a shared `_capability_to_dict()` helper that both `by_file` and `by_type` construction use. This helper should copy (not mutate) the source data. | Unit test: `test_docstring_truncation_in_by_file_and_by_type` — verify both indexes truncate at 500 chars. `test_truncation_does_not_mutate_source` — verify original `ExtractedCapability` objects are unchanged after transformation. |
| R8-S7 | security | medium | The plan shells out to Eagle as a fallback (Section 2, Integration Points) and passes `project_root` as a path argument. If `project_root` contains shell metacharacters or is user-supplied (e.g., from a web UI triggering the pipeline), this creates a command injection vector. The library-import path is safe, but the subprocess fallback is not addressed. | While R4-S3/R4-S4 addressed security concerns generally, the specific subprocess invocation `eagle.py --reference-dir <path>` with an unsanitized path was never reviewed. The feature doc recommends library import with subprocess fallback, meaning this code path will exist. | Section 2 (Dependencies) or a new subsection on subprocess safety — specify that subprocess calls must use `subprocess.run([...], shell=False)` with list arguments (not string interpolation), and that `project_root` must be validated as an existing directory via `Path.resolve()` before use. | Unit test: `test_subprocess_fallback_rejects_shell_metacharacters` — pass a `project_root` containing `; rm -rf /` and verify it's sanitized or rejected before subprocess invocation. |
| R8-S8 | ops | medium | The plan estimates "Cost: $0.00 \| Time: ~3-8 seconds" and the feature doc concurs, but neither accounts for filesystem I/O on network-mounted volumes (NFS, EFS) common in CI/CD and container environments. Eagle's `RepoScanner` reads every file to compute LOC and SHA256 (for shared assets), and ContextCore's extractor reads every Python file for AST parsing. On a 5000-file project over NFS, this could easily take 30-60 seconds, not 3-8. | The accepted R7-F3 rejection (timeouts handled at pipeline level) is reasonable, but the *estimate* being off by 10x could cause incorrect pipeline scheduling, SLA misconfiguration, or premature timeout kills by the very pipeline-level timeout the rejection defers to. The estimate should at least acknowledge the variance. | Section 10 (Risks) — add Risk 9: "Performance on network filesystems. The 3-8 second estimate assumes local SSD. On NFS/EFS, I/O-bound scanning may take 10-60 seconds for large projects. Pipeline timeout configuration should account for this." | Document the estimate range as "3-8s (local SSD) / 10-60s (network FS)" in the architecture diagram. |
| R8-S9 | validation | medium | The integration test plan (Section 9) tests against a single minimal fixture project (`tests/fixtures/sample_project/`). All 7 integration tests use this one fixture. This means zero coverage of: (a) single-service flat projects (Risk 2), (b) projects with no tests, (c) projects with co-located tests (R1-F4), (d) projects with generated files. The fixture is a "happy path" multi-service project that exercises the least interesting code paths. | With 46 accepted suggestions adding edge case handling (orphan files R2-F2, co-located tests R1-F4, empty test maps R3-F3, generated files R6-F2, partial failures R1-S2), the integration tests should cover at least the primary edge cases, not just the golden path. A single fixture cannot validate the accepted suggestions' implementations. | Section 9 (Integration Test Plan) — add 2-3 additional fixture projects: `fixtures/single_service_flat/` (flat layout, no service dirs), `fixtures/no_tests_project/` (exercises empty test_association_map), `fixtures/colocated_tests/` (test files alongside source). | Each fixture should have at least one dedicated integration test validating the specific edge case it represents. |
| R8-S10 | interfaces | low | The output schema specifies `capability_map.by_file` includes `cli_commands` as a category key (per R5-F1, all category keys always present), but CLI commands extracted by ContextCore typically come from module-level decorators (`@click.command()`) which are also functions. The same capability could appear in both `by_file[path]["functions"]` and `by_file[path]["cli_commands"]`, creating duplicate entries. The plan's Section 5 iterates `cli_commands` and `functions` separately without deduplication. | This is a subtle data quality issue. A Click-decorated function appears in both `ExtractionResult.functions` and `ExtractionResult.cli_commands`. Without deduplication, the `by_file` index double-counts it, and `total_capabilities` is inflated. The `codebase_summary` would then report more capabilities than actually exist. | Section 5 (`_build_by_file_index`) — add a note that if a capability appears in multiple type lists (e.g., a function that is also a CLI command), it should appear only in the more specific category (`cli_commands` takes precedence over `functions`). Document the precedence order. | Unit test: `test_by_file_deduplicates_cli_functions` — create an `ExtractedCapability` present in both `functions` and `cli_commands` lists, verify it appears only under `cli_commands` in `by_file`. |

#### Feature Requirements Suggestions

| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R8-F1 | Output Schema → `capability_map.by_file` | Missing Detail | R5-F1 (accepted) specifies all category keys are always present, but the feature doc's `by_file` example only shows `classes`, `functions`, and `api_endpoints`. The full set of always-present keys should be explicitly enumerated in the feature doc's output schema example — especially since R5-F3 (accepted) resolved the test file inclusion question. The current example contradicts both accepted suggestions. | Medium — implementers referencing the feature doc's example will produce incomplete `by_file` entries. | Update the `by_file` example in the Output Schema to show all always-present keys including `cli_commands`, and clarify whether `tests` and `doc_sections` are included per the R5-F3 resolution. |
| R8-F2 | Output Schema → `project_structure.service_dependencies` | Stale Schema | Despite R1-F1 being accepted (rename `from`/`to` to `source_service`/`target_service`), the Output Schema in the feature doc still shows `"from": str, "to": str`. The feature doc is the canonical schema reference and should reflect accepted changes. | High — any consumer implementing against the feature doc's output schema will use the wrong key names. | Update the Output Schema's `service_dependencies` to use `"source_service"` and `"target_service"`. |
| R8-F3 | Design Decisions → test_coverage_map | Stale Naming | R7-F2 was accepted to rename `test_coverage_map` to `test_association_map` (or add prominent documentation that it's heuristic-based). The feature doc's Output Schema, Design Decisions section, and Limitations section all still reference `test_coverage_map`. | Medium — the canonical document contradicts the accepted naming decision, causing confusion for implementers. | Search-and-replace `test_coverage_map` with `test_association_map` throughout the feature doc, or add the accepted documentation caveat to the Output Schema. |
| R8-F4 | Integration Points → With startd8-sdk | Missing Detail | The feature doc shows the bridge called in `ExplorePhaseHandler.execute()` which receives `context` as a parameter. But the feature doc doesn't specify whether `build_context()` returns the NEW keys only (to be merged) or returns a COMPLETE context dict (including existing keys like `workflow_id`). The current signature `build_context() → dict[str, Any]` is ambiguous. | Medium — if `build_context()` returns only new keys, `context.update(merged)` works. If it returns a full context with its own `workflow_id`, it could overwrite pipeline-managed keys. | Clarify that `build_context()` returns only the three bridge-owned keys (`project_structure`, `capability_map`, `codebase_summary`) and does not include or echo back existing context keys. |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
|---|---|---|---|
| Problem Statement | Section 1, 2 | Full | — |
| Goal 1: Run Eagle → ProjectMetadata | Phase 2 (Steps 4-6), Section 4 | Full | — |
| Goal 2: Run ContextCore extract → ExtractionResult | Phase 3 (Steps 8-9), Section 4 | Full | — |
| Goal 3: Merge into context dict | Phase 5 (Step 15), Section 4 | Partial | Merge semantics (R1-F7 accepted) documented but plan Section 15 still shows `context.update()` without conflict handling |
| Goal 4: No LLM cost | Section 1 (Overview) | Full | — |
| Input Schema: Eagle ProjectMetadata | Section 4 (Eagle mapping) | Full | — |
| Input Schema: ContextCore ExtractionResult | Section 4 (ContextCore mapping) | Full | — |
| Output Schema: project_structure | Section 4 | Partial | `service_dependencies` keys still use `from`/`to` (see R8-S1), file paths not normalized to project-root-relative (see R8-S5) |
| Output Schema: capability_map.by_file | Section 5 | Partial | Deduplication of CLI commands vs functions not addressed (see R8-S10), all-keys-present contract from R5-F1 not reflected in code template |
| Output Schema: capability_map.by_type | Section 4 | Full | — |
| Output Schema: test_coverage_map | Section 6 | Partial | Still uses old name despite R7-F2 acceptance (see R8-F3) |
| Output Schema: codebase_summary | Section 7 | Partial | No partial-data rendering when Eagle fails (see R8-S2) |
| Design Decision 1: by_file index | Section 5 | Full | — |
| Design Decision 2: test_coverage_map | Section 6 | Full | — |
| Design Decision 3: codebase_summary as LLM-ready | Section 7 | Full | — |
| Design Decision 4: Deterministic, no LLM | Throughout | Full | — |
| Architecture: ContextBridge class | Sections 1-3, dependency graph | Full | — |
| Integration: Eagle (library + subprocess fallback) | Section 2 | Partial | Subprocess fallback has no input sanitization (see R8-S7) |
| Integration: ContextCore | Section 2 | Full | — |
| Integration: startd8-sdk (ExplorePhaseHandler) | Phase 5 | Partial | No idempotency guard (see R8-S4), return scope ambiguous (see R8-F4) |
| Limitation 1: Python-only extraction | Section 7 (note), Risks | Full | — |
| Limitation 2: Service-per-directory | Risk 2 | Full | — |
| Limitation 3: No semantic analysis | Documented | Full | — |
| Limitation 4: Dynamic registrations (R7-F4) | Not in plan | None | Accepted R7-F4 not reflected in plan's Risk section |
| Estimated Effort | Section 3 (phases) | Full | — |
| Dependencies | Section 2 | Full | — |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None — all prior Appendix C suggestions have been triaged into Appendix A or B.

#### Review Round R9
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 01:29:30 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R9-S1 | architecture | High | Integrate `ContextBridge` directly into the `startd8-sdk` source tree rather than as a standalone `hybrid_scaffold` package with its own `pyproject.toml`. | The Requirements describe `ContextBridge` being instantiated inside `ExplorePhaseHandler` (part of the SDK). Creating a separate package with path-based dependencies (`pyproject.toml` pointing to local Eagle/ContextCore) creates deployment conflicts and makes the SDK hard to package. It should be a module within the SDK (e.g., `startd8_sdk.integrations`). | Section 1 (File-by-File Breakdown) and Section 2 (Dependencies) | Verify imports work within the SDK context without extra pip installs. |
| R9-S2 | data | Critical | Explicitly normalize `project_structure.services[].files[].path` to be relative to `project_root`, handling Eagle's service-relative paths. | Eagle's decomposition often reports files relative to the identified service directory (e.g., `src/main.py` inside service `auth`). If mapped directly to output, the agent loses the `auth/` prefix. The plan notes this in Section 7 for the *summary*, but Section 4's transformation logic (`FileInfo.path → file["path"]`) misses this normalization for the structured output. | Section 4 (Data Transformation Logic - Eagle) | Unit test with a service in a subdirectory ensuring output path includes the subdirectory. |
| R9-S3 | ops | Medium | Implement the `ContextBridgeTimeout` logic in `build_context` as requested in R7-F3. | R7-F3 was applied, but the Plan (Section 3 & 8) only mentions "Implement build_context" without detailing the timeout wrapper. Given Eagle's potential to hang on large repos, this protection must be explicit in the implementation steps. | Section 3 (Phase 5) and Section 8 (Orchestration) | Test `build_context` raises specific Timeout exception when mocked sub-calls delay. |
| R9-S4 | validation | Medium | Synthesize a "Root Service" if Eagle returns zero services (Risk 2), rather than just logging a warning. | Plan Risk 2 suggests "Log warning and continue with ContextCore data only" for flat projects. This leaves `project_structure.services` empty, depriving the agent of macro-level stats (LOC, languages) for flat repositories. A fallback strategy should wrap root-level files into a synthetic service entry. | Section 10 (Risk 2) and Section 4 (Eagle Transformation) | Test against a flat project structure; verify `services` list has 1 entry. |
| R9-S5 | interfaces | Low | Use `dataclasses.asdict()` instead of `vars()` for transforming `ExtractionResult` lists. | Plan Section 4 specifies `vars()`. `vars()` is shallow and fails if dataclasses use `__slots__`. `asdict()` is the standard, safe way to serialize nested dataclasses to dicts. | Section 4 (ContextCore Transformation) | Verify serialization of nested objects works correctly. |
| R9-S6 | data | Medium | Implement defensive retrieval for `ServiceDependency.evidence` using `getattr(dep, "evidence", None)`. | R4-F1 identified that `evidence` is missing from Eagle's input schema. While the requirement was to "update input schema", the Bridge code should be robust to the field being missing in the installed version of Eagle to prevent `AttributeError`. | Section 4 (Eagle Transformation) | Test with a mock `ServiceDependency` object lacking the `evidence` attribute. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F2: Explicitly specify path relativity. (Critical for data integrity across tools).
- R4-F1: Resolve `evidence` field mismatch. (Real runtime crash risk).
- R7-F3: Add timeout. (Essential for pipeline reliability).

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R9-F1 | Input Schemas | Ambiguity | The Eagle `ServiceMetadata` schema lists `files: List[FileInfo]`, but does not specify if `FileInfo.path` is relative to the *Service* root or the *Project* root. | Critical — Determines whether path joining logic is required in the Bridge. Incorrect assumption breaks file lookups. | Explicitly state the path format provided by Eagle (likely service-relative) and require the Bridge to normalize to project-relative. |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| :--- | :--- | :--- | :--- |
| **Context Bridge Goal** | Overview, Section 3 | Full | - |
| **Input Schemas** | Section 2 | Full | - |
| **Output Schema** | Section 4, 5, 6, 7 | Full | - |
| **Design Dec 1: by_file** | Section 5 | Full | - |
| **Design Dec 2: test_coverage** | Section 6 | Full | - |
| **Design Dec 3: summary** | Section 7 | Partial | Plan implements heuristic truncation (15 services) but lacks strict token budget enforcement (R1-F5). |
| **Design Dec 4: Deterministic** | Overview | Full | - |
| **Architecture** | Section 1, 3 | Partial | Plan proposes standalone packaging (`hybrid_scaffold`) which conflicts with "Integration Points" implying SDK embedding. |
| **Integration Points** | Section 3 | Partial | Plan uses `extract_all` (internal API) instead of `run_extraction` (Requirements recommendation), creating stability risk. |
| **Limitations** | Section 10 | Full | Risks 2, 6, 7 cover limitations well. |

#### Review Round R10

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 01:34:31 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R10-S1 | data | high | Plan Section 4 still shows `dep["from"]` / `dep["to"]` as output keys despite R1-F1 (accepted) renaming them to `source_service`/`target_service`. The unit test table in Section 8 also tests the OLD mapping: `test_transform_eagle_service_dependencies_key_rename` verifies `from_service/to_service → from/to`. The plan's transformation logic and test assertions are internally consistent but contradict the accepted schema change. | R8-F2 was accepted to fix the *feature doc's* Output Schema, but the *implementation plan* was never updated. An implementer following the plan will produce the wrong keys, and the unit test will assert the wrong output. This is a concrete implementation bug introduced by applying R1-F1 to the feature doc but not propagating it to the plan. | Section 4 (Eagle transformation mapping) and Section 8 (unit test `test_transform_eagle_service_dependencies_key_rename`) — both must use `source_service`/`target_service`. | Grep plan for `dep["from"]`, `dep["to"]`, `from_service`, `to_service` and verify all references use the accepted key names. |
| R10-S2 | data | high | Plan Section 5 explicitly states "Tests and doc_sections excluded from by_file" but R5-F3 was accepted to resolve this contradiction. The plan was never updated to reflect the R5-F3 resolution. Similarly, Section 8's test `test_by_file_excludes_tests_and_docs` asserts the old behavior. | The accepted R5-F3 resolved whether test files appear in `by_file`, but the plan still enforces the pre-resolution behavior. Whichever way R5-F3 was resolved (include tests or document source-only), the plan must reflect it. Currently the plan contradicts the accepted suggestion. | Section 5 (by_file construction logic), Section 8 (test `test_by_file_excludes_tests_and_docs`). | Verify Section 5 logic and Section 8 test expectations match the R5-F3 resolution documented in the feature doc. |
| R10-S3 | architecture | medium | `_render_codebase_summary()` depends on BOTH `project_structure` and `capability_map` data, but the dependency graph in Section 11 shows it depending only on `_transform_extract()`. The summary template in Section 7 references service counts, languages, and LOC (from Eagle) plus function/class/test counts (from ContextCore). If Eagle fails partially (Risk 2 mitigation: "continue with ContextCore data only"), the summary renderer will receive incomplete data but has no documented fallback for missing Eagle fields. | The partial-failure path (zero Eagle services) creates a second-order issue: the summary's "Project: {N} services, {N} languages, {N} total LOC" line would render as "Project: 0 services, 0 languages, 0 total LOC" — which is misleading rather than informative. The renderer needs a graceful degradation path when Eagle data is absent. | Section 7 (summary rendering) — add conditional logic for when `project_structure` has zero services. Section 11 (dependency graph) — add arrow from `_transform_eagle()` to `_render_codebase_summary()`. | Unit test: `test_summary_eagle_failure_graceful_degradation` — verify summary with empty project_structure produces meaningful output (e.g., "Project structure unavailable. {N} capabilities extracted."). |
| R10-S4 | interfaces | medium | The plan's Section 2 lists `models.ProjectMetadata` and `models.ServiceMetadata` as imports but does not list `models.ServiceDependency`, `models.SharedAsset`, or `models.FileInfo`. Section 4's transformation logic accesses fields on all these types. If Eagle's import structure requires explicit imports of these sub-models (common with dataclass hierarchies), the implementation will fail with `ImportError` or `AttributeError`. | The dependency table is incomplete — it only lists top-level types but the transformation logic destructures nested types. An implementer following Section 2 alone would miss required imports. | Section 2 (Dependencies and Imports) — add `models.ServiceDependency`, `models.SharedAsset`, `models.FileInfo` to the Eagle imports table. | Verify all types accessed in Section 4 transformations have corresponding import entries in Section 2. |
| R10-S5 | validation | medium | Section 8's unit test plan has no test for the `is_generated` field propagation into `capability_map` entries (accepted R6-F2). The Eagle transformation tests verify `is_generated` in `project_structure.services[].files[]`, but no test verifies that `capability_map.by_file` entries carry `is_generated` derived from Eagle's file metadata. This cross-source join is the most error-prone part of the bridge. | R6-F2 was accepted to add `is_generated` to capability_map entries, requiring a join between Eagle's file list and ContextCore's capabilities by file path. This join depends on the path normalization logic (Risk 5, R9-F1). A missing test for this specific cross-source derivation means the most fragile transformation goes unverified. | Section 8 (Unit Test Plan, ContextCore Transformation or by_file Index section) — add `test_by_file_is_generated_from_eagle` that verifies capabilities in generated files carry `is_generated: true`. | The test should use a fixture where Eagle marks a file as generated and ContextCore extracts capabilities from it, then verify the `is_generated` flag appears in the `by_file` entry. |
| R10-S6 | risks | medium | Risk 5 identifies the path prefix mismatch and Section 7 notes "Must prepend service name when cross-referencing," but the plan never specifies WHERE this normalization happens in the code or WHICH component's paths are canonical. R9-F1 (accepted) requires explicitly stating Eagle's path format, but the plan's transformation logic in Section 4 simply copies `FileInfo.path → file["path"]` without normalization. The `_build_by_file_index()` in Section 5 uses `capability.file_path` as the key. If Eagle paths are service-relative and ContextCore paths are project-relative, these will never match. | The path normalization is acknowledged as critical (Risk 5, R1-F2, R9-F1) but the plan contains no implementation step for it. Section 4 copies paths verbatim, Section 5 uses ContextCore paths as keys, and the cross-reference in `is_generated` (R6-F2) requires matching between the two. The gap is not in awareness but in the plan's actual implementation steps. | Add a new step between Phase 2 and Phase 3 (or within `_build_by_file_index`): `_normalize_paths()` that converts Eagle's service-relative paths to project-relative paths by prepending the service name. Document this as the canonical normalization point. | Unit test: `test_path_normalization_eagle_to_project_relative` — given Eagle service "auth" with file "main.py", verify normalized path is "auth/main.py" matching ContextCore's `file_path`. |
| R10-S7 | validation | medium | Section 8 has no test for the docstring truncation behavior accepted in R4-F2 (truncate to 500 characters). The `by_type` and `by_file` transformations in Sections 4-5 should truncate docstrings, but no test verifies this boundary. | Without a test, a future refactor could easily remove the truncation logic. Given that the truncation was specifically accepted to prevent token bloat, it should have explicit boundary tests (499 chars, 500 chars, 501 chars). | Section 8 (Unit Test Plan, ContextCore Transformation) — add `test_capability_docstring_truncation_at_boundary`. | Test with docstrings of 499, 500, and 501 characters; verify output is ≤500 chars and that truncation adds an ellipsis marker or clean cut. |
| R10-S8 | architecture | medium | The plan lists `_build_test_coverage_map()` under Phase 3 (ContextCore Transformation), but Section 6's heuristic requires matching test basenames against *source file paths* from cli_commands, classes, functions, and api_endpoints. If R5-F3 was resolved to include tests in `by_file`, then `_build_by_file_index()` runs first and already has the file list. But if R10-S2 reveals tests are excluded, the coverage map must independently collect source paths. The implementation order doesn't account for this data dependency. | The test association map and `by_file` index share the same source file path collection. Without specifying which runs first or whether they share intermediate data, the implementation might duplicate work or, worse, use inconsistent path sets. | Section 3 (Implementation Order, Phase 3) — explicitly state that `_build_by_file_index()` runs before `_build_test_coverage_map()` and that the test map uses the same source path set. | Review implementation order to verify `_build_test_coverage_map` can access the by_file source path set without circular dependency. |
| R10-S9 | security | low | Section 7's summary rendering interpolates user-controlled data (service names, file paths, project names) into a markdown string destined for LLM prompt injection. While R5-F2 clarifies the summary shouldn't be machine-parsed, a service named `## Ignore previous instructions` or a file path containing markdown injection could alter LLM behavior when the summary is injected into prompts. | This is a prompt injection vector through data, not through user input. Eagle extracts service names from directory names, which are developer-controlled. In a supply-chain attack scenario (malicious repo analyzed by the pipeline), crafted directory names could inject instructions into the LLM prompt via `codebase_summary`. | Section 7 (summary rendering) — sanitize service names, file paths, and project names by stripping markdown control characters (`#`, `*`, `[`, `]`, `` ` ``) before interpolation. | Unit test: `test_summary_sanitizes_markdown_injection` — service name containing `## DROP TABLE` renders as plain text without markdown heading interpretation. |
| R10-S10 | ops | low | The plan specifies "~3-8 seconds" execution time in the architecture diagram but defines no mechanism to measure or log actual execution time. With 61 accepted suggestions adding validation, truncation, path normalization, schema checks, and cross-source joins, the actual runtime could exceed this estimate significantly on real projects. Without instrumentation, performance regressions will go unnoticed. | Accepted suggestions (particularly path normalization across all files, `is_generated` cross-referencing, docstring truncation, and schema validation from Risk 8) add non-trivial computation. The original estimate predates these additions. Basic timing instrumentation enables teams to detect when the bridge becomes a pipeline bottleneck. | Section 15 (`build_context()` orchestration) — add `time.perf_counter()` instrumentation that logs wall-clock time for Eagle extraction, ContextCore extraction, and total bridge execution. Emit as structured log at INFO level. | Integration test: verify log output contains timing entries. Ops: set alerting threshold if bridge exceeds 30s (half the rejected R7-F3 timeout). |

#### Feature Requirements Suggestions

| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R10-F1 | Output Schema → `capability_map.by_file` | Inconsistency with Accepted Suggestions | The feature doc's `by_file` example still shows only `classes`, `functions`, `api_endpoints` — missing `cli_commands`, `tests`, and `doc_sections`. R5-F1 (accepted) requires all category keys always present. R8-F1 (accepted) called for updating this example. R5-F3 (accepted) resolved the test inclusion question. The example in the feature doc has not been updated to reflect ANY of these three accepted suggestions. | High — The canonical schema example contradicts three accepted suggestions, making it the primary source of implementer confusion. | Update the `by_file` example to show all six category keys with empty-list defaults, reflecting R5-F1, R5-F3, and R8-F1. |
| R10-F2 | Output Schema → `project_structure.service_dependencies` | Stale Schema (Persistent) | Despite R1-F1 and R8-F2 both being accepted, the Output Schema code block in the feature doc STILL shows `"from": str, "to": str` and `"evidence": str`. The `from`/`to` keys should be `source_service`/`target_service`. This has been flagged twice and accepted twice but never actually applied to the document. | High — Implementers copy-pasting the schema will use wrong key names. This is now a process failure, not a review gap. | Apply the accepted R1-F1 and R8-F2 changes to the actual Output Schema code block. This should be treated as a blocking pre-implementation task. |
| R10-F3 | Design Decisions → Section 2 (test_coverage_map) | Stale Naming (Persistent) | R7-F2 and R8-F3 were both accepted to rename `test_coverage_map` to `test_association_map`. The feature doc still uses `test_coverage_map` in the Output Schema, Design Decisions Section 2, and the Design Decisions Section 2 heading. | Medium — Same as R10-F2: accepted changes not applied to the document. | Search-and-replace all instances of `test_coverage_map` with `test_association_map` in the feature doc. |
| R10-F4 | Input Schema → `ServiceDependency` | Missing Field Definition | R4-F1 (accepted, 4 endorsements) identified that the Input Schema for `ServiceDependency` lacks the `evidence` field required by the Output Schema. R2-F1 (accepted) flagged the same issue. Despite both being accepted, the Input Schema dataclass definition in the feature doc has NOT been updated to include `evidence: str`. | Critical — This is the highest-endorsed suggestion across all rounds and remains unresolved in the document. Implementation will fail with AttributeError. | Add `evidence: Optional[str]` to the `ServiceDependency` dataclass in the Input Schema section, or remove `evidence` from the Output Schema and document it as derived. |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
|---|---|---|---|
| Problem Statement | Section 1 (Overview) | Full | — |
| Goal #1: Run Eagle | Phase 2, Step 5 (`run_eagle()`) | Full | — |
| Goal #2: Run ContextCore | Phase 3, Step 8 (`run_extract()`) | Full | — |
| Goal #3: Merge into context dict | Phase 5, Step 15 (`build_context()`) | Full | — |
| Goal #4: No LLM cost | Entire plan (no LLM imports) | Full | — |
| Input Schema: ProjectMetadata | Section 4 (Eagle transformation) | Partial | Missing imports for sub-types (R10-S4). Path format unspecified in plan despite R9-F1 acceptance (R10-S6). |
| Input Schema: ExtractionResult | Section 4 (ContextCore transformation) | Full | — |
| Output Schema: project_structure | Section 4 | Partial | Plan still uses `from`/`to` instead of `source_service`/`target_service` (R10-S1). |
| Output Schema: capability_map.by_file | Section 5 | Partial | Plan contradicts accepted R5-F3 on test inclusion (R10-S2). No `is_generated` cross-reference test (R10-S5). |
| Output Schema: capability_map.by_type | Section 4 | Full | — |
| Output Schema: capability_map.test_association_map | Section 6 | Partial | Plan still uses old name `test_coverage_map`. No test for heuristic boundary cases with normalized paths. |
| Output Schema: codebase_summary | Section 7 | Partial | No graceful degradation when Eagle fails (R10-S3). No markdown sanitization (R10-S9). |
| Design Decision #1: by_file for localization | Section 5 | Full | — |
| Design Decision #2: test_association_map | Section 6 | Full | — |
| Design Decision #3: codebase_summary as LLM-ready | Section 7 | Full | — |
| Design Decision #4: Deterministic, no LLM | Entire plan | Full | — |
| Architecture: ContextBridge class | Section 1, 3, 4, 5, 6, 7 | Full | — |
| Integration: With Eagle (library import + fallback) | Section 2, Phase 2 | Partial | Plan only implements library import path; no subprocess fallback implemented or tested. |
| Integration: With ContextCore (library import) | Section 2, Phase 3 | Full | — |
| Integration: With startd8-sdk (ExplorePhaseHandler) | Section 8 (`test_build_context_does_not_overwrite_existing`) | Full | R8-F4 accepted: returns only bridge-owned keys. |
| Limitation: Python-only extraction | Risk 2 mitigation, Section 7 | Full | — |
| Limitation: Service-per-directory | Risk 2 | Full | — |
| Limitation: No semantic analysis | Not explicitly tested | Partial | No test verifies the bridge makes no LLM calls — could add a mock-based assertion. |
| Limitation: Dynamic registrations (R7-F4) | Not in plan | None | Accepted R7-F4 added this limitation to the feature doc but the plan has no corresponding documentation or test caveat. |
| Estimated Effort: ~1 day | Section 3 (Phase 1-6 totals ~5.5 hours) | Full | — |
| Dependencies: Eagle, ContextCore | Section 2 | Full | — |
| Accepted: R1-F1 (rename from/to) | Section 4 | None | Plan still uses old key names (R10-S1). |
| Accepted: R1-F2 (paths relative to project_root) | Section 5 | Partial | Acknowledged in Risk 5 but no normalization step in plan (R10-S6). |
| Accepted: R4-F2 (docstring truncation 500 chars) | Not in plan | None | No implementation step or test for docstring truncation (R10-S7). |
| Accepted: R5-F1 (all category keys always present) | Section 5 | Partial | Logic mentions grouping but doesn't explicitly initialize all keys to `[]`. |
| Accepted: R6-F2 (is_generated in capability_map) | Not in plan | None | No implementation step or test for cross-referencing Eagle's `is_generated` into capability_map (R10-S5). |
| Accepted: R7-F3 (configurable timeout) | Not in plan | None | R7-F3 was accepted in Appendix A but also appears in Appendix B as rejected. Contradictory triage — needs resolution. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None — all prior Appendix C suggestions have been triaged into Appendix A or B. No untriaged suggestions remain.

#### Review Round R11
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 01:36:20 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R11-S1 | architecture | medium | Synthesize a `_root` or `misc` service in `project_structure` for files not assigned to any Eagle service. | R2-F2 (Applied) identified the need to handle orphan/root files, but the Plan's transformation logic (Section 4) does not explicitly include a step to collect these files and add them to the structure. Without this, root-level config files or scripts in flat projects will be missing from the `project_structure`. | Phase 2, Step 6 (`_transform_eagle`) | Unit test `test_transform_eagle_flat_project` verifying root files appear in a synthetic service. |
| R11-S2 | data | high | Enforce POSIX path separators (`/`) for all paths in the output `context` dict. | Mixed separators (Windows `\` vs Linux `/`) cause issues for LLM tokenization and break cross-referencing if the Bridge runs in a different environment than the consumer. Standardizing on `/` ensures consistency. | Phase 3, Step 9 & 10 (Path normalization util) | Unit test with Windows-style input paths verifying output is `/` separated. |
| R11-S3 | architecture | medium | Include `doc_sections` in the `by_file` index (reversing the exclusion in Section 5). | Excluding `doc_sections` makes documentation files (like `README.md`) appear empty to agents using the `by_file` index. Knowing a file has specific sections (e.g., "Installation", "API") is valuable for localization. | Phase 3, Step 10 (`_build_by_file_index`) | Unit test verifying `README.md` entry contains `doc_sections`. |
| R11-S4 | validation | medium | Sort services by `estimated_loc` (descending) before truncation in `codebase_summary`. | The plan mentions truncation at 15 services but doesn't specify sort order. Non-deterministic ordering (e.g., hash order) could produce different summaries on different runs. | Phase 4, Step 13 (`_render_codebase_summary`) | Unit test checking summary content stability and priority of large services. |
| R11-S5 | interfaces | high | Implement a fallback getter for `ServiceDependency.evidence` (e.g., `getattr(dep, "evidence", "Inferred")`). | R4-F1 identified that the input schema lacks `evidence`, but the output requires it. Until Eagle is updated, the code must handle the missing attribute to avoid `AttributeError`. | Phase 2, Step 6 (Transformation logic) | Unit test with `ServiceDependency` object lacking `evidence` field. |
| R11-S6 | data | medium | Verify method storage location in `ExtractionResult` and iterate `classes` children if necessary. | The Input Schema implies a flat list of `functions`, but if ContextCore stores methods nested within `classes` (and not in the top-level `functions` list), the current iteration logic will miss them. | Phase 3, Step 10 (`_build_by_file_index`) | Integration test with a class containing methods; verify methods appear in `by_file`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R9-F1: Critical for correct path joining. Without knowing if Eagle's path is service-relative or project-relative, the bridge cannot reliably construct the full path.

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R11-F1 | Input Schemas → `ServiceMetadata` | Missing Detail | `ServiceMetadata` has `name` but no `root_path`. If a service is nested (e.g. `backend/services/auth`), and `name` is just "auth", the bridge cannot reconstruct the project-relative path of its files to match ContextCore's paths. | High — Path joining fails for nested services. | Add `root_path` (relative to project root) to `ServiceMetadata` schema. |
| R11-F2 | Input Schemas → `ExtractedCapability` | Ambiguity | The schema does not specify if methods are included in the top-level `functions` list or nested within `classes`. | Medium — Potential data loss if methods are nested and not iterated. | Clarify if `functions` list includes class methods, or add `methods` field to `ExtractedCapability` for class objects. |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| :--- | :--- | :--- | :--- |
| **Context Bridge Goal** | Overview, Phase 1-6 | Full | |
| **Input: Eagle Schema** | Section 4, Phase 2 | Partial | Missing `root_path` handling (R11-F1). Handling of missing `evidence` (R11-S5). |
| **Input: ContextCore Schema** | Section 4, Phase 3 | Full | |
| **Output Schema** | Section 4, 5, 6, 7 | Full | |
| **Design: by_file index** | Section 5 | Partial | Excludes `doc_sections` (R11-S3). |
| **Design: test_coverage_map** | Section 6 | Full | |
| **Design: codebase_summary** | Section 7 | Partial | Sorting for determinism not specified (R11-S4). |
| **Design: Deterministic/No LLM** | Overview | Full | |
| **Integration: Eagle** | Section 3, Risk 1 | Full | |
| **Integration: ContextCore** | Section 3 | Full | |
| **Integration: startd8-sdk** | Section 3 (Phase 5) | Full | |
| **Limitations** | Section 10 | Full | |
