"""
Custom exception classes for startd8 SDK

Provides specific exception types for better error handling and debugging.
"""


class Startd8Error(Exception):
    """Base exception for all startd8 errors"""
    pass


class StorageError(Startd8Error):
    """Base exception for storage-related errors"""
    
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message)
        self.original_error = original_error


class FileOperationError(StorageError):
    """Error during file operations"""
    
    def __init__(self, message: str, file_path: str = None, original_error: Exception = None):
        super().__init__(message)
        self.file_path = file_path
        self.original_error = original_error


class ValidationError(Startd8Error):
    """Error during data validation"""
    
    def __init__(self, message: str, field: str = None, value=None):
        super().__init__(message)
        self.field = field
        self.value = value


class APIError(Startd8Error):
    """Error during API calls to LLM providers"""
    
    def __init__(
        self,
        message: str,
        provider: str = None,
        status_code: int = None,
        retry_after: int = None,
        original_error: Exception = None
    ):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retry_after = retry_after
        self.original_error = original_error


class ConfigurationError(Startd8Error):
    """Error in configuration"""
    pass


class AgentError(Startd8Error):
    """Error in agent operations"""

    def __init__(self, message: str, agent_name: str = None, original_error: Exception = None):
        super().__init__(message)
        self.agent_name = agent_name
        self.original_error = original_error


class GeminiSafetyFilterError(APIError):
    """Gemini refused to generate due to content safety filter.

    Raised when finish_reason is SAFETY, indicating the prompt or expected
    response tripped Gemini's content classifier.  This is distinct from
    rate-limit or server errors and may be recoverable by reducing context
    or adjusting safety_settings.

    Attributes:
        prompt_tokens: Approximate input token count of the blocked prompt.
        safety_ratings: Raw safety ratings from the Gemini response, if available.
    """

    def __init__(
        self,
        message: str,
        provider: str = "gemini",
        prompt_tokens: int = None,
        safety_ratings: list = None,
        original_error: Exception = None,
    ):
        super().__init__(
            message,
            provider=provider,
            original_error=original_error,
        )
        self.prompt_tokens = prompt_tokens
        self.safety_ratings = safety_ratings or []


class SizeRegressionError(Startd8Error):
    """Edit-first size regression gate failure (REQ-EFE-020).

    Raised when generated output is smaller than the threshold percentage
    of the original file size, indicating a destructive rewrite instead
    of an incremental edit.
    """

    def __init__(
        self,
        message: str,
        task_id: str = None,
        file_path: str = None,
        ratio: float = None,
        threshold: float = None,
    ):
        super().__init__(message)
        self.task_id = task_id
        self.file_path = file_path
        self.ratio = ratio
        self.threshold = threshold


class TruncationError(Startd8Error):
    """
    Exception raised when a response is detected as truncated.

    This is raised when truncation is severe enough to warrant stopping execution,
    such as when document enhancement produces incomplete output.

    Attributes:
        step_name: Name of the processing step where truncation occurred
        input_length: Length of the input document (characters)
        output_length: Length of the output document (characters)
        truncation_indicators: List of indicators that triggered truncation detection
        original_input: The original input text (optional, for debugging)
    """

    def __init__(
        self,
        message: str,
        step_name: str = None,
        input_length: int = None,
        output_length: int = None,
        truncation_indicators: list = None,
        original_input: str = None
    ):
        super().__init__(message)
        self.step_name = step_name
        self.input_length = input_length
        self.output_length = output_length
        self.truncation_indicators = truncation_indicators or []
        self.original_input = original_input


class MissingTemplateError(Startd8Error):
    """Structured refusal for an empty-fillable spec — RUN-007 FR-2.

    Raised when a feature has zero fillable elements (FR-0) and no
    ``FRAMEWORK_CONFIG_DEFAULTS`` match, and file-whole escalation either could
    not run (budget exhausted / provider unavailable — FR-4) or still produced
    an empty/stub artifact. The feature is refused as a real failure rather than
    shipping an unfilled basename-class skeleton.

    Carries attribution so the post-mortem is not blind to refusals (FR-2.2):
    ``root_cause`` / ``pipeline_stage`` default to the empty-spec refusal
    classification.
    """

    def __init__(
        self,
        message: str,
        *,
        file_path: str = None,
        feature_id: str = None,
        reason: str = "empty_spec",
        root_cause: str = "empty_spec_refusal",
        pipeline_stage: str = "micro_prime_escalation",
    ):
        super().__init__(message)
        self.file_path = file_path
        self.feature_id = feature_id
        self.reason = reason
        self.root_cause = root_cause
        self.pipeline_stage = pipeline_stage

    def __str__(self):
        parts = [super().__str__()]
        if self.step_name:
            parts.append(f"Step: {self.step_name}")
        if self.input_length is not None:
            parts.append(f"Input length: {self.input_length}")
        if self.output_length is not None:
            parts.append(f"Output length: {self.output_length}")
        if self.truncation_indicators:
            parts.append(f"Indicators: {', '.join(self.truncation_indicators)}")
        return " | ".join(parts)


class MissingUpstreamArtifact(Startd8Error):
    """A feature's declared upstream producer output is absent — RUN-008 FR-2.

    Raised when feature F2 depends on F1 (or imports from a path F1 produces)
    but F1's generated artifact is not on disk at F2's design time. F2 MUST halt
    loudly rather than fall back to summaries or invent the cross-file contract
    (the run-008 failure mode). Carries attribution so the post-mortem is not
    blind to the blocked dependency.
    """

    def __init__(
        self,
        message: str,
        *,
        missing_path: str = None,
        feature_id: str = None,
        root_cause: str = "cross_file_contract",
        pipeline_stage: str = "cross_feature_contract",
    ):
        super().__init__(message)
        self.missing_path = missing_path
        self.feature_id = feature_id
        self.root_cause = root_cause
        self.pipeline_stage = pipeline_stage


class TruncationWarning(UserWarning):
    """
    Warning issued when a response appears to be truncated.

    This is raised as a warning (not exception) so processing can continue
    while alerting the caller to potential incomplete output.

    Attributes:
        agent_name: Name of the agent that produced the response
        finish_reason: API-reported finish reason (e.g., 'max_tokens', 'length')
        output_tokens: Number of output tokens generated
        max_tokens: The max_tokens limit that was set
        indicators: List of heuristic indicators suggesting truncation
        confidence: Confidence score from heuristic detection (0.0-1.0)
    """

    def __init__(
        self,
        message: str,
        agent_name: str = None,
        finish_reason: str = None,
        output_tokens: int = None,
        max_tokens: int = None,
        indicators: list = None,
        confidence: float = None
    ):
        super().__init__(message)
        self.agent_name = agent_name
        self.finish_reason = finish_reason
        self.output_tokens = output_tokens
        self.max_tokens = max_tokens
        self.indicators = indicators or []
        self.confidence = confidence






