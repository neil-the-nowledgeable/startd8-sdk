"""Within-run signal aggregator for the review feedback loop.

REQ-RFL-200: Accumulates per-feature quality signals and provides
pattern detection + spec hint generation for subsequent features.

NOT persisted to disk — instantiated per run, reset on resume.
Sequential processing → no concurrency concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _FeatureSignals:
    """Accumulated signals for a single feature."""

    feature_id: str
    disk_quality_score: Optional[float] = None
    semantic_categories: List[str] = field(default_factory=list)
    review_score: Optional[int] = None
    review_classified_issues: List[Dict[str, str]] = field(default_factory=list)
    repair_step_count: int = 0


class RunQualityAccumulator:
    """Aggregates quality signals across features within a single run.

    Usage::

        acc = RunQualityAccumulator()
        for feature in features:
            # ... generate, integrate, review ...
            acc.record(feature_id, integration_metadata, review_result)
            hints = acc.build_spec_hints(existing_kaizen_categories)
            if hints:
                context["run_quality_hints"] = hints
    """

    def __init__(self) -> None:
        self._features: List[_FeatureSignals] = []
        self._semantic_counts: Dict[str, int] = {}
        self._review_issue_counts: Dict[str, int] = {}

    def record(
        self,
        feature_id: str,
        integration_metadata: Dict[str, Any],
        review_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record signals from a completed feature."""
        signals = _FeatureSignals(feature_id=feature_id)

        # Disk quality score
        signals.disk_quality_score = integration_metadata.get(
            "disk_quality_score",
        )

        # Semantic categories from compliance
        compliance = integration_metadata.get("disk_compliance", {})
        if not isinstance(compliance, dict):
            compliance = {}
        for _file, data in compliance.items():
            for issue in data.get("semantic_issues", []):
                cat = issue.get("category", "unknown")
                signals.semantic_categories.append(cat)
                self._semantic_counts[cat] = (
                    self._semantic_counts.get(cat, 0) + 1
                )

        # Repair step count
        for summary in integration_metadata.get("repair_summaries", []):
            signals.repair_step_count += len(
                summary.get("steps_applied", []),
            )

        # Review signals
        if review_result:
            signals.review_score = review_result.get("score")
            classified = review_result.get("classified_issues", [])
            signals.review_classified_issues = classified
            for ci in classified:
                cat = ci.get("category", "other")
                self._review_issue_counts[cat] = (
                    self._review_issue_counts.get(cat, 0) + 1
                )

        self._features.append(signals)

    def get_run_level_patterns(self) -> Dict[str, int]:
        """Return semantic + review issue categories with count >= 2."""
        patterns: Dict[str, int] = {}
        for cat, count in self._semantic_counts.items():
            if count >= 2:
                patterns[f"semantic:{cat}"] = count
        for cat, count in self._review_issue_counts.items():
            if count >= 2:
                patterns[f"review:{cat}"] = count
        return patterns

    def build_spec_hints(
        self,
        existing_kaizen_categories: Optional[set[str]] = None,
    ) -> Optional[str]:
        """Build condensed hint string (<= 500 chars) for next spec.

        Deduplicates against existing kaizen categories to avoid
        redundant guidance.
        """
        if not self._features:
            return None

        patterns = self.get_run_level_patterns()
        if not patterns:
            return None

        existing = existing_kaizen_categories or set()

        lines: List[str] = []
        for pattern, count in sorted(
            patterns.items(), key=lambda x: -x[1],
        ):
            # Deduplicate against kaizen
            base_cat = pattern.split(":", 1)[-1]
            if base_cat in existing:
                continue
            lines.append(f"- {pattern} ({count}x this run)")

        if not lines:
            return None

        hint = "\n".join(lines)
        if len(hint) > 500:
            hint = hint[:497] + "..."
        return hint

    def get_quality_trend(self) -> Optional[str]:
        """Return 'declining' if last 3 scores are strictly decreasing."""
        scores = [
            f.disk_quality_score
            for f in self._features
            if f.disk_quality_score is not None
        ]
        if len(scores) < 3:
            return None
        last3 = scores[-3:]
        if last3[0] > last3[1] > last3[2]:
            return "declining"
        return None

    @property
    def feature_count(self) -> int:
        """Number of features recorded."""
        return len(self._features)
