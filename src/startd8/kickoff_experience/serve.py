"""M7 — serve plumbing, preflight/doctor, scratch GC, inspect mode, feature modes.

The kickoff web app (M4) is a throwaway *local* app. There is no in-SDK precedent for serving a
generated FastAPI app (FR-NEW-4), so this module owns the lifecycle:

* **Feature modes (R4-F5)** — ``inspect`` / ``preview`` / ``write`` / ``demo``. Default to the least
  privileged that the caller needs; ``write`` is the only mode that can reach ``apply_write_plan``.
* **Inspect / dry-run JSON (R4-F3 / R4-F8)** — :func:`inspect_payload` emits canonical state +
  readiness + next action + preflight WITHOUT opening a port, generating a scratch app, or writing.
  Versioned (``schema_version``) so IDE/MCP agents can consume it safely.
* **Preflight / doctor (R3-F3)** — :func:`preflight` checks the predictable failures (inputs dir
  exists/writable, port bindable, authoring docs present) before a serve, with actionable detail.
* **Loopback bind (R1-S8)** — :func:`serve_kickoff` binds ``127.0.0.1`` only; combined with the M4
  CSRF/rate-limit and the M6 allow-list, a local writer is not exposed cross-origin.
* **Scratch GC (R5-S8)** — stale generated-app scratch dirs are reclaimed on the next launch.
"""

from __future__ import annotations

import shutil
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .docs import load_kickoff_docs
from .manifest import KickoffExperienceConfig, default_config
from .ranking import next_action
from .readiness import build_readiness
from .web import app_fingerprint, load_state

INSPECT_SCHEMA_VERSION = 1  # R4-F8: bump on a breaking change to the inspect JSON shape


class Mode:
    """Feature modes (R4-F5). Least-privilege first."""

    INSPECT = "inspect"   # read-only state, no serve, no write
    PREVIEW = "preview"   # serve, but applies are refused (preview only)
    WRITE = "write"       # serve + applies allowed
    DEMO = "demo"         # serve over a fixture
    ALL = (INSPECT, PREVIEW, WRITE, DEMO)


