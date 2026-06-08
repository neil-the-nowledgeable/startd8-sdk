# startd8 SDK Architecture

**Version:** 0.4.0
**Document Version:** v1.2
**Last Updated:** 2026-06-08

## Overview

startd8-SDK is a software-engineering harness and toolkit for LLM-assisted development. It has
two complementary halves:

1. **Deterministic-first code generation** — a Requirements→Capabilities delivery pipeline whose
   centerpiece is the `backend_codegen` cascade: project one Prisma data-model contract into a
   working all-Python application (Pydantic + SQLModel + FastAPI + HTMX) at **$0 LLM cost**,
   using language models only for integration glue.
2. **Multi-LLM agent framework** — provider-abstracted agents, benchmarking, prompt versioning,
   multi-step pipelines, cost tracking, and cloud/edge model evaluation.

It supports 8 providers (Anthropic, OpenAI, Gemini, Mistral, Ollama, NIM, OpenAI-compatible,
Mock) and 7 language profiles (Python — strongest — Go, Node.js, Java, C#, Vue, Prisma).

## Core Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              startd8 SDK                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐     │
│  │     CLI     │   │     TUI     │   │   Python    │   │  HTTP Server│     │
│  │  (typer)    │   │(questionary)│   │     API     │   │  (serve)    │     │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘     │
│         └─────────────────┴────────┬────────┴─────────────────┘             │
│                                    │                                         │
│   ┌────────────────────────────────┴────────────────────────────────┐      │
│   │                  Deterministic codegen ($0, no LLM)               │      │
│   │   backend_codegen: .prisma → Pydantic + SQLModel + FastAPI +     │      │
│   │   HTMX + views + export + AI-schemas + completeness               │      │
│   │   CLI: wireframe · generate (frontend/backend/scaffold/views) ·  │      │
│   │        polish · repair · manifest                                 │      │
│   └──────────────────────────────────┬────────────────────────────────┘    │
│                                       │                                       │
│   ┌───────────────────────────────────┴───────────────────────────────┐    │
│   │              LLM-assisted construction (integration)               │    │
│   │  Prime Contractor (active) · Artisan Contractor (ON HOLD) ·        │    │
│   │  Micro Prime · Repair · Kaizen · Security/Query Prime             │    │
│   └───────────────────────────────────┬───────────────────────────────┘    │
│                                        │                                      │
│                          ┌─────────────▼─────────────┐                       │
│                          │  AgentFramework (agents,   │                       │
│                          │  benchmarking, pipelines)  │                       │
│                          └─────────────┬─────────────┘                       │
│         ┌──────────────────────────────┼──────────────────────────┐         │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐       │
│  │  Providers  │  │  Languages  │  │   Storage   │  │  Job Queue  │       │
│  │  (8, entry  │  │  (7, entry  │  │ (file/JSON) │  │ (file-based)│       │
│  │   points)   │  │   points)   │  │             │  │             │       │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │
├─────────────────────────────────────────────────────────────────────────────┤
│  Support: Models (Pydantic) · Config · Cost Tracking · OTel/Loki · Prompt    │
│           Builder · Forward Manifest · Complexity routing · Exemplars        │
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

**Providers** are discovered via entry points (`ProviderRegistry.discover()`). 8 are registered:
`anthropic`, `openai`, `gemini`, `mistral`, `ollama`, `nim`, `openai-compatible`, `mock`.
Edge/local and self-hosted models run through `ollama`, `nim`, and any OpenAI-compatible endpoint.

**Languages** are likewise entry-point discovered (`LanguageRegistry.discover()`). 7 profiles:
`python` (strongest — AST repair/splicing; the deterministic backend target), `go`, `nodejs`,
`java`, `csharp`, `vue`, `prisma`.

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

### 9. Deterministic Code Generation (`backend_codegen/`)

The $0 cascade — the headline capability. Projects **one Prisma data-model contract** into a
working all-Python application with **no LLM calls**. Output is byte-identical/idempotent and
drift-checkable; ~12 owned file kinds, all deterministic-skip.

Public API (`from startd8.backend_codegen import ...`):

```python
render_backend            # full backend assembler (the cascade entry point)
render_pydantic_models    # .prisma → Pydantic models
render_sqlmodel_tables    # .prisma → SQLModel tables
render_routers, render_db, render_main, render_spine   # FastAPI CRUD + wiring
render_web, render_ui, render_pages, render_authoring   # HTMX UI + page authoring
render_export, render_ai_schemas, render_completeness   # export / LLM-facing / completeness
render_requirements       # generated requirements.txt
render_contract_tests, render_completeness_tests        # generated test suites
check_drift, owned_file_in_sync, is_owned_generated_file # drift detection (`generate --check`)
verify_pydantic_fidelity, verify_sqlmodel_fidelity      # contract-fidelity gates
PydanticSQLModelProvider, CANONICAL_LAYOUT
```

CLI: `startd8 wireframe` (preview), `startd8 generate {frontend|backend|scaffold|views}`,
`startd8 polish`. The deterministic toolchain gate lives in `validators/python_toolchain.py`.

### 10. Contractors (`contractors/`) — LLM-assisted integration

Multi-phase workflow orchestration for the integration passes (bucket 3):

- **Prime Contractor** (active path): per-feature `generate → integrate → validate` loop with
  protocol-based design (CodeGenerator, Instrumentor, SizeEstimator, MergeStrategy), tier
  routing (template → Haiku → Sonnet), checkpoint/resume, and Kaizen cross-run quality feedback.
- **Artisan Contractor** (**ON HOLD since 2026-03-12** — kept for reference, not deleted): the
  legacy 8-phase workflow (PLAN→SCAFFOLD→DESIGN→IMPLEMENT→INTEGRATE→TEST→REVIEW→FINALIZE).
  Prime-vs-Artisan routing is vestigial.
- **Micro Prime** (`micro_prime/`): element-level local generation for SIMPLE/MODERATE tasks.
- **Repair** (`repair/`): ~45 post-generation repair steps organized by language.
- **Design Handoff** (`handoff.py`): serializable context state (`design-handoff.json`) for
  two-half split execution.

```
contractors/
├── prime_contractor.py       # PrimeContractorWorkflow (active)
├── integration_engine.py     # generate→merge→checkpoint→repair engine
├── queue.py                  # feature queue + cycle detection + resume
├── checkpoint.py             # per-phase checkpoint/crash recovery
├── batch_postmortem.py       # BatchLedger cross-run progression
├── artisan_contractor.py     # ArtisanContractorWorkflow (ON HOLD)
├── context_seed/             # phase handlers (+ context_seed_handlers.py wrapper)
├── handoff.py                # design handoff persistence
└── protocols.py              # protocol interfaces
```

See [Prime Contractor Workflow Guide](PRIME_CONTRACTOR_WORKFLOW_GUIDE.md). The Capability
Delivery Pipeline (`.cap-dev-pipe/`) drives requirements → app end to end.

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

## Observability

OpenTelemetry traces/metrics/logs flow to a Loki/Grafana stack; per-provider cost tracking lives
in `costs/`. Use `from startd8.logging_config import get_logger` (not `logging.getLogger()`) so
logs reach the OTel→Loki bridge. CLI: `startd8 otel-status`, `startd8 otel-configure`. See
[LOKI_SETUP_GUIDE](LOKI_SETUP_GUIDE.md).

## Future Considerations

1. **Polyglot deterministic codegen**: extend the `backend_codegen` cascade beyond Python
2. **Completeness domain manifest**: enforce "AI never writes derived/value fields"
3. **Streaming**: streaming response support
4. **Database Storage**: optional SQLite/PostgreSQL storage backends

> Already shipped (previously listed as future): async agent variants, the HTTP server
> (`startd8 serve`), and the entry-point plugin system for providers/languages/workflows.



