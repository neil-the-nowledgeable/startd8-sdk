"""Tests for dashboard_creator.discovery — mixin discovery + toolchain detection."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.dashboard_creator.discovery import (
    MixinContext,
    ToolchainInfo,
    detect_toolchain,
    discover_mixin,
)
from startd8.exceptions import ConfigurationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mixin_dir(tmp_path):
    """Create a valid mixin directory structure."""
    mixin = tmp_path / "startd8-mixin"
    (mixin / "lib").mkdir(parents=True)
    (mixin / "dashboards").mkdir()
    vendor = mixin / "vendor"
    vendor.mkdir()
    # Required files
    (mixin / "config.libsonnet").write_text("{ _config+:: {} }")
    (mixin / "lib" / "panels.libsonnet").write_text("{}")
    (mixin / "lib" / "variables.libsonnet").write_text("{}")
    (mixin / "mixin.libsonnet").write_text("{}")
    # vendor/ must not be empty
    (vendor / "grafonnet").mkdir()
    return mixin


# ---------------------------------------------------------------------------
# discover_mixin
# ---------------------------------------------------------------------------


class TestDiscoverMixin:
    def test_finds_mixin_in_explicit_path(self, mixin_dir):
        ctx = discover_mixin(search_paths=[mixin_dir])
        assert isinstance(ctx, MixinContext)
        assert ctx.mixin_dir == mixin_dir.resolve()
        assert ctx.panels_path.is_file()
        assert ctx.variables_path.is_file()
        assert ctx.config_path.is_file()

    def test_raises_when_not_found(self, tmp_path, monkeypatch):
        # Patch __file__-based SDK root and CWD fallbacks to tmp_path
        # so only the explicit search_paths matter
        monkeypatch.setattr(
            "startd8.dashboard_creator.discovery.Path.cwd",
            staticmethod(lambda: tmp_path),
        )
        monkeypatch.setattr(
            "startd8.dashboard_creator.discovery.__file__",
            str(tmp_path / "fake" / "discovery.py"),
        )
        with pytest.raises(ConfigurationError, match="not found"):
            discover_mixin(search_paths=[tmp_path / "nonexistent"])

    def test_raises_when_vendor_missing(self, mixin_dir):
        import shutil
        shutil.rmtree(mixin_dir / "vendor")
        with pytest.raises(ConfigurationError, match="jb install"):
            discover_mixin(search_paths=[mixin_dir])

    def test_raises_when_vendor_empty(self, mixin_dir):
        import shutil
        shutil.rmtree(mixin_dir / "vendor")
        (mixin_dir / "vendor").mkdir()
        with pytest.raises(ConfigurationError, match="jb install"):
            discover_mixin(search_paths=[mixin_dir])

    def test_raises_when_required_files_missing(self, mixin_dir):
        (mixin_dir / "lib" / "panels.libsonnet").unlink()
        with pytest.raises(ConfigurationError, match="Missing files"):
            discover_mixin(search_paths=[mixin_dir])

    def test_mixin_context_paths(self, mixin_dir):
        ctx = discover_mixin(search_paths=[mixin_dir])
        assert ctx.dashboards_dir == mixin_dir.resolve() / "dashboards"
        assert ctx.vendor_dir == mixin_dir.resolve() / "vendor"
        assert ctx.mixin_libsonnet == mixin_dir.resolve() / "mixin.libsonnet"


# ---------------------------------------------------------------------------
# detect_toolchain
# ---------------------------------------------------------------------------


class TestDetectToolchain:
    def test_detects_binary(self):
        with patch("shutil.which", return_value="/usr/local/bin/jsonnet"):
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="Jsonnet commandline interpreter v0.20.0"
                ),
            ):
                info = detect_toolchain()
                assert info.backend == "binary"
                assert info.binary_path == "/usr/local/bin/jsonnet"
                assert "0.20.0" in info.version

    def test_falls_back_to_python(self):
        mock_gojsonnet = MagicMock()
        mock_gojsonnet.__version__ = "0.20.0"
        with patch("shutil.which", return_value=None):
            with patch.dict("sys.modules", {"_gojsonnet": mock_gojsonnet}):
                info = detect_toolchain()
                assert info.backend == "python"

    def test_raises_when_neither_available(self):
        with patch("shutil.which", return_value=None):
            with patch.dict("sys.modules", {"_gojsonnet": None}):
                with pytest.raises(ConfigurationError, match="No Jsonnet toolchain"):
                    detect_toolchain()

    def test_binary_version_timeout(self):
        with patch("shutil.which", return_value="/usr/local/bin/jsonnet"):
            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("jsonnet", 5),
            ):
                info = detect_toolchain()
                assert info.backend == "binary"
                assert info.version == "unknown"
