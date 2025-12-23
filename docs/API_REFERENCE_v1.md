# Startd8 API Reference

**Version:** 0.4.0  
**Document Version:** v1  
**Last Updated:** 2025-01-13

## Table of Contents

1. [Core Classes](#core-classes)
2. [Agent Classes](#agent-classes)
3. [Orchestration](#orchestration)
4. [Data Models](#data-models)
5. [Storage](#storage)
6. [Job Queue](#job-queue)
7. [Document Enhancement](#document-enhancement)
8. [Exceptions](#exceptions)
9. [Utilities](#utilities)

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
    name: str = "anthropic:claude-3-opus-20240229",
    model: str = "claude-3-opus-20240229",
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
- `claude-3-5-sonnet-20241022`
- `claude-3-opus-20240229`
- `claude-3-haiku-20240307`

### GPT4Agent

```python
from startd8 import GPT4Agent

agent = GPT4Agent(
    name: str = "openai:gpt-4-turbo-preview",
    model: str = "gpt-4-turbo-preview",
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
- `gpt-4-turbo-preview`
- `gpt-4-turbo`
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


