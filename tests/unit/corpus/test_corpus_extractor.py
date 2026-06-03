"""Tests for the corpus extractor + its postmortem wiring."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from startd8.corpus.extractor import extract_corpus_from_run, stable_run_id
from startd8.corpus.registry import ControlledCorpusRegistry


def _feat(name, target_files, success, req, dqs=1.0):
    return SimpleNamespace(name=name, target_files=target_files, success=success,
                           requirement_score=req, disk_quality_score=dqs)


def _report(features):
    return SimpleNamespace(report_id="rep-x", features=features)


# ---- extractor unit behavior ---------------------------------------------
def test_extractor_basic_and_skips_empty_targets():
    report = _report([
        _feat("Email Service JSON Logger", ["src/emailservice/logger.py"], True, 1.0),
        _feat("orphan feature", [], True, 1.0),  # no target -> skipped (PI-noise)
    ])
    obs = extract_corpus_from_run(report, "run-001")
    assert len(obs) == 1
    o = obs[0]
    assert o.kind == "file"
    assert o.bindings[0].language == "python"
    assert o.bindings[0].construct_ref == "src/emailservice/logger.py"
    assert o.success is True and o.requirement_score == 1.0
    assert o.confidence == "inferred"  # R2-F1: provenance, not disk-quality


def test_extractor_confidence_is_provenance_not_quality():
    # R2-F1: confidence must NOT be derived from disk_quality_score
    high = extract_corpus_from_run(_report([_feat("X", ["src/x.go"], True, 1.0, dqs=1.0)]), "r")
    low = extract_corpus_from_run(_report([_feat("X", ["src/x.go"], True, 1.0, dqs=0.2)]), "r")
    assert high[0].confidence == low[0].confidence == "inferred"
    assert low[0].bindings[0].language == "go"


def test_extractor_multifile_keeps_all_targets():
    # R2-S4: multi-file feature emits one observation per target
    obs = extract_corpus_from_run(
        _report([_feat("Multi", ["src/a.py", "src/b.py"], True, 1.0)]), "r")
    assert {o.bindings[0].construct_ref for o in obs} == {"src/a.py", "src/b.py"}


def test_stable_run_id_finds_run_ancestor(tmp_path):
    d = tmp_path / "run-122-20260514T1140" / "plan-ingestion"
    d.mkdir(parents=True)
    assert stable_run_id(str(d)) == "run-122-20260514T1140"
    assert stable_run_id(str(tmp_path / "gemini-python-0141")) == "gemini-python-0141"


def test_extractor_feeds_registry_idempotent():
    report = _report([_feat("Logger", ["src/emailservice/logger.py"], True, 1.0)])
    reg = ControlledCorpusRegistry()
    reg.merge_run("run-001", extract_corpus_from_run(report, "run-001"))
    reg.merge_run("run-001", extract_corpus_from_run(report, "run-001"))  # idempotent
    assert len(reg) == 1
    assert reg.terms[0].determinism.n_observations == 1


# ---- trove-backed integration (skips if external trove absent) -----------
_TROVE = Path("/Users/neilyashinsky/Documents/dev/online-boutique-demo/"
              ".cap-dev-pipe/pipeline-output/online-boutique")


def _load_real_features(run_dir: Path):
    pm = run_dir / "plan-ingestion" / "prime-postmortem-report.json"
    if not pm.exists():
        return None
    data = json.loads(pm.read_text())
    feats = [SimpleNamespace(**{k: f.get(k) for k in
             ("name", "target_files", "success", "requirement_score", "disk_quality_score")})
             for f in data.get("features", [])]
    return _report(feats)


@pytest.mark.skipif(not _TROVE.exists(), reason="online-boutique trove not present")
def test_real_trove_cross_run_accumulation():
    runs = [d for d in sorted(_TROVE.glob("run-*")) if (_load_real_features(d) is not None)]
    if len(runs) < 2:
        pytest.skip("need >=2 runs with postmortems")
    reg = ControlledCorpusRegistry()
    for d in runs:
        rid = stable_run_id(str(d / "plan-ingestion"))
        reg.merge_run(rid, extract_corpus_from_run(_load_real_features(d), rid))

    # cross-run accumulation works: some recurring term reached maturity >= 2
    assert any(t.maturity >= 2 for t in reg.terms)

    # emailservice/logger.py is structurally stable wherever it recurs
    logger_term = next((t for t in reg.terms
                        if t.canonical_key == "src/emailservice/logger.py"), None)
    if logger_term:
        assert logger_term.determinism.success_stability == 1.0

    # the Flask RAG is the known false-PASS (stable build, low requirement_score)
    rag = next((t for t in reg.terms
                if t.canonical_key.endswith("shoppingassistantservice.py")), None)
    if rag and rag.determinism.mean_requirement_score is not None:
        assert rag.determinism.corpus_class in ("false_pass_risk", "mixed", "residue_corpus_gap")
