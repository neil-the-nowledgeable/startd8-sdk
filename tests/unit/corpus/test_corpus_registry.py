"""Tests for the Controlled Corpus registry — proves the FR success criteria:
idempotent + order-independent merge, maturity-from-recurrence, two-axis
determinism (false_pass_risk), and persistence round-trip.
"""
import json

import pytest

from startd8.corpus import (
    Binding,
    ControlledCorpusRegistry,
    TermObservation,
)
from startd8.corpus.canonical import canonical_key


def _obs(target, run_success, req, surface, *, conf="explicit", lang="python"):
    """One file-term observation."""
    ck = canonical_key("file", surface, target)
    return TermObservation(
        kind="file", canonical_key=ck, surface_form=surface,
        bindings=[Binding(language=lang, construct_kind="file", construct_ref=target,
                          source_reference="deterministic")],
        confidence=conf, success=run_success, requirement_score=req,
    )


def _run(success=True, req=1.0, surface="Email Service JSON Logger"):
    return [_obs("src/emailservice/logger.py", success, req, surface)]


# ---- idempotency (FR-4 success criterion) --------------------------------
def test_merge_is_idempotent():
    r = ControlledCorpusRegistry()
    r.merge_run("run-001", _run())
    snap1 = json.dumps([t.to_dict() for t in r.terms], sort_keys=True)
    r.merge_run("run-001", _run())  # same run again
    snap2 = json.dumps([t.to_dict() for t in r.terms], sort_keys=True)
    assert snap1 == snap2
    assert r.terms[0].determinism.n_observations == 1
    assert r.terms[0].source_run_ids == ["run-001"]


# ---- order independence (FR-4 success criterion) -------------------------
def test_merge_is_order_independent():
    a = ControlledCorpusRegistry()
    a.merge_run("run-001", _run(req=1.0, surface="Shared JSON Logger — emailservice"))
    a.merge_run("run-002", _run(req=1.0, surface="Email Service JSON Logger"))
    a.merge_run("run-003", _run(req=1.0, surface="JSON logger"))

    b = ControlledCorpusRegistry()
    b.merge_run("run-003", _run(req=1.0, surface="JSON logger"))
    b.merge_run("run-001", _run(req=1.0, surface="Shared JSON Logger — emailservice"))
    b.merge_run("run-002", _run(req=1.0, surface="Email Service JSON Logger"))

    sa = json.dumps([t.to_dict() for t in a.terms], sort_keys=True)
    sb = json.dumps([t.to_dict() for t in b.terms], sort_keys=True)
    assert sa == sb  # byte-identical regardless of order


# ---- title drift collapses to one term, stability stays 1.0 --------------
def test_title_drift_one_term_multiple_surface_forms():
    r = ControlledCorpusRegistry()
    r.merge_run("run-001", _run(surface="Shared JSON Logger — emailservice"))
    r.merge_run("run-002", _run(surface="Email Service JSON Logger"))
    assert len(r) == 1                                   # one binding, not two
    term = r.terms[0]
    assert len(term.surface_forms) == 2                  # both labels captured (residue)
    assert term.determinism.success_stability == 1.0


# ---- maturity from recurrence (FR-3) -------------------------------------
def test_maturity_ladder():
    r = ControlledCorpusRegistry()
    r.merge_run("run-001", _run())
    assert r.terms[0].maturity == 1                      # extracted-once
    r.merge_run("run-002", _run())
    assert r.terms[0].maturity == 2                      # cross-run-validated
    r.merge_run("run-003", _run())
    assert r.terms[0].maturity in (3, 4)                 # stable / canonical


# ---- two-axis determinism: the false_pass_risk (FR-8) --------------------
def test_false_pass_risk_detected():
    r = ControlledCorpusRegistry()
    # structurally passes every run but only half-satisfies the requirement
    for rid in ("run-001", "run-002", "run-003"):
        r.merge_run(rid, [_obs("src/shoppingassistantservice/shoppingassistantservice.py",
                               True, 0.5, "Shopping Assistant Service — Flask RAG")])
    term = r.terms[0]
    assert term.determinism.success_stability == 1.0
    assert term.determinism.mean_requirement_score == 0.5
    assert term.determinism.corpus_class == "false_pass_risk"   # NOT deterministic_candidate


