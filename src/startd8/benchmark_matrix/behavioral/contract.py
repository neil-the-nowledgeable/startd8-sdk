"""Startup contract + per-language serve resolution (M-T2.2 / FR-T2-CONTRACT / FR-T2-HOOK).

`LanguageProfile` is a ``@runtime_checkable`` Protocol and ``LanguageRegistry.register`` gates on
``isinstance(profile, LanguageProfile)`` (registry.py:76) — so adding a serve method to the Protocol
would break every existing profile's registration. The serve command is therefore resolved here,
**additively**: a seed's optional ``startup`` block is authoritative; absent that, a small
per-language default builder fills in (Node only, for the paymentservice pilot); anything else
returns ``None`` → the behavioral cell degrades (FR-32), it never crashes.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PORT_TOKEN = "$PORT"


@dataclass(frozen=True)
class StartupContract:
    """How to launch a generated service (FR-T2-CONTRACT) — part of the cell's fixed contract."""

    cmd: Tuple[str, ...]               # argv template; ``$PORT`` tokens substituted with the port
    port_env: Optional[str] = "PORT"   # env var that also carries the port (None = argv-only)
    readiness: str = "tcp"             # "tcp" = port-listening probe (gRPC default); "http" = health probe
    health_path: str = "/health"       # REST lane: path polled for readiness when readiness == "http"

    @classmethod
    def from_seed(cls, seed: dict) -> Optional["StartupContract"]:
        block = (seed or {}).get("startup")
        if not block or not block.get("cmd"):
            return None
        return cls(
            cmd=tuple(block["cmd"]),
            port_env=block.get("port_env", "PORT"),
            readiness=block.get("readiness", "tcp"),
            health_path=block.get("health_path", "/health"),
        )

    def resolve(self, port: int) -> Tuple[List[str], Dict[str, str]]:
        """Concrete ``(argv, extra_env)`` for ``port``: substitute ``$PORT`` and set ``port_env``."""
        argv = [
            str(port) if tok == PORT_TOKEN else tok.replace(PORT_TOKEN, str(port))
            for tok in self.cmd
        ]
        env = {self.port_env: str(port)} if self.port_env else {}
        return argv, env


def _node_default(target_files: List[str], port: int) -> Optional[Tuple[List[str], Dict[str, str]]]:
    """Default Node launch: ``node <entry.js>`` with ``PORT`` injected (OQ-T2-1: env injection)."""
    entry = next((f for f in target_files if f.endswith(".js")),
                 target_files[0] if target_files else None)
    if not entry:
        return None
    return (["node", entry], {"PORT": str(port)})


def _go_default(target_files: List[str], port: int) -> Optional[Tuple[List[str], Dict[str, str]]]:
    """Default Go launch (P2): run the service's module from its dir (`go.mod` lives there after
    `go mod tidy` provisioning). ``exec`` under the sandbox's setsid means killpg reaps the compiled
    child too — no orphan. PORT injected via env."""
    entry = next((f for f in target_files if f.endswith(".go")),
                 target_files[0] if target_files else None)
    if not entry:
        return None
    svc_dir = str(Path(entry).parent)
    # Serve the binary provisioning pre-built (./.bin/server) — no `go run` compile under the sandbox.
    return (["sh", "-c", f"cd {shlex.quote(svc_dir)} && exec ./.bin/server"], {"PORT": str(port)})


def _python_default(target_files: List[str], port: int) -> Optional[Tuple[List[str], Dict[str, str]]]:
    """Default Python launch (E6 / FR-X5-LANG): run the service entry script directly with
    ``python3 <entry.py>``. The OB Python services (recommendation, email) start a gRPC server in
    ``__main__`` and read ``PORT`` from the environment — so the port is injected via env (the OB
    convention), the same way Node does. Run from the service dir so any sibling provisioned deps
    (catalog client stub, Jinja2 template) resolve relatively. ``exec`` under setsid ⇒ killpg reaps
    the interpreter, no orphan."""
    entry = next((f for f in target_files if f.endswith(".py")),
                 target_files[0] if target_files else None)
    if not entry:
        return None
    svc_dir = str(Path(entry).parent)
    script = Path(entry).name
    return (
        ["sh", "-c", f"cd {shlex.quote(svc_dir)} && exec python3 {shlex.quote(script)}"],
        {"PORT": str(port)},
    )


def _csharp_default(target_files: List[str], port: int) -> Optional[Tuple[List[str], Dict[str, str]]]:
    """Default C# launch (E6 / FR-X5-LANG): run the published .NET service DLL with
    ``dotnet ./.bin/<svc>.dll`` — mirroring Go's pre-built-binary convention (no ``dotnet run`` /
    ``dotnet build`` compile under the sandbox, which would need network restore). The published
    closure is expected under ``./.bin/`` at prepare time (provision.py, deferred — see FR-X5-DEPS).

    .NET binds via the ``ASPNETCORE_URLS`` / Kestrel ``PORT`` convention; the OB cartservice reads
    ``PORT`` from the environment (gRPC C-core listener), so we inject ``PORT`` like the other
    languages and additionally set ``ASPNETCORE_URLS`` to the loopback host:port for Kestrel-hosted
    variants. The launcher itself is fully resolvable; whether the published DLL exists is a
    *provisioning* concern (deferred) — if absent the cell degrades at boot, it never false-0s."""
    entry = next((f for f in target_files if f.endswith(".cs")),
                 target_files[0] if target_files else None)
    if not entry:
        return None
    # The .cs target lives at .../src/services/CartService.cs; the published service root is the
    # service dir (…/cartservice). Walk up to the directory named like the service, else the parent
    # of the immediate dir. Provisioning publishes the DLL to ``<svc_root>/.bin/server.dll``.
    p = Path(entry)
    svc_root = p.parent
    for anc in p.parents:
        if anc.name.endswith("service"):
            svc_root = anc
            break
    svc_root_s = str(svc_root)
    return (
        [
            "sh",
            "-c",
            f"cd {shlex.quote(svc_root_s)} && exec dotnet ./.bin/server.dll",
        ],
        {
            "PORT": str(port),
            "ASPNETCORE_URLS": f"http://127.0.0.1:{port}",
        },
    )


# Per-language fallback launchers (additive; the seed `startup` contract is authoritative).
# Java still needs a secured launcher (javac/vendored jars, not gradle) → absent ⇒ degrade.
# C# is resolvable here, but its published-DLL provisioning is deferred (E6) — boot degrades cleanly
# until provision.py publishes the offline closure.
_DEFAULTS = {
    "nodejs": _node_default,
    "go": _go_default,
    "python": _python_default,
    "csharp": _csharp_default,
}


def resolve_serve_command(
    seed: dict,
    target_files: List[str],
    port: int,
    language_id: Optional[str] = None,
) -> Optional[Tuple[List[str], Dict[str, str]]]:
    """Return ``(argv, extra_env)`` to launch the service on ``port``, or ``None`` → degrade.

    The seed's ``startup`` contract is authoritative; otherwise fall back to the per-language
    default. ``None`` means "no way to launch this language/service" — the caller records the cell
    degraded, never scores it 0.
    """
    contract = StartupContract.from_seed(seed)
    if contract is not None:
        return contract.resolve(port)
    seed = seed or {}
    # Real seeds nest language under service_metadata; an explicit arg wins, then top-level, then nested.
    lang = language_id or seed.get("language") or seed.get("service_metadata", {}).get("language")
    builder = _DEFAULTS.get(lang)
    return builder(target_files, port) if builder else None
