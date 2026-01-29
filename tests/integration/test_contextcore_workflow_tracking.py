# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
# See LICENSE.md for complete terms.

"""
Integration tests for ContextCore workflow tracking (SDK-105).

Tests that verify:
1. Workflow execution creates task span
2. Span attributes match config
3. Phase events are recorded
4. Span completion on workflow success
5. Span cancellation on workflow failure
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from startd8.integrations import (
    ContextCoreConfig,
    ContextCoreWorkflowAdapter,
    WorkflowTaskSpec,
)
from startd8.workflows.models import WorkflowResult, WorkflowMetrics, StepResult


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_workflow():
    """Create a mock workflow that returns success."""
    workflow = Mock()
    workflow.run.return_value = WorkflowResult(
        workflow_id="test-workflow-123",
        success=True,
        output="Test output content",
        metrics=WorkflowMetrics(
            total_cost=0.05,
            total_time_ms=1500,
            step_count=3,
            input_tokens=500,
            output_tokens=200,
        ),
        steps=[
            StepResult(step_name="draft", output="Draft content"),
            StepResult(step_name="review", output="Review passed"),
            StepResult(step_name="final", output="Final output"),
        ],
    )
    return workflow


@pytest.fixture
def failing_workflow():
    """Create a mock workflow that returns failure."""
    workflow = Mock()
    workflow.run.return_value = WorkflowResult(
        workflow_id="test-workflow-fail",
        success=False,
        output=None,
        error="Validation failed: missing required field",
        metrics=WorkflowMetrics(
            total_cost=0.02,
            total_time_ms=500,
            step_count=1,
            input_tokens=200,
            output_tokens=50,
        ),
    )
    return workflow


@pytest.fixture
def exception_workflow():
    """Create a mock workflow that raises an exception."""
    workflow = Mock()
    workflow.run.side_effect = RuntimeError("API connection timeout")
    return workflow


@pytest.fixture
def contextcore_config():
    """Create a standard ContextCore config for testing."""
    return ContextCoreConfig(
        project_id="test-project",
        project_name="Test Project",
        sprint_id="sprint-5",
        auto_create_task=True,
        auto_complete_task=True,
        emit_insights=True,
    )


@pytest.fixture
def mock_tracker():
    """Create a mock TaskTrackerWrapper."""
    tracker = Mock()
    tracker.enabled = True
    tracker.start_task.return_value = True
    tracker.update_status.return_value = True
    tracker.add_event.return_value = True
    tracker.complete_task.return_value = True
    tracker.fail_task.return_value = True
    tracker.emit_decision.return_value = True
    tracker.shutdown.return_value = None
    return tracker


# ============================================================================
# Test: Workflow Creates Task Span
# ============================================================================

class TestWorkflowCreatesTaskSpan:
    """Test that workflow execution creates task span."""

    def test_start_task_called_with_correct_params(
        self, mock_workflow, contextcore_config, mock_tracker
    ):
        """Verify start_task is called with all provided attributes."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )
        # Inject mock tracker
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            task_title="Integration test task",
            workflow_config={"task_description": "Test the integration"},
            task_type="task",
            parent_id="SDK-100",
            depends_on=["SDK-101", "SDK-102"],
            story_points=2,
            priority="high",
            assignee="test-user",
            labels=["testing", "integration"],
            url="https://example.com/task/SDK-105",
        )

        mock_tracker.start_task.assert_called_once_with(
            task_id="SDK-105",
            title="Integration test task",
            task_type="task",
            parent_id="SDK-100",
            sprint_id="sprint-5",
            depends_on=["SDK-101", "SDK-102"],
            story_points=2,
            priority="high",
            assignee="test-user",
            labels=["testing", "integration"],
            url="https://example.com/task/SDK-105",
        )

    def test_status_updated_to_in_progress(
        self, mock_workflow, contextcore_config, mock_tracker
    ):
        """Verify task status is set to in_progress when started."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test task",
        )

        mock_tracker.update_status.assert_called_with("SDK-105", "in_progress")

    def test_task_not_created_when_auto_create_disabled(
        self, mock_workflow, mock_tracker
    ):
        """Verify no task span when auto_create_task is False."""
        config = ContextCoreConfig(
            project_id="test-project",
            auto_create_task=False,
        )
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=config,
        )
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test task",
        )

        mock_tracker.start_task.assert_not_called()
        mock_tracker.update_status.assert_not_called()


# ============================================================================
# Test: Span Attributes Match Config
# ============================================================================

class TestSpanAttributesMatchConfig:
    """Test that span attributes match the provided configuration."""

    def test_task_id_propagated(
        self, mock_workflow, contextcore_config, mock_tracker
    ):
        """Verify task_id is correctly propagated to tracker."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        result = adapter.run_as_task(
            task_id="CUSTOM-TASK-123",
            task_title="Custom task",
        )

        # Verify task_id used in start_task
        call_kwargs = mock_tracker.start_task.call_args[1]
        assert call_kwargs["task_id"] == "CUSTOM-TASK-123"

        # Verify project context on result
        assert result.project_context.task_id == "CUSTOM-TASK-123"
        assert result.project_context.project_id == "test-project"
        assert result.project_context.sprint_id == "sprint-5"

    def test_title_defaults_to_task_description(
        self, mock_workflow, contextcore_config, mock_tracker
    ):
        """Verify title defaults to task_description when not provided."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            workflow_config={"task_description": "Implement rate limiter"},
        )

        call_kwargs = mock_tracker.start_task.call_args[1]
        assert call_kwargs["title"] == "Implement rate limiter"

    def test_title_defaults_to_task_id_when_no_description(
        self, mock_workflow, contextcore_config, mock_tracker
    ):
        """Verify title defaults to task_id when no description provided."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            workflow_config={},
        )

        call_kwargs = mock_tracker.start_task.call_args[1]
        assert call_kwargs["title"] == "SDK-105"

    def test_sprint_id_from_config(
        self, mock_workflow, mock_tracker
    ):
        """Verify sprint_id is taken from config."""
        config = ContextCoreConfig(
            project_id="test-project",
            sprint_id="sprint-99",
        )
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=config,
        )
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test",
        )

        call_kwargs = mock_tracker.start_task.call_args[1]
        assert call_kwargs["sprint_id"] == "sprint-99"


