"""Tiered reviewer tests (FR-6/7/15, R1-S7/R2-S1/R4-S2) using an injected fake agent."""

import json

from startd8.semantic_compliance.models import (
    InconclusiveReason,
    ReportConfig,
    Tier,
    Verdict,
)
from startd8.semantic_compliance.requirement_loader import LoadedRequirement
from startd8.semantic_compliance.reviewer import SemanticReviewer


class _FakeResult:
    def __init__(self, text):
        self.text = text


class _FakeAgent:
    def __init__(self, responses):
        self._responses = list(responses)

    def generate(self, prompt, **kwargs):
        return _FakeResult(self._responses.pop(0) if self._responses else "")


def _factory(by_spec):
    """by_spec: {model_spec: [response, ...]}; records which specs were called."""
    calls = []

    def make(spec):
        calls.append(spec)
        return _FakeAgent(by_spec.get(spec, []))

    make.calls = calls
    return make


def _svr(verdict, confidence, issues=()):
    return json.dumps({
        "verdict": verdict, "confidence": confidence,
        "issues": [dict(severity=s, category=c, description=d) for s, c, d in issues],
        "element_fqn": "feature:x",
    })


def _loaded(language="python"):
    return LoadedRequirement(
        feature_id="PI-1", requirement_text="Never compute Metric.value.",
        target_files=["m.py"], negative_scope=["compute Metric.value"], language=language,
    )


CFG = ReportConfig(model_cheap="anthropic:claude-haiku-4-5",
                   model_escalation="anthropic:claude-sonnet-4-6", theta=0.7)


def test_clean_pass_no_escalation():
    f = _factory({CFG.model_cheap: [_svr("pass", 0.9)]})
    out = SemanticReviewer(CFG, agent_factory=f).review(_loaded(), "code", "feature:x")
    assert out.verdict.verdict == Verdict.PASS
    assert out.tier == Tier.CHEAP
    assert f.calls == [CFG.model_cheap]  # never escalated


def test_false_pass_caught_at_cheap_tier():
    # Structurally-PASS feature, but the reviewer says fail with high confidence → escalates,
    # Sonnet confirms fail. This is the capability's unique value.
    f = _factory({
        CFG.model_cheap: [_svr("fail", 0.8, [("critical", "requirement_violation", "computes value")])],
        CFG.model_escalation: [_svr("fail", 0.9, [("critical", "requirement_violation", "computes value")])],
    })
    out = SemanticReviewer(CFG, agent_factory=f).review(_loaded(), "code", "feature:x")
    assert out.verdict.verdict == Verdict.FAIL
    assert out.tier == Tier.ESCALATED
    assert f.calls == [CFG.model_cheap, CFG.model_escalation]
    assert out.issues[0].severity == "critical"


def test_low_confidence_escalates_and_sonnet_is_terminal():
    f = _factory({
        CFG.model_cheap: [_svr("pass", 0.4)],          # below theta → escalate
        CFG.model_escalation: [_svr("pass", 0.5)],     # still low, but Sonnet is terminal (R4-S2)
    })
    out = SemanticReviewer(CFG, agent_factory=f).review(_loaded(), "code", "feature:x")
    assert out.tier == Tier.ESCALATED
    assert out.verdict.verdict == Verdict.PASS
    assert f.calls == [CFG.model_cheap, CFG.model_escalation]


def test_parse_failure_retries_then_inconclusive():
    f = _factory({CFG.model_cheap: ["not json", "still not json"]})
    out = SemanticReviewer(CFG, agent_factory=f).review(_loaded(), "code", "feature:x")
    assert out.verdict.verdict == Verdict.INCONCLUSIVE
    assert out.verdict.inconclusive_reason == InconclusiveReason.PARSE_FAILURE
    assert f.calls == [CFG.model_cheap, CFG.model_cheap]  # one retry, no escalation


def test_non_python_is_inconclusive_no_agent_call():
    f = _factory({})
    out = SemanticReviewer(CFG, agent_factory=f).review(_loaded(language="go"), "code", "feature:x")
    assert out.verdict.inconclusive_reason == InconclusiveReason.LANGUAGE_UNSUPPORTED
    assert f.calls == []  # never spent a token (R2-S1)


def test_oversized_input_is_truncated():
    f = _factory({CFG.model_cheap: [_svr("pass", 0.9)]})
    cfg = ReportConfig(max_input_tokens=10)  # ~40 chars budget
    out = SemanticReviewer(cfg, agent_factory=f).review(_loaded(), "x" * 5000, "feature:x")
    assert out.truncated is True
