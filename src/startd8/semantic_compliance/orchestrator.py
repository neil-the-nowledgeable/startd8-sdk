# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Semantic Compliance Reviewer orchestrator (facade).

detect → load requirement → triage → review → score → patterns → Kaizen → report → notify.
Run detached by the Service Assistant (S-R1-1) or standalone via ``startd8 assist semantic-review``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .. import __version__
from ..logging_config import get_logger
from . import feedback as _feedback
from . import report as _report
from .cache import VerdictCache, code_checksum
from .models import (
    FeatureReview,
    InconclusiveReason,
    ReportConfig,
    ReportSummary,
    SemanticComplianceReport,
    Selection,
    SelectionReason,
    Tier,
    Verdict,
    VerdictResult,
)
from .requirement_loader import SeedIndex
from .reviewer import AgentFactory, SemanticReviewer
from .scoring import aggregate_score, compute_compliance_score
from .triage import TriageCandidate, reviewable, triage

logger = get_logger(__name__)

POSTMORTEM_REPORT = "prime-postmortem-report.json"


class SemanticComplianceOrchestrator:
    def __init__(self, config: Optional[ReportConfig] = None, agent_factory: Optional[AgentFactory] = None) -> None:
        self.config = config or ReportConfig()
        self.reviewer = SemanticReviewer(self.config, agent_factory=agent_factory)

    def review_run(
        self,
        output_dir: Path,
        run_id: Optional[str] = None,
        project_root: Optional[Path] = None,
        *,
        emit_events: bool = True,
    ) -> SemanticComplianceReport:
        output_dir = Path(output_dir)
        run_id = run_id or output_dir.parent.name
        project_root = Path(project_root) if project_root else None

        features_pm = self._load_postmortem_features(output_dir)
        seeds = SeedIndex.load(output_dir)
        cache = VerdictCache.load(output_dir, run_id)

        candidates = triage(features_pm, self.config)
        reviews: List[FeatureReview] = [
            self._review_candidate(c, seeds, cache, project_root) for c in reviewable(candidates)
        ]
        # Budget-dropped suspects are recorded as not_reviewed (no silent caps).
        reviews += [self._not_reviewed(c) for c in candidates if c.reason == SelectionReason.NOT_REVIEWED]

        patterns = _feedback.detect_patterns(reviews, reviewed_count=sum(1 for r in reviews if r.review_status == "complete"))
        suggestions = _feedback.build_suggestions(reviews, self.config)
        passed = [r.feature_id for r in reviews if r.verdict.verdict == Verdict.PASS]
        kaizen_emitted = _feedback.emit(suggestions, passed, output_dir, run_id)

        summary = self._summarize(features_pm, reviews)
        report = SemanticComplianceReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            scr_version=__version__,
            run_id=run_id,
            output_dir=str(output_dir),
            config=self.config,
            summary=summary,
            status="complete",
            features=reviews,
            cross_feature_patterns=patterns,
            kaizen_emitted=kaizen_emitted,
        )
        _report.write_report(report, output_dir)
        cache.save()
        if emit_events:
            self._emit(report)
        return report

    # -- steps ---------------------------------------------------------------

    def _load_postmortem_features(self, output_dir: Path) -> List[dict]:
        path = output_dir / POSTMORTEM_REPORT
        if not path.is_file():
            logger.info("SCR: no %s — nothing to triage (R3-S3)", POSTMORTEM_REPORT)
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("features", []) or []
        except (json.JSONDecodeError, OSError):
            logger.warning("SCR: could not parse %s", path)
            return []

    def _review_candidate(self, c: TriageCandidate, seeds: SeedIndex, cache: VerdictCache,
                          project_root: Optional[Path]) -> FeatureReview:
        fqn = f"feature:{c.feature_id}"
        selection = Selection(c.suspicion_score, Tier.CHEAP, c.reason)
        loaded, reason = seeds.lookup(c.feature_id, c.generated_files)
        if reason is not None:
            return self._inconclusive(c, selection, reason)

        checksum = code_checksum(c.generated_files, root=project_root)
        cached = cache.get(c.feature_id, checksum)
        if cached is not None:
            return self._from_cached(c, selection, loaded, cached)

        code = self._read_code(c.generated_files, project_root)
        outcome = self.reviewer.review(loaded, code, fqn)
        selection.tier = outcome.tier  # reflect final tier (cheap or escalated)
        score = compute_compliance_score(outcome.verdict.verdict, outcome.verdict.confidence, outcome.issues)
        cache.put(c.feature_id, checksum, {
            "verdict": outcome.verdict.verdict.value, "confidence": outcome.verdict.confidence,
        })
        return FeatureReview(
            feature_id=c.feature_id, language=loaded.language, review_granularity="feature",
            element_fqn=fqn, selection=selection, verdict=outcome.verdict,
            requirement=loaded.to_ref(corroborated=True), issues=outcome.issues,
            semantic_compliance_score=score, reviewed_files=list(c.generated_files),
        )

    def _read_code(self, files: List[str], project_root: Optional[Path]) -> str:
        chunks: List[str] = []
        for rel in files:
            p = (project_root / rel) if project_root else Path(rel)
            try:
                chunks.append(f"# === {rel} ===\n{p.read_text(encoding='utf-8')}")
            except OSError:
                continue
        return "\n\n".join(chunks)

    def _inconclusive(self, c, selection, reason: InconclusiveReason) -> FeatureReview:
        return FeatureReview(
            feature_id=c.feature_id, language="python", review_granularity="feature",
            element_fqn=f"feature:{c.feature_id}", selection=selection,
            verdict=VerdictResult(Verdict.INCONCLUSIVE, 0.0, reason),
            reviewed_files=list(c.generated_files),
        )

    def _from_cached(self, c, selection, loaded, cached: dict) -> FeatureReview:
        v = VerdictResult(Verdict(cached["verdict"]), float(cached["confidence"]))
        return FeatureReview(
            feature_id=c.feature_id, language=loaded.language, review_granularity="feature",
            element_fqn=f"feature:{c.feature_id}", selection=selection, verdict=v,
            requirement=loaded.to_ref(corroborated=True),
            semantic_compliance_score=compute_compliance_score(v.verdict, v.confidence, []),
            reviewed_files=list(c.generated_files),
        )

    def _not_reviewed(self, c: TriageCandidate) -> FeatureReview:
        return FeatureReview(
            feature_id=c.feature_id, language="python", review_granularity="feature",
            element_fqn=f"feature:{c.feature_id}",
            selection=Selection(c.suspicion_score, Tier.CHEAP, SelectionReason.NOT_REVIEWED, c.not_reviewed_reason),
            verdict=VerdictResult(Verdict.INCONCLUSIVE, 0.0),
            review_status="pending",
        )

    def _summarize(self, features_pm: List[dict], reviews: List[FeatureReview]) -> ReportSummary:
        done = [r for r in reviews if r.review_status == "complete"]
        n_pass = sum(1 for r in done if r.verdict.verdict == Verdict.PASS)
        n_fail = sum(1 for r in done if r.verdict.verdict == Verdict.FAIL)
        n_inc = sum(1 for r in done if r.verdict.verdict == Verdict.INCONCLUSIVE)
        n_escalated = sum(1 for r in done if r.selection.tier == Tier.ESCALATED)
        agg = aggregate_score([r.semantic_compliance_score for r in done])
        rate = (n_inc / len(done)) if done else 0.0
        exceeded = rate > self.config.max_inconclusive_rate
        return ReportSummary(
            total_features=len(features_pm) or len(reviews), escalated=n_escalated,
            reviewed=len(done), not_reviewed=len(reviews) - len(done),
            pass_=n_pass, fail=n_fail, inconclusive=n_inc,
            semantic_compliance_aggregate=agg, inconclusive_rate=round(rate, 4),
            inconclusive_rate_exceeded=exceeded,
        )

    def _emit(self, report: SemanticComplianceReport) -> None:
        try:
            from ..events import Event, EventBus, EventPriority, EventType
            from ..events.otel_bridge import OTelEventBridge
            OTelEventBridge.activate()
            EventBus.emit(Event(
                type=EventType.SEMANTIC_REVIEW_COMPLETE, source="SemanticComplianceReviewer",
                data={"run_id": report.run_id, "aggregate": report.summary.semantic_compliance_aggregate,
                      "fail": report.summary.fail, "report_path": str(Path(report.output_dir) / _report.REPORT_JSON)},
                priority=EventPriority.HIGH,
            ))
            if report.summary.inconclusive_rate_exceeded:
                EventBus.emit(Event(
                    type=EventType.SYSTEM_WARNING, source="SemanticComplianceReviewer",
                    data={"run_id": report.run_id, "reason": "inconclusive_rate_exceeded",
                          "rate": report.summary.inconclusive_rate},
                    priority=EventPriority.HIGH,
                ))
        except Exception:  # pragma: no cover - events are best-effort
            logger.warning("SCR: event emission failed", exc_info=True)


def run_semantic_compliance(
    output_dir: Path,
    run_id: Optional[str] = None,
    project_root: Optional[Path] = None,
    config: Optional[ReportConfig] = None,
    *,
    emit_events: bool = True,
) -> SemanticComplianceReport:
    """Convenience entry point for the CLI / Service Assistant."""
    return SemanticComplianceOrchestrator(config).review_run(
        output_dir, run_id=run_id, project_root=project_root, emit_events=emit_events
    )
