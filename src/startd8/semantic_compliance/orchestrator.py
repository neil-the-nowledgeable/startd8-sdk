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
    VerificationIssue,
)
from .requirement_loader import SeedIndex, load_forward_manifest
from .reviewer import AgentFactory, ReviewOutcome, SemanticReviewer
from .signature_check import missing_required_symbols
from .scoring import aggregate_score, compute_compliance_score
from .triage import TriageCandidate, reviewable, triage

logger = get_logger(__name__)

POSTMORTEM_REPORT = "prime-postmortem-report.json"


def _force_missing_symbol_fail(outcome: ReviewOutcome, missing: List[str]) -> ReviewOutcome:
    """FR-17: override to a critical ``fail`` when a required public symbol is absent."""
    issue = VerificationIssue(
        severity="critical",
        category="missing_required_symbol",
        description=(
            f"Required public symbol(s) declared in the requirement's api_signatures are absent "
            f"from the generated code: {', '.join(missing)}. The feature is missing its primary "
            f"deliverable."
        ),
        suggested_fix=f"Define {', '.join(missing)} as specified in the api_signatures.",
    )
    return ReviewOutcome(
        verdict=VerdictResult(Verdict.FAIL, max(outcome.verdict.confidence, 0.95)),
        issues=[issue, *outcome.issues],
        tier=outcome.tier,
        truncated=outcome.truncated,
    )


def _cache_payload(review: FeatureReview) -> dict:
    """Full verdict payload for the cache so a re-run reproduces the review exactly (S-R1-2)."""
    v = review.verdict
    return {
        "verdict": v.verdict.value,
        "confidence": v.confidence,
        "inconclusive_reason": v.inconclusive_reason.value if v.inconclusive_reason else None,
        "tier": review.selection.tier.value,
        "score": review.semantic_compliance_score,
        "issues": [
            {"severity": i.severity, "category": i.category, "description": i.description,
             "line_hint": i.line_hint, "suggested_fix": i.suggested_fix}
            for i in review.issues
        ],
    }


class SemanticComplianceOrchestrator:
    def __init__(self, config: Optional[ReportConfig] = None, agent_factory: Optional[AgentFactory] = None) -> None:
        self.config = config or ReportConfig()
        self.reviewer = SemanticReviewer(self.config, agent_factory=agent_factory)
        # FR-CL-1 (read side): the persisted forward manifest for the run, loaded
        # in review_run(). The reviewer (E2) and signature check (E1) read this to
        # validate against the structured contract instead of api_signatures prose.
        self._forward_manifest: Optional[object] = None

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
        # FR-CL-1 (read side): make the run's canonical contract reachable to the
        # detached reviewer. Absent → reviewer/signature-check degrade to prose.
        self._forward_manifest = load_forward_manifest(output_dir, seeds.seed_path)
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
        if c.generated_files and not code.strip():
            # Files were expected but none were readable (e.g. wrong project_root). Reviewing
            # absent code would yield a confident false-FAIL that poisons Kaizen — so degrade to
            # inconclusive and do NOT cache it (an environment issue, retry next run).
            return self._inconclusive(c, selection, InconclusiveReason.CODE_UNAVAILABLE)

        outcome = self.reviewer.review(loaded, code, fqn)
        # FR-17 deterministic backstop: a required api_signature symbol absent from the FULL code is
        # a critical fail — override a lenient LLM verdict (run-029: PI-001 missing jobs_dashboard /
        # job_workspace yet passed as a low issue while app boot crashed).
        missing = missing_required_symbols(code, loaded.api_signatures)
        if missing:
            outcome = _force_missing_symbol_fail(outcome, missing)
        selection.tier = outcome.tier  # reflect final tier (cheap or escalated)
        score = compute_compliance_score(outcome.verdict.verdict, outcome.verdict.confidence, outcome.issues)
        review = FeatureReview(
            feature_id=c.feature_id, language=loaded.language, review_granularity="feature",
            element_fqn=fqn, selection=selection, verdict=outcome.verdict,
            requirement=loaded.to_ref(corroborated=True), issues=outcome.issues,
            semantic_compliance_score=score, reviewed_files=list(c.generated_files),
        )
        # Cache the FULL outcome so a re-run reproduces the verdict, issues, and score exactly.
        cache.put(c.feature_id, checksum, _cache_payload(review))
        return review

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
        reason = cached.get("inconclusive_reason")
        v = VerdictResult(
            Verdict(cached["verdict"]),
            float(cached["confidence"]),
            InconclusiveReason(reason) if reason else None,
        )
        issues = [VerificationIssue(**i) for i in cached.get("issues", [])]
        selection.tier = Tier(cached.get("tier", Tier.CHEAP.value))
        return FeatureReview(
            feature_id=c.feature_id, language=loaded.language, review_granularity="feature",
            element_fqn=f"feature:{c.feature_id}", selection=selection, verdict=v,
            requirement=loaded.to_ref(corroborated=True), issues=issues,
            semantic_compliance_score=cached.get("score"),
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
