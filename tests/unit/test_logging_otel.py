"""
Tests for OTel logging bridge (Phase 3).

Covers:
- OTelTraceContextFilter injects trace_id/span_id
- OTelLogHandler severity mapping
- No-op when OTel is not available
- LogRecord → OTel LogRecord conversion
"""

import logging
from unittest.mock import patch, MagicMock
import pytest


class TestOTelTraceContextFilter:
    """Tests for OTelTraceContextFilter."""

    def test_injects_trace_context_when_available(self):
        """Filter adds trace_id and span_id from active span."""
        from startd8.logging_otel import OTelTraceContextFilter

        filt = OTelTraceContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello", args=(), exc_info=None,
        )

        mock_span_ctx = MagicMock()
        mock_span_ctx.trace_id = 0xABCDEF1234567890ABCDEF1234567890
        mock_span_ctx.span_id = 0xFEDCBA0987654321

        mock_span = MagicMock()
        mock_span.get_span_context.return_value = mock_span_ctx

        with patch("startd8.logging_otel._OTEL_LOGS_AVAILABLE", True), \
             patch("startd8.logging_otel._otel_trace") as mock_trace:
            mock_trace.get_current_span.return_value = mock_span

            result = filt.filter(record)

            assert result is True
            assert record.trace_id == "abcdef1234567890abcdef1234567890"
            assert record.span_id == "fedcba0987654321"

    def test_empty_context_when_no_span(self):
        """Filter adds empty strings when no active span."""
        from startd8.logging_otel import OTelTraceContextFilter

        filt = OTelTraceContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello", args=(), exc_info=None,
        )

        with patch("startd8.logging_otel._OTEL_LOGS_AVAILABLE", True), \
             patch("startd8.logging_otel._otel_trace") as mock_trace:
            mock_span = MagicMock()
            mock_span_ctx = MagicMock()
            mock_span_ctx.trace_id = 0  # No valid trace
            mock_span.get_span_context.return_value = mock_span_ctx
            mock_trace.get_current_span.return_value = mock_span

            filt.filter(record)
            assert record.trace_id == ""
            assert record.span_id == ""

    def test_no_op_without_otel(self):
        """Filter adds empty strings when OTel is unavailable."""
        from startd8.logging_otel import OTelTraceContextFilter

        filt = OTelTraceContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello", args=(), exc_info=None,
        )

        with patch("startd8.logging_otel._OTEL_LOGS_AVAILABLE", False):
            filt.filter(record)
            assert record.trace_id == ""
            assert record.span_id == ""


class TestOTelLogHandler:
    """Tests for OTelLogHandler."""

    def test_no_op_when_otel_unavailable(self):
        """Handler.emit() is a no-op when OTel is unavailable."""
        from startd8.logging_otel import OTelLogHandler

        handler = OTelLogHandler()

        with patch("startd8.logging_otel._OTEL_LOGS_AVAILABLE", False):
            handler._initialized = False
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="test.py",
                lineno=1, msg="test message", args=(), exc_info=None,
            )
            # Should not raise
            handler.emit(record)
            assert handler._otel_logger is None

    def test_severity_mapping(self):
        """Python log levels map to correct OTel severity numbers."""
        from startd8.logging_otel import _SEVERITY_MAP

        assert _SEVERITY_MAP[logging.DEBUG] == 5
        assert _SEVERITY_MAP[logging.INFO] == 9
        assert _SEVERITY_MAP[logging.WARNING] == 13
        assert _SEVERITY_MAP[logging.ERROR] == 17
        assert _SEVERITY_MAP[logging.CRITICAL] == 21

    def test_emit_creates_otel_log_record(self):
        """Handler converts Python LogRecord to OTel LogRecord."""
        from startd8.logging_otel import OTelLogHandler

        handler = OTelLogHandler()
        mock_otel_logger = MagicMock()
        handler._otel_logger = mock_otel_logger
        handler._initialized = True

        record = logging.LogRecord(
            name="startd8.test", level=logging.WARNING, pathname="/src/test.py",
            lineno=42, msg="test warning", args=(), exc_info=None,
        )
        record.funcName = "test_func"

        with patch("startd8.logging_otel._OTEL_LOGS_AVAILABLE", True), \
             patch("startd8.logging_otel._otel_trace") as mock_trace:
            mock_span = MagicMock()
            mock_span.get_span_context.return_value = None
            mock_trace.get_current_span.return_value = mock_span

            handler.emit(record)

            mock_otel_logger.emit.assert_called_once()
            otel_record = mock_otel_logger.emit.call_args[0][0]
            assert otel_record.severity_text == "WARNING"
            assert otel_record.attributes["logger.name"] == "startd8.test"
            assert otel_record.attributes["code.lineno"] == 42
            assert otel_record.attributes["code.function"] == "test_func"

    def test_emit_does_not_raise_on_error(self):
        """Handler swallows exceptions to never break the application."""
        from startd8.logging_otel import OTelLogHandler

        handler = OTelLogHandler()
        mock_otel_logger = MagicMock()
        mock_otel_logger.emit.side_effect = RuntimeError("boom")
        handler._otel_logger = mock_otel_logger
        handler._initialized = True

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="test", args=(), exc_info=None,
        )

        with patch("startd8.logging_otel._OTEL_LOGS_AVAILABLE", True), \
             patch("startd8.logging_otel._otel_trace") as mock_trace:
            mock_trace.get_current_span.return_value = MagicMock()
            # Should not raise
            handler.emit(record)
