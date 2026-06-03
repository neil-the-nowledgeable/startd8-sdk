# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Report assembly + persistence (FR-9).

Writes ``semantic-compliance-report.json`` (authoritative) + ``.md`` (human render). The JSON is
**round-trip-safe by construction** — verdict/confidence/inconclusive_reason are stored flat on each
feature, NOT inside the ``SemanticVerificationResult`` ``"verification"`` envelope that would silently
reload as ``inconclusive`` (R1-S1). Atomic write + ``status: pending|complete`` so a detached SCR
never lets the SA fold read a partial file (R2-S3). Stores file paths only, never raw code (R4-S3).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ..logging_config import get_logger
from ..utils.file_operations import atomic_write_json
from .models import SemanticComplianceReport, Verdict

logger = get_logger(__name__)

REPORT_JSON = "semantic-compliance-report.json"
REPORT_MD = "semantic-compliance-report.md"


def write_report(report: SemanticComplianceReport, output_dir: Path) -> Path:
    """Atomically write the JSON + MD artifacts; return the JSON path."""
    output_dir = Path(output_dir)
    json_path = output_dir / REPORT_JSON
    atomic_write_json(json_path, report.to_dict(), indent=2)
    (output_dir / REPORT_MD).write_text(render_markdown(report), encoding="utf-8")
    logger.info("SCR report: %s (status=%s)", json_path, report.status)
    return json_path


def write_pending(output_dir: Path, run_id: str, scr_version: str) -> Path:
    """Drop a minimal ``status: pending`` marker before a detached review starts (R2-S3)."""
    payload = {"schema_version": "1.0", "status": "pending", "run": {"run_id": run_id}, "scr_version": scr_version}
    path = Path(output_dir) / REPORT_JSON
    atomic_write_json(path, payload, indent=2)
    return path


def render_markdown(report: SemanticComplianceReport) -> str:
    s = report.summary
    cost = f" · Cost: ${s.cost_usd:.4f}" if s.cost_usd is not None else ""
    agg = f"{s.semantic_compliance_aggregate:.2f}" if s.semantic_compliance_aggregate is not None else "—"
    lines: List[str] = [
        f"# Semantic Compliance Report — {report.run_id}",
        "",
        f"**Status:** {report.status} · **Aggregate compliance:** {agg}{cost}",
        f"Reviewed {s.reviewed}/{s.total_features} features ({s.escalated} escalated). "
        f"pass {s.pass_} · fail {s.fail} · inconclusive {s.inconclusive}.",
        "",
    ]
    if s.inconclusive_rate_exceeded:
        lines += [f"> ⚠️ Inconclusive rate {s.inconclusive_rate:.0%} exceeds the bound — SYSTEM_WARNING emitted.", ""]

    fails = [f for f in report.features if f.verdict.verdict == Verdict.FAIL]
    if fails:
        lines += ["## Failed / low-compliance features", "",
                  "| Feature | Conf | Score | Requirement violation |",
                  "|---------|------|-------|-----------------------|"]
        for f in fails:
            top = f.issues[0].description if f.issues else f.verdict.verdict.value
            score = f"{f.semantic_compliance_score:.2f}" if f.semantic_compliance_score is not None else "—"
            lines.append(f"| `{f.feature_id}` | {f.verdict.confidence:.2f} | {score} | {top} |")
        lines.append("")

    inconclusive = [f for f in report.features if f.verdict.verdict == Verdict.INCONCLUSIVE]
    if inconclusive:
        lines += ["## Inconclusive", "", "| Feature | Reason |", "|---------|--------|"]
        for f in inconclusive:
            reason = f.verdict.inconclusive_reason.value if f.verdict.inconclusive_reason else "—"
            lines.append(f"| `{f.feature_id}` | {reason} |")
        lines.append("")

    if report.cross_feature_patterns:
        lines += ["## Cross-feature patterns", ""]
        for p in report.cross_feature_patterns:
            lines.append(f"- **{p.pattern_type}** ({p.severity}): {p.description} "
                         f"— {', '.join(p.affected_features)}")
        lines.append("")

    lines += ["_Advisory — fed to Kaizen for the next run; no run blocked._", ""]
    return "\n".join(lines)
