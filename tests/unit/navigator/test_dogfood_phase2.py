"""Dogfood + Phase 2: Lives-before-Verify, prefer_git, APPROVE? → signoff."""

from __future__ import annotations

import json
from pathlib import Path

from startd8.navigator.det_req import parse_fr_lines, split_fr_fields
from startd8.navigator.git_lives import prefer_git_ref
from startd8.navigator.project import nodes_to_wireframe_plan
from startd8.navigator.sources_requirements import nodes_from_requirements
from startd8.wireframe.signoff import format_signoff, load_signoff
from startd8.wireframe_view.compose import compose

REQ01 = Path("docs/design/requirements-visualization/REQ-01-sdk-node-home.md")


def test_lives_inside_verify_prose_is_not_evidence():
    # Dogfood bug: Verify text citing `Lives: code git:…` must not invent evidence.
    rest = (
        "Touches: x. "
        "Verify: fixture REQ with `Lives: code git:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:src/x.py` builds."
    )
    _b, _t, _v, _s, lives, _ann, _ap, _was = split_fr_fields(rest)
    assert lives == []


def test_approve_prompts_parsed():
    rest = "Touches: x. Approve?: does DOES match · is WON'T right?. Verify: ok."
    _b, _t, _v, _s, _lives, _ann, prompts, _was = split_fr_fields(rest)
    assert prompts == ("does DOES match", "is WON'T right?")


def test_was_aliases_parsed_and_projected():
    rest = "Touches: x. Was: old-name · prior-label. Verify: ok."
    _b, _t, _v, _s, _lives, _ann, _ap, was = split_fr_fields(rest)
    assert was == ("old-name", "prior-label")


def test_req01_dogfood_ten_frs_no_false_lives_on_fr6():
    assert REQ01.is_file()
    frs = parse_fr_lines(REQ01.read_text(encoding="utf-8"))
    assert {f["id"] for f in frs} >= {f"FR-{i}" for i in range(1, 11)}
    by = {f["id"]: f for f in frs}
    # FR-6 Verify mentions locators in prose — must not invent a bogus git ref.
    for e in by["FR-6"]["lives"]:
        assert "<40-hex>" not in e.get("ref", "")
    assert by["FR-1"]["lives"]
    assert by["FR-1"]["approve_prompts"]


def test_req01_nodes_compose_approve_prompts_and_html_roundtrip(tmp_path: Path):
    nodes = nodes_from_requirements(REQ01)
    assert len(nodes) >= 10
    assert any(n.lives for n in nodes)
    plan = nodes_to_wireframe_plan(nodes, group_by="category")
    vm = compose(plan)
    # At least one section carries Approve? prompts into the sign-off surface.
    prompted = [s for s in vm["sections"] if s.get("approve_prompts")]
    assert prompted, "expected approve_prompts on a composed section"
    # App-path omit still holds for a classic empty item (regression).
    from startd8.wireframe import ContentCoverageStats, WireframeItem, WireframePlan, WireframeSection

    classic = WireframePlan(
        project_root=".",
        sections=(
            WireframeSection(
                key="entities",
                title="Entities",
                status="planned",
                items=(WireframeItem(label="User", status="planned"),),
            ),
        ),
        input_provenance={},
        merge_warnings=(),
        shape={"entities": 1, "crud_routes": 0, "pages": 0, "views": 0, "ai_passes": 0},
        readiness={},
        status_counts={"planned": 1},
        content_coverage=ContentCoverageStats(),
    )
    assert set(compose(classic)["sections"][0]["items"][0].keys()) == {
        "label",
        "status",
        "detail",
        "paths",
        "mockup",
        "technical",
    }


def test_prefer_git_upgrades_tracked_path():
    # cli.py is tracked — soft path should become git:<sha>:path at HEAD.
    upgraded = prefer_git_ref("src/startd8/cli.py", repo=Path.cwd())
    assert upgraded.startswith("git:") and upgraded.endswith(":src/startd8/cli.py")


def test_signoff_roundtrip_keeps_approve_prompts(tmp_path: Path):
    path = tmp_path / "so.json"
    path.write_text(
        json.dumps(
            {
                "app": "spec",
                "sections": [
                    {
                        "key": "functional-requirements",
                        "title": "FRs",
                        "status": "ok",
                        "note": "",
                        "approve_prompts": ["does the Node field set match NODE-SCHEMA?"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    so = load_signoff(path)
    assert so["sections"][0]["approve_prompts"]
    text = format_signoff(so)
    assert "Approve?" in text
    assert "NODE-SCHEMA" in text
