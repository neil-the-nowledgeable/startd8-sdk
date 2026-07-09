"""Tests for the v2 dynamic Workbook — dynamic-dashboards M6 (FR-8/FR-9)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from startd8.concierge.audience import KickoffAudience
from startd8.concierge.confirmation import audience_default_provenance
from startd8.dashboard_creator.v2 import v2_json, validate_v2_dashboard
from startd8.kickoff_experience.portal_spec_v2 import build_workbook_v2, workbook_v2_uid
from startd8.kickoff_experience.state import FieldState, KickoffState, SourceInventory

pytestmark = pytest.mark.unit

_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "dashboard_creator/fixtures/v2_workbook.golden.json"
)


def _fs(m, p, a, v="v", s="extracted"):
    return FieldState(
        manifest=m, value_path=p, status=s, attention=a, ambiguity="none", value=v
    )


def _state():
    return KickoffState(
        fields=(
            _fs("business-targets.yaml", "/goal", "blocked", None, "not_extracted"),
            _fs("business-targets.yaml", "/kpi", "ok", "95%"),
            _fs("conventions.yaml", "/lang", "ok", "python"),
        ),
        inventory=SourceInventory((), (), (), {}),
        grammar_version="g",
        contract_diff=(),
    )


_PROV = {
    "/goal": {
        "value": "x",
        "at": "t",
        "mode": "set",
        "provenance": audience_default_provenance("business-targets"),
    }
}


def _tabs(board):
    # M3: the cockpit is a TabsLayout board (Status / Assistant / Proposals).
    return board["spec"]["layout"]["spec"]["tabs"]


def _status_tab(board):
    tab = next(t for t in _tabs(board) if t["spec"]["title"] == "Status")
    return tab


def _rows(board):
    # The Status tab wraps the (unchanged) per-domain rows.
    return _status_tab(board)["spec"]["layout"]["spec"]["rows"]


def _conds(board):
    return [
        r["spec"].get("conditionalRendering", {}).get("spec", {}) for r in _rows(board)
    ]


def test_audience_is_a_fixed_custom_allowlist_defaulting_to_resolved():
    # FR-8 / R1-F8: a `custom` variable, enumerated, current = the resolved audience token
    for aud, tok in [
        (KickoffAudience.BEGINNER, "beginner"),
        (KickoffAudience.ADVANCED, "advanced"),
        (None, "intermediate"),
    ]:
        var = build_workbook_v2(_state(), "demo", audience=aud, provenance=_PROV)[
            "spec"
        ]["variables"][0]
        assert var["kind"] == "CustomVariable"
        assert var["spec"]["query"] == "beginner,intermediate,advanced"
        assert var["spec"]["current"]["value"] == tok


def test_fr9_byte_identical_except_audience_current():
    # FR-9: one deterministic board; identical across audiences EXCEPT the audience variable block
    def _stripped(aud):
        b = copy.deepcopy(
            build_workbook_v2(_state(), "demo", audience=aud, provenance=_PROV)
        )
        b["spec"]["variables"] = "<AUDIENCE_VAR>"
        return v2_json(b)

    assert (
        _stripped(KickoffAudience.BEGINNER)
        == _stripped(KickoffAudience.INTERMEDIATE)
        == _stripped(KickoffAudience.ADVANCED)
    )


def test_disclosure_rules_beginner_intro_and_standard_intro():
    conds = _conds(build_workbook_v2(_state(), "demo", provenance=_PROV))
    # a beginner-only intro (show when audience==beginner)
    assert any(
        c.get("visibility") == "show"
        and any(i["spec"].get("value") == "beginner" for i in c.get("items", []))
        for c in conds
    )
    # a standard intro hidden for beginner
    assert any(
        c.get("visibility") == "hide"
        and any(i["spec"].get("value") == "beginner" for i in c.get("items", []))
        for c in conds
    )


def test_surface_shielded_fields_in_hidden_for_beginner_subsection_with_badge():
    board = build_workbook_v2(_state(), "demo", provenance=_PROV)
    # a "safe defaults" subsection row exists AND is hidden-for-beginner
    sd_rows = [r for r in _rows(board) if "set for you" in r["spec"]["title"]]
    assert (
        sd_rows
        and sd_rows[0]["spec"]["conditionalRendering"]["spec"]["visibility"] == "hide"
    )
    # its panel carries the 🛡️ badge for the shielded /goal field
    sd_panel = next(
        e
        for e in board["spec"]["elements"].values()
        if "safe defaults" in e["spec"]["title"]
    )
    content = sd_panel["spec"]["vizConfig"]["spec"]["options"]["content"]
    assert "🛡️" in content and "/goal" in content
    # the non-shielded /kpi is NOT in the safe-defaults panel; it's in the main domain panel
    assert "/kpi" not in content
    main = next(
        e
        for e in board["spec"]["elements"].values()
        if e["spec"]["title"] == "Business targets"
    )
    assert "/kpi" in main["spec"]["vizConfig"]["spec"]["options"]["content"]


def test_no_shielded_no_subsection_no_badge():
    board = build_workbook_v2(_state(), "demo", provenance={})  # empty ledger
    assert not any("set for you" in r["spec"]["title"] for r in _rows(board))
    assert not any(
        "🛡️" in e["spec"]["vizConfig"]["spec"]["options"]["content"]
        for e in board["spec"]["elements"].values()
    )


def test_validates_and_deterministic_and_golden():
    board = build_workbook_v2(
        _state(), "demo", audience=KickoffAudience.INTERMEDIATE, provenance=_PROV
    )
    assert validate_v2_dashboard(board, expected_uid=workbook_v2_uid("demo")) == []
    assert v2_json(board) == v2_json(
        build_workbook_v2(
            _state(), "demo", audience=KickoffAudience.INTERMEDIATE, provenance=_PROV
        )
    )
    assert v2_json(board) == _GOLDEN.read_text(encoding="utf-8")


_PRE_REFACTOR_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "dashboard_creator/fixtures/v2_workbook_status_content.pre_refactor.golden.json"
)


def test_cockpit_has_three_tabs():
    # FR-5: the v2 board is now a Status / Assistant / Proposals TabsLayout cockpit.
    board = build_workbook_v2(_state(), "demo", provenance=_PROV)
    assert board["spec"]["layout"]["kind"] == "TabsLayout"
    assert [t["spec"]["title"] for t in _tabs(board)] == ["Status", "Assistant", "Proposals"]


def test_status_tab_content_byte_identical_to_pre_refactor_golden():
    # R1-S4: the Status tab's rows + its referenced panels are byte-identical to the pre-refactor board
    # (the committed golden captured BEFORE the TabsLayout refactor). Proves "wrap, don't rewrite".
    import json

    pre = json.loads(_PRE_REFACTOR_GOLDEN.read_text(encoding="utf-8"))
    board = build_workbook_v2(
        _state(), "demo", audience=KickoffAudience.INTERMEDIATE, provenance=_PROV
    )
    # rows unchanged
    assert _rows(board) == pre["spec"]["layout"]["spec"]["rows"]
    # every Status panel (panel-1..panel-N) is byte-identical in content
    status_keys = pre["spec"]["elements"].keys()
    for key in status_keys:
        assert board["spec"]["elements"][key] == pre["spec"]["elements"][key]


def test_assistant_and_proposals_empty_states_without_view():
    board = build_workbook_v2(_state(), "demo", provenance=_PROV)  # no view
    elements = board["spec"]["elements"]
    assistant = next(e for e in elements.values() if e["spec"]["title"] == "Assistant")
    assert "kickoff chat" in assistant["spec"]["vizConfig"]["spec"]["options"]["content"]
    proposals = next(
        e for e in elements.values() if "awaiting confirmation" in e["spec"]["title"]
    )
    assert "No proposals" in proposals["spec"]["vizConfig"]["spec"]["options"]["content"]


def test_assistant_tab_renders_snapshot_and_loki_depth_panel(tmp_path):
    from startd8.kickoff_experience import session_snapshot as ss
    from startd8.kickoff_experience.agentic_view import build_agentic_view

    snap = ss.build_session_snapshot(
        messages=[
            {"role": "user", "content": "how ready?"},
            {"role": "assistant", "content": [{"type": "text", "text": "3 gaps remain"}]},
        ],
        model="m",
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        cost_usd=0.0,
        posture="concierge · propose-only",
        project=str(tmp_path),
        session_id="sid-xyz",
        generated_at="2026-07-09T00:00:00+00:00",
    )
    ss.write_snapshot(tmp_path, snap)
    view = build_agentic_view(tmp_path)
    board = build_workbook_v2(_state(), "demo", provenance=_PROV, view=view)
    elements = board["spec"]["elements"]
    # transcript text panel carries the cost line + disclosure + the turn text
    transcript = next(e for e in elements.values() if "transcript" in e["spec"]["title"])
    content = transcript["spec"]["vizConfig"]["spec"]["options"]["content"]
    assert "3 gaps remain" in content and "not a live agent" in content
    # a Loki logs panel scoped to this session id (FR-6b full depth)
    logs = next(e for e in elements.values() if e["spec"]["vizConfig"]["kind"] == "logs")
    expr = logs["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["expr"]
    assert 'session_id="sid-xyz"' in expr
    assert logs["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["datasource"]["name"] == "loki"


def test_proposals_tab_confirm_command_round_trips(tmp_path):
    # FR-7 / R1-F4: the rendered confirm command parses back to the exact proposal id, with a
    # value_path containing spaces/quotes surviving the escaping.
    import json as _json

    from startd8.kickoff_experience.agentic_view import build_agentic_view, parse_confirm_command
    from startd8.vipp.models import EnvelopedProposal, ProposalEnvelope

    tricky = 'conventions."odd key" with spaces'
    env = ProposalEnvelope(
        project_id="p",
        envelope_seq=1,
        proposals=[EnvelopedProposal(kind="capture", params={"value_path": tricky, "value": "v"}, id="P-42")],
    )
    ip = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text(_json.dumps(env.to_dict()), encoding="utf-8")

    view = build_agentic_view(tmp_path)
    board = build_workbook_v2(_state(), "demo", provenance=_PROV, view=view)
    proposals = next(
        e for e in board["spec"]["elements"].values() if "awaiting confirmation" in e["spec"]["title"]
    )
    content = proposals["spec"]["vizConfig"]["spec"]["options"]["content"]
    assert "P-42" in content
    # recover the confirm command from the row and round-trip it
    parsed = parse_confirm_command(view.proposals[0].confirm_command)
    assert parsed["id"] == "P-42"
    assert parsed["path"] == tricky


def test_distinct_uid_coexists_with_classic():
    # FR: the v2 board uses a distinct -v2 UID so it never clobbers the classic Workbook (R2-F5 coexistence)
    assert workbook_v2_uid("My App") == "cc-portal-kickoff-my-app-v2"


def test_m6_v2_path_is_separate_from_the_classic_builder():
    # R2-F5: M6 is additive — `build_workbook_v2` is a SEPARATE module and neither calls nor mutates the
    # classic `build_kickoff_portal_spec`. (Post-Era-1 the classic builder DOES carry `audience` params —
    # that is Era 1's classic audience port, an independent feature; M6 neither added them nor depends on
    # them. So we verify structural separateness, not the absence of the word "audience".)
    from startd8.kickoff_experience.portal_spec import build_kickoff_portal_spec

    assert build_workbook_v2.__module__ == "startd8.kickoff_experience.portal_spec_v2"
    assert (
        build_kickoff_portal_spec.__module__ == "startd8.kickoff_experience.portal_spec"
    )
    # the v2 builder never *calls* the classic spec builder (bytecode name refs — no docstring false-match)
    assert "build_kickoff_portal_spec" not in build_workbook_v2.__code__.co_names