def _nearest_existing(path: Path) -> Optional[Path]:
    """The nearest existing ancestor of *path* (where a package would be created)."""
    cur = path
    for _ in range(64):
        if cur.is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def find_free_port(host: str = "127.0.0.1") -> int:
    """Bind an ephemeral port on the loopback and return it (the OS picks a free one)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, 0))
        return s.getsockname()[1]
    finally:
        s.close()


# --- preflight / doctor ------------------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    blocking: bool = True

    def to_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail, "blocking": self.blocking}


@dataclass(frozen=True)
class PreflightResult:
    checks: tuple

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.blocking)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "checks": [c.to_dict() for c in self.checks]}


def preflight(
    project_root: str | Path,
    *,
    mode: str = Mode.WRITE,
    config: Optional[KickoffExperienceConfig] = None,
) -> PreflightResult:
    """Doctor the predictable serve failures before launching (R3-F3)."""
    import os

    root = Path(project_root).expanduser()
    inputs = root / "docs" / "kickoff" / "inputs"
    checks: List[Check] = []

    # NR-CM-A: `inputs_dir`/`inputs_writable` are ADVISORY, not blocking — a package-less project
    # must still serve so the Concierge mode can offer to instantiate it (FR-CM-6). When `inputs/`
    # is present but a parent dir is writable, a write-mode serve can still create it.
    inputs_ok = inputs.is_dir()
    checks.append(
        Check("inputs_dir", inputs_ok,
              f"{inputs} {'exists' if inputs_ok else 'missing — use Concierge mode to instantiate a kickoff package'}",
              blocking=False)
    )

    if mode in (Mode.WRITE, Mode.DEMO):
        # Writability of inputs/ if it exists, else of the nearest existing ancestor (where
        # instantiate would create the package). Advisory either way.
        probe = inputs if inputs_ok else _nearest_existing(inputs.parent)
        writable = bool(probe and os.access(probe, os.W_OK))
        checks.append(
            Check("inputs_writable", writable,
                  "kickoff inputs path is writable" if writable
                  else "kickoff inputs path is not writable for a write-mode serve",
                  blocking=False)
        )

    try:
        find_free_port()
        port_ok, port_detail = True, "a loopback port is bindable"
    except OSError as exc:
        port_ok, port_detail = False, f"cannot bind a loopback port: {exc}"
    checks.append(Check("port_bindable", port_ok, port_detail))

    docs = load_kickoff_docs(root)
    # Authoring docs are advisory: a brand-new project still serves (empty state).
    checks.append(
        Check("authoring_docs", True, f"{len(docs)} authoring doc(s) found", blocking=False)
    )

    return PreflightResult(checks=tuple(checks))


# --- scratch lifecycle (R5-S8) -----------------------------------------------------------------


def _scratch_root(project_root: Path) -> Path:
    return project_root / ".startd8" / "kickoff-scratch"


def scratch_dir_for(project_root: str | Path, fingerprint: str) -> Path:
    """The scratch dir for a given app fingerprint (R5-S1)."""
    return _scratch_root(Path(project_root).expanduser()) / fingerprint[:16]


def gc_stale_scratch(project_root: str | Path, keep_fingerprint: str, *, keep_n: int = 2) -> List[str]:
    """Remove scratch dirs that are not the current fingerprint, keeping at most *keep_n* (R5-S8).

    Returns the list of removed scratch dir names (for telemetry / a clear report).
    """
    root = _scratch_root(Path(project_root).expanduser())
    if not root.is_dir():
        return []
    keep = keep_fingerprint[:16]
    entries = sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime)
    removed: List[str] = []
    # Always keep the current fingerprint; among the rest, keep the newest (keep_n - 1).
    stale = [d for d in entries if d.name != keep]
    to_remove = stale[: max(0, len(stale) - (keep_n - 1))]
    for d in to_remove:
        shutil.rmtree(d, ignore_errors=True)
        removed.append(d.name)
    return removed


# --- inspect / dry-run (R4-F3 / R4-F8) ---------------------------------------------------------


def inspect_payload(
    project_root: str | Path,
    *,
    config: Optional[KickoffExperienceConfig] = None,
    mode: str = Mode.INSPECT,
) -> dict:
    """Canonical state + readiness + next action + preflight, with **no** serve/port/write (R4-F3).

    Versioned for safe agent consumption (R4-F8). This is also the read-only payload the MCP
    ``kickoff-state`` tool returns (FR-13, ``readOnlyHint`` preserved).
    """
    cfg = config or default_config()
    root = Path(project_root).expanduser()
    state = load_state(root)
    try:
        readiness = build_readiness(root)
    except Exception:
        readiness = None
    pf = preflight(root, mode=mode, config=cfg)
    return {
        "schema_version": INSPECT_SCHEMA_VERSION,
        "mode": mode,
        "project_root": str(root),
        "fingerprint": app_fingerprint(cfg),
        "state": state.to_dict(),
        "readiness": readiness.to_dict() if readiness is not None else None,
        "next_action": next_action(state, readiness).to_dict(),
        "preflight": pf.to_dict(),
    }


# --- serve (loopback) --------------------------------------------------------------------------


def make_chat_factory(project_root: str | Path, agent_spec: str, *, red_carpet: bool = False):
    """Build a `chat_factory` for the web agentic panel, or None if the agent can't be resolved.

    Returns a zero-arg callable yielding a fresh chat. When *red_carpet*, that is the **stage-aware
    Red Carpet conductor** chat (FR-RCT, OQ-4) — same propose/confirm floor, but it drives the staged
    build; otherwise the agentic Concierge chat. Returns ``None`` (panel disabled) on a missing key /
    unknown provider so serving degrades gracefully.
    """
    try:
        from ..utils.agent_resolution import resolve_agent_spec
        from .chat import new_agentic_kickoff_chat, new_red_carpet_chat

        factory = new_red_carpet_chat if red_carpet else new_agentic_kickoff_chat
        factory(resolve_agent_spec(agent_spec), project_root)  # validate up front
    except Exception:
        return None
    return lambda: factory(resolve_agent_spec(agent_spec), project_root)


def serve_kickoff(
    project_root: str | Path,
    *,
    mode: str = Mode.WRITE,
    theme: str = "professional",
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    config: Optional[KickoffExperienceConfig] = None,
    agent_spec: Optional[str] = None,
    red_carpet: bool = False,
) -> None:  # pragma: no cover - blocking I/O; covered indirectly via build_kickoff_app + preflight
    """Serve the kickoff web app on the loopback (R1-S8). Blocks until interrupted.

    Runs preflight first and refuses on a blocking failure. The scratch GC reclaims stale app
    fingerprints before serving (R5-S8). When *agent_spec* resolves, the web agentic chat panel
    (`/concierge/chat`) is enabled (spends LLM tokens); else the panel shows a disabled notice.
    """
    from .web import build_kickoff_app

    if mode not in Mode.ALL:
        raise ValueError(f"unknown mode {mode!r}; one of {Mode.ALL}")
    cfg = config or default_config()
    pf = preflight(project_root, mode=mode, config=cfg)
    if not pf.ok:
        failed = [c.name for c in pf.checks if c.blocking and not c.ok]
        raise RuntimeError(f"kickoff preflight failed: {failed}")

    gc_stale_scratch(project_root, app_fingerprint(cfg, theme=theme))
    chat_factory = (make_chat_factory(project_root, agent_spec, red_carpet=red_carpet)
                    if agent_spec else None)
    app = build_kickoff_app(project_root, config=cfg, theme=theme, mode=mode,
                            chat_factory=chat_factory)
    bind_port = port or find_free_port(host)

    import uvicorn

    uvicorn.run(app, host=host, port=bind_port)
