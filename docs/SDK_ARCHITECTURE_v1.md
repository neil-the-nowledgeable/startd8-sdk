# Startd8 SDK Architecture

**Version:** 0.4.0
**Document Version:** v1.1
**Last Updated:** 2026-02-11

## Overview

The Startd8 SDK is a comprehensive Python framework for managing multi-LLM agent workflows, benchmarking, and prompt version control. It provides a unified interface for working with multiple AI providers (Anthropic, OpenAI, OpenAI-compatible endpoints) and includes tools for comparing, tracking, and managing AI-generated outputs.

## Core Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Startd8 SDK                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐     │
│  │     CLI     │   │     TUI     │   │   Python    │   │  Job Queue  │     │
│  │  (typer)    │   │(questionary)│   │     API     │   │  (File-     │     │
│  │             │   │             │   │             │   │   based)    │     │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘     │
│         │                 │                 │                 │             │
│         └─────────────────┴────────┬────────┴─────────────────┘             │
│                                    │                                         │
│                          ┌─────────▼─────────┐                              │
│                          │  AgentFramework   │                              │
│                          │  (Core Engine)    │                              │
│                          └─────────┬─────────┘                              │
│                                    │                                         │
│         ┌──────────────────────────┼──────────────────────────┐             │
│         │                          │                          │             │
│  ┌──────▼──────┐  ┌───────▼───────┐  ┌──────▼──────┐  ┌──────▼──────┐   │
│  │   Agents    │  │ Orchestration │  │ Contractors │  │   Storage   │   │
│  │             │  │               │  │             │  │             │   │
│  │ • Claude    │  │ • Pipeline    │  │ • Prime     │  │ • File-     │   │
│  │ • GPT-4     │  │ • Workflows   │  │   Contractor│  │   based     │   │
│  │ • Gemini    │  │ • Multi-step  │  │ • Artisan   │  │ • JSON      │   │
│  │ • Ollama    │  │   chains      │  │   Contractor│  │   format    │   │
│  │ • Mock      │  │               │  │ • Handoff   │  │ • Paginated │   │
│  └─────────────┘  └───────────────┘  └─────────────┘  └─────────────┘   │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                            Support Modules                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Models    │  │   Config    │  │  Document   │  │   Prompt    │        │
│  │  (Pydantic) │  │  Manager    │  │ Enhancement │  │   Builder   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Descriptions

### 1. AgentFramework (`framework.py`)

The central orchestrator that manages:
- Prompt creation and versioning
- Response recording and retrieval
- Benchmark creation and management
- Response comparison and metrics

```python
from startd8 import AgentFramework

framework = AgentFramework(storage_dir=Path("~/.startd8"))

# Create versioned prompts
prompt = framework.create_prompt(
    content="Implement user auth",
    version="1.0.0",
    tags=["auth", "backend"]
)

# Record and compare responses
comparison = framework.compare_responses(prompt.id)
```

### 2. Agents (`agents.py`)

Abstract base class and implementations for LLM providers:

| Agent Class | Provider | Description |
|-------------|----------|-------------|
| `BaseAgent` | Abstract | Base class for all agents |
| `ClaudeAgent` | Anthropic | Claude models (Sonnet, Opus, Haiku) |
| `GPT4Agent` | OpenAI | GPT-4 models |
| `OpenAICompatibleAgent` | Various | Any OpenAI-compatible API |
| `ComposerAgent` | Cursor | Cursor's Composer model |
| `MockAgent` | Testing | Simulated responses for testing |

**Agent Status Types:**
- **Built-in**: Provider-backed agents via `ProviderRegistry` (Anthropic, OpenAI, Gemini, Ollama, Mock)
- **User added**: Custom-configured agents created by users

### 3. Orchestration (`orchestration.py`)

Multi-step pipeline workflows:

```python
from startd8 import WorkflowTemplates
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

# Use pre-built template
pipeline = WorkflowTemplates.design_review_chain(
    drafter_agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    reviewer_agent=openai.create_agent("gpt-4o"),
    final_reviewer_agent=anthropic.create_agent("claude-opus-4-5-20251101"),
)

result = pipeline.run("Design a feature for X")
```

### 4. Storage (`storage/`)

File-based storage with pagination support:

- **Prompts**: Versioned prompts with tags and metadata
- **Responses**: Agent responses with timing and token usage
- **Benchmarks**: Benchmark definitions and results

### 5. TUI (`tui_improved.py`)

Interactive terminal interface with:
- Agent configuration and testing
- Prompt creation and distribution
- Result viewing and comparison
- API key management
- Output folder management

### 6. Document Enhancement (`document_enhancement.py`)

