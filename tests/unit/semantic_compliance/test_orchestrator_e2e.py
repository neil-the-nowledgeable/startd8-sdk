"""End-to-end orchestrator test — the false-PASS catch + artifacts (FR-7/8/9/10/11)."""

import json

from startd8.semantic_compliance import run_semantic_compliance
from startd8.semantic_compliance.models import ReportConfig, Verdict


class _FakeResult:
    def __init__(self, text):
        self.text = text


class _ScriptedAgent:
    """Returns a fixed verdict regardless of prompt — keyed by model spec via the factory."""

    def __init__(self, payload):
        self._payload = payload

    def generate(self, prompt, **kwargs):
        return _FakeResult(json.dumps(self._payload))


def _svr(verdict, confidence, issues=()):
    return {"verdict": verdict, "confidence": confidence,
            "issues": [dict(severity=s, category=c, description=d, suggested_fix=fx) for s, c, d, fx in issues],
            "element_fqn": "x"}


def _build_run(tmp_path):
    """A structurally-PASS run with a feature that secretly violates its requirement."""
    project = tmp_path / "project"
    out = tmp_path / "pipeline-output" / "proj" / "run-027" / "plan-ingestion"
    (project / "src").mkdir(parents=True)
    out.mkdir(parents=True)

    # The offending generated code (computes a field the requirement forbids).
    (project / "src" / "metric_ingest.py").write_text(
        "def ingest(row):\n    row['value'] = sum(row['samples']) / len(row['samples'])\n    return row\n",
        encoding="utf-8",
    )

    # Seed: requirement + negative scope + target files (real shape).
    seed = {"tasks": [{
        "task_id": "metric-ingest",
        "config": {
            "task_description": "Ingest metric rows. The AI must NEVER compute Metric.value.",
            "context": {"feature_id": "metric-ingest", "target_files": ["src/metric_ingest.py"],
                        "negative_scope": ["compute Metric.value"], "language_id": "python"},
        },
    }]}
    (out / "prime-context-seed-enriched.json").write_text(json.dumps(seed), encoding="utf-8")

    # Post-mortem says PASS (structurally) — the trap.
    pm = {"aggregate_verdict": "PASS", "features": [
        {"feature_id": "metric-ingest", "success": True, "requirement_score": 0.9,
         "generated_files": ["src/metric_ingest.py"], "root_cause": "unknown"},
    ]}
    (out / "prime-postmortem-report.json").write_text(json.dumps(pm), encoding="utf-8")
    return out, project


def test_false_pass_is_caught_end_to_end(tmp_path):
    out, project = _build_run(tmp_path)
    # The reviewer (any tier) returns the requirement violation.
    payload = _svr("fail", 0.88, [("critical", "requirement_violation",
                                   "computes Metric.value", "assign it from the input unchanged")])
    factory = lambda spec: _ScriptedAgent(payload)

    cfg = ReportConfig(reserved_pass_quota=2, suspicion_threshold=0.5)
    report = run_semantic_compliance(out, run_id="run-027", project_root=project,
                                     config=cfg, emit_events=False)

    # The structurally-PASS feature is now flagged FAIL by the SCR.
    assert report.summary.fail == 1
    mi = next(f for f in report.features if f.feature_id == "metric-ingest")
    assert mi.verdict.verdict == Verdict.FAIL
    assert mi.selection.reason.value == "pass_sample"   # caught via the reserved sample
    assert mi.semantic_compliance_score is not None and mi.semantic_compliance_score < 0.5

    # Artifacts written.
    rj = json.loads((out / "semantic-compliance-report.json").read_text())
    assert rj["status"] == "complete" and rj["summary"]["fail"] == 1
    assert (out / "semantic-compliance-report.md").is_file()

    # Kaizen suggestion emitted in the canonical shape the loop consumes.
    ks = json.loads((out / "kaizen-suggestions.json").read_text())
    scr = [s for s in ks["suggestions"] if s.get("source") == "semantic_compliance_reviewer"]
    assert scr and scr[0]["config_key"] == "prompt_hints"
    assert scr[0]["pattern_type"] == "requirement_semantic_gap"
    assert scr[0]["confidence"] == "high"  # bucketed from 0.88


def test_idempotent_second_run_uses_cache(tmp_path):
    out, project = _build_run(tmp_path)
    calls = []

    def factory_counting(spec):
        calls.append(spec)
        return _ScriptedAgent(_svr("fail", 0.88, [("critical", "c", "d", "fx")]))

    cfg = ReportConfig()
    from startd8.semantic_compliance.orchestrator import SemanticComplianceOrchestrator
    SemanticComplianceOrchestrator(cfg, agent_factory=factory_counting).review_run(
        out, run_id="run-027", project_root=project, emit_events=False)
    first = len(calls)
    SemanticComplianceOrchestrator(cfg, agent_factory=factory_counting).review_run(
        out, run_id="run-027", project_root=project, emit_events=False)
    assert len(calls) == first  # second run hit the verdict cache, zero new agent calls (S-R1-2)


def test_cache_hit_preserves_issues_and_score(tmp_path):
    """A cached FAIL must reload with its issues + score intact (not an empty generic)."""
    out, project = _build_run(tmp_path)
    payload = _svr("fail", 0.88, [("critical", "requirement_violation",
                                   "computes Metric.value", "assign from input unchanged")])
    factory = lambda spec: _ScriptedAgent(payload)
    cfg = ReportConfig()
    from startd8.semantic_compliance.orchestrator import SemanticComplianceOrchestrator

    r1 = SemanticComplianceOrchestrator(cfg, agent_factory=factory).review_run(
        out, run_id="run-027", project_root=project, emit_events=False)
    # Second run is fully cached.
    r2 = SemanticComplianceOrchestrator(cfg, agent_factory=factory).review_run(
        out, run_id="run-027", project_root=project, emit_events=False)

    f1 = next(f for f in r1.features if f.feature_id == "metric-ingest")
    f2 = next(f for f in r2.features if f.feature_id == "metric-ingest")
    assert f2.verdict.verdict == f1.verdict.verdict
    assert [i.description for i in f2.issues] == [i.description for i in f1.issues]  # issues survive cache
    assert f2.semantic_compliance_score == f1.semantic_compliance_score
    # The Kaizen hint on the cached run is still the templated suggested_fix, not the generic.
    ks = json.loads((out / "kaizen-suggestions.json").read_text())
    scr = [s for s in ks["suggestions"] if s.get("source") == "semantic_compliance_reviewer"]
    assert scr and "assign from input unchanged" in scr[0]["suggested_action"]


def test_unreadable_code_is_inconclusive_not_false_fail(tmp_path):
    """Wrong project_root → files unreadable → inconclusive(code_unavailable), never a confident fail."""
    out, project = _build_run(tmp_path)
    payload = _svr("fail", 0.95, [("critical", "x", "y", "z")])  # reviewer would say fail on empty code
    factory = lambda spec: _ScriptedAgent(payload)
    cfg = ReportConfig()

    # Point project_root at an empty dir so the listed generated_files cannot be read.
    bad_root = tmp_path / "wrong-root"
    bad_root.mkdir()
    report = run_semantic_compliance(out, run_id="run-027", project_root=bad_root,
                                     config=cfg, emit_events=False)
    mi = next(f for f in report.features if f.feature_id == "metric-ingest")
    assert mi.verdict.verdict.value == "inconclusive"
    assert mi.verdict.inconclusive_reason.value == "code_unavailable"
    assert report.summary.fail == 0  # no false fails poisoning Kaizen
