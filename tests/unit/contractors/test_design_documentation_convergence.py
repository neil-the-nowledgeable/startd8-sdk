"""Targeted convergence tests for DesignDocumentationPhase orchestration."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from startd8.contractors.artisan_phases.design_documentation import (
    DesignDocument,
    DesignDocumentationPhase,
    FeatureContext,
    ResolutionAction,
    ResolutionDecision,
    ReviewRole,
    ReviewVerdict,
)


class _DummyLLM:
    """Minimal backend stub; run() tests patch phase methods directly."""

    total_input_tokens = 0
    total_output_tokens = 0
    total_cost_usd = 0.0

    def get_model_spec(self) -> str | None:
        return "mock:dummy"

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        return "unused"


class _StaticResolutionCallback:
    """Always returns a fixed decision."""

    def __init__(self, action: ResolutionAction = ResolutionAction.MERGE):
        self._action = action

    async def resolve(self, escalation_report):  # pragma: no cover - typed protocol
        return ResolutionDecision(
            action=self._action,
            guidance="apply merged feedback",
            decided_by="test",
            decided_at=datetime.now(timezone.utc),
        )


def _design(iteration: int, marker: str) -> DesignDocument:
    return DesignDocument(
        feature_name="Feature A",
        sections={},
        raw_text=f"## Overview\n{marker}",
        generated_at=datetime.now(timezone.utc),
        iteration=iteration,
    )


def _verdict(role: ReviewRole, approved: bool, confidence: float, summary: str) -> ReviewVerdict:
    return ReviewVerdict(
        role=role,
        approved=approved,
        confidence=confidence,
        concerns=[],
        suggestions=[],
        summary=summary,
        reviewed_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_non_rereview_resolution_rereviews_revised_design(monkeypatch):
    """REQ-PAQ-200/201: revise path must re-review and use latest verdict pair."""
    phase = DesignDocumentationPhase(
        llm=_DummyLLM(),
        max_iterations=3,
        resolution_callback=_StaticResolutionCallback(ResolutionAction.MERGE),
    )
    ctx = FeatureContext(
        feature_name="Feature A",
        description="desc",
        target_file="src/a.py",
    )

    d1 = _design(1, "draft-v1")
    d2 = _design(2, "draft-v2")

    async def _gen(*args, **kwargs):
        return d1

    async def _revise(*args, **kwargs):
        return d2

    review_calls: list[tuple[str, str]] = []

    rv1 = _verdict(ReviewRole.REVIEWER, approved=False, confidence=0.9, summary="reject-v1")
    av1 = _verdict(ReviewRole.ARBITER, approved=True, confidence=0.9, summary="approve-v1")
    rv2 = _verdict(ReviewRole.REVIEWER, approved=True, confidence=0.9, summary="approve-v2")
    av2 = _verdict(ReviewRole.ARBITER, approved=True, confidence=0.9, summary="approve-v2")
    verdicts = [rv1, av1, rv2, av2]

    async def _review(design, role, feature_context=None):
        review_calls.append((design.raw_text, role.value))
        return verdicts.pop(0)

    monkeypatch.setattr(phase, "_generate_design", _gen)
    monkeypatch.setattr(phase, "_revise_design", _revise)
    monkeypatch.setattr(phase, "_review_design", _review)

    result = await phase.run(ctx)

    assert result.agreed is True
    assert result.design_document.raw_text.endswith("draft-v2")
    assert result.reviewer_verdict.summary == "approve-v2"
    assert result.arbiter_verdict.summary == "approve-v2"
    assert result.final_iteration == 2
    # Two reviews on v1 + two reviews on revised v2.
    assert len(review_calls) == 4
    assert review_calls[2][0].endswith("draft-v2")
    assert review_calls[3][0].endswith("draft-v2")
    assert result.resolution_audit is not None
    assert result.resolution_audit["resolution_action_counts"]["merge"] == 1
    event = result.resolution_audit["events"][0]
    assert event["outcome"] == "accepted_after_revision"
    assert "delta_summary" in event
    assert result.prompt_telemetry is not None
    assert result.prompt_telemetry["total_calls"] >= 0
    assert result.disagreement_telemetry is not None
    assert result.disagreement_telemetry["review_pair_count"] == 2


@pytest.mark.asyncio
async def test_converged_rejection_is_not_agreed(monkeypatch):
    """Agreement without approval should return agreed=False with reason code."""
    phase = DesignDocumentationPhase(llm=_DummyLLM(), max_iterations=2)
    ctx = FeatureContext(
        feature_name="Feature A",
        description="desc",
        target_file="src/a.py",
    )

    d1 = _design(1, "draft-v1")
    rv = _verdict(ReviewRole.REVIEWER, approved=False, confidence=0.8, summary="reject")
    av = _verdict(ReviewRole.ARBITER, approved=False, confidence=0.85, summary="reject")
    verdicts = [rv, av]

    async def _gen(*args, **kwargs):
        return d1

    async def _review(*args, **kwargs):
        return verdicts.pop(0)

    monkeypatch.setattr(phase, "_generate_design", _gen)
    monkeypatch.setattr(phase, "_review_design", _review)

    result = await phase.run(ctx)

    assert result.agreed is False
    assert result.non_agreement_reason_code == "DUAL_REJECTION"
    assert result.final_iteration == 1


@pytest.mark.asyncio
async def test_post_revision_disagreement_returns_reason_code(monkeypatch):
    """Unresolved post-revision disagreement should return DISAGREEMENT_UNRESOLVED."""
    phase = DesignDocumentationPhase(
        llm=_DummyLLM(),
        max_iterations=3,
        resolution_callback=_StaticResolutionCallback(ResolutionAction.MERGE),
    )
    ctx = FeatureContext(
        feature_name="Feature A",
        description="desc",
        target_file="src/a.py",
    )

    d1 = _design(1, "draft-v1")
    d2 = _design(2, "draft-v2")

    rv1 = _verdict(ReviewRole.REVIEWER, approved=False, confidence=0.9, summary="reject-v1")
    av1 = _verdict(ReviewRole.ARBITER, approved=True, confidence=0.9, summary="approve-v1")
    rv2 = _verdict(ReviewRole.REVIEWER, approved=False, confidence=0.9, summary="reject-v2")
    av2 = _verdict(ReviewRole.ARBITER, approved=True, confidence=0.9, summary="approve-v2")
    verdicts = [rv1, av1, rv2, av2]

    async def _gen(*args, **kwargs):
        return d1

    async def _revise(*args, **kwargs):
        return d2

    async def _review(*args, **kwargs):
        return verdicts.pop(0)

    monkeypatch.setattr(phase, "_generate_design", _gen)
    monkeypatch.setattr(phase, "_revise_design", _revise)
    monkeypatch.setattr(phase, "_review_design", _review)

    result = await phase.run(ctx)

    assert result.agreed is False
    assert result.non_agreement_reason_code == "DISAGREEMENT_UNRESOLVED"
    assert result.final_iteration == 2
    assert result.design_document.raw_text.endswith("draft-v2")


@pytest.mark.asyncio
async def test_non_rereview_resolution_at_max_iterations_marks_exhausted(monkeypatch):
    """When no room to revise, reason should be MAX_ITERATIONS_EXCEEDED."""
    phase = DesignDocumentationPhase(
        llm=_DummyLLM(),
        max_iterations=1,
        resolution_callback=_StaticResolutionCallback(ResolutionAction.MERGE),
    )
    ctx = FeatureContext(
        feature_name="Feature A",
        description="desc",
        target_file="src/a.py",
    )

    d1 = _design(1, "draft-v1")
    rv1 = _verdict(ReviewRole.REVIEWER, approved=False, confidence=0.9, summary="reject-v1")
    av1 = _verdict(ReviewRole.ARBITER, approved=True, confidence=0.9, summary="approve-v1")
    verdicts = [rv1, av1]

    async def _gen(*args, **kwargs):
        return d1

    async def _review(*args, **kwargs):
        return verdicts.pop(0)

    monkeypatch.setattr(phase, "_generate_design", _gen)
    monkeypatch.setattr(phase, "_review_design", _review)

    result = await phase.run(ctx)

    assert result.agreed is False
    assert result.non_agreement_reason_code == "MAX_ITERATIONS_EXCEEDED"
    assert result.final_iteration == 1
