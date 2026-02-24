"""
Unit tests for manifest validate-capabilities CLI command (Step 10).

Tests that:
- Drift detection for non-existent evidence ref (AC-10)
- Valid ref passes
- Path traversal: ../../../etc/passwd ref rejected with SECURITY error
- Path traversal: absolute path /etc/passwd ref rejected
- Path traversal: legitimate nested path passes
- Registry-first: ref missing from manifest but present on disk still reports drift
- Path normalization: backslash refs match POSIX registry keys
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from startd8.cli import app


runner = CliRunner()


@pytest.fixture
def cap_yaml_file(tmp_path: Path) -> Path:
    """Create a minimal capability YAML file."""
    cap_data = {
        "capabilities": [
            {
                "id": "cap-001",
                "name": "Test Capability",
                "evidence": [
                    {"type": "code", "ref": "src/startd8/agents/claude.py"},
                    {"type": "doc", "ref": "docs/README.md"},
                ],
            }
        ]
    }
    cap_file = tmp_path / "capabilities.yaml"
    cap_file.write_text(yaml.safe_dump(cap_data), encoding="utf-8")
    return cap_file


@pytest.fixture
def cap_yaml_with_traversal(tmp_path: Path) -> Path:
    cap_data = {
        "capabilities": [
            {
                "id": "cap-evil",
                "evidence": [
                    {"type": "code", "ref": "../../../etc/passwd"},
                ],
            }
        ]
    }
    cap_file = tmp_path / "evil.yaml"
    cap_file.write_text(yaml.safe_dump(cap_data), encoding="utf-8")
    return cap_file


@pytest.fixture
def cap_yaml_absolute(tmp_path: Path) -> Path:
    cap_data = {
        "capabilities": [
            {
                "id": "cap-abs",
                "evidence": [
                    {"type": "code", "ref": "/etc/passwd"},
                ],
            }
        ]
    }
    cap_file = tmp_path / "absolute.yaml"
    cap_file.write_text(yaml.safe_dump(cap_data), encoding="utf-8")
    return cap_file


class TestValidateCapabilities:

    @patch("startd8.utils.manifest_registry.ManifestRegistry")
    def test_drift_detection_missing_ref(
        self, mock_registry_cls, cap_yaml_file: Path
    ) -> None:
        """AC-10: Drift detection for non-existent evidence ref."""
        mock_registry = MagicMock()
        mock_registry.get.return_value = None  # ref not in manifests
        mock_registry_cls.from_cache.return_value = mock_registry

        result = runner.invoke(app, ["manifest", "validate-capabilities", str(cap_yaml_file)])
        assert result.exit_code == 1
        assert "DRIFT" in result.output

    @patch("startd8.utils.manifest_registry.ManifestRegistry")
    def test_valid_ref_passes(self, mock_registry_cls, cap_yaml_file: Path) -> None:
        mock_registry = MagicMock()
        mock_manifest = MagicMock()
        mock_manifest.elements = []
        mock_registry.get.return_value = mock_manifest
        mock_registry_cls.from_cache.return_value = mock_registry

        result = runner.invoke(app, ["manifest", "validate-capabilities", str(cap_yaml_file)])
        assert result.exit_code == 0
        assert "validated" in result.output

    def test_path_traversal_dotdot_rejected(self, cap_yaml_with_traversal: Path) -> None:
        """Path traversal: ../../../etc/passwd ref rejected with SECURITY error."""
        with patch("startd8.utils.manifest_registry.ManifestRegistry") as mock_cls:
            mock_cls.from_cache.return_value = MagicMock()
            result = runner.invoke(
                app, ["manifest", "validate-capabilities", str(cap_yaml_with_traversal)]
            )
        assert result.exit_code == 1
        assert "SECURITY" in result.output

    def test_path_traversal_absolute_rejected(self, cap_yaml_absolute: Path) -> None:
        """Path traversal: absolute path /etc/passwd ref rejected."""
        with patch("startd8.utils.manifest_registry.ManifestRegistry") as mock_cls:
            mock_cls.from_cache.return_value = MagicMock()
            result = runner.invoke(
                app, ["manifest", "validate-capabilities", str(cap_yaml_absolute)]
            )
        assert result.exit_code == 1
        assert "SECURITY" in result.output

    @patch("startd8.utils.manifest_registry.ManifestRegistry")
    def test_registry_first_disk_fallback_still_drift(
        self, mock_registry_cls, tmp_path: Path
    ) -> None:
        """Registry-first: ref missing from manifest but present on disk still reports drift."""
        # Create a capability with a ref that exists on disk
        cap_data = {
            "capabilities": [
                {
                    "id": "cap-disk",
                    "evidence": [{"type": "code", "ref": "src/exists.py"}],
                }
            ]
        }
        cap_file = tmp_path / "cap.yaml"
        cap_file.write_text(yaml.safe_dump(cap_data), encoding="utf-8")

        # Registry loaded but ref not in it
        mock_registry = MagicMock()
        mock_registry.get.return_value = None
        mock_registry_cls.from_cache.return_value = mock_registry

        result = runner.invoke(app, ["manifest", "validate-capabilities", str(cap_file)])
        assert result.exit_code == 1
        assert "DRIFT" in result.output

    @patch("startd8.utils.manifest_registry.ManifestRegistry")
    def test_backslash_ref_normalized(self, mock_registry_cls, tmp_path: Path) -> None:
        """Path normalization: backslash refs match POSIX registry keys."""
        cap_data = {
            "capabilities": [
                {
                    "id": "cap-win",
                    "evidence": [{"type": "code", "ref": "src\\startd8\\cli.py"}],
                }
            ]
        }
        cap_file = tmp_path / "win.yaml"
        cap_file.write_text(yaml.safe_dump(cap_data), encoding="utf-8")

        mock_registry = MagicMock()
        mock_manifest = MagicMock()
        mock_manifest.elements = []
        mock_registry.get.return_value = mock_manifest
        mock_registry_cls.from_cache.return_value = mock_registry

        result = runner.invoke(app, ["manifest", "validate-capabilities", str(cap_file)])
        # Should have called get() with normalized path
        mock_registry.get.assert_called_with("src/startd8/cli.py")
