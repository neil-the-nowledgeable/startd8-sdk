"""Per-service container image build (R3-M0 — FR-T2-CONTAINER / CONTAINERIZATION_SCOPING §5/§7b).

Turns a model-generated service workdir into a runnable container image by REUSING the offline-dep
provisioning the bare-process behavioral harness already ships (``behavioral.provision`` +
``behavioral.execute.prepare_node_workdir``) and dropping a parameterized per-language Dockerfile
template (``fleet/templates/Dockerfile.<lang>.tmpl``) into the build context. This is the
``provision.py`` logic relocated into a Docker build stage — the harness owns the build manifests
(go.mod / .pydeps / node_modules / .csproj), the model owns only the source (§4 build-files injection).

Design stance (CONTAINERIZATION_SCOPING §5):
  - **Templates, not hand-Dockerfiles** — one parameterized template per language, filled from the
    seed + ``contract.py`` so the container substrate stays honest about the same inputs as the
    bare-process fleet.
  - **REUSE the offline closures** — ``setup_go_stubs`` (Go local-module stub vendoring + ``replace``),
    the ``demo_pb2*`` co-location + ``.pydeps`` install plan (Python), the vendored ``node_modules``
    closure (Node), and ``publish_dotnet_service`` inputs (C#). The same helpers the prepare-time
    behavioral path calls — no duplicated dep logic, no drift from ``provision.py``.
  - **Injected runner** — the actual ``docker build`` runs through an injected ``runner`` (default
    ``subprocess.run``) so a test (and a ``--dry-run``) can capture the constructed command WITHOUT
    executing docker. ``build_service_image(..., build=False)`` returns the command only.
  - **Degrade-honest** — docker absent (``shutil.which('docker')`` is None) or ``build=False`` ⇒ a
    cmd-only result with ``ok=False`` and a ``skipped_reason``; an env failure is never a silent pass.

DEFERRED (not M0):
  - ``--network=none`` HERMETIC build (pre-pull digest-pinned base images + bake the dep caches into
    the build context / a local registry). M0 builds pull base + module deps over the network (v1);
    the §5 offline base-image prep + warm-cache bake (NuGet/.m2/GOMODCACHE/wheels) is M1+ (OQ-C1/C6).
  - Multi-arch (``--platform`` per TARGETARCH) — the canonical norm (§7b) but baked caches are
    arch-specific (OQ-C4); M0 builds for the host arch.
  - Java/adservice — no offline-build provisioning exists yet (OQ-C5, deferred to v2).
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ..behavioral import provision as _prov
from ..behavioral.execute import prepare_node_workdir

_TEMPLATES = Path(__file__).parent / "templates"
_BEHAVIORAL = Path(_prov.__file__).parent

# A runner runs (argv, cwd) and returns (returncode, combined_output). Injectable so a test / dry-run
# captures the command WITHOUT executing docker. Mirrors provision.Runner's spirit (here cwd-only).
Runner = Callable[..., "subprocess.CompletedProcess"]


@dataclass(frozen=True)
class ImageSpec:
    """Per-language image build recipe: which template + the canonical digest-pinned base images.

    Base images mirror the upstream microservices-demo-latest Dockerfiles (CONTAINERIZATION_SCOPING
    §7b) — the authoritative, digest-pinned, multi-arch canonical build for each language. M0 keeps
    the *build pattern*; the network-fetch dep steps are what M1+ swaps for pre-baked offline caches.
    """

    language: str
    template: str                      # template filename under fleet/templates/
    params: Dict[str, str]             # {TOKEN: value} filled into the template
    runtime_port: int = 8080


# Canonical digest-pinned bases (CONTAINERIZATION_SCOPING §7b table). Pins reused verbatim from the
# upstream microservices-demo-latest Dockerfiles so the harness image matches the canonical build.
_GO_BUILDER = "golang:1.25.6-alpine@sha256:98e6cffc31ccc44c7c15d83df1d69891efee8115a5bb7ede2bf30a38af3e3c92"
_GO_RUNTIME = "gcr.io/distroless/static"
_PYTHON_BASE = "python:3.12-slim"  # slim (not the alpine pin) — wheels need glibc for grpcio C-ext (OQ-C4)
_NODE_BASE = "node:20.20.0-alpine@sha256:09e2b3d9726018aecf269bd35325f46bf75046a643a66d28360ec71132750ec8"
_DOTNET_SDK = "mcr.microsoft.com/dotnet/sdk:10.0.100-noble@sha256:c7445f141c04f1a6b454181bd098dcfa606c61ba0bd213d0a702489e5bd4cd71"
_DOTNET_RUNTIME = "mcr.microsoft.com/dotnet/aspnet:10.0"

# Per-language curated pip set baked into the Python image (the common gRPC runtime install_plan
# installs into .pydeps). protobuf/typing_extensions pure-Python; grpcio C-ext provided by the wheel.
_PY_PIP_PKGS = "grpcio protobuf typing_extensions"


@dataclass
class ImageBuildResult:
    """Outcome of (preparing the build context for and optionally building) a service image."""

    tag: str
    language: str
    dockerfile: Path                   # the rendered Dockerfile written into the workdir
    build_cmd: List[str]               # the constructed ``docker build ...`` argv
    returncode: Optional[int] = None   # None when not built (skipped / build=False)
    log: str = ""                      # combined build output tail, or the skip note
    ok: bool = False                   # True only when an actual build ran and returned 0
    skipped_reason: str = ""           # set when cmd-only (docker absent or build=False)
    context_files: List[str] = field(default_factory=list)  # provenance: staged build-context inputs


# ---------------------------------------------------------------------------------------------------
# Build-context preparation — one per language, each REUSING behavioral/provision.py helpers.
# ---------------------------------------------------------------------------------------------------

def _svc_dir(workdir: Path, target_files: List[str]) -> Path:
    """The service directory (build context root for the staged source) — the target's parent."""
    if target_files:
        return Path(workdir) / Path(target_files[0]).parent
    return Path(workdir)


