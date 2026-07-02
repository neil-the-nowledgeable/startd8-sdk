# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M2 tests — the Teian CLI (recommend/review/approve/reject) and the capture.py-splice approve path."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from startd8.cli_panel import panel_app
from startd8.stakeholder_panel.models import Recommendation
from startd8.stakeholder_panel.proposals import ProposalStore

from .conftest import ScriptedAgent

runner = CliRunner()

_ROSTER = (
    "domain: stakeholders\n"
    "personas:\n"
    "  - role_id: product-owner\n"
    "    display_name: Product Owner\n"
    "    goals: ['ship the MVP']\n"
    "  - role_id: architect\n"
    "    display_name: Architect\n"
    "    goals: ['keep it clean']\n"
)

# business-targets with a human comment that MUST survive an approve splice (SOTTO / R2-S1).
_BUSINESS_TARGETS = (
    "# BUSINESS TARGETS — do not delete this comment\n"
    "domain: business-targets\n"
    "provenance_default: estimate\n"
    "product_funnel:\n"
    "  signup_rate:                 # inline comment must survive\n"
    '    target: "<NN%>"\n'
    "    why: <core funnel KPI>\n"
)

_CONVENTIONS = (
    "domain: conventions\n"
    "provenance_default: estimate\n"
    "language: python\n"
    "data_model:\n"
    '  money: "<cents | float>"\n'
)


def _project(tmp_path: Path) -> Path:
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "stakeholders.yaml").write_text(_ROSTER, encoding="utf-8")
    (inputs / "business-targets.yaml").write_text(_BUSINESS_TARGETS, encoding="utf-8")
    (inputs / "conventions.yaml").write_text(_CONVENTIONS, encoding="utf-8")
    return tmp_path


def _stage(tmp_path, session, *recs):
    ProposalStore(tmp_path, session).save(list(recs))


def _signup_rec(session="sess-1"):
    return Recommendation(
        domain="business-targets",
        value_path="product_funnel.signup_rate",
        recommended_value={"target": "40%", "why": "the core funnel"},
        composite_keys=("target", "why"),
        role_id="product-owner",
        origin="panel:product-owner",
        session_id=session,
    )


# --- recommend (mock agent, no keys) --------------------------------------------------


def test_recommend_drafts_and_stages(tmp_path, monkeypatch):
    _project(tmp_path)
    import startd8.utils.agent_resolution as ar

    monkeypatch.setattr(
        ar,
        "resolve_agent_spec",
        lambda spec, **kw: ScriptedAgent(
            reply="VALUE: fastapi || TARGET: fastapi || WHY: solid default\nGROUNDING: grounded"
        ),
    )
    res = runner.invoke(panel_app, ["recommend", "--project", str(tmp_path)])
    assert res.exit_code == 0, res.stdout
    assert "drafted 2 field(s)" in res.stdout
    # a staging file now exists
    from startd8.stakeholder_panel.proposals import session_ids

    assert session_ids(tmp_path), "no staging session written"


# --- approve (capture.py splice) ------------------------------------------------------


def test_approve_composite_preserves_comments_and_updates_yaml(tmp_path):
    _project(tmp_path)
    _stage(tmp_path, "sess-1", _signup_rec())
    res = runner.invoke(
        panel_app,
        ["approve", "--field", "business-targets:product_funnel.signup_rate", "--project", str(tmp_path)],
    )
    assert res.exit_code == 0, res.stdout
    assert "approved" in res.stdout

    yaml_text = (tmp_path / "docs/kickoff/inputs/business-targets.yaml").read_text()
    assert "target: 40%" in yaml_text  # spliced (composite → two scalar writes, R4-S1)
    assert "why: the core funnel" in yaml_text
    assert "# BUSINESS TARGETS — do not delete this comment" in yaml_text  # SOTTO
    assert "# inline comment must survive" in yaml_text

    # audit trail updated (R1-S4)
    assert ProposalStore(tmp_path, "sess-1").get(
        "business-targets", "product_funnel.signup_rate"
    ).disposition == "approved"


def test_approve_gate_rejection_marks_invalid_and_leaves_file(tmp_path):
    _project(tmp_path)
    bad = Recommendation(
        domain="conventions",
        value_path="data_model.money",
        recommended_value="banana",  # not in the {cents, float} enum → strict parser rejects
        role_id="architect",
        origin="panel:architect",
    )
    _stage(tmp_path, "sess-1", bad)
    before = (tmp_path / "docs/kickoff/inputs/conventions.yaml").read_text()
    res = runner.invoke(
        panel_app, ["approve", "--field", "conventions:data_model.money", "--project", str(tmp_path)]
    )
    assert res.exit_code == 4, res.stdout  # _EXIT_GATE (R1-F3)
    assert "gate rejected" in res.stdout
    # file untouched, disposition flipped to invalid
    assert (tmp_path / "docs/kickoff/inputs/conventions.yaml").read_text() == before
    assert ProposalStore(tmp_path, "sess-1").get("conventions", "data_model.money").disposition == "invalid"


