"""FR-SAP-9 — host integration entry point (the cross-task output channel).

``domain-preflight``'s native output is per-task ``TaskEnrichment``; the Sapper friction report
is **cross-task** (it ranks across the whole plan). So this module is the *new* output channel
(requirements §0.9 discovery #4): given the in-memory ForwardManifest + skeleton_sources the
EMIT stage already produced, it runs the gate, writes the report artifact, emits metrics, and
returns the downstream-injection block.

A ``domain-preflight`` host calls ``sapper_preflight_hook(...)`` after classify/check; it does
not need to thread the report through ``TaskEnrichment``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from startd8.logging_config import get_logger

from .gate import SapperGateResult, run_sapper_gate
from .report import build_injection_block, emit_metrics, write_report

logger = get_logger(__name__)


@dataclass
class SapperPreflightOutcome:
    result: SapperGateResult
    artifacts: Dict[str, str]
    metrics: Dict[str, object]
    injection_block: str

    @property
    def blocked(self) -> bool:
        return self.result.blocked


def sapper_preflight_hook(
    manifest,
    skeleton_sources: Optional[dict],
    *,
    project_root: Optional[str] = None,
    out_dir: Optional[str] = None,
    fde=None,
) -> SapperPreflightOutcome:
    """Run the survey and deliver the report. The single seam a host stage calls (FR-SAP-9).

    Returns the gate result, written artifact paths (if ``out_dir`` given), the metric payload,
    and the prompt-injection block to fold into downstream generation prompts (FR-SAP-12).
    """
    result = run_sapper_gate(manifest, skeleton_sources, project_root, fde=fde)
    artifacts: Dict[str, str] = {}
    if out_dir:
        artifacts = write_report(result.report, out_dir)
    metrics = emit_metrics(result.report)
    injection = build_injection_block(result.report)

    logger.info(
        "sapper preflight complete",
        extra={
            "findings": len(result.report.findings),
            "unresolved_rate": result.report.unresolved_rate(),
            "bore_status": result.report.bore_status,
            "blocked": result.blocked,
        },
    )
    return SapperPreflightOutcome(
        result=result, artifacts=artifacts, metrics=metrics, injection_block=injection
    )
