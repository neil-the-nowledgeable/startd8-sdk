from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    Any, Callable, Dict, Iterator, List, Literal, Optional,
    Protocol, runtime_checkable,
)

from pydantic import BaseModel, Field, model_validator

class MergeStatus(Enum):
    """Status of a merge operation."""
    SUCCESS = 'success'
    CONFLICT = 'conflict'
    SKIPPED = 'skipped'
    ERROR = 'error'

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
    model: str = ''
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def quality_score(self) -> Optional[int]:
        """Quality score from the generation pipeline (0-100), or None if not scored.

        Generators that include an LLM review loop (e.g. PrimaryContractorCodeGenerator)
        populate ``metadata["quality_score"]``.  Generators without review (e.g.
        MicroPrimeCodeGenerator for TRIVIAL/SIMPLE tiers) may omit it.
        """
        val = self.metadata.get("quality_score")
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                return None
        return None

@dataclass
class SizeEstimate:
    """Estimated size of generated output."""
    lines: int
    tokens: int
    complexity: str
    confidence: float
    reasoning: str = ''

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

    def generate(self, task: str, context: Dict[str, Any], target_files: List[str]) -> GenerationResult:
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

    def emit_span(self, name: str, attributes: Dict[str, Any]) -> SpanContext:
        """
        Start a new span for tracking an operation.

        Args:
            name: Span name (e.g., "prime_contractor.process_feature")
            attributes: Key-value attributes for the span

        Returns:
            SpanContext with trace/span IDs
        """
        ...

    def emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Emit a point-in-time event.

        Args:
            event_type: Type of event (e.g., "integration_started")
            data: Event data
        """
        ...

    def emit_metric(self, name: str, value: float, labels: Dict[str, str]) -> None:
        """
        Record a metric value.

        Args:
            name: Metric name (e.g., "prime_contractor.cost.usd")
            value: Metric value
            labels: Label key-value pairs
        """
        ...

    def emit_insight(self, insight_type: str, summary: str, confidence: float=1.0, **context: Any) -> None:
        """
        Emit an agent insight for tracking decisions.

        Args:
            insight_type: Type (e.g., "workflow_started", "feature_selected")
            summary: Human-readable summary
            confidence: Confidence level (0.0-1.0)
            **context: Additional context
        """
        ...

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

    def estimate(self, task: str, inputs: Dict[str, Any]) -> SizeEstimate:
        """
        Estimate the size of generated output.

        Args:
            task: Task description
            inputs: Additional inputs (target_files, required_exports, etc.)

        Returns:
            SizeEstimate with predicted lines, tokens, and complexity
        """
        ...

@runtime_checkable
class MergeStrategy(Protocol):
    """
    Protocol for merging generated code with existing files.

    Implementations handle different merge strategies:
    - SimpleMergeStrategy: Overwrites target (default)
    - ASTMergeStrategy: Python AST-aware merge
    - PatchMergeStrategy: Git-style patch application
    """

    def can_merge(self, source: Path, target: Path) -> bool:
        """
        Check if this strategy can handle the given files.

        Args:
            source: Path to generated file
            target: Path to target file

        Returns:
            True if this strategy can merge these files
        """
        ...

    def merge(self, source: Path, target: Path, backup: bool=True) -> MergeResult:
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

@runtime_checkable
class IntegrationUnit(Protocol):
    """Protocol for a unit of work to be integrated.

    Implementations wrap whatever task representation the caller uses
    (FeatureSpec, SeedTask, etc.) and expose a uniform surface for
    IntegrationEngine.
    """

    @property
    def id(self) -> str:
        """Unique identifier for this unit."""
        ...

    @property
    def name(self) -> str:
        """Human-readable name for logging."""
        ...

    @property
    def generated_files(self) -> List[str]:
        """Paths to generated source files (may be in a staging dir)."""
        ...

    @property
    def target_files(self) -> List[str]:
        """Paths where files should land in project_root."""
        ...

    @property
    def context(self) -> Dict[str, Any]:
        """Arbitrary metadata forwarded to listeners and diagnostics."""
        ...


@runtime_checkable
class IntegrationListener(Protocol):
    """Observer protocol for IntegrationEngine lifecycle events."""

    def on_integration_started(self, unit: IntegrationUnit) -> None: ...
    def on_file_integrated(self, unit: IntegrationUnit, source: Path, target: Path) -> None: ...
    def on_checkpoint_result(self, unit: IntegrationUnit, result: Any) -> None: ...
    def on_integration_failed(self, unit: IntegrationUnit, error: str) -> None: ...
    def on_integration_completed(self, unit: IntegrationUnit, files: List[Path]) -> None: ...


class IntegrationStatus(Enum):
    """Status of an integration operation."""
    SUCCESS = "success"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


# Distinct exit code for size regression blocks (PCA-604).
EXIT_SIZE_REGRESSION = 78


@dataclass
class IntegrationResult:
    """Outcome of an IntegrationEngine.integrate() call."""

    success: bool
    integrated_files: List[Path] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    rollback_performed: bool = False
    checkpoint_results: List[Any] = field(default_factory=list)
    skipped_files: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: IntegrationStatus = IntegrationStatus.SUCCESS


class ModelRole(str, Enum):
    """Role a model plays in the contractor pipeline.

    Tier mapping (numerical aliases for the 3-tier Artisan architecture):

    | Tier | Alias       | Role     | Purpose                                |
    |------|-------------|----------|----------------------------------------|
    | T1   | Economy     | DRAFT    | Fast draft generation, cheap retries   |
    | T2   | Standard    | VALIDATE | Refinement, validation, quality gating |
    | T3   | Premium     | REVIEW   | Final review, arbitration, design      |

    See ``T1_ECONOMY``, ``T2_STANDARD``, ``T3_PREMIUM`` module-level aliases.
    """
    DRAFT = 'draft'
    VALIDATE = 'validate'
    REVIEW = 'review'
    REFINE = 'refine'

class LessonCategory(str, Enum):
    """Category classification for lessons."""
    BUG_FIX = 'bug_fix'
    PERFORMANCE = 'performance'
    SECURITY = 'security'
    ARCHITECTURE = 'architecture'
    BEST_PRACTICE = 'best_practice'
    ANTI_PATTERN = 'anti_pattern'
    GENERAL = 'general'

class LessonSeverity(str, Enum):
    """Severity level of a lesson."""
    INFO = 'info'
    WARNING = 'warning'
    CRITICAL = 'critical'

class SortOrder(str, Enum):
    """Sort order for query results."""
    RELEVANCE = 'relevance'
    RECENCY = 'recency'
    SEVERITY = 'severity'

@dataclass
class LessonQuery:
    """Query object for searching lessons.

    Attributes:
        query_text: The search text (required, non-empty).
        categories: Optional list of categories to filter by.
        severity: Optional minimum severity filter.
        tags: Optional list of tags to filter by.
        max_results: Maximum number of results (1-100, default 10).
        sort_by: Sort order for results (default RELEVANCE).
        context: Optional arbitrary context dict for provider use.
    """
    query_text: str
    categories: Optional[List[LessonCategory]] = None
    severity: Optional[LessonSeverity] = None
    tags: Optional[List[str]] = None
    max_results: int = 10
    sort_by: SortOrder = SortOrder.RELEVANCE
    context: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Validate query parameters."""
        if not isinstance(self.query_text, str) or not self.query_text.strip():
            raise ValueError('query_text must be a non-empty string')
        self.query_text = self.query_text.strip()
        if self.max_results < 1:
            raise ValueError('max_results must be >= 1')
        if self.max_results > 100:
            raise ValueError('max_results must be <= 100')

