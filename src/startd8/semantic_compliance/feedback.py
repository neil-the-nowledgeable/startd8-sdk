# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Kaizen feedback + cross-feature patterns (FR-10/11).

Emits the **canonical structured suggestion dict** the existing Kaizen loop consumes
(`pattern`/`pattern_type`/`suggested_action`/`config_key="prompt_hints"`/`phase`/`confidence`/
`auto_applicable`) — NOT bare strings (R1-S2/R1-F3). Emission is **confidence-gated** (≥θ or
Sonnet-confirmed) so a cheap-tier false-`fail` cannot poison the next run (F-R1-4), and records are
**advisory** so the next generation validates them syntactically (R3-F2). Prior SCR suggestions for
a feature that now passes are **pruned** (R3-S2).

Cross-feature patterns reuse the existing ``CrossFeaturePattern`` shape on a **relative** threshold
(≥2 AND ≥10% of reviewed) so large runs don't get noise patterns (R2-S6/R1-F5/R4-F2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ..logging_config import get_logger
from ..utils.file_operations import atomic_write_json
from .models import (
    CrossFeaturePattern,
    FeatureReview,
    ReportConfig,
    Tier,
    Verdict,
)

logger = get_logger(__name__)

KAIZEN_FILE = "kaizen-suggestions.json"
_SCR_SOURCE = "semantic_compliance_reviewer"


def _confidence_bucket(c: float) -> str:
    return "high" if c >= 0.8 else "medium" if c >= 0.5 else "low"


def _gated(review: FeatureReview, theta: float) -> bool:
    """Emit only confident fails: Sonnet-confirmed OR cheap-tier confidence ≥ θ (F-R1-4)."""
    return review.verdict.verdict == Verdict.FAIL and (
        review.selection.tier == Tier.ESCALATED or review.verdict.confidence >= theta
    )


def build_suggestions(reviews: List[FeatureReview], config: ReportConfig) -> List[dict]:
    theta = config.theta or 0.7
    out: List[dict] = []
    for r in reviews:
        if not _gated(r, theta):
            continue
        issue = r.issues[0] if r.issues else None
        action = (issue.suggested_fix or issue.description) if issue else "Address the requirement gap."
        out.append({
            "pattern": f"Requirement semantic gap in {r.feature_id}",
            "pattern_type": "requirement_semantic_gap",
            "frequency": 1,
            "suggested_action": action,
            "config_key": "prompt_hints",
            "phase": "draft",
            "confidence": _confidence_bucket(r.verdict.confidence),
            "auto_applicable": False,
            # SCR extensions (ignored by the loop, used for prune + future gate):
            "source": _SCR_SOURCE,
            "feature_id": r.feature_id,
            "confidence_score": r.verdict.confidence,
            "advisory": True,
        })
    return out


def detect_patterns(reviews: List[FeatureReview], reviewed_count: int) -> List[CrossFeaturePattern]:
    by_category: dict[str, List[str]] = {}
    for r in reviews:
        if r.verdict.verdict != Verdict.FAIL:
            continue
        for issue in r.issues:
            by_category.setdefault(issue.category, []).append(r.feature_id)

    floor = max(2, int(0.10 * max(reviewed_count, 1) + 0.999))  # ≥2 AND ≥10% (R4-F2)
    patterns: List[CrossFeaturePattern] = []
    for category, features in by_category.items():
        uniq = sorted(set(features))
        if len(uniq) >= floor:
            patterns.append(CrossFeaturePattern(
                pattern_type="requirement_semantic_gap",
                grouping_key=f"category:{category}",
                description=f"{len(uniq)} features share the semantic gap '{category}'.",
                affected_features=uniq,
                severity="high" if len(uniq) >= 3 else "medium",
            ))
    return patterns


def emit(suggestions: List[dict], passed_feature_ids: List[str], output_dir: Path, run_id: str) -> List[str]:
    """Merge SCR suggestions into ``kaizen-suggestions.json`` (creating it if absent); prune stale
    SCR entries for features that now pass (R3-S2). Returns the emitted suggestion references."""
    path = Path(output_dir) / KAIZEN_FILE
    doc = {"schema_version": "1.0", "source_run": run_id, "suggestions": []}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("SCR: kaizen-suggestions.json unreadable, recreating: %s", path)

    existing = doc.get("suggestions", []) or []
    passed = set(passed_feature_ids)
    refreshed_features = {s["feature_id"] for s in suggestions}

    def _keep(entry: dict) -> bool:
        if entry.get("source") != _SCR_SOURCE:
            return True  # never touch non-SCR suggestions
        fid = entry.get("feature_id")
        return fid not in passed and fid not in refreshed_features  # prune stale/superseded SCR entries

    doc["suggestions"] = [e for e in existing if _keep(e)] + suggestions
    atomic_write_json(path, doc, indent=2)

    emitted = [f"requirement_semantic_gap:{s['feature_id']}" for s in suggestions]
    logger.info("SCR emitted %d Kaizen suggestion(s); pruned to %d total", len(emitted), len(doc["suggestions"]))
    return emitted
