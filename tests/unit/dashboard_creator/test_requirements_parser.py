"""Tests for the requirements markdown → DashboardSpec parser."""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest
import yaml

from startd8.dashboard_creator.models import (
    DashboardSpec,
    GridPos,
    PanelType,
    ThresholdStep,
    VariableType,
)
from startd8.dashboard_creator.requirements_parser import (
    _extract_description,
    _parse_color_overrides,
    _parse_data_link,
    _parse_field_config,
    _parse_grid,
    _parse_panels,
    _parse_promql,
    _parse_thresholds,
    _parse_transformations,
    _parse_variable_table,
    _parse_variables,
    _split_sections,
    _split_transform_chain,
    _uid_transform,
    parse_requirements,
    requirements_to_yaml,
)


# ---------------------------------------------------------------------------
# Paths to golden files
# ---------------------------------------------------------------------------
_DESIGN_DIR = Path(
    "/Users/neilyashinsky/Documents/politics/government-observability/"
    "Michigan-budget-dashboard/design"
)
_DASHBOARDS_DIR = Path(
    "/Users/neilyashinsky/Documents/politics/government-observability/"
    "Michigan-budget-dashboard/dashboards"
)

_INTRO_REQ = _DESIGN_DIR / "intro-requirements.md"
_REVENUE_REQ = _DESIGN_DIR / "revenue-control-requirements.md"
_OVERVIEW_REQ = _DESIGN_DIR / "overview-requirements.md"
_INTRO_GOLDEN = _DASHBOARDS_DIR / "michigan-budget-intro.spec.yaml"
_REVENUE_GOLDEN = _DASHBOARDS_DIR / "michigan-revenue-control.spec.yaml"


# ===========================================================================
# Unit tests — leaf parsers
# ===========================================================================


class TestUidTransform:
    def test_gov_prefix(self):
        assert _uid_transform("gov-michigan-budget-intro") == "cc-govbudget-michigan-budget-intro"

    def test_already_cc(self):
        assert _uid_transform("cc-govbudget-michigan-budget-intro") == "cc-govbudget-michigan-budget-intro"

    def test_plain(self):
        assert _uid_transform("my-dashboard") == "cc-govbudget-my-dashboard"


