"""Validation tests for CRP rounds R3–R4 accepted suggestions."""
import json
from types import SimpleNamespace

import startd8.corpus.models as M
from startd8.corpus import Binding, ControlledCorpusRegistry, TermObservation
from startd8.corpus.canonical import canonical_key
from startd8.corpus.extractor import (
    extract_corpus_from_run, extract_seed_terms_from_context, input_scope_id_for,
)
from startd8.corpus.view import should_escalate, stable_authorities


def _file_obs(target, success, req, surface="X", scope=""):
    return TermObservation(
        kind="file", canonical_key=canonical_key("file", surface, target), surface_form=surface,
        bindings=[Binding("python", "file", target, "deterministic")],
        confidence="inferred", success=success, requirement_score=req, input_scope_id=scope)


def _reg(target, results, surface="X"):
    r = ControlledCorpusRegistry()
    for i, (s, q) in enumerate(results):
        r.merge_run(f"run-{i}", [_file_obs(target, s, q, surface)])
    return r


# ---- R3-S1: precedence is a superset of forward_manifest --------------------
def test_source_precedence_extends_forward_manifest():
    from startd8.forward_manifest_extractor import _SOURCE_PRECEDENCE as fm
    for k, v in fm.items():
        assert M.SOURCE_PRECEDENCE[k] == v  # shared values preserved
    assert "human" in M.SOURCE_PRECEDENCE and "inferred" in M.SOURCE_PRECEDENCE


# ---- R3-F2: corpus_class is NOT persisted (derived) -------------------------
def test_corpus_class_not_in_canonical_dict():
    r = _reg("src/a.py", [(True, 1.0), (True, 1.0)])
    d = r.terms[0].to_dict()
    assert "corpus_class" not in d
    assert "corpus_class_computed" in r.terms[0].as_debug_dict()


# ---- R3-F1: eviction never removes false_pass_risk --------------------------
def test_eviction_protects_false_pass_risk(monkeypatch):
    monkeypatch.setattr(M, "MAX_CORPUS_SIZE", 2)
    import startd8.corpus.registry as R
    monkeypatch.setattr(R, "MAX_CORPUS_SIZE", 2)
    r = ControlledCorpusRegistry()
    # a false_pass_risk term (stable build, low req) at L2
    r.merge_run("r0", [_file_obs("src/rag.py", True, 0.5)])
    r.merge_run("r1", [_file_obs("src/rag.py", True, 0.5)])
    # flood with L1 file terms to force eviction
    for i in range(5):
        r.merge_run(f"f{i}", [_file_obs(f"src/x{i}.py", True, 1.0)])
    keys = {t.canonical_key for t in r.terms}
    assert "src/rag.py" in keys  # never evicted


# ---- R4-F1: cross-scope observations do not share a stability aggregate -----
def test_cross_scope_not_merged():
    r = ControlledCorpusRegistry()
    # same target, two scopes: scope feat17 all-pass, scope feat7 all-fail
    for i in range(3):
        r.merge_run(f"a{i}", [_file_obs("src/s.py", True, 1.0, scope="feat17")])
    for i in range(2):
        r.merge_run(f"b{i}", [_file_obs("src/s.py", False, 0.0, scope="feat7")])
    det = r.terms[0].determinism
    # dominant scope = feat17 (3 obs) -> stability 1.0, NOT blended to 0.6
    assert det.success_stability == 1.0
    assert set(det.scopes()) == {"feat7", "feat17"}


def test_input_scope_id_from_report():
    rep = SimpleNamespace(total_features=17, features=[])
    assert input_scope_id_for(rep) == "feat17"


# ---- R4-F2: should_escalate uses BOTH axes ----------------------------------
def test_escalate_high_stability_mid_req():
    # stability 1.0 but req 0.8 -> needs_semantic_review -> escalate (R4-F2)
    r = _reg("src/mid.py", [(True, 0.8), (True, 0.8), (True, 0.8)])
    assert r.terms[0].determinism.corpus_class == "needs_semantic_review"
    assert should_escalate(r, "src/mid.py") is True


def test_no_escalate_only_for_deterministic_candidate():
    r = _reg("src/good.py", [(True, 1.0), (True, 1.0)])
    assert should_escalate(r, "src/good.py") is False


# ---- R4-F3: corpus_version is monotonic + persisted -------------------------
def test_corpus_version_increments(tmp_path):
    r = ControlledCorpusRegistry()
    r.merge_run("r0", [_file_obs("src/a.py", True, 1.0)])
    r.merge_run("r1", [_file_obs("src/a.py", True, 1.0)])
    assert r.corpus_version == 2
    p = tmp_path / "c.json"
    r.save(p)
    assert json.loads(p.read_text())["corpus_version"] == 2
    assert ControlledCorpusRegistry.load(p).corpus_version == 2


# ---- R3-S2: unobserved terms excluded from authorities ----------------------
def test_unobserved_terms_excluded_from_authorities():
    r = ControlledCorpusRegistry()
    # a vocabulary (service) term with recurrence but no determinism observations
    for i in range(3):
        r.merge_run(f"r{i}", [TermObservation(
            kind="service", canonical_key="cartservice", surface_form="CartService",
            confidence="inferred")])
    assert r.terms[0].maturity == 2
    assert r.terms[0].determinism.corpus_class == "unobserved"
    assert stable_authorities(r) == []  # zero-evidence term not an authority


# ---- R4-S1: vocabulary terms grow from the seed -----------------------------
def test_extract_seed_terms(tmp_path):
    seed = {"service_communication_graph": {"services": {
        "emailservice": {}, "cartservice": {}, "shared": {},
        "reqcdpobs001servicelevelobjectives": {}, "multiserviceprojectguidance": {},
    }}}
    (tmp_path / "prime-context-seed.json").write_text(json.dumps(seed))
    obs = extract_seed_terms_from_context(str(tmp_path), "run-1")
    keys = {o.canonical_key for o in obs}
    assert "emailservice" in keys and "cartservice" in keys
    assert not any("req" in k or "guidance" in k for k in keys)  # pseudo-services filtered
    assert all(o.kind == "service" for o in obs)


def test_extract_seed_terms_missing_seed_is_empty(tmp_path):
    assert extract_seed_terms_from_context(str(tmp_path), "run-1") == []
