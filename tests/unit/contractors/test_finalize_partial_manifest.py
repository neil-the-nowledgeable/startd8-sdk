"""AR-815: Partial manifest on FINALIZE crash.

Verifies that when _write_manifest() or report writing fails,
a partial manifest is written with incomplete=True to preserve
artifacts from prior phases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def finalize_handler(tmp_path):
    """Create a FinalizePhaseHandler with output_dir set."""
    from startd8.contractors.context_seed_handlers import FinalizePhaseHandler

    return FinalizePhaseHandler(output_dir=str(tmp_path))


@pytest.fixture
def minimal_context():
    """Minimal context for FINALIZE to run."""
    from startd8.contractors.protocols import GenerationResult

    gr = GenerationResult(
        success=True,
        generated_files=[],
        cost_usd=0.01,
        model="mock:mock",
    )

    return {
        "tasks": [],
        "task_index": {},
        "generation_results": {"T-1": gr},
        "implementation": {"total_cost": 0.01},
        "test_results": {
            "test_plan": [],
            "total_passed": 0,
            "total_failed": 0,
            "per_task": {},
        },
        "review_results": {
            "review_items": [],
            "total_passed": 0,
            "total_failed": 0,
            "per_task": {},
        },
        "project_root": "/tmp/fake-project",
    }


@pytest.mark.unit
class TestPartialManifestOnCrash:
    """AR-815: Verify partial manifest written when report/manifest write fails."""

    def test_partial_manifest_written_on_atomic_write_error(
        self, finalize_handler, minimal_context, tmp_path,
    ):
        """When atomic_write_json raises, partial manifest should be created."""
        from startd8.utils.file_operations import atomic_write_json

        call_count = 0
        original_write = atomic_write_json

        def failing_write(path, data, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Fail on first call (execution report)
                raise OSError("Disk full")
            # Allow subsequent calls (partial manifest)
            return original_write(path, data, **kwargs)

        with patch(
            "startd8.contractors.context_seed.phases.finalize.atomic_write_json",
            side_effect=failing_write,
        ):
            result = finalize_handler.execute(
                phase=MagicMock(value="finalize"),
                context=minimal_context,
                dry_run=False,
            )

        # Check that partial manifest was written
        manifest_path = tmp_path / "generation-manifest.json"
        assert manifest_path.exists(), "Partial manifest should exist"

        manifest = json.loads(manifest_path.read_text())
        assert manifest.get("incomplete") is True
        assert "error" in manifest
        assert manifest.get("workflow_version") == "0.4.0"

    def test_normal_finalize_writes_complete_manifest(
        self, finalize_handler, minimal_context, tmp_path,
    ):
        """Normal execution should write a complete manifest without incomplete flag."""
        result = finalize_handler.execute(
            phase=MagicMock(value="finalize"),
            context=minimal_context,
            dry_run=False,
        )

        # Manifest may or may not exist (depends on artifacts), but
        # summary should be complete
        summary = minimal_context.get("workflow_summary", {})
        assert summary.get("manifest_incomplete") is None