def _stage_go_context(workdir: Path, target_files: List[str]) -> Tuple[List[str], str]:
    """REUSE ``provision.setup_go_stubs``: vendor the hipstershop proto stubs as a LOCAL module under
    ``.gostubs`` + ``require``/``replace`` the model's stub-import → local, so ``go mod tidy`` resolves
    offline against known-good stubs (the upstream ``@latest`` dropped ``hipstershop``). Returns the
    staged context files (provenance) + a degrade reason ("" on success)."""
    svc = _svc_dir(workdir, target_files)
    stub_err = _prov.setup_go_stubs(Path(workdir), svc)
    if stub_err:
        return [], stub_err
    # CONTAINERIZE FIX: setup_go_stubs writes an ABSOLUTE host path in the `replace` directive (fine
    # for the bare-process build, where that path exists on the host). Inside the container the host
    # path is absent, so `go build` fails to read .gostubs/go.mod. Rewrite the replace target to a
    # path RELATIVE to the service go.mod so `COPY . .` + the relative replace resolve in-image
    # (mirrors the validated compose-prototype `=> ./_stubs` recipe). Leaves provision.py untouched.
    gomod = svc / "go.mod"
    gostubs = Path(workdir) / ".gostubs"
    if gomod.is_file() and gostubs.is_dir():
        rel = os.path.relpath(gostubs.resolve(), svc.resolve())
        # Go requires a replacement dir path to start with `./` or `../` — NOT just any leading dot
        # (e.g. `.gostubs` is rejected; `./.gostubs` is required).
        if not (rel.startswith("./") or rel.startswith("../")):
            rel = "./" + rel
        text = gomod.read_text()
        text = re.sub(r"(replace\s+\S+\s+=>\s+)\S+", lambda m: m.group(1) + rel, text)
        gomod.write_text(text)
    staged = ["go.mod"]
    if gostubs.is_dir():
        staged += [str(p.relative_to(workdir)) for p in sorted(gostubs.iterdir())]
    return staged, ""


def _stage_python_context(workdir: Path, target_files: List[str]) -> Tuple[List[str], str]:
    """REUSE the OB Python convention ``provision.install_plan`` encodes: co-locate the gRPC stubs
    (``demo_pb2.py`` / ``demo_pb2_grpc.py``) next to the server so the generated import resolves; the
    common gRPC runtime (``grpcio protobuf typing_extensions``) is pip-installed by the template
    (M0 baked via the template's pip step; the ``.pydeps`` wheel-closure bake is the M1 offline path)."""
    svc = _svc_dir(workdir, target_files)
    svc.mkdir(parents=True, exist_ok=True)
    staged: List[str] = []
    for stub in ("demo_pb2.py", "demo_pb2_grpc.py"):
        src = _BEHAVIORAL / stub
        if not src.is_file():
            return [], f"behavioral gRPC stub missing: {stub}"
        shutil.copy(src, svc / stub)
        staged.append(str((svc / stub).relative_to(workdir)))
    return staged, ""


