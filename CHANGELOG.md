# Changelog

All notable changes to the startd8 SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### VIPP — project-side negotiator/applier (new `startd8 vipp`)

> The project-side counterpart to the Concierge / Welcome Mat / Red Carpet hosts — the
> **OBSERVED(project)-authority dual of the FDE**. New package `src/startd8/vipp/` + host seam
> `kickoff_experience/vipp_seam.py` + `startd8 vipp` CLI. Design + traceability:
> `docs/design/vipp/` (`VIPP_REQUIREMENTS.md` v0.3 — reflective-requirements → 3-lens CRP;
> `VIPP_PLAN.md` M0–M6).

**New surfaces:**

| Surface | What it does |
|---------|--------------|
| `startd8 vipp init` | Opt the project into VIPP (creates `.startd8/vipp/`; the host then serializes pending proposals there) |
| `startd8 vipp negotiate` | Adjudicate the host proposal inbox against Sapper project ground truth → source-labeled dispositions (`$0`, deterministic) |
| `startd8 vipp apply` | Preview by default; `--apply` writes accepted proposals at **project human privilege** through the `apply_proposal` floor |
| `kickoff_experience/vipp_seam.py` | Host-side serialization seam — **additive & opt-in**; `proposals.py` is byte-for-byte unchanged |
| `EventType.VIPP_NEGOTIATE_COMPLETE` | One structured EventBus/Loki event per negotiation (counts + `project.id`, no free-text) |

**Design invariants:** file-protocol-first (Keiyaku contracts), out-of-process-only (the file seam is
the trust boundary), provenance-pinned apply (`kind`/`base_sha` from the trusted inbox, human-confirm
the sole content gate), VIPP mints only OBSERVED(project) claims (cannot forge SDK-mechanism
authority), byte-identical-when-absent when VIPP is not opted in.

### RUN-007 empty-spec remediation

> **Heads-up for anyone working in the code-generation path.** Lands via
> `fix/run-007-empty-spec-remediation`. Closes the run-007 partial-delivery
> defect: Prime/Micro-Prime could ship empty-class stubs (`export class <stem> {}`)
> as *successful* `$0.00` output, and the post-mortem scored them ~0.94 (blind to
> the failure). Both halves — generation **and** detection — are now closed.
> Design + traceability: `docs/design/RUN_007_REMEDIATION_{REQUIREMENTS,PLAN}.md`
> (v0.3, hardened by a 6-round Convergent Review) and
> `docs/design/RUN_007_PARTIAL_DELIVERY_POSTMORTEM.md`.

**Behavior changes to be prepared for (by surface):**

| Surface (file) | What changes | What you'll observe |
|----------------|--------------|---------------------|
| `micro_prime/prime_adapter._generate_skeletons` | Empty-spec gate: a feature with **no fillable elements** (and no framework-config registry match) no longer gets a stem-named skeleton | The file routes to cloud file-whole escalation; if escalation yields no real content it is **refused** (`MissingTemplateError`, feature `success=False`) — never an unfilled stub |
| `complexity/classifier`, `complexity/signals` | FR-7 guard: an empty-fillable, non-registry feature is **no longer classified `SIMPLE`** | Such features route to the real-LLM path instead of the no-LLM SIMPLE tier |
| `forward_manifest_validator` (disk validation) | An empty stem-named type with no members now **FAILs** for source files (`ast_valid=False`, disk score ≤ 0.3) | The post-mortem *sees* a stub instead of scoring it ~0.94. `.d.ts`/barrel/marker files are exempt |
| `contractors/prime_contractor` (orchestration) | Threads remaining `$` budget into the generation context | Empty-spec targets are **refused (not escalated)** once `max_cost_usd` is reached |

### Added
- `startd8.element_fillability` — shared `is_fillable_spec` / `is_empty_fillable_spec`
  / `is_empty_stem_type_artifact` (positive fillability + run-007 stub detection).
- `startd8.exceptions.MissingTemplateError` — structured refusal for under-specified
  features (carries `root_cause` / `pipeline_stage` for post-mortem attribution).
