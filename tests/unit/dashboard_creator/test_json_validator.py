"""Tests for dashboard_creator.json_validator — compiled JSON validation."""

import json


from startd8.dashboard_creator.json_validator import (
    validate_dashboard_json,
)


def _valid_dashboard(**overrides):
    """Build a minimal valid dashboard dict with optional overrides."""
    base = {
        "title": "Test",
        "uid": "cc-startd8-test",
        "panels": [],
        "templating": {"list": []},
        "schemaVersion": 39,
    }
    base.update(overrides)
    return base


class TestValidateDashboardJson:
    def test_valid_json_passes(self):
        data = _valid_dashboard()
        result = validate_dashboard_json(json.dumps(data), "cc-startd8-test")
        assert result.valid is True
        assert result.errors == []
        assert result.dashboard_json["title"] == "Test"

    def test_malformed_json(self):
        result = validate_dashboard_json("not json {{{", "cc-test")
        assert result.valid is False
        assert any("Invalid JSON" in e for e in result.errors)

    def test_missing_required_key_panels(self):
        data = {"title": "Test", "uid": "cc-test", "templating": {}, "schemaVersion": 39}
        result = validate_dashboard_json(json.dumps(data), "cc-test")
        assert result.valid is False
        assert any("panels" in e for e in result.errors)

    def test_missing_required_key_templating(self):
        data = {"title": "Test", "uid": "cc-test", "panels": [], "schemaVersion": 39}
        result = validate_dashboard_json(json.dumps(data), "cc-test")
        assert result.valid is False
        assert any("templating" in e for e in result.errors)

    def test_missing_required_key_schema_version(self):
        data = {"title": "Test", "uid": "cc-test", "panels": [], "templating": {}}
        result = validate_dashboard_json(json.dumps(data), "cc-test")
        assert result.valid is False
        assert any("schemaVersion" in e for e in result.errors)

    def test_uid_mismatch(self):
        data = _valid_dashboard(uid="wrong-uid")
        result = validate_dashboard_json(json.dumps(data), "cc-startd8-test")
        assert result.valid is False
        assert any("UID mismatch" in e for e in result.errors)

    def test_unsupported_schema_version_is_error(self):
        data = _valid_dashboard(schemaVersion=99)
        result = validate_dashboard_json(json.dumps(data), "cc-startd8-test")
        assert result.valid is False  # DC-106 AC3: must be within supported range
        assert any("schemaVersion" in e for e in result.errors)

    def test_panels_not_a_list(self):
        data = _valid_dashboard(panels="not-a-list")
        result = validate_dashboard_json(json.dumps(data), "cc-startd8-test")
        assert result.valid is False
        assert any("list" in e for e in result.errors)

    def test_non_object_root(self):
        result = validate_dashboard_json(json.dumps([1, 2, 3]), "cc-test")
        assert result.valid is False
        assert any("object" in e for e in result.errors)

    def test_supported_schema_versions(self):
        for sv in [36, 37, 38, 39, 40, 41]:
            data = _valid_dashboard(uid="cc-t", schemaVersion=sv)
            result = validate_dashboard_json(json.dumps(data), "cc-t")
            assert result.warnings == [], f"schemaVersion {sv} should be supported"


class TestPanelCountValidation:
    def test_panel_count_matches(self):
        panels = [
            {"type": "stat", "title": "A"},
            {"type": "timeseries", "title": "B"},
        ]
        data = _valid_dashboard(panels=panels)
        result = validate_dashboard_json(json.dumps(data), "cc-startd8-test", expected_panel_count=2)
        assert result.valid is True

    def test_panel_count_excludes_rows(self):
        panels = [
            {"type": "row", "title": "Section"},
            {"type": "stat", "title": "A"},
            {"type": "timeseries", "title": "B"},
        ]
        data = _valid_dashboard(panels=panels)
        result = validate_dashboard_json(json.dumps(data), "cc-startd8-test", expected_panel_count=2)
        assert result.valid is True

    def test_panel_count_mismatch(self):
        panels = [{"type": "stat", "title": "A"}]
        data = _valid_dashboard(panels=panels)
        result = validate_dashboard_json(json.dumps(data), "cc-startd8-test", expected_panel_count=3)
        assert result.valid is False
        assert any("Panel count mismatch" in e for e in result.errors)
        assert any("expected 3" in e and "got 1" in e for e in result.errors)

    def test_panel_count_none_skips_check(self):
        data = _valid_dashboard(panels=[{"type": "stat", "title": "A"}])
        result = validate_dashboard_json(json.dumps(data), "cc-startd8-test", expected_panel_count=None)
        assert result.valid is True

    def test_panel_count_with_only_rows(self):
        panels = [
            {"type": "row", "title": "R1"},
            {"type": "row", "title": "R2"},
        ]
        data = _valid_dashboard(panels=panels)
        result = validate_dashboard_json(json.dumps(data), "cc-startd8-test", expected_panel_count=0)
        assert result.valid is True
