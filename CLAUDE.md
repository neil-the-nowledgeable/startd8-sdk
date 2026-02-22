# CLAUDE.md

This file provides guidance to Claude Code for the StartDate (startd8) SDK repository.

## Project Overview

StartD8 is a Python SDK and CLI tool for managing multi-LLM agent workflows, benchmarking different models (Anthropic, OpenAI, Gemini, Mistral, Ollama), and prompt version control. It provides a unified interface for comparing LLM responses, tracking costs, and orchestrating multi-phase code generation (Artisan Contractor 8-phase pipeline, PrimeContractor batch workflows). Includes ContextCore integration for project observability and OTel-based telemetry.

## Tech Stack

- **Language:** Python 3.9+ (venv uses 3.14)
- **CLI Framework:** Typer with Rich for terminal output
- **Data Models:** Pydantic v2
- **HTTP Client:** httpx (async support)
- **Build System:** setuptools with pyproject.toml
- **Testing:** pytest with pytest-asyncio (markers: unit, integration, slow, asyncio, evaluation)
- **Observability:** OpenTelemetry (traces, metrics, logs) with Loki/Grafana stack

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
src/startd8/              # Main package
├── __init__.py           # Public API exports
├── cli.py                # Typer CLI commands
├── framework.py          # Core AgentFramework class
├── benchmark.py          # BenchmarkRunner and ComparisonReport
├── models.py             # Pydantic data models
├── orchestration.py      # Pipeline and workflow orchestration
├── config.py / config_models.py  # Configuration management
├── model_catalog.py      # Model discovery and centralized defaults
├── truncation_detection.py  # Code-aware truncation detection
├── security.py           # Security utilities
├── logging_config.py     # Logging configuration
├── logging_otel.py       # OpenTelemetry log bridge
├── otel.py               # OpenTelemetry integration
├── document_enhancement.py  # Document enhancement chains
│
├── agents/               # Agent implementations
│   ├── base.py           # BaseAgent protocol
│   ├── claude.py         # Anthropic/Claude agent
│   ├── openai.py         # OpenAI/GPT agent
│   ├── gemini.py         # Google Gemini agent
│   ├── mock.py           # Mock agent for testing
│   ├── pool.py           # Agent pool management
│   └── tracked.py        # Tracked agent wrapper
│
├── providers/            # Provider abstraction layer
│   ├── protocol.py       # Provider protocol (interface)
│   ├── registry.py       # ProviderRegistry for discovery
│   ├── anthropic.py      # Anthropic/Claude provider
│   ├── openai.py         # OpenAI/GPT provider (+ Ollama)
│   ├── gemini.py         # Google Gemini provider
│   ├── mistral.py        # Mistral AI provider
│   └── mock.py           # Mock provider for testing
│
├── costs/                # Cost tracking system
│   ├── tracker.py        # CostTracker
│   ├── pricing.py        # PricingService
│   ├── budget.py         # BudgetManager
│   ├── analytics.py      # CostAnalytics
│   ├── otel_metrics.py   # OTel cost metrics export
│   └── usage_limits.py   # Usage limit management
│
├── contractors/          # Multi-phase workflow orchestration
│   ├── artisan_contractor.py     # ArtisanContractorWorkflow (8-phase orchestrator)
│   ├── artisan_models.py         # Artisan phase data models
│   ├── artisan_prompts.py        # Artisan phase prompt templates
│   ├── context_seed_handlers.py  # Phase handlers (Design/Implement/Integrate/Review/Finalize/Test)
│   ├── context_schema.py         # Pydantic output models (DesignPhaseOutput, ImplementPhaseOutput, ValidationPhaseOutput)
│   ├── gate_contracts.py         # Phase boundary validation (QualitySpec, EvaluationSpec)
│   ├── handoff.py                # Design↔Implementation handoff (two-half split)
│   ├── checkpoint.py             # Checkpoint/crash recovery
│   ├── prime_contractor.py       # PrimeContractorWorkflow
│   ├── protocols.py              # Protocol interfaces
│   ├── registry.py               # Contractor registry
│   ├── queue.py                  # Task queueing
│   ├── cli_helpers.py            # CLI helper functions
│   ├── generators/               # Code generators (LeadContractor)
│   ├── adapters/                 # Instrumentation adapters (ContextCore, Standalone)
│   ├── contracts/                # Pipeline contract YAML specs
│   │   └── artisan-pipeline.contract.yaml  # Phase entry/exit requirements + quality gates
│   └── artisan_phases/           # 12 individual phase implementations
│       ├── context.py            # Shared phase context
│       ├── plan_deconstruction.py  # PLAN phase
│       ├── design_documentation.py # DESIGN phase (dual-review orchestration)
│       ├── development.py          # IMPLEMENT phase (LLMChunkExecutor)
│       ├── test_construction.py    # TEST phase (LLMTestGenerator)
│       ├── final_testing.py        # TEST validation
│       ├── final_assembly.py       # FINALIZE phase
│       ├── preflight.py            # Preflight checks
│       ├── domain_checklist.py     # Domain-aware constraints
│       ├── lessons_discovery.py    # Lessons discovery
│       ├── retrospective.py        # Retrospective phase
│       └── runner.py               # Phase runner
│
├── utils/                # Shared utilities
│   ├── agent_resolution.py       # Agent spec resolution
│   ├── code_extraction.py        # Code extraction from LLM responses
│   ├── file_operations.py        # File I/O operations
│   ├── prime_task_enrichment.py  # Prime task enrichment
│   ├── retry.py                  # Retry logic
│   └── token_usage.py            # Token usage tracking
│
├── workflows/            # Workflow orchestration
│   ├── base.py           # WorkflowBase class
│   ├── registry.py       # Workflow registry
│   ├── models.py         # Workflow data models
│   └── builtin/          # Built-in workflows
│       ├── lead_contractor_workflow.py
│       ├── plan_ingestion_workflow.py
│       ├── domain_preflight_workflow.py
│       ├── critical_review_workflow.py
│       ├── convergent_review_workflow.py  # Multi-round convergent review
│       ├── design_polish_workflow.py
│       ├── architectural_review_log_workflow.py
│       ├── doc_review_log_workflow.py
│       ├── iterative_dev_workflow.py
│       ├── task_tracking_emitter.py       # ContextCore SpanState v2 task emission
│       ├── schema_versions.py             # Schema version constants
│       └── preflight_rules/  # Domain-specific preflight rule system
│
├── diagnostics/          # Diagnostic/validation system with auto-fix
├── observability/        # OTel manifest and collector
├── evaluation/           # Evaluation corpus and pipeline
├── storage/              # Storage backends
├── events/               # Event bus system
├── mcp/                  # MCP (Model Context Protocol) integration
├── skills/               # Skill agents and factories
├── prompt_builder/       # Prompt templating system
├── ratelimit/            # Rate limiting
├── resilience/           # Resilience patterns
├── server/               # REST API server (Starlette: /workflows, /workflows/{id}/run)
├── integrations/         # ContextCore workflow adapter and task runner
├── testing/              # Test assertion utilities
└── help_content/         # TUI help YAML files (topics, contextual, workflow, advanced)