- `TaskComplexitySignals.has_fillable_elements: Optional[bool]`.
- Generation-context key `_cost_budget_remaining_usd` (orchestration → micro-prime).

### Changed
- `micro_prime/prime_adapter`: empty-spec gate + escalate-or-refuse; a refused
  target now makes the feature `success=False` (no longer `effective_file_count > 0`).
- `complexity/classifier`: FR-7 fillability guard (new `has_fillable_elements` signal).
- `forward_manifest_validator`: empty-stem-stub disk-validation FAIL (FR-5/FR-6).
- `contractors/prime_contractor`: threads the remaining `$` budget to generation (FR-4).

### Compatibility
- All changes are **guarded / additive**: specs with real elements, and runs
  without a `max_cost_usd` ceiling, are unchanged. The `has_fillable_elements`
  signal defaults to `None` (no guard); the budget guard is a no-op without a cap.

## [0.4.0] - 2026-06-02

> **The deterministic-first pivot.** startd8 became a software-engineering harness for
> LLM-assisted development built on a Requirements→Capabilities delivery pipeline, with the
> explicit goal of maximizing deterministic ($0) generation and using LLMs only for
> integration. This entry consolidates the 0.3.x → 0.4.0 history (the changelog had no
> intermediate release entries).

### Added — deterministic code generation ($0, no LLM)
- **`src/startd8/backend_codegen/`** — projects one `.prisma` data-model contract into a full
  all-Python backend (Pydantic + SQLModel + FastAPI + HTMX + export/AI-schemas/completeness),
  ~12 owned file kinds, all $0-deterministic. Runtime-verified end to end against FastAPI +
  SQLModel + Jinja2 (FK / `Relationship()` / `@default` translation / reserved-name guard).
- **`startd8 generate`** CLI with four targets: `frontend`, `backend`, `scaffold`
  (pyproject/logging/alembic/Dockerfile from `app.yaml`), `views` (composite/relational views
  from `views.yaml`).
- **`startd8 wireframe`** — $0 read-only pre-generation summary of what the deterministic
  cascade will build, with `--json` for CI.
- **`startd8 polish`** — apply an accessible design theme to a built app ($0).
- `validators/python_toolchain.py` deterministic quality gate; `STARTD8_PY_TYPECHECK` env.

### Added — pipeline, contractors & evaluation
- **Prime Contractor** as the active multi-feature construction path (tier-routed
  template → Haiku → Sonnet), with checkpoint/resume, ~45 per-language repair steps, and the
  **Kaizen** cross-run quality feedback system.
- **`startd8 compare-models`** — run the same seed through Prime Contractor across 2+ models in
  isolated sandboxes (cloud and edge/local) and rank them.
- New CLI surfaces: `fde` (forward-deployed-engineer failure explanation), `sapper`
  (pre-execution plan validation), `assist` (Service Assistant run triage), `repair`,
  `manifest`, `workflow`, `project`, `serve`, `element-registry`.
- Embedded **Capability Delivery Pipeline** (`.cap-dev-pipe/`).

### Added — providers & languages
- Providers expanded to 8: added `nim` and `openai-compatible` (edge/local + self-hosted)
  alongside `anthropic`, `openai`, `gemini`, `mistral`, `ollama`, `mock`.
- Language profiles expanded to 7: added `vue` and `prisma` alongside `python`, `go`,
  `nodejs`, `java`, `csharp`.

### Changed
- **Artisan Contractor placed ON HOLD (2026-03-12)**; Prime Contractor is the only active
  construction path. Prime-vs-Artisan routing is vestigial.
- Primary Contractor naming: `LeadContractorWorkflow` is also exported as
  `PrimaryContractorWorkflow`; legacy `lead_contractor_*` names preserved for compatibility.

### Fixed
- Orchestration harden-in-place (R1-S2 gate ADR): per-run repair circuit-breaker scope
  (`RepairSession`), `deque(maxlen=)` event history (trim race removed), and `FeatureQueue`
  resume state-hash integrity with loud refusal on corrupt/invalid resume state. Also revived a
  silently-disabled post-integrate contract-violation repair path.

