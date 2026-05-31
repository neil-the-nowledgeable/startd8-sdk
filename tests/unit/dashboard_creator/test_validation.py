"""Tests for dashboard_creator.validation — UID enforcement + spec validation."""

import pytest

from startd8.dashboard_creator.config_merge import get_default_config
from startd8.dashboard_creator.models import (
    DashboardSpec,
    GridPos,
    PanelSpec,
    TargetSpec,
    VariableSpec,
)
from startd8.dashboard_creator.validation import (
    enforce_uid,
    generate_uid_from_title,
    layout_grid_warnings,
    validate_row_placement,
    validate_spec,
)
from startd8.exceptions import ValidationError


# ---------------------------------------------------------------------------
# generate_uid_from_title
# ---------------------------------------------------------------------------


class TestGenerateUid:
    def test_basic_title(self):
        assert generate_uid_from_title("My Dashboard") == "cc-startd8-my-dashboard"

    def test_special_characters(self):
        uid = generate_uid_from_title("Agent Performance (v2)")
        assert uid == "cc-startd8-agent-performance-v2"

    def test_underscores(self):
        uid = generate_uid_from_title("cost_tracking_overview")
        assert uid == "cc-startd8-cost-tracking-overview"

    def test_truncates_to_40_chars(self):
        uid = generate_uid_from_title("A Very Long Dashboard Title That Exceeds Forty Characters Easily")
        assert len(uid) <= 40

    def test_custom_pack(self):
        uid = generate_uid_from_title("Overview", pack="myapp")
        assert uid.startswith("cc-myapp-")

    def test_multiple_spaces(self):
        uid = generate_uid_from_title("My   Dashboard")
        assert uid == "cc-startd8-my-dashboard"


# ---------------------------------------------------------------------------
# enforce_uid
# ---------------------------------------------------------------------------


class TestEnforceUid:
    def _spec(self, uid=None, title="Test"):
        return DashboardSpec(
            title=title,
            uid=uid,
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
        )

    def test_auto_generate_when_none(self):
        result = enforce_uid(self._spec(uid=None, title="My Dashboard"))
        assert result.uid == "cc-startd8-my-dashboard"

    def test_conforming_uid_passes(self):
        result = enforce_uid(self._spec(uid="cc-startd8-agent-perf"))
        assert result.uid == "cc-startd8-agent-perf"

    def test_non_conforming_raises(self):
        with pytest.raises(ValidationError, match="does not match"):
            enforce_uid(self._spec(uid="bad-uid-format"))

    def test_suggestion_in_error(self):
        with pytest.raises(ValidationError, match="Suggestion"):
            enforce_uid(self._spec(uid="BAD", title="Test Dashboard"))

    def test_long_uid_truncated(self):
        long_uid = "cc-startd8-" + "a" * 40
        result = enforce_uid(self._spec(uid=long_uid, title="X"))
        assert len(result.uid) <= 40


# ---------------------------------------------------------------------------
# validate_spec
# ---------------------------------------------------------------------------