def _stage_node_context(workdir: Path, target_files: List[str]) -> Tuple[List[str], str]:
    """REUSE ``execute.prepare_node_workdir``: stage the FULLY VENDORED offline closure
    (``node_runtime/node_modules`` = grpc-js + proto-loader + pino + uuid + decimal.js) and
    ``demo.proto`` at every conventional location, so the generated Node server runs with NO npm
    install — the most offline-ready lane. False ⇒ the runtime hasn't been vendored (run vendor.sh)."""
    if not prepare_node_workdir(Path(workdir), target_files):
        return [], "node runtime not vendored — run node_runtime/vendor.sh"
    staged = ["node_modules", "demo.proto"]
    return staged, ""


def _stage_csharp_context(workdir: Path, target_files: List[str]) -> Tuple[List[str], str]:
    """REUSE the ``publish_dotnet_service`` stance (§4/§7b): co-locate ``demo.proto`` into the project
    dir so Grpc.Tools codegens the C# server stubs at ``dotnet publish`` time (the build runs INSIDE
    the image here, not at prepare time). A harness-owned ``.csproj`` with ``<AssemblyName>server</…>``
    + the ``<Protobuf>`` item is expected in the context; M0 stages the proto, the warm-NuGet-cache
    bake for a hermetic build is DEFERRED (OQ-C6 — the one load-bearing unsolved reuse gap)."""
    svc = _svc_dir(workdir, target_files)
    svc.mkdir(parents=True, exist_ok=True)
    proto_src = _BEHAVIORAL / "demo.proto"
    if not proto_src.is_file():
        return [], "behavioral demo.proto missing"
    shutil.copy(proto_src, svc / "demo.proto")
    return [str((svc / "demo.proto").relative_to(workdir))], ""


_STAGERS: Dict[str, Callable[[Path, List[str]], Tuple[List[str], str]]] = {
    "go": _stage_go_context,
    "python": _stage_python_context,
    "node": _stage_node_context,
    "nodejs": _stage_node_context,
    "csharp": _stage_csharp_context,
}


# ---------------------------------------------------------------------------------------------------
# Template -> ImageSpec resolution.
# ---------------------------------------------------------------------------------------------------

def _entry_for(language: str, target_files: List[str]) -> str:
    """The server entry script the template ENTRYPOINTs (Python/Node only — Go/C# run a binary)."""
    ext = {"python": ".py", "node": ".js", "nodejs": ".js"}.get(language, "")
    if ext:
        return next((Path(f).name for f in target_files if f.endswith(ext)),
                    Path(target_files[0]).name if target_files else f"server{ext}")
    return ""


def _image_spec(language: str, service: str, target_files: List[str], port: int,
                extra_pip: Optional[List[str]] = None) -> ImageSpec:
    """Build the per-language ImageSpec (template + filled params). Canonical bases per §7b.

    ``extra_pip`` are per-service Python deps appended to the curated baseline (``_PY_PIP_PKGS``) —
    the container analogue of ``provision.install_plan``'s service ``requirements.txt`` top-up. Kept
    per-service (not baked into the baseline) so leaf services that don't need them stay lean: e.g.
    emailservice renders its confirmation body from a jinja2 template and needs ``jinja2``, but
    recommendationservice does not."""
    lang = "node" if language == "nodejs" else language
    if lang == "go":
        return ImageSpec(lang, "Dockerfile.go.tmpl",
                         {"GO_BUILDER": _GO_BUILDER, "RUNTIME": _GO_RUNTIME, "PORT": str(port)}, port)
    if lang == "python":
        pip_pkgs = " ".join([_PY_PIP_PKGS, *(extra_pip or [])]).strip()
        return ImageSpec(lang, "Dockerfile.python.tmpl",
                         {"PYTHON_BASE": _PYTHON_BASE, "PIP_PKGS": pip_pkgs,
                          "ENTRY": _entry_for("python", target_files), "PORT": str(port)}, port)
    if lang == "node":
        return ImageSpec(lang, "Dockerfile.node.tmpl",
                         {"NODE_BASE": _NODE_BASE, "ENTRY": _entry_for("node", target_files),
                          "PORT": str(port)}, port)
    if lang == "csharp":
        return ImageSpec(lang, "Dockerfile.csharp.tmpl",
                         {"DOTNET_SDK": _DOTNET_SDK, "DOTNET_RUNTIME": _DOTNET_RUNTIME,
                          "PORT": str(port)}, port)
    raise ValueError(f"no container template for language '{language}' (Java deferred to v2 — OQ-C5)")


