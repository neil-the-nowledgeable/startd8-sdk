"""
Protocol definitions for Prime Contractor workflow.

These protocols define the abstract interfaces for the Prime Contractor
components, enabling dependency injection and optional ContextCore integration.

The protocols are designed to allow:
1. Standalone operation (using logging-based instrumentation)
2. Full observability integration (when ContextCore is available)
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    Union,
    runtime_checkable,
)


# ============================================================================
# Data Classes
# ============================================================================


class MergeStatus(Enum):
    """Status of a merge operation."""
    SUCCESS = "success"
    CONFLICT = "conflict"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class GenerationResult:
    """Result from a code generation operation."""
    success: bool
    generated_files: List[Path] = field(default_factory=list)
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    iterations: int = 1
    model: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SizeEstimate:
    """Estimated size of generated output."""
    lines: int
    tokens: int
    complexity: str  # "low", "medium", "high"
    confidence: float  # 0.0 to 1.0
    reasoning: str = ""


@dataclass
class MergeResult:
    """Result from a merge operation."""
    status: MergeStatus
    merged_content: Optional[str] = None
    error: Optional[str] = None
    conflicts: List[str] = field(default_factory=list)
    backup_path: Optional[Path] = None


@dataclass
class SpanContext:
    """Minimal span context for instrumentation."""
    trace_id: str
    span_id: str
    attributes: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Protocol 1: CodeGenerator
# ============================================================================


@runtime_checkable
class CodeGenerator(Protocol):
    """
    Protocol for code generation backends.

    Implementations handle the actual LLM-based code generation,
    using whatever workflow or model combination they prefer.

    Example implementations:
    - LeadContractorCodeGenerator: Uses lead/drafter pattern
    - SingleModelCodeGenerator: Uses one model directly
    """

    def generate(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """
        Generate code for the given task.

        Args:
            task: Description of what to implement
            context: Additional context (existing code, requirements, etc.)
            target_files: Expected output file paths

        Returns:
            GenerationResult with success status and generated file paths
        """
        ...


# ============================================================================
# Protocol 2: Instrumentor
# ============================================================================


@runtime_checkable
class Instrumentor(Protocol):
    """
    Protocol for observability instrumentation.

    Implementations can emit telemetry to different backends:
    - LoggingInstrumentor: Python logging (standalone)
    - ContextCoreInstrumentor: OTel spans via ContextCore

    The Prime Contractor uses this to track:
    - Feature processing spans
    - Integration events
    - Cost metrics
    - Insights/decisions
    """

    def emit_span(
        self,
        name: str,
        attributes: Dict[str, Any],
    ) -> SpanContext:
        """
        Start a new span for tracking an operation.

        Args:
            name: Span name (e.g., "prime_contractor.process_feature")
            attributes: Key-value attributes for the span

        Returns:
            SpanContext with trace/span IDs
        """
        ...

    def emit_event(
        self,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Emit a point-in-time event.

        Args:
            event_type: Type of event (e.g., "integration_started")
            data: Event data
        """
        ...

    def emit_metric(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
    ) -> None:
        """
        Record a metric value.

        Args:
            name: Metric name (e.g., "prime_contractor.cost.usd")
            value: Metric value
            labels: Label key-value pairs
        """
        ...

    def emit_insight(
        self,
        insight_type: str,
        summary: str,
        confidence: float = 1.0,
        **context: Any,
    ) -> None:
        """
        Emit an agent insight for tracking decisions.

        Args:
            insight_type: Type (e.g., "workflow_started", "feature_selected")
            summary: Human-readable summary
            confidence: Confidence level (0.0-1.0)
            **context: Additional context
        """
        ...


# ============================================================================
# Protocol 3: SizeEstimator
# ============================================================================


@runtime_checkable
class SizeEstimator(Protocol):
    """
    Protocol for estimating output size before generation.

    This enables proactive truncation prevention by estimating
    whether generated output will exceed safe limits.

    Implementations:
    - HeuristicSizeEstimator: Rule-based estimation
    - LLMSizeEstimator: Uses LLM to estimate (higher accuracy)
    """

    def estimate(
        self,
        task: str,
        inputs: Dict[str, Any],
    ) -> SizeEstimate:
        """
        Estimate the size of generated output.

        Args:
            task: Task description
            inputs: Additional inputs (target_files, required_exports, etc.)

        Returns:
            SizeEstimate with predicted lines, tokens, and complexity
        """
        ...


# ============================================================================
# Protocol 4: MergeStrategy
# ============================================================================


@runtime_checkable
class MergeStrategy(Protocol):
    """
    Protocol for merging generated code with existing files.

    Implementations handle different merge strategies:
    - SimpleMergeStrategy: Overwrites target (default)
    - ASTMergeStrategy: Python AST-aware merge
    - PatchMergeStrategy: Git-style patch application
    """

    def can_merge(
        self,
        source: Path,
        target: Path,
    ) -> bool:
        """
        Check if this strategy can handle the given files.

        Args:
            source: Path to generated file
            target: Path to target file

        Returns:
            True if this strategy can merge these files
        """
        ...

    def merge(
        self,
        source: Path,
        target: Path,
        backup: bool = True,
    ) -> MergeResult:
        """
        Merge source into target.

        Args:
            source: Path to generated file
            target: Path to target file (may not exist)
            backup: Whether to create a .backup file

        Returns:
            MergeResult with status and merged content
        """
        ...


# ============================================================================
# Type Aliases
# ============================================================================


# Callback for progress updates: (current_step, total_steps, message) -> None
ProgressCallback = Callable[[int, int, str], None]

# Callback for feature completion: (feature_spec) -> None
FeatureCompleteCallback = Callable[[Any], None]

# Callback for checkpoint failure: (feature_spec, results) -> None
CheckpointFailedCallback = Callable[[Any, List[Any]], None]
