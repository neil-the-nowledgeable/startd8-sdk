"""Tests for dashboard_creator.mixin_update — DC-204."""


from startd8.dashboard_creator.mixin_update import (
    derive_mixin_entry,
    update_mixin_imports,
)


# ---------------------------------------------------------------------------
# derive_mixin_entry
# ---------------------------------------------------------------------------


class TestDeriveMixinEntry:
    def test_strips_cc_startd8_prefix(self):
        json_fn, libsonnet_path = derive_mixin_entry("cc-startd8-overview")
        assert json_fn == "cc-startd8-overview.json"
        assert libsonnet_path == "dashboards/overview.libsonnet"

    def test_strips_cc_prefix(self):
        json_fn, libsonnet_path = derive_mixin_entry("cc-custom-my-dash")
        assert json_fn == "cc-custom-my-dash.json"
        assert libsonnet_path == "dashboards/custom_my_dash.libsonnet"

    def test_hyphens_converted_to_underscores(self):
        _, libsonnet_path = derive_mixin_entry("cc-startd8-cost-per-request")
        assert libsonnet_path == "dashboards/cost_per_request.libsonnet"


# ---------------------------------------------------------------------------
# update_mixin_imports
# ---------------------------------------------------------------------------


class TestUpdateMixinImports:
    def _write_mixin(self, tmp_path, content):
        mixin = tmp_path / "mixin.libsonnet"
        mixin.write_text(content)
        return mixin

    def test_adds_entry_to_grafana_dashboards_block(self, tmp_path):
        mixin = self._write_mixin(tmp_path, """\
{
  grafanaDashboards+:: {
    'existing.json': (import 'dashboards/existing.libsonnet'),
  },
}
""")
        result = update_mixin_imports(
            mixin, "cc-startd8-new.json", "dashboards/new.libsonnet"
        )
        assert result is True
        content = mixin.read_text()
        assert "'cc-startd8-new.json': (import 'dashboards/new.libsonnet')," in content

    def test_duplicate_entry_not_added(self, tmp_path):
        mixin = self._write_mixin(tmp_path, """\
{
  grafanaDashboards+:: {
    'cc-startd8-overview.json': (import 'dashboards/overview.libsonnet'),
  },
}
""")
        result = update_mixin_imports(
            mixin, "cc-startd8-overview.json", "dashboards/overview.libsonnet"
        )
        assert result is False

    def test_idempotent_double_call(self, tmp_path):
        mixin = self._write_mixin(tmp_path, """\
{
  grafanaDashboards+:: {
  },
}
""")
        update_mixin_imports(mixin, "new.json", "dashboards/new.libsonnet")
        content_after_first = mixin.read_text()
        update_mixin_imports(mixin, "new.json", "dashboards/new.libsonnet")
        content_after_second = mixin.read_text()
        assert content_after_first == content_after_second

    def test_missing_mixin_returns_false(self, tmp_path):
        path = tmp_path / "nonexistent.libsonnet"
        result = update_mixin_imports(path, "x.json", "dashboards/x.libsonnet")
        assert result is False

    def test_no_grafana_dashboards_block_returns_false(self, tmp_path):
        mixin = self._write_mixin(tmp_path, "{ someOtherBlock:: {} }")
        result = update_mixin_imports(mixin, "x.json", "dashboards/x.libsonnet")
        assert result is False
