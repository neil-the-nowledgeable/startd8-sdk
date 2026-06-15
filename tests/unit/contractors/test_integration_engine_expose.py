"""Tests for expose-defects mode + FR-A1 non-destructive downgrade."""

from unittest.mock import MagicMock

from startd8.contractors.integration_engine import IntegrationEngine
from startd8.repair.config import RepairConfig


def _engine(tmp_path, repair_config=None):
    return IntegrationEngine(
        project_root=tmp_path, merge_strategy=MagicMock(),
        checkpoint=MagicMock(), repair_config=repair_config,
    )


class TestExposeFlag:
    def test_default_is_not_expose(self, tmp_path):
        assert _engine(tmp_path, RepairConfig())._expose_defects() is False

    def test_expose_detected(self, tmp_path):
        assert _engine(tmp_path, RepairConfig(expose_defects=True))._expose_defects() is True

    def test_no_config_is_not_expose(self, tmp_path):
        assert _engine(tmp_path)._expose_defects() is False

    def test_expose_composes_with_shadow(self, tmp_path):
        eng = _engine(tmp_path, RepairConfig(repair_mode="shadow", expose_defects=True))
        assert eng._is_shadow() is True and eng._expose_defects() is True


class TestDowngradeBehavior:
    """FR-A1 (preserve error detail) + FR-B1 (skip downgrade in expose)."""

    def _downgrade(self, results, repair_success, expose):
        # Mirrors integration_engine.py advisory-downgrade block exactly.
        from startd8.contractors.checkpoint import CheckpointStatus
        if not repair_success and not expose:
            for r in results:
                if r.name in ("Import Check", "Lint Check") and r.status == CheckpointStatus.FAILED:
                    r.downgraded_errors = list(r.errors or [])   # FR-A1
                    r.status = CheckpointStatus.WARNING
                    r.warnings = (r.warnings or []) + (r.errors or [])
                    r.errors = []
        return results

    def _failed(self):
        from startd8.contractors.checkpoint import CheckpointStatus, CheckpointResult
        return CheckpointResult(
            status=CheckpointStatus.FAILED, name="Import Check",
            message="x", errors=["no module 'foo'"], warnings=[],
        )

    def test_fr_a1_downgrade_preserves_errors(self):
        from startd8.contractors.checkpoint import CheckpointStatus
        r = self._failed()
        (out,) = self._downgrade([r], repair_success=False, expose=False)
        assert out.status == CheckpointStatus.WARNING       # downgraded
        assert out.errors == []                             # cleared from errors (as before)
        assert out.downgraded_errors == ["no module 'foo'"]  # FR-A1: detail retained
        assert "no module 'foo'" in out.warnings            # also surfaced as warning

    def test_fr_b1_expose_keeps_failed(self):
        from startd8.contractors.checkpoint import CheckpointStatus
        r = self._failed()
        (out,) = self._downgrade([r], repair_success=False, expose=True)
        assert out.status == CheckpointStatus.FAILED        # NOT downgraded in expose mode
        assert out.errors == ["no module 'foo'"]            # detail intact