# ============================================================================
# Test: Phase Events Recorded
# ============================================================================

class TestPhaseEventsRecorded:
    """Test that workflow phase events are recorded."""

    def test_progress_callback_emits_events(
        self, mock_workflow, contextcore_config, mock_tracker
    ):
        """Verify progress callbacks emit task events."""
        # Capture the progress callback
        captured_callback = None

        def capture_run(config, agents=None, on_progress=None):
            nonlocal captured_callback
            captured_callback = on_progress
            # Simulate progress callbacks
            if on_progress:
                on_progress(1, 3, "Drafting...")
                on_progress(2, 3, "Reviewing...")
                on_progress(3, 3, "Finalizing...")
            return WorkflowResult(
                workflow_id="test",
                success=True,
                output="Done",
                metrics=WorkflowMetrics(
                    total_cost=0.01,
                    total_time_ms=100,
                    step_count=3,
                    input_tokens=100,
                    output_tokens=50,
                ),
            )

        mock_workflow.run.side_effect = capture_run

        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test",
        )

        # Verify progress events were emitted
        event_calls = [c for c in mock_tracker.add_event.call_args_list
                       if c[0][1] == "workflow.progress"]
        assert len(event_calls) == 3

        # Verify event attributes
        assert event_calls[0][0][2]["step"] == 1
        assert event_calls[0][0][2]["message"] == "Drafting..."
        assert event_calls[1][0][2]["step"] == 2
        assert event_calls[2][0][2]["step"] == 3

    def test_completion_event_includes_metrics(
        self, mock_workflow, contextcore_config, mock_tracker
    ):
        """Verify completion event includes workflow metrics."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test",
        )

        # Find the completion event
        completion_calls = [c for c in mock_tracker.add_event.call_args_list
                           if c[0][1] == "workflow.completed"]
        assert len(completion_calls) == 1

        event_attrs = completion_calls[0][0][2]
        assert event_attrs["workflow_id"] == "test-workflow-123"
        assert event_attrs["total_cost"] == 0.05
        assert event_attrs["total_time_ms"] == 1500
        assert event_attrs["step_count"] == 3
        assert event_attrs["input_tokens"] == 500
        assert event_attrs["output_tokens"] == 200


# ============================================================================
# Test: Span Completion on Success
# ============================================================================

class TestSpanCompletionOnSuccess:
    """Test that span is completed when workflow succeeds."""

    def test_complete_task_called_on_success(
        self, mock_workflow, contextcore_config, mock_tracker
    ):
        """Verify complete_task is called when workflow succeeds."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        result = adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test",
        )

        assert result.success is True
        mock_tracker.complete_task.assert_called_once_with("SDK-105")
        mock_tracker.fail_task.assert_not_called()

    def test_decision_insight_emitted_on_success(
        self, mock_workflow, contextcore_config, mock_tracker
    ):
        """Verify decision insight is emitted when workflow succeeds."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test task for insights",
        )

        mock_tracker.emit_decision.assert_called_once()
        call_kwargs = mock_tracker.emit_decision.call_args[1]
        assert "Completed workflow" in call_kwargs["summary"]
        assert call_kwargs["confidence"] == 0.9
        assert call_kwargs["context"]["task_id"] == "SDK-105"

    def test_no_completion_when_auto_complete_disabled(
        self, mock_workflow, mock_tracker
    ):
        """Verify no completion when auto_complete_task is False."""
        config = ContextCoreConfig(
            project_id="test-project",
            auto_complete_task=False,
        )
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=config,
        )
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test",
        )

        mock_tracker.complete_task.assert_not_called()
        mock_tracker.fail_task.assert_not_called()

    def test_project_context_set_on_result(
        self, mock_workflow, contextcore_config, mock_tracker
    ):
        """Verify project context is set on workflow result."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        result = adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test",
        )

        assert result.project_context is not None
        assert result.project_context.project_id == "test-project"
        assert result.project_context.project_name == "Test Project"
        assert result.project_context.task_id == "SDK-105"
        assert result.project_context.sprint_id == "sprint-5"


