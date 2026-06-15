"""Startup contract + per-language serve resolution (M-T2.2 / FR-T2-CONTRACT / FR-T2-HOOK).

`LanguageProfile` is a ``@runtime_checkable`` Protocol and ``LanguageRegistry.register`` gates on
``isinstance(profile, LanguageProfile)`` (registry.py:76) — so adding a serve method to the Protocol
would break every existing profile's registration. The serve command is therefore resolved here,
**additively**: a seed's optional ``startup`` block is authoritative; absent that, a small
per-language default builder fills in (Node only, for the paymentservice pilot); anything else
returns ``None`` → the behavioral cell degrades (FR-32), it never crashes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

PORT_TOKEN = "$PORT"


@dataclass(frozen=True)
class StartupContract:
    """How to launch a generated service (FR-T2-CONTRACT) — part of the cell's fixed contract."""

    cmd: Tuple[str, ...]               # argv template; ``$PORT`` tokens substituted with the port
    port_env: Optional[str] = "PORT"   # env var that also carries the port (None = argv-only)
    readiness: str = "tcp"             # v1: "tcp" = port-listening probe

    @classmethod
    def from_seed(cls, seed: dict) -> Optional["StartupContract"]:
        block = (seed or {}).get("startup")
        if not block or not block.get("cmd"):
            return None
        return cls(
            cmd=tuple(block["cmd"]),
            port_env=block.get("port_env", "PORT"),
            readiness=block.get("readiness", "tcp"),
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


# Per-language fallback launchers. Node only for the pilot; others absent → degrade (FR-32).
_DEFAULTS = {"nodejs": _node_default}


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
