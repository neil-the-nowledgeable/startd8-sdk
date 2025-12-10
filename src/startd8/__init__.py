"""
StartDate (startd8) SDK - Multi-LLM Agent Framework
====================================================

A Python SDK for managing multi-LLM development workflows, benchmarking,
and prompt version control in the StartDate project.

Example Usage:
    ```python
    from startd8 import AgentFramework, Prompt
    
    # Initialize framework
    framework = AgentFramework()
    
    # Create a versioned prompt
    prompt = framework.create_prompt(
        content="Implement user authentication",
        version="1.0.0",
        tags=["auth", "backend"]
    )
    
    # Send to multiple agents
    agents = ["claude", "gpt4", "gemini"]
    for agent in agents:
        response = framework.send_to_agent(prompt, agent)
        framework.record_response(response)
    
    # Compare responses
    comparison = framework.compare_responses(prompt.id)
    print(comparison.summary())
    ```
"""

from .framework import AgentFramework
from .models import (
    Prompt, 
    AgentResponse, 
    Benchmark, 
    TokenUsage,
    DocumentEnhancementConfig,
    AgentConfig,
    EnhancementStepResult,
    DocumentEnhancementResult,
    ErrorHandling,
    # Job Queue models
    JobStatus,
    JobFile,
    JobQueueConfig,
    JobResult,
    PromptSpec,
)
from .agents import ClaudeAgent, GPT4Agent, GeminiAgent, ComposerAgent, BaseAgent, MockAgent
from .benchmark import BenchmarkRunner, ComparisonReport
from .orchestration import Pipeline, WorkflowTemplates, PipelineComparison
from .document_enhancement import DocumentEnhancementChain
from .job_queue import (
    JobQueue,
    AgentRegistry,
    create_job_file,
    load_queue_config,
    save_queue_config,
)
from .exceptions import (
    Startd8Error,
    StorageError,
    FileOperationError,
    ValidationError,
    APIError,
    ConfigurationError,
    AgentError,
)
from .logging_config import get_logger, setup_logging, correlation_id
from .events import EventBus, Event, EventType, EventPriority
from .costs import (
    CostTracker,
    BudgetManager,
    PricingService,
    CostAnalytics,
    CostRecord,
    Budget,
    BudgetStatus,
    CostSummary,
    CostOptimization,
    CostPeriod,
    BudgetExceededError,
)

__version__ = "0.3.0"  # Bumped for cost tracking feature
__all__ = [
    "AgentFramework",
    "Prompt",
    "AgentResponse",
    "Benchmark",
    "TokenUsage",
    "ClaudeAgent",
    "GPT4Agent",
    "GeminiAgent",
    "ComposerAgent",
    "BaseAgent",
    "MockAgent",
    "BenchmarkRunner",
    "ComparisonReport",
    "Pipeline",
    "WorkflowTemplates",
    "PipelineComparison",
    # Document Enhancement
    "DocumentEnhancementChain",
    "DocumentEnhancementConfig",
    "AgentConfig",
    "EnhancementStepResult",
    "DocumentEnhancementResult",
    "ErrorHandling",
    # Job Queue
    "JobQueue",
    "JobQueueConfig",
    "JobFile",
    "JobStatus",
    "JobResult",
    "PromptSpec",
    "AgentRegistry",
    "create_job_file",
    "load_queue_config",
    "save_queue_config",
    # Exceptions
    "Startd8Error",
    "StorageError",
    "FileOperationError",
    "ValidationError",
    "APIError",
    "ConfigurationError",
    "AgentError",
    # Logging
    "get_logger",
    "setup_logging",
    "correlation_id",
    # Events
    "EventBus",
    "Event",
    "EventType",
    "EventPriority",
    # Cost Tracking
    "CostTracker",
    "BudgetManager",
    "PricingService",
    "CostAnalytics",
    "CostRecord",
    "Budget",
    "BudgetStatus",
    "CostSummary",
    "CostOptimization",
    "CostPeriod",
    "BudgetExceededError",
]

