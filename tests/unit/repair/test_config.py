"""Tests for startd8.repair.config."""

import dataclasses
from pathlib import Path

import pytest

from startd8.repair.config import RepairConfig


class TestRepairConfig:
    def test_defaults(self):
        c = RepairConfig()
        assert c.repair_enabled is True
        assert c.repairable_categories == frozenset({"syntax", "import", "lint", "semantic", "security", "convention"})
        assert c.pre_checkpoint_repair is False
        assert c.staging_root is None
        assert c.circuit_breaker_threshold == 3
        assert c.per_step_timeout_s == 2.0
        assert c.total_timeout_s == 5.0
        assert c.delta_threshold == 0.5
        assert c.staging_retention_hours == 24

    def test_frozen_immutability(self):
        c = RepairConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.repair_enabled = False  # type: ignore[misc]

    def test_field_overrides_via_replace(self):
        c = RepairConfig()
        c2 = dataclasses.replace(c, repair_enabled=False, total_timeout_s=10.0)
        assert c2.repair_enabled is False
        assert c2.total_timeout_s == 10.0
        # Original unchanged
        assert c.repair_enabled is True

    def test_custom_staging_root(self):
        c = RepairConfig(staging_root=Path("/tmp/repair"))
        assert c.staging_root == Path("/tmp/repair")

    def test_custom_categories(self):
        c = RepairConfig(repairable_categories=frozenset({"syntax"}))
        assert "syntax" in c.repairable_categories
        assert "import" not in c.repairable_categories
