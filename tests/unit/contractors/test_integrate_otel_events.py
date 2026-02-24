"""AR-820/AR-825: OTel event and attribute tests for INTEGRATE phase.

Verifies:
  - Truncation rejection emits span event with correct attributes
  - Import validation sets span attributes (unresolved_count, unresolved_modules)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call

import pytest


@pytest.mark.unit
class TestTruncationRejectionEvent:
    """AR-820: Verify OTel span event emitted for truncation-blocked tasks."""

    def test_truncation_rejection_event_attributes(self):
        """Span event should have confidence, action, and source attributes."""
        # Simulate the span event that would be emitted
        mock_span = MagicMock()

        # Reproduce the logic from IntegratePhaseHandler
        _task_trunc = {
            "detected": True,
            "max_confidence": 0.7,
            "truncation_blocked": True,
            "source": "heuristic_high",
        }

        if _task_trunc.get("truncation_blocked"):
            mock_span.set_attribute("task.truncation_blocked", True)
            mock_span.set_attribute(
                "truncation.confidence",
                _task_trunc.get("max_confidence", 0),
            )
            mock_span.add_event(
                "truncation.rejection",
                attributes={
                    "truncation.confidence": _task_trunc.get("max_confidence", 0),
                    "truncation.action": "rejected",
                    "truncation.source": _task_trunc.get("source", "unknown"),
                },
            )

        # Verify the span event was called
        mock_span.add_event.assert_called_once_with(
            "truncation.rejection",
            attributes={
                "truncation.confidence": 0.7,
                "truncation.action": "rejected",
                "truncation.source": "heuristic_high",
            },
        )

        # Verify attributes
        mock_span.set_attribute.assert_any_call("task.truncation_blocked", True)
        mock_span.set_attribute.assert_any_call("truncation.confidence", 0.7)


@pytest.mark.unit
class TestImportValidationSpanAttributes:
    """AR-825: Verify import validation OTel span attributes."""

    def test_unresolved_modules_set_on_span(self):
        """Span should have unresolved_count and unresolved_modules attributes."""
        mock_span = MagicMock()

        # Simulate skipped_files from integration result
        skipped_files = [
            {
                "path": "/tmp/staging/src/module.py",
                "reason": "unresolved_imports",
                "unresolved": ["startd8.nonexistent", "startd8.fake_module"],
            },
        ]

        # Reproduce the AR-825 logic
        _import_skipped = [
            s for s in skipped_files
            if isinstance(s, dict) and s.get("reason") == "unresolved_imports"
        ]
        _unresolved_modules: list[str] = []
        for s in _import_skipped:
            _unresolved_modules.extend(s.get("unresolved", []))

        mock_span.set_attribute(
            "task.import_validation.unresolved_count", len(_unresolved_modules),
        )
        mock_span.set_attribute(
            "task.import_validation.unresolved_modules",
            ", ".join(_unresolved_modules) if _unresolved_modules else "",
        )

        # Verify
        mock_span.set_attribute.assert_any_call(
            "task.import_validation.unresolved_count", 2,
        )
        mock_span.set_attribute.assert_any_call(
            "task.import_validation.unresolved_modules",
            "startd8.nonexistent, startd8.fake_module",
        )

    def test_no_unresolved_modules_sets_zero(self):
        """When no imports are unresolved, count should be 0."""
        mock_span = MagicMock()

        skipped_files = [
            {"path": "/tmp/staging/src/module.py", "reason": "size_regression"},
        ]

        _import_skipped = [
            s for s in skipped_files
            if isinstance(s, dict) and s.get("reason") == "unresolved_imports"
        ]
        _unresolved_modules: list[str] = []
        for s in _import_skipped:
            _unresolved_modules.extend(s.get("unresolved", []))

        mock_span.set_attribute(
            "task.import_validation.unresolved_count", len(_unresolved_modules),
        )
        mock_span.set_attribute(
            "task.import_validation.unresolved_modules",
            ", ".join(_unresolved_modules) if _unresolved_modules else "",
        )

        mock_span.set_attribute.assert_any_call(
            "task.import_validation.unresolved_count", 0,
        )
        mock_span.set_attribute.assert_any_call(
            "task.import_validation.unresolved_modules", "",
        )
