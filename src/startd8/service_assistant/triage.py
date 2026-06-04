"""Triage synthesis for the Service Assistant (FR-7, FR-8, FR-9).

Reads the artifacts the post-mortem path already produced and *synthesizes* a triage
view. Classification is **consumed** from ``prime-postmortem-report.json`` (FR-8), not
re-derived; the ``RootCauseClassifier`` fallback fires only when the report is absent.
Cross-run persistence is read from the batch report (FR-9).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..logging_config import get_logger
from .detector import DetectionResult
from .models import (
    BatchInfo,
    CrossFeaturePatternView,
    FailureTriage,
    RecommendedAction,
    Verdict,
)
from .operational_actions import apply_cost_overlay, resolve_operational_action

logger = get_logger(__name__)

BATCH_REPORT = "batch-postmortem-report.json"


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Service Assistant could not read %s", path)
        return None


def _batch_persistence(output_dir: Path) -> Tuple[Dict[str, int], Optional[BatchInfo]]:
    """Map feature_id -> failure occurrences, plus batch summary (FR-9).

    The batch report lives at the pipeline-output base (parent of run-* dirs).
    """
    for parent in (output_dir.parent, output_dir.parent.parent, output_dir):
        candidate = parent / BATCH_REPORT
        if candidate.is_file():
            data = _read_json(candidate)
            if not data:
                continue
            occurrences: Dict[str, int] = {}
            for pf in data.get("persistent_failures", []) or []:
                tid = pf.get("task_id") or pf.get("feature_id")
                if tid:
                    occurrences[str(tid)] = int(pf.get("fail_count", pf.get("occurrences", 2)))
            velocity = data.get("velocity", {}) or {}
            batch = BatchInfo(
                batch_id=str(data.get("batch_id", "")),
                runs_in_batch=int(data.get("runs_in_batch", data.get("total_runs", 1)) or 1),
                persistent_failure_count=len(occurrences),
                velocity_trend=str(velocity.get("trend", "unknown")),
            )
            return occurrences, batch
    return {}, None


def build_verdict(detection: DetectionResult, report: Optional[dict], result: Optional[dict]) -> Verdict:
    """Derive the aggregate verdict from the best available artifact."""
    if detection.hard_abort:
        return Verdict(
            aggregate_verdict="ABORTED",
            total_features=detection.features_attempted or 0,
            succeeded=0,
            failed=detection.features_attempted or 0,
        )
    if report:
        return Verdict(
            aggregate_verdict=report.get("aggregate_verdict") or "UNKNOWN",
            total_features=int(report.get("total_features", 0) or 0),
            succeeded=int(report.get("successful_features", 0) or 0),
            failed=int(report.get("failed_features", 0) or 0),
            total_cost_usd=(report.get("cost_summary") or {}).get("total_usd"),
        )
    if result:
        succeeded = int(result.get("succeeded", 0) or 0)
        failed = int(result.get("failed", 0) or 0)
        verdict = "PASS" if result.get("success") else ("PARTIAL" if succeeded else "FAIL")
        return Verdict(
            aggregate_verdict=verdict,
            total_features=int(result.get("processed", succeeded + failed) or 0),
            succeeded=succeeded,
            failed=failed,
            total_cost_usd=result.get("total_cost_usd"),
        )
    return Verdict()


def _failures_from_report(report: dict, occurrences: Dict[str, int]) -> List[FailureTriage]:
    failures: List[FailureTriage] = []
    for feat in report.get("features", []) or []:
        if feat.get("success"):
            continue
        root_cause = feat.get("root_cause", "unknown")
        stage = feat.get("pipeline_stage", "unknown")
        op = resolve_operational_action(root_cause)
        # FR-14: a $0 deterministic failure can't be fixed by a re-run (idempotent) — override.
        op, deterministic = apply_cost_overlay(op, root_cause, feat.get("cost_usd"))
        fid = str(feat.get("feature_id", ""))
        occ = occurrences.get(fid, 0)
        target_files = feat.get("target_files") or []
        failures.append(
            FailureTriage(
                feature_id=fid,
                root_cause=str(root_cause),
                pipeline_stage=str(stage),
                severity=op.severity,
                actionable=op.actionable,
                deterministic=deterministic,
                recommended_action=RecommendedAction(
                    action=op.action,
                    re_run_strategy=op.re_run_strategy,
                    rationale=feat.get("error_message") or None,
                    source_classification="postmortem_report",
                ),
                element_id=None,
                file=target_files[0] if target_files else None,
                persistent=occ >= 2,
                occurrences=max(occ, 1),
                force_regenerated=bool(feat.get("force_regenerated", False)),
            )
        )
    return failures


def _failures_from_result_fallback(result: dict, occurrences: Dict[str, int]) -> List[FailureTriage]:
    """FR-8 fallback: classify from prime-result when the post-mortem is absent."""
    try:
        from ..contractors.prime_postmortem import RootCauseClassifier
        classifier = RootCauseClassifier()
    except Exception:  # pragma: no cover - defensive
        classifier = None

    failures: List[FailureTriage] = []
    for entry in result.get("history", []) or []:
        if entry.get("success"):
            continue
        fid = str(entry.get("feature_id", entry.get("id", "")))
        root_cause = "unknown"
        stage = "unknown"
        if classifier is not None:
            try:
                rc, ps = classifier.classify_feature(entry, entry)
                root_cause, stage = rc.value, ps.value
            except Exception:
                pass
        op = resolve_operational_action(root_cause)
        op, deterministic = apply_cost_overlay(op, root_cause, entry.get("cost_usd"))
        occ = occurrences.get(fid, 0)
        failures.append(
            FailureTriage(
                feature_id=fid,
                root_cause=root_cause,
                pipeline_stage=stage,
                severity=op.severity,
                actionable=op.actionable,
                deterministic=deterministic,
                recommended_action=RecommendedAction(
                    action=op.action,
                    re_run_strategy=op.re_run_strategy,
                    rationale=entry.get("error") or entry.get("error_message") or None,
                    source_classification="fallback_classifier",
                ),
                persistent=occ >= 2,
                occurrences=max(occ, 1),
            )
        )
    return failures


def _cross_patterns(report: Optional[dict]) -> List[CrossFeaturePatternView]:
    if not report:
        return []
    out: List[CrossFeaturePatternView] = []
    for p in report.get("cross_feature_patterns", []) or []:
        out.append(
            CrossFeaturePatternView(
                pattern_type=str(p.get("pattern_type", "")),
                description=str(p.get("description", "")),
                affected_features=list(p.get("affected_features", []) or []),
                severity=str(p.get("severity", "medium")),
            )
        )
    return out


def synthesize_triage(detection: DetectionResult) -> Tuple[
    Verdict, List[FailureTriage], List[CrossFeaturePatternView], Optional[BatchInfo]
]:
    """Read the run/post-mortem/batch artifacts and produce the triage view."""
    report = _read_json(detection.postmortem_sentinel) if detection.postmortem_present else None
    result = _read_json(detection.run_sentinel) if detection.run_sentinel_present else None
    occurrences, batch = _batch_persistence(detection.output_dir)

    verdict = build_verdict(detection, report, result)

    if report:
        failures = _failures_from_report(report, occurrences)
    elif result:
        failures = _failures_from_result_fallback(result, occurrences)
    else:
        failures = []

    return verdict, failures, _cross_patterns(report), batch