Multi-agent document processing chains:

```python
from startd8 import DocumentEnhancementChain

chain = DocumentEnhancementChain(config)
result = chain.process(document_path)
```

### 7. Prompt Builder (`prompt_builder/`)

Template-based prompt generation:
- YAML template definitions
- Variable interpolation
- Project context auto-fill

### 8. Job Queue (`job_queue.py`)

File-based job queue for batch processing:
- Priority-based job ordering
- Agent registry
- Progress tracking

### 9. Contractors (`contractors/`)

Multi-phase workflow orchestration for code generation:

- **PrimeContractor**: Per-feature `generate -> integrate -> validate` loop with protocol-based design (CodeGenerator, Instrumentor, SizeEstimator, MergeStrategy)
- **ArtisanContractor**: 8-phase workflow (PLAN -> SCAFFOLD -> DESIGN -> IMPLEMENT -> INTEGRATE -> TEST -> REVIEW -> FINALIZE) with phase handlers, checkpoints, cost budget enforcement, and OTel tracing
- **Design Handoff**: Serializable context state (`design-handoff.json`) enabling two-half split execution where design and implementation run as separate processes
- **Context Seed Handlers**: Bridges enriched context seeds to the orchestrator via `ContextSeedHandlers.create_all()`

```
contractors/
├── artisan_contractor.py     # ArtisanContractorWorkflow orchestrator
├── context_seed_handlers.py  # Phase handler implementations
├── handoff.py                # Design handoff persistence
├── prime_contractor.py       # PrimeContractorWorkflow
├── protocols.py              # Protocol interfaces
├── generators/               # Code generators (LeadContractor)
├── adapters/                 # Instrumentation adapters
└── artisan_phases/           # Phase implementations (design, testing, etc.)
```

See [Artisan Workflow Guide](ARTISAN_WORKFLOW_GUIDE.md) and [Contractors README](../src/startd8/contractors/README.md) for details.

## Data Models

### Core Models (`models.py`)

```python
from startd8 import (
    Prompt,              # Versioned prompt
    AgentResponse,       # Agent response with metrics
    Benchmark,           # Benchmark definition
    TokenUsage,          # Token usage statistics
    JobFile,             # Job queue entry
    JobQueueConfig,      # Queue configuration
)
```

### Agent Selection

The SDK provides a modular approach to agent selection:

```python
# Get all agents with Ready status
ready_agents = tui._get_ready_agents_for_selection()

# Select a single ready agent
agent = tui._select_ready_agent("Select an agent", "Claude")
```

## Configuration

### Environment Variables

```bash
# API Keys
ANTHROPIC_API_KEY="sk-ant-..."
OPENAI_API_KEY="sk-..."
CURSOR_API_KEY="..."

# Storage
STARTD8_DATA_DIR="~/.startd8"
```

### Config Files

```
~/.startd8/
├── config.json          # Main configuration
├── api_keys.json        # Stored API keys
├── custom_agents.json   # User-added agents
└── tui_settings.json    # TUI preferences
```

## Entry Points

### CLI (`cli.py`)

```bash
startd8 --help
startd8 tui              # Interactive TUI
startd8 create-prompt    # Create a prompt
startd8 run-benchmark    # Run benchmarks
startd8 queue run        # Process job queue
```

### Python API

```python
from startd8 import (
    AgentFramework,
    ClaudeAgent,
    GPT4Agent,
    Pipeline,
    WorkflowTemplates,
)
```

## Error Handling

Custom exception hierarchy:

```python
from startd8 import (
    Startd8Error,        # Base exception
    StorageError,        # Storage operations
    FileOperationError,  # File I/O
    ValidationError,     # Data validation
    APIError,            # API calls
    ConfigurationError,  # Configuration
    AgentError,          # Agent operations
)
```

## Logging

```python
from startd8 import get_logger, setup_logging

logger = get_logger(__name__)
setup_logging(level="DEBUG")
```

## Dependencies

### Required
- `rich>=13.0.0` - Terminal formatting
- `pydantic>=2.0.0` - Data validation
- `typer>=0.9.0` - CLI framework
- `httpx>=0.25.0` - HTTP client
- `questionary>=2.0.0` - Interactive prompts
- `pyyaml>=6.0.0` - YAML parsing

### Optional
- `anthropic>=0.18.0` - Claude API
- `openai>=1.0.0` - OpenAI API

## Future Considerations

1. **Database Storage**: Support for SQLite/PostgreSQL backends
2. **Async Support**: Async agent implementations
3. **Web Interface**: REST API and web UI
4. **Plugin System**: Third-party agent plugins
5. **Streaming**: Streaming response support



