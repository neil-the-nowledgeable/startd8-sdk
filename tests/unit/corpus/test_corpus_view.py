"""Tests for the corpus read views (FR-9/10): SCR triage + generation authorities."""
import pytest

from startd8.corpus import (
    Binding,
    ControlledCorpusRegistry,
    TermObservation,
    as_project_knowledge,
    render_authorities_md,
    should_escalate,
    stable_authorities,
    triage_signal,
)
from startd8.corpus.canonical import canonical_key


def _file_obs(target, success, req, surface):
    return TermObservation(
        kind="file", canonical_key=canonical_key("file", surface, target),
        surface_form=surface,
        bindings=[Binding("python", "file", target, "deterministic")],
        confidence="explicit", success=success, requirement_score=req)


def _reg_with(target, results, surface="X"):
    """results: list of (success, req); each as its own run."""
    r = ControlledCorpusRegistry()
    for i, (s, q) in enumerate(results):
        r.merge_run(f"run-{i:03d}", [_file_obs(target, s, q, surface)])
    return r


# ---- SCR triage (FR-10) --------------------------------------------------
def test_triage_signal_shape():
    r = _reg_with("src/a.py", [(True, 1.0), (True, 1.0)])
    sig = triage_signal(r, "src/a.py")
    assert sig["success_stability"] == 1.0
    assert sig["corpus_class"] == "deterministic_candidate"
    assert sig["maturity"] >= 2
    assert sig["n_observations"] == 2


def test_triage_signal_unseen_is_none():
    r = ControlledCorpusRegistry()
    assert triage_signal(r, "src/never.py") is None


def test_should_escalate_unseen():
    r = ControlledCorpusRegistry()
    assert should_escalate(r, "src/never.py") is True


def test_should_not_escalate_deterministic_candidate():
    r = _reg_with("src/logger.py", [(True, 1.0), (True, 1.0)])
    assert should_escalate(r, "src/logger.py") is False


def test_should_escalate_false_pass_risk():
    # stable build, low requirement_score -> must escalate (the SCR's reason to exist)
    r = _reg_with("src/rag.py", [(True, 0.5), (True, 0.5), (True, 0.5)])
    assert triage_signal(r, "src/rag.py")["corpus_class"] == "false_pass_risk"
    assert should_escalate(r, "src/rag.py") is True


def test_should_escalate_residue_gap():
    r = _reg_with("src/docker", [(True, 1.0), (False, 0.0), (False, 0.0)])
    assert should_escalate(r, "src/docker") is True


# ---- generation authorities (FR-9) --------------------------------------
def test_stable_authorities_excludes_immature_and_false_pass():
    r = ControlledCorpusRegistry()
    # mature, good
    r.merge_run("r1", [_file_obs("src/good.py", True, 1.0, "Good")])
    r.merge_run("r2", [_file_obs("src/good.py", True, 1.0, "Good")])
    # mature but false-pass
    r.merge_run("r1", [_file_obs("src/rag.py", True, 0.5, "RAG")])
    r.merge_run("r2", [_file_obs("src/rag.py", True, 0.5, "RAG")])
    # immature (one run only)
    r.merge_run("r3", [_file_obs("src/new.py", True, 1.0, "New")])

    auth = stable_authorities(r, min_maturity=2)
    keys = {a["canonical"] for a in auth}
    assert "src/good.py" in keys
    assert "src/rag.py" not in keys      # false_pass excluded
    assert "src/new.py" not in keys      # immature excluded


def test_render_authorities_md():
    r = _reg_with("src/emailservice/logger.py", [(True, 1.0), (True, 1.0)], surface="Logger")
    md = render_authorities_md(r)
    assert "Established project vocabulary" in md
    assert "src/emailservice/logger.py" in md


def test_render_authorities_md_empty_when_nothing_mature():
    r = _reg_with("src/x.py", [(True, 1.0)])  # one run -> maturity 1
    assert render_authorities_md(r, min_maturity=2) == ""


# ---- ProjectKnowledge-shaped view (FR-9) --------------------------------
def test_as_project_knowledge_shape_and_boundary():
    r = _reg_with("src/a.py", [(True, 1.0), (True, 1.0)])
    pk = as_project_knowledge(r, project_root="/proj")
    assert pk.project_root == "/proj"
    assert pk.field_sets == ()        # corpus does not own Prisma authorities
    assert pk.negatives == ()
    assert pk.omissions and "stable_authorities" in pk.omissions[0]
