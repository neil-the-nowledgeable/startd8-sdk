"""
Unit tests for CrossFileImportValidator (Step 11, PF-3).

Tests that:
- Circular import detected -> WARNING severity (req R2-S10)
- Missing FQN reference -> ERROR severity (req R2-S10)
- Graceful degradation when registry is None (PF-5)
- No contribution when no issues found
- dep_graph failure handled gracefully
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from startd8.workflows.builtin.domain_preflight_models import (
    AvailableDeps,
    TaskDomain,
)
from startd8.workflows.builtin.preflight_rules._base import (
    PYTHON_DOMAINS,
    RuleContext,
)
from startd8.workflows.builtin.preflight_rules.cross_file_imports import (
    CrossFileImportValidator,
)


def _make_context(
    target_file: str = "src/foo.py",
    manifest: Any = None,
    manifest_registry: Any = None,
) -> RuleContext:
    """Create a minimal RuleContext for testing."""
    project_root = Path("/tmp/project")
    target_path = project_root / target_file
    return RuleContext(
        target_file=target_file,
        target_path=target_path,
        target_dir=target_path.parent,
        project_root=project_root,
        domain=TaskDomain.PYTHON_SINGLE_MODULE,
        available_deps=AvailableDeps(),
        manifest=manifest,
        manifest_registry=manifest_registry,
    )


class TestCrossFileImportValidatorBasics:
    """Basic validator properties."""

    def test_rule_id(self) -> None:
        v = CrossFileImportValidator()
        assert v.rule_id == "cross_file_import_check"

    def test_domains_are_python(self) -> None:
        v = CrossFileImportValidator()
        assert v.domains == PYTHON_DOMAINS

    def test_priority_is_late(self) -> None:
        v = CrossFileImportValidator()
        assert v.priority == 200


class TestGracefulDegradation:
    """PF-5: Returns None when registry is unavailable."""

    def test_returns_none_when_registry_is_none(self) -> None:
        v = CrossFileImportValidator()
        ctx = _make_context(manifest_registry=None)
        result = v.evaluate(ctx)
        assert result is None

    def test_returns_none_when_dep_graph_raises(self) -> None:
        v = CrossFileImportValidator()
        mock_registry = MagicMock()
        mock_registry.dependency_graph.side_effect = RuntimeError("boom")
        ctx = _make_context(manifest_registry=mock_registry)
        result = v.evaluate(ctx)
        assert result is None


class TestCircularImportDetection:
    """Circular import -> WARNING severity (req R2-S10)."""

    def test_circular_import_detected(self) -> None:
        v = CrossFileImportValidator()
        mock_registry = MagicMock()
        mock_registry.dependency_graph.return_value = {
            "src/foo.py": {"src/bar.py"},
            "src/bar.py": {"src/foo.py"},
        }
        ctx = _make_context(target_file="src/foo.py", manifest_registry=mock_registry)
        result = v.evaluate(ctx)
        assert result is not None
        assert len(result.checks) == 1
        check = result.checks[0]
        assert check.check_name == "circular_import"
        assert check.status == "warn"
        assert "src/foo.py" in check.message
        assert "src/bar.py" in check.message

    def test_no_circular_no_issue(self) -> None:
        v = CrossFileImportValidator()
        mock_registry = MagicMock()
        mock_registry.dependency_graph.return_value = {
            "src/foo.py": {"src/bar.py"},
            "src/bar.py": set(),
        }
        ctx = _make_context(target_file="src/foo.py", manifest_registry=mock_registry)
        result = v.evaluate(ctx)
        assert result is None

    def test_target_not_in_graph(self) -> None:
        v = CrossFileImportValidator()
        mock_registry = MagicMock()
        mock_registry.dependency_graph.return_value = {
            "src/bar.py": {"src/baz.py"},
        }
        ctx = _make_context(target_file="src/foo.py", manifest_registry=mock_registry)
        result = v.evaluate(ctx)
        assert result is None


class TestMissingFQNDetection:
    """Missing FQN reference -> ERROR severity (req R2-S10)."""

    def test_missing_fqn_detected(self) -> None:
        v = CrossFileImportValidator()

        # Build mock import
        mock_import = MagicMock()
        mock_import.is_relative = False
        mock_import.module = "mypackage.utils"
        mock_import.names = ["missing_func"]

        # Build mock manifest with imports + dependencies
        mock_manifest = MagicMock()
        mock_manifest.imports = [mock_import]
        mock_deps = MagicMock()
        mock_deps.internal = ["mypackage.utils"]
        mock_manifest.dependencies = mock_deps

        mock_registry = MagicMock()
        mock_registry.dependency_graph.return_value = {}
        mock_registry.fqn_exists.return_value = False

        ctx = _make_context(
            target_file="src/foo.py",
            manifest=mock_manifest,
            manifest_registry=mock_registry,
        )
        result = v.evaluate(ctx)
        assert result is not None
        assert len(result.checks) == 1
        check = result.checks[0]
        assert check.check_name == "missing_fqn_ref"
        assert check.status == "fail"
        assert "mypackage.utils.missing_func" in check.message

    def test_existing_fqn_no_issue(self) -> None:
        v = CrossFileImportValidator()

        mock_import = MagicMock()
        mock_import.is_relative = False
        mock_import.module = "mypackage.utils"
        mock_import.names = ["existing_func"]

        mock_manifest = MagicMock()
        mock_manifest.imports = [mock_import]
        mock_deps = MagicMock()
        mock_deps.internal = ["mypackage.utils"]
        mock_manifest.dependencies = mock_deps

        mock_registry = MagicMock()
        mock_registry.dependency_graph.return_value = {}
        mock_registry.fqn_exists.return_value = True

        ctx = _make_context(
            manifest=mock_manifest,
            manifest_registry=mock_registry,
        )
        result = v.evaluate(ctx)
        assert result is None

    def test_relative_imports_skipped(self) -> None:
        v = CrossFileImportValidator()

        mock_import = MagicMock()
        mock_import.is_relative = True

        mock_manifest = MagicMock()
        mock_manifest.imports = [mock_import]

        mock_registry = MagicMock()
        mock_registry.dependency_graph.return_value = {}

        ctx = _make_context(
            manifest=mock_manifest,
            manifest_registry=mock_registry,
        )
        result = v.evaluate(ctx)
        assert result is None

    def test_external_imports_not_flagged(self) -> None:
        """External imports (not in dependencies.internal) are not flagged."""
        v = CrossFileImportValidator()

        mock_import = MagicMock()
        mock_import.is_relative = False
        mock_import.module = "requests"
        mock_import.names = ["get"]

        mock_manifest = MagicMock()
        mock_manifest.imports = [mock_import]
        mock_deps = MagicMock()
        mock_deps.internal = ["mypackage.core"]  # "requests" not in internal
        mock_manifest.dependencies = mock_deps

        mock_registry = MagicMock()
        mock_registry.dependency_graph.return_value = {}
        mock_registry.fqn_exists.return_value = False

        ctx = _make_context(
            manifest=mock_manifest,
            manifest_registry=mock_registry,
        )
        result = v.evaluate(ctx)
        assert result is None

    def test_no_manifest_skips_fqn_check(self) -> None:
        """When manifest is None, FQN check is skipped (only circular runs)."""
        v = CrossFileImportValidator()

        mock_registry = MagicMock()
        mock_registry.dependency_graph.return_value = {}

        ctx = _make_context(manifest=None, manifest_registry=mock_registry)
        result = v.evaluate(ctx)
        assert result is None
