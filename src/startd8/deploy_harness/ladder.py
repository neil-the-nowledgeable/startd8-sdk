"""Graded-ladder result model for the local deploy harness.

The harness runs a generated app through a fixed ladder of stages and records, per stage, whether
it ``passed``, ``failed``, was ``skipped`` (with a typed reason), or was ``not_reached``. The whole
point — see ``docs/design/local-deploy-harness/`` — is cross-model *comparison* of raw LLM output,
so every result carries enough provenance (entry-point derivation, dep source, deviations) and
environment (:class:`HarnessEnv`) to make a ``fail`` attributable to the model and *reproducible*,
not confounded with harness flakiness (CRP R1-F9/S6).

M0 ships the data model only; the live stages (install/boot/health/smoke) are populated in M1+.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Stage(str, Enum):
    """The ordered rungs of the deploy ladder. ``order`` drives ``highest_stage`` computation."""

    DISCOVER = "discover"
    INSTALL = "install"
    BOOT = "boot"
    HEALTH = "health"
    SMOKE = "smoke"
    CONTEXT_SMOKE = "context_smoke"

    @property
    def order(self) -> int:
        return _STAGE_ORDER[self]


_STAGE_ORDER: Dict[Stage, int] = {
    Stage.DISCOVER: 0,
    Stage.INSTALL: 1,
    Stage.BOOT: 2,
    Stage.HEALTH: 3,
    Stage.SMOKE: 4,
    Stage.CONTEXT_SMOKE: 5,
}


class StageStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"
    NOT_REACHED = "not_reached"


class StageResult(BaseModel):
    """Outcome of a single rung. ``reason`` is a typed, machine-greppable string on non-pass."""

    status: StageStatus
    reason: Optional[str] = None
    ms: Optional[float] = None


class Deviation(BaseModel):
    """A recorded departure from the canonical SDK layout — graded, never fatal (FR-1/2/3)."""

    code: str  # e.g. "entrypoint-noncanonical", "deps-missing", "mode-ambiguous"
    detail: str


class EntryPoint(BaseModel):
    """The detected ASGI target plus how confidently it was found (CRP R1-F8/S5)."""

    target: Optional[str] = None  # "module:attr", e.g. "app.main:app"
    matched_by: str = "none"  # manifest | app-package-default | candidate | scan | none
    # ``scan``/``candidate`` are lower confidence than ``manifest``; ambiguity → a Deviation.


class HarnessEnv(BaseModel):
    """Environment captured so a ``fail`` is reproducible and not harness flakiness (CRP R1-F9/S6).

    All optional — populated by the live stages in M1+; absent in a discover-only (M0) result.
    """

    install_timeout_s: Optional[float] = None
    boot_timeout_s: Optional[float] = None
    venv_python_version: Optional[str] = None
    installed_deps: Optional[List[str]] = None  # `pip freeze` output
    pip_index_url: Optional[str] = None
    network_reachable: Optional[bool] = None
    port: Optional[int] = None


# Deployment-mode constants (mirror backend_codegen; "unknown" is harness-only — see discovery).
MODE_INSTALLED = "installed"
MODE_DEPLOYED = "deployed"
MODE_UNKNOWN = "unknown"


class LadderResult(BaseModel):
    """The per-app graded result (FR-11). One of these per deployed app; aggregated in batch (FR-12)."""

    app_root: str
    model: Optional[str] = (
        None  # verbatim model id from sidecar (FR-12); None for ad-hoc runs
    )
    mode: str = MODE_INSTALLED
    mode_derivation: str = "default"  # header | default | ambiguous
    entrypoint: EntryPoint = Field(default_factory=EntryPoint)
    dep_source: str = (
        "none"  # requirements.txt | pyproject:project | pyproject:poetry | dep_floor | none
    )
    highest_stage: str = Stage.DISCOVER.value
    stages: Dict[str, StageResult] = Field(default_factory=dict)
    deviations: List[Deviation] = Field(default_factory=list)
    harness_env: HarnessEnv = Field(default_factory=HarnessEnv)
    log_paths: Dict[str, str] = Field(default_factory=dict)
    outbound_context_smoke: Dict[str, StageResult] = Field(default_factory=dict)

    # ---- builder helpers (used by the stage orchestration in M1+) ----

    def record(
        self,
        stage: Stage,
        status: StageStatus,
        *,
        reason: Optional[str] = None,
        ms: Optional[float] = None,
    ) -> "LadderResult":
        """Record a stage outcome and advance ``highest_stage`` to the furthest rung *reached*.

        A rung is "reached" whether it passed, failed, or was skipped — i.e. the ladder got to it.
        ``highest_stage`` is therefore the max ``order`` over all recorded stages.
        """
        self.stages[stage.value] = StageResult(status=status, reason=reason, ms=ms)
        if stage.order >= Stage(self.highest_stage).order:
            self.highest_stage = stage.value
        return self

    def add_deviation(self, code: str, detail: str) -> "LadderResult":
        self.deviations.append(Deviation(code=code, detail=detail))
        return self

    def to_json(self, *, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    def summary(self) -> str:
        """One-line human roll-up: ``<root> mode=installed highest=health [install:pass boot:pass …]``."""
        rungs = " ".join(
            f"{name}:{self.stages[name].status.value}"
            for name in (s.value for s in Stage)
            if name in self.stages
        )
        return (
            f"{self.app_root} model={self.model or '-'} mode={self.mode} "
            f"highest={self.highest_stage} [{rungs}]"
        )
