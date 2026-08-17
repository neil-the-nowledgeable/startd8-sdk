"""Fuel follow-on — the realization→retrospective→auto-tier loop fires LIVE end-to-end on a realistic
regression (not a synthetic Finding fixture).

Closes REQ-20 H1 (a regression can now fire — the pipeline carries declared regimes) + REQ-21 H2 (the
lesson carries the measured confidence, so the auto-tier is reachable).
"""

from __future__ import annotations

from startd8.navigator.realization import MeasuredProvenanceSource
from startd8.navigator.realization_contract import parse_record
from startd8.navigator.revise_tier import (
    TIER_AUTO,
    auto_apply_revise,
    classify_revise_tier,
    eligibility_of,
)
from startd8.navigator.sources_pipeline import nodes_from_pipeline
from startd8.navigator.sources_retrospective import lesson_status, nodes_from_retrospective


def _drift_provenance(confidence=0.95):
    """Provenance reporting stage:impl's artifact as llm — a real determinism regression: the stage was
    DECLARED deterministic (the $0 compiler) but MEASURED llm."""
    impl = next(n for n in nodes_from_pipeline() if n.key == "stage:impl")
    artifact = impl.lives[0].ref
    return MeasuredProvenanceSource(
        {artifact: parse_record({"file": artifact, "regime": "llm", "source_confidence": confidence})})


def test_full_arc_fires_live_on_a_pipeline_regression(tmp_path):
    """The whole loop, live: provenance drift → regression → grounded Lesson (with confidence) → the
    auto-tier is reachable → auto-apply through a passing guard → an audit record."""
    lessons = nodes_from_retrospective(tmp_path, _drift_provenance(0.95))   # tmp_path has no REQ docs → pipeline only
    assert lessons, "a pipeline determinism-regression should produce a Lesson (H1 fixed)"
    lesson = next(x for x in lessons if "stage:impl" in x.key)

    # H2: the lesson carries the measured confidence — no longer None → auto-tier reachable
    assert lesson.confidence == 0.95
    assert lesson_status(lesson) == "proposed"                    # still proposed (human default)
    assert lesson.attributes["revise_tier"] == "human"            # at projection (byte-identity unproven)

    # the auto-tier is now REACHABLE (was structurally impossible while confidence was None):
    elig = eligibility_of(lesson, byte_identical=True, effects=[])
    assert classify_revise_tier(elig) == TIER_AUTO
    audit = auto_apply_revise(lesson, elig, guard=lambda: True, timestamp="2026-08-16T00:00Z", revert_ref="deadbeef")
    assert audit is not None and audit.lesson == lesson.key and audit.guard_result is True


def test_low_confidence_regression_stays_human(tmp_path):
    """A low-confidence measured regression yields a below-floor lesson → the auto-tier is NOT reachable
    (fail-safe): the honesty firewall carries all the way through to the auto-tier."""
    lessons = nodes_from_retrospective(tmp_path, _drift_provenance(0.2))
    # a below-threshold measured regime degrades (REQ-18 seam) → no regression → no lesson, OR a lesson
    # whose confidence is below the floor. Either way, nothing is auto-eligible.
    for lesson in lessons:
        elig = eligibility_of(lesson, byte_identical=True, effects=[])
        assert classify_revise_tier(elig) != TIER_AUTO