scripts/                  # Runner and utility scripts (~25 files)
├── run_artisan_workflow.py       # Full 8-phase artisan workflow
├── run_artisan_design_only.py    # Design half (PLAN→SCAFFOLD→DESIGN)
├── run_artisan_implement_only.py # Impl half (IMPLEMENT→INTEGRATE→TEST→REVIEW→FINALIZE)
├── run_artisan_contractor.py     # Main artisan contractor runner
├── run_prime_workflow.py         # PrimeContractor batch workflow runner
├── run_contextcore_workflow.py   # ContextCore integration workflow
├── run_iterative_plan_ingestion.py  # Plan ingestion pipeline
├── emit_task_tracking.py         # ContextCore task tracking emission
├── enrich_prime_tasks.py         # Prime task enrichment
├── generate_observability_manifest.py  # OTel manifest generation
└── ...                           # OTel, evaluation, decompose scripts

tests/                    # Test suite (~133 files)
├── unit/                 # Unit tests
├── unit/contractors/     # Contractor-specific unit tests
├── contractors/          # Contractor integration tests
├── integration/          # Integration tests
├── e2e/                  # End-to-end tests
├── plan_validation/      # Plan ingestion validation tests
└── costs/                # Cost tracking tests

docs/                     # Documentation (~40 files)
examples/                 # Usage examples
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

### Artisan Contractor (8-Phase Orchestrator)

The primary code generation pipeline, split into a design half and implementation half:

1. **PLAN** - Plan deconstruction into implementable chunks
2. **SCAFFOLD** - Project structure scaffolding
3. **DESIGN** - Design documentation with dual-review orchestration (`AgentLLMBackend`)
4. **IMPLEMENT** - Code generation via `LLMChunkExecutor` with cost tracking (writes to staging)
5. **INTEGRATE** - Merge staged files into project root with validation and rollback (no LLM calls)
6. **TEST** - Test generation via `LLMTestGenerator` with retry
7. **REVIEW** - LLM-powered quality review
8. **FINALIZE** - Final assembly and validation

Key patterns:
- **Handoff**: Design half (PLAN→SCAFFOLD→DESIGN) produces a handoff file consumed by implementation half (IMPLEMENT→INTEGRATE→TEST→REVIEW→FINALIZE)
- **Context Seed Handlers**: `DesignPhaseHandler`, `ImplementPhaseHandler`, `IntegratePhaseHandler`, `TestPhaseHandler`, `ReviewPhaseHandler`, `FinalizePhaseHandler` in `context_seed_handlers.py`
- **HandlerConfig.from_config()**: Loads handler configuration from artisan YAML config
- **Checkpoint/Recovery**: Per-phase crash recovery via `checkpoint.py`; generation results saved for resume
- **Resume Caching**: IMPLEMENT, TEST, and REVIEW phases persist results to `.startd8/state/` with 3-layer validation (schema version → source checksum → per-task file hash)
- **Contract Validation**: `artisan-pipeline.contract.yaml` defines entry/exit requirements per phase with QualitySpec and EvaluationSpec; validated by `gate_contracts.py`
- **Per-task Error Guards**: Each phase wraps per-task work in try/except to prevent single-task failures from aborting the entire phase
- **Per-phase timeouts**: Configurable via CLI args

### Key Classes

- `AgentFramework` - Core orchestration, manages prompts/responses/storage
- `BenchmarkRunner` - Run comparisons across multiple agents
- `Pipeline` - Sequential workflow execution
- `ProviderRegistry` - Dynamic provider discovery via entry points
- `CostTracker` - Track API costs across providers
- `ArtisanContractorWorkflow` - 8-phase code generation orchestrator
- `PrimeContractorWorkflow` - Multi-feature batch code generation
- `WorkflowBase` - Base class for registered workflows
- `ModelCatalogEntry` - Centralized model defaults with `.agent_spec` property

### ContextCore Integration

`integrations/contextcore.py` provides unified project observability and task tracking:
- `ContextCoreConfig` - Configuration for project/task/sprint IDs
- `ContextCoreWorkflowAdapter` - Wraps workflows with OTel span tracking
- `ContextCoreTaskRunner` - Multi-task runner with dependency resolution
- `ContextCoreTaskSource` - Loads tasks from `~/.contextcore/state/{project}/` (single-project only)
- OTel semantic conventions: `CONTEXTCORE_PROJECT_ID`, `CONTEXTCORE_TASK_ID`, etc.

**SpanState v2 compliance** (when emitting ContextCore state files via `task_tracking_emitter`):
- Top-level `status` field is **required**: `"OK"` / `"ERROR"` / `"UNSET"` (distinct from `task.status` attribute)
- `task.status` must use ContextCore canonical enum: `backlog|todo|in_progress|in_review|blocked|done|cancelled` — NOT `"pending"`
- `task.type` must use canonical enum: `epic|story|task|subtask|bug|spike|incident` — custom classifiers go in `task.labels`
- `task.percent_complete` attribute required for Grafana gauge panels
- Zero-point `task.created` event with `percent_complete: 0` required for burndown charts
- See `ContextCore/docs/plans/WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md` (REQ-8) for cross-repo dashboard alignment

### Session Tracking

`session_tracking.py` provides session lifecycle management:
- `SessionTracker` / `get_session_tracker()` - Track session state, metrics, and context usage
- `SessionMetrics`, `SessionState`, `ContextUsage` - Session data models

### Entry Points

