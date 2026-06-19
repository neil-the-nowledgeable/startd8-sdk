"""Ladder orchestration: walk one generated app discover→install→boot→health→smoke (FR-11).

The public entry point, :func:`deploy_app_local`. Everything is graded — a non-canonical app, a
failed install, a dead boot, or a failed smoke-CRUD all produce a populated :class:`LadderResult`,
never an exception. Smoke (FR-9/10) is best-effort; pass ``do_smoke=False`` to stop after health.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

from startd8.logging_config import get_logger

from .discovery import detect_deps, detect_entrypoint, detect_mode
from .ladder import (
    MODE_INSTALLED,
    HarnessEnv,
    LadderResult,
    Stage,
    StageStatus,
)
from .server import LiveServer
from .smoke import run_smoke
from .context_smoke import (
    aggregate_outbound_smoke,
    run_outbound_context_smokes,
)
from .venv_runner import ResourceLimits, Venv, create_venv, install_deps

logger = get_logger("startd8.deploy_harness.deploy")

# Map a SmokeOutcome.status string onto the ladder StageStatus.
_SMOKE_STATUS = {
    "pass": StageStatus.PASS,
    "fail": StageStatus.FAIL,
    "skipped": StageStatus.SKIPPED,
}


def deploy_app_local(
    app_root: Path | str,
    *,
    model: Optional[str] = None,
    install_timeout_s: float = 600.0,
    boot_timeout_s: float = 60.0,
    keep: bool = False,
    do_smoke: bool = True,
    do_context_smoke: bool = True,
    limits: Optional[ResourceLimits] = None,
    runner_python: Optional[str] = None,
    editable_installs: Optional[list[str]] = None,
    work_parent: Optional[Path] = None,
) -> LadderResult:
    """Deploy one generated app locally and return its graded :class:`LadderResult`.

    ``runner_python`` — when given, skip venv creation and use this interpreter (it must already have
    the app's deps + uvicorn). Used by fast tests and power users with a prepared env; default
    ``None`` builds a throwaway venv and installs into it (the untrusted-code path, FR-4/5).
    """
    root = Path(app_root).resolve()
    result = LadderResult(app_root=str(root), model=model)
    result.harness_env = HarnessEnv(
        install_timeout_s=install_timeout_s,
        boot_timeout_s=boot_timeout_s,
    )
    limits = limits or ResourceLimits()

    # ---- discover (FR-1/2/3) ----
    entry, e_devs = detect_entrypoint(root)
    dep, d_devs = detect_deps(root)
    mode, mode_deriv, m_devs = detect_mode(root)
    for dv in (*e_devs, *d_devs, *m_devs):
        result.add_deviation(dv.code, dv.detail)
    result.entrypoint = entry
    result.dep_source = dep.source
    result.mode = mode
    result.mode_derivation = mode_deriv

    if entry.target is None:
        result.record(Stage.DISCOVER, StageStatus.FAIL, reason="entrypoint-missing")
        return result
    result.record(Stage.DISCOVER, StageStatus.PASS)

    # Working dir for venv + logs (outside the app root, FR-4). Throwaway unless --keep.
    work = (
        Path(work_parent)
        if work_parent
        else Path(tempfile.mkdtemp(prefix="startd8-deploy-"))
    )
    work.mkdir(parents=True, exist_ok=True)
    cleanup = (not keep) and (work_parent is None)
    try:
        # ---- install (FR-5/16/17) ----
        if runner_python is not None:
            venv_obj = Venv(
                root=Path(runner_python).parent.parent, python=Path(runner_python)
            )
            result.record(
                Stage.INSTALL, StageStatus.SKIPPED, reason="skipped:prepared-env"
            )
        else:
            t0 = time.monotonic()
            venv_obj = create_venv(work)
            outcome = install_deps(
                venv_obj,
                dep.packages,
                timeout_s=install_timeout_s,
                limits=limits,
                log_path=work / "install.log",
                editable_installs=editable_installs,
            )
            result.harness_env.installed_deps = outcome.freeze
            result.harness_env.pip_index_url = outcome.index_url
            result.harness_env.network_reachable = outcome.ok or None
            if outcome.log_path:
                result.log_paths["install"] = outcome.log_path
            result.record(
                Stage.INSTALL,
                StageStatus.PASS if outcome.ok else StageStatus.FAIL,
                reason=outcome.reason,
                ms=(time.monotonic() - t0) * 1000,
            )
            if not outcome.ok:
                return result

        result.harness_env.venv_python_version = venv_obj.python_version

        # ---- boot (FR-6/8) — installed mode only; deployed/unknown can't self-bootstrap a DB ----
        if mode != MODE_INSTALLED:
            reason = (
                "skipped:deployed-needs-db"
                if mode == "deployed"
                else "skipped:mode-unknown"
            )
            result.record(Stage.BOOT, StageStatus.SKIPPED, reason=reason)
            return result

        log_path = work / "server.log"
        t0 = time.monotonic()
        with LiveServer(
            venv_obj.python,
            entry.target,
            root,
            boot_timeout_s=boot_timeout_s,
            limits=limits,
            throwaway_home=work,
            log_path=log_path,
        ) as boot:
            boot_ms = (time.monotonic() - t0) * 1000
            result.harness_env.port = boot.port
            result.log_paths["server"] = str(log_path)
            if not boot.booted:
                result.record(
                    Stage.BOOT, StageStatus.FAIL, reason=boot.boot_reason, ms=boot_ms
                )
                return result
            result.record(Stage.BOOT, StageStatus.PASS, ms=boot_ms)

            # ---- health (FR-7) ----
            if boot.health_ok:
                reason = (
                    "pass:liveness-only" if boot.quality == "liveness-only" else None
                )
                result.record(Stage.HEALTH, StageStatus.PASS, reason=reason)
            else:
                result.record(Stage.HEALTH, StageStatus.FAIL, reason=boot.health_reason)
                return result

            # ---- smoke (FR-9/10) ----
            if not do_smoke:
                result.record(
                    Stage.SMOKE, StageStatus.SKIPPED, reason="skipped:smoke-disabled"
                )
            else:
                t0 = time.monotonic()
                sm = run_smoke(f"http://127.0.0.1:{boot.port}")
                result.record(
                    Stage.SMOKE,
                    _SMOKE_STATUS[sm.status],
                    reason=sm.reason,
                    ms=(time.monotonic() - t0) * 1000,
                )

            # ---- context smoke (Role 3 remote/deployed producers) ----
            if not do_context_smoke:
                result.record(
                    Stage.CONTEXT_SMOKE,
                    StageStatus.SKIPPED,
                    reason="skipped:context-smoke-disabled",
                )
            else:
                t0 = time.monotonic()
                outbound = run_outbound_context_smokes(root, loopback_port=boot.port)
                for item in outbound:
                    result.outbound_context_smoke[item.producer_id] = StageResult(
                        status=_SMOKE_STATUS[item.outcome.status],
                        reason=item.outcome.reason,
                    )
                status, reason = aggregate_outbound_smoke(outbound)
                result.record(
                    Stage.CONTEXT_SMOKE,
                    _SMOKE_STATUS[status],
                    reason=reason,
                    ms=(time.monotonic() - t0) * 1000,
                )
        return result
    finally:
        if cleanup:
            shutil.rmtree(work, ignore_errors=True)
