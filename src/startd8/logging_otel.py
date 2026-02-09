"""
Python logging → OpenTelemetry log bridge.

Provides:
- ``OTelLogHandler``: logging.Handler that converts Python LogRecords to
  OTel LogRecords and exports them via the global LoggerProvider.
- ``OTelTraceContextFilter``: logging.Filter that injects trace_id and
  span_id from the current OTel context into every LogRecord, so file
  handlers also get trace correlation.

Both are no-ops if OTel is not available.
"""

import logging
from typing import Optional

# OTel severity mapping (Python level → OTel severity number)
_SEVERITY_MAP = {
    logging.DEBUG: 5,      # DEBUG
    logging.INFO: 9,       # INFO
    logging.WARNING: 13,   # WARN
    logging.ERROR: 17,     # ERROR
    logging.CRITICAL: 21,  # FATAL
}

try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry._logs import get_logger_provider, SeverityNumber
    _OTEL_LOGS_AVAILABLE = True
except ImportError:
    _otel_trace = None  # type: ignore[assignment]
    _OTEL_LOGS_AVAILABLE = False
    SeverityNumber = None  # type: ignore[assignment,misc]


class OTelTraceContextFilter(logging.Filter):
    """
    Logging filter that injects OTel trace context into log records.

    Adds ``trace_id`` and ``span_id`` attributes to every log record
    so that even file-based handlers (not going through the OTel bridge)
    include trace correlation IDs.

    No-op if OTel is not available.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if _OTEL_LOGS_AVAILABLE and _otel_trace:
            span = _otel_trace.get_current_span()
            ctx = span.get_span_context() if span else None
            if ctx and ctx.trace_id:
                record.trace_id = format(ctx.trace_id, "032x")  # type: ignore[attr-defined]
                record.span_id = format(ctx.span_id, "016x")  # type: ignore[attr-defined]
            else:
                record.trace_id = ""  # type: ignore[attr-defined]
                record.span_id = ""  # type: ignore[attr-defined]
        else:
            record.trace_id = ""  # type: ignore[attr-defined]
            record.span_id = ""  # type: ignore[attr-defined]
        return True


class OTelLogHandler(logging.Handler):
    """
    Logging handler that converts Python log records to OTel log records.

    Automatically injects trace_id / span_id from the current OTel context
    and maps Python log levels to OTel severity numbers.

    Attributes on each OTel log record:
    - ``logger.name``: Python logger name
    - ``code.filepath``: Source file path
    - ``code.lineno``: Source line number
    - ``code.function``: Function name

    No-op if OTel LoggerProvider is not configured.
    """

    def __init__(self, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self._otel_logger = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazy-init the OTel logger on first use."""
        if self._initialized:
            return self._otel_logger is not None
        self._initialized = True

        if not _OTEL_LOGS_AVAILABLE:
            return False

        try:
            provider = get_logger_provider()
            if provider is not None:
                self._otel_logger = provider.get_logger("startd8")
                return True
        except Exception:
            pass
        return False

    def emit(self, record: logging.LogRecord) -> None:
        """Convert a Python LogRecord to an OTel LogRecord and emit it."""
        if not self._ensure_initialized():
            return

        try:
            # Map severity
            severity_number = _SEVERITY_MAP.get(record.levelno, 9)

            # Build attributes
            attributes = {
                "logger.name": record.name,
                "code.filepath": record.pathname,
                "code.lineno": record.lineno,
                "code.function": record.funcName,
            }

            # Include extra fields from the log record
            for key in ("correlation_id", "agent_name", "pipeline_id"):
                val = getattr(record, key, None)
                if val is not None:
                    attributes[key] = str(val)

            # Get trace context
            span_context = None
            if _otel_trace:
                span = _otel_trace.get_current_span()
                if span:
                    span_context = span.get_span_context()

            self._otel_logger.emit(
                _OTelLogRecord(
                    body=self.format(record) if record.msg else record.getMessage(),
                    severity_text=record.levelname,
                    severity_number=SeverityNumber(severity_number),
                    attributes=attributes,
                    span_context=span_context,
                )
            )
        except Exception:
            # Never let OTel logging failures break the application
            pass


class _OTelLogRecord:
    """Minimal log record compatible with the OTel SDK LoggerProvider.emit()."""

    def __init__(
        self,
        body: str,
        severity_text: str,
        severity_number: "SeverityNumber",
        attributes: Optional[dict] = None,
        span_context: Optional[object] = None,
    ):
        self.body = body
        self.severity_text = severity_text
        self.severity_number = severity_number
        self.attributes = attributes or {}

        # Extract trace/span IDs for the OTel log record
        self.trace_id = 0
        self.span_id = 0
        self.trace_flags = 0
        if span_context and hasattr(span_context, "trace_id"):
            self.trace_id = span_context.trace_id
            self.span_id = span_context.span_id
            self.trace_flags = getattr(span_context, "trace_flags", 0)
