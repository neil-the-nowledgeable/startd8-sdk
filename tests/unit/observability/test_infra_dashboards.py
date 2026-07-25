# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for infra dashboard rendering (container-o11y Step 2c, FR-8)."""

import json

from startd8.observability.infra_dashboards import render_infra_dashboards

# the bundle's sli_rules shape ({record, expr, labels}); one per level incl. container
SLI_RULES = [
    {"record": "cluster_pods_ready_ratio", "expr": "...", "labels": {"level": "cluster", "unit": "ratio", "framing": "availability"}},
    {"record": "node_cpu_saturation", "expr": "...", "labels": {"level": "node", "unit": "ratio", "framing": "USE"}},
    {"record": "node_ready", "expr": "...", "labels": {"level": "node", "unit": "bool", "framing": "USE"}},
    {"record": "pod_ready", "expr": "...", "labels": {"level": "pod", "unit": "bool", "framing": "availability"}},
    {"record": "container_cpu_throttling_ratio", "expr": "...", "labels": {"level": "container", "unit": "ratio", "framing": "USE"}},
    {"record": "apiserver_availability", "expr": "...", "labels": {"level": "control_plane", "unit": "ratio", "framing": "RED"}},
]


def test_one_dashboard_per_level_including_the_container_dashboard():
    dashboards = render_infra_dashboards(SLI_RULES)
    assert set(dashboards) == {"cluster", "node", "pod", "container", "control_plane"}
    # the 4th (container) dashboard the kubernetes-mixin lacks — covered because our SLI intent has it
    assert dashboards["container"]["uid"] == "cc-infra-container"


def test_panels_read_recorded_series_not_raw_expr_closure_consistent():
    node = render_infra_dashboards(SLI_RULES)["node"]
    exprs = {p["targets"][0]["expr"] for p in node["panels"]}
    # panels query the RECORDED series (what the ruler emits), never the raw SLI expr
    assert exprs == {"node_cpu_saturation", "node_ready"}
    assert len(node["panels"]) == 2


def test_fr8_cross_links_both_directions():
    dashboards = render_infra_dashboards(SLI_RULES)
    cluster_links = {l["url"] for l in dashboards["cluster"]["links"]}
    # cluster links down to node/pod/container/control-plane
    assert "/d/cc-infra-node" in cluster_links
    assert "/d/cc-infra-container" in cluster_links
    # and container links back up to cluster (roll-up direction)
    container_links = {l["url"] for l in dashboards["container"]["links"]}
    assert "/d/cc-infra-cluster" in container_links
    # a dashboard never links to itself
    assert "/d/cc-infra-cluster" not in {l["url"] for l in dashboards["cluster"]["links"]}


def test_no_data_sentinel_and_valid_grafana_json():
    for level, dash in render_infra_dashboards(SLI_RULES).items():
        # serializes to JSON (provisionable)
        json.dumps(dash)
        assert dash["schemaVersion"] == 39
        assert dash["tags"] == ["cc-infra", level]
        for panel in dash["panels"]:
            # R3-S7 sentinel present so an empty series is an explicit state
            assert "No data" in panel["fieldConfig"]["defaults"]["noValue"]
            assert panel["datasource"]["type"] == "prometheus"


def test_ratio_unit_maps_to_grafana_percentunit():
    node = render_infra_dashboards(SLI_RULES)["node"]
    cpu = next(p for p in node["panels"] if p["targets"][0]["expr"] == "node_cpu_saturation")
    assert cpu["fieldConfig"]["defaults"]["unit"] == "percentunit"