def _render_template(spec: ImageSpec) -> str:
    tmpl_path = _TEMPLATES / spec.template
    text = tmpl_path.read_text()
    for tok, val in spec.params.items():
        text = text.replace("{" + tok + "}", val)
    return text


def docker_available() -> bool:
    """True when the ``docker`` CLI is on PATH (degrade-honest gate; never runs docker)."""
    return shutil.which("docker") is not None


def _default_tag(service: str, language: str) -> str:
    """The image tag namespace (§5 ``r3/<model>/<service>:<tag>`` minus the model, supplied later)."""
    return f"r3/{service}:{language}"


# ---------------------------------------------------------------------------------------------------
# The builder.
# ---------------------------------------------------------------------------------------------------

def build_service_image(
    service: str,
    workdir: Path,
    language: str,
    *,
    target_files: Optional[List[str]] = None,
    tag: Optional[str] = None,
    build: bool = True,
    runner: Runner = subprocess.run,
    build_port: int = 8080,
    extra_pip: Optional[List[str]] = None,
) -> ImageBuildResult:
    """Prepare the build context (REUSING ``provision.py``) + render the Dockerfile + construct (and,
    via ``runner``, optionally run) the ``docker build`` command for ``service``'s generated workdir.

    Args:
      service: OB service name (e.g. ``"paymentservice"``) — drives the tag + suite mapping.
      workdir: the model-generated cell workdir (build-context root).
      language: ``"go" | "python" | "node"/"nodejs" | "csharp"`` (Java deferred to v2, OQ-C5).
      target_files: generated source paths relative to ``workdir`` (resolves the service dir + entry).
      tag: image tag; defaults to ``r3/<service>:<language>``.
      build: when False (or docker absent) → return the constructed command ONLY (``ok=False`` +
        ``skipped_reason``), never executing docker (degrade-honest, used by ``--dry-run`` / CI).
      runner: injected (argv, cwd=...) -> CompletedProcess; default ``subprocess.run``. A test/dry-run
        passes a fake runner so the command is captured WITHOUT executing docker.
      build_port: the EXPOSE/PORT baked into the image (compose rebinds at run; M0 default 8080).
      extra_pip: per-service Python deps appended to the curated baseline (Python only) — e.g.
        ``["jinja2"]`` for emailservice; the container analogue of the service ``requirements.txt``
        top-up in ``provision.install_plan``.

    Returns an :class:`ImageBuildResult`. ``--network=none`` hermetic build is DEFERRED (see module
    docstring): M0 builds pull base + deps over the network; the offline base/cache bake is M1+.
    """
    workdir = Path(workdir)
    target_files = list(target_files or [])
    tag = tag or _default_tag(service, language)

    # Resolve the per-language image recipe (raises for an unsupported language — Java/v2).
    spec = _image_spec(language, service, target_files, build_port, extra_pip)

    # Prepare the build context by REUSING the behavioral provisioning helpers (§4/§6 reuse ledger).
    stager = _STAGERS.get(language)
    if stager is None:  # pragma: no cover — guarded by _image_spec above
        raise ValueError(f"no build-context stager for language '{language}'")
    context_files, stage_err = stager(workdir, target_files)

    # Render the per-language Dockerfile template into the workdir (the build context root).
    dockerfile = workdir / "Dockerfile"
    dockerfile.write_text(_render_template(spec))

    # Construct the docker build command. M0 = networked build (no --network=none yet, see docstring).
    build_cmd = ["docker", "build", "-t", tag, "-f", str(dockerfile), str(workdir)]

    result = ImageBuildResult(
        tag=tag, language=spec.language, dockerfile=dockerfile, build_cmd=build_cmd,
        context_files=context_files,
    )

    # Context-prep failure (e.g. node closure not vendored) → degrade-honest: keep the command for
    # provenance, but don't run a build that's guaranteed to fail; name the reason.
    if stage_err:
        result.skipped_reason = f"build-context prep failed: {stage_err}"
        result.log = result.skipped_reason
        return result

    if not build:
        result.skipped_reason = "build=False (command-only / dry-run)"
        result.log = " ".join(build_cmd)
        return result
    if not docker_available():
        result.skipped_reason = "docker CLI not found on PATH (degrade-honest)"
        result.log = result.skipped_reason
        return result

    # Execute the actual build through the injected runner (default subprocess.run).
    proc = runner(build_cmd, cwd=str(workdir), capture_output=True, text=True, check=False)
    result.returncode = getattr(proc, "returncode", None)
    out = (getattr(proc, "stderr", "") or "") + (getattr(proc, "stdout", "") or "")
    result.log = out[-2000:]
    result.ok = result.returncode == 0
    return result


