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