@dataclass
class Lesson:
    """A single lesson entry.

    Attributes:
        lesson_id: Unique identifier for this lesson.
        title: Human-readable title.
        content: Full lesson content/body text.
        category: The lesson's category classification.
        severity: The lesson's severity level.
        tags: List of string tags for this lesson.
        source: Optional source attribution string.
        created_at: Optional ISO 8601 timestamp string.
        metadata: Optional additional metadata dict.
    """
    lesson_id: str
    title: str
    content: str
    category: LessonCategory
    severity: LessonSeverity
    tags: List[str] = field(default_factory=list)
    source: str = ''
    created_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class LessonResult:
    """Result object returned from a lessons query.

    Attributes:
        query: The original query that produced this result.
        lessons: List of matched Lesson objects.
        total_count: Total number of matches (may exceed len(lessons) if paginated).
        has_more: Whether more results are available beyond this page.
        search_metadata: Optional metadata about the search execution.
    """
    query: LessonQuery
    lessons: List[Lesson] = field(default_factory=list)
    total_count: int = 0
    has_more: bool = False
    search_metadata: Optional[Dict[str, Any]] = None

    @property
    def is_empty(self) -> bool:
        """Returns True if no lessons were found."""
        return len(self.lessons) == 0

    def __len__(self) -> int:
        """Return the number of lessons in this result."""
        return len(self.lessons)

    def __iter__(self) -> Iterator[Lesson]:
        """Iterate over lessons in this result."""
        return iter(self.lessons)

