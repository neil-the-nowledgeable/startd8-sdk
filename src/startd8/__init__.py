# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
#
# Licensed under the Equitable Use License, Version 1.0.
# You may obtain a copy of the License at: LICENSE.md
#
# This software is provided "AS IS" without warranties of any kind.
#
# IMPORTANT: Use by government agencies (federal, state, local), fossil fuel
# companies, military contractors, private prisons, investment banks, and
# organizations using forced ranking systems is subject to the Maximum Fee.
# See LICENSE.md for complete terms including worker protection provisions.

"""
StartDate (startd8) SDK - Multi-LLM Agent Framework
====================================================

A Python SDK for managing multi-LLM development workflows, benchmarking,
and prompt version control in the StartDate project.

Example Usage:
    ```python
    from startd8 import AgentFramework, Prompt
    from startd8.providers import ProviderRegistry
    
    # Initialize framework
    framework = AgentFramework()
    
    # Create a versioned prompt
    prompt = framework.create_prompt(
        content="Implement user authentication",
        version="1.0.0",
        tags=["auth", "backend"]
    )
    
    # Send to multiple agents (provider:model specs)
    ProviderRegistry.discover()
    agent_specs = [
        "anthropic:claude-sonnet-4-20250514",
        "openai:gpt-4o",
        "gemini:gemini-2.0-flash",
    ]
    for spec in agent_specs:
        provider_name, model = spec.split(":", 1)
        provider = ProviderRegistry.get_provider(provider_name)
        if not provider:
            raise RuntimeError(f"Unknown provider: {provider_name}")
        provider.validate_config({})
        agent = provider.create_agent(model)

        agent_response = agent.create_response(prompt.id, prompt.content)
        framework.record_response(
            prompt_id=prompt.id,
            agent_name=agent.name,
            model=agent.model,
            response=agent_response.response,
            response_time_ms=agent_response.response_time_ms,
            token_usage=agent_response.token_usage,
            metadata=agent_response.metadata,
            response_id=agent_response.id,
            timestamp=agent_response.timestamp,
        )
    
    # Compare responses
    comparison = framework.compare_responses(prompt.id)
    print(comparison.summary())
    ```
"""

from typing import Optional

from .framework import AgentFramework
from .models import (
    Prompt,
    AgentResponse,
    GenerateResult,
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
from .agents import (
    ClaudeAgent,
    GPT4Agent,
    GeminiAgent,
    ComposerAgent,
    BaseAgent,
    MockAgent,
    OpenAICompatibleAgent,
    TimeoutConfig,
    ClientPool,
    get_client_pool,
)
from .utils.retry import RetryConfig, RetryError
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
    GeminiSafetyFilterError,
)
from .logging_config import get_logger, setup_logging, correlation_id

# Eagerly initialize OTel log bridge so that modules using raw
# logging.getLogger(__name__) still propagate to Loki.
from .logging_config import _ensure_default_log_file_handler
_ensure_default_log_file_handler()
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
from .skills import (
    SkillAgent,
    SkillAgentConfig,
    CircuitState,
    SkillMetrics,
    create_game_enhancer_agent,
    create_html5_game_designer_agent,
    create_code_reviewer_agent,
)
from .session_tracking import (
    SessionTracker,
    SessionMetrics,
    SessionState,
    ContextUsage,
    get_session_tracker,
)
from .exceptions import TruncationError, TruncationWarning

# OpenTelemetry with ContextCore support
from .otel import (
    OTEL_AVAILABLE,
    CONTEXTCORE_PROJECT_ID,
    CONTEXTCORE_PROJECT_NAME,
    CONTEXTCORE_TASK_ID,
    CONTEXTCORE_SPRINT_ID,
    CONTEXTCORE_BUSINESS_CRITICALITY,
    ProjectContext as OTelProjectContext,
    OTelConfig,
    create_resource as create_otel_resource,
    configure_tracing,
    configure_metrics,
    configure_otel,
    shutdown_otel,
    add_project_context_to_span,
)

def _read_version_from_pyproject() -> Optional[str]:
    """Best-effort read of [project].version from a nearby pyproject.toml."""
    from pathlib import Path
    import re

    start = Path(__file__).resolve().parent
    pyproject: Optional[Path] = None

    # Limit how far we walk up to avoid scanning the whole filesystem.
    for parent in [start] + list(start.parents)[:6]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            pyproject = candidate
            break

    if pyproject is None:
        return None

    try:
        text = pyproject.read_text(encoding="utf-8")
    except Exception:
        return None

    # Prefer tomllib when available (Python 3.11+), otherwise fall back to regex.
    try:
        import tomllib  # type: ignore[attr-defined]

        data = tomllib.loads(text)
        version = data.get("project", {}).get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    except Exception:
        pass

    # Minimal regex fallback for Python 3.9/3.10 without extra deps.
    m = re.search(r"^\[project\]\s*$([\s\S]*?)(?=^\[|\Z)", text, flags=re.MULTILINE)
    if not m:
        return None
    project_section = m.group(1)
    m2 = re.search(r"^\s*version\s*=\s*[\"']([^\"']+)[\"']\s*$", project_section, flags=re.MULTILINE)
    if not m2:
        return None
    return m2.group(1).strip() or None


def _read_version_from_metadata() -> Optional[str]:
    """Read installed distribution version (best-effort)."""
    try:
        from importlib.metadata import PackageNotFoundError, version as _pkg_version
    except Exception:  # pragma: no cover
        return None

    try:
        return _pkg_version("startd8")
    except PackageNotFoundError:
        return None


# Decision 29B: in a source checkout, prefer pyproject.toml version; fall back to
# installed distribution metadata; then to a safe placeholder.
__version__ = _read_version_from_pyproject() or _read_version_from_metadata() or "0.0.0"

__all__ = [
    "AgentFramework",
    "Prompt",
    "AgentResponse",
    "GenerateResult",
    "Benchmark",
    "TokenUsage",
    "ClaudeAgent",
    "GPT4Agent",
    "GeminiAgent",
    "ComposerAgent",
    "BaseAgent",
    "MockAgent",
    "OpenAICompatibleAgent",
    "TimeoutConfig",
    "ClientPool",
    "get_client_pool",
    "RetryConfig",
    "RetryError",
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
    # Skills (MCP Integration)
    "SkillAgent",
    "SkillAgentConfig",
    "CircuitState",
    "SkillMetrics",
    "create_game_enhancer_agent",
    "create_html5_game_designer_agent",
    "create_code_reviewer_agent",
    # OpenTelemetry with ContextCore
    "OTEL_AVAILABLE",
    "CONTEXTCORE_PROJECT_ID",
    "CONTEXTCORE_PROJECT_NAME",
    "CONTEXTCORE_TASK_ID",
    "CONTEXTCORE_SPRINT_ID",
    "CONTEXTCORE_BUSINESS_CRITICALITY",
    "OTelProjectContext",
    "OTelConfig",
    "create_otel_resource",
    "configure_tracing",
    "configure_metrics",
    "configure_otel",
    "shutdown_otel",
    "add_project_context_to_span",
]

