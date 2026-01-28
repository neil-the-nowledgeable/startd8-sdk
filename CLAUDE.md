# CLAUDE.md

This file provides guidance to Claude Code for the StartDate (startd8) SDK repository.

## Project Overview

StartD8 is a Python SDK and CLI tool for managing multi-LLM agent workflows, benchmarking different models (Anthropic, OpenAI, Gemini, Ollama), and prompt version control. It provides a unified interface for comparing LLM responses, tracking costs, and managing development workflows.

## Tech Stack

- **Language:** Python 3.9+ (venv uses 3.14)
- **CLI Framework:** Typer with Rich for terminal output
- **Data Models:** Pydantic v2
- **HTTP Client:** httpx (async support)
- **Build System:** setuptools with pyproject.toml
- **Testing:** pytest with pytest-asyncio

## Commands

```bash
# Activate virtual environment
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Install with all providers
pip install -e ".[all,dev]"

# Run tests
pytest

# Run specific test file
pytest tests/unit/test_agents.py -v

# Run with coverage
pytest --cov=startd8 --cov-report=term-missing

# Lint and format
ruff check src/
black src/

# Type checking
mypy src/

# Run CLI
startd8 --help
startd8 tui          # Launch interactive TUI
startd8 init         # Initialize framework in current dir
startd8 run-benchmark --help
```

## Project Structure

```
src/startd8/           # Main package
├── __init__.py        # Public API exports
├── cli.py             # Typer CLI commands
├── framework.py       # Core AgentFramework class
├── agents.py          # Agent implementations (Claude, GPT4, Gemini, etc.)
├── benchmark.py       # BenchmarkRunner and ComparisonReport
├── models.py          # Pydantic data models
├── orchestration.py   # Pipeline and workflow orchestration
├── providers/         # Provider abstraction layer
│   ├── protocol.py    # Provider protocol (interface)
│   ├── registry.py    # ProviderRegistry for discovery
│   ├── anthropic.py   # Anthropic/Claude provider
│   ├── openai.py      # OpenAI/GPT provider (+ Ollama)
│   ├── gemini.py      # Google Gemini provider
│   └── mock.py        # Mock provider for testing
├── costs/             # Cost tracking system
│   ├── tracker.py     # CostTracker
│   ├── pricing.py     # PricingService
│   ├── budget.py      # BudgetManager
│   └── analytics.py   # CostAnalytics
├── storage/           # Storage backends
├── events/            # Event bus system
├── mcp/               # MCP (Model Context Protocol) integration
├── skills/            # Skill agents and factories
├── prompt_builder/    # Prompt templating system
└── document_enhancement.py  # Document enhancement chains

tests/                 # Test suite
├── unit/              # Unit tests
├── integration/       # Integration tests
└── costs/             # Cost tracking tests

docs/                  # Documentation
examples/              # Usage examples
```

## Architecture

### Provider Pattern

The SDK uses a provider abstraction to support multiple LLM backends:

```python
# Discover and use providers
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
provider = ProviderRegistry.get_provider("anthropic")
provider.validate_config({})
agent = provider.create_agent("claude-sonnet-4-20250514")
```

### Key Classes

- `AgentFramework` - Core orchestration, manages prompts/responses/storage
- `BenchmarkRunner` - Run comparisons across multiple agents
- `Pipeline` - Sequential workflow execution
- `ProviderRegistry` - Dynamic provider discovery via entry points
- `CostTracker` - Track API costs across providers

### Entry Points

Providers are registered via `pyproject.toml` entry points:
```toml
[project.entry-points."startd8.providers"]
anthropic = "startd8.providers.anthropic:AnthropicProvider"
openai = "startd8.providers.openai:OpenAIProvider"
```

## Conventions

### Naming
- **Files:** snake_case.py (e.g., `document_enhancement.py`)
- **Classes:** PascalCase (e.g., `BenchmarkRunner`)
- **Functions:** snake_case (e.g., `run_benchmark`)
- **Constants:** UPPER_SNAKE_CASE

### Code Style
- Type hints on all public functions
- Pydantic models for data structures
- Async support via `async/await` (many methods have sync + async variants)
- Rich console output for CLI commands

### Agent Specs
Agents are specified as `provider:model` strings:
- `anthropic:claude-sonnet-4-20250514`
- `openai:gpt-4-turbo-preview`
- `gemini:gemini-1.5-pro`
- `ollama:llama2`
- `mock:mock-model`

### Storage
- Default storage: `.startd8/` directory in project root
- JSON-based file storage (prompts, responses, benchmarks)
- Configurable via `AgentFramework(storage_dir=...)`

## Important Context

### Must Do
- Always call `ProviderRegistry.discover()` before using providers
- Call `provider.validate_config({})` before creating agents
- Use `BaseAgent` as the type hint for agents (not specific implementations)
- Run tests with `pytest` before committing changes
- Preserve existing exception handling patterns in `exceptions.py`

### Must Avoid
- Don't hardcode API keys - they come from environment variables
- Don't skip provider validation - it checks for required config
- Don't use blocking calls in async code paths
- Don't modify the `__all__` exports without updating tests

### Environment Variables
```bash
ANTHROPIC_API_KEY    # For Claude models
OPENAI_API_KEY       # For GPT models
GOOGLE_API_KEY       # For Gemini models
OLLAMA_HOST          # Ollama server URL (optional)
```

### Known Issues
- Response ID tracking has edge cases in concurrent scenarios
- Gemini provider requires separate google-genai package
- Cost tracking assumes standard pricing (may differ for enterprise)

## Version

Current version: **0.4.0** (defined in pyproject.toml)

Pre-1.0 SemVer: breaking changes may occur in MINOR versions.

## Documentation

Key docs in `docs/`:
- `SDK_ARCHITECTURE_v1.md` - Architecture overview
- `API_REFERENCE_v1.md` - API reference
- `COST_TRACKING_USER_GUIDE.md` - Cost tracking guide
- `PIPELINE_WORKFLOWS_v1.md` - Pipeline workflows
- `TUI_USER_GUIDE_v1.md` - TUI usage guide

## Lessons Learned

See `SDK_developer_LESSONS_LEARNED.md` at `/Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/` for accumulated development wisdom.
