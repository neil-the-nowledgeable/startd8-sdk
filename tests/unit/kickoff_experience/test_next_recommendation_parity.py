"""Parity/consistency tests for the unified next-recommendation formatter (FR-NU + CRP R1)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from startd8.kickoff_experience import concierge_view, ranking
from startd8.kickoff_experience.docs import live_schema_text, load_kickoff_docs
from startd8.kickoff_experience.readiness import build_readiness
from startd8.kickoff_experience.red_carpet import (
    RedCarpetStage,
    RedCarpetState,
    build_red_carpet_state,
    playbook_top_subject,
)
from startd8.kickoff_experience.state import build_kickoff_state


def _kickoff_state(root):
    return build_kickoff_state(load_kickoff_docs(root), live_schema_text=live_schema_text(root))


def _rv_dict(blockers):
    return {"blockers": blockers}


# ── FR-NU-2 / R1-S1: blocker_cta is the single source (monkeypatch hits BOTH surfaces) ────────────

def test_blocker_cta_single_source(monkeypatch, tmp_path):
    rv = build_readiness(tmp_path)
    ks = _kickoff_state(tmp_path)
    sentinel = ranking.NextAction("SENTINEL", "T", "D")
    monkeypatch.setattr(ranking, "blocker_cta", lambda r: sentinel)
    # next_action Tier-1 routes through it
    assert ranking.next_action(ks, rv).kind == "SENTINEL"
    # concierge blocker branch routes through it (module-qualified → patch bites)
    assert concierge_view._next_action("complete", rv.to_dict())["kind"] == "SENTINEL"


def test_blocker_wording_defined_exactly_once():
    """R1-S4 source-scan: the blocker CTA wording lives in exactly one place (blocker_cta)."""
    pkg = Path(ranking.__file__).parent
    hits = sum(
        f.read_text(encoding="utf-8").count('"Resolve readiness blocker:')
        + f.read_text(encoding="utf-8").count("Resolve readiness blocker: {section}")
        for f in pkg.rglob("*.py")
    )
    # exactly one literal source (the f-string in blocker_cta)
    literal = sum(f.read_text(encoding="utf-8").count("Resolve readiness blocker: {section}")
                  for f in pkg.rglob("*.py"))
    assert literal == 1, f"blocker wording must be defined once; found {literal}"


# ── FR-NU-3 / R1-F3/F4: concierge blocker CTA == next_action; package-missing diverges ────────────

def test_concierge_blocker_matches_next_action(tmp_path):
    rv = build_readiness(tmp_path)
    ks = _kickoff_state(tmp_path)
    na = ranking.next_action(ks, rv)
    cv = concierge_view._next_action("complete", rv.to_dict())
    assert cv == na.to_dict()          # identical wording across surfaces
    assert cv["detail"]                # non-empty (R1-S3 fallback guarantee)


def test_concierge_package_missing_diverges(tmp_path):
    rv = build_readiness(tmp_path)
    # package incomplete → instantiate CTA, an expected divergence from the ungated next_action
    assert concierge_view._next_action("missing", rv.to_dict())["kind"] == "instantiate"
    assert ranking.next_action(_kickoff_state(tmp_path), rv).kind == "resolve_blocker"


def test_concierge_none_readiness_is_ready():
    # R1-S6: build_readiness exception path passes readiness=None → ready, never crashes.
    assert concierge_view._next_action("complete", None)["kind"] == "ready"


# ── FR-NU-4 / R1-S5: subject-level agreement (schema-absent) + None handling ──────────────────────

def test_subject_agreement_schema_absent(tmp_path):
    rv = build_readiness(tmp_path)          # greenfield: schema absent
    na = ranking.next_action(_kickoff_state(tmp_path), rv)
    rc = build_red_carpet_state(tmp_path)
    assert na.kind == "resolve_blocker"
    assert ranking.blocker_subject(na) == playbook_top_subject(rc) == "data_model"


def test_playbook_top_subject_none_for_run_stage():
    # R1-S5: when rank-1 is not a gate stage (offerable → run), the subject is None (assert skipped).
    from startd8.kickoff_experience.red_carpet_advisor import NextStep
    state = RedCarpetState(
        stages=(RedCarpetStage("run", "done", ""),), next_stage=None,
        cascade_offerable=True, unmet_gates=(), readiness_score=1.0,
        next_steps=(NextStep(1, "run", "Run the $0 cascade", "…", "startd8 generate backend"),),
    )
    assert playbook_top_subject(state) is None


# ── R1-S6 / R1-S3: normalization contract + non-empty fallback ────────────────────────────────────

def test_blocker_cta_normalization():
    assert ranking.blocker_cta(None) is None
    assert ranking.blocker_cta({"blockers": []}) is None
    assert ranking.blocker_cta(_rv_dict([{"section": "Pages"}])) is not None  # Mapping form
    # ReadinessView form
    rv = build_readiness(tempfile.mkdtemp())
    assert (ranking.blocker_cta(rv) is None) or (ranking.blocker_cta(rv).kind == "resolve_blocker")


def test_non_empty_detail_fallback():
    cta = ranking.blocker_cta(_rv_dict([{"section": "X"}]))  # no consequence/status
    assert cta.detail == "Fill the kickoff inputs the cascade still needs."


# ── R1-S2 / R1-F1: shared vocabulary + no playbook coupling ────────────────────────────────────────

def test_subject_vocabulary_is_shared():
    # every stage subject and every blocker subject is drawn from the ONE shared SUBJECTS set (or None).
    for subj in ranking._STAGE_SUBJECT.values():
        assert subj in ranking.SUBJECTS
    for section in ("Services", "Entities & CRUD", "Pages & Nav", "Content Inputs", "unknown"):
        s = ranking.blocker_subject(ranking.NextAction("resolve_blocker", f"X: {section}", "no contract"))
        assert s in ranking.SUBJECTS or s is None


def test_advisor_does_not_call_the_formatter():
    # R1-F1: the playbook keeps its build-action wording — it must not route through blocker_cta.
    import startd8.kickoff_experience.red_carpet_advisor as adv
    src = Path(adv.__file__).read_text(encoding="utf-8")
    assert "blocker_cta" not in src