class TestParseGrid:
    def test_standard(self):
        g = _parse_grid("h=5 w=4 x=0 y=1")
        assert g == GridPos(h=5, w=4, x=0, y=1)

    def test_embedded(self):
        g = _parse_grid("- **Grid**: h=12 w=24 x=0 y=30")
        assert g.h == 12
        assert g.w == 24

    def test_invalid(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            _parse_grid("invalid")


class TestParseThresholds:
    def test_single(self):
        steps = _parse_thresholds("blue(null)")
        assert len(steps) == 1
        assert steps[0].color == "blue"
        assert steps[0].value is None

    def test_chain(self):
        steps = _parse_thresholds("red(null)→orange(0.15)→green(0.50)")
        assert len(steps) == 3
        assert steps[0] == ThresholdStep(value=None, color="red")
        assert steps[1] == ThresholdStep(value=0.15, color="orange")
        assert steps[2] == ThresholdStep(value=0.50, color="green")

    def test_chain_with_four(self):
        steps = _parse_thresholds("red(null)→orange(0.15)→yellow(0.25)→green(0.50)")
        assert len(steps) == 4

    def test_arrow_alt(self):
        steps = _parse_thresholds("red(null)->green(0)")
        assert len(steps) == 2


class TestParseFieldConfig:
    def test_basic(self):
        result = _parse_field_config("unit=currencyUSD, decimals=0, threshold=blue(null)")
        assert result["unit"] == "currencyUSD"
        assert result["fieldConfig"]["defaults"]["decimals"] == 0
        assert len(result["thresholds"]) == 1
        assert result["thresholds"][0].color == "blue"

    def test_with_min_max(self):
        result = _parse_field_config("unit=percentunit, decimals=1, min=0, max=1, thresholds: red(null)→orange(0.15)→green(0.50)")
        assert result["unit"] == "percentunit"
        assert result["fieldConfig"]["defaults"]["min"] == 0.0
        assert result["fieldConfig"]["defaults"]["max"] == 1.0
        assert len(result["thresholds"]) == 3

    def test_horizontal_and_bar_width(self):
        result = _parse_field_config("unit=currencyUSD, decimals=0, horizontal, palette-classic, barWidth=0.7")
        assert result["options"]["orientation"] == "horizontal"
        assert result["options"]["barWidth"] == 0.7

    def test_fixed_color(self):
        result = _parse_field_config("unit=currencyUSD, decimals=0, horizontal, color=blue, barWidth=0.7")
        assert result["fieldConfig"]["defaults"]["color"] == {"mode": "fixed", "fixedColor": "blue"}

    def test_unit_none(self):
        result = _parse_field_config("unit=none, decimals=0, threshold=blue(null)")
        assert result["unit"] == ""

    def test_graph_mode(self):
        result = _parse_field_config("unit=currencyUSD, decimals=0, threshold=red(null), graphMode=none")
        assert result["options"]["graphMode"] == "none"


class TestParsePromQL:
    def test_single_target(self):
        block = '- **PromQL**: `sum(last_over_time(gov_expenditure_amount{level="state"}[3000d]))`'
        expr, targets = _parse_promql(block)
        assert expr == 'sum(last_over_time(gov_expenditure_amount{level="state"}[3000d]))'
        assert targets is None

    def test_multi_target(self):
        block = textwrap.dedent("""\
            - **PromQL** (2 targets):
              - **A**: `sum by (department_display) (last_over_time(gov_expenditure_amount{fiscal_year="2027"}[3000d]))` → FY2027 Proposed
              - **B**: `sum by (department_display) (last_over_time(gov_expenditure_amount{fiscal_year="2026"}[3000d]))` → FY2026 Enacted
        """)
        expr, targets = _parse_promql(block)
        assert expr is None
        assert len(targets) == 2
        assert targets[0]["refId"] == "A"
        assert targets[1]["refId"] == "B"
        assert targets[0]["legendFormat"] == "FY2027 Proposed"

    def test_no_promql(self):
        block = "- **Type**: text\n- **Content**: Hello"
        expr, targets = _parse_promql(block)
        assert expr is None
        assert targets is None


class TestParseTransformations:
    def test_sort_by(self):
        transforms = _parse_transformations("sortBy (Value, desc)")
        assert len(transforms) == 1
        assert transforms[0].id == "sortBy"
        assert transforms[0].options == {"sort": [{"field": "Value", "desc": True}]}

    def test_none(self):
        transforms = _parse_transformations("None")
        assert len(transforms) == 0

    def test_chained(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            transforms = _parse_transformations(
                "joinByField (department_display, outer) → organize (exclude Time) → sortBy (GF/GP, desc)"
            )
        assert len(transforms) == 3
        assert transforms[0].id == "joinByField"
        assert transforms[2].id == "sortBy"
        assert transforms[2].options["sort"][0]["field"] == "GF/GP"


class TestSplitTransformChain:
    def test_simple_chain(self):
        parts = _split_transform_chain("sortBy (Value, desc)")
        assert parts == ["sortBy (Value, desc)"]

    def test_nested_arrows(self):
        parts = _split_transform_chain(
            "organize (rename Value #A→FY2027) → sortBy (Value, desc)"
        )
        assert len(parts) == 2
        assert "FY2027" in parts[0]
        assert "sortBy" in parts[1]


class TestParseDataLink:
    def test_standard(self):
        dl = _parse_data_link(
            "Click → `gov-michigan-dept-detail` with "
            "var-department=${__field.labels.department}, includeVars: true, keepTime: true"
        )
        assert dl is not None
        assert dl.title == "View Department Detail"
        assert "/d/gov-michigan-dept-detail" in dl.url
        assert "var-department=${__field.labels.department}" in dl.url
        assert "${__url_time_range}" in dl.url

    def test_no_match(self):
        dl = _parse_data_link("no data link here")
        assert dl is None


class TestParseColorOverrides:
    def test_standard(self):
        block = textwrap.dedent("""\
            - **Color overrides**:
              - General Fund/General Purpose → green
              - Federal → blue
              - State Restricted → orange
        """)
        overrides = _parse_color_overrides(block)
        assert len(overrides) == 3
        assert overrides[0]["matcher"]["options"] == "General Fund/General Purpose"
        assert overrides[0]["properties"][0]["value"]["fixedColor"] == "green"
        assert overrides[2]["matcher"]["options"] == "State Restricted"

    def test_no_overrides(self):
        overrides = _parse_color_overrides("- **Type**: stat\n- **Grid**: h=5")
        assert len(overrides) == 0


class TestSplitSections:
    def test_basic(self):
        text = textwrap.dedent("""\
            # Title
            **Dashboard UID**: `my-uid`

            ---

            ## 1. Mission

            Content here.

            ## 2. Questions

            More content.

            ## 3. Concepts

            Last section.
        """)
        header, sections = _split_sections(text)
        assert "my-uid" in header
        assert 1 in sections
        assert 2 in sections
        assert 3 in sections
        assert "Mission" in sections[1]
        assert "Questions" in sections[2]


class TestParseVariableTable:
    def test_basic_custom(self):
        block = textwrap.dedent("""\
            ### `fiscal_year`

            | Property | Value |
            |----------|-------|
            | **name** | `fiscal_year` |
            | **label** | `Fiscal Year` |
            | **type** | `custom` |
            | **query** | `2027,2026` |
            | **default** | `2027` |
            | **includeAll** | `false` |
            | **multi** | `false` |
            | **hide** | `0` |
        """)
        v = _parse_variable_table(block, "fiscal_year")
        assert v.name == "fiscal_year"
        assert v.label == "Fiscal Year"
        assert v.type == VariableType.CUSTOM
        assert v.query == "2027,2026"
        assert v.default == "2027"
        assert v.includeAll is False
        assert v.multi is False

    def test_with_all_value(self):
        block = textwrap.dedent("""\
            ### `budget_status`

            | Property | Value |
            |----------|-------|
            | **name** | `budget_status` |
            | **label** | `Budget Status` |
            | **type** | `custom` |
            | **query** | `proposed,enacted` |
            | **default** | `All` (`$__all`) |
            | **allValue** | `.*` |
            | **includeAll** | `true` |
            | **multi** | `true` |
            | **hide** | `0` |
        """)
        v = _parse_variable_table(block, "budget_status")
        assert v.allValue == ".*"
        assert v.includeAll is True
        assert v.multi is True
        assert v.default == "All"


# ===========================================================================
# Integration tests — golden file comparison
# ===========================================================================


def _load_golden(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


@pytest.mark.skipif(
    not _INTRO_REQ.exists(), reason="Requirements file not found"
)
class TestIntroGoldenFile:
    """Verify intro-requirements.md parses to match the golden YAML."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return parse_requirements(_INTRO_REQ)

    @pytest.fixture(scope="class")
    def golden(self):
        return _load_golden(_INTRO_GOLDEN)

    def test_title(self, parsed, golden):
        assert parsed.title == golden["title"]

    def test_uid(self, parsed, golden):
        assert parsed.uid == golden["uid"]

    def test_panel_count(self, parsed, golden):
        assert len(parsed.panels) == len(golden["panels"])

    def test_variable_count(self, parsed, golden):
        assert len(parsed.variables) == len(golden["variables"])

    def test_link_count(self, parsed, golden):
        assert len(parsed.links) == len(golden["links"])

    def test_tags(self, parsed):
        assert "government" in parsed.tags
        assert "budget" in parsed.tags
        assert "michigan" in parsed.tags

    def test_panel_types(self, parsed, golden):
        for i, (p, g) in enumerate(zip(parsed.panels, golden["panels"])):
            assert p.type.value == g["type"], f"Panel {i}: {p.type.value} != {g['type']}"

    def test_panel_grid_positions(self, parsed, golden):
        for i, (p, g) in enumerate(zip(parsed.panels, golden["panels"])):
            if p.gridPos and "gridPos" in g:
                assert p.gridPos.h == g["gridPos"]["h"], f"Panel {i} h"
                assert p.gridPos.w == g["gridPos"]["w"], f"Panel {i} w"
                assert p.gridPos.x == g["gridPos"]["x"], f"Panel {i} x"
                assert p.gridPos.y == g["gridPos"]["y"], f"Panel {i} y"

    def test_stat_panels_have_targets(self, parsed):
        stat_panels = [p for p in parsed.panels if p.type == PanelType.STAT]
        for p in stat_panels:
            assert p.targets and len(p.targets) > 0, f"Stat '{p.title}' has no targets"
            assert p.targets[0].instant is True, f"Stat '{p.title}' not instant"

    def test_bar_charts_have_format_table(self, parsed):
        bar_panels = [p for p in parsed.panels if p.type == PanelType.BARCHART]
        for p in bar_panels:
            assert p.targets and p.targets[0].format == "table", (
                f"Barchart '{p.title}' missing format=table"
            )

    def test_bar_charts_have_sort_transform(self, parsed):
        bar_panels = [p for p in parsed.panels if p.type == PanelType.BARCHART]
        for p in bar_panels:
            assert any(t.id == "sortBy" for t in p.transformations), (
                f"Barchart '{p.title}' missing sortBy"
            )

    def test_bar_charts_have_data_links(self, parsed):
        bar_panels = [p for p in parsed.panels if p.type == PanelType.BARCHART]
        for p in bar_panels:
            assert len(p.dataLinks) > 0, f"Barchart '{p.title}' missing dataLinks"

    def test_text_panels_have_content(self, parsed):
        text_panels = [p for p in parsed.panels if p.type == PanelType.TEXT]
        for p in text_panels:
            assert "content" in p.options, f"Text '{p.title}' missing content"
            assert len(p.options["content"]) > 0

    def test_variable_types(self, parsed, golden):
        for i, (v, g) in enumerate(zip(parsed.variables, golden["variables"])):
            assert v.type.value == g["type"], f"Var {i}: {v.type.value} != {g['type']}"

    def test_variable_names(self, parsed, golden):
        for i, (v, g) in enumerate(zip(parsed.variables, golden["variables"])):
            assert v.name == g["name"], f"Var {i}: {v.name} != {g['name']}"

    def test_link_titles(self, parsed, golden):
        for i, (l, g) in enumerate(zip(parsed.links, golden["links"])):
            assert l.title == g["title"], f"Link {i}: {l.title} != {g['title']}"

    def test_link_urls(self, parsed, golden):
        for i, (l, g) in enumerate(zip(parsed.links, golden["links"])):
            assert l.url == g["url"], f"Link {i}: {l.url} != {g['url']}"

    def test_piechart_options(self, parsed):
        pie_panels = [p for p in parsed.panels if p.type == PanelType.PIECHART]
        assert len(pie_panels) == 1
        p = pie_panels[0]
        assert p.options.get("pieType") == "donut"
        assert p.options.get("legend", {}).get("displayMode") == "table"

    def test_prometheusdatasource_auto_prepended(self, parsed):
        assert parsed.variables[0].type == VariableType.PROMETHEUS_DATASOURCE
        assert parsed.variables[0].name == "datasource"


@pytest.mark.skipif(
    not _REVENUE_REQ.exists(), reason="Requirements file not found"
)
class TestRevenueControlGoldenFile:
    """Verify revenue-control-requirements.md parses to match the golden YAML."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return parse_requirements(_REVENUE_REQ)

    @pytest.fixture(scope="class")
    def golden(self):
        return _load_golden(_REVENUE_GOLDEN)

    def test_title(self, parsed, golden):
        assert parsed.title == golden["title"]

    def test_uid(self, parsed, golden):
        assert parsed.uid == golden["uid"]

    def test_panel_count(self, parsed, golden):
        assert len(parsed.panels) == len(golden["panels"])

    def test_panel_titles_match(self, parsed, golden):
        for i, (p, g) in enumerate(zip(parsed.panels, golden["panels"])):
            assert p.title == g["title"], f"Panel {i}: {p.title!r} != {g['title']!r}"

    def test_gauge_thresholds(self, parsed, golden):
        gauge_panels = [p for p in parsed.panels if p.type == PanelType.GAUGE]
        assert len(gauge_panels) == 1
        g = gauge_panels[0]
        assert len(g.thresholds) == 4  # red→orange→yellow→green
        assert g.thresholds[0].color == "red"
        assert g.thresholds[0].value is None
        assert g.thresholds[1].value == 0.15
        assert g.thresholds[3].color == "green"

    def test_piechart_color_overrides(self, parsed, golden):
        pie_panels = [p for p in parsed.panels if p.type == PanelType.PIECHART]
        assert len(pie_panels) == 1
        p = pie_panels[0]
        assert len(p.overrides) == 5
        names = [o["matcher"]["options"] for o in p.overrides]
        assert "General Fund/General Purpose" in names
        assert "Federal" in names
        colors = {
            o["matcher"]["options"]: o["properties"][0]["value"]["fixedColor"]
            for o in p.overrides
        }
        assert colors["General Fund/General Purpose"] == "green"
        assert colors["Federal"] == "blue"

    def test_barchart_fixed_colors(self, parsed, golden):
        """Bar charts with color=X should have fixed color in fieldConfig."""
        for i, (p, g) in enumerate(zip(parsed.panels, golden["panels"])):
            if p.type == PanelType.BARCHART:
                p_fc = p.fieldConfig.get("defaults", {}).get("color", {})
                g_fc = g.get("fieldConfig", {}).get("defaults", {}).get("color", {})
                assert p_fc == g_fc, f"Panel {i} ({p.title}) fieldConfig.color mismatch"

    def test_link_count_and_icons(self, parsed, golden):
        assert len(parsed.links) == len(golden["links"])
        for i, (pl, gl) in enumerate(zip(parsed.links, golden["links"])):
            assert pl.icon == gl["icon"], f"Link {i}: icon {pl.icon} != {gl['icon']}"

    def test_data_link_on_gfgp_bar(self, parsed):
        # Panel 11 (GF/GP Allocation by Department) should have a data link
        gfgp_bar = [p for p in parsed.panels if p.title == "GF/GP Allocation by Department"]
        assert len(gfgp_bar) == 1
        assert len(gfgp_bar[0].dataLinks) == 1
        assert "var-department" in gfgp_bar[0].dataLinks[0].url

    def test_variable_values_match(self, parsed, golden):
        """Check variable field-level match against golden."""
        for i, (v, g) in enumerate(zip(parsed.variables, golden["variables"])):
            assert v.type.value == g["type"], f"Var {i} type"
            assert v.name == g["name"], f"Var {i} name"
            if g.get("query"):
                assert v.query == g["query"], f"Var {i} query"


@pytest.mark.skipif(
    not _OVERVIEW_REQ.exists(), reason="Requirements file not found"
)
class TestOverviewParsing:
    """Verify overview-requirements.md (most complex) parses without error."""

    @pytest.fixture(scope="class")
    def parsed(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return parse_requirements(_OVERVIEW_REQ)

    def test_panel_count(self, parsed):
        assert len(parsed.panels) == 32  # 7 rows + 25 content panels, but overview has 26 panels per header

    def test_variable_count(self, parsed):
        assert len(parsed.variables) == 5  # datasource + fiscal_year + budget_status + department + fund_source

    def test_link_count(self, parsed):
        assert len(parsed.links) == 4

    def test_multi_target_panel(self, parsed):
        """Panel 12 (Fund Source Breakdown) should have 6 targets."""
        fund_source_panel = [
            p for p in parsed.panels
            if "Fund Source Breakdown by Department" in p.title
        ]
        assert len(fund_source_panel) == 1
        assert fund_source_panel[0].targets is not None
        assert len(fund_source_panel[0].targets) == 6

    def test_yoy_table_two_targets(self, parsed):
        """Panel 32 (YoY Comparison) should have 2 targets."""
        yoy_panel = [
            p for p in parsed.panels
            if "YoY Comparison" in p.title
        ]
        assert len(yoy_panel) == 1
        assert yoy_panel[0].targets is not None
        assert len(yoy_panel[0].targets) == 2

    def test_four_variables(self, parsed):
        """Overview has 4 custom variables plus datasource."""
        custom_vars = [v for v in parsed.variables if v.type == VariableType.CUSTOM]
        assert len(custom_vars) == 4
        names = {v.name for v in custom_vars}
        assert names == {"fiscal_year", "budget_status", "department", "fund_source"}

    def test_department_variable_query(self, parsed):
        dept_var = [v for v in parsed.variables if v.name == "department"]
        assert len(dept_var) == 1
        # Should have the full department list
        assert "corrections" in dept_var[0].query or "Corrections" in dept_var[0].query

    def test_complex_transforms_preserved(self, parsed):
        """Complex transforms should be stored with _raw descriptions."""
        yoy_panel = [p for p in parsed.panels if "YoY Comparison" in p.title]
        assert len(yoy_panel) == 1
        transforms = yoy_panel[0].transformations
        assert len(transforms) >= 3  # joinByField, organize, calculateField(s), sortBy
        sort_transforms = [t for t in transforms if t.id == "sortBy"]
        assert len(sort_transforms) == 1


# ===========================================================================
# YAML output tests
# ===========================================================================


@pytest.mark.skipif(
    not _INTRO_REQ.exists(), reason="Requirements file not found"
)
class TestYamlOutput:
    def test_yaml_is_valid(self):
        yaml_str = requirements_to_yaml(_INTRO_REQ)
        data = yaml.safe_load(yaml_str)
        assert isinstance(data, dict)
        assert "title" in data
        assert "panels" in data

    def test_yaml_creates_valid_spec(self):
        yaml_str = requirements_to_yaml(_INTRO_REQ)
        data = yaml.safe_load(yaml_str)
        # Should be loadable as DashboardSpec
        spec = DashboardSpec(**data)
        assert len(spec.panels) == 22

    def test_revenue_control_yaml_creates_valid_spec(self):
        yaml_str = requirements_to_yaml(_REVENUE_REQ)
        data = yaml.safe_load(yaml_str)
        spec = DashboardSpec(**data)
        assert len(spec.panels) == 17


# ===========================================================================
# Edge case tests
# ===========================================================================


class TestEdgeCases:
    def test_empty_transform_string(self):
        assert _parse_transformations("") == []

    def test_threshold_single_null(self):
        steps = _parse_thresholds("green(null)")
        assert len(steps) == 1
        assert steps[0].value is None

    def test_field_config_empty_string(self):
        result = _parse_field_config("")
        assert result == {}

    def test_data_link_without_vars(self):
        dl = _parse_data_link("Click → `my-dashboard` with var-x=${value}")
        assert dl is not None
        assert "var-x=${value}" in dl.url

    def test_color_overrides_empty_block(self):
        assert _parse_color_overrides("nothing here") == []

    def test_piechart_field_config(self):
        """pieType=donut and legend settings should parse from field config string."""
        result = _parse_field_config(
            "unit=currencyUSD, decimals=0, palette-classic, pieType=donut, "
            "legend=table+right with value+percent"
        )
        assert result["unit"] == "currencyUSD"

    def test_extract_description_no_match(self):
        assert _extract_description("No dashboard question here") == ""

    def test_parse_variables_auto_prepends_datasource(self):
        section6 = textwrap.dedent("""\
            ## 6. Template Variable Contract

            ### `my_var`

            | Property | Value |
            |----------|-------|
            | **name** | `my_var` |
            | **label** | `My Var` |
            | **type** | `custom` |
            | **query** | `a,b,c` |
            | **hide** | `0` |
        """)
        variables = _parse_variables(section6)
        assert len(variables) == 2
        assert variables[0].type == VariableType.PROMETHEUS_DATASOURCE
        assert variables[0].name == "datasource"
        assert variables[1].name == "my_var"
