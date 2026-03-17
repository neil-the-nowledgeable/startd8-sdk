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
│   ├── context_seed_handlers.py  # Compat wrapper — re-exports from context_seed/ subpackage
│   ├── context_seed/             # Phase handler implementations (refactored from context_seed_handlers.py)
│   │   ├── core.py               # Main handler classes (Design/Implement/Integrate/Review/Finalize/Test)
│   │   ├── design_support.py     # Design-phase helpers, CCD span attrs, complexity classification
│   │   ├── shared.py             # Shared utilities (PCA context fields, logging helpers)
│   │   ├── tracing.py            # OTel tracing integration
│   │   └── phases/               # Individual phase implementations (design, plan, scaffold)
│   ├── context_schema.py         # Pydantic output models (DesignPhaseOutput, ImplementPhaseOutput, ValidationPhaseOutput)
│   ├── context_resolution.py     # Context resolution strategies
│   ├── context_formatters.py     # JSON→Markdown context formatters with prompt injection mitigation
│   ├── copy_detection.py         # Identifies copy/copy-modify tasks to bypass LLM generation
│   ├── gate_contracts.py         # Phase boundary validation (QualitySpec, EvaluationSpec, GateEmitter)
│   ├── integration_engine.py     # INTEGRATE phase merge engine with pre/post-merge repair + semantic checks
│   ├── handoff.py                # Design↔Implementation handoff (two-half split)
│   ├── checkpoint.py             # Checkpoint/crash recovery
│   ├── prime_contractor.py       # PrimeContractorWorkflow
│   ├── prime_postmortem.py       # Post-mortem evaluation (16 RootCauses, disk quality scoring, Kaizen suggestions)
│   ├── batch_postmortem.py       # Cross-run batch analysis (accumulates results across runs sharing same seed)
│   ├── protocols.py              # Protocol interfaces
│   ├── registry.py               # Contractor registry
│   ├── queue.py                  # Task queueing (with cycle detection/breaking)
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
│       ├── lead_contractor_workflow.py  # Primary Contractor (aliased as PrimaryContractorWorkflow)
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
├── complexity/           # Complexity classification and tier routing
│   ├── classifier.py     # classify_tier() — TRIVIAL/SIMPLE/MODERATE/COMPLEX
│   ├── models.py         # TaskComplexitySignals dataclass
│   ├── router.py         # Routes tasks to appropriate generator by tier
│   └── signals.py        # Signal extraction from task metadata
│
├── micro_prime/          # Local code generation engine (element-level)
│   ├── engine.py         # MicroPrimeEngine — orchestrates element generation
│   ├── decomposer.py     # Moderate decomposer (Class/Function strategies)
│   ├── splicer.py        # Code splicing into existing files
│   ├── models.py         # GenerationPlan, SubElement, etc.
│   ├── templates.py      # Template registry for code generation
│   ├── prime_adapter.py  # PrimeContractor ↔ MicroPrime bridge
│   ├── repair.py         # Element-level repair
│   ├── metrics.py        # OTel metrics for generation
│   └── config_loader.py  # Configuration loading
│
├── repair/               # Post-generation repair pipeline
│   ├── orchestrator.py   # run_file_repair(), run_element_repair()
│   ├── diagnostics.py    # Checkpoint diagnostic parsing and classification
│   ├── routing.py        # Failure routing to repair steps
│   ├── staging.py        # Atomic staging for repair operations
│   ├── models.py         # RepairOutcome, RepairRoute, RepairStepResult
│   ├── config.py         # RepairConfig (repairable_categories, timeouts)
│   └── steps/            # Individual repair steps (fence_strip, ast_validate, etc.)
│
├── languages/            # Multi-language support (Protocol-based)
│   ├── protocol.py       # LanguageProfile protocol (15 properties/methods)
│   ├── registry.py       # LanguageRegistry singleton with entry point discovery
│   ├── resolution.py     # resolve_language() — dominant language from target files
│   ├── python.py         # PythonLanguageProfile (AST repair, Ruff lint, pytest)
│   ├── go.py             # GoLanguageProfile (goimports, text-based splicer, go.mod gen)
│   ├── go_parser.py      # Regex-based Go structure extraction (functions, types, methods)
│   ├── go_splicer.py     # Text-based Go body splicing with brace matching
│   ├── nodejs.py         # NodeLanguageProfile (CommonJS+ESM, package.json gen)
│   └── java.py           # JavaLanguageProfile (Gradle, build.gradle gen)
│
├── validators/           # Code quality validators
│   └── semantic_checks.py  # 4-check AST validator (dupe main guards, dupe defs, bare except, phantom imports)
│
├── implementation_engine/  # Code generation engine for contractors
│   ├── spec_builder.py   # Spec prompt construction (with enforce_prompt_budget)
│   ├── drafter.py        # Draft prompt construction (with budget check)
│   ├── budget.py         # Budget constants, enforce_prompt_budget(), truncation utils
│   └── prompts/          # YAML prompt templates
│       ├── __init__.py   # get_template(), format_prompt() with fallback strings
│       └── contractor_prompts.yaml  # Consolidated spec/draft/review templates
│
├── dashboard_creator/    # Grafana dashboard generation pipeline
│   ├── workflow.py       # DashboardCreatorWorkflow
│   ├── compiler.py       # Dashboard JSON compilation
│   ├── generator.py      # Panel/dashboard generation
│   └── models.py         # DashboardSpec, PanelSpec
│
├── seeds/                # Seed task builder and derivation
│   ├── builder.py        # SeedBuilder
│   ├── derivation.py     # Task derivation from plans
│   └── models.py         # Seed data models
│
├── project/              # Project scaffolding
│   ├── scaffolder.py     # Project structure generation
│   └── manifest.py       # Project manifest
│
├── forward_manifest.py           # ForwardManifest, InterfaceContract models
├── forward_manifest_validator.py # Contract violation detection + DiskComplianceResult disk validation
├── forward_manifest_extractor.py # Extract contracts from source code
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