class TestValidateSpec:
    def _config(self):
        return get_default_config()

    def _valid_spec(self):
        return DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(
                    type="stat",
                    title="Active Sessions",
                    expr="${metrics.activeSessions}",
                )
            ],
            variables=[
                VariableSpec(
                    type="prometheusDatasource",
                    name="datasource",
                    label="Prometheus",
                )
            ],
        )

    def test_valid_spec_no_errors(self):
        errors = validate_spec(self._valid_spec(), self._config())
        assert errors == []

    def test_unresolvable_metric_ref(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(
                    type="stat",
                    title="Bad Metric",
                    expr="${metrics.unknownMetric}",
                )
            ],
        )
        errors = validate_spec(spec, self._config())
        assert any("unknownMetric" in e for e in errors)

    def test_unresolvable_selector_ref(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(
                    type="timeseries",
                    title="Bad Selector",
                    targets=[
                        TargetSpec(expr="rate(up{${selectors.unknownSelector}}[5m])")
                    ],
                )
            ],
        )
        errors = validate_spec(spec, self._config())
        assert any("unknownSelector" in e for e in errors)

    def test_duplicate_panel_titles(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(type="stat", title="Same Title", expr="up"),
                PanelSpec(type="gauge", title="Same Title", expr="up"),
            ],
        )
        errors = validate_spec(spec, self._config())
        assert any("Duplicate panel title" in e for e in errors)

    def test_valid_metric_ref_passes(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(
                    type="stat",
                    title="Sessions",
                    expr="${metrics.activeSessions}",
                )
            ],
        )
        errors = validate_spec(spec, self._config())
        assert errors == []

    def test_valid_selector_ref_passes(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(
                    type="timeseries",
                    title="By Model",
                    targets=[
                        TargetSpec(
                            expr="rate(up{${selectors.serviceName}, ${selectors.model}}[5m])"
                        )
                    ],
                )
            ],
        )
        errors = validate_spec(spec, self._config())
        assert errors == []

    def test_metric_ref_in_variable(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
            variables=[
                VariableSpec(
                    type="modelVariable",
                    name="model",
                    label="Model",
                    metric="${metrics.unknownVarMetric}",
                )
            ],
        )
        errors = validate_spec(spec, self._config())
        assert any("unknownVarMetric" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_row_placement
# ---------------------------------------------------------------------------


class TestValidateRowPlacement:
    def test_no_row_panels_ok(self):
        spec = DashboardSpec(
            title="T",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(type="stat", title="A", expr="up", gridPos=GridPos(h=4, w=6, x=0, y=0)),
            ],
        )
        assert validate_row_placement(spec) == []

    def test_content_below_row_ok(self):
        spec = DashboardSpec(
            title="T",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(
                    type="row",
                    title="Section",
                    gridPos=GridPos(h=1, w=24, x=0, y=0),
                ),
                PanelSpec(
                    type="stat",
                    title="KPI",
                    expr="up",
                    gridPos=GridPos(h=4, w=6, x=0, y=1),
                ),
            ],
        )
        assert validate_row_placement(spec) == []

    def test_content_same_y_as_row_fails(self):
        spec = DashboardSpec(
            title="T",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(
                    type="row",
                    title="Section",
                    gridPos=GridPos(h=1, w=24, x=0, y=0),
                ),
                PanelSpec(
                    type="stat",
                    title="Bad",
                    expr="up",
                    gridPos=GridPos(h=4, w=6, x=0, y=0),
                ),
            ],
        )
        err = validate_row_placement(spec)
        assert len(err) == 1
        assert "Bad" in err[0]
        assert "y >= 1" in err[0]

    def test_row_without_gridpos_fails(self):
        spec = DashboardSpec(
            title="T",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(type="row", title="Section"),
                PanelSpec(type="stat", title="A", expr="up", gridPos=GridPos(h=4, w=6, x=0, y=1)),
            ],
        )
        err = validate_row_placement(spec)
        assert len(err) == 1
        assert "no gridPos" in err[0]


# ---------------------------------------------------------------------------
# layout_grid_warnings
# ---------------------------------------------------------------------------


class TestLayoutGridWarnings:
    def test_all_explicit_no_warning(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(
                    type="stat",
                    title="A",
                    expr="up",
                    gridPos=GridPos(h=4, w=6, x=0, y=1),
                ),
                PanelSpec(
                    type="stat",
                    title="B",
                    expr="up",
                    gridPos=GridPos(h=4, w=6, x=6, y=1),
                ),
            ],
        )
        assert layout_grid_warnings(spec) == []

    def test_all_implicit_no_warning(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(type="stat", title="A", expr="up"),
                PanelSpec(type="stat", title="B", expr="up"),
            ],
        )
        assert layout_grid_warnings(spec) == []

    def test_mixed_emits_warning(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(
                    type="stat",
                    title="With",
                    expr="up",
                    gridPos=GridPos(h=4, w=6, x=0, y=1),
                ),
                PanelSpec(type="stat", title="Without", expr="up"),
            ],
        )
        w = layout_grid_warnings(spec)
        assert len(w) == 1
        assert "mixed explicit and implicit" in w[0].lower()
        assert "With" in w[0]
        assert "Without" in w[0]

    def test_row_panels_ignored(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[
                PanelSpec(type="row", title="R1"),
                PanelSpec(
                    type="stat",
                    title="A",
                    expr="up",
                    gridPos=GridPos(h=4, w=6, x=0, y=1),
                ),
                PanelSpec(type="stat", title="B", expr="up"),
            ],
        )
        w = layout_grid_warnings(spec)
        assert len(w) == 1
        assert "B" in w[0]