## [0.2.0] - 2024-12-XX

### Added (Phase 2)
- **Testing Infrastructure**: Comprehensive test suite with pytest
  - 40+ unit tests covering storage, framework, models, and agents
  - Integration tests for file operations and workflows
  - Test fixtures and factories for easy test data generation
  - CI/CD pipeline with GitHub Actions (multi-platform, multi-version)
  - Coverage reporting with 80%+ target
- **Configuration System**: Flexible configuration management
  - `PricingConfig` for per-model pricing configuration
  - `ModelRegistry` for model management
  - Default pricing for Claude and GPT models
  - Extensible configuration system
- **Code Duplication Reduction**: DRY principles applied
  - `BaseStorageOperations` generic class for common patterns
  - ~70% reduction in storage code duplication
  - Error handling decorator for consistent error management

### Changed (Phase 2)
- **Type Safety**: Fixed tuple type hints for Python 3.9 compatibility
  - All `tuple[...]` changed to `Tuple[...]` from typing
  - Consistent type hints throughout
- **Storage Layer**: Refactored to use base operations
  - All storage methods now use `BaseStorageOperations`
  - Maintained backward compatibility
  - Improved error handling consistency
- **Cost Calculation**: Now uses configurable pricing
  - `TokenUsage.cost_estimate` uses `PricingConfig`
  - Per-model pricing support
  - Fallback to default pricing

### Added (Phase 1)
- **Error Handling System**: Custom exception classes for better error handling
  - `Startd8Error`, `StorageError`, `FileOperationError`, `ValidationError`, `APIError`, `ConfigurationError`, `AgentError`
- **Structured Logging**: JSON-formatted logging for production environments
  - `setup_logging()` and `get_logger()` functions
  - Correlation ID support for request tracking
- **Atomic File Operations**: Safe file writes that prevent corruption
  - `atomic_write()` and `atomic_write_json()` utilities
  - File locking mechanism for concurrent access
- **Security Improvements**:
  - Enhanced API key masking (always masks regardless of length)
  - Path sanitization to prevent directory traversal attacks
  - API key format validation
- **Input Validation**: Comprehensive validation using Pydantic
  - Prompt content validation (non-empty, length limits)
  - Semver format validation for versions
  - Response time and token usage validation
  - Token total validation (must equal input + output)

### Changed
- **Deprecated Code Removed**: Replaced all `datetime.utcnow()` with `datetime.now(timezone.utc)`
  - Python 3.12+ compatible
  - All datetimes are now timezone-aware
- **Error Handling**: Improved exception handling throughout
  - Exception context preserved with `raise ... from e`
  - Proper logging instead of print statements
  - Specific exception types for different error scenarios
- **Storage Operations**: All file operations now use atomic writes
  - Prevents partial/corrupted files
  - Thread-safe with file locking
  - Better error handling and logging
- **Project Structure**: Relocated to new development directory
  - Updated all documentation references from `startdate-sdk` to `startd8-sdk-project`
  - Synchronized version numbers across `setup.py` and `__init__.py`

### Fixed
- **Security**: Fixed API key masking to always mask (not just if > 14 chars)
- **Security**: Improved API key handling for localhost URLs
- **Concurrency**: Fixed race conditions in file operations
- **Error Handling**: Fixed exception context loss in API calls
- **Logging**: Replaced all `print()` statements with proper logging

### Notes
- This version represents Phase 1 of the implementation plan
- All critical issues from code review have been addressed
- Backward compatible - no breaking API changes

## [0.1.0] - Initial Release

### Added
- Multi-agent support (Claude, GPT-4, Gemini)
- Prompt version control with semantic versioning
- Response tracking with timing and token usage
- Benchmarking tools for comparing multiple LLMs
- Cost tracking and estimation
- CLI tools for easy management
- Flexible JSON-based file system storage
- TUI (Text User Interface) for interactive use
- Prompt Builder with template system

