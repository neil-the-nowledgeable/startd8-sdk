"""
Unit tests for plan ingestion manifest enrichment (Step 6).

Tests that:
- API surface uses manifest counts when available (PI-1, AC-4)
- Falls back to feature_count * 8 when None (PI-5)
- Dependency ordering uses manifest graph (PI-2)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest


@dataclass
class FakeFeature:
    """Minimal feature stub for testing."""
    feature_id: str = "F-001"
    name: str = "Test Feature"
    description: str = "A test feature"
    dependencies: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


@dataclass
class FakeParsedPlan:
    """Minimal parsed plan stub for testing."""
    title: str = "Test Plan"
    goals: list[str] = field(default_factory=list)
    features: list[FakeFeature] = field(default_factory=list)


class TestHeuristicAssessComplexity:

    def _get_assess_fn(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            _heuristic_assess_complexity,
        )
        return _heuristic_assess_complexity

    def test_without_manifest_uses_feature_count(self) -> None:
        """PI-5: Falls back to feature_count * 8 when manifest is None."""
        assess = self._get_assess_fn()
        plan = FakeParsedPlan(
            features=[
                FakeFeature(feature_id="F-001", target_files=["src/a.py"]),
                FakeFeature(feature_id="F-002", target_files=["src/b.py"]),
            ]
        )
        result = assess(plan, threshold=50, force_route=None)
        # With 2 features and no manifest: api_surface = min(100, max(10, 2*8)) = 16
        assert result.api_surface == 16

    def test_with_manifest_uses_element_count(self) -> None:
        """PI-1: api_surface uses manifest public_element_count when available."""
        assess = self._get_assess_fn()
        plan = FakeParsedPlan(
            features=[
                FakeFeature(feature_id="F-001", target_files=["src/a.py"]),
                FakeFeature(feature_id="F-002", target_files=["src/b.py"]),
            ]
        )

        mock_registry = MagicMock()
        # Simulate 15 public elements per file
        mock_registry.public_element_count.return_value = 15
        mock_registry.dependency_graph.return_value = {}

        result = assess(plan, threshold=50, force_route=None, manifest_registry=mock_registry)
        # With manifest: api_surface = min(100, max(10, 15+15)) = 30
        assert result.api_surface == 30

    def test_with_manifest_uses_dep_graph(self) -> None:
        """PI-2: cross_file_deps uses manifest dependency_graph."""
        assess = self._get_assess_fn()
        plan = FakeParsedPlan(
            features=[
                FakeFeature(
                    feature_id="F-001",
                    target_files=["src/a.py"],
                    dependencies=["src/b.py"],
                ),
            ]
        )

        mock_registry = MagicMock()
        mock_registry.public_element_count.return_value = 5
        # Simulate 3 dependencies for src/a.py
        mock_registry.dependency_graph.return_value = {
            "src/a.py": {"src/b.py", "src/c.py", "src/d.py"},
        }

        result = assess(plan, threshold=50, force_route=None, manifest_registry=mock_registry)
        # cross_file_deps normalized to 0-100: min(100, max(0, 3 * 10)) = 30
        assert result.cross_file_deps == 30

    def test_manifest_failure_falls_back(self) -> None:
        """If manifest raises, fall back to heuristic."""
        assess = self._get_assess_fn()
        plan = FakeParsedPlan(
            features=[
                FakeFeature(
                    feature_id="F-001",
                    target_files=["src/a.py"],
                    dependencies=["dep1"],
                ),
            ]
        )

        mock_registry = MagicMock()
        mock_registry.dependency_graph.side_effect = RuntimeError("boom")
        mock_registry.public_element_count.side_effect = RuntimeError("boom")

        result = assess(plan, threshold=50, force_route=None, manifest_registry=mock_registry)
        # Should not crash — falls back to heuristic
        # feature_count normalized to 0-100: min(100, max(10, 1 * 7)) = 10
        assert result.feature_count == 10
        # cross_file_deps normalized to 0-100: min(100, max(0, 1 * 10)) = 10
        assert result.cross_file_deps == 10
