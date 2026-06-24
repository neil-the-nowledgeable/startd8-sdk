"""Gated live oracle self-validation for the cartservice suite (Track-2 expansion — STATEFUL C#).

Mirrors ``test_catalog_e2e_go.py`` / ``test_email_e2e_python.py`` but for the first STATEFUL leaf in
its canonical language (C#/.NET): co-locate demo.proto, ``dotnet publish`` the reference CartService
to ``./.bin/server.dll`` (Grpc.Tools codegens the Hipstershop stubs from the proto at build time),
launch it, and score ``run_cart_suite`` over loopback.

  - ``cart_reference`` (correct, in-memory per-user store)  → coverage 1.00 (proves the oracle).
  - ``cart_broken``    (GetCart always empty)               → the STATEFUL cases fail; the
    unknown-user case still passes (proves per-case statefulness discrimination).

The first block drives the published DLL directly; the second proves the dedicated
``run_behavioral_cell`` leaf path (registration + C# proto co-location + publish + dotnet serve)
end-to-end through the real sandbox.

Gated on ``dotnet`` on PATH; skips cleanly otherwise. Set ``STARTD8_RUN_INTEGRATION=1`` to run.
NOTE: ``dotnet publish`` performs a NuGet restore — needs network on a COLD cache (cached thereafter).
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import execute
from startd8.benchmark_matrix.behavioral.cart_suite import run_cart_suite

_FIXTURES = Path(__file__).parent / "fixtures"
_REFERENCE = _FIXTURES / "cart_reference"
_BROKEN = _FIXTURES / "cart_broken"
_PROTO = Path(execute.__file__).parent / "demo.proto"

pytestmark = [
    pytest.mark.skipif(os.environ.get("STARTD8_RUN_INTEGRATION") != "1",
                       reason="gated: set STARTD8_RUN_INTEGRATION=1"),
    pytest.mark.skipif(shutil.which("dotnet") is None, reason="dotnet not on PATH"),
]


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _publish_cart(fixture_dir: Path, workdir: Path) -> Path:
    """Replicate the harness C# provisioning: stage the project + co-located demo.proto into the
    service dir, then ``dotnet publish -o .bin`` → ./.bin/server.dll (Grpc.Tools codegens the stubs)."""
    svc_dir = workdir / "src" / "cartservice"
    svc_dir.mkdir(parents=True, exist_ok=True)
    for f in fixture_dir.iterdir():
        shutil.copy(f, svc_dir / f.name)
    shutil.copy(_PROTO, svc_dir / "demo.proto")
    proc = subprocess.run(
        ["dotnet", "publish", "-c", "Release", "-o", ".bin", "--nologo"],
        cwd=str(svc_dir), capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, f"dotnet publish failed:\n{proc.stdout}\n{proc.stderr}"
    dll = svc_dir / ".bin" / "server.dll"
    assert dll.is_file(), f"no server.dll under {svc_dir/'.bin'}"
    return dll


def _run_and_score(dll: Path):
    port = _free_port()
    env = {**os.environ, "PORT": str(port), "ASPNETCORE_URLS": f"http://127.0.0.1:{port}"}
    proc = subprocess.Popen(
        ["dotnet", str(dll)], env=env, cwd=str(dll.parent.parent),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        ch = grpc.insecure_channel(f"127.0.0.1:{port}")
        grpc.channel_ready_future(ch).result(timeout=30.0)
        ch.close()
        return run_cart_suite(port)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_reference_cart_scores_full_coverage(tmp_path):
    dll = _publish_cart(_REFERENCE, tmp_path)
    suite = _run_and_score(dll)
    failing = [r.__dict__ for r in suite.results if not r.passed]
    assert suite.coverage == 1.0, f"coverage={suite.coverage}; failing={failing}"


def test_broken_cart_fails_stateful_cases(tmp_path):
    dll = _publish_cart(_BROKEN, tmp_path)
    suite = _run_and_score(dll)
    failed = {r.name for r in suite.results if not r.passed}
    # GetCart always empty → every stateful case fails; the unknown-user case (expects empty) passes.
    assert failed == {
        "add_then_get_reflects_item",
        "add_twice_accumulates",
        "add_distinct_products",
    }, [r.__dict__ for r in suite.results]
    assert suite.coverage == 2 / 5


# --------------------------------------------------------------------------- via run_behavioral_cell
# Prove the dedicated leaf path: registration + C# proto co-location + dotnet publish + dotnet serve
# drive the SAME published DLL through the real sandbox, scored from the live stateful RPC responses.
_SEED = {
    "service_metadata": {"language": "csharp"},
    "startup": {
        "cmd": ["sh", "-c", "cd src/cartservice && exec dotnet ./.bin/server.dll"],
        "port_env": "PORT",
        "readiness": "tcp",
    },
}
_TARGETS = ["src/cartservice/CartService.cs"]


def _stage_source(fixture_dir: Path, workdir: Path) -> None:
    """Drop the fixture's project where the branch's own provisioning expects it (it publishes).
    The harness itself co-locates demo.proto (execute.py) — we do NOT pre-stage it."""
    svc_dir = workdir / "src" / "cartservice"
    svc_dir.mkdir(parents=True, exist_ok=True)
    for f in fixture_dir.iterdir():
        shutil.copy(f, svc_dir / f.name)


def test_reference_cart_full_coverage_via_run_behavioral_cell(tmp_path):
    _stage_source(_REFERENCE, tmp_path)
    res = execute.run_behavioral_cell(_SEED, tmp_path, "cartservice", _TARGETS)
    assert res.has_suite and not res.degraded and not res.model_fault, res.provenance
    assert res.functional == 1.0, res.provenance.get("suite")


def test_broken_cart_real_miss_via_run_behavioral_cell(tmp_path):
    _stage_source(_BROKEN, tmp_path)
    res = execute.run_behavioral_cell(_SEED, tmp_path, "cartservice", _TARGETS)
    assert not res.degraded and not res.model_fault, res.provenance
    assert res.functional == 2 / 5, res.provenance.get("suite")