@dataclass
class ModelCatalogEntry:
    """An entry in the model catalog describing an available AI model.

    Attributes:
        model_id: Unique model identifier (e.g. 'claude-sonnet-4-6').
        model_name: Human-readable model name.
        role: The role this model serves (draft, validate, etc.).
        provider: The model provider name (e.g. 'anthropic', 'openai').
        description: Optional description of the model's strengths.
        max_tokens: Maximum output tokens (default 4096).
        supports_streaming: Whether the model supports streaming responses.
        config: Optional default configuration dict (e.g. temperature).
        version: Model version string.
    """
    model_id: str
    model_name: str
    role: ModelRole
    provider: str
    description: str = ''
    max_tokens: int = 4096
    supports_streaming: bool = False
    config: Optional[Dict[str, Any]] = None
    version: str = '1.0'

    @property
    def agent_spec(self) -> str:
        """Return the ``"provider:model_id"`` string used by ``resolve_agent_spec()``."""
        return f"{self.provider}:{self.model_id}"

    def __post_init__(self) -> None:
        """Validate model catalog entry parameters."""
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError('model_id must be a non-empty string')
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError('model_name must be a non-empty string')
        if self.max_tokens < 1:
            raise ValueError('max_tokens must be >= 1')

@dataclass
class ValidationDiagnostic(BaseModel):
    """Single diagnostic entry from validation.
    
    Attributes:
        code: Machine-readable diagnostic code, e.g. 'MISSING_KEY'.
        message: Human-readable description.
        severity: Severity level ('error', 'warning', or 'info').
        context_key: The context key this diagnostic relates to, if applicable.
    """
    code: str = Field(description="Machine-readable diagnostic code, e.g. 'MISSING_KEY'.")
    message: str = Field(description="Human-readable description.")
    severity: Literal["error", "warning", "info"] = "info"
    context_key: Optional[str] = Field(
        default=None,
        description="The context key this diagnostic relates to, if applicable.",
    )


@dataclass
class ValidationConfig(BaseModel):
    """Configuration for post-generation validation hookpoint.
    
    Attributes:
        mode: Execution mode ('standalone' or 'pipeline').
        fail_on_warning: Whether warnings should cause validation failure.
            Default False preserves standalone behavior.
        required_context_keys: Context keys that must be present in resolved output.
            Empty list (standalone default) means no mandatory keys.
        custom_validators: Named validator hooks to run during validation.
            Hook names are resolved by the concrete strategy implementation.
    """
    mode: Literal["standalone", "pipeline"] = "standalone"
    fail_on_warning: bool = Field(
        default=False,
        description="Whether warnings should cause validation failure. "
        "Default False preserves standalone behavior. "
        "Pipeline mode typically sets this to True.",
    )
    required_context_keys: List[str] = Field(
        default_factory=list,
        description="Context keys that must be present in resolved output. "
        "Empty list (standalone default) means no mandatory keys.",
    )
    custom_validators: List[str] = Field(
        default_factory=list,
        description="Named validator hooks to run during validation. "
        "Hook names are resolved by the concrete strategy implementation. "
        "Unrecognized names should produce a diagnostic with code 'UNKNOWN_VALIDATOR'.",
    )


