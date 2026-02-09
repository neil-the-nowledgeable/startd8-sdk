"""
Tests for Phase 3.2 OpenTelemetry Integration:
- FR-400: Parent span in run()
- FR-401: Child span per step
- FR-402: ProjectContext labels on span
- FR-403: Graceful no-op when OTel not installed
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, Any, List, Optional

from startd8.workflows.models import (
    WorkflowMetadata,
    WorkflowInput,
    WorkflowResult,
    WorkflowMetrics,
)
from startd8.workflows.base import WorkflowBase


# =========================================================================
# Test workflow for OTel tests
# =========================================================================

class OTelTestWorkflow(WorkflowBase):
    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="otel-test",
            name="OTel Test",
            description="Workflow for OTel testing",
            version="1.0.0",
            inputs=[
                WorkflowInput(name="document", type="text", required=True),
            ],
            requires_agents=False,
        )

    def _execute(self, config, agents=None, on_progress=None):
        return WorkflowResult(
            workflow_id="otel-test",
            success=True,
            output="done",
            metrics=WorkflowMetrics(input_tokens=10, output_tokens=20),
        )


class FailingOTelWorkflow(WorkflowBase):
    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="otel-fail",
            name="OTel Fail",
            description="Workflow that raises",
            inputs=[],
            requires_agents=False,
        )

    def _execute(self, config, agents=None, on_progress=None):
        raise RuntimeError("workflow boom")


# =========================================================================
# FR-403: Graceful no-op
# =========================================================================

class TestGracefulNoOp:
    def test_no_error_without_otel(self):
        """When OTel is not installed, workflows still run normally."""
        wf = OTelTestWorkflow()
        # Even without OTel, run() works fine
        result = wf.run({"document": "hello"})
        assert result.success is True

    def test_tracer_is_none_or_tracer(self):
        """_tracer is either None (no OTel) or a valid tracer."""
        from startd8.workflows import base
        # _tracer can be None or an OTel tracer
        assert base._tracer is None or hasattr(base._tracer, 'start_span')


# =========================================================================
# FR-400: Parent span
# =========================================================================

class TestParentSpan:
    @staticmethod
    def _make_mock_tracer():
        """Create a mock tracer with start_as_current_span returning a context manager."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_span)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_ctx
        return mock_tracer, mock_span

    def test_span_created_when_tracer_available(self):
        """When _tracer is set, a span is created with correct attributes."""
        mock_tracer, mock_span = self._make_mock_tracer()

        wf = OTelTestWorkflow()
        with patch("startd8.workflows.base._tracer", mock_tracer), \
             patch("startd8.workflows.base._otel_trace") as mock_trace:
            result = wf.run({"document": "hello"})

        mock_tracer.start_as_current_span.assert_called_once()
        call_args = mock_tracer.start_as_current_span.call_args
        assert "workflow.otel-test" in call_args[0][0]
        # Verify attributes
        attrs = call_args[1].get("attributes", call_args[0][1] if len(call_args[0]) > 1 else {})
        assert attrs["workflow.id"] == "otel-test"
        assert attrs["workflow.name"] == "OTel Test"
        assert attrs["workflow.version"] == "1.0.0"

    def test_span_ended_on_success(self):
        mock_tracer, mock_span = self._make_mock_tracer()

        wf = OTelTestWorkflow()
        with patch("startd8.workflows.base._tracer", mock_tracer), \
             patch("startd8.workflows.base._otel_trace"):
            wf.run({"document": "hello"})

        # Context manager exit closes the span — verify __exit__ was called
        mock_tracer.start_as_current_span.return_value.__exit__.assert_called_once()

    def test_span_records_error_on_failure(self):
        mock_tracer, mock_span = self._make_mock_tracer()
        mock_trace = MagicMock()

        wf = FailingOTelWorkflow()
        with patch("startd8.workflows.base._tracer", mock_tracer), \
             patch("startd8.workflows.base._otel_trace", mock_trace):
            with pytest.raises(RuntimeError, match="workflow boom"):
                wf.run({})

        mock_span.set_status.assert_called_once()
        mock_span.record_exception.assert_called_once()

    def test_span_sets_success_attribute(self):
        mock_tracer, mock_span = self._make_mock_tracer()

        wf = OTelTestWorkflow()
        with patch("startd8.workflows.base._tracer", mock_tracer), \
             patch("startd8.workflows.base._otel_trace"):
            wf.run({"document": "hi"})

        mock_span.set_attribute.assert_any_call("workflow.success", True)


# =========================================================================
# FR-402: ProjectContext labels
# =========================================================================

class TestProjectContextOnSpan:
    @staticmethod
    def _make_mock_tracer():
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_span)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_ctx
        return mock_tracer, mock_span

    def test_project_context_labels_attached(self):
        mock_tracer, mock_span = self._make_mock_tracer()

        wf = OTelTestWorkflow()
        config = {
            "document": "hello",
            "project_context": {
                "project_id": "proj-123",
                "project_name": "My Project",
            },
        }
        with patch("startd8.workflows.base._tracer", mock_tracer), \
             patch("startd8.workflows.base._otel_trace"):
            wf.run(config)

        # Verify project context labels were set
        set_attr_calls = {
            call.args[0]: call.args[1]
            for call in mock_span.set_attribute.call_args_list
        }
        assert set_attr_calls.get("io.contextcore.project_id") == "proj-123"
        assert set_attr_calls.get("io.contextcore.project_name") == "My Project"

    def test_no_context_no_labels(self):
        mock_tracer, mock_span = self._make_mock_tracer()

        wf = OTelTestWorkflow()
        with patch("startd8.workflows.base._tracer", mock_tracer), \
             patch("startd8.workflows.base._otel_trace"):
            wf.run({"document": "hello"})

        # No io.contextcore labels should be set (only workflow.success)
        io_calls = [
            call for call in mock_span.set_attribute.call_args_list
            if call.args[0].startswith("io.contextcore")
        ]
        assert len(io_calls) == 0


# =========================================================================
# FR-401: Child span per step (orchestration module)
# =========================================================================

class TestChildSpanOrchestration:
    def test_tracer_import_in_orchestration(self):
        """Orchestration module has _tracer available."""
        from startd8 import orchestration
        assert hasattr(orchestration, '_tracer')

    def test_tracer_is_none_or_tracer_in_orchestration(self):
        from startd8 import orchestration
        assert orchestration._tracer is None or hasattr(orchestration._tracer, 'start_span')
