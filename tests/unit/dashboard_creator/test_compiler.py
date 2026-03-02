"""Tests for dashboard_creator.compiler — Jsonnet compilation."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.dashboard_creator.compiler import (
    CompilationError,
    CompilationResult,
    compile_jsonnet,
    compile_jsonnet_string,
)
from startd8.dashboard_creator.discovery import MixinContext, ToolchainInfo


@pytest.fixture
def mixin_ctx(tmp_path):
    mixin = tmp_path / "startd8-mixin"
    (mixin / "lib").mkdir(parents=True)
    (mixin / "dashboards").mkdir()
    (mixin / "vendor").mkdir()
    return MixinContext(
        mixin_dir=mixin,
        panels_path=mixin / "lib" / "panels.libsonnet",
        variables_path=mixin / "lib" / "variables.libsonnet",
        config_path=mixin / "config.libsonnet",
        dashboards_dir=mixin / "dashboards",
        vendor_dir=mixin / "vendor",
        mixin_libsonnet=mixin / "mixin.libsonnet",
    )


@pytest.fixture
def binary_toolchain():
    return ToolchainInfo(
        backend="binary", version="v0.20.0", binary_path="/usr/local/bin/jsonnet"
    )


@pytest.fixture
def python_toolchain():
    return ToolchainInfo(backend="python", version="0.20.0")


class TestCompileJsonnetBinary:
    def test_invokes_subprocess_with_j_flags(self, mixin_ctx, binary_toolchain, tmp_path):
        source = tmp_path / "test.libsonnet"
        source.write_text("{}")
        valid_json = '{"result": true}\n'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=valid_json, stderr=""
            )
            result = compile_jsonnet(source, mixin_ctx, binary_toolchain)

            args = mock_run.call_args[0][0]
            assert "-J" in args
            assert str(mixin_ctx.vendor_dir) in args
            assert result.backend == "binary"
            assert result.json_str == valid_json

    def test_compilation_error(self, mixin_ctx, binary_toolchain, tmp_path):
        source = tmp_path / "bad.libsonnet"
        source.write_text("invalid jsonnet")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="STATIC ERROR: line 1"
            )
            with pytest.raises(CompilationError, match="STATIC ERROR"):
                compile_jsonnet(source, mixin_ctx, binary_toolchain)

    def test_timeout_raises(self, mixin_ctx, binary_toolchain, tmp_path):
        source = tmp_path / "slow.libsonnet"
        source.write_text("{}")

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("jsonnet", 30)):
            with pytest.raises(TimeoutError, match="timed out"):
                compile_jsonnet(source, mixin_ctx, binary_toolchain, timeout_seconds=30)

    def test_result_includes_duration(self, mixin_ctx, binary_toolchain, tmp_path):
        source = tmp_path / "test.libsonnet"
        source.write_text("{}")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedResult = subprocess.CompletedProcess(
                args=[], returncode=0, stdout='{"ok": true}\n', stderr=""
            )
            result = compile_jsonnet(source, mixin_ctx, binary_toolchain)
            assert isinstance(result.duration_ms, int)
            assert result.duration_ms >= 0


class TestCompileJsonnetPython:
    def test_calls_evaluate_file(self, mixin_ctx, python_toolchain, tmp_path):
        source = tmp_path / "test.libsonnet"
        source.write_text("{}")

        mock_gojsonnet = MagicMock()
        mock_gojsonnet.evaluate_file.return_value = '{"result": true}\n'

        with patch.dict("sys.modules", {"_gojsonnet": mock_gojsonnet}):
            result = compile_jsonnet(source, mixin_ctx, python_toolchain)
            assert result.backend == "python"
            mock_gojsonnet.evaluate_file.assert_called_once()
            call_kwargs = mock_gojsonnet.evaluate_file.call_args
            assert str(source) in call_kwargs[0]

    def test_runtime_error_becomes_compilation_error(
        self, mixin_ctx, python_toolchain, tmp_path
    ):
        source = tmp_path / "bad.libsonnet"
        source.write_text("bad")

        mock_gojsonnet = MagicMock()
        mock_gojsonnet.evaluate_file.side_effect = RuntimeError("parse error")

        with patch.dict("sys.modules", {"_gojsonnet": mock_gojsonnet}):
            with pytest.raises(CompilationError, match="parse error"):
                compile_jsonnet(source, mixin_ctx, python_toolchain)


class TestCompileJsonnetString:
    def test_writes_tempfile_and_compiles(self, mixin_ctx, binary_toolchain):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout='{"x": 1}\n', stderr=""
            )
            result = compile_jsonnet_string("{}", mixin_ctx, binary_toolchain)
            assert result.json_str == '{"x": 1}\n'

    def test_output_is_valid_json(self, mixin_ctx, binary_toolchain):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout='{"valid": true}', stderr=""
            )
            result = compile_jsonnet_string("{}", mixin_ctx, binary_toolchain)
            parsed = json.loads(result.json_str)
            assert parsed["valid"] is True
