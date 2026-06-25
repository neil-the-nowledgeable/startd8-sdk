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


def _python_workdir(tmp_path: Path) -> Path:
    shutil.copy(_FIX / "email_reference" / "server.py", tmp_path / "server.py")
    return tmp_path


def _node_workdir(tmp_path: Path) -> Path:
    ref = _FIX / "payment_reference"
    shutil.copy(ref / "server.js", tmp_path / "server.js")
    shutil.copy(ref / "package.json", tmp_path / "package.json")
    return tmp_path


def _csharp_workdir(tmp_path: Path) -> Path:
    ref = _FIX / "cart_reference"
    shutil.copy(ref / "Program.cs", tmp_path / "Program.cs")
    shutil.copy(ref / "cartservice.csproj", tmp_path / "cartservice.csproj")
    return tmp_path


def _pip_line(dockerfile_text: str) -> str:
    return next(l for l in dockerfile_text.splitlines() if l.startswith("RUN pip install"))


# The Node closure (node_runtime/node_modules) is gitignored — present only after vendor.sh runs.
_NODE_VENDORED = (
    Path(C.__file__).resolve().parents[1]
    / "behavioral" / "node_runtime" / "node_modules" / "@grpc"
).is_dir()


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


def test_python_build_command_constructed(tmp_path):
    wd = _python_workdir(tmp_path)
    res = C.build_service_image("emailservice", wd, "python", target_files=["server.py"], build=False)
    assert res.tag == "r3/emailservice:python"
    assert res.language == "python"
    assert (wd / "Dockerfile").is_file()
    df = (wd / "Dockerfile").read_text()
    assert 'ENTRYPOINT ["python3", "server.py"]' in df


def test_python_extra_pip_appended_to_dockerfile(tmp_path):
    """CONTAINERIZE FIX: per-service Python deps (``extra_pip``) must be appended to the curated
    baseline on the image's pip-install line. emailservice renders its confirmation from a jinja2
    template, so without ``jinja2`` the server imports-crashes on startup — the container boots, then
    exits, and the probe sees coverage 0.0 (build/boot 'ok', RPC dead)."""
    wd = _python_workdir(tmp_path)
    C.build_service_image("emailservice", wd, "python", target_files=["server.py"],
                          build=False, extra_pip=["jinja2"])
    pip_line = _pip_line((wd / "Dockerfile").read_text())
    assert "grpcio" in pip_line and "protobuf" in pip_line  # baseline gRPC runtime preserved
    assert "jinja2" in pip_line                              # per-service dep appended


def test_python_no_extra_pip_stays_lean(tmp_path):
    """Per-service, NOT baked into the baseline: a Python leaf without extra deps must not carry
    jinja2 — else every Python image bloats (recommendationservice doesn't render templates)."""
    wd = _python_workdir(tmp_path)
    C.build_service_image("recommendationservice", wd, "python", target_files=["server.py"], build=False)
    assert "jinja2" not in _pip_line((wd / "Dockerfile").read_text())


def test_node_build_command_constructed(tmp_path):
    """The Node Dockerfile is rendered regardless of vendoring (ENTRYPOINT + tag); the offline
    closure is staged by _stage_node_context, so the template carries NO npm install step."""
    wd = _node_workdir(tmp_path)
    res = C.build_service_image("paymentservice", wd, "node", target_files=["server.js"], build=False)
    assert res.tag == "r3/paymentservice:node"
    assert res.language == "node"
    df = (wd / "Dockerfile").read_text()
    assert 'ENTRYPOINT ["node", "server.js"]' in df
    # vendored closure is authoritative — no npm in any actual build step (RUN line); comments may mention it
    run_lines = [l for l in df.splitlines() if l.startswith("RUN")]
    assert not any("npm" in l for l in run_lines)


def test_node_unvendored_degrades_honestly(tmp_path, monkeypatch):
    """When the node_runtime closure isn't vendored, the stager must degrade honestly (named reason),
    never run a build guaranteed to fail on a missing require('@grpc/grpc-js')."""
    wd = _node_workdir(tmp_path)
    monkeypatch.setattr(C, "prepare_node_workdir", lambda *a, **k: False)
    res = C.build_service_image("paymentservice", wd, "node", target_files=["server.js"], build=True)
    assert not res.ok
    assert "vendor" in res.skipped_reason.lower()


