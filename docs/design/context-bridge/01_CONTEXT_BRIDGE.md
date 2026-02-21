# Context Bridge: Eagle + ContextCore Extract → startd8-sdk Context Dict

## Status: Not Built

## Problem

Eagle produces `eagle-decomposition.json` (macro project structure). ContextCore `capability-index extract` produces `raw_capabilities.yaml` (micro capability inventory). startd8-sdk's Artisan pipeline consumes a `context: dict[str, Any]` shared across all phases.

No adapter exists to merge the two deterministic analysis outputs into the format startd8-sdk expects.

## Goal

A lightweight adapter that:
1. Runs Eagle against a project root → gets `ProjectMetadata`
2. Runs ContextCore extract against the same root → gets `ExtractionResult`
3. Merges both into a single `context` dict compatible with startd8-sdk's phase handlers
4. Adds no LLM cost (purely deterministic)

## Input Schemas

### Eagle: ProjectMetadata

```python
@dataclass
class ProjectMetadata:
    project_id: str
    generated_at: str
    extractor: str
    extractor_version: str
    services: List[ServiceMetadata]       # service name, language, LOC, files, build system
    shared_assets: List[SharedAsset]      # files identical across services
    service_dependencies: List[ServiceDependency]  # runtime deps (gRPC, HTTP)
    input_sources: List[InputSource]      # provenance
    artifact_inventory: List[ArtifactEntry]

@dataclass
class ServiceMetadata:
    name: str
    language: str
    language_confidence: float
    estimated_loc: int
    files: List[FileInfo]                 # path, loc, size_bytes, is_generated
    build_system: Optional[str]
    dependency_manifest: Optional[str]
    dependency_manifest_contents: Optional[str]
    has_dockerfile: bool
    has_tests: bool
    protocols: List[str]
    extraction_source: str
```

### ContextCore: ExtractionResult

```python
@dataclass
class ExtractionResult:
    project_path: str
    project_name: str
    extracted_at: str
    cli_commands: list[ExtractedCapability]
    classes: list[ExtractedCapability]
    functions: list[ExtractedCapability]
    doc_sections: list[ExtractedCapability]
    tests: list[ExtractedCapability]
    api_endpoints: list[ExtractedCapability]

@dataclass
class ExtractedCapability:
    name: str
    source_type: str       # "cli", "class", "function", "doc", "test", "api"
    file_path: str
    line_number: Optional[int]
    docstring: Optional[str]
    signature: Optional[str]
    decorators: list
    parent: Optional[str]
```

## Output Schema

The merged context dict consumed by downstream startd8-sdk phases:

```python
context = {
    # Existing startd8-sdk keys (unchanged)
    "workflow_id": str,
    "project_root": str,
    "drafter_model": str,
    "validator_model": str,
    "reviewer_model": str,

    # New: Eagle macro structure
    "project_structure": {
        "project_id": str,
        "services": [
            {
                "name": str,
                "language": str,
                "estimated_loc": int,
                "build_system": str | None,
                "has_tests": bool,
                "has_dockerfile": bool,
                "protocols": [str],
                "files": [
                    {"path": str, "loc": int, "is_generated": bool}
                ],
            }
        ],
        "service_dependencies": [
            {"from": str, "to": str, "protocol": str, "evidence": str}
        ],
        "shared_assets": [
            {"filename": str, "services": [str], "sha256": str}
        ],
        "languages": [str],         # deduplicated
        "total_loc": int,
        "total_services": int,
    },

    # New: ContextCore micro capabilities
    "capability_map": {
        "project_name": str,
        "total_capabilities": int,
        "by_file": {
            "src/auth.py": {
                "classes": [{"name": str, "line": int, "signature": str, "docstring": str}],
                "functions": [{"name": str, "line": int, "signature": str, "docstring": str}],
                "api_endpoints": [{"name": str, "line": int, "signature": str}],
            }
        },
        "by_type": {
            "cli_commands": [ExtractedCapability.to_dict()],
            "classes": [...],
            "functions": [...],
            "api_endpoints": [...],
            "tests": [...],
            "doc_sections": [...],
        },
        "test_coverage_map": {
            "src/auth.py": ["test_login", "test_logout"],  # test names covering each file
        },
    },

    # New: Combined summary for LLM consumption
    "codebase_summary": str,
    # A concise markdown summary combining Eagle + Extract:
    # "Project: 8 services, 3 languages, 4200 total LOC.
    #  Services: emailservice (Python, 340 LOC, 12 functions, 8 tests), ...
    #  Dependencies: emailservice → paymentservice (gRPC), ...
    #  Entry points: 4 CLI commands, 6 API endpoints, 23 public classes"
}
```

## Design Decisions

### 1. by_file index for localization

The `capability_map.by_file` index is the key addition. When the agent explores an issue, it needs to quickly answer "what's in this file?" without reading it. This index provides instant lookup.

### 2. test_coverage_map for validation

Maps source files to their test functions. Enables the DESIGN phase to know which tests already exist for affected files, and the TEST phase to know which tests to run.

### 3. codebase_summary as LLM-ready text

A pre-rendered markdown summary that can be injected directly into LLM prompts. Saves tokens vs passing raw JSON — the LLM gets a concise overview, and can request specific details from `project_structure` or `capability_map` if needed.

### 4. Deterministic, no LLM

The bridge itself uses zero tokens. It's a pure data transformation: Eagle JSON + Extract YAML → context dict. The LLM only enters the picture in downstream phases.

## Architecture

```
┌──────────────────────────────────────────────┐
│ ContextBridge                                 │
│                                               │
│  __init__(project_root: Path)                 │
│                                               │
│  run_eagle() → ProjectMetadata                │
│    - Calls eagle.extractors.RepoScanner       │
│    - Or shells out: eagle.py --reference-dir   │
│                                               │
│  run_extract() → ExtractionResult             │
│    - Calls capability_extractor.run_extraction │
│    - Or shells out: contextcore capability-    │
│      index extract                             │
│                                               │
│  build_context() → dict[str, Any]             │
│    - Runs Eagle + Extract                      │
│    - Transforms to output schema               │
│    - Builds by_file index                      │
│    - Builds test_coverage_map                  │
│    - Renders codebase_summary                  │
│    - Returns merged context dict               │
│                                               │
│  Cost: $0.00 | Time: ~3-8 seconds             │
└──────────────────────────────────────────────┘
```

## Integration Points

### With Eagle

Two options:
- **Library import**: `from eagle.extractors.repo_scanner import RepoScanner` + `from eagle.decomposer import Decomposer` — tighter coupling, faster
- **Subprocess**: `eagle.py --reference-dir <path> --project <id> --json` — looser coupling, Eagle stays independent

Recommendation: **Library import** for the bridge, with a fallback subprocess path for environments where Eagle isn't installed as a package.

### With ContextCore

Two options:
- **Library import**: `from contextcore.utils.capability_extractor import run_extraction` — direct
- **CLI**: `contextcore capability-index extract <path> -o <output_dir>` — independent

Recommendation: **Library import**. ContextCore is already a dependency of startd8-sdk (via the Beaver integration).

