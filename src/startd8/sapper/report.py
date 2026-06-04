"""FR-SAP-12 — report delivery & observability.

An advisory report only has value if it reaches a reader:
- (a) ``build_injection_block`` renders the findings into a prompt block forwarded into the
  downstream generation prompts (lead/drafter and micro-prime) so the generator is warned.
- (b) ``emit_metrics`` produces OTel-shaped metrics (``sapper.findings.count{...}``,
  ``unresolved_rate``, ``bore_degraded``) — best-effort, no-op if no meter is wired.

Plus ``write_report`` for the ``sapper-friction-report.json`` + ``.md`` artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from startd8.logging_config import get_logger

from .models import AssumptionVerdict, FrictionReport, UnresolvedReason

logger = get_logger(__name__)

JSON_NAME = "sapper-friction-report.json"
MD_NAME = "sapper-friction-report.md"


def write_report(report: FrictionReport, out_dir: str) -> Dict[str, str]:
    """Write the JSON + MD artifacts; return the written paths."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    json_path = d / JSON_NAME
    md_path = d / MD_NAME
    json_path.write_text(report.to_json(), encoding="utf-8")
    md_path.write_text(report.to_markdown(), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def build_injection_block(report: FrictionReport, *, limit: int = 12) -> str:
    """Render the top findings as a warning block for downstream generation prompts (R3-F2).

    Empty when there is nothing to warn about (so injection is additive / no-op on clean plans).
    """
    actionable = [f for f in report.ranked if f.verdict in (AssumptionVerdict.REFUTED, AssumptionVerdict.UNRESOLVED)]
    if not actionable:
        return ""
    lines = [
        "## ⚠️ Pre-execution alignment (Sapper) — heed before implementing",
        "The plan was surveyed against the real codebase. Do NOT reproduce these misalignments:",
    ]
    for f in actionable[:limit]:
        tag = f.verdict.value.upper() + (f"/{f.reason.value}" if f.reason else "")
        fix = f"  → {f.suggested_fix}" if f.suggested_fix else ""
        lines.append(f"- [{tag}] `{f.file}`: {f.expected} (found: {f.found}){fix}")
    if len(actionable) > limit:
        lines.append(f"- …and {len(actionable) - limit} more (see {JSON_NAME}).")
    return "\n".join(lines)


def emit_metrics(report: FrictionReport, *, meter=None) -> Dict[str, object]:
    """Compute (and best-effort emit) the observability metrics (R2-F4/R1-F6/R5-F5).

    Returns the metric payload regardless of whether a meter is available, so callers/tests
    can assert on it. ``bore_degraded_count`` spiking is the silent-toolchain-breakage signal.
    """
    bore_degraded = sum(
        1 for f in report.unresolved if f.reason is UnresolvedReason.BORE_DEGRADED
    )
    payload: Dict[str, object] = {
        "sapper.findings.count": len(report.findings),
        "sapper.findings.by_verdict": report.counts(),
        "sapper.findings.by_reason": report.reason_breakdown(),
        "sapper.unresolved_rate": report.unresolved_rate(),
        "sapper.bore_degraded_count": bore_degraded,
        "sapper.bore_status": report.bore_status,
    }
    _try_emit(payload, meter)
    if bore_degraded:
        logger.warning(
            "sapper bore_degraded findings present — possible silent toolchain breakage",
            extra={"bore_degraded_count": bore_degraded},
        )
    return payload


def _try_emit(payload: Dict[str, object], meter) -> None:
    if meter is None:
        try:  # pragma: no cover - depends on otel runtime
            from opentelemetry import metrics  # type: ignore

            meter = metrics.get_meter("startd8.sapper")
        except Exception:
            return
    try:  # pragma: no cover - depends on otel runtime
        counter = meter.create_counter("sapper.findings.count")
        counter.add(int(payload["sapper.findings.count"]))
        gauge_val = float(payload["sapper.unresolved_rate"])  # noqa: F841
    except Exception:
        logger.debug("sapper metric emit skipped (no usable meter)")
