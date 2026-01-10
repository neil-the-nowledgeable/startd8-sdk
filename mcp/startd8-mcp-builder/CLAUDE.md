# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The **Startd8 MCP Builder** is a Model Context Protocol (MCP) server that exposes Startd8 SDK capabilities to LLMs. It enables IDE integrations (starting with Cursor) to leverage skill-based agents, workflows, and evaluation pipelines through a standardized protocol.

The server bridges Startd8's skill-based agent framework with external tools via MCP, allowing LLMs to discover, inspect, and execute Claude Skills programmatically.

## Key Commands

### Development

```bash
# Install dependencies (using uv or pip)
pip install -r requirements-server.txt
pip install -r requirements-dev.txt

# Test locally (basic smoke test)
python3 test_server.py

# Run the MCP server (stdio mode)
./run_mcp.sh

# Run with MCP Inspector for debugging
npx @modelcontextprotocol/inspector ./run_mcp.sh
```

### Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_01_basic.py

# Run specific test function
pytest tests/test_05_use_skill.py::test_use_skill_basic

# Run with verbose output
pytest -v

# Run with output capture disabled (see print statements)
pytest -s
```

### Environment Setup

```bash
# Required for skill execution
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional: Custom skill paths (colon-separated)
export STARTD8_SKILL_PATH="~/my-skills:~/other-skills"

# Optional: SDK path for advanced features
export STARTD8_SDK_PATH="/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/src"

# Optional: Logging (stderr only, safe for MCP)
export STARTD8_MCP_LOG_FILE="/tmp/startd8-mcp.log"

# Optional: Structured event log (JSONL)
export STARTD8_MCP_EVENT_LOG_FILE="logs/mcp-events.jsonl"

# Optional: Prometheus metrics (requires prometheus-client)
export STARTD8_MCP_METRICS_PORT=9464
```

## Architecture

### Core Design Principles

1. **JSON-First with Markdown View**: Internal canonical JSON, formatted Markdown output for humans
2. **MCP as Harness**: Captures outputs + metrics; analysis happens externally
3. **Backward Compatibility**: Defaults preserve existing behavior
4. **Separation of Concerns**: MCP-focused, SDK integration modular

### Main Components

#### Primary Server (`startd8_mcp.py`)

A single-file MCP server (~4300 lines) using FastMCP. Key sections:

- **Startup Error Aggregation** (lines 34-48): Collects and surfaces errors during initialization
- **Logging Guards** (lines 50-105): Prevents LogRecord collisions on reserved keys
- **Pydantic Models** (lines ~200-800): Input validation for all tools
- **Skill Discovery** (lines ~900-1400): Filesystem scanning and SKILL.md parsing
- **Core Tools** (lines ~1800-3000):
  - `startd8_help`: Capabilities and usage examples
  - `startd8_status`: Diagnostics and health checks
  - `startd8_list_skills`: Skill discovery and listing
  - `startd8_get_skill_info`: Detailed skill information
  - `startd8_use_skill`: Execute skill-based agents via Anthropic API
  - `startd8_compare_agents`: Multi-agent comparison (placeholder)
- **Task Runner Tools** (lines ~3000-3400): Task list management and execution
- **Dynamic Skill Tools** (lines ~3400-3600): Optional per-skill tool registration
- **Server Initialization** (lines ~3900-4300): FastMCP setup, resource registration, signal handlers

#### Launcher Script (`run_mcp.sh`)

Bash script that:
- Loads environment from `.env` and `.env.local` files
- Selects Python interpreter (prefers local `.venv`)
- Sets MCP-safe defaults (quiet mode, event logging when driven by client)
- Validates stdout/stderr separation (required for MCP stdio)
- Adds default skill paths if they exist
- Executes `startd8_mcp.py` with proper buffering

#### Test Suite (`tests/`)

72+ test functions covering:
- Basic server initialization and tool discovery
- Skill discovery and listing
- Input validation
- MCP protocol compliance
- Error handling
- Performance benchmarks
- Workflow integration
- Task runner functionality

### Skill Discovery Flow

1. **Scan directories** in `STARTD8_SKILL_PATH` plus defaults:
   - `~/.startd8/skills/`
   - `~/Documents/FMLs/dev/version2/`
   - `./skills/`
   - `/Users/neilyashinsky/Documents/tools/Anthropic/context/Claude/Skills`

2. **Look for `SKILL.md`** files containing:
   - YAML frontmatter with `name` and `description`
   - Markdown content with skill instructions

3. **Cache results** with TTL (default 10 seconds, configurable via `STARTD8_MCP_SKILL_CACHE_TTL_SECONDS`)

4. **Optional: Register per-skill tools** when `STARTD8_MCP_REGISTER_SKILL_TOOLS=1` (up to `STARTD8_MCP_MAX_SKILL_TOOLS` limit)

### MCP Protocol Integration

The server exposes:

- **Tools**: Callable functions for skill discovery, execution, and task management
- **Resources**: Browsable `skill://` URIs with skill content
- **Annotations**: MCP hints (readOnly, destructive, idempotent, openWorld)

All tools return structured responses in either:
- **Markdown** (default): Human-readable with metrics footer
- **JSON**: Machine-readable with full metadata

### Observability

The server supports multiple observability backends:

1. **Structured Event Log** (JSONL): All tool invocations logged to `logs/mcp-events.jsonl` by default
2. **Prometheus Metrics**: Optional HTTP endpoint on port 9464 (requires `prometheus-client`)
3. **OpenTelemetry Tracing**: Optional OTLP export to Alloy/Tempo (set `STARTD8_MCP_TRACING=1`)
4. **Stderr Logging**: Text logs to file via `STARTD8_MCP_LOG_FILE`

All observability mechanisms are MCP-safe (stderr only, never stdout).

## Important Patterns

### MCP Stdio Safety

**CRITICAL**: MCP uses stdout for JSON-RPC. Never write to stdout or merge stderr into stdout:

```bash
# ❌ WRONG - breaks MCP
python3 startd8_mcp.py 2>&1 | tee log.txt

# ✅ RIGHT - logs to stderr only
STARTD8_MCP_LOG_FILE=/tmp/log.txt ./run_mcp.sh
```

The launcher script validates this at runtime and exits with error code 2 if violated.

### Skill Tool Registration

When `STARTD8_MCP_REGISTER_SKILL_TOOLS=1`, the server dynamically creates one tool per skill (e.g., `skill_mcp_builder`, `skill_html5_game_designer_pro`). This enables direct skill invocation:

```json
{
  "skill_name": "mcp-builder",
  "prompt": "Create an MCP server for GitHub API"
}
```

This is an optimization for UX in MCP clients (fewer clicks) but functionally equivalent to:

```json
{
  "tool": "startd8_use_skill",
  "params": {
    "skill_name": "mcp-builder",
    "prompt": "Create an MCP server for GitHub API"
  }
}
```

### Task Runner Integration

The server includes a task runner subsystem for managing multi-step workflows:

- **Task List**: Markdown file (default: `MASTER_TASK_LIST.md`) with structured task definitions
- **Tools**: `tasks.list`, `tasks.status`, `tasks.create`, `tasks.run`
- **Execution**: Supports dependencies, automatic dependency resolution, agent selection
- **Tracking**: Logs execution history and results

This enables complex, multi-step agent workflows to be defined and tracked programmatically.

### Error Handling Philosophy

1. **Startup errors** are aggregated and surfaced in `startd8_status` diagnostics
2. **Runtime errors** return structured JSON with actionable messages
3. **API errors** (Anthropic) are caught and formatted with suggestions
4. **Missing dependencies** (like Anthropic SDK) provide installation instructions

## Development Notes

### Adding New Tools

1. Define Pydantic input model with validation
2. Implement tool function with `@mcp.tool()` decorator
3. Add MCP annotations (readOnly, destructive, idempotent, openWorld)
4. Support both JSON and Markdown response formats
5. Emit structured events for observability
6. Add tests in `tests/` directory

### Modifying Skill Discovery

Skill discovery logic is in `_discover_skills()`. Key considerations:

- **Caching**: Results are cached with TTL to avoid filesystem thrashing
- **Robustness**: Gracefully handles malformed YAML, missing files, permission errors
- **Performance**: Discovery is async and can be parallelized (currently sequential)

### Testing Best Practices

- Use fixtures from `tests/fixtures.py` for isolated test environments
- Mock Anthropic API calls to avoid charges and ensure determinism
- Test both JSON and Markdown response formats
- Validate MCP protocol compliance (annotations, return types)
- Include error cases and edge conditions

## Key Files and Their Roles

- **`startd8_mcp.py`**: Main server implementation (single-file FastMCP)
- **`run_mcp.sh`**: Production launcher with env loading and validation
- **`test_server.py`**: Quick local testing script (non-MCP)
- **`pyproject.toml`**: Dependencies and Python project metadata
- **`requirements-server.txt`**: Runtime dependencies
- **`requirements-dev.txt`**: Dev/test dependencies
- **`cursor-mcp-config.json`**: Example Cursor MCP configuration
- **`env.sample`**: Template for environment variables
- **`PROJECT_CHARTER.md`**: Project vision, scope, and phases
- **`QUICKSTART.md`**: 5-minute getting started guide
- **`README_SERVER.md`**: Full server documentation
- **`SKILL.md`**: This project's own skill definition (meta!)

## Context Documents

The `context/` directory contains LLM-friendly documentation:

- **`startd8_overview_v1.md`**: What is Startd8 and its architecture
- **`sdk_and_fmls_v1.md`**: SDK structure and Force Multiplier Labs methodology
- **`mcp_integration_plan_v1.md`**: Integration strategy and phases
- **`evaluations_and_workflows_v1.md`**: Evaluation approach and workflows
- **`glossary_v1.md`**: Term definitions

These documents are designed to give LLMs comprehensive context about the broader Startd8 ecosystem.

## Related Repositories

- **Startd8 SDK**: `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/`
- **StartDate OSS**: `/Users/neilyashinsky/Documents/biz/incubator/StartDateOSS/`
- **Claude Skills**: `/Users/neilyashinsky/Documents/tools/Anthropic/context/Claude/Skills`
- **FMLs (Force Multiplier Labs)**: `~/Documents/FMLs/dev/version2/`

## Current Status

- **Phase 1 (MCP Server Core)**: ✅ Complete
- **Phase 2 (Refinement and Testing)**: ✅ Complete
- **Phase 3 (Evaluations)**: 🔄 In Progress
- **Phase 4 (Cursor Integration)**: 📋 Planned
- **Phase 5 (SDK Integration)**: 📋 Planned

See `PROJECT_STATUS.md` for detailed status and next steps.