scripts/                  # Runner and utility scripts (~45 files)
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

tests/                    # Test suite (~407 files)
├── unit/                 # Unit tests
│   ├── contractors/      # Contractor-specific unit tests (~2744 tests)
│   ├── micro_prime/      # Micro Prime engine tests (~355 tests)
│   ├── complexity/       # Complexity classifier tests
│   ├── repair/           # Repair pipeline tests
│   ├── seeds/            # Seed builder tests
│   ├── dashboard_creator/  # Dashboard creator tests
│   ├── implementation_engine/  # Implementation engine tests
│   ├── languages/        # Multi-language profile tests
│   ├── validators/       # Semantic checks + disk compliance tests
│   └── workflows/        # Workflow tests
├── contract_validation/  # Pipeline contract validation tests
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
- **Context Seed Handlers**: `DesignPhaseHandler`, `ImplementPhaseHandler`, `IntegratePhaseHandler`, `TestPhaseHandler`, `ReviewPhaseHandler`, `FinalizePhaseHandler` in `context_seed/core.py` (re-exported via `context_seed_handlers.py` compat wrapper)
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
- `ArtisanContractorWorkflow` - 8-phase code generation orchestrator (ON HOLD)
- `PrimeContractorWorkflow` - Multi-feature batch code generation (active construction path)
- `PrimePostMortemEvaluator` - Post-mortem evaluation with disk quality scoring
- `LanguageRegistry` - Multi-language profile discovery and resolution
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

### Complexity Classification and Micro Prime

The SDK routes code generation tasks by complexity tier:
- `complexity/classifier.py` — `classify_tier()` assigns TRIVIAL/SIMPLE/MODERATE/COMPLEX
- `complexity/router.py` — Routes tasks to the appropriate generator
- `micro_prime/engine.py` — `MicroPrimeEngine` handles SIMPLE/MODERATE tasks locally (no LLM calls for trivial)
- `micro_prime/decomposer.py` — Breaks MODERATE elements into SIMPLE sub-elements (Class/Function strategies)
- `micro_prime/splicer.py` — Splices generated code into existing files
- `micro_prime/prime_adapter.py` — Bridges PrimeContractor ↔ MicroPrime

### Multi-Language Support

The SDK supports code generation for multiple languages via a Protocol-based abstraction:

```python
from startd8.languages import LanguageProfile, LanguageRegistry, resolve_language

LanguageRegistry.discover()  # loads from entry points
profile = resolve_language(["src/main.go", "src/util.go"])  # -> GoLanguageProfile
```

