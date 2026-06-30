"""§2.3 `Panel:` line production (VSP-G1 / lane D9 / spike F3).

A constrained `- Panel: <Name> = <field>, …` line on a detail-compose view → a `panels` entry
surfacing Root-entity fields (rendered when any is set). Flag-don't-guess on unknown fields;
detail-compose only; repeatable; byte-identical when absent; round-trips through parse_views.
"""

from __future__ import annotations

import yaml
import pytest

from startd8.manifest_extraction import extract_manifests
from startd8.manifest_extraction.models import Status
from startd8.view_codegen.manifest import parse_views

pytestmark = pytest.mark.unit

_ENTITIES = """
## Entities

### Widget
A widget.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |
| tier | text | no | |
| story | long text | no | |
"""


def _views(view_block: str) -> dict:
    res = extract_manifests({"k.md": _ENTITIES + "\n## Views\n" + view_block})
    return res


def _panels(res, view_name: str = "demo"):
    data = yaml.safe_load(res.manifests["views.yaml"])
    by_name = {v["name"]: v for v in data["views"]}
    return by_name[view_name].get("panels")


def test_panel_surfaces_resolved_root_fields():
    res = _views(
        "### View: Demo\n- Kind: detail-compose\n- Root: Widget\n"
        "- Panel: Details = name, story\n"
    )
    assert _panels(res) == [
        {"name": "Details", "fields": ["name", "story"], "show_when": "any_set"}
    ]


def test_panel_is_repeatable():
    res = _views(
        "### View: Demo\n- Kind: detail-compose\n- Root: Widget\n"
        "- Panel: A = name\n- Panel: B = tier, story\n"
    )
    panels = _panels(res)
    assert [p["name"] for p in panels] == ["A", "B"]
    assert panels[1]["fields"] == ["tier", "story"]


def test_panel_field_parenthetical_tolerated_and_case_insensitive():
    res = _views(
        "### View: Demo\n- Kind: detail-compose\n- Root: Widget\n"
        "- Panel: Details = NAME (the label), Story\n"
    )
    assert _panels(res)[0]["fields"] == ["name", "story"]  # canonical casing


def test_unknown_field_dropped_and_flagged():
    res = _views(
        "### View: Demo\n- Kind: detail-compose\n- Root: Widget\n"
        "- Panel: Details = name, ghost\n"
    )
    assert _panels(res) == [
        {"name": "Details", "fields": ["name"], "show_when": "any_set"}
    ]
    flags = [r.reason for r in res.by_status(Status.NOT_EXTRACTED)
             if "/panels/" in r.value_path]
    assert any("ghost" in (x or "") and "never a guessed field" in (x or "") for x in flags)


def test_all_unknown_fields_drops_whole_panel():
    res = _views(
        "### View: Demo\n- Kind: detail-compose\n- Root: Widget\n"
        "- Panel: Details = ghost, phantom\n"
    )
    assert _panels(res) is None  # no panels key emitted
    flags = [r.reason for r in res.by_status(Status.NOT_EXTRACTED)
             if "/panels/" in r.value_path]
    assert any("no resolvable Root field" in (x or "") for x in flags)


def test_panel_off_archetype_is_flagged():
    res = _views(
        "### View: Demo\n- Kind: dashboard\n- Root: Widget\n"
        "- Panel: Details = name\n"
    )
    assert _panels(res) is None
    flags = [r.reason for r in res.by_status(Status.NOT_EXTRACTED)
             if "/panels/" in r.value_path]
    assert any("detail-compose-only" in (x or "") for x in flags)


def test_byte_identical_when_no_panel_line():
    """FR-7: a detail-compose with no Panel line emits no `panels` key."""
    res = _views("### View: Demo\n- Kind: detail-compose\n- Root: Widget\n")
    data = yaml.safe_load(res.manifests["views.yaml"])
    assert "panels" not in data["views"][0]


def test_emitted_panels_round_trip_through_parse_views():
    """FR-8: the emitted views.yaml parses cleanly (only resolved fields are emitted)."""
    res = _views(
        "### View: Demo\n- Kind: detail-compose\n- Root: Widget\n"
        "- Panel: Details = name, story, ghost\n"
    )
    specs = parse_views(res.manifests["views.yaml"], known_entities=frozenset({"Widget"}))
    demo = next(s for s in specs if s.name == "demo")
    assert demo.panels[0].name == "Details"
    assert demo.panels[0].fields == ("name", "story")
    assert demo.panels[0].show_when == "any_set"
