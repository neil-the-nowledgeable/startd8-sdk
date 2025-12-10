# Changelog

All notable changes to the startd8 SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

