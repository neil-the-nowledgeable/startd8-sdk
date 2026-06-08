"""Runtime boot-smoke gate for generated FastAPI apps (C-6, Layer 1).

The deterministic, ``$0`` half of C-6: actually **boot** a generated app and confirm it serves
``GET /openapi.json``, listing the expected routes. This catches the class that ``compileall``/``mypy``
and structural scoring demonstrably miss — wrong imports that pass syntax but fail at import
(run-021/023/024 ``routes.py``; run-025's non-importing ``app/ai/*`` modules; the "PASS 0.86 was
hollow" gap).

Why a **subprocess**, not in-process: importing a generated ``app`` package in this process pollutes
``sys.modules`` and needs path/cache surgery (see ``tests/.../test_runtime_smoke.py``). A subprocess is
isolated and mirrors how ``python_toolchain`` already shells its stages.

Absent app deps (``fastapi``/``sqlmodel`` not installed) ⇒ ``unavailable`` ⇒ **non-pass**, never a
silent skip (NFR-MA-2 / FR-9). Layers 2 (transcript-backed per-pass exercise) and 3 (``--live-smoke``)
land with the AI layer (M-C) and are out of scope here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Runs inside the subprocess. Reports a single JSON line on stdout. Categorizes "deps missing"
# (unavailable) distinctly from "app failed to boot" (fail) so the gate never green-skips.
# The subprocess prints exactly one result line, prefixed with this sentinel, so app stdout/logging
# (which may itself be JSON-shaped) can never be mistaken for our result (M3).
_SENTINEL = "__BOOT_SMOKE__"

_BOOT_SCRIPT = r'''
import json, sys, importlib
SENTINEL = "__BOOT_SMOKE__"
def emit(d): print(SENTINEL + json.dumps(d))
spec = sys.argv[1]
try:
    from fastapi.testclient import TestClient  # noqa: F401
except Exception as e:  # deps not provisioned in this env
    emit({"status": "unavailable", "reason": "fastapi/TestClient unavailable: %s" % e})
    sys.exit(0)
mod, _, attr = spec.partition(":")
attr = attr or "app"
try:
    m = importlib.import_module(mod)
    app = getattr(m, attr)
    from fastapi.testclient import TestClient
    with TestClient(app) as c:  # context manager triggers lifespan -> init_db
        r = c.get("/openapi.json")
        paths = sorted((r.json().get("paths") or {}).keys()) if r.status_code == 200 else []
        emit({"status": "checked", "ok": r.status_code == 200,
              "status_code": r.status_code, "paths": paths})
except Exception as e:
    import traceback
    emit({"status": "checked", "ok": False,
          "error": "%s: %s" % (type(e).__name__, e),
          "trace": traceback.format_exc()[-1500:]})
'''


@dataclass
class BootSmokeResult:
    """Outcome of booting a generated app and inventorying its routes.

    ``status``: ``checked`` (booted) | ``unavailable`` (deps missing — NOT a pass) |
    ``timeout`` | ``error``. ``ok`` is the in-subprocess boot result; ``missing_routes`` are
    ``expected_routes`` not found in the served OpenAPI.
    """

    status: str
    ok: bool = False
    routes: Tuple[str, ...] = ()
    missing_routes: Tuple[str, ...] = ()
    message: str = ""
    diagnostics: List[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """``pass`` | ``fail`` | ``unavailable``."""
        if self.status == "unavailable":
            return "unavailable"
        if self.status != "checked":
            return "fail"
        return "pass" if (self.ok and not self.missing_routes) else "fail"

    @property
    def is_pass(self) -> bool:
        return self.verdict == "pass"


def resolve_app_target(project_root: str, *, package: Optional[str] = None) -> Optional[str]:
    """Resolve the ASGI ``module:attr`` target for a generated app (F-5, RUN-008 1a-iii).

    The gate must never hardcode one variant: the deterministic cascade emits
    ``{package}.main:app``, while ``--ai-passes`` additionally emits ``{package}/server.py``
    (the AI composition entrypoint, which wraps ``main`` and mounts the AI router). A healthy
    app must be able to pass the gate regardless of which variant was generated.

    Resolution order:

    1. *package* — when not given, read ``app.yaml`` (the scaffold manifest,
       :class:`~startd8.scaffold_codegen.manifest.AppManifest.package`) from the project root
       or ``prisma/app.yaml``; default ``"app"``.
    2. ``{package}/server.py`` on disk → ``{package}.server:app`` (superset entrypoint).
    3. ``{package}/main.py`` on disk → ``{package}.main:app``.
    4. Neither exists → ``None`` (nothing bootable to gate).
    """
    root = Path(project_root)
    if package is None:
        package = "app"
        for manifest_path in (root / "app.yaml", root / "prisma" / "app.yaml"):
            if manifest_path.is_file():
                try:
                    from startd8.scaffold_codegen.manifest import parse_app_manifest

                    package = parse_app_manifest(
                        manifest_path.read_text(encoding="utf-8")
                    ).package
                except Exception as exc:  # malformed manifest → conventional default
                    logger.debug(
                        "boot-smoke: could not read package from %s (%s); using 'app'",
                        manifest_path,
                        exc,
                    )
                break
    pkg_dir = root.joinpath(*package.split("."))
    if (pkg_dir / "server.py").is_file():
        return f"{package}.server:app"
    if (pkg_dir / "main.py").is_file():
        return f"{package}.main:app"
    return None


def run_boot_smoke(
    project_root: str,
    *,
    app: Optional[str] = None,
    expected_routes: Optional[List[str]] = None,
    timeout: int = 60,
) -> BootSmokeResult:
    """Boot *app* from *project_root* in a subprocess; confirm it serves ``/openapi.json``.

    *app* is a ``module:attr`` spec. When ``None`` (the default) the target is resolved via
    :func:`resolve_app_target` — scaffold-manifest package, then ``{package}.server:app`` if
    ``server.py`` exists on disk, else ``{package}.main:app`` — so the gate matches whichever
    variant was actually generated instead of hardcoding one (F-5). *expected_routes*
    (optional) are OpenAPI paths that MUST be present — e.g. each declared AI pass route.
    Returns a :class:`BootSmokeResult`; ``unavailable`` (deps missing) is a **non-pass**,
    never silently green.
    """
    root = Path(project_root)
    if not root.exists():
        return BootSmokeResult(status="error", message=f"path not found: {root}")

    if app is None:
        app = resolve_app_target(project_root)
        if app is None:
            return BootSmokeResult(
                status="error",
                message=(
                    f"no app entrypoint found under {root} "
                    "(looked for {package}/server.py and {package}/main.py)"
                ),
            )

    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "_boot_smoke.py"
        script.write_text(_BOOT_SCRIPT, encoding="utf-8")
        db_path = Path(tmp) / "smoke.db"
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(root), os.environ.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        try:
            proc = subprocess.run(
                [sys.executable, str(script), app],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return BootSmokeResult(status="timeout", message=f"boot smoke timed out ({app})")
        except OSError as exc:
            return BootSmokeResult(status="error", message=str(exc))

    out = (proc.stdout or "").strip().splitlines()
    payload = None
    for line in reversed(out):  # our sentinel-prefixed line — immune to app stdout/logging (M3)
        if _SENTINEL in line:
            try:
                payload = json.loads(line.split(_SENTINEL, 1)[1])
                break
            except ValueError:
                continue
    if payload is None:
        return BootSmokeResult(
            status="error",
            message="boot smoke produced no parseable result",
            diagnostics=[(proc.stdout or "")[-800:], (proc.stderr or "")[-800:]],
        )

    if payload.get("status") == "unavailable":
        return BootSmokeResult(status="unavailable", message=payload.get("reason", ""))

    ok = bool(payload.get("ok"))
    routes = tuple(payload.get("paths") or ())
    missing = tuple(r for r in (expected_routes or []) if r not in routes)
    diags: List[str] = []
    if not ok:
        diags.append(payload.get("error", "boot failed"))
        if payload.get("trace"):
            diags.append(payload["trace"])
    return BootSmokeResult(
        status="checked",
        ok=ok,
        routes=routes,
        missing_routes=missing,
        message=("booted" if ok else payload.get("error", "boot failed")),
        diagnostics=diags,
    )
