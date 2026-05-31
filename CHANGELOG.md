# Changelog

All notable changes to the startd8 SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