@dataclass
class ValidationResult(BaseModel):
    """Structured result from post-generation validation.

    The model_validator enforces that is_valid cannot be True when errors
    are present. When fail_on_warning metadata is set and warnings are
    present, is_valid is also forced to False.
    
    Attributes:
        is_valid: Overall pass/fail status of validation.
        mode: Execution mode that produced this result.
        errors: List of error diagnostics.
        warnings: List of warning diagnostics.
        info: List of informational diagnostics.
        metadata: Arbitrary provenance/diagnostic metadata.
    """
    is_valid: bool = Field(
        description="Overall pass/fail status of validation."
    )
    mode: Literal["standalone", "pipeline"]
    errors: List[ValidationDiagnostic] = Field(default_factory=list)
    warnings: List[ValidationDiagnostic] = Field(default_factory=list)
    info: List[ValidationDiagnostic] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary provenance/diagnostic metadata. "
        "May include 'fail_on_warning': bool to control warning-as-failure semantics.",
    )

    @model_validator(mode="after")
    def _enforce_is_valid_invariant(self) -> "ValidationResult":
        """Structurally enforce is_valid consistency.

        - If errors is non-empty, is_valid is forced to False.
        - If metadata['fail_on_warning'] is True and warnings is non-empty,
          is_valid is forced to False.

        This prevents implementors from accidentally constructing a
        ValidationResult(is_valid=True, errors=[...]).
        """
        if self.errors:
            self.is_valid = False
        if self.metadata.get("fail_on_warning", False) and self.warnings:
            self.is_valid = False
        return self


