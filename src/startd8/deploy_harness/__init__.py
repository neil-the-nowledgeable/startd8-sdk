"""Local deployment + graded-validation harness for SDK-generated apps.

Takes a generated app root (raw LLM output from a PrimeContractor run — *not* assumed canonical) and
runs it through a graded ladder ``discover → install → boot → health → smoke-CRUD``, recording a
typed reason per rung for cross-model code-quality comparison in the Summer 2026 benchmark.

**Trust boundary (v1):** the apps under test are UNTRUSTED. v1 isolation is throwaway-venv +
subprocess + loopback bind + resource limits + timeouts — **not** a kernel sandbox. The first
arbitrary-code-execution surface is ``pip install`` (PEP 517 build hooks run before any boot
timeout), so the v1 containment line is drawn at install, with full containment deferred to the
v2/FR-44 Docker upgrade. See ``docs/design/local-deploy-harness/`` (Requirements FR-15..18).

M0 (shipped): tolerant discovery + the result data model. M1+ adds the live stages.
"""

from __future__ import annotations

from .deploy import deploy_app_local
from .discovery import (
    DEP_FLOOR,
    DepDetection,
    detect_deps,
    detect_entrypoint,
    detect_mode,
)
from .server import BootOutcome, LiveServer, free_port
from .smoke import (
    SmokeOutcome,
    run_smoke,
    select_crud_resource,
    synthesize_body,
)
from .venv_runner import InstallOutcome, ResourceLimits, Venv, create_venv, install_deps
from .ladder import (
    Deviation,
    EntryPoint,
    HarnessEnv,
    LadderResult,
    MODE_DEPLOYED,
    MODE_INSTALLED,
    MODE_UNKNOWN,
    Stage,
    StageResult,
    StageStatus,
)

__all__ = [
    # orchestration (FR-11)
    "deploy_app_local",
    # discovery (FR-1/2/3)
    "detect_entrypoint",
    "detect_deps",
    "detect_mode",
    "DepDetection",
    "DEP_FLOOR",
    # live stages (FR-4/5/6/7/8/16)
    "create_venv",
    "install_deps",
    "Venv",
    "InstallOutcome",
    "ResourceLimits",
    "LiveServer",
    "BootOutcome",
    "free_port",
    # smoke (FR-9/10)
    "run_smoke",
    "select_crud_resource",
    "synthesize_body",
    "SmokeOutcome",
    # result model (FR-11)
    "LadderResult",
    "Stage",
    "StageStatus",
    "StageResult",
    "EntryPoint",
    "Deviation",
    "HarnessEnv",
    "MODE_INSTALLED",
    "MODE_DEPLOYED",
    "MODE_UNKNOWN",
]
