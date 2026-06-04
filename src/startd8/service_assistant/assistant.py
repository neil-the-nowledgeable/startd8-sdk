"""Service Assistant facade — orchestrates detect -> enrich -> triage -> notify -> write.

This is the one-shot bridge between a project built with the SDK and the SDK itself
(FR-11). It is invoked after each cap-dev-pipe Prime Contractor run; it detects the
new run/post-mortem artifacts, synthesizes a project-contextualized triage report with
recommended actions (it never executes them), notifies via EventBus, and writes the
authoritative triage artifact.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import __version__
from ..logging_config import get_logger
from . import detector as _detector
from .context import load_project_context
from .models import (
    CursorInfo,
    Detection,
    RunInfo,
    Summary,
    TriageReport,
)
from .notify import emit_events
from .triage import synthesize_triage

logger = get_logger(__name__)

TRIAGE_JSON = "service-assistant-triage.json"
TRIAGE_MD = "service-assistant-triage.md"


class ServiceAssistant:
    """Detect, triage, and relay a completed Prime Contractor run."""

    def __init__(self, *, emit: bool = True, write_artifact: bool = True) -> None:
        self.emit = emit
        self.write_artifact = write_artifact

    def process(self, output_dir: Path, run_id: Optional[str] = None) -> Optional[TriageReport]:
        """Run one detect->triage->notify->write cycle for a run output dir.

        Returns the :class:`TriageReport` produced, or ``None`` when there is nothing
        actionable yet (no run sentinel and no abort) or the run was already processed
        (idempotent no-op, FR-3).
        """
        output_dir = Path(output_dir)
        detection = _detector.detect_run(output_dir, run_id)

        if not detection.actionable:
            logger.info(
                "Service Assistant: nothing actionable in %s (status=%s)",
                output_dir,
                detection.status,
            )
            return None

        seen, cursor_path = _detector.already_processed(detection)
        if seen:
            logger.info(
                "Service Assistant: run %s already processed (idempotent no-op)", detection.run_id
            )
            return None

        project_context = load_project_context(output_dir)
        verdict, failures, patterns, batch = synthesize_triage(detection)

        triage_path = output_dir / TRIAGE_JSON
        emitted = []
        if self.emit:
            emitted = emit_events(
                detection, verdict, str(triage_path), project_context.project_id
            )

        report = TriageReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            assistant_version=__version__,
            run=RunInfo(
                run_id=detection.run_id,
                output_dir=str(output_dir),
                status=detection.status,
                detected_at=datetime.now(timezone.utc).isoformat(),
            ),
            detection=Detection(
                run_sentinel_present=detection.run_sentinel_present,
                postmortem_present=detection.postmortem_present,
                state_file_present=detection.state_file_present,
                hard_abort=detection.hard_abort,
                features_attempted=detection.features_attempted,
                aux_signals=detection.aux_signals,
            ),
            verdict=verdict,
            project_context=project_context,
            failures=failures,
            cross_feature_patterns=patterns,
            batch=batch,
            events_emitted=emitted,
            cursor=CursorInfo(
                cursor_path=str(cursor_path),
                previously_processed=False,
                run_checksum=detection.checksum,
            ),
            summary=_build_summary(detection, verdict, failures),
            semantic_review=_fold_semantic_review(output_dir),
        )

        if self.write_artifact:
            self._write(output_dir, report)

        # Only record the cursor once the run is fully resolved (post-mortem present or
        # aborted). A bare result with no post-mortem yet stays re-processable (FR-4).
        if detection.postmortem_present or detection.hard_abort:
            _detector.record_processed(detection, cursor_path)

        return report

    def _write(self, output_dir: Path, report: TriageReport) -> None:
        (output_dir / TRIAGE_JSON).write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
        (output_dir / TRIAGE_MD).write_text(_render_markdown(report), encoding="utf-8")
        logger.info("Service Assistant triage: %s", output_dir / TRIAGE_JSON)


def _fold_semantic_review(output_dir: Path):
    """Fold an existing Semantic Compliance Reviewer report into the triage artifact (FR-12).

    Read-only: the SA surfaces the SCR report if one is present; it does not launch the reviewer
    here (auto-launch is gated/deferred to avoid surprise spend — see semantic_compliance/)."""
    import json

    from .models import SemanticReviewRef

    path = output_dir / "semantic-compliance-report.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    summary = data.get("summary", {}) or {}
    return SemanticReviewRef(
        status=str(data.get("status", "complete")),
        report_path=str(path),
        aggregate=summary.get("semantic_compliance_aggregate"),
        fail=int(summary.get("fail", 0) or 0),
        inconclusive=int(summary.get("inconclusive", 0) or 0),
    )


def _build_summary(detection, verdict, failures) -> Summary:
    v = verdict
    cost = f" (${v.total_cost_usd:.2f})" if v.total_cost_usd else ""
    headline = (
        f"{detection.run_id} {v.aggregate_verdict}: {v.succeeded}/{v.total_features} "
        f"features passed{cost}."
    )
    if failures:
        persistent = sum(1 for f in failures if f.persistent)
        headline += f" {len(failures)} failure(s)"
        if persistent:
            headline += f", {persistent} persistent across the batch"
        headline += "."
    top = None
    if failures:
        # Skip-filter (Coyote): actionable failures rank above non-actionable ones,
        # so an environmental/transient cause never becomes the headline recommendation
        # when a genuine code/spec fix is available.
        ordered = sorted(
            failures,
            key=lambda f: (
                not f.actionable,
                {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(f.severity, 4),
                not f.persistent,
            ),
        )
        worst = ordered[0]
        flags = "critical" if worst.severity == "critical" else worst.severity
        if worst.deterministic:
            flags += ", deterministic"
        if worst.persistent:
            flags += ", persistent"
        if not worst.actionable:
            flags += ", not actionable"
        top = f"{worst.feature_id} ({flags}): {worst.recommended_action.action}"
    return Summary(headline=headline, top_recommendation=top)


def _render_markdown(report: TriageReport) -> str:
    lines = [
        "# Service Assistant Triage",
        "",
        f"**Run:** `{report.run.run_id}`  ",
        f"**Status:** {report.run.status}  ",
        f"**Verdict:** {report.verdict.aggregate_verdict}  ",
        f"**Generated:** {report.generated_at}",
        "",
        f"> {report.summary.headline}",
        "",
    ]
    if report.summary.top_recommendation:
        lines += [f"**Top recommendation:** {report.summary.top_recommendation}", ""]
    if report.failures:
        lines += ["## Failures", ""]
        lines += ["| Feature | Root cause | Stage | Severity | Deterministic | Recommended action |",
                  "|---------|------------|-------|----------|---------------|--------------------|"]
        for f in report.failures:
            lines.append(
                f"| `{f.feature_id}` | {f.root_cause} | {f.pipeline_stage} | {f.severity} | "
                f"{'yes (re-run is futile)' if f.deterministic else 'no'} | {f.recommended_action.action} |"
            )
        lines.append("")
    if report.cross_feature_patterns:
        lines += ["## Cross-feature patterns", ""]
        for p in report.cross_feature_patterns:
            lines.append(f"- **{p.pattern_type}** ({p.severity}): {p.description} "
                         f"— affects {', '.join(p.affected_features)}")
        lines.append("")
    aux = report.detection.aux_signals
    if aux and aux.total:
        lines += [
            "## Auxiliary error signals",
            "",
            f"- Failed checkpoints: {aux.failed_checkpoints}",
            f"- Task-store errors: {aux.task_errors}",
            f"- Per-task error files: {aux.pi_errors}",
            "",
        ]
    if report.events_emitted:
        emitted = ", ".join(e.type for e in report.events_emitted)
        lines += [f"_Events emitted: {emitted}_", ""]
    lines += [
        "_Recommendations are advisory; the Service Assistant does not execute them._",
        "",
    ]
    return "\n".join(lines)


def run_service_assistant(
    output_dir: Path,
    run_id: Optional[str] = None,
    *,
    emit: bool = True,
    write_artifact: bool = True,
) -> Optional[TriageReport]:
    """Convenience entry point used by the CLI and the cap-dev-pipe shim."""
    return ServiceAssistant(emit=emit, write_artifact=write_artifact).process(output_dir, run_id)