@pytest.mark.skipif(not _NODE_VENDORED, reason="node_runtime/node_modules not vendored (run vendor.sh)")
def test_node_vendored_closure_staged(tmp_path):
    """CONTAINERIZE staging: the vendored offline closure + proto are staged into the build context
    so the Node server runs with no network — node_modules + demo.proto land in the workdir."""
    wd = _node_workdir(tmp_path)
    res = C.build_service_image("paymentservice", wd, "node", target_files=["server.js"], build=False)
    assert "node_modules" in res.context_files and "demo.proto" in res.context_files
    assert (wd / "node_modules" / "@grpc").is_dir()
    assert (wd / "demo.proto").is_file()


def test_csharp_build_command_constructed(tmp_path):
    wd = _csharp_workdir(tmp_path)
    res = C.build_service_image("cartservice", wd, "csharp", target_files=["Program.cs"], build=False)
    assert res.tag == "r3/cartservice:csharp"
    assert res.language == "csharp"
    df = (wd / "Dockerfile").read_text()
    assert 'ENTRYPOINT ["dotnet", "/app/server.dll"]' in df


def test_csharp_proto_colocated(tmp_path):
    """CONTAINERIZE staging: demo.proto is co-located into the project dir so Grpc.Tools codegens the
    C# server stubs at publish time (no committed/vendored stub set)."""
    wd = _csharp_workdir(tmp_path)
    res = C.build_service_image("cartservice", wd, "csharp", target_files=["Program.cs"], build=False)
    assert "demo.proto" in res.context_files
    assert (wd / "demo.proto").is_file()


def test_csharp_uses_system_protoc_arm64_fix(tmp_path):
    """CONTAINERIZE FIX (OQ-C4): Grpc.Tools 2.71's bundled linux_arm64 protoc SIGSEGVs (exit 139)
    under the MSBuild Protobuf_Compile invocation; the build installs the system protoc and points
    Grpc.Tools at it (Protobuf_ProtocFullPath) so codegen succeeds."""
    wd = _csharp_workdir(tmp_path)
    C.build_service_image("cartservice", wd, "csharp", target_files=["Program.cs"], build=False)
    df = (wd / "Dockerfile").read_text()
    assert "protobuf-compiler" in df  # system protoc installed in the build stage
    assert "-p:Protobuf_ProtocFullPath=/usr/bin/protoc" in df  # Grpc.Tools points at it


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
    assert bp.run_cmd[:2] == ["docker", "run"]
    assert "-d" in bp.run_cmd
    # NO --rm: a crashed container must persist so its logs are readable on a readiness failure
    # (the caller tears it down explicitly with `docker rm -f`).
    assert "--rm" not in bp.run_cmd
    assert any("127.0.0.1:18080:" in a for a in bp.run_cmd)
    assert bp.probe_suite  # a behavioral probe suite is mapped for this service
    assert "run=False" in bp.skipped_reason  # command-only by default


def test_boot_readiness_gate_fails_when_port_never_accepts(monkeypatch):
    """A clean `docker run` exit with a process that never serves must report ok=False (not ok), with
    the container logs captured — the fix for the misleading 'boot ok -> coverage 0.0' failure mode."""
    class _Proc:
        returncode = 0
        stdout = "deadbeef\n"  # docker run printed a container id (launch accepted)
        stderr = ""

    monkeypatch.setattr(C, "docker_available", lambda: True)
    monkeypatch.setattr(C, "_container_logs", lambda name, **kw: "ModuleNotFoundError: jinja2")
    bp = C.boot_and_probe(
        "r3/emailservice:python", "emailservice", "python",
        host_port=18099, run=True, runner=lambda *a, **k: _Proc(),
        ready_check=lambda port, timeout: False,  # never becomes ready
    )
    assert bp.returncode == 0  # docker run itself succeeded...
    assert bp.ready is False and bp.ok is False  # ...but the server never served -> NOT ok
    assert "did not become ready" in bp.skipped_reason
    assert "jinja2" in bp.log  # container logs surfaced for a self-explaining failure


def test_boot_readiness_gate_passes_when_port_accepts(monkeypatch):
    class _Proc:
        returncode = 0
        stdout = "deadbeef\n"
        stderr = ""

    monkeypatch.setattr(C, "docker_available", lambda: True)
    bp = C.boot_and_probe(
        "r3/productcatalogservice:go", "productcatalogservice", "go",
        host_port=18098, run=True, runner=lambda *a, **k: _Proc(),
        ready_check=lambda port, timeout: True,
    )
    assert bp.ready is True and bp.ok is True


def test_unsupported_language_raises(tmp_path):
    wd = _go_workdir(tmp_path)
    with pytest.raises(ValueError):
        C.build_service_image("adservice", wd, "java", target_files=["Main.java"], build=False)
