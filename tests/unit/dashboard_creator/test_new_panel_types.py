"""Compiled-JSON checks for the Phase 5 panel types (geomap, canvas, heatmap,
state-timeline, xychart, candlestick). Compile-gated: skip when the Jsonnet
toolchain / vendored mixin is unavailable (NFR-AES-5)."""

import asyncio
import inspect
import json
from pathlib import Path

import pytest

from startd8.dashboard_creator import DashboardCreatorWorkflow

_DS = {"type": "prometheusDatasource", "name": "datasource", "label": "DS"}


def _compile(panels, tmp_path):
    spec = {"title": "p5", "uid": "cc-test-p5x", "variables": [_DS], "panels": panels}
    result = DashboardCreatorWorkflow().run({"spec": spec, "output_dir": str(tmp_path)})
    if inspect.isawaitable(result):
        result = asyncio.get_event_loop().run_until_complete(result)
    if not result.success:
        err = (getattr(result, "error", "") or "").lower()
        if any(t in err for t in ("jsonnet", "vendor", "mixin", "jb install", "toolchain")):
            pytest.skip(f"toolchain unavailable: {result.error}")
        pytest.fail(f"workflow failed: {result.error}")
    return {p["title"]: p for p in json.load(open(Path(result.output["json_path"])))["panels"]}


class TestNewPanelTypes:
    def test_all_six_compile_with_correct_type(self, tmp_path):
        types = ["geomap", "canvas", "heatmap", "state-timeline", "xychart", "candlestick"]
        P = _compile([{"type": t, "title": t, "targets": [{"expr": "up"}]} for t in types], tmp_path)
        for t in types:
            assert P[t]["type"] == t

    def test_geomap_has_markers_layer(self, tmp_path):
        P = _compile([{"type": "geomap", "title": "geomap", "targets": [{"expr": "up"}]}], tmp_path)
        layers = P["geomap"]["options"]["layers"]
        assert layers and layers[0]["type"] == "markers"

    def test_candlestick_mode(self, tmp_path):
        P = _compile([{"type": "candlestick", "title": "candlestick", "targets": [{"expr": "up"}]}], tmp_path)
        assert P["candlestick"]["options"]["mode"] == "candles+volume"

    def test_state_timeline_type_string(self, tmp_path):
        # The hyphenated type compiles via the stateTimeline constructor.
        P = _compile([{"type": "state-timeline", "title": "state-timeline", "targets": [{"expr": "up"}]}], tmp_path)
        assert P["state-timeline"]["type"] == "state-timeline"