# ============================================================================
# Test: Span Cancellation on Failure
# ============================================================================

class TestSpanCancellationOnFailure:
    """Test that span is cancelled/failed when workflow fails."""

    def test_fail_task_called_on_workflow_failure(
        self, failing_workflow, contextcore_config, mock_tracker
    ):
        """Verify fail_task is called when workflow returns failure."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=failing_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        result = adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test",
        )

        assert result.success is False
        mock_tracker.fail_task.assert_called_once_with(
            "SDK-105",
            "Validation failed: missing required field"
        )
        mock_tracker.complete_task.assert_not_called()

    def test_fail_task_called_on_exception(
        self, exception_workflow, contextcore_config, mock_tracker
    ):
        """Verify fail_task is called when workflow raises exception."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=exception_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        with pytest.raises(RuntimeError, match="API connection timeout"):
            adapter.run_as_task(
                task_id="SDK-105",
                task_title="Test",
            )

        mock_tracker.fail_task.assert_called_once_with(
            "SDK-105",
            "API connection timeout"
        )

    def test_fail_task_with_generic_message_when_no_error(
        self, mock_tracker
    ):
        """Verify fail_task uses generic message when no error provided."""
        workflow = Mock()
        workflow.run.return_value = WorkflowResult(
            workflow_id="test",
            success=False,
            output=None,
            error=None,  # No error message
            metrics=WorkflowMetrics(
                total_cost=0.01,
                total_time_ms=100,
                step_count=1,
                input_tokens=50,
                output_tokens=25,
            ),
        )

        config = ContextCoreConfig(project_id="test-project")
        adapter = ContextCoreWorkflowAdapter(workflow=workflow, config=config)
        adapter._tracker = mock_tracker

        adapter.run_as_task(task_id="SDK-105", task_title="Test")

        mock_tracker.fail_task.assert_called_once_with("SDK-105", "Workflow failed")

    def test_no_insight_emitted_on_failure(
        self, failing_workflow, contextcore_config, mock_tracker
    ):
        """Verify no decision insight is emitted on failure."""
        adapter = ContextCoreWorkflowAdapter(
            workflow=failing_workflow,
            config=contextcore_config,
        )
        adapter._tracker = mock_tracker

        adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test",
        )

        mock_tracker.emit_decision.assert_not_called()