# ---------------------------------------------------------------------------------------------------
# Boot + one-RPC probe — constructed here, RUN LIVE by the orchestrator (via the injected runner).
# ---------------------------------------------------------------------------------------------------

@dataclass
class BootProbeResult:
    """Outcome of constructing (and, via the runner, optionally running) a container boot + RPC probe.

    ``ok`` means **booted AND ready** — the container started AND its published port accepted a TCP
    connection within ``readiness_timeout``. A clean ``docker run`` exit is NOT sufficient: a process
    that crashes on startup (missing dep) or binds the wrong address (container-localhost instead of
    0.0.0.0) returns ``docker run`` rc=0 yet never serves. ``ready`` records the readiness check
    outcome explicitly; ``log`` carries the container logs when readiness fails, so the failure is
    self-explaining instead of surfacing downstream as a misleading probe coverage 0.0."""

    image: str
    service: str
    language: str
    run_cmd: List[str]                 # the constructed ``docker run ...`` argv
    host_port: int                     # the loopback port the published gRPC port maps to
    probe_suite: str                   # the behavioral suite module that probes the booted container
    returncode: Optional[int] = None
    log: str = ""
    ok: bool = False
    ready: Optional[bool] = None       # readiness-gate outcome (None when not run / not gated)
    skipped_reason: str = ""


