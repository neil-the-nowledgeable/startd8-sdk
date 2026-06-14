"""Unit tests for insight_emission (T3 / Section C / FR-12/13/14 / OQ-6)."""

import json
from pathlib import Path

from startd8.integrations.insight_emission import (
    emit_insight_spec,
    emit_notable_cell_insights,
)


class _RecordingBridge:
    """Duck-typed AgentInsightBridge that records calls and reports success."""

    def __init__(self):
        self.calls = []

    def _rec(self, kind, summary, **kw):
        self.calls.append({"kind": kind, "summary": summary, **kw})
        return True

    def emit_decision(self, summary, confidence=0.9, **kw):
        return self._rec("decision", summary, confidence=confidence, **kw)

    def emit_risk(self, summary, confidence=0.8, **kw):
        return self._rec("risk", summary, confidence=confidence, **kw)

    def emit_lesson(self, summary, category="general", **kw):
        return self._rec("lesson", summary, category=category, **kw)

    def emit_question(self, question, **kw):
        return self._rec("question", question, **kw)

    def emit_blocker(self, summary, confidence=1.0, **kw):
        return self._rec("blocker", summary, confidence=confidence, **kw)


def test_emit_insight_spec_counts_and_types():
    spec = {
        "decisions": [
            {"summary": "Temporal NO-GO", "confidence": 0.9,
             "evidence": [{"type": "adr", "ref": "ADR-001.md"}]},
            {"summary": "Cursor cut", "confidence": 0.95},
        ],
        "risks": [{"summary": "FR-44 sandbox", "confidence": 1.0}],
        "lessons": [{"summary": "infra vs model", "category": "methodology"}],
        "questions": [{"question": "budget ceiling?"}],
    }
    bridge = _RecordingBridge()
    counts = emit_insight_spec(bridge, spec)
    assert counts == {"decisions": 2, "risks": 1, "lessons": 1, "questions": 1}
    kinds = [c["kind"] for c in bridge.calls]
    assert kinds == ["decision", "decision", "risk", "lesson", "question"]
    # evidence forwarded
    assert bridge.calls[0]["evidence"] == [{"type": "adr", "ref": "ADR-001.md"}]


def test_empty_spec_emits_nothing():
    bridge = _RecordingBridge()
    assert emit_insight_spec(bridge, {}) == {"decisions": 0, "risks": 0, "lessons": 0, "questions": 0}
    assert bridge.calls == []


def test_notable_cells_only_failures_and_violations():
    """OQ-6: ok/infra_fail/budget_skip/integrity_fail are NOT emitted; only failures + sandbox."""
    cells = [
        {"cell_id": "h:cart:opus:r0", "status": "ok"},                       # skip
        {"cell_id": "h:cart:opus:r1", "status": "failed", "error": "boom"},  # blocker
        {"cell_id": "h:email:gpt:r0", "status": "infra_fail", "error": "429"},  # skip (not model)
        {"cell_id": "h:ship:gem:r0", "status": "budget_skip"},               # skip
        {"cell_id": "h:pay:opus:r0", "status": "integrity_fail"},            # skip (exclusion)
        {"cell_id": "h:ad:opus:r0", "status": "ok", "sandbox_violation": "egress attempt"},  # risk
        {"cell_id": "h:ad:opus:r1", "status": "timeout"},                    # blocker
    ]
    bridge = _RecordingBridge()
    n = emit_notable_cell_insights(bridge, cells, run_id="abc123")
    assert n == 3
    kinds = sorted(c["kind"] for c in bridge.calls)
    assert kinds == ["blocker", "blocker", "risk"]
    # the failed cell's error rode into the blocker rationale
    blocker = next(c for c in bridge.calls if "failed" in c["summary"])
    assert blocker["rationale"] == "boom"


def test_notable_cells_from_path(tmp_path):
    cells = [{"cell_id": "x", "status": "failed", "error": "e"}]
    p = tmp_path / "cells.json"
    p.write_text(json.dumps(cells))
    bridge = _RecordingBridge()
    assert emit_notable_cell_insights(bridge, p) == 1


def test_real_insights_yaml_is_valid_and_emits():
    import yaml
    spec_path = (
        Path(__file__).resolve().parents[2]
        / "docs/design/benchmark-observability-tracking/insights.yaml"
    )
    spec = yaml.safe_load(spec_path.read_text())
    bridge = _RecordingBridge()
    counts = emit_insight_spec(bridge, spec)
    assert counts["decisions"] >= 5
    assert counts["risks"] >= 2   # the two FR-44/45 CRITICALs
    assert counts["lessons"] >= 3
