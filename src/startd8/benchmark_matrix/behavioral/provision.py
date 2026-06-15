"""Per-language dependency provisioning at prepare time (P1 — FR-P1-1..6 + FR-P1-SEC-1..5).

Runs BEFORE the egress-denied run sandbox, so it CAN use the network — but it installs untrusted
model manifests, which re-opens arbitrary-code-execution (FR-44). The CRP-mandated controls:
  - **scripts-disabled** installs (FR-P1-SEC-1): pip `--only-binary` (no setup.py build), npm
    `--ignore-scripts`; Go modules have no install scripts.
  - **scrubbed env** (FR-P1-SEC-2 / FR-45): no API keys/tokens reach the installer (reuses
    `sandbox.scrub_env`), HOME redirected into the cell workdir.
  - **per-cell caches** (FR-P1-SEC-5): GOMODCACHE/pip/npm caches under the cell workdir, so one
    cell can't poison another's.
  - **integrity** (FR-P1-SEC-4): Go writes/verifies `go.sum`; pip/npm use lockfile/hash where present.
  - **offline → fail closed** (FR-P1-SEC-3): an offline run degrades, it never silently opens the net.
Anything unsupported or toolchain-absent → **degrade (FR-T2-2/FR-P1-5)**, never scored 0.

NOTE (v1): OS-level network restriction to package registries (FR-P1-SEC-2) is best-effort here — a
transparent egress proxy/allowlist is v2 (CRP F-6 deferred). The controls actually applied are
recorded in ``ProvisionResult.controls`` (honest, never silently claimed).

Node is handled by ``execute.prepare_node_workdir`` (offline vendored closure — the safest path);
this module covers Go and Python. Java/C# secure provisioning (javac/restore over vendored jars,
NOT gradle/msbuild which execute untrusted build scripts) is a follow-up → degrade for now.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ..sandbox import scrub_env

# Vendored protoc-generated Go stubs (FR-P1-GO-STUBS) — generated once from demo.proto.
_GO_STUBS_DIR = Path(__file__).parent / "go_stubs" / "hipstershop"
# The model invents a proto module under this prefix and pseudo-versions it; go mod can't fetch it.
_GO_STUB_MODULE_MARKER = "github.com/GoogleCloudPlatform/microservices-demo"

V1_CONTROLS = "scripts-disabled+scrubbed-env+per-cell-cache+integrity"  # egress-allowlist proxy = v2

# FR-P1-2 curated common set (the gRPC/proto runtime models routinely don't declare).
_COMMON: Dict[str, List[str]] = {"python": ["grpcio", "protobuf"]}
# language -> toolchain executable that must be present (FR-P1-SEC-1/FR-P1-5).
_TOOLCHAIN: Dict[str, str] = {"go": "go", "python": "python3", "java": "javac", "csharp": "dotnet"}

# A runner runs (argv, cwd, env, timeout) and returns (returncode, tail_output). Injectable for tests.
Runner = Callable[[List[str], Path, Dict[str, str], float], Tuple[int, str]]


@dataclass
class ProvisionResult:
    ok: bool
    language: str
    controls: str = ""        # which security controls actually applied (FR-P1-SEC, honest)
    detail: str = ""
    degraded_reason: str = ""  # set when ok=False for an env reason (FR-T2-2)


def secure_env(workdir: Path) -> Dict[str, str]:
    """Scrubbed env (no secrets, HOME→workdir) + per-cell package caches (FR-P1-SEC-2/5)."""
    workdir = Path(workdir).resolve()  # Go requires GOMODCACHE absolute; callers may pass relative
    env = scrub_env(workdir)
    cache = workdir / ".cache"
    env["GOMODCACHE"] = str(cache / "go-mod")
    env["GOCACHE"] = str(cache / "go-build")
    env["GOFLAGS"] = "-mod=mod"          # derive deps from imports; write go.sum (integrity)
    env["PIP_CACHE_DIR"] = str(cache / "pip")
    env["npm_config_cache"] = str(cache / "npm")
    env["GOTELEMETRY"] = "off"   # don't scatter Go telemetry dirs into the cell (HOME=workdir)
    return env


def setup_go_stubs(workdir: Path, svc_dir: Path) -> Optional[str]:
    """FR-P1-GO-STUBS: vendor the proto stubs as a local module + ``replace`` the model's invented
    stub-import module → local, so `go mod tidy` resolves it (the stubs aren't a fetchable module).
    Returns None on success (or when there's nothing to vendor), else a degrade reason."""
    gomod = Path(svc_dir) / "go.mod"
    if not gomod.is_file():
        return "go.mod missing"
    text = gomod.read_text()
    m = re.search(rf"({re.escape(_GO_STUB_MODULE_MARKER)}[^\s]*)\s+v", text)
    if not m:
        return None  # no external proto module required → model self-contains; nothing to vendor
    module = m.group(1)
    # The pb import is `<module>[/<subpath>]` somewhere in the .go sources — place stubs at that subpath.
    subpath = ""
    for go_file in Path(svc_dir).glob("*.go"):
        im = re.search(rf'"{re.escape(module)}(/[\w./-]+)?"', go_file.read_text())
        if im:
            subpath = (im.group(1) or "").lstrip("/")
            break
    localmod = Path(workdir).resolve() / ".gostubs"
    dest = (localmod / subpath) if subpath else localmod
    dest.mkdir(parents=True, exist_ok=True)
    for f in ("demo.pb.go", "demo_grpc.pb.go"):
        if not (_GO_STUBS_DIR / f).is_file():
            return "vendored go stubs missing (regenerate go_stubs from demo.proto)"
        shutil.copy(_GO_STUBS_DIR / f, dest / f)
    (localmod / "go.mod").write_text(
        f"module {module}\n\ngo 1.21\n\n"
        "require (\n\tgoogle.golang.org/grpc v1.81.1\n\tgoogle.golang.org/protobuf v1.36.11\n)\n")
    if f"replace {module}" not in text:
        gomod.write_text(text.rstrip() + f"\n\nreplace {module} => {localmod}\n")
    return None


def install_plan(language: str, workdir: Path, target_files: List[str]) -> Optional[Tuple[List[str], Path]]:
    """Return a (scripts-disabled) ``(argv, cwd)`` install command, or None if unsupported → degrade."""
    svc_dir = (Path(workdir) / Path(target_files[0]).parent) if target_files else Path(workdir)
    if language == "go":
        # go mod tidy derives deps from imports (FR-P1-SEC-4 go.sum), THEN compile the binary here at
        # prepare time (network/resources OK). The serve runs the pre-built ./.bin/server — no compile
        # under the egress-denied, rlimited sandbox (which was killing `go run`).
        return (["sh", "-c", "go mod tidy && go build -o .bin/server ."], svc_dir)
    if language == "python":
        target = Path(workdir) / ".pydeps"
        # --only-binary: no setup.py build executes (FR-P1-SEC-1). Common set; requirements.txt top-up.
        cmd = ["pip", "install", "--only-binary=:all:", "--no-input", "--target", str(target), *_COMMON["python"]]
        req = svc_dir / "requirements.txt"
        if req.is_file():
            cmd += ["-r", str(req)]
        return (cmd, svc_dir)
    # java/csharp: secure path (javac/restore over vendored jars, not gradle/msbuild) not yet built.
    return None


def _subprocess_runner(argv: List[str], cwd: Path, env: Dict[str, str], timeout: float) -> Tuple[int, str]:
    try:
        p = subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True, text=True,
                           check=False, timeout=timeout)
        return p.returncode, ((p.stderr or "") + (p.stdout or ""))[-400:]
    except subprocess.TimeoutExpired:
        return 124, f"provision timed out after {timeout}s"
    except Exception as e:  # noqa: BLE001 — provisioning must never crash the harness
        return 1, f"provision launch error: {type(e).__name__}: {e}"


def provision_workdir(
    workdir: Path,
    language: Optional[str],
    target_files: List[str],
    *,
    offline: bool = False,
    runner: Optional[Runner] = None,
    timeout: float = 600.0,
) -> ProvisionResult:
    """Securely provision a non-Node cell's deps at prepare time. Degrades honestly on any env reason."""
    runner = runner or _subprocess_runner
    lang = language or "unknown"
    plan = install_plan(lang, Path(workdir), target_files)
    if plan is None:
        # No provisioning strategy (java/csharp secure path TBD, or unknown lang) → SKIP and proceed,
        # don't fail the cell: the server may ship its own deps, else it degrades on startup with the
        # missing module named (FR-T2-DEPS2). We never run untrusted build scripts (gradle/msbuild).
        return ProvisionResult(True, lang, controls="skipped",
                               detail=f"no provisioning strategy for '{lang}' — proceeding")
    tool = _TOOLCHAIN.get(lang)
    if tool and shutil.which(tool) is None:
        return ProvisionResult(False, lang, degraded_reason=f"toolchain absent: {tool}")
    if offline:  # FR-P1-SEC-3: fail closed, never silently open the network
        return ProvisionResult(False, lang,
                               degraded_reason="offline: declared-dep install needs network (fail-closed)")
    argv, cwd = plan
    Path(cwd).mkdir(parents=True, exist_ok=True)
    if lang == "go":  # FR-P1-GO-STUBS: vendor stubs + replace before `go mod tidy` can resolve them
        stub_err = setup_go_stubs(Path(workdir), cwd)
        if stub_err:
            return ProvisionResult(False, lang, degraded_reason=f"go-stub provisioning: {stub_err}")
    rc, out = runner(argv, Path(cwd), secure_env(Path(workdir)), timeout)
    if rc != 0:
        return ProvisionResult(False, lang, controls=V1_CONTROLS,
                               degraded_reason=f"provision failed (rc={rc}): {out[-160:]}")
    return ProvisionResult(True, lang, controls=V1_CONTROLS, detail=" ".join(argv))