| Language | ID | Capabilities | MicroPrime |
|----------|-----|-------------|------------|
| **Python** | `python` | AST repair, Ruff lint, pytest, pip | Full (AST splicer) |
| **Go** | `go` | goimports/gofmt, text-based stub detection, body splicing, go.mod gen | Bypass (text-based splicer only) |
| **Node.js** | `nodejs` | Node syntax check, npm test, CommonJS+ESM, package.json gen | Bypass |
| **Java** | `java` | Gradle compile, text-based stub detection, build.gradle gen | Bypass |

Key patterns:
- **LanguageProfile protocol**: 15 properties/methods covering syntax check, lint, test, stub detection, dependency file gen, Docker images, merge strategy
- **Non-Python bypass**: Non-Python tasks bypass MicroPrime element-level generation and use file-whole generation instead
- **resolve_language()**: Counts file extensions across target files, returns dominant language profile, falls back to Python
- **Go-specific tooling**: `go_parser.py` (regex-based structure extraction), `go_splicer.py` (text-based body splicing with brace matching)

### Kaizen Quality System

Cross-run quality measurement and improvement feedback loop (Phases A-E):

- **Phase A — Registry Enrichment**: `engine.py` emits generation metadata (strategy, model, timing, AST validity) per element
- **Phase B — Disk Validation**: `forward_manifest_validator.py:validate_disk_compliance()` → `DiskComplianceResult` (AST valid, stubs remaining, import completeness, contract compliance, semantic issues)
- **Phase C — Feedback Loop**: `prime_postmortem.py:CAUSE_TO_SUGGESTION` (25 root cause mappings) → `generate_kaizen_suggestions()` → kaizen hints injected as P1 sections in spec/draft prompts
- **Phase D — Semantic Validation**: `validators/semantic_checks.py` — 4 AST checks (duplicate main guards, duplicate definitions, bare except:pass, phantom imports). Wired into `integration_engine.py` as non-blocking warnings.
- **Phase E — Dual Scoring**: `compute_disk_quality_score()` = (contract_compliance × 0.4) + (import_completeness × 0.2) + (stub_penalty × 0.2) + (semantic_penalty × 0.2). `assembly_delta` = requirement_score - disk_quality_score.

Post-mortem artifacts per run:
- `prime-postmortem-report.json` — per-feature scores, disk compliance, semantic issues
- `prime-postmortem-summary.md` — human-readable summary
- `kaizen-metrics.json` — aggregate metrics (success rate, cost, assembly delta, semantic breakdown)
- `kaizen-suggestions.json` — actionable improvement suggestions
- `batch-postmortem-report.json` — cross-run progression tracking
- `kaizen-trends.json/md` — success rate slope, cost slope, failure patterns across runs
- `kaizen-correlation.json/md` — prompt feature ↔ outcome Spearman correlations

### Keiyaku A2A Contracts (Micro Prime)

Agent-to-agent boundaries in Micro Prime use typed contracts per the [Keiyaku Design Principle](docs/design-princples/KEIYAKU_DESIGN_PRINCIPLE.md):
- `ClassificationResult` — carries `TaskComplexitySignals` from classifier to decomposer (K-10)
- `EscalationHandoff` — structured JSON handoff replacing prose escalation context (K-6)
- `EscalationRepairOutcome` — structured repair diagnostics at escalation boundary (K-9)
- `SemanticVerificationResult` — pre-defined contract for LLM semantic verification (K-7)

See `docs/design/micro-prime/KEIYAKU_GAP_ANALYSIS.md` for the full boundary inventory.

### Repair Pipeline

Post-generation repair for syntax, lint, and import errors:
- `repair/orchestrator.py` — `run_file_repair()`, `run_element_repair()` orchestrators
- `repair/diagnostics.py` — Checkpoint diagnostic parsing and failure classification
- `repair/routing.py` — Routes failures to appropriate repair steps
- `repair/staging.py` — Atomic staging for safe repair operations
- Integration: `IntegrationEngine._attempt_pre_merge_repair()` (pre-merge) and `_attempt_repair()` (post-merge)

### Implementation Engine (Prompt Pipeline)

