"""Deterministic-core tests for the Semantic Compliance Reviewer (FR-1/4/5/5a/8, S-R1-2)."""

import json

import pytest

from startd8.semantic_compliance import models as m
from startd8.semantic_compliance.cache import VerdictCache, code_checksum
from startd8.semantic_compliance.requirement_loader import SeedIndex
from startd8.semantic_compliance.scoring import (
    aggregate_score,
    compute_compliance_score,
    severity_weight,
)
from startd8.semantic_compliance.triage import reviewable, triage
from startd8.semantic_compliance.models import (
    InconclusiveReason,
    ReportConfig,
    SelectionReason,
    Verdict,
)


# --- scoring (FR-8) ---------------------------------------------------------

def test_score_pass_no_issues_is_confidence():
    assert compute_compliance_score(Verdict.PASS, 0.9, []) == pytest.approx(0.9)


def test_score_critical_issue_zeroes_a_pass():
    issues = [m.VerificationIssue("critical", "requirement_violation", "x")]
    # 1.0*0.9 - 0.5 = 0.4
    assert compute_compliance_score(Verdict.PASS, 0.9, issues) == pytest.approx(0.4)


def test_score_fail_is_zero():
    assert compute_compliance_score(Verdict.FAIL, 0.9, []) == 0.0


def test_inconclusive_excluded_from_aggregate():
    assert compute_compliance_score(Verdict.INCONCLUSIVE, 0.4, []) is None
    # aggregate ignores the None (R3-F3) — mean of [1.0, 0.0], not /3
    assert aggregate_score([1.0, None, 0.0]) == pytest.approx(0.5)
    assert aggregate_score([None, None]) is None


def test_severity_weight_unknown_defaults_medium():
    assert severity_weight("bogus") == severity_weight("medium")


def test_score_is_deterministic():
    issues = [m.VerificationIssue("high", "c", "d")]
    a = compute_compliance_score(Verdict.PASS, 0.8, issues)
    b = compute_compliance_score(Verdict.PASS, 0.8, issues)
    assert a == b


# --- requirement loader + join corroboration (FR-1 / S-R1-5) ----------------

def _seed(tmp_path, tasks):
    seed = tmp_path / "prime-context-seed-enriched.json"
    seed.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
    return tmp_path


def test_loader_joins_and_corroborates(tmp_path):
    out = _seed(tmp_path, [{
        "task_id": "PI-001",
        "config": {
            "task_description": "Do the thing. Never compute X.",
            "context": {"feature_id": "PI-001", "target_files": ["app/thing.py"],
                        "negative_scope": ["invent X"], "language_id": "python"},
        },
    }])
    idx = SeedIndex.load(out)
    loaded, reason = idx.lookup("PI-001", generated_files=["app/thing.py"])
    assert reason is None
    assert loaded.requirement_text.startswith("Do the thing")
    assert loaded.negative_scope == ["invent X"]
    assert idx.corroborated("PI-001", ["app/thing.py"]) is True


def test_loader_mismatched_files_is_ambiguous(tmp_path):
    out = _seed(tmp_path, [{
        "task_id": "PI-001",
        "config": {"task_description": "x", "context": {"feature_id": "PI-001",
                   "target_files": ["app/a.py"]}},
    }])
    idx = SeedIndex.load(out)
    loaded, reason = idx.lookup("PI-001", generated_files=["app/totally_different.py"])
    assert loaded is None
    assert reason == InconclusiveReason.REQUIREMENT_JOIN_AMBIGUOUS


def test_loader_missing_feature_unavailable(tmp_path):
    idx = SeedIndex.load(_seed(tmp_path, []))
    loaded, reason = idx.lookup("PI-999")
    assert loaded is None
    assert reason == InconclusiveReason.REQUIREMENT_TEXT_UNAVAILABLE