def test_approve_refuses_stale_field_unless_forced(tmp_path):
    _project(tmp_path)
    _stage(tmp_path, "sess-1", _signup_rec())
    # human fills the field directly in the YAML → the draft is stale (R3-S3)
    bt = tmp_path / "docs/kickoff/inputs/business-targets.yaml"
    bt.write_text(bt.read_text().replace('target: "<NN%>"', "target: 55%"), encoding="utf-8")

    res = runner.invoke(
        panel_app, ["approve", "--field", "business-targets:product_funnel.signup_rate", "--project", str(tmp_path)]
    )
    assert res.exit_code == 0
    assert "stale" in res.stdout
    assert "target: 55%" in bt.read_text()  # human edit preserved

    forced = runner.invoke(
        panel_app,
        ["approve", "--field", "business-targets:product_funnel.signup_rate", "--force", "--project", str(tmp_path)],
    )
    assert forced.exit_code == 0
    assert "target: 40%" in bt.read_text()  # --force overrides


def test_approve_all_and_manual_flip_hint(tmp_path):
    _project(tmp_path)
    # both unfilled fields drafted; approving all fully resolves both domains
    money = Recommendation(
        domain="conventions",
        value_path="data_model.money",
        recommended_value="cents",
        role_id="architect",
        origin="panel:architect",
    )
    _stage(tmp_path, "sess-1", _signup_rec(), money)
    res = runner.invoke(panel_app, ["approve", "--all", "--project", str(tmp_path)])
    assert res.exit_code == 0, res.stdout
    assert res.stdout.count("approved") >= 2
    assert "provenance_default: authored" in res.stdout  # manual-flip hint (R4-S2)


def test_reject_marks_disposition(tmp_path):
    _project(tmp_path)
    _stage(tmp_path, "sess-1", _signup_rec())
    res = runner.invoke(
        panel_app, ["reject", "--field", "business-targets:product_funnel.signup_rate", "--project", str(tmp_path)]
    )
    assert res.exit_code == 0
    assert ProposalStore(tmp_path, "sess-1").get(
        "business-targets", "product_funnel.signup_rate"
    ).disposition == "rejected"


# --- review ---------------------------------------------------------------------------


def test_review_shows_draft_brief_and_hides_stale(tmp_path):
    _project(tmp_path)
    _stage(tmp_path, "sess-1", _signup_rec())
    res = runner.invoke(panel_app, ["review", "--project", str(tmp_path)])
    assert res.exit_code == 0, res.stdout
    assert "product_funnel.signup_rate" in res.stdout
    assert "ship the MVP" in res.stdout  # persona brief adjacent (FR-KIR-9)
    assert "UNRATIFIED" in res.stdout

    # fill the field directly → the draft is hidden from review (R3-S3)
    bt = tmp_path / "docs/kickoff/inputs/business-targets.yaml"
    bt.write_text(bt.read_text().replace('target: "<NN%>"', "target: 55%"), encoding="utf-8")
    res2 = runner.invoke(panel_app, ["review", "--project", str(tmp_path)])
    assert "no pending drafts" in res2.stdout


def test_review_warns_on_roster_drift(tmp_path):
    _project(tmp_path)
    drifted = Recommendation(
        domain="business-targets",
        value_path="product_funnel.signup_rate",
        recommended_value={"target": "40%", "why": "x"},
        composite_keys=("target", "why"),
        role_id="product-owner",
        origin="panel:product-owner",
        roster_version="sha256:stale-old-version",
    )
    _stage(tmp_path, "sess-1", drifted)
    res = runner.invoke(panel_app, ["review", "--project", str(tmp_path)])
    assert "roster context has changed" in res.stdout


def test_ambiguous_session_errors(tmp_path):
    _project(tmp_path)
    _stage(tmp_path, "sess-1", _signup_rec("sess-1"))
    _stage(tmp_path, "sess-2", _signup_rec("sess-2"))
    res = runner.invoke(panel_app, ["review", "--project", str(tmp_path)])
    assert res.exit_code == 2
    assert "multiple sessions" in res.stdout