The `implementation_engine/` module handles spec→draft→review prompt construction:
- **Consolidated prompts**: All templates in `contractor_prompts.yaml` (single source of truth). Fallback strings in `prompts/__init__.py` ensure the engine works without the YAML file.
- **Budget enforcement**: `enforce_prompt_budget()` uses P0-P3 priority-ordered section removal. `TOTAL_SPEC_BUDGET_TOKENS` (4096) and `TOTAL_DRAFT_BUDGET_TOKENS` (8192) hard caps.
- **Primary Contractor**: The `LeadContractorWorkflow` is now also exported as `PrimaryContractorWorkflow` (alias). Comments/docstrings use "Primary Contractor" terminology; the `lead_contractor_*` filenames and class names are preserved for backward compatibility.

### Forward Manifest

Design-time contract forwarding for review-time validation:
- `forward_manifest.py` — `ForwardManifest`, `InterfaceContract` models
- `forward_manifest_extractor.py` — Extracts contracts from source code AST
- `forward_manifest_validator.py` — Validates generated code against contracts, produces `ContractViolation` list; also provides `DiskComplianceResult` + `validate_disk_compliance()` for post-assembly disk validation (10 validation layers: imports, stubs, duplicates, factory returns, discarded returns, service identity, method resolution, reachability, contract compliance, semantic issues)
- Consumed by `ReviewPhaseHandler` to enforce structural compliance and by `PrimePostMortemEvaluator` for disk quality scoring

### Context Seed Compat Wrapper Pattern

`context_seed_handlers.py` is a **compatibility wrapper** that re-exports all symbols from the `context_seed/` subpackage. This preserves the legacy import path (`from startd8.contractors.context_seed_handlers import X`) while allowing the implementation to live in organized submodules. **When modifying context_seed/, always verify that new public symbols are re-exported in the wrapper and that test `mock.patch` targets reference `context_seed.core`, not `context_seed_handlers`.**

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

# Workflows (16 registered)
[project.entry-points."startd8.workflows"]
pipeline, doc-enhancement, iterative-dev, design-polish,
critical-review, convergent-review, lead-contractor,
lead-contractor-contextcore, primary-contractor,
primary-contractor-contextcore, architectural-review-log,
policy-analysis, plain-language, plan-ingestion,
domain-preflight, dashboard-create

# Language profiles (4 registered)
[project.entry-points."startd8.languages"]
python, go, nodejs, java

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
- When modifying `context_seed/` subpackage, verify new symbols are re-exported in `context_seed_handlers.py` compat wrapper
- When splitting modules, run `grep -rn 'from old_module import\|patch.*old_module' tests/` to find all symbols and patch targets that need forwarding
- When adding new LLM-calling boundaries in `micro_prime/`, define JSON input/output contracts before implementation (REQ-MP-1010, Keiyaku compliance gate)
- Call `LanguageRegistry.discover()` before using language profiles (same pattern as ProviderRegistry)
- Non-Python tasks must bypass MicroPrime — use file-whole generation path via `prime_adapter.py`

### Must Avoid
- Don't hardcode API keys - they come from environment variables
- Don't skip provider validation - it checks for required config
- Don't use blocking calls in async code paths
- Don't modify the `__all__` exports without updating tests
- Don't use `logging.getLogger()` directly in `contractors/` or other SDK modules — logs silently miss Loki
- Don't hardcode model version strings — use `model_catalog.py` centralized defaults
- Don't use ad-hoc status strings in `task_tracking_emitter` — use ContextCore's canonical `TaskStatus` enum values from `contracts/types.py` (`todo`, not `pending`)
- Don't omit the top-level `status` field when creating ContextCore state files — SpanState v2 requires it (`UNSET`/`OK`/`ERROR`)
- Don't patch `context_seed_handlers.X` in tests when the code under test imports from `context_seed.core` — patch where the symbol is **looked up**, not where it's re-exported
- Don't split a module without updating the logger acquisition policy test allowlist (`test_logger_acquisition_policy.py`) for any new files using string logger names

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
- `docs/design/micro-prime/` - Micro Prime engine requirements and plans
- `docs/design/prime/` - Prime Contractor requirements, Kaizen convergent review
- `docs/design/kaizen/` - Kaizen quality system requirements, validation reports, phase plans
- `docs/design-princples/` - Cross-cutting design principles:
  - `MOTTAINAI_DESIGN_PRINCIPLE.md` - Don't discard artifacts (within a run)
  - `KAIZEN_DESIGN_PRINCIPLE.md` - Don't discard lessons (across runs)
  - `WARM_UP_DESIGN_PRINCIPLE.md` - Don't discard context (across toolchain transitions)
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
