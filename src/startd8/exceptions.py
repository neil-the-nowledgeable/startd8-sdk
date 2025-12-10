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






