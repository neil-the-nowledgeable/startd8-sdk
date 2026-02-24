"""
Unit tests for preflight manifest enrichment (Step 7).

Tests that:
- RuleContext accepts manifest=None (backward compat, AC-8)
- RuleContext accepts mock FileManifest
- RuleContext accepts manifest_registry
- Validators access ctx.manifest without error
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from startd8.workflows.builtin.preflight_rules._base import RuleContext
from startd8.workflows.builtin.domain_preflight_models import AvailableDeps, TaskDomain


class TestRuleContextManifestFields:

    def _make_ctx(self, manifest=None, manifest_registry=None) -> RuleContext:
        return RuleContext(
            target_file="src/foo.py",
            target_path=Path("/tmp/project/src/foo.py"),
            target_dir=Path("/tmp/project/src"),
            project_root=Path("/tmp/project"),
            domain=TaskDomain.PYTHON_SINGLE_MODULE,
            available_deps=AvailableDeps(),
            manifest=manifest,
            manifest_registry=manifest_registry,
        )

    def test_manifest_none_backward_compat(self) -> None:
        """AC-8: RuleContext with manifest=None should work normally."""
        ctx = self._make_ctx()
        assert ctx.manifest is None
        assert ctx.manifest_registry is None

    def test_manifest_with_mock_file_manifest(self) -> None:
        mock_manifest = MagicMock()
        mock_manifest.elements = []
        ctx = self._make_ctx(manifest=mock_manifest)
        assert ctx.manifest is mock_manifest
        assert ctx.manifest.elements == []

    def test_manifest_registry_accessible(self) -> None:
        mock_registry = MagicMock()
        mock_registry.fqn_exists.return_value = True
        ctx = self._make_ctx(manifest_registry=mock_registry)
        assert ctx.manifest_registry.fqn_exists("foo.bar") is True

    def test_frozen_dataclass_with_manifest(self) -> None:
        """Frozen dataclass should accept manifest fields."""
        ctx = self._make_ctx(manifest=MagicMock(), manifest_registry=MagicMock())
        # Should not raise — frozen dataclass supports init
        assert ctx.manifest is not None
        assert ctx.manifest_registry is not None

    def test_default_fields_omitted(self) -> None:
        """RuleContext without manifest fields should work (backward compat)."""
        ctx = RuleContext(
            target_file="src/foo.py",
            target_path=Path("/tmp/project/src/foo.py"),
            target_dir=Path("/tmp/project/src"),
            project_root=Path("/tmp/project"),
            domain=TaskDomain.PYTHON_SINGLE_MODULE,
            available_deps=AvailableDeps(),
        )
        assert ctx.manifest is None
        assert ctx.manifest_registry is None
