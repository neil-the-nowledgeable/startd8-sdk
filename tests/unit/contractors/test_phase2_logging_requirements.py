"""Phase 2 logging requirement coverage (AL-200/201/202/300/301)."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from unittest.mock import patch


def test_execute_phase_has_phase_and_gate_logging_hooks() -> None:
    from startd8.contractors.artisan_contractor import ArtisanContractorWorkflow

    source = inspect.getsource(ArtisanContractorWorkflow._execute_phase)

    assert '"Starting phase: %s"' in source
    assert '"Finished phase: %s (%s)"' in source
    assert '"gate.entry.passed=true phase=%s"' in source
    assert '"gate.entry.passed=false phase=%s violations=%s"' in source
    assert '"gate.exit.passed=true phase=%s"' in source
    assert '"gate.exit.passed=false phase=%s violations=%s"' in source
    assert '"phase": phase.value' in source
    assert '"passed": entry_result.passed' in source
    assert '"passed": exit_result.passed' in source
    assert '"duration_ms": phase_duration_ms' in source
    assert '"workflow_id": workflow_id' in source


def test_task_boundary_helpers_emit_required_fields() -> None:
    from startd8.contractors.context_seed_handlers import (
        _log_task_boundary_complete,
        _log_task_boundary_start,
        logger,
    )

    @dataclass
    class _Task:
        task_id: str = "T-100"
        title: str = "Implement telemetry"
        domain: str = "observability"

    with patch.object(logger, "debug") as debug_spy:
        _log_task_boundary_start(_Task(), phase="implement")
        _log_task_boundary_complete(
            "T-100",
            status="generated",
            phase="implement",
            cost_usd=1.25,
        )

        assert debug_spy.call_count == 2
        assert debug_spy.call_args_list[0].kwargs["extra"] == {
            "task_id": "T-100",
            "task_title": "Implement telemetry",
            "phase": "implement",
            "domain": "observability",
        }
        assert debug_spy.call_args_list[1].kwargs["extra"] == {
            "task_id": "T-100",
            "status": "generated",
            "phase": "implement",
            "cost_usd": 1.25,
        }


def test_phase_handlers_are_wired_for_task_boundary_logging() -> None:
    from startd8.contractors.context_seed_handlers import (
        DesignPhaseHandler,
        ImplementPhaseHandler,
        IntegratePhaseHandler,
        ReviewPhaseHandler,
        TestPhaseHandler,
    )

    design_src = inspect.getsource(DesignPhaseHandler.execute)
    implement_chunks_src = inspect.getsource(ImplementPhaseHandler._tasks_to_chunks)
    implement_map_src = inspect.getsource(ImplementPhaseHandler._map_development_result)
    test_src = inspect.getsource(TestPhaseHandler.execute)
    review_src = inspect.getsource(ReviewPhaseHandler.execute)
    integrate_src = inspect.getsource(IntegratePhaseHandler.execute)

    assert "_log_task_boundary_start(task, phase=\"design\")" in design_src
    assert "_log_task_boundary_complete(" in design_src

    assert "_log_task_boundary_start(task, phase=\"implement\")" in implement_chunks_src
    assert "_log_task_boundary_complete(" in implement_chunks_src
    assert "_log_task_boundary_complete(" in implement_map_src

    assert "_log_task_boundary_start(task, phase=\"test\")" in test_src
    assert "_log_task_boundary_complete(" in test_src

    assert "_log_task_boundary_start(task, phase=\"review\")" in review_src
    assert "_log_task_boundary_complete(" in review_src

    assert "_log_task_boundary_start(task, phase=\"integrate\")" in integrate_src
    assert "_log_task_boundary_complete(" in integrate_src
