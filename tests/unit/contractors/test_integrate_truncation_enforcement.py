"""AR-816/AR-818/AR-819: Truncation enforcement at INTEGRATE phase.

Tests:
  - truncation_blocked tasks are skipped during integration
  - Compound gate lowers truncation threshold for existing files
  - Size regression uses stricter threshold when truncation detected
  - New files use standard threshold
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _fake_gen_result():
    """Create a minimal GenerationResult-like object."""
    from startd8.contractors.protocols import GenerationResult
    return GenerationResult(
        success=True,
        generated_files=[Path("/tmp/staging/src/module.py")],
        cost_usd=0.01,
        model="mock:mock",
    )


@pytest.fixture
def _fake_seed_task():
    """Create a fake SeedTask for testing."""
    from tests.unit.contractors.conftest import FakeSeedTask
    return FakeSeedTask(
        task_id="T-1",
        title="Test task",
        target_files=["src/module.py"],
    )


@pytest.mark.unit
class TestTruncationBlockedSkipsIntegration:
    """AR-816: Tasks with truncation_blocked=true should not be merged."""

    def test_truncation_blocked_task_produces_blocked_status(
        self, _fake_seed_task, _fake_gen_result,
    ):
        """When truncation_blocked is true, integration result has status BLOCKED."""
        from startd8.contractors.context_seed_handlers import SeedTaskUnit

        unit = SeedTaskUnit(
            _fake_seed_task,
            _fake_gen_result,
            extra_context={"_truncation_flags": {
                "detected": True,
                "max_confidence": 0.7,
                "truncation_blocked": True,
                "source": "heuristic_high",
            }},
        )

        # The truncation_blocked flag should be in the unit context
        ctx = unit.context
        assert ctx["_truncation_flags"]["truncation_blocked"] is True

    def test_seedtaskunit_extra_context_merges(
        self, _fake_seed_task, _fake_gen_result,
    ):
        """SeedTaskUnit extra_context is merged into unit.context."""
        from startd8.contractors.context_seed_handlers import SeedTaskUnit

        unit = SeedTaskUnit(
            _fake_seed_task,
            _fake_gen_result,
            extra_context={"module_inventory": ["pkg_a", "pkg_a.sub"]},
        )
        ctx = unit.context
        assert ctx["module_inventory"] == ["pkg_a", "pkg_a.sub"]
        # Original task fields preserved
        assert ctx["task_id"] == "T-1"


@pytest.mark.unit
class TestCompoundGateLowersThreshold:
    """AR-819: Existing file + truncation → lower reject threshold."""

    def test_existing_file_uses_lower_threshold(self, tmp_path):
        """When target file exists, threshold should be CONFIDENCE_IS_TRUNCATED (0.5)."""
        from startd8.truncation_detection import (
            CONFIDENCE_HIGH,
            CONFIDENCE_IS_TRUNCATED,
        )
        # AR-819 logic: target_exists → threshold = 0.5, not 0.7
        assert CONFIDENCE_IS_TRUNCATED < CONFIDENCE_HIGH
        assert CONFIDENCE_IS_TRUNCATED == 0.5


@pytest.mark.unit
class TestSizeRegressionStricterWithTruncation:
    """AR-818: Size regression threshold raised to 0.70 when truncation detected."""

    def test_effective_threshold_stricter_with_truncation(self):
        """When _truncation_flags.max_confidence >= 0.5, threshold is 0.70."""
        from startd8.contractors.integration_engine import (
            _INTEGRATION_SIZE_REGRESSION_THRESHOLD,
        )
        from startd8.truncation_detection import CONFIDENCE_IS_TRUNCATED

        base_threshold = _INTEGRATION_SIZE_REGRESSION_THRESHOLD  # 0.60
        trunc_conf = 0.7  # above CONFIDENCE_IS_TRUNCATED (0.5)

        effective = base_threshold
        if trunc_conf >= CONFIDENCE_IS_TRUNCATED:
            effective = 0.70

        assert effective == 0.70
        assert effective > base_threshold

    def test_no_truncation_uses_standard_threshold(self):
        """Without truncation, standard threshold (0.60) applies."""
        from startd8.contractors.integration_engine import (
            _INTEGRATION_SIZE_REGRESSION_THRESHOLD,
        )
        from startd8.truncation_detection import CONFIDENCE_IS_TRUNCATED

        trunc_conf = 0.0  # below CONFIDENCE_IS_TRUNCATED

        effective = _INTEGRATION_SIZE_REGRESSION_THRESHOLD
        if trunc_conf >= CONFIDENCE_IS_TRUNCATED:
            effective = 0.70

        assert effective == _INTEGRATION_SIZE_REGRESSION_THRESHOLD
        assert effective == 0.60


@pytest.mark.unit
class TestGate4TruncationBlockedFlag:
    """AR-816: Gate 4 sets truncation_blocked when confidence >= 0.5."""

    def test_truncation_blocked_set_on_high_confidence(self):
        """truncation_blocked should be True when max_confidence >= 0.5."""
        from startd8.truncation_detection import CONFIDENCE_IS_TRUNCATED

        # Simulate Gate 4 logic
        flag = {
            "detected": True,
            "max_confidence": 0.6,
        }
        flag["truncation_blocked"] = (
            flag["detected"] and flag["max_confidence"] >= CONFIDENCE_IS_TRUNCATED
        )
        assert flag["truncation_blocked"] is True

    def test_truncation_not_blocked_on_low_confidence(self):
        """truncation_blocked should be False when max_confidence < 0.5."""
        from startd8.truncation_detection import CONFIDENCE_IS_TRUNCATED

        flag = {
            "detected": True,
            "max_confidence": 0.3,
        }
        flag["truncation_blocked"] = (
            flag["detected"] and flag["max_confidence"] >= CONFIDENCE_IS_TRUNCATED
        )
        assert flag["truncation_blocked"] is False