def _await_port_ready(host_port: int, timeout: float, *, host: str = "127.0.0.1",
                      interval: float = 0.5) -> bool:
    """Poll ``host:host_port`` until a TCP connection is accepted or ``timeout`` elapses. A published
    container port only accepts once the server inside is actually listening on its external interface
    (0.0.0.0) — a crashed process or a container-localhost-only bind never accepts, which is exactly
    the failure this gate catches."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, host_port), timeout=2.0):
                return True
        except OSError:
            time.sleep(interval)
    return False


def _container_logs(name: str, *, tail: int = 60) -> str:
    """Best-effort tail of a container's logs (for a self-explaining readiness failure). The boot run
    drops ``--rm`` so a crashed container persists long enough to read its logs here; the caller is
    responsible for explicit ``docker rm -f`` teardown."""
    try:
        r = subprocess.run(["docker", "logs", "--tail", str(tail), name],
                           capture_output=True, text=True, check=False, timeout=15)
        return ((r.stdout or "") + (r.stderr or ""))[-1500:]
    except Exception:  # noqa: BLE001 — log fetch is diagnostic-only; never mask the real failure
        return ""


# Which behavioral suite probes a booted container for a one-RPC liveness check (the orchestrator
# imports + calls suite(host_port) against the published port AFTER the run_cmd brings the image up).
_PROBE_SUITES: Dict[str, str] = {
    "paymentservice": "startd8.benchmark_matrix.behavioral.charge_suite:run_charge_suite",
    "currencyservice": "startd8.benchmark_matrix.behavioral.currency_suite:run_currency_suite",
    "productcatalogservice": "startd8.benchmark_matrix.behavioral.catalog_suite:run_catalog_suite",
    "cartservice": "startd8.benchmark_matrix.behavioral.cart_suite:run_cart_suite",
    "emailservice": "startd8.benchmark_matrix.behavioral.email_suite:run_email_suite",
    "shippingservice": "startd8.benchmark_matrix.behavioral.shipping_suite:run_shipping_suite",
    "adservice": "startd8.benchmark_matrix.behavioral.ad_suite:run_ad_suite",
}


def boot_and_probe(
    image: str,
    service: str,
    language: str,
    *,
    host_port: int = 0,
    container_port: int = 8080,
    runner: Runner = subprocess.run,
    run: bool = False,
    container_name: Optional[str] = None,
    readiness_timeout: float = 30.0,
    ready_check: Optional[Callable[[int, float], bool]] = None,
) -> BootProbeResult:
    """Construct (and, via the injected ``runner``, optionally run) the ``docker run`` that boots a
    built image + name the one-RPC behavioral probe the ORCHESTRATOR runs against the published port.

    The container is started detached, publishing its gRPC port to a host loopback port; the
    orchestrator then imports ``probe_suite`` and calls ``suite(host_port)`` for a one-RPC liveness
    check (e.g. ``PaymentService.Charge`` for paymentservice — the SDK-authored ground truth). This is
    DESIGNED to be run live by the orchestrator: ``run=False`` (default) returns the command only so a
    test / dry-run captures it WITHOUT executing docker.

    ``host_port=0`` lets docker pick an ephemeral host port; the orchestrator reads the actual mapping
    from ``docker port`` after the run. A non-zero ``host_port`` pins the mapping (used by tests).

    **Readiness gate:** when a non-zero ``host_port`` is pinned, ``ok`` requires the published port to
    accept a TCP connection within ``readiness_timeout`` — not merely a clean ``docker run`` exit. The
    boot run drops ``--rm`` (so a crashed container's logs survive for diagnosis); **the caller MUST
    explicitly ``docker rm -f`` the container in teardown** (``validate_m0``/``validate_m1`` do). On a
    readiness failure the container logs are captured into ``log`` so the cause (crash, wrong bind) is
    visible instead of surfacing as a misleading downstream probe coverage 0.0. ``ready_check`` is
    injectable for tests.
    """
    name = container_name or f"r3-{service}-{language}"
    publish = f"{host_port}:{container_port}" if host_port else str(container_port)
    # Detached, loopback-published, named for deterministic teardown by the orchestrator. NO --rm: a
    # crashed container must persist so its logs are readable on a readiness failure (the caller tears
    # it down explicitly). Loopback bind (127.0.0.1) keeps the published port host-local.
    run_cmd = [
        "docker", "run", "-d", "--name", name,
        "-p", f"127.0.0.1:{publish}",
        image,
    ]
    probe = _PROBE_SUITES.get(service, "")
    result = BootProbeResult(
        image=image, service=service, language=language, run_cmd=run_cmd,
        host_port=host_port, probe_suite=probe,
    )
    if not probe:
        result.skipped_reason = f"no behavioral probe suite for service '{service}'"
    if not run:
        if not result.skipped_reason:
            result.skipped_reason = "run=False (command-only — orchestrator runs the live boot+probe)"
        result.log = " ".join(run_cmd)
        return result
    if not docker_available():
        result.skipped_reason = "docker CLI not found on PATH (degrade-honest)"
        result.log = result.skipped_reason
        return result
    proc = runner(run_cmd, capture_output=True, text=True, check=False)
    result.returncode = getattr(proc, "returncode", None)
    out = (getattr(proc, "stderr", "") or "") + (getattr(proc, "stdout", "") or "")
    if result.returncode != 0:
        result.log = out[-2000:]  # docker run itself failed (bad image / port clash) — keep its error
        result.ok = False
        return result

    # docker run accepted the launch — now GATE on actual readiness. A pinned host_port lets us poll
    # the published port; an ephemeral (0) port can't be polled here, so fall back to the launch rc.
    if not host_port:
        result.ok = True
        result.skipped_reason = "readiness not gated (ephemeral host_port=0; pin a port to gate)"
        result.log = out[-2000:]
        return result
    check = ready_check or _await_port_ready
    result.ready = bool(check(host_port, readiness_timeout))
    result.ok = result.ready
    if not result.ready:
        logs = _container_logs(name)
        result.skipped_reason = (
            f"container '{name}' booted (docker run rc=0) but did not become ready on "
            f"127.0.0.1:{host_port} within {readiness_timeout:.0f}s — the process likely crashed on "
            f"startup or bound a non-published address (e.g. container-localhost, not 0.0.0.0)"
        )
        result.log = f"{result.skipped_reason}\n--- container logs ({name}) ---\n{logs}"
    else:
        result.log = out[-2000:]
    return result
