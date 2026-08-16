"""F-2: WireframeItem grounding + compose omit-when-empty + honest-skip need_items."""

from __future__ import annotations

from startd8.navigator.models import Node, NodeEvidence, NodeStatus
from startd8.navigator.project import nodes_to_wireframe_plan
from startd8.wireframe import ContentCoverageStats, EvidenceRef, WireframeItem, WireframePlan, WireframeSection
from startd8.wireframe_view.compose import compose


def _app_plan() -> WireframePlan:
    item = WireframeItem(label="User", status="planned", detail="", paths=())
    sec = WireframeSection(key="entities", title="Entities", status="planned", items=(item,))
    return WireframePlan(
        project_root=".",
        sections=(sec,),
        input_provenance={},
        merge_warnings=(),
        shape={"entities": 1, "crud_routes": 0, "pages": 0, "views": 0, "ai_passes": 0},
        readiness={},
        status_counts={"planned": 1},
        content_coverage=ContentCoverageStats(),
    )


def test_compose_app_path_omits_node_keys():
    vm = compose(_app_plan())
    item = vm["sections"][0]["items"][0]
    assert set(item.keys()) == {"label", "status", "detail", "paths", "mockup", "technical"}


def test_compose_navigator_preserves_typed_lives_and_confidence():
    sha = "a" * 40
    node = Node(
        key="FR-1",
        does="Strong lives",
        status=NodeStatus.BUILT,
        lives=(NodeEvidence(type="code", ref=f"git:{sha}:src/x.py"),),
        confidence=0.9,
        category="frs",
    )
    plan = nodes_to_wireframe_plan([node], group_by="category")
    vm = compose(plan)
    item = vm["sections"][0]["items"][0]
    assert item["lives"][0]["type"] == "code"
    assert item["lives"][0]["ref"].startswith("git:")
    assert item["confidence"] == 0.9
    assert item["key"] == "FR-1"


def test_honest_skip_excluded_from_need_items():
    item = WireframeItem(
        label="FR-KIT — deferred",
        status="not_defined",
        detail="",
        paths=(),
        route_state="declared_unimplemented",
        ships_when="P7",
    )
    app_gap = WireframeItem(label="Missing", status="not_defined", detail="", paths=())
    sec = WireframeSection(
        key="open",
        title="Open",
        status="not_defined",
        items=(item, app_gap),
    )
    plan = WireframePlan(
        project_root=".",
        sections=(sec,),
        input_provenance={},
        merge_warnings=(),
        shape={"entities": 0, "crud_routes": 0, "pages": 0, "views": 0, "ai_passes": 0},
        readiness={},
        status_counts={"not_defined": 2},
        content_coverage=ContentCoverageStats(),
    )
    vm = compose(plan)
    need = vm["sections"][0]["need_items"]
    assert "Missing" in need
    assert "FR-KIT — deferred" not in need


def test_app_need_items_unchanged_without_route_state():
    item = WireframeItem(label="Gap", status="not_defined", detail="", paths=())
    sec = WireframeSection(key="x", title="X", status="not_defined", items=(item,))
    plan = WireframePlan(
        project_root=".",
        sections=(sec,),
        input_provenance={},
        merge_warnings=(),
        shape={"entities": 0, "crud_routes": 0, "pages": 0, "views": 0, "ai_passes": 0},
        readiness={},
        status_counts={"not_defined": 1},
        content_coverage=ContentCoverageStats(),
    )
    assert compose(plan)["sections"][0]["need_items"] == ["Gap"]