def test_loader_id_collision_is_ambiguous(tmp_path):
    out = _seed(tmp_path, [
        {"task_id": "PI-001", "config": {"task_description": "a", "context": {"feature_id": "PI-001"}}},
        {"task_id": "PI-001b", "config": {"task_description": "b", "context": {"feature_id": "PI-001"}}},
    ])
    idx = SeedIndex.load(out)
    _, reason = idx.lookup("PI-001")
    assert reason == InconclusiveReason.REQUIREMENT_JOIN_AMBIGUOUS


def test_loader_latest_seed_by_mtime(tmp_path):
    import os
    old = tmp_path / "prime-context-seed.json"
    old.write_text(json.dumps({"tasks": [{"task_id": "OLD", "config": {"task_description": "old",
                   "context": {"feature_id": "OLD"}}}]}), encoding="utf-8")
    new = tmp_path / "prime-context-seed-enriched.json"
    new.write_text(json.dumps({"tasks": [{"task_id": "NEW", "config": {"task_description": "new",
                   "context": {"feature_id": "NEW"}}}]}), encoding="utf-8")
    t = os.stat(new).st_mtime
    os.utime(old, (t - 100, t - 100))
    idx = SeedIndex.load(tmp_path)
    assert idx.lookup("NEW")[0] is not None
    assert idx.lookup("OLD")[0] is None  # older seed ignored (R1-S5)


# --- triage (FR-4/5/5a) -----------------------------------------------------

def test_structural_emptiness_outranks_keyword_score():
    cfg = ReportConfig(suspicion_threshold=0.5)
    # High keyword requirement_score but a fake_work_stub → must still rank high-suspicion (F-R1-1).
    feats = [{"feature_id": "stubby", "success": True, "requirement_score": 0.95,
              "root_cause": "fake_work_stub", "semantic_error_count": 1}]
    cands = triage(feats, cfg)
    assert cands and cands[0].suspicion_score >= 0.5
    assert cands[0].reason == SelectionReason.SUSPECT


def test_reserved_pass_quota_independent_of_budget():
    cfg = ReportConfig(suspicion_threshold=0.5, max_escalations=1, reserved_pass_quota=2)
    feats = (
        [{"feature_id": f"fail{i}", "success": False, "root_cause": "x"} for i in range(3)]
        + [{"feature_id": f"ok{i}", "success": True, "requirement_score": 0.9} for i in range(4)]
    )
    cands = triage(feats, cfg)
    reasons = [c.reason for c in cands]
    # Budget=1 suspect reviewed; the rest of the suspects are not_reviewed (no silent caps)…
    assert reasons.count(SelectionReason.SUSPECT) == 1
    assert reasons.count(SelectionReason.NOT_REVIEWED) == 2
    # …and the reserved PASS sample still gets its quota despite the saturated suspect budget.
    assert reasons.count(SelectionReason.PASS_SAMPLE) == 2
    assert len(reviewable(cands)) == 3  # 1 suspect + 2 pass-sample


# --- cache idempotency (S-R1-2) ---------------------------------------------

def test_verdict_cache_roundtrip(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("print(1)", encoding="utf-8")
    ck = code_checksum(["a.py"], root=tmp_path)

    cache = VerdictCache.load(tmp_path, run_id="run-1")
    assert cache.get("F1", ck) is None
    cache.put("F1", ck, {"verdict": "pass", "confidence": 0.9})
    cache.save()

    reloaded = VerdictCache.load(tmp_path, run_id="run-1")
    assert reloaded.get("F1", ck) == {"verdict": "pass", "confidence": 0.9}

    # Code change ⇒ checksum change ⇒ cache miss (re-review).
    f.write_text("print(2)", encoding="utf-8")
    assert reloaded.get("F1", code_checksum(["a.py"], root=tmp_path)) is None


def test_report_to_dict_key_and_run_nesting():
    r = m.SemanticComplianceReport(
        generated_at="t", scr_version="0.1.0", run_id="run-9", output_dir="d",
        config=m.ReportConfig(), summary=m.ReportSummary(pass_=3, fail=1))
    d = r.to_dict()
    assert d["summary"]["pass"] == 3 and "pass_" not in d["summary"]
    assert d["run"] == {"run_id": "run-9", "output_dir": "d", "language": "python"}
