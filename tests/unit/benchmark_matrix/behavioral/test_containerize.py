"""Unit tests for the R3-M0 container builder (fleet.containerize) — NO real docker.

Exercises command construction + the per-language build-context staging + degrade-honesty via the
`build=False` (command-only) path and an injected fake runner. The live docker build/boot/1-RPC
validation is a separate gated path the orchestrator runs (see docs/design/round3-full-app/PLAN.md M0).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from startd8.benchmark_matrix.fleet import containerize as C

pytestmark = pytest.mark.unit

_FIX = Path(__file__).resolve().parent / "fixtures"


def _go_workdir(tmp_path: Path) -> Path:
    ref = _FIX / "catalog_reference"
    shutil.copy(ref / "main.go", tmp_path / "main.go")
    shutil.copy(ref / "go.mod", tmp_path / "go.mod")
    return tmp_path


def test_go_build_command_constructed(tmp_path):
    wd = _go_workdir(tmp_path)
    res = C.build_service_image("productcatalogservice", wd, "go", target_files=["main.go"], build=False)
    assert res.build_cmd[:2] == ["docker", "build"]
    assert "-t" in res.build_cmd and "r3/productcatalogservice:go" in res.build_cmd
    assert res.tag == "r3/productcatalogservice:go"
    assert res.language == "go"
    assert "build=False" in res.skipped_reason  # command-only, no docker executed
    assert (wd / "Dockerfile").is_file()


def test_go_stub_replace_is_relative_for_container(tmp_path):
    """CONTAINERIZE FIX: the go.mod stub `replace` must be RELATIVE (./.gostubs), not an absolute
    host path — else `go build` inside the container can't find the local stub module."""
    wd = _go_workdir(tmp_path)
    C.build_service_image("productcatalogservice", wd, "go", target_files=["main.go"], build=False)
    gomod = (wd / "go.mod").read_text()
    assert "=> ./.gostubs" in gomod, gomod
    # no absolute host path leaked into the build context
    assert "/private/" not in gomod and "/Users/" not in gomod
    assert (wd / ".gostubs" / "go.mod").is_file()  # the local stub module exists


def test_docker_absent_degrades_honestly(tmp_path, monkeypatch):
    wd = _go_workdir(tmp_path)
    monkeypatch.setattr(C, "docker_available", lambda: False)
    res = C.build_service_image("productcatalogservice", wd, "go", target_files=["main.go"], build=True)
    assert not res.ok
    assert "docker" in res.skipped_reason.lower()


def test_fake_runner_build_ok(tmp_path):
    """With build=True + a fake runner returning 0, the result is ok (no real docker)."""
    wd = _go_workdir(tmp_path)

    class _FakeProc:
        returncode = 0
        stdout = "built"
        stderr = ""

    calls = []

    def fake_runner(cmd, **kw):
        calls.append(cmd)
        return _FakeProc()

    res = C.build_service_image(
        "productcatalogservice", wd, "go", target_files=["main.go"], build=True, runner=fake_runner
    )
    assert res.ok and res.returncode == 0
    assert calls and calls[0][:2] == ["docker", "build"]


def test_boot_and_probe_command_only(tmp_path):
    bp = C.boot_and_probe("r3/productcatalogservice:go", "productcatalogservice", "go", host_port=18080)
    assert bp.run_cmd[:3] == ["docker", "run", "--rm"]
    assert any("127.0.0.1:18080:" in a for a in bp.run_cmd)
    assert bp.probe_suite  # a behavioral probe suite is mapped for this service
    assert "run=False" in bp.skipped_reason  # command-only by default


def test_unsupported_language_raises(tmp_path):
    wd = _go_workdir(tmp_path)
    with pytest.raises(ValueError):
        C.build_service_image("adservice", wd, "java", target_files=["Main.java"], build=False)
