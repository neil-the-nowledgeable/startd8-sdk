# startd8 API Reference

**Version:** 0.4.0
**Document Version:** v1.2
**Last Updated:** 2026-06-08

> **Scope note.** startd8 has two halves. The **deterministic code generation** API (the headline
> capability) is in [§0](#deterministic-code-generation) and the [CLI](#cli-command-surface).
> The **agent-framework** API (benchmarking, pipelines, agents) follows from §1 onward and is
> unchanged. A few legacy concrete agent classes (`ClaudeAgent`, `GPT4Agent`) remain for
> backward compatibility, but the preferred entry point is `ProviderRegistry` (see
> [Agent Classes](#agent-classes)).

## Table of Contents

0. [Deterministic Code Generation](#deterministic-code-generation)
1. [CLI Command Surface](#cli-command-surface)
2. [Core Classes](#core-classes)
3. [Agent Classes](#agent-classes)
4. [Orchestration](#orchestration)
5. [Contractors](#contractors)
6. [Data Models](#data-models)
7. [Storage](#storage)
8. [Job Queue](#job-queue)
9. [Document Enhancement](#document-enhancement)
10. [Exceptions](#exceptions)
11. [Utilities](#utilities)

---

## Deterministic Code Generation

`$0`, no LLM calls. Projects one Prisma data-model contract into a working all-Python
application (Pydantic + SQLModel + FastAPI + HTMX). Output is idempotent and drift-checkable.

```python
from startd8.backend_codegen import (
    render_backend,            # full cascade entry point (.prisma + inputs → file set)
    render_pydantic_models,    # → Pydantic models     (PydanticRenderResult)
    render_sqlmodel_tables,    # → SQLModel tables      (SQLModelRenderResult)
    render_routers, render_db, render_main, render_spine,    # FastAPI CRUD + wiring
    render_web, render_ui, render_pages, render_authoring,   # HTMX UI + page authoring
    render_export, render_ai_schemas, render_completeness,   # export / LLM-facing / completeness
    render_requirements,                                     # generated requirements.txt
    render_contract_tests, render_completeness_tests,        # generated test suites
    check_drift, owned_file_in_sync, is_owned_generated_file,  # drift detection
    verify_pydantic_fidelity, verify_sqlmodel_fidelity,       # contract-fidelity gates
    PydanticSQLModelProvider, CANONICAL_LAYOUT,
)
```

These are normally invoked through the CLI (below) rather than directly. Drift detection backs
`startd8 generate --check` (CI-friendly: non-zero exit when a generated file is out of sync).

---

## CLI Command Surface

`startd8 <command>` — run `startd8 --help` or `startd8 <command> --help` for full options.

| Area | Commands |
|------|----------|
| **Deterministic codegen** | `wireframe`, `generate {frontend\|backend\|scaffold\|views}`, `polish`, `repair`, `manifest` |
| **Pipeline & contractors** | `workflow`, `project`, `queue`, `compare-models`, `assist`, `fde`, `sapper`, `element-registry` |
| **Benchmarking & prompts** | `init`, `create-prompt`, `list-prompts`, `show-prompt`, `run-benchmark`, `compare`, `list-responses`, `show-response`, `stats`, `templates`, `build-prompt` |
| **Pipelines & serving** | `pipeline`, `serve`, `dashboard` |
| **Interactive & ops** | `tui`, `otel-status`, `otel-configure` |

Key codegen/eval commands:

```bash
startd8 wireframe --inputs assembly-inputs.yaml [--json]   # $0 read-only preview
startd8 generate backend  --schema schema.prisma --out ./app
startd8 generate scaffold --inputs app.yaml --out ./app
startd8 generate views    --inputs views.yaml --out ./app
startd8 generate --check                                   # CI drift check (non-zero on drift)
startd8 polish ./app                                       # $0 accessible theme
startd8 compare-models --seed seed.json --model anthropic:... --model ollama:...
```

---

## Core Classes

### AgentFramework

Main orchestrator for the startd8 SDK.

```python
from startd8 import AgentFramework

framework = AgentFramework(storage_dir: Optional[Path] = None)
```

#### Parameters
- `storage_dir`: Optional path to project data directory. Defaults to `./.startd8`  
  (User-scoped config like API keys and TUI settings defaults to `~/.startd8`)

#### Methods

##### create_prompt

```python
prompt = framework.create_prompt(
    content: str,
    version: str,
    tags: List[str] = None,
    metadata: Dict[str, Any] = None
) -> Prompt
```

Create a new versioned prompt.

##### get_prompt

```python
prompt = framework.get_prompt(prompt_id: str) -> Optional[Prompt]
```

Retrieve a prompt by ID.

##### list_prompts

```python
prompts = framework.list_prompts(
    tags: List[str] = None,
    limit: int = None,
    offset: int = 0
) -> List[Prompt]
```

List prompts with optional filtering.

##### record_response

```python
response = framework.record_response(
    prompt_id: str,
    agent_name: str,
    model: str,
    response: str,
    response_time_ms: int,
    token_usage: TokenUsage,
    metadata: Dict[str, Any] = None
) -> AgentResponse
```

Record an agent response.

##### compare_responses

```python
comparison = framework.compare_responses(prompt_id: str) -> Dict[str, Any]
```

Compare all responses for a prompt.

Returns:
```python
{
    "prompt_id": str,
    "responses": List[AgentResponse],
    "metrics": {
        "avg_response_time_ms": float,
        "total_tokens": int,
        "total_cost": float,
    },
    "rankings": {
        "by_speed": List[str],
        "by_token_efficiency": List[str],
        "by_cost": List[str],
    }
}
```

---

## Agent Classes

### BaseAgent (Abstract)

```python
from startd8 import BaseAgent

class BaseAgent(ABC):
    def __init__(self, name: str, model: str)
    
    @abstractmethod
    def generate(self, prompt: str) -> Tuple[str, int, TokenUsage]
    
    def create_response(
        self,
        prompt_id: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentResponse
```

### ClaudeAgent

```python
from startd8 import ClaudeAgent

agent = ClaudeAgent(
    name: str = "anthropic:claude-sonnet-4-20250514",
    model: str = "claude-sonnet-4-20250514",
    api_key: Optional[str] = None,
    max_tokens: int = 4096
)
```

#### Parameters
- `name`: Agent identifier
- `model`: Claude model to use
- `api_key`: API key (defaults to `ANTHROPIC_API_KEY` env var)
- `max_tokens`: Maximum tokens in response

#### Available Models
- `claude-sonnet-4-20250514`
- `claude-sonnet-4-20250514`
- `claude-sonnet-4-20250514`
- `claude-haiku-4-5-20251008`

### GPT4Agent

```python
from startd8 import GPT4Agent

agent = GPT4Agent(
    name: str = "openai:gpt-4o",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    max_tokens: int = 4096
)
```

#### Parameters
- `name`: Agent identifier
- `model`: OpenAI model to use
- `api_key`: API key (defaults to `OPENAI_API_KEY` env var)
- `max_tokens`: Maximum tokens in response

#### Available Models
- `gpt-4o`
- `gpt-4o`
- `gpt-4`
- `gpt-4o`
- `gpt-4o-mini`
- `gpt-3.5-turbo`

### OpenAICompatibleAgent

```python
from startd8.agents import OpenAICompatibleAgent

agent = OpenAICompatibleAgent(
    name: str,
    model: str,
    base_url: str,
    api_key_env: Optional[str] = None,
    max_tokens: int = 4096
)
```

#### Parameters
- `name`: Agent identifier
- `model`: Model name
- `base_url`: API base URL
- `api_key_env`: Environment variable for API key
- `max_tokens`: Maximum tokens in response

### MockAgent

```python
from startd8 import MockAgent

agent = MockAgent(
    name: str = "mock",
    model: str = "mock-model"
)
```

For testing purposes. Returns deterministic mock responses.

### ComposerAgent

```python
from startd8.agents import ComposerAgent

agent = ComposerAgent(
    name: str = "composer",
    model: str = "composer-1"
)
```

Cursor's Composer model integration.

---

## Orchestration

### Pipeline

```python
from startd8 import Pipeline

pipeline = Pipeline(
    name: str = "pipeline",
    framework: Optional[AgentFramework] = None
)
```

#### Methods

##### add_step

```python
pipeline.add_step(
    name: str,
    agent: BaseAgent,
    transform: Optional[Callable[[str], str]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Pipeline
```

Add a step to the pipeline.

##### run

```python
result = pipeline.run(
    initial_input: str,
    store: bool = True
) -> PipelineResult
```

Execute the pipeline.

### WorkflowTemplates

Pre-built pipeline templates.

```python
from startd8 import WorkflowTemplates

# Planner-Implementer workflow
pipeline = WorkflowTemplates.planner_implementer(
    planner: BaseAgent,
    implementer: BaseAgent
) -> Pipeline

# Code Review workflow
pipeline = WorkflowTemplates.code_review(
    reviewer: BaseAgent,
    improver: BaseAgent
) -> Pipeline

# Design Review Chain (3-step)
pipeline = WorkflowTemplates.design_review_chain(
    drafter: BaseAgent,
    reviewer: BaseAgent,
    final_reviewer: BaseAgent
) -> Pipeline
```

### PipelineResult

```python
@dataclass
class PipelineResult:
    steps: List[Dict[str, Any]]
    final_output: str
    total_time_ms: int
    total_tokens: int
    total_cost: float
    pipeline_id: str
    timestamp: datetime
```

---

## Contractors

Multi-phase workflow orchestration for the LLM-assisted **integration** passes (bucket 3).

> **Active path: Prime Contractor.** `PrimeContractorWorkflow` is the only active construction
> path; use it (or the `.cap-dev-pipe/` Capability Delivery Pipeline) for multi-feature
> generation. The **Artisan Contractor is ON HOLD (2026-03-12)** — its API is documented below
> for reference and remains importable, but new work should target Prime. See the
> [Prime Contractor Workflow Guide](PRIME_CONTRACTOR_WORKFLOW_GUIDE.md) and
> [PRIME_CONTRACTOR_CONFIG_REFERENCE](PRIME_CONTRACTOR_CONFIG_REFERENCE.md).

### ArtisanContractorWorkflow (ON HOLD — reference only)

```python
from startd8.contractors.artisan_contractor import (
    ArtisanContractorWorkflow,
    WorkflowConfig,
    WorkflowPhase,
    WorkflowResult,
    WorkflowStatus,
    PhaseStatus,
    PhaseResult,
    AbstractPhaseHandler,
)
```

#### WorkflowConfig

```python
config = WorkflowConfig(
    workflow_id: str = auto,              # Auto-generated UUID
    dry_run: bool = False,
    total_timeout_seconds: float = None,
    phase_timeout_seconds: float = None,
    cost_budget: float = None,            # Max USD across all phases
    max_retries_per_phase: int = 0,
    checkpoint_dir: str = None,
    project_root: str = None,
    metadata: dict = {},
)
```

#### ArtisanContractorWorkflow Methods

```python
workflow = ArtisanContractorWorkflow(
    config: WorkflowConfig = None,
    handlers: dict[WorkflowPhase, AbstractPhaseHandler] = None,
    checkpoint_store: CheckpointStore = None,
    phases: list[WorkflowPhase] = None,   # Default: all 8 phases
)

# Register a phase handler
workflow.register_handler(
    phase: WorkflowPhase,
    handler: AbstractPhaseHandler,
) -> None

# Execute the workflow
result: WorkflowResult = workflow.execute(
    context: dict = None,                 # Shared mutable context
    resume_from: str = None,              # Phase name to resume from
    resume_from_checkpoint: bool = False,  # Load last checkpoint
)
```

#### WorkflowPhase

```python
WorkflowPhase.PLAN       # "plan"
WorkflowPhase.SCAFFOLD   # "scaffold"
WorkflowPhase.DESIGN     # "design"
WorkflowPhase.IMPLEMENT  # "implement"
WorkflowPhase.TEST       # "test"
WorkflowPhase.REVIEW     # "review"
WorkflowPhase.FINALIZE   # "finalize"

WorkflowPhase.ordered() -> list[WorkflowPhase]     # All 7 in order
WorkflowPhase.from_value(value: str) -> WorkflowPhase
```

#### WorkflowResult

```python
@dataclass
class WorkflowResult:
    workflow_id: str
    status: WorkflowStatus           # COMPLETED, FAILED, TIMED_OUT, etc.
    phase_results: list[PhaseResult]
    total_cost: float
    total_duration_seconds: float
    start_time: str                   # ISO-8601
    end_time: str
    resumed_from: str | None
    dry_run: bool
    metadata: dict
```

#### PhaseResult

```python
@dataclass
class PhaseResult:
    phase: WorkflowPhase
    status: PhaseStatus               # COMPLETED, FAILED, SKIPPED, DRY_RUN, etc.
    start_time: str
    end_time: str
    duration_seconds: float
    cost: float
    output: Any                       # Phase-specific payload
    error_message: str | None
    retry_count: int
    metadata: dict
```

### ContextSeedHandlers

```python
from startd8.contractors.context_seed_handlers import ContextSeedHandlers, HandlerConfig

handlers: dict[WorkflowPhase, AbstractPhaseHandler] = ContextSeedHandlers.create_all(
    enriched_seed_path: str,
    output_dir: str = None,
    *,
    lead_agent: str = None,
    drafter_agent: str = None,
    max_iterations: int = None,
    pass_threshold: int = None,
    max_tokens: int = None,
    fail_on_truncation: bool = None,
    check_truncation: bool = None,
    strict_truncation: bool = None,
    test_timeout_seconds: int = None,
    review_temperature: float = None,
    review_max_code_chars: int = None,
    development_timeout_seconds: float = None,
)
```

### Design Handoff

```python
from startd8.contractors.handoff import (
    write_design_handoff,
    load_design_handoff,
    HandoffData,
    DESIGN_HANDOFF_FILENAME,   # "design-handoff.json"
    SCHEMA_VERSION,            # 1
)

# Write handoff after design phase
path: Path = write_design_handoff(
    output_dir: str,
    enriched_seed_path: str,
    project_root: str,
    workflow_id: str,
    completed_phases: list[str] = None,
    design_results: dict = None,
    scaffold: dict = None,
)

# Load handoff (accepts file path or directory)
handoff: HandoffData = load_design_handoff(path: str | Path)
```

#### HandoffData

```python
@dataclass
class HandoffData:
    enriched_seed_path: str
    project_root: str
    output_dir: str
    workflow_id: str
    completed_phases: list[str]
    design_results: dict
    scaffold: dict
    created_at: str              # ISO-8601
    schema_version: int          # Currently 1
```

### Contractor Exceptions

```python
from startd8.contractors.artisan_contractor import (
    WorkflowError,              # Base (carries optional checkpoint)
    WorkflowTimeoutError,       # Total or phase timeout exceeded
    CostBudgetExceededError,    # Cumulative cost > budget
    PhaseExecutionError,        # Phase failed after retries
)
```

---

## Data Models

### Prompt

```python
from startd8 import Prompt

@dataclass
class Prompt:
    id: str
    content: str
    version: str
    tags: List[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
```

### AgentResponse

```python
from startd8 import AgentResponse

@dataclass
class AgentResponse:
    id: str
    prompt_id: str
    agent_name: str
    model: str
    response: str
    response_time_ms: int
    token_usage: TokenUsage
    metadata: Dict[str, Any]
    created_at: datetime
```

### TokenUsage

```python
from startd8 import TokenUsage

@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_estimate: Optional[float] = None
```

### Benchmark

```python
from startd8 import Benchmark

@dataclass
class Benchmark:
    id: str
    name: str
    prompt_id: str
    status: str  # "running", "completed", "failed"
    response_ids: List[str]
    metadata: Dict[str, Any]
    created_at: datetime
    completed_at: Optional[datetime]
```

---

## Job Queue

### JobQueue

```python
from startd8 import JobQueue, JobQueueConfig

config = JobQueueConfig(
    watch_folder: Path,
    poll_interval: int = 5,
    max_retries: int = 3
)

queue = JobQueue(config, framework)
```

#### Methods

##### get_pending_jobs

```python
jobs = queue.get_pending_jobs() -> List[JobFile]
```

##### process_next

```python
result = queue.process_next() -> Optional[JobResult]
```

##### process_all

```python
results = queue.process_all(
    on_progress: Optional[Callable] = None
) -> List[JobResult]
```

### JobFile

```python
from startd8 import JobFile

@dataclass
class JobFile:
    job_id: str
    file_path: Optional[Path]
    prompt: PromptSpec
    agents: List[str]
    priority: int = 0
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    response_ids: List[str]
    error: Optional[str]
    metadata: Dict[str, Any]
```

### JobStatus

```python
from startd8 import JobStatus

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

### Helper Functions

```python
from startd8 import create_job_file, load_queue_config, save_queue_config

# Create a job file
job = create_job_file(
    prompt_content: str,
    agents: List[str],
    output_path: Path,
    **kwargs
)

# Load/save queue config
config = load_queue_config(path: Path) -> JobQueueConfig
save_queue_config(config: JobQueueConfig, path: Path)
```

---

## Document Enhancement

### DocumentEnhancementChain

```python
from startd8 import DocumentEnhancementChain, DocumentEnhancementConfig

config = DocumentEnhancementConfig(
    agents=[...],
    error_handling=ErrorHandling.STOP_ON_ERROR
)

chain = DocumentEnhancementChain(config)
result = chain.process(document_path: Path) -> DocumentEnhancementResult
```

### DocumentEnhancementConfig

```python
from startd8 import DocumentEnhancementConfig, AgentConfig, ErrorHandling

config = DocumentEnhancementConfig(
    agents: List[AgentConfig],
    output_dir: Optional[Path] = None,
    error_handling: ErrorHandling = ErrorHandling.STOP_ON_ERROR,
    preserve_original: bool = True
)
```

### AgentConfig (Enhancement)

```python
from startd8 import AgentConfig

config = AgentConfig(
    name: str,
    agent_type: str,
    model: str,
    instructions: Optional[str] = None
)
```

### ErrorHandling

```python
from startd8 import ErrorHandling

class ErrorHandling(Enum):
    STOP_ON_ERROR = "stop_on_error"
    SKIP_AND_CONTINUE = "skip_and_continue"
    RETRY = "retry"
```

---

## Exceptions

```python
from startd8 import (
    Startd8Error,        # Base exception for all startd8 errors
    StorageError,        # Storage operation errors
    FileOperationError,  # File I/O errors
    ValidationError,     # Data validation errors
    APIError,            # API call errors
    ConfigurationError,  # Configuration errors
    AgentError,          # Agent operation errors
)
```

### Exception Hierarchy

```
Startd8Error
├── StorageError
│   └── FileOperationError
├── ValidationError
├── APIError
├── ConfigurationError
└── AgentError
```

---

## Utilities

### Logging

```python
from startd8 import get_logger, setup_logging

# Get a logger
logger = get_logger(__name__)

# Configure logging
setup_logging(
    level: str = "INFO",  # DEBUG, INFO, WARNING, ERROR
    format: str = "default"
)
```

### BenchmarkRunner

```python
from startd8 import BenchmarkRunner

runner = BenchmarkRunner(framework)

results = runner.run_benchmark(
    prompt_content: str,
    agents: List[BaseAgent],
    benchmark_name: str = None,
    metadata: Dict[str, Any] = None
) -> List[AgentResponse]
```

### ComparisonReport

```python
from startd8 import ComparisonReport

report = ComparisonReport(framework)

# Generate markdown report
markdown = report.generate_markdown_report(
    prompt_id: str,
    output_file: Optional[Path] = None
) -> str

# Generate metrics
metrics = report.generate_metrics(prompt_id: str) -> Dict[str, Any]
```

---

## Module Exports

All public APIs are exported from the main package:

```python
from startd8 import (
    # Core
    AgentFramework,
    
    # Models
    Prompt,
    AgentResponse,
    Benchmark,
    TokenUsage,
    
    # Agents
    BaseAgent,
    ClaudeAgent,
    GPT4Agent,
    GeminiAgent,
    ComposerAgent,
    MockAgent,
    
    # Orchestration
    Pipeline,
    WorkflowTemplates,
    PipelineComparison,
    
    # Document Enhancement
    DocumentEnhancementChain,
    DocumentEnhancementConfig,
    AgentConfig,
    EnhancementStepResult,
    DocumentEnhancementResult,
    ErrorHandling,
    
    # Job Queue
    JobQueue,
    JobQueueConfig,
    JobFile,
    JobStatus,
    JobResult,
    PromptSpec,
    AgentRegistry,
    create_job_file,
    load_queue_config,
    save_queue_config,
    
    # Benchmarking
    BenchmarkRunner,
    ComparisonReport,
    
    # Exceptions
    Startd8Error,
    StorageError,
    FileOperationError,
    ValidationError,
    APIError,
    ConfigurationError,
    AgentError,
    
    # Logging
    get_logger,
    setup_logging,
)
```