@runtime_checkable
class ContextResolutionStrategy(Protocol):
    """Strategy protocol for context resolution in standalone/pipeline modes.

    Implementations provide mode-specific resolution logic, generation
    provenance, and post-generation validation. The protocol uses structural
    subtyping — concrete classes need not inherit from this type.

    Note on @runtime_checkable: isinstance() checks verify structural
    presence of methods and properties only — they do NOT verify parameter
    signatures, return types, or behavioral contracts. Pair isinstance()
    guards with integration tests for full contract verification.
    Requires CPython >= 3.12 for correct @property member detection.
    """

    @property
    def mode(self) -> Literal["standalone", "pipeline"]:
        """The execution mode this strategy implements."""
        ...

    @property
    def provenance(self) -> Dict[str, Any]:
        """Generation provenance metadata for audit/tracing."""
        ...

    def resolve(self, context_seed: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve a context seed into a fully-populated context dict.

        Args:
            context_seed: Raw context data (may be minimal in standalone,
                rich with onboarding/architectural/calibration data in pipeline).

        Returns:
            Resolved context dictionary ready for consumption by the workflow.

        Note on mandatory key validation: resolve() performs best-effort
        resolution and SHOULD NOT duplicate the mandatory-key checking that
        validate() performs via ValidationConfig.required_context_keys.
        In pipeline mode, resolve() may raise KeyError only for keys that
        are structurally required to *perform* resolution (e.g., a data
        source URI), not for keys that are required in the *output*.
        Output completeness is the responsibility of validate().
        """
        ...

    def validate(
        self, result: Dict[str, Any], config: ValidationConfig
    ) -> ValidationResult:
        """Post-generation validation hookpoint.

        Args:
            result: The generated/resolved output to validate.
            config: Validation configuration controlling strictness and rules.

        Returns:
            Structured validation result with diagnostics. Implementors
            SHOULD set metadata["fail_on_warning"] = config.fail_on_warning
            to enable the ValidationResult model_validator enforcement.
        """
        ...


@runtime_checkable
class LessonsProvider(Protocol):
    """Protocol defining the interface for lessons providers.

    Any class that implements query_lessons, get_lesson_by_id, and
    list_categories with the correct signatures satisfies this protocol.
    Explicit inheritance is NOT required (structural subtyping).

    This uses @runtime_checkable so isinstance() checks work at runtime.
    """

    def query_lessons(self, query: LessonQuery) -> LessonResult:
        """Search for lessons matching the given query.

        Args:
            query: A LessonQuery specifying search parameters.

        Returns:
            A LessonResult containing matched lessons.
        """
        ...

    def get_lesson_by_id(self, lesson_id: str) -> Optional[Lesson]:
        """Retrieve a specific lesson by its unique ID.

        Args:
            lesson_id: The unique identifier of the lesson.

        Returns:
            The Lesson if found, None otherwise.
        """
        ...

    def list_categories(self) -> List[LessonCategory]:
        """Return all available lesson categories.

        Returns:
            A list of LessonCategory enum values.
        """
        ...

def get_models_by_role(role: ModelRole) -> List[ModelCatalogEntry]:
    """Return all catalog entries matching the given role.

    Args:
        role: The ModelRole to filter by.

    Returns:
        List of matching ModelCatalogEntry objects.
    """
    return [entry for entry in MODEL_CATALOG.values() if entry.role == role]

def get_draft_models() -> List[ModelCatalogEntry]:
    """Return all draft model catalog entries.

    Returns:
        List of ModelCatalogEntry objects with role=DRAFT.
    """
    return get_models_by_role(ModelRole.DRAFT)

def get_validate_models() -> List[ModelCatalogEntry]:
    """Return all validate model catalog entries.

    Returns:
        List of ModelCatalogEntry objects with role=VALIDATE.
    """
    return get_models_by_role(ModelRole.VALIDATE)

def get_review_models() -> List[ModelCatalogEntry]:
    """Return all review model catalog entries.

    Returns:
        List of ModelCatalogEntry objects with role=REVIEW.
    """
    return get_models_by_role(ModelRole.REVIEW)

def get_model_by_id(model_id: str) -> Optional[ModelCatalogEntry]:
    """Look up a model catalog entry by its model_id.

    Args:
        model_id: The unique model identifier string.

    Returns:
        The ModelCatalogEntry if found, None otherwise.
    """
    return MODEL_CATALOG.get(model_id)


ProgressCallback = Callable[[int, int, str], None]
FeatureCompleteCallback = Callable[[Any], None]
CheckpointFailedCallback = Callable[[Any, List[Any]], None]

DRAFT_MODEL_CLAUDE_HAIKU = ModelCatalogEntry(
    model_id='claude-haiku-4-5-20251001',
    model_name='Claude Haiku 4.5',
    role=ModelRole.DRAFT,
    provider='anthropic',
    description='Fast, low-cost model for drafting. Cheap retries, expensive validation.',
    max_tokens=8192,
    supports_streaming=True,
    config={'temperature': 0.7},
    version='4.5',
)
VALIDATE_MODEL_CLAUDE_SONNET = ModelCatalogEntry(
    model_id='claude-sonnet-4-6',
    model_name='Claude Sonnet 4.6',
    role=ModelRole.VALIDATE,
    provider='anthropic',
    description='Balanced model for validation and quality gating.',
    max_tokens=8192,
    supports_streaming=True,
    config={'temperature': 0.0},
    version='4.6',
)
REVIEW_MODEL_CLAUDE_OPUS = ModelCatalogEntry(
    model_id='claude-opus-4-6',
    model_name='Claude Opus 4.6',
    role=ModelRole.REVIEW,
    provider='anthropic',
    description='Flagship model for independent design review and arbitration.',
    max_tokens=8192,
    supports_streaming=True,
    config={'temperature': 0.0},
    version='4.6',
)
MODEL_CATALOG: Dict[str, ModelCatalogEntry] = {
    entry.model_id: entry
    for entry in [
        DRAFT_MODEL_CLAUDE_HAIKU,
        VALIDATE_MODEL_CLAUDE_SONNET,
        REVIEW_MODEL_CLAUDE_OPUS,
    ]
}

# ── Tier aliases (3-tier Artisan architecture) ──────────────────────
T1_ECONOMY = DRAFT_MODEL_CLAUDE_HAIKU
T2_STANDARD = VALIDATE_MODEL_CLAUDE_SONNET
T3_PREMIUM = REVIEW_MODEL_CLAUDE_OPUS

__all__ = [
    'ModelRole', 'LessonCategory', 'LessonSeverity', 'SortOrder',
    'LessonQuery', 'Lesson', 'LessonResult', 'ModelCatalogEntry',
    'LessonsProvider',
    'IntegrationUnit', 'IntegrationListener', 'IntegrationResult',
    'IntegrationStatus', 'EXIT_SIZE_REGRESSION',
    'DRAFT_MODEL_CLAUDE_HAIKU', 'VALIDATE_MODEL_CLAUDE_SONNET',
    'REVIEW_MODEL_CLAUDE_OPUS',
    'T1_ECONOMY', 'T2_STANDARD', 'T3_PREMIUM',
    'MODEL_CATALOG',
    'get_models_by_role', 'get_draft_models', 'get_validate_models',
    'get_review_models', 'get_model_by_id',
    'ValidationDiagnostic', 'ValidationConfig', 'ValidationResult',
    'ContextResolutionStrategy',
]