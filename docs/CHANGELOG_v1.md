# Startd8 SDK Changelog

**Document Version:** v1  
**Last Updated:** 2025-01-13

## Version 0.2.0 (Current)

### New Features

#### Agent System Improvements
- **Modular Agent Selection**: New `_get_ready_agents_for_selection()` and `_select_ready_agent()` methods for consistent agent selection across the SDK
- **Renamed Agent Types**: Changed terminology from "Custom" to "User added" for clarity
  - "Custom agents" → "User added agents"
  - Type column displays "Built-in" or "User added"
- **Agent Status Table**: Consolidated agent display with improved readability
  - Fixed column widths for consistent layout
  - Truncated long API key masks for better display
  - Removed table borders for cleaner appearance

#### TUI Enhancements
- **Improved Contrast**: Section headers (WORKFLOW, MANAGE, AGENTS, SYSTEM) now use white bold text for better visibility on blue backgrounds
- **Better Typography**: 
  - Instruction text now uses bold instead of italic
  - Agent column uses bold cyan to match "Agent Status" title
- **Design Pipeline Updates**:
  - Shows all agents with Ready status in a table before selection
  - Uses modular agent selection for consistency
  - Refreshes agent status before pipeline execution

#### Document Enhancement Chain
- Multi-agent document processing with sequential enhancement
- Configurable error handling (stop, skip, retry)
- Preserves original documents optionally

#### Job Queue System
- File-based job queue for batch processing
- Priority-based job ordering
- Agent registry for dynamic agent management
- Progress tracking with callbacks

### Bug Fixes
- Fixed datetime storage issues with timezone handling
- Improved error handling in storage operations
- Fixed agent status detection for OpenAI-compatible providers

### Documentation
- Added comprehensive SDK documentation:
  - SDK_ARCHITECTURE_v1.md
  - TUI_USER_GUIDE_v1.md
  - AGENT_CONFIGURATION_GUIDE_v1.md
  - API_REFERENCE_v1.md
  - PIPELINE_WORKFLOWS_v1.md
  - QUICK_START_v1.md

---

## Version 0.1.0 (Initial Release)

### Core Features

#### Framework
- `AgentFramework` class for managing prompts, responses, and benchmarks
- File-based JSON storage with pagination support
- Prompt versioning with semantic versioning support
- Response tracking with timing and token usage

#### Agents
- `BaseAgent` abstract class
- `ClaudeAgent` for Anthropic Claude models
- `GPT4Agent` for OpenAI GPT-4 models
- `MockAgent` for testing
- `GeminiAgent` for Google Gemini models (basic)

#### Orchestration
- `Pipeline` class for sequential agent workflows
- `WorkflowTemplates` with pre-built pipelines:
  - `planner_implementer`
  - `code_review`
  - `design_review_chain`
- `PipelineResult` with comprehensive metrics

#### CLI
- Typer-based command-line interface
- Commands: `create-prompt`, `list-prompts`, `run-benchmark`, `compare`
- Pipeline command with workflow templates

#### TUI
- Questionary-based interactive terminal interface
- Rich-formatted output with tables and panels
- Agent configuration and testing
- API key management

#### Models
- Pydantic models for data validation:
  - `Prompt`
  - `AgentResponse`
  - `Benchmark`
  - `TokenUsage`

#### Benchmarking
- `BenchmarkRunner` for running multi-agent benchmarks
- `ComparisonReport` for generating comparison reports
- Cost estimation based on token usage

### Dependencies
- `rich>=13.0.0` - Terminal formatting
- `pydantic>=2.0.0` - Data validation
- `typer>=0.9.0` - CLI framework
- `httpx>=0.25.0` - HTTP client
- `questionary>=2.0.0` - Interactive prompts
- `pyyaml>=6.0.0` - YAML parsing

### Optional Dependencies
- `anthropic>=0.18.0` - Claude API support
- `openai>=1.0.0` - OpenAI API support

---

## Upgrade Guide

### From 0.1.0 to 0.2.0

#### Terminology Changes
If you have scripts or documentation referencing "custom agents":
- Update UI text from "Custom" to "User added"
- Internal code (`CustomAgentManager`, `custom_agents.json`) remains unchanged

#### New Agent Selection
Replace direct agent list building with modular functions:

```python
# Old
custom_agents = self.agent_manager.list_agents()
all_agents = self._build_unified_agent_list(custom_agents, set())
ready = [a for a in all_agents if a['available']]

# New (recommended)
ready = self._get_ready_agents_for_selection()
```

#### TUI Style Updates
The TUI now uses:
- White bold separators (previously gray)
- Bold instruction text (previously italic)
- Cyan bold Agent column

No code changes needed - styles apply automatically.

---

## Planned Features (Future)

### Version 0.3.0 (Planned)
- Async agent implementations
- Streaming response support
- SQLite storage backend option
- Web API server mode

### Version 0.4.0 (Planned)
- Plugin system for third-party agents
- Parallel pipeline execution
- Advanced comparison metrics
- Export to various formats

---

## Migration Notes

### Configuration Files

Configuration files are backward compatible:
- `~/.startd8/config.json` - Main configuration
- `~/.startd8/api_keys.json` - API key storage
- `~/.startd8/custom_agents.json` - User added agents

### Breaking Changes

**0.2.0**
- None - All 0.1.0 code should work without changes

---

## Versioning Policy

Startd8 follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes to the public API
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

Pre-1.0 versions may have breaking changes in minor versions.