The SDK uses `pyproject.toml` entry points for plugin discovery:
```toml
# Providers (6 registered)
[project.entry-points."startd8.providers"]
anthropic, openai, ollama, gemini, mistral, mock

# Workflows (13 registered)
[project.entry-points."startd8.workflows"]
pipeline, doc-enhancement, iterative-dev, design-polish,
critical-review, convergent-review, lead-contractor,
lead-contractor-contextcore, architectural-review-log,
policy-analysis, plain-language, plan-ingestion, domain-preflight

# Contractor plugins
[project.entry-points."startd8.contractors.instrumentors"]
[project.entry-points."startd8.contractors.size_estimators"]
[project.entry-points."startd8.contractors.merge_strategies"]

# Third-party preflight rules
[project.entry-points."startd8.preflight_rules"]
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
- `mistral:mistral-large-latest`
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
- Use `from startd8.logging_config import get_logger` for logging in SDK modules (NOT `logging.getLogger()`) — ensures OTel log bridge attachment for Loki visibility
- Use `ModelCatalogEntry.agent_spec` for model defaults — don't scatter hardcoded model strings

### Must Avoid
- Don't hardcode API keys - they come from environment variables
- Don't skip provider validation - it checks for required config
- Don't use blocking calls in async code paths
- Don't modify the `__all__` exports without updating tests
- Don't use `logging.getLogger()` directly in `contractors/` or other SDK modules — logs silently miss Loki
- Don't hardcode model version strings — use `model_catalog.py` centralized defaults
- Don't use ad-hoc status strings in `task_tracking_emitter` — use ContextCore's canonical `TaskStatus` enum values from `contracts/types.py` (`todo`, not `pending`)
- Don't omit the top-level `status` field when creating ContextCore state files — SpanState v2 requires it (`UNSET`/`OK`/`ERROR`)

### Environment Variables
```bash
ANTHROPIC_API_KEY    # For Claude models
OPENAI_API_KEY       # For GPT models
GOOGLE_API_KEY       # For Gemini models
MISTRAL_API_KEY      # For Mistral models
OLLAMA_HOST          # Ollama server URL (optional)
```

### Infrastructure Config (repo root)
- `pytest.ini` - Test markers and asyncio config
- `docker-compose.loki-stack.yml` - Loki/Grafana observability stack
- `promtail-config.yml` - Log shipping to Loki
- `.contextcore.yaml` - ContextCore project/task configuration

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
- `ARTISAN_WORKFLOW_GUIDE.md` - Artisan contractor workflow guide (phases, handoff, scripts)
- `COST_TRACKING_USER_GUIDE.md` - Cost tracking guide
- `PIPELINE_WORKFLOWS_v1.md` - Pipeline workflows
- `PRIME_CONTRACTOR_WORKFLOW_GUIDE.md` - Prime contractor pattern guide
- `TUI_USER_GUIDE_v1.md` - TUI usage guide
- `DOWNSTREAM_WORKAROUND_CATALOG.md` - Downstream project workaround tracking
- `ITERATIVE_DEV_WORKFLOW.md` - Iterative development workflow
- `FEATURE_WORKFLOW_GUIDE.md` - Feature workflow guide
- `LOKI_SETUP_GUIDE.md` - Observability/Loki setup
- `PATTERN-truncation-detection.md` - Code-aware truncation detection pattern
- `PATTERN-silent-telemetry-loss.md` - OTel log bridge init gap pattern
- `ARTISAN_WORKFLOW_ISSUES_CATALOG.md` - Known artisan pipeline issues and fixes
- `docs/design/` - Design documents for major features
- `docs/capability-index/` - Capability tracking across versions (benefits, capabilities, functional requirements, agent card, MCP tools)

## Embedded Pipeline (`.cap-dev-pipe/`)

This project embeds the **Capability Delivery Pipeline** via symlinks to the canonical source at `~/Documents/dev/cap-dev-pipe/`. The `.cap-dev-pipe/` directory contains:

- **Symlinked scripts** — `run-cap-delivery.sh`, `run-plan-ingestion.sh`, `run-prime-contractor.sh`, `run-artisan.sh`, `resolve-provenance.py`
- **`pipeline.env`** — project-specific config (tracked in git)
- **`pipeline-output/`** — runtime artifacts (gitignored)

Run pipeline commands from `.cap-dev-pipe/`:
```bash
cd .cap-dev-pipe
./run-cap-delivery.sh --plan /path/to/plan.md --requirements /path/to/reqs.md --project startd8 --name my-run
./run-plan-ingestion.sh --provenance pipeline-output/my-run/run-provenance.json
./run-prime-contractor.sh --provenance pipeline-output/my-run/run-provenance.json --list
```

## Lessons Learned

See `SDK_developer_LESSONS_LEARNED.md` at `/Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/` for accumulated development wisdom.
