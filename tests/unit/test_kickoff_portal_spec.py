"""Unit tests for the kickoff portal spec builder (docs/design/kickoff-portal/)."""
from __future__ import annotations

import pytest

from startd8.kickoff_experience.portal_spec import build_kickoff_portal_spec
from startd8.kickoff_experience.state import FieldState, KickoffState, SourceInventory

pytestmark = pytest.mark.unit


def _fs(manifest: str, path: str, attention: str, value: str = "v", status: str = "extracted") -> FieldState:
    return FieldState(
        manifest=manifest,
        value_path=path,
        status=status,
        attention=attention,
        ambiguity="none",
        value=value,
    )


def _state(*fields: FieldState, grammar: str = "authoring-contract-v0.4") -> KickoffState:
    return KickoffState(
        fields=tuple(fields),
        inventory=SourceInventory((), (), (), {}),
        grammar_version=grammar,
        contract_diff=(),
    )


def _titles(spec: dict) -> list[str]:
    return [p["title"] for p in spec["panels"]]


@pytest.fixture
def demo_state() -> KickoffState:
    return _state(
        _fs("business-targets.yaml", "/product_funnel/on_time_rate", "ok", "95%"),
        _fs("business-targets.yaml", "/monetization/mode_now", "blocked", None, status="not_extracted"),
        _fs("observability.yaml", "/owners/0/team", "ok", "household-core"),
        _fs("conventions.yaml", "/stack/framework", "ok", "fastapi"),
        _fs("build-preferences.yaml", "/budgets/llm_monthly", "review", "$25", status="defaulted"),
        _fs("app.yaml", "/app/port", "ok", "8099"),  # non-canonical manifest
    )


def test_spec_shape(demo_state: KickoffState) -> None:
    spec = build_kickoff_portal_spec(demo_state, "demo")
    assert spec["uid"] == "cc-portal-kickoff-demo"
    assert spec["title"] == "demo — Digital Project Workbook"
    assert spec["tags"] == ["portal", "kickoff", "workbook", "demo"]
    # prometheus datasource variable is required by the gauge/stat panels + workflow validation
    assert any(v["type"] == "prometheusDatasource" for v in spec["variables"])
    types = [p["type"] for p in spec["panels"]]
    assert "text" in types and "gauge" in types and "stat" in types


def test_unique_panel_titles(demo_state: KickoffState) -> None:
    # DashboardCreatorWorkflow validation rejects duplicate panel titles — guard it here.
    titles = _titles(build_kickoff_portal_spec(demo_state, "demo"))
    assert len(titles) == len(set(titles)), f"duplicate titles: {titles}"


def test_completeness_and_gaps(demo_state: KickoffState) -> None:
    spec = build_kickoff_portal_spec(demo_state, "demo")
    gauge = next(p for p in spec["panels"] if p["type"] == "gauge")
    # 4 of 6 fields are attention 'ok'
    assert gauge["expr"] == "vector(0.6667)"
    gaps = next(p for p in spec["panels"] if p["title"].startswith("Open Gaps"))
    assert gaps["expr"] == "vector(1)"  # exactly one 'blocked' field


def test_per_domain_chips_only_for_present_domains(demo_state: KickoffState) -> None:
    titles = _titles(build_kickoff_portal_spec(demo_state, "demo"))
    assert "business-targets · confirmed" in titles
    assert "observability · confirmed" in titles
    # 'build-preferences' present (review counts as a field) -> chip exists
    assert "build-preferences · confirmed" in titles


def test_cites_explain_content(demo_state: KickoffState) -> None:
    # single-source vocabulary: the business-targets section carries the canonical label + question
    spec = build_kickoff_portal_spec(demo_state, "demo")
    bt = next(p for p in spec["panels"] if "business-targets.yaml" in p["title"])
    content = bt["options"]["content"]
    assert "Business targets" in content
    assert "**Who:**" in content
    # gaps sort first: the blocked monetization field precedes the ok funnel field in the table
    assert content.index("/monetization/mode_now") < content.index("/product_funnel/on_time_rate")


def test_gap_field_marked(demo_state: KickoffState) -> None:
    spec = build_kickoff_portal_spec(demo_state, "demo")
    bt = next(p for p in spec["panels"] if "business-targets.yaml" in p["title"])
    assert "🔴" in bt["options"]["content"]  # the blocked field is flagged


def test_deterministic(demo_state: KickoffState) -> None:
    assert build_kickoff_portal_spec(demo_state, "demo") == build_kickoff_portal_spec(demo_state, "demo")


def test_uid_slugifies_project_name(demo_state: KickoffState) -> None:
    spec = build_kickoff_portal_spec(demo_state, "My Project_Name")
    assert spec["uid"] == "cc-portal-kickoff-my-project-name"


def test_empty_state_still_valid() -> None:
    spec = build_kickoff_portal_spec(_state(), "empty")
    assert spec["uid"] == "cc-portal-kickoff-empty"
    gauge = next(p for p in spec["panels"] if p["type"] == "gauge")
    assert gauge["expr"] == "vector(0.0000)"
    assert len(_titles(spec)) == len(set(_titles(spec)))