### With startd8-sdk

The bridge is called inside the ExplorePhaseHandler (see `02_TOOL_USING_PHASE_HANDLER.md`):

```python
class ExplorePhaseHandler(AbstractPhaseHandler):
    def execute(self, phase, context, dry_run=False):
        bridge = ContextBridge(Path(context["project_root"]))
        merged = bridge.build_context()
        context.update(merged)
        # ... then do targeted agent exploration
```

## Limitations

- **ContextCore extract is Python-only** — AST parsing only works for Python files. Eagle handles multi-language at the macro level, but the micro capability map will be empty for Go/Java/JS services.
- **Eagle expects service-per-directory** — projects that aren't organized as service directories need a different extraction strategy.
- **No semantic analysis** — neither tool understands what the code *does*, only what *exists*. Semantic understanding comes from the LLM in the localization step.

## Estimated Effort

~1 day:
- 4 hours: Implement ContextBridge class with Eagle + Extract integration
- 2 hours: Build by_file index and test_coverage_map transformations
- 2 hours: Render codebase_summary markdown
- Unit tests for each transformation

## Dependencies

- `eagle` (Python package or available on PATH)
- `contextcore` (Python package — already a startd8-sdk dependency)
- No new external dependencies

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Rename `from`/`to` keys in service_dependencies to avoid Python reserved word conflicts. | claude-4 (claude-opus-4-6) | 3 endorsements and `from` is indeed a Python reserved keyword that causes real issues with kwargs unpacking and attribute access patterns. Renaming to `source_service`/`target_service` is a low-cost, high-clarity improvement. | 2026-02-20 01:07:56 UTC |
| R1-F2 | Explicitly specify that all `by_file` paths are relative to `project_root`. | claude-4 (claude-opus-4-6) | 1 endorsement but this is critical for correctness — the Eagle/ContextCore path mismatch (Risk 5) makes this ambiguity dangerous. Pinning the path format is essential for cross-referencing to work at all. | 2026-02-20 01:07:56 UTC |
| R1-F3 | Specify the format of test identifiers in `test_coverage_map` (function name vs fully qualified). | claude-4 (claude-opus-4-6) | Downstream consumers need to know whether they can locate tests from the map alone. Specifying the format (e.g., `test_name` or `file_path::test_name`) eliminates ambiguity. | 2026-02-20 01:07:56 UTC |
| R1-F4 | Document expected behavior for co-located tests and non-standard test file layouts. | claude-4 (claude-opus-4-6) | The heuristic assumes a `tests/` directory structure. Co-located tests, conftest.py, and inline tests are common Python patterns that would produce incorrect or empty coverage maps without guidance. | 2026-02-20 01:07:56 UTC |
| R1-F5 | Specify a target token budget and truncation strategy for `codebase_summary`. | claude-4 (claude-opus-4-6) | The stated purpose is to save tokens vs passing raw JSON. Without a size constraint, large projects could produce summaries that defeat this purpose. A target range (e.g., 200-500 tokens) and truncation strategy are necessary. | 2026-02-20 01:07:56 UTC |
| R1-F7 | Specify merge semantics for `context.update(merged)` — overwrite, deep-merge, or raise on conflict. | claude-4 (claude-opus-4-6) | Silent overwrites of existing context keys could cause data loss on re-runs or when other components populate the same keys. The integration example needs explicit merge semantics documented. | 2026-02-20 01:07:56 UTC |
| R2-F1 | Clarify whether `evidence` in `service_dependencies` is derived or from Eagle's input schema. | gemini-3 (gemini-3-pro-preview) | 2 endorsements. This is the same issue as R4-F1 — the input schema doesn't list `evidence` on `ServiceDependency`. Must resolve whether to add it to input schema or derive it. | 2026-02-20 01:07:56 UTC |
| R2-F2 | Specify handling of files that exist in ContextCore but belong to no Eagle service (orphan files). | gemini-3 (gemini-3-pro-preview) | 3 endorsements. Root-level scripts, utility files, and other orphans are common in real projects. Without a policy (e.g., add to a `_root` or `_misc` service, or include in `capability_map` only), these files are silently lost or cause errors. | 2026-02-20 01:07:56 UTC |
| R3-F2 | Clarify whether `None` fields from `vars()` should be retained or omitted in capability dicts. | claude-4 (claude-opus-4-6) | Previously accepted. Consistent null-handling is necessary for downstream consumers to know what to expect in the JSON output. | 2026-02-20 01:07:56 UTC |
| R3-F3 | Specify that `test_coverage_map` is always present, defaulting to `{}` when no tests found. | claude-4 (claude-opus-4-6) | Downstream consumers need a consistent contract — checking for key existence vs empty dict is a common source of bugs. Stating it's always present with `{}` default is simple and clear. | 2026-02-20 01:07:56 UTC |
| R3-F4 | Clarify that the bridge should run once in Explore phase with output persisting in context for subsequent phases. | claude-4 (claude-opus-4-6) | Without lifecycle documentation, the bridge may run redundantly in multi-phase pipelines, wasting time. This is a simple documentation addition with real performance implications. | 2026-02-20 01:07:56 UTC |
| R4-F1 | Resolve mismatch: Output Schema requires `service_dependencies[].evidence` but Input Schema for `ServiceDependency` lacks this field. | gemini-3 (gemini-3-pro-preview) | 3 endorsements. This is a concrete bug — implementation will fail with `AttributeError`. Either the input schema must be updated to include `evidence` or it must be removed/derived in the output schema. | 2026-02-20 01:07:56 UTC |
| R4-F2 | Add a length constraint (e.g., 500 chars) for docstrings in `capability_map`. | gemini-3 (gemini-3-pro-preview) | 2 endorsements. Large docstrings or license headers mistakenly parsed as docstrings will bloat the context dict. A truncation limit is a simple safeguard against token waste. | 2026-02-20 01:07:56 UTC |
| R5-F1 | Specify that all category keys (`classes`, `functions`, `api_endpoints`, `cli_commands`) are always present in each `by_file` entry, defaulting to `[]`. | claude-4 (claude-opus-4-6) | Consistent key presence prevents `KeyError` in downstream consumers. This is a simple contract that avoids the ambiguity between missing keys and empty lists. | 2026-02-20 01:07:56 UTC |
| R5-F2 | Clarify that `codebase_summary` is for LLM prompt injection only and must not be machine-parsed. | claude-4 (claude-opus-4-6) | Establishing this contract prevents downstream phases from building fragile regex parsers against a human-readable string. Structured data should come from `project_structure` or `capability_map`. | 2026-02-20 01:07:56 UTC |
| R5-F3 | Resolve contradiction: `by_file` excludes tests but design goal is to answer 'what's in this file?' for any file including test files. | claude-4 (claude-opus-4-6) | This is a genuine contradiction in the spec. Either test files should be included in `by_file` or the doc should explicitly state `by_file` is source-code-only and test file lookups use `by_type.tests`. | 2026-02-20 01:07:56 UTC |
| R5-F5 | Specify ordering of `languages` list (alphabetical or by LOC) for deterministic output. | claude-4 (claude-opus-4-6) | Non-deterministic ordering causes flaky tests and inconsistent summaries across runs. Specifying alphabetical sort is trivial to implement and ensures reproducibility. | 2026-02-20 01:07:56 UTC |
| R6-F1 | Define 'public' in the summary context as names not starting with `_`. | gemini-3 (gemini-3-pro-preview) | 1 endorsement. Without a definition, the summary's 'public classes/functions' count is ambiguous. Python's underscore convention is the natural choice and easy to implement. | 2026-02-20 01:07:56 UTC |
| R6-F2 | Add `is_generated` boolean to `capability_map` entries, derived from Eagle's file status. | gemini-3 (gemini-3-pro-preview) | 1 endorsement. Previously accepted. Agents using the capability map need to know if code is auto-generated to avoid suggesting edits that will be overwritten. | 2026-02-20 01:07:56 UTC |
| R7-F2 | Rename `test_coverage_map` to `test_association_map` or add explicit documentation that it's a heuristic filename association, not execution-based coverage. | claude-4 (claude-opus-4-6) | The term 'coverage' strongly implies execution-based analysis (like coverage.py). Using it for a filename heuristic could mislead agents and downstream consumers into treating it as authoritative coverage data. A clarifying rename or prominent documentation note is low-cost and prevents misuse. | 2026-02-20 01:07:56 UTC |
| R7-F4 | Add a fourth limitation documenting that dynamic registrations (runtime routes, programmatic CLI commands, monkey-patched classes) are not captured by static AST extraction. | claude-4 (claude-opus-4-6) | This is a common and important limitation of AST-based extraction, especially in Python web frameworks (Flask, FastAPI with dynamic routes). Documenting it prevents agents from assuming the capability map is complete and sets appropriate expectations. | 2026-02-20 01:07:56 UTC |
| R1-F1 | Rename `from`/`to` keys in service_dependencies to `source_service`/`target_service` to avoid Python reserved word conflicts. | claude-4 (claude-opus-4-6) | 3 endorsements, `from` is a Python reserved word causing real usability issues with kwargs unpacking and dataclass fields. High-impact, low-cost fix. | 2026-02-20 01:32:05 UTC |
| R1-F2 | Explicitly specify that all paths in `by_file` keys are relative to `project_root`. | claude-4 (claude-opus-4-6) | 2 endorsements, path format ambiguity is a critical interoperability issue between Eagle and ContextCore outputs. Without this, cross-referencing breaks. | 2026-02-20 01:32:05 UTC |
| R1-F3 | Specify the format of test identifiers in test_coverage_map (file_path::test_name vs just test_name). | claude-4 (claude-opus-4-6) | Downstream consumers need to locate tests from the map alone. Without a specified format, the map is ambiguous and potentially unusable. | 2026-02-20 01:32:05 UTC |
| R1-F4 | Add examples of expected behavior for co-located tests and conftest files in the input schema. | claude-4 (claude-opus-4-6) | Non-standard test layouts are common in Python projects. Without guidance, the heuristic will produce incorrect or empty coverage maps for these cases. | 2026-02-20 01:32:05 UTC |
| R1-F5 | Specify a target token range and truncation strategy for the codebase_summary. | claude-4 (claude-opus-4-6) | For large projects the summary could become unbounded, defeating its stated purpose of saving tokens. A token budget is essential for LLM prompt injection use cases. | 2026-02-20 01:32:05 UTC |
| R1-F7 | Specify merge semantics (overwrite, deep-merge, or raise on conflict) for repeated build_context() calls. | claude-4 (claude-opus-4-6) | Silent overwriting on re-runs could cause data loss. The merge contract must be explicit to prevent subtle bugs in multi-phase pipelines. | 2026-02-20 01:32:05 UTC |
| R2-F1 | Clarify whether `evidence` in service_dependencies is derived or if the Input Schema is incomplete. | gemini-3 (gemini-3-pro-preview) | 2 endorsements. The output schema requires `evidence` but the input schema doesn't list it. This ambiguity will cause AttributeError at runtime or require guessing. | 2026-02-20 01:32:05 UTC |
| R2-F2 | Clarify handling of files that exist in ContextCore but belong to no Eagle service (hybrid/orphan files). | gemini-3 (gemini-3-pro-preview) | 3 endorsements. Without this, files in the project root or outside service directories silently disappear from the structured output, leaving gaps agents can't explain. | 2026-02-20 01:32:05 UTC |
| R3-F2 | Clarify whether None fields in ExtractedCapability.to_dict() output should be omitted or included as null. | claude-4 (claude-opus-4-6) | Consistency in JSON output affects downstream consumers' null-handling logic. Specifying this contract prevents inconsistent implementations. | 2026-02-20 01:32:05 UTC |
| R3-F3 | State that test_coverage_map is always present in the output, defaulting to empty dict when no tests are found. | claude-4 (claude-opus-4-6) | Downstream consumers need to know whether to check for key existence or handle empty dict. An always-present key simplifies consumer code. | 2026-02-20 01:32:05 UTC |
| R3-F4 | Clarify that the bridge runs once in Explore phase and its output persists in context for subsequent phases. | claude-4 (claude-opus-4-6) | Without lifecycle documentation, the bridge may be redundantly invoked in multiple phases, wasting compute and potentially causing inconsistency. | 2026-02-20 01:32:05 UTC |
| R4-F1 | Resolve the mismatch: Output Schema requires `evidence` in service_dependencies but Input Schema for ServiceDependency doesn't list it. | gemini-3 (gemini-3-pro-preview) | 4 endorsements — highest endorsement count. This is a concrete implementation blocker that will cause AttributeError. Must be resolved before coding begins. | 2026-02-20 01:32:05 UTC |
| R4-F2 | Truncate docstrings in capability_map to 500 characters to prevent token bloat. | gemini-3 (gemini-3-pro-preview) | 2 endorsements. Large docstrings or license headers parsed as docstrings can significantly bloat the context dict, consuming tokens in downstream phases unnecessarily. | 2026-02-20 01:32:05 UTC |
| R5-F1 | Specify that all category keys (classes, functions, api_endpoints, cli_commands) are always present in each by_file entry, defaulting to empty list. | claude-4 (claude-opus-4-6) | Prevents KeyError in downstream code and establishes a consistent contract. Low implementation cost with high usability benefit. | 2026-02-20 01:32:05 UTC |
| R5-F2 | Clarify that codebase_summary is for LLM prompt injection only and must not be machine-parsed. | claude-4 (claude-opus-4-6) | Prevents downstream phases from coupling to the summary format via regex parsing, which would make format changes breaking. | 2026-02-20 01:32:05 UTC |
| R5-F3 | Resolve contradiction between stated goal ('what's in this file?') and plan's exclusion of tests from by_file. | claude-4 (claude-opus-4-6) | The design decision's stated goal contradicts the implementation plan. This must be explicitly resolved — either include tests in by_file or document that by_file is source-only. | 2026-02-20 01:32:05 UTC |
| R5-F5 | Specify ordering for the `languages` list (alphabetical or by LOC) for deterministic output. | claude-4 (claude-opus-4-6) | Non-deterministic ordering causes flaky tests and inconsistent summaries across runs. Specifying alphabetical ordering is trivial to implement and ensures reproducibility. | 2026-02-20 01:32:05 UTC |
| R6-F1 | Define 'public' in the context of the summary as 'names not starting with `_`'. | gemini-3 (gemini-3-pro-preview) | 1 endorsement. Without this definition, the summary's 'public classes/functions' count is meaningless. Python's underscore convention is the natural choice. | 2026-02-20 01:32:05 UTC |
| R6-F2 | Add `is_generated` boolean to capability_map entries, derived from Eagle's file status. | gemini-3 (gemini-3-pro-preview) | 1 endorsement. Without this, agents may attempt to modify auto-generated code, leading to changes that get overwritten. Cross-referencing Eagle's file metadata into capability_map prevents this. | 2026-02-20 01:32:05 UTC |
| R7-F2 | Rename test_coverage_map to test_association_map or add prominent documentation that it's heuristic-based, not execution-based coverage. | claude-4 (claude-opus-4-6) | The word 'coverage' implies execution-based coverage which this is not. Misleading terminology could cause agents or downstream consumers to overestimate confidence in test associations. | 2026-02-20 01:32:05 UTC |
| R7-F3 | Specify a configurable timeout for build_context() to prevent indefinite blocking on large repos. | claude-4 (claude-opus-4-6) | 1 endorsement. Eagle's RepoScanner scanning a massive monorepo could hang indefinitely. A timeout with a clear exception type is essential for pipeline reliability. | 2026-02-20 01:32:05 UTC |
| R7-F4 | Add a limitation noting that dynamic registrations (runtime routes, programmatic CLI commands, monkey-patching) are not captured by static AST extraction. | claude-4 (claude-opus-4-6) | This is a common Python pattern (Flask, Click, Django) that systematically produces incomplete capability maps. Documenting it prevents agents from assuming completeness. | 2026-02-20 01:32:05 UTC |
| R8-F1 | Update the feature doc's by_file example to show all always-present keys including cli_commands, consistent with accepted R5-F1. | claude-4 (claude-opus-4-6) | The feature doc is the canonical reference. Its example contradicts accepted R5-F1 (all category keys always present), which will confuse implementers. | 2026-02-20 01:32:05 UTC |
| R8-F2 | Update the Output Schema in the feature doc to use source_service/target_service instead of from/to, consistent with accepted R1-F1. | claude-4 (claude-opus-4-6) | The feature doc is the canonical schema reference. Leaving it with the old from/to keys directly contradicts the accepted R1-F1 and will cause consumers to implement the wrong schema. | 2026-02-20 01:32:05 UTC |
| R8-F3 | Update all references to test_coverage_map in the feature doc to test_association_map, consistent with accepted R7-F2. | claude-4 (claude-opus-4-6) | The canonical document must reflect accepted naming changes. Multiple references throughout the feature doc still use the old name, creating confusion. | 2026-02-20 01:32:05 UTC |
| R8-F4 | Clarify that build_context() returns only the three bridge-owned keys and does not include existing context keys. | claude-4 (claude-opus-4-6) | Without this clarification, an implementation that returns a full context dict could silently overwrite pipeline-managed keys like workflow_id. The return contract must be explicit. | 2026-02-20 01:32:05 UTC |
| R9-F1 | Explicitly state in the Input Schema whether Eagle's FileInfo.path is service-relative or project-relative. | gemini-3 (gemini-3-pro-preview) | This is the root cause of the path normalization issue flagged by R8-S5, R9-S2, and Risk 5. Pinning down the input format in the schema is prerequisite to implementing correct normalization logic. | 2026-02-20 01:32:05 UTC |
| R1-F1 | Rename `from`/`to` keys to `source_service`/`target_service` to avoid Python reserved word conflicts. | claude-4 (claude-opus-4-6) | 3 endorsements, `from` is a Python reserved word causing awkward access patterns, and this has been accepted in prior rounds (R1-S* context). Concrete, low-cost fix. | 2026-02-20 01:39:21 UTC |
| R1-F2 | Specify that all paths in `by_file` keys are relative to `project_root`. | claude-4 (claude-opus-4-6) | 2 endorsements, path format ambiguity is a critical cross-referencing issue (ties to Risk 5 and R9-F1). Essential for correctness. | 2026-02-20 01:39:21 UTC |
| R1-F3 | Specify the format of test identifiers in `test_coverage_map` (file_path::test_name vs just test_name). | claude-4 (claude-opus-4-6) | Downstream consumers need unambiguous test identifiers to locate tests. Without this, the map is unreliable. | 2026-02-20 01:39:21 UTC |
| R1-F4 | Add examples of expected behavior for co-located tests and conftest files. | claude-4 (claude-opus-4-6) | Non-standard test layouts are common in Python projects. Without guidance, the heuristic will silently produce incorrect mappings. | 2026-02-20 01:39:21 UTC |
| R1-F5 | Specify a target token range and truncation strategy for `codebase_summary`. | claude-4 (claude-opus-4-6) | Without a size constraint, large projects could produce summaries that defeat the stated purpose of saving tokens. Practical concern for LLM prompt injection. | 2026-02-20 01:39:21 UTC |
| R1-F7 | Specify merge semantics for `context.update(merged)` — overwrite, deep-merge, or raise on conflict. | claude-4 (claude-opus-4-6) | Silent overwrite of existing context keys is a real data loss risk. The contract must be explicit to prevent bugs in multi-phase pipelines. | 2026-02-20 01:39:21 UTC |
| R2-F1 | Clarify whether `evidence` in `service_dependencies` is derived or from Eagle's input schema. | gemini-3 (gemini-3-pro-preview) | 2 endorsements. This is the same issue as R4-F1 (4 endorsements). The input schema genuinely lacks `evidence`, creating an implementation gap. | 2026-02-20 01:39:21 UTC |
| R2-F2 | Specify behavior for files that exist in ContextCore but belong to no Eagle service (hybrid/orphan files). | gemini-3 (gemini-3-pro-preview) | Flat projects or root-level scripts are common. Without a spec, these files silently disappear from `project_structure`. | 2026-02-20 01:39:21 UTC |
| R3-F2 | Clarify whether `None` fields in `ExtractedCapability.to_dict()` output should be omitted or included as `null`. | claude-4 (claude-opus-4-6) | Affects JSON size and downstream null-handling. A clear convention prevents inconsistencies. | 2026-02-20 01:39:21 UTC |
| R3-F3 | State that `test_coverage_map` (now `test_association_map`) is always present, even if empty `{}`. | claude-4 (claude-opus-4-6) | Key existence vs empty dict is a fundamental contract question. Downstream code needs to know whether to check for presence. | 2026-02-20 01:39:21 UTC |
| R3-F4 | Clarify that the bridge runs once in Explore phase and output persists in context for subsequent phases. | claude-4 (claude-opus-4-6) | Without lifecycle documentation, implementers may re-run the bridge in every phase, wasting time. Simple clarification with real impact. | 2026-02-20 01:39:21 UTC |
| R4-F1 | Resolve that `ServiceDependency` input schema lacks the `evidence` field required by the output schema. | gemini-3 (gemini-3-pro-preview) | 4 endorsements — highest across all rounds. Implementation will fail with AttributeError. This is a blocking schema inconsistency. | 2026-02-20 01:39:21 UTC |
| R4-F2 | Add requirement to truncate docstrings in `capability_map` to 500 characters. | gemini-3 (gemini-3-pro-preview) | 2 endorsements. Large docstrings or mistakenly parsed license headers will bloat context and waste tokens. Simple, effective constraint. | 2026-02-20 01:39:21 UTC |
| R5-F1 | Specify that all category keys (`classes`, `functions`, `api_endpoints`, `cli_commands`) are always present in `by_file` entries, defaulting to `[]`. | claude-4 (claude-opus-4-6) | Prevents KeyError in downstream consumers. Standard practice for schema contracts. | 2026-02-20 01:39:21 UTC |
| R5-F2 | Clarify that `codebase_summary` is for LLM prompt injection only and must not be machine-parsed. | claude-4 (claude-opus-4-6) | Prevents downstream phases from building brittle regex parsers against a human-readable string. Important contract clarification. | 2026-02-20 01:39:21 UTC |
| R5-F3 | Resolve the contradiction between the design goal ('what's in this file?') and the plan's exclusion of tests from `by_file`. | claude-4 (claude-opus-4-6) | The plan explicitly excludes tests from `by_file` which contradicts the stated agent use case. Must be resolved for consistent behavior. | 2026-02-20 01:39:21 UTC |
| R5-F5 | Specify ordering of `languages` list (alphabetical or by LOC). | claude-4 (claude-opus-4-6) | Non-deterministic ordering across runs is a testing and reproducibility issue. Simple fix — pick alphabetical and document it. | 2026-02-20 01:39:21 UTC |
| R6-F1 | Define 'public' in the summary context as 'names not starting with `_`'. | gemini-3 (gemini-3-pro-preview) | Without a definition, the summary may overstate the public API surface. Python's underscore convention is the obvious choice. | 2026-02-20 01:39:21 UTC |
| R6-F2 | Add `is_generated` boolean to `capability_map` entries, derived from Eagle's file metadata. | gemini-3 (gemini-3-pro-preview) | Agents modifying generated code will have changes overwritten. This cross-source enrichment is valuable and directly actionable. | 2026-02-20 01:39:21 UTC |
| R7-F2 | Rename `test_coverage_map` to `test_association_map` to avoid implying execution-based coverage. | claude-4 (claude-opus-4-6) | The heuristic is filename-based, not execution-based. 'Coverage' is misleading and could cause agents to make incorrect assumptions about test completeness. | 2026-02-20 01:39:21 UTC |
| R7-F3 | Specify a configurable timeout for `build_context()` with a `ContextBridgeTimeout` exception. | claude-4 (claude-opus-4-6) | Eagle scanning a massive monorepo could hang indefinitely, blocking the entire pipeline. A 60s default timeout is a simple safety net. | 2026-02-20 01:39:21 UTC |
| R7-F4 | Add limitation documenting that dynamic registrations (runtime routes, programmatic CLI commands) are not captured by static AST extraction. | claude-4 (claude-opus-4-6) | Common in Flask, Click, and other Python frameworks. Agents assuming completeness will make incorrect decisions. Low-cost documentation addition. | 2026-02-20 01:39:21 UTC |
| R8-F1 | Update the `by_file` example in the Output Schema to show all always-present keys including `cli_commands`. | claude-4 (claude-opus-4-6) | The example contradicts three accepted suggestions (R5-F1, R5-F3, R8-F1). Implementers copy examples — this must be correct. | 2026-02-20 01:39:21 UTC |
| R8-F2 | Update the Output Schema's `service_dependencies` to use `source_service`/`target_service` keys. | claude-4 (claude-opus-4-6) | R1-F1 was accepted but never applied to the canonical schema. The feature doc is the primary implementer reference. | 2026-02-20 01:39:21 UTC |
| R8-F3 | Search-and-replace `test_coverage_map` with `test_association_map` throughout the feature doc. | claude-4 (claude-opus-4-6) | R7-F2 was accepted but the document still uses the old name everywhere. Consistency between accepted decisions and the document is critical. | 2026-02-20 01:39:21 UTC |
| R8-F4 | Clarify that `build_context()` returns only the three bridge-owned keys, not existing context keys. | claude-4 (claude-opus-4-6) | If the method echoes back pipeline-managed keys like `workflow_id`, `context.update()` could silently overwrite them. Clear contract prevents data loss. | 2026-02-20 01:39:21 UTC |
| R9-F1 | Explicitly state whether Eagle's `FileInfo.path` is service-relative or project-relative, and require the bridge to normalize. | gemini-3 (gemini-3-pro-preview) | 1 endorsement. This is the root cause of Risk 5 (path prefix mismatch). Without knowing Eagle's path format, the bridge cannot correctly cross-reference files. | 2026-02-20 01:39:21 UTC |
| R10-F1 | Update the `by_file` example in the feature doc to show all six category keys with empty-list defaults. | claude-4 (claude-opus-4-6) | The canonical schema example contradicts three accepted suggestions (R5-F1, R5-F3, R8-F1). This is the single most impactful doc fix for implementer clarity. | 2026-02-20 01:39:21 UTC |
| R10-F2 | Apply the accepted R1-F1 and R8-F2 key renames (`source_service`/`target_service`) to the actual Output Schema code block. | claude-4 (claude-opus-4-6) | Flagged and accepted twice but never applied. This is now a process failure — must be treated as a blocking pre-implementation task. | 2026-02-20 01:39:21 UTC |
| R10-F3 | Search-and-replace all instances of `test_coverage_map` with `test_association_map` in the feature doc. | claude-4 (claude-opus-4-6) | Same as R8-F3 — accepted changes not applied to the document. Duplicate but reinforces the need to actually make the change. | 2026-02-20 01:39:21 UTC |
| R10-F4 | Add `evidence: Optional[str]` to the `ServiceDependency` dataclass in the Input Schema, or remove it from the Output Schema. | claude-4 (claude-opus-4-6) | Highest-endorsed suggestion across all rounds (4 endorsements via R4-F1). Remains unresolved despite being accepted twice. Implementation will fail with AttributeError. | 2026-02-20 01:39:21 UTC |
| R11-F1 | Add `root_path` (relative to project root) to `ServiceMetadata` schema for nested service path reconstruction. | gemini-3 (gemini-3-pro-preview) | Without `root_path`, the bridge cannot reconstruct project-relative paths for nested services like `backend/services/auth` where `name` is just 'auth'. Directly impacts path normalization (R10-S6). | 2026-02-20 01:39:21 UTC |
| R11-F2 | Clarify whether class methods are in the top-level `functions` list or nested within `classes` in `ExtractionResult`. | gemini-3 (gemini-3-pro-preview) | Same issue as R11-S6 — if methods are nested, the bridge must iterate class children. The input schema must be explicit about this structure. | 2026-02-20 01:39:21 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R5-F4 | Update effort estimate from ~1 day to ~2 days to account for expanded scope from review suggestions. |  | While the observation is valid, effort estimates in planning documents are living artifacts that the implementing team adjusts naturally. This is a project management concern, not an architectural suggestion that changes the implementation plan's technical content. | 2026-02-20 01:00:59 UTC |
| R1-F6 | Specify handling of non-Python files in `capability_map` with an `unsupported` marker. | claude-4 (claude-opus-4-6) | Adding unsupported language markers for every non-Python file would bloat the capability map significantly. The simpler approach (already implied) is that non-Python files simply don't appear in `by_file` — the limitation is already documented. Consumers can cross-reference with Eagle's file list to identify unanalyzed files. | 2026-02-20 01:07:56 UTC |
| R3-F1 | Specify thread-safety or reentrancy semantics for `ContextBridge`. | claude-4 (claude-opus-4-6) | Already addressed — R3-S1 and R3-S2 were previously accepted, which documented concurrency semantics. This is a duplicate concern. | 2026-02-20 01:07:56 UTC |
| R5-F4 | Update effort estimate from ~1 day to ~2 days due to expanded scope from accepted suggestions. | claude-4 (claude-opus-4-6) | Effort estimates are operational planning concerns, not architectural requirements. The estimate will naturally be revised during sprint planning. This doesn't belong in the architecture review. | 2026-02-20 01:07:56 UTC |
| R7-F1 | Add `max_files_per_service` parameter with truncation for large services. | claude-4 (claude-opus-4-6) | This adds premature optimization complexity. The bridge should faithfully transform Eagle's output. If file lists are too large, that's a concern for the downstream consumer or for Eagle's scanning configuration. Adding truncation parameters and flags increases the API surface for a speculative problem. | 2026-02-20 01:07:56 UTC |
| R7-F3 | Add a configurable timeout for `build_context()` with a `ContextBridgeTimeout` exception. | claude-4 (claude-opus-4-6) | Timeout management is typically handled at the pipeline/orchestration layer (startd8-sdk), not within individual components. Adding timeout logic to a synchronous data transformation layer adds complexity. If Eagle hangs, the pipeline's own timeout or process management should handle it. | 2026-02-20 01:07:56 UTC |
| R1-F6 | Specify handling of non-Python files in capability_map with an unsupported language marker. | claude-4 (claude-opus-4-6) | ContextCore is Python-only by design and the feature doc acknowledges this. Adding unsupported-language markers adds complexity for minimal value — non-Python files simply won't appear in capability_map, which is the expected behavior. Downstream consumers can infer this from the limitation. | 2026-02-20 01:32:05 UTC |
| R3-F1 | Specify thread-safety or reentrancy semantics for ContextBridge. | claude-4 (claude-opus-4-6) | The bridge is a deterministic data transformer called once in the Explore phase. Thread-safety concerns are premature — the pipeline is single-threaded by design and no concurrent use case is described. A simple documentation note suffices but doesn't warrant an architectural change. | 2026-02-20 01:32:05 UTC |
| R5-F4 | Update effort estimate from ~1 day to ~2 days to account for expanded scope from accepted suggestions. | claude-4 (claude-opus-4-6) | While the observation is valid, effort estimates are operational planning concerns, not architectural decisions. The plan can adjust timelines during sprint planning without a formal requirements change. | 2026-02-20 01:32:05 UTC |
| R7-F1 | Add configurable max_files_per_service parameter with truncation for large services. | claude-4 (claude-opus-4-6) | Premature optimization. The feature doc targets Python projects where 1000+ files per service is rare. The summary already truncates at 15 services. If file arrays become problematic, this can be added in a future iteration without schema changes. | 2026-02-20 01:32:05 UTC |
| R1-F6 | Specify handling of non-Python files in `capability_map` (absent vs empty with language marker). | claude-4 (claude-opus-4-6) | The doc already acknowledges Python-only extraction as a limitation. Adding `language: unsupported` markers adds schema complexity for marginal value. Non-Python files simply won't appear in capability_map, which is self-consistent. | 2026-02-20 01:39:21 UTC |
| R3-F1 | Specify thread-safety or reentrancy semantics for `ContextBridge`. | claude-4 (claude-opus-4-6) | This is a deterministic data transformer in a pipeline context. Concurrent usage is not a realistic scenario for v1. Over-engineering for a non-existent concurrency model. | 2026-02-20 01:39:21 UTC |
| R5-F4 | Update effort estimate from ~1 day to ~2 days due to expanded scope from accepted suggestions. | claude-4 (claude-opus-4-6) | Effort estimates are operational guidance, not architectural requirements. This is a project management concern, not a schema/design issue needing formal acceptance. | 2026-02-20 01:39:21 UTC |
| R7-F1 | Add configurable `max_files_per_service` parameter with truncation for large services. | claude-4 (claude-opus-4-6) | Premature optimization. The bridge produces a dict consumed by the pipeline — if truncation is needed, it can be added later. Adding truncation now complicates the initial implementation without evidence of real-world impact. | 2026-02-20 01:39:21 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 00:49:10 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

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

#### Review Round R2

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 00:49:46 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Issue | Description |
|---|---|---|
| R2-F1 | Ambiguity | The Output Schema requires `evidence` in `service_dependencies`. The Input Schema for Eagle's `ServiceDependency` does not explicitly list an `evidence` field (it lists `protocol`). Clarify if `evidence` should be derived (e.g., "Inferred from gRPC import") or if the Input Schema definition was incomplete. |
| R2-F2 | Missing Requirement | The Requirements do not specify behavior for "Hybrid" paths where a file exists in ContextCore (e.g., a script in root) but belongs to no Eagle service. Clarify if these should be added to a "misc" service entry or left as orphans in `capability_map` only. |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 00:53:04 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Architecture → ContextBridge | Missing Detail | The architecture diagram shows `build_context() → dict[str, Any]` but doesn't specify thread-safety or reentrancy semantics. If multiple Artisan pipelines share a process (e.g., in a web server or test runner), concurrent `build_context()` calls on different project roots could interfere via shared state (e.g., if Eagle or ContextCore use module-level globals). | Medium — concurrency bugs in CI or server deployments | State explicitly that `ContextBridge` instances are not thread-safe, or make them so by ensuring no shared mutable state; document single-threaded usage expectation |
| R3-F2 | Output Schema → `capability_map.by_type` | Ambiguity | `by_type` values are described as `[ExtractedCapability.to_dict()]` but `ExtractedCapability` has no `to_dict()` method defined in the input schema. The plan uses `vars()` in Section 4, which includes all fields including `None` values. Clarify whether `None` fields should be omitted or included as `null` in the output. | Low — affects downstream JSON size and consumer null-handling | Specify: use `vars()` with `None` values retained (consistent with JSON conventions), or explicitly filter them |
| R3-F3 | Design Decisions → test_coverage_map | Missing Detail | The design decision section doesn't specify what happens when ContextCore finds zero tests. Is `test_coverage_map` an empty dict `{}`? Is it omitted from the output? The plan's Section 6 implies it's always present but doesn't state this explicitly. | Low — downstream consumers need to know whether to check for key existence or empty dict | State: `test_coverage_map` is always present; if no tests found, it is `{}` |
| R3-F4 | Integration Points → With startd8-sdk | Missing Detail | The integration example shows the bridge called inside `ExplorePhaseHandler.execute()`, but doesn't specify whether the bridge should be instantiated once per pipeline run or once per phase. If multiple phases need bridge data and the phase handler is re-instantiated, the bridge runs redundantly. | Medium — performance impact on multi-phase pipelines | Clarify: bridge should run once in Explore phase and its output persists in `context` dict for all subsequent phases. Document this lifecycle expectation. |

#### Review Round R4

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 00:54:00 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Input Schema (Eagle) vs Output Schema | Conflict | The Output Schema requires `service_dependencies[].evidence`, and the Plan maps it from `ServiceDependency.evidence`. However, the Input Schema for `ServiceDependency` does **not** list an `evidence` field. | High — Implementation will fail `AttributeError` or require hallucinating data. | Update Input Schema to include `evidence` or remove it from Output Schema requirements. |
| R4-F2 | Output Schema (Capability Map) | Missing Constraint | The `docstring` field in `capability_map` has no length constraint. Large docstrings (or license headers mistakenly parsed as docstrings) will bloat the context dictionary, consuming tokens even if not in the summary. | Medium — Token waste in downstream phases. | Add requirement: "Docstrings in `capability_map` must be truncated to 500 characters." |

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 00:58:37 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Output Schema → `capability_map.by_file` | Missing Constraint | The schema shows `by_file` keyed by file path with `classes`, `functions`, `api_endpoints` as sub-keys, but doesn't specify whether empty sub-keys should be present. E.g., if `src/utils.py` has functions but no classes, should the output be `{"functions": [...]}` (omit empty) or `{"classes": [], "functions": [...]}` (always present)? This affects downstream code that uses `ctx["capability_map"]["by_file"]["src/utils.py"]["classes"]` — KeyError vs empty list. | Medium — downstream consumers need consistent key presence contract | Specify: all category keys (`classes`, `functions`, `api_endpoints`, `cli_commands`) are always present in each `by_file` entry, defaulting to `[]` |
| R5-F2 | Output Schema → `codebase_summary` | Missing Constraint | The feature doc says the summary is "a concise markdown summary" and provides an example format, but doesn't specify whether it's a stable format that downstream phases can parse, or a human-readable string that may change between versions. If any downstream phase regex-parses the summary (e.g., to extract service count), format changes become breaking. | Medium — unclear contract stability | Clarify: `codebase_summary` is for LLM prompt injection only and must NOT be machine-parsed; any structured data should be read from `project_structure` or `capability_map` directly |
| R5-F3 | Design Decisions → Section 1 (by_file) | Inconsistency with Plan | The feature doc says "When the agent explores an issue, it needs to quickly answer 'what's in this file?'" — but the plan's Section 5 explicitly excludes `tests` and `doc_sections` from `by_file`. If an agent asks "what's in `tests/test_auth.py`?", the answer would be empty despite ContextCore having extracted test capabilities from that file. The design decision's stated goal contradicts the plan's exclusion rule. | Medium — agents cannot look up test file contents via `by_file` | Either include tests/docs in `by_file` (making it a complete file index) or explicitly document that `by_file` is a *source code* index and test files should be looked up via `capability_map.by_type.tests` |
| R5-F4 | Architecture Diagram → Cost/Time | Stale Estimate | The architecture diagram states "Cost: $0.00 | Time: ~3-8 seconds" but with 26 accepted suggestions adding validation, consistency checks, path sanitization, schema validation, truncation logic, and partial-failure handling, the implementation is significantly more complex than originally scoped. The "~1 day" effort estimate in the feature doc likely underestimates the now-expanded scope. | Low — planning accuracy | Update effort estimate to ~2 days to account for validation logic, error handling, and schema contract tests added through review rounds |
| R5-F5 | Output Schema → `project_structure.languages` | Missing Detail | The schema says `"languages": [str]` is "deduplicated" but doesn't specify ordering. Is it alphabetical? By LOC prevalence? By service count? This matters for `codebase_summary` rendering and for downstream phases that might use `languages[0]` as the "primary language." | Low — inconsistent ordering across runs, non-deterministic output | Specify: `languages` sorted alphabetically (deterministic) or by descending total LOC (useful) — pick one and document it |

#### Review Round R6

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 01:00:00 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | Output Schema → `codebase_summary` | Ambiguity | The summary requirement mentions counting "public classes/functions", but the `ExtractedCapability` schema lacks a visibility field. Python uses `_` convention, but this isn't specified as the filter criteria. | Medium — Summary may overstate public API surface if private members are counted. | Define "public" in this context as "names not starting with `_`". |
| R6-F2 | Output Schema → `capability_map` | Missing Feature | `project_structure` includes `is_generated` for files, but `capability_map` does not. Agents using the map won't know if a class is auto-generated (and thus shouldn't be edited). | Medium — Agent might try to modify generated code, leading to overwritten changes. | Add `is_generated` boolean to the `capability_map` entry schema, derived from the file's status in Eagle. |

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 01:06:31 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R7-F1 | Output Schema → `project_structure.services[].files` | Missing Constraint | The output schema includes a `files` array per service with `path`, `loc`, and `is_generated`, but for large services (1000+ files), this array dominates the context dict size. No cap or filtering strategy is specified. Unlike `codebase_summary` (which truncates at 15 services), the files array has no equivalent bound. | Medium — large monorepo services could produce multi-MB context dicts, slowing serialization and consuming memory unnecessarily when most files are never referenced by downstream phases. | Add a configurable `max_files_per_service` parameter (default: 500) with truncation sorted by LOC descending, plus a `files_truncated: bool` flag in the service dict. |
| R7-F2 | Output Schema → `test_coverage_map` | Semantic Ambiguity | The requirement specifies map keys as source file paths and values as test names, but doesn't define the directionality expectation. A source file `src/auth.py` mapped to `["test_login", "test_logout"]` implies these tests *cover* that file, but the heuristic is purely filename-based. The word "coverage" implies execution-based coverage (e.g., `coverage.py`), which this is not. | Low — could mislead downstream consumers or agents into treating this as actual coverage data rather than a naming-convention heuristic. | Rename to `test_association_map` or add explicit documentation: "This is a heuristic filename association, not execution-based coverage. Actual test coverage requires running the test suite." |
| R7-F3 | Integration Points → With startd8-sdk | Missing Constraint | The feature doc shows `context.update(merged)` in `ExplorePhaseHandler` but doesn't specify the contract for what happens if `build_context()` is slow (>8s estimate). No timeout is defined for the bridge call, and if Eagle hangs on a massive repo (e.g., scanning a monorepo with 100K files), the entire Artisan pipeline blocks indefinitely. | Medium — no timeout or cancellation mechanism for a synchronous call in a pipeline that may have SLA expectations. | Specify a configurable timeout (default: 60s) for `build_context()`, with the bridge raising `ContextBridgeTimeout` if exceeded. Document that Eagle's `RepoScanner` is the likely bottleneck for large repos. |
| R7-F4 | Limitations | Missing Limitation | The doc lists three limitations (Python-only extraction, service-per-directory expectation, no semantic analysis) but doesn't mention that `ExtractionResult` captures only *static* capabilities. Dynamically registered routes (e.g., Flask `add_url_rule()` called in a loop), dynamically generated CLI commands (e.g., Click groups built at import time), or monkey-patched classes won't appear in the capability map. | Low — agents may assume the capability map is complete when it systematically misses dynamic registrations common in Python web frameworks. | Add a fourth limitation: "Dynamic registrations (runtime route addition, programmatic CLI commands, monkey-patched classes) are not captured by static AST extraction." |

#### Review Round R8

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 01:29:30 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R8-F1 | Output Schema → `capability_map.by_file` | Missing Detail | R5-F1 (accepted) specifies all category keys are always present, but the feature doc's `by_file` example only shows `classes`, `functions`, and `api_endpoints`. The full set of always-present keys should be explicitly enumerated in the feature doc's output schema example — especially since R5-F3 (accepted) resolved the test file inclusion question. The current example contradicts both accepted suggestions. | Medium — implementers referencing the feature doc's example will produce incomplete `by_file` entries. | Update the `by_file` example in the Output Schema to show all always-present keys including `cli_commands`, and clarify whether `tests` and `doc_sections` are included per the R5-F3 resolution. |
| R8-F2 | Output Schema → `project_structure.service_dependencies` | Stale Schema | Despite R1-F1 being accepted (rename `from`/`to` to `source_service`/`target_service`), the Output Schema in the feature doc still shows `"from": str, "to": str`. The feature doc is the canonical schema reference and should reflect accepted changes. | High — any consumer implementing against the feature doc's output schema will use the wrong key names. | Update the Output Schema's `service_dependencies` to use `"source_service"` and `"target_service"`. |
| R8-F3 | Design Decisions → test_coverage_map | Stale Naming | R7-F2 was accepted to rename `test_coverage_map` to `test_association_map` (or add prominent documentation that it's heuristic-based). The feature doc's Output Schema, Design Decisions section, and Limitations section all still reference `test_coverage_map`. | Medium — the canonical document contradicts the accepted naming decision, causing confusion for implementers. | Search-and-replace `test_coverage_map` with `test_association_map` throughout the feature doc, or add the accepted documentation caveat to the Output Schema. |
| R8-F4 | Integration Points → With startd8-sdk | Missing Detail | The feature doc shows the bridge called in `ExplorePhaseHandler.execute()` which receives `context` as a parameter. But the feature doc doesn't specify whether `build_context()` returns the NEW keys only (to be merged) or returns a COMPLETE context dict (including existing keys like `workflow_id`). The current signature `build_context() → dict[str, Any]` is ambiguous. | Medium — if `build_context()` returns only new keys, `context.update(merged)` works. If it returns a full context with its own `workflow_id`, it could overwrite pipeline-managed keys. | Clarify that `build_context()` returns only the three bridge-owned keys (`project_structure`, `capability_map`, `codebase_summary`) and does not include or echo back existing context keys. |

#### Review Round R9

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 01:30:30 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R9-F1 | Input Schemas | Ambiguity | The Eagle `ServiceMetadata` schema lists `files: List[FileInfo]`, but does not specify if `FileInfo.path` is relative to the *Service* root or the *Project* root. | Critical — Determines whether path joining logic is required in the Bridge. Incorrect assumption breaks file lookups. | Explicitly state the path format provided by Eagle (likely service-relative) and require the Bridge to normalize to project-relative. |

#### Review Round R10

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 01:36:20 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R10-F1 | Output Schema → `capability_map.by_file` | Inconsistency with Accepted Suggestions | The feature doc's `by_file` example still shows only `classes`, `functions`, `api_endpoints` — missing `cli_commands`, `tests`, and `doc_sections`. R5-F1 (accepted) requires all category keys always present. R8-F1 (accepted) called for updating this example. R5-F3 (accepted) resolved the test inclusion question. The example in the feature doc has not been updated to reflect ANY of these three accepted suggestions. | High — The canonical schema example contradicts three accepted suggestions, making it the primary source of implementer confusion. | Update the `by_file` example to show all six category keys with empty-list defaults, reflecting R5-F1, R5-F3, and R8-F1. |
| R10-F2 | Output Schema → `project_structure.service_dependencies` | Stale Schema (Persistent) | Despite R1-F1 and R8-F2 both being accepted, the Output Schema code block in the feature doc STILL shows `"from": str, "to": str` and `"evidence": str`. The `from`/`to` keys should be `source_service`/`target_service`. This has been flagged twice and accepted twice but never actually applied to the document. | High — Implementers copy-pasting the schema will use wrong key names. This is now a process failure, not a review gap. | Apply the accepted R1-F1 and R8-F2 changes to the actual Output Schema code block. This should be treated as a blocking pre-implementation task. |
| R10-F3 | Design Decisions → Section 2 (test_coverage_map) | Stale Naming (Persistent) | R7-F2 and R8-F3 were both accepted to rename `test_coverage_map` to `test_association_map`. The feature doc still uses `test_coverage_map` in the Output Schema, Design Decisions Section 2, and the Design Decisions Section 2 heading. | Medium — Same as R10-F2: accepted changes not applied to the document. | Search-and-replace all instances of `test_coverage_map` with `test_association_map` in the feature doc. |
| R10-F4 | Input Schema → `ServiceDependency` | Missing Field Definition | R4-F1 (accepted, 4 endorsements) identified that the Input Schema for `ServiceDependency` lacks the `evidence` field required by the Output Schema. R2-F1 (accepted) flagged the same issue. Despite both being accepted, the Input Schema dataclass definition in the feature doc has NOT been updated to include `evidence: str`. | Critical — This is the highest-endorsed suggestion across all rounds and remains unresolved in the document. Implementation will fail with AttributeError. | Add `evidence: Optional[str]` to the `ServiceDependency` dataclass in the Input Schema section, or remove `evidence` from the Output Schema and document it as derived. |

#### Review Round R11

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 01:37:42 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Requirement Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R11-F1 | Input Schemas → `ServiceMetadata` | Missing Detail | `ServiceMetadata` has `name` but no `root_path`. If a service is nested (e.g. `backend/services/auth`), and `name` is just "auth", the bridge cannot reconstruct the project-relative path of its files to match ContextCore's paths. | High — Path joining fails for nested services. | Add `root_path` (relative to project root) to `ServiceMetadata` schema. |
| R11-F2 | Input Schemas → `ExtractedCapability` | Ambiguity | The schema does not specify if methods are included in the top-level `functions` list or nested within `classes`. | Medium — Potential data loss if methods are nested and not iterated. | Clarify if `functions` list includes class methods, or add `methods` field to `ExtractedCapability` for class objects. |