# ============================================================================
# Test: Graceful Degradation
# ============================================================================

class TestGracefulDegradation:
    """Test behavior when ContextCore is not available."""

    def test_workflow_runs_when_tracker_disabled(self, mock_workflow):
        """Verify workflow still runs when tracker is disabled."""
        config = ContextCoreConfig(project_id="test-project")
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=config,
        )

        # Create a disabled tracker
        disabled_tracker = Mock()
        disabled_tracker.enabled = False
        adapter._tracker = disabled_tracker

        result = adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test",
        )

        # Workflow should still execute
        assert result.success is True
        assert result.output == "Test output content"
        mock_workflow.run.assert_called_once()

    def test_project_context_set_even_when_tracking_disabled(self, mock_workflow):
        """Verify project context is set even without tracking."""
        config = ContextCoreConfig(
            project_id="test-project",
            sprint_id="sprint-5",
        )
        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=config,
        )

        # Disable tracking
        disabled_tracker = Mock()
        disabled_tracker.enabled = False
        adapter._tracker = disabled_tracker

        result = adapter.run_as_task(
            task_id="SDK-105",
            task_title="Test",
        )

        # Project context should still be populated
        assert result.project_context is not None
        assert result.project_context.project_id == "test-project"
        assert result.project_context.task_id == "SDK-105"


# ============================================================================
# Test: End-to-End with TaskTrackerWrapper
# ============================================================================

class TestEndToEndWithWrapper:
    """End-to-end tests using actual TaskTrackerWrapper (mocked ContextCore)."""

    @patch("startd8.integrations.contextcore.TaskTrackerWrapper")
    def test_full_successful_workflow_lifecycle(
        self, MockWrapper, mock_workflow, contextcore_config
    ):
        """Test complete lifecycle: create -> progress -> complete."""
        # Setup mock wrapper instance
        mock_instance = Mock()
        mock_instance.enabled = True
        mock_instance.start_task.return_value = True
        mock_instance.update_status.return_value = True
        mock_instance.add_event.return_value = True
        mock_instance.complete_task.return_value = True
        mock_instance.emit_decision.return_value = True
        MockWrapper.return_value = mock_instance

        adapter = ContextCoreWorkflowAdapter(
            workflow=mock_workflow,
            config=contextcore_config,
        )

        result = adapter.run_as_task(
            task_id="SDK-105",
            task_title="Full lifecycle test",
            story_points=3,
            labels=["test"],
        )

        # Verify full lifecycle
        assert result.success is True
        mock_instance.start_task.assert_called_once()
        mock_instance.update_status.assert_called_with("SDK-105", "in_progress")
        mock_instance.complete_task.assert_called_once_with("SDK-105")

    @patch("startd8.integrations.contextcore.TaskTrackerWrapper")
    def test_full_failed_workflow_lifecycle(
        self, MockWrapper, failing_workflow, contextcore_config
    ):
        """Test complete lifecycle with failure: create -> fail."""
        mock_instance = Mock()
        mock_instance.enabled = True
        mock_instance.start_task.return_value = True
        mock_instance.update_status.return_value = True
        mock_instance.fail_task.return_value = True
        MockWrapper.return_value = mock_instance

        adapter = ContextCoreWorkflowAdapter(
            workflow=failing_workflow,
            config=contextcore_config,
        )

        result = adapter.run_as_task(
            task_id="SDK-105",
            task_title="Failing test",
        )

        assert result.success is False
        mock_instance.start_task.assert_called_once()
        mock_instance.fail_task.assert_called_once()
        mock_instance.complete_task.assert_not_called()
