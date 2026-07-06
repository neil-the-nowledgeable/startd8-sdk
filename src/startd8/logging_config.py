"""
Logging configuration for startd8 SDK

Provides structured logging with JSON format for production environments.
Automatically sets up a default log file handler for error persistence.
"""

import logging
import logging.handlers
import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from .context import correlation_id as correlation_id_ctx
from .paths import default_config_dir

# Environment variable for log level control
_ENV_LOG_LEVEL = os.environ.get("STARTD8_LOG_LEVEL", "").upper() or None

# Log rotation defaults: 5 MB per file, keep 3 backups (≈20 MB total)
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_DEFAULT_BACKUP_COUNT = 3

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
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            Can also be set via STARTD8_LOG_LEVEL env var (env var takes precedence).
        json_format: Use JSON formatting (for production)
        log_file: Optional file to write logs to
        correlation_id: Optional correlation ID for request tracking

    Returns:
        Configured logger
    """
    # Environment variable overrides the argument
    effective_level = _ENV_LOG_LEVEL or level.upper()
    logger = logging.getLogger("startd8")
    logger.setLevel(getattr(logging, effective_level))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, effective_level))
    
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified (rotating to prevent unbounded growth)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=_DEFAULT_MAX_BYTES,
            backupCount=_DEFAULT_BACKUP_COUNT,
            encoding="utf-8",
        )
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
    
    # Check if a file handler already exists (RotatingFileHandler is a FileHandler subclass)
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
        
        # Set up rotating file handler with JSON format (Loki-friendly)
        # 5 MB per file, 3 backups → ~20 MB max disk usage
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=_DEFAULT_MAX_BYTES,
            backupCount=_DEFAULT_BACKUP_COUNT,
            encoding="utf-8",
        )
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
    
    # Also ensure console handler exists for stderr/stdout.
    # FileHandler is a StreamHandler subclass, so exclude it explicitly.
    has_console_handler = any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    )
    
    if not has_console_handler:
        console_level = getattr(logging, _ENV_LOG_LEVEL) if _ENV_LOG_LEVEL else logging.INFO
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(console_level)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # Set root logger level (env var overrides default)
    if root_logger.level == logging.NOTSET or _ENV_LOG_LEVEL:
        root_level = getattr(logging, _ENV_LOG_LEVEL) if _ENV_LOG_LEVEL else logging.INFO
        root_logger.setLevel(root_level)

    # Mark as initialized (file + console handlers are ready).
    # Set BEFORE OTel calls to prevent re-entrancy if OTel init logs.
    _default_logging_initialized = True

    # Auto-configure OTel if available (must run before attaching handlers
    # so the LoggerProvider exists when _attach_otel_handlers checks for it)
    try:
        from .otel import auto_configure_otel
        auto_configure_otel()
    except ImportError:
        pass

    # Add OTel log handler and trace context filter if OTel LoggerProvider is available
    _attach_otel_handlers(root_logger)


def _attach_otel_handlers(logger: logging.Logger) -> None:
    """Attach OTel log handler and trace context filter if OTel is configured."""
    try:
        from .logging_otel import OTelLogHandler, OTelTraceContextFilter

        # Avoid duplicate handlers
        if any(isinstance(h, OTelLogHandler) for h in logger.handlers):
            return

        # Check if OTel LoggerProvider is available
        try:
            from opentelemetry._logs import get_logger_provider
            provider = get_logger_provider()
            if provider is None:
                return
        except (ImportError, Exception):
            return

        # Add OTel log handler
        otel_handler = OTelLogHandler()
        otel_handler.setLevel(logging.DEBUG)
        logger.addHandler(otel_handler)

        # Add trace context filter to all existing handlers
        trace_filter = OTelTraceContextFilter()
        for handler in logger.handlers:
            handler.addFilter(trace_filter)

    except ImportError:
        pass


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


def _env_debug() -> bool:
    """True when ``STARTD8_DEBUG`` is set to a truthy value (``1``/``true``/``yes``/``on``).

    Used by the CLI to resolve the diagnostic-logging toggle from the environment,
    complementing the ``--debug`` flag (Kickoff UX FR-UX-14).
    """
    return os.environ.get("STARTD8_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def configure_cli_logging(*, debug: bool) -> None:
    """Apply the CLI output-hygiene logging policy (Kickoff UX FR-UX-13/14).

    Interactive CLI invocations are **quiet by default**: the console shows only
    ``WARNING``/``ERROR`` unless ``debug`` is requested, so diagnostic plumbing
    lines (``<ts> - startd8.<module> - INFO - …``) never reach the user's terminal.
    ``INFO``/``DEBUG`` records still flow to the rotating file sink and OTel.

    Two levels are set, and **both matter**:

    - The ``startd8`` **logger** level is pinned to ``DEBUG`` so records are not
      dropped *before any handler* — otherwise the file/OTel sinks lose fidelity
      and ``--debug`` could never surface ``DEBUG`` on the console (the logger gate
      that ``_ensure_default_log_file_handler`` leaves at ``INFO``, see :242).
    - The **console handler(s)** level gates terminal visibility: ``WARNING`` by
      default, ``DEBUG`` under ``debug``.

    Precedence: an explicit ``STARTD8_LOG_LEVEL`` **wins** and is honored verbatim
    for both the logger and the console (preserving the pre-existing env override),
    so e.g. ``STARTD8_LOG_LEVEL=ERROR`` overrides ``--debug``.

    CLI-only: this is invoked from the CLI entry, never from library import, so
    embedders keep the ``_ensure_default_log_file_handler`` defaults.

    Idempotent — mutates handler/logger *levels* (adds a console handler only if
    one is genuinely absent); safe to call twice (import guard + root callback).

    Note: ``--debug`` (parsed from argv) cannot retroactively surface logs emitted
    *before* argv is parsed; the earliest import-time logs honor only the env vars.
    """
    root_logger = logging.getLogger("startd8")

    if _ENV_LOG_LEVEL:
        # Explicit env override wins for everything (verbatim), matching prior semantics.
        logger_level = getattr(logging, _ENV_LOG_LEVEL, logging.WARNING)
        console_level = logger_level
    else:
        # Keep the logger open so file/OTel retain full fidelity; gate the console.
        logger_level = logging.DEBUG
        console_level = logging.DEBUG if debug else logging.WARNING

    def _apply_console_level() -> None:
        # Mutate every non-file console StreamHandler (a stderr one from
        # _ensure_default_log_file_handler AND possibly a stdout one from setup_logging).
        handlers = [
            h for h in root_logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        if not handlers:
            # _ensure_default_log_file_handler early-returns before adding a console
            # handler when a file handler already exists; add one so the quiet default
            # (and --debug) actually take effect rather than silently no-op'ing.
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                )
            )
            root_logger.addHandler(handler)
            handlers = [handler]
        for handler in handlers:
            handler.setLevel(console_level)

    # Quiet the console BEFORE _ensure_default_log_file_handler() runs its first-time
    # init — that path creates the console handler (at INFO) AND calls
    # auto_configure_otel(), which logs "Telemetry: ACTIVE …" at INFO. Setting the
    # level up front (and the logger level, so _ensure won't reset a NOTSET logger to
    # INFO) suppresses that line on the quiet default.
    root_logger.setLevel(logger_level)
    _apply_console_level()
    _ensure_default_log_file_handler()
    # Re-assert after init (it may have added handlers / re-set the root level).
    root_logger.setLevel(logger_level)
    _apply_console_level()

