"""Tests for the v2 dynamic Workbook — dynamic-dashboards M6 (FR-8/FR-9)."""

from __future__ import annotations

import copy
import json
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


def _rows(board):
    return board["spec"]["layout"]["spec"]["rows"]


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


def test_distinct_uid_coexists_with_classic():
    # FR: the v2 board uses a distinct -v2 UID so it never clobbers the classic Workbook (R2-F5 coexistence)
    assert workbook_v2_uid("My App") == "cc-portal-kickoff-my-app-v2"


def test_classic_build_kickoff_portal_spec_untouched():
    # R2-F5: M6 is additive — the classic spec builder is not modified by this milestone
    import inspect
    from startd8.kickoff_experience.portal_spec import build_kickoff_portal_spec

    src = inspect.getsource(build_kickoff_portal_spec)
    assert (
        "audience" not in src
    )  # the classic builder on this branch has no audience params (untouched)