def test_deterministic_candidate_requires_both_axes():
    r = ControlledCorpusRegistry()
    for rid in ("run-001", "run-002"):
        r.merge_run(rid, _run(success=True, req=1.0))
    assert r.terms[0].determinism.corpus_class == "deterministic_candidate"


def test_residue_corpus_gap():
    r = ControlledCorpusRegistry()
    r.merge_run("run-001", _run(success=True, req=1.0))
    r.merge_run("run-002", _run(success=False, req=0.0))
    r.merge_run("run-003", _run(success=False, req=0.0))
    assert r.terms[0].determinism.success_stability < 0.7
    assert r.terms[0].determinism.corpus_class == "residue_corpus_gap"


# ---- binding precedence (FR-4) -------------------------------------------
def test_binding_precedence_upgrade():
    r = ControlledCorpusRegistry()
    r.merge_run("run-001", [TermObservation(
        kind="file", canonical_key="src/x.py", surface_form="X",
        bindings=[Binding("python", "file", "src/x.py", "inferred")], confidence="inferred")])
    r.merge_run("run-002", [TermObservation(
        kind="file", canonical_key="src/x.py", surface_form="X",
        bindings=[Binding("python", "file", "src/x.py", "human-yaml")], confidence="explicit")])
    term = r.terms[0]
    assert term.bindings[0].source_reference == "human-yaml"   # higher precedence wins
    assert term.confidence == "explicit"


# ---- persistence round-trip (FR-1) ---------------------------------------
def test_persistence_round_trip(tmp_path):
    r = ControlledCorpusRegistry(project_id="ob")
    r.merge_run("run-001", _run())
    r.merge_run("run-002", _run())
    p = tmp_path / "controlled-corpus.json"
    r.save(p)
    assert p.exists()
    r2 = ControlledCorpusRegistry.load(p)
    assert len(r2) == len(r)
    assert r2.terms[0].maturity == r.terms[0].maturity
    assert r2.terms[0].determinism.success_stability == r.terms[0].determinism.success_stability


def test_load_missing_returns_empty(tmp_path):
    r = ControlledCorpusRegistry.load(tmp_path / "nope.json")
    assert len(r) == 0


# ---- CRP R1 triage: validation approaches for accepted suggestions ----
from startd8.corpus.models import classify_determinism, SCHEMA_VERSION


def test_classify_unscored_not_deterministic_candidate():
    # R1-F1: stable but no requirement_score -> distinct class, NOT deterministic_candidate
    assert classify_determinism(0.98, None, 3) == "deterministic_candidate_unscored"
    assert classify_determinism(0.98, 1.0, 3) == "deterministic_candidate"


def test_classify_min_sample_guard():
    # R1-F5: a single observation is not evidence of determinism
    assert classify_determinism(1.0, 1.0, 1) == "insufficient_samples"
    assert classify_determinism(1.0, 1.0, 2) == "deterministic_candidate"


def test_classify_mixed_split():
    # R2-F2: the old "mixed" splits into two remediation paths
    assert classify_determinism(0.85, 1.0, 3) == "needs_more_runs"        # mid stability
    assert classify_determinism(0.98, 0.8, 3) == "needs_semantic_review"  # mid req_score


def test_proto_term_no_observations_caps_at_L2():
    # R1-F2/S4: recurrence without observed stability must not reach L3
    r = ControlledCorpusRegistry()
    for i in range(5):
        r.merge_run(f"run-{i}", [TermObservation(
            kind="service", canonical_key="cartservice", surface_form="CartService",
            confidence="explicit")])  # no success/requirement_score => no determinism obs
    term = r.terms[0]
    assert term.determinism.n_observations == 0
    assert term.maturity == 2  # NOT 3 — stability never observed


def test_schema_major_mismatch_returns_empty(tmp_path):
    # R1-F3: incompatible major schema -> start empty (no silent corruption)
    import json
    r = ControlledCorpusRegistry()
    r.merge_run("run-001", _run())
    p = tmp_path / "c.json"
    r.save(p)
    data = json.loads(p.read_text())
    data["schema_version"] = "0.9.0"  # incompatible major
    p.write_text(json.dumps(data))
    assert len(ControlledCorpusRegistry.load(p)) == 0
