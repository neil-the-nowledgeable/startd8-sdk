"""Offline comparison of the pilot artifact with sanitized live Dash0 export evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_FIXTURES = Path(__file__).with_name("fixtures")
_PILOT = _REPO / "docs/design/dashboard-vendor-neutrality/pilot"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _panels(dashboard):
    return dashboard["spec"]["panels"].values()


def _queries(dashboard):
    for panel in _panels(dashboard):
        yield from panel["spec"].get("queries", [])


def _datasources(dashboard):
    for query in _queries(dashboard):
        plugin_spec = query["spec"]["plugin"]["spec"]
        if "datasource" in plugin_spec:
            yield plugin_spec["datasource"]


def _units(dashboard):
    for panel in _panels(dashboard):
        plugin_spec = panel["spec"]["plugin"]["spec"]
        unit = (plugin_spec.get("yAxis", {}).get("format", {}).get("unit"))
        if unit is None:
            unit = plugin_spec.get("format", {}).get("unit")
        if unit is not None:
            yield unit


def test_pilot_core_matches_live_dash0_export_profile_and_deltas_stay_explicit():
    profile = _load(_FIXTURES / "dash0_live_export_profile.golden.json")
    artifact = _load(_PILOT / "obs-domain-dash0-pilot-v2.perses.json")

    assert profile["resourceCount"] == 14
    assert profile["resourceEnvelope"]["apiVersions"] == ["perses.dev/v1alpha1"]
    assert profile["resourceEnvelope"]["kinds"] == ["PersesDashboard"]
    assert profile["resourceEnvelope"]["resourcesWithManagedId"] == 14
    assert profile["resourceEnvelope"]["labelKeys"] == [
        "dash0.com/dataset",
        "dash0.com/id",
    ]
    assert profile["spec"]["resourcesWithDatasourceObject"] == 0
    assert profile["spec"]["variablesTypes"] == ["array"]

    observed_panel_plugins = set(profile["spec"]["panelPluginKinds"])
    artifact_panel_plugins = {
        panel["spec"]["plugin"]["kind"] for panel in _panels(artifact)
    }
    assert artifact_panel_plugins <= observed_panel_plugins

    observed_query_kinds = set(profile["spec"]["queryKinds"])
    observed_query_plugins = set(profile["spec"]["queryPluginKinds"])
    assert {query["kind"] for query in _queries(artifact)} <= observed_query_kinds
    assert {
        query["spec"]["plugin"]["kind"] for query in _queries(artifact)
    } <= observed_query_plugins

    panel_keys = set(artifact["spec"]["panels"])
    layout_refs = {
        item["content"]["$ref"].removeprefix("#/spec/panels/")
        for layout in artifact["spec"]["layouts"]
        for item in layout["spec"]["items"]
    }
    assert layout_refs == panel_keys

    known_deltas = {
        "resourceEnvelope": {
            "artifact": (artifact.get("apiVersion"), artifact["kind"]),
            "dash0Export": (
                profile["resourceEnvelope"]["apiVersions"][0],
                profile["resourceEnvelope"]["kinds"][0],
            ),
        },
        "metadataLabels": "labels" not in artifact["metadata"],
        "variables": "variables" not in artifact["spec"],
        "datasourceObjects": list(_datasources(artifact)),
        "artifactUnitsNotObservedInExports": sorted(
            set(_units(artifact)) - set(profile["spec"]["units"])
        ),
    }
    assert known_deltas == {
        "resourceEnvelope": {
            "artifact": (None, "Dashboard"),
            "dash0Export": ("perses.dev/v1alpha1", "PersesDashboard"),
        },
        "metadataLabels": True,
        "variables": True,
        "datasourceObjects": [
            {"kind": "PrometheusDatasource", "name": "default"},
            {"kind": "PrometheusDatasource", "name": "default"},
            {"kind": "PrometheusDatasource", "name": "default"},
        ],
        "artifactUnitsNotObservedInExports": ["decimal", "seconds"],
    }


def test_sanitized_profile_contains_no_dash0_managed_identifier_values():
    profile_text = (
        _FIXTURES / "dash0_live_export_profile.golden.json"
    ).read_text(encoding="utf-8")
    assert re.search(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        profile_text,
        re.IGNORECASE,
    ) is None
    assert "dash0.com/id" in profile_text
