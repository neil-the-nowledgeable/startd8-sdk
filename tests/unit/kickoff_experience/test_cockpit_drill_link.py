"""H1 — cockpit readiness rows drill to the navig8r node via the declared ``surface_links`` binding.

Covers REQ-cockpit-surface-links-adopter FR-1 (web anchor), FR-2 (Grafana v2 markdown link) and FR-5
(empty-default: an unbound definition renders the pre-H1 row). FR-3 (terminal) is deferred — the
terminal cockpit has no per-field rows to annotate.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.kickoff_experience.manifest import default_config
from startd8.kickoff_experience.portal_spec import drill_href
from startd8.kickoff_experience.portal_spec_v2 import _field_table, build_workbook_v2
from startd8.kickoff_experience.ranking import next_action
from startd8.kickoff_experience.state import FieldState, KickoffState, SourceInventory

# `web.py` imports fastapi lazily (inside `build_kickoff_app`), so the pure renderer is testable
# without the optional web extra installed.
from startd8.kickoff_experience.web import _render_overview, load_state

pytestmark = pytest.mark.unit

#: An unbound definition: the drill binding is absent entirely (FR-5a).
_NO_LINKS: dict = {}
#: A declared-but-hrefless drill binding — a rollup-shaped link (FR-5b).
_HREFLESS = {"drill": {"from_surface": "cockpit", "to_surface": "navig8r", "href": ""}}

CONVENTIONS = textwrap.dedent(
    """\
    domain: conventions
    provenance_default: authored
    language: python
    stack:
      framework: fastapi
    data_model:
      money: cents
    """
)


def _fs(manifest: str, path: str, attention: str, value: str = "v") -> FieldState:
    return FieldState(
        manifest=manifest,
        value_path=path,
        status="extracted",
        attention=attention,
        ambiguity="none",
        value=value,
    )


def _state() -> KickoffState:
    return KickoffState(
        fields=(
            _fs("business-targets.yaml", "/kpi", "ok", "95%"),
            _fs("conventions.yaml", "/lang", "ok", "python"),
        ),
        inventory=SourceInventory((), (), (), {}),
        grammar_version="g",
        contract_diff=(),
    )


# --- the shared seam (FR-1c) --------------------------------------------------------------------


def test_drill_href_resolves_the_declared_template_for_a_key():
    # The base definition declares `href: "#{key}"`; the key is the field's value_path, used as-is.
    assert drill_href("/kpi") == "#/kpi"


@pytest.mark.parametrize("links", [_NO_LINKS, _HREFLESS])
def test_drill_href_is_empty_for_an_unbound_definition(links):
    assert drill_href("/kpi", links) == ""


def test_drill_href_delegates_to_resolve_surface_link_href(monkeypatch):
    """FR-1c — the href comes from the shipped resolver, not a hand-built anchor."""
    from startd8.navigator import view_definition

    calls = []
    real = view_definition.resolve_surface_link_href

    def spy(link, key):
        calls.append((dict(link or {}), key))
        return real(link, key)

    monkeypatch.setattr(view_definition, "resolve_surface_link_href", spy)
    assert drill_href("/kpi") == "#/kpi"
    assert len(calls) == 1
    link, key = calls[0]
    assert key == "/kpi"
    assert link["relation"] == "drill" and link["href"] == "#{key}"


def test_no_renderer_hand_builds_a_key_anchor():
    """FR-1c (structural) — neither renderer may construct the ``#<key>`` URL itself."""
    src_dir = Path(__file__).resolve().parents[3] / "src/startd8/kickoff_experience"
    for name in ("web.py", "portal_spec_v2.py"):
        text = (src_dir / name).read_text(encoding="utf-8")
        assert 'f"#{' not in text and "f'#{" not in text, f"{name} hand-builds a #<key> href"
        assert '"#" +' not in text and "'#' +" not in text, f"{name} hand-builds a #<key> href"


# --- FR-1 / FR-5: the web overview -------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Path:
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "conventions.yaml").write_text(CONVENTIONS, encoding="utf-8")
    return tmp_path


def _web_state(project: Path) -> KickoffState:
    state = load_state(project)
    assert state.fields, "fixture must produce at least one field row to annotate"
    return state


def _overview(project: Path, **kwargs) -> str:
    state = _web_state(project)
    return _render_overview(
        state, None, next_action(state, None), default_config(), "", None, **kwargs
    )


def test_web_overview_field_rows_carry_a_drill_link(project: Path):
    html = _overview(project)
    for field in _web_state(project).fields:
        assert f"<a href='#{field.value_path}' class='drill-link'>" in html
        assert f"<code>{field.value_path}</code></a>" in html


@pytest.mark.parametrize("links", [_NO_LINKS, _HREFLESS])
def test_web_overview_has_no_drill_link_for_an_unbound_definition(project: Path, links):
    html = _overview(project, surface_links=links)
    assert "drill-link" not in html
    assert "<a href='#" not in html
    for field in _web_state(project).fields:
        # The pre-H1 cell, byte-identical: a bare <code> in its own <td>.
        assert f"<td><code>{field.value_path}</code></td>" in html


# --- FR-2 / FR-5: the Grafana v2 board ---------------------------------------------------------


def test_v2_field_table_carries_a_markdown_drill_link():
    table = _field_table(list(_state().fields), {})
    assert "| `/kpi` [→ navig8r](#/kpi) |" in table
    assert "| `/lang` [→ navig8r](#/lang) |" in table


@pytest.mark.parametrize("links", [_NO_LINKS, _HREFLESS])
def test_v2_field_table_is_unchanged_for_an_unbound_definition(links):
    table = _field_table(list(_state().fields), {}, surface_links=links)
    assert "navig8r" not in table
    assert "| `/kpi` |" in table


def test_v2_board_json_carries_the_markdown_drill_link():
    board = build_workbook_v2(_state(), "demo")
    contents = [
        e["spec"]["vizConfig"]["spec"]["options"].get("content", "")
        for e in board["spec"]["elements"].values()
        if e["spec"]["vizConfig"]["kind"] == "text"
    ]
    assert any("[→ navig8r](#/kpi)" in c for c in contents)
    assert any("[→ navig8r](#/lang)" in c for c in contents)
