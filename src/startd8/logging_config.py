"""
Logging configuration for startd8 SDK

Provides structured logging with JSON format for production environments.
Automatically sets up a default log file handler for error persistence.
"""

import logging
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from .context import correlation_id as correlation_id_ctx
from .paths import default_config_dir

# Backwards-compatible export: `startd8.logging_config.correlation_id`
correlation_id = correlation_id_ctx

# Track if default logging has been initialized
_default_logging_initialized = False


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging (Loki-friendly format)"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON (optimized for Loki ingestion)"""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            # Also add exception type and value for better Loki querying
            exc_type, exc_value, _ = record.exc_info
            log_data["exception_type"] = exc_type.__name__ if exc_type else None
            log_data["exception_message"] = str(exc_value) if exc_value else None
        
        # Add trace_id for Loki correlation (if available from OpenTelemetry)
        if hasattr(record, "trace_id"):
            log_data["trace_id"] = record.trace_id
        
        if hasattr(record, "span_id"):
            log_data["span_id"] = record.span_id
        
        # Add extra fields
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id
        
        if hasattr(record, "agent_name"):
            log_data["agent_name"] = record.agent_name
        
        if hasattr(record, "file_path"):
            log_data["file_path"] = record.file_path
        
        # Add source location for debugging
        log_data["source"] = {
            "file": record.pathname,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add any other extra fields
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs", "message",
                "pathname", "process", "processName", "relativeCreated", "thread",
                "threadName", "exc_info", "exc_text", "stack_info", "correlation_id",
                "agent_name", "file_path", "trace_id", "span_id"
            ]:
                log_data[key] = value
        
        return json.dumps(log_data)


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: Optional[Path] = None,
    correlation_id: Optional[str] = None
) -> logging.Logger:
    """
    Set up logging configuration
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON formatting (for production)
        log_file: Optional file to write logs to
        correlation_id: Optional correlation ID for request tracking
    
    Returns:
        Configured logger
    """
    logger = logging.getLogger("startd8")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # More verbose in files
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Add correlation ID to all log records if provided
    if correlation_id:
        # Also set ContextVar so events/costs can pick it up
        correlation_id_ctx.set(correlation_id)

        old_factory = logging.getLogRecordFactory()
        
        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.correlation_id = correlation_id
            return record
        
        logging.setLogRecordFactory(record_factory)
    
    return logger


def _ensure_default_log_file_handler():
    """
    Ensure a default log file handler is set up for error persistence.
    This is called automatically when get_logger is first used.
    """
    global _default_logging_initialized
    
    if _default_logging_initialized:
        return
    
    root_logger = logging.getLogger("startd8")
    
    # Check if a file handler already exists
    has_file_handler = any(
        isinstance(handler, logging.FileHandler) 
        for handler in root_logger.handlers
    )
    
    if has_file_handler:
        _default_logging_initialized = True
        return
    
    # Set up default log file in ~/.startd8/logs/startd8.log
    # This location is searched by error_analysis.py
    config_dir = default_config_dir()
    log_dir = config_dir / "logs"
    log_file = log_dir / "startd8.log"
    
    # Try to set up file handler, but handle permission errors gracefully
    try:
        # Create log directory if it doesn't exist
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up file handler with JSON format (Loki-friendly)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # Capture all levels in file
        file_handler.setFormatter(JSONFormatter())
        
        # Add file handler to root logger
        root_logger.addHandler(file_handler)
    except (PermissionError, OSError) as e:
        # Permission denied or other filesystem error - fall back to console-only logging
        # This can happen in sandboxed environments or when user doesn't have write access
        import warnings
        warnings.warn(
            f"Could not create log file at {log_file}: {e}. "
            "Falling back to console-only logging.",
            RuntimeWarning,
            stacklevel=2
        )
        # Continue without file handler - console handler will still be set up below
    
    # Also ensure console handler exists for stderr/stdout
    has_console_handler = any(
        isinstance(handler, logging.StreamHandler) 
        for handler in root_logger.handlers
    )
    
    if not has_console_handler:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.INFO)  # Less verbose in console
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # Set root logger level
    if root_logger.level == logging.NOTSET:
        root_logger.setLevel(logging.INFO)
    
    _default_logging_initialized = True


def get_logger(name: str = "startd8") -> logging.Logger:
    """
    Get a logger instance.
    
    Automatically sets up a default log file handler if one doesn't exist.
    Logs are written to ~/.startd8/logs/startd8.log in JSON format (Loki-friendly).
    
    Args:
        name: Logger name (defaults to "startd8")
    
    Returns:
        Logger instance
    """
    _ensure_default_log_file_handler()
    return logging.getLogger(name)

