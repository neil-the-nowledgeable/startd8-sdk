# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Tests for datasource-UID binding (REQ_DATASOURCE_UID_BINDING FR-3/FR-4/FR-7).

Covers the startd8 half: ServiceHints extraction of the resolved UID map, the
dashboard-spec config_overrides injection, byte-identical back-compat when no UID is
declared, and the end-to-end render (panels bind the real UID).
"""

from __future__ import annotations

import json
import os
import tempfile

import yaml

from startd8.observability.artifact_generator_context import extract_service_hints
from startd8.observability.artifact_generator_generators import generate_dashboard_spec
from startd8.observability.artifact_generator_models import (
    BusinessContext,
    ConventionMetric,
    ServiceHints,
)


def _cm():
    return [ConventionMetric(name="rpc.server.duration", type="histogram", source="convention")]


# ─────────────────────────── extraction (FR-3) ─────────────────────────────


def test_extract_service_hints_reads_datasource_uids():
    metadata = {
        "instrumentation_hints": {
            "checkout": {
                "transport": "grpc",
                "metrics": {"convention_based": []},
                "datasources": {"prometheus": "webstore-metrics", "loki": "webstore-logs"},
            }
        }
    }
    [hints] = extract_service_hints(metadata)
    assert hints.datasource_uids == {"prometheus": "webstore-metrics", "loki": "webstore-logs"}


def test_extract_service_hints_absent_datasources_is_empty():
    metadata = {"instrumentation_hints": {"checkout": {"transport": "grpc", "metrics": {}}}}
    [hints] = extract_service_hints(metadata)
    assert hints.datasource_uids == {}


def test_extract_service_hints_drops_blank_uid_values():
    metadata = {
        "instrumentation_hints": {
            "checkout": {"transport": "grpc", "metrics": {}, "datasources": {"prometheus": "  ", "loki": "ok"}}
        }
    }
    [hints] = extract_service_hints(metadata)
    assert hints.datasource_uids == {"loki": "ok"}


# ──────────────────── config_overrides injection (FR-4/FR-7) ────────────────


def test_dashboard_spec_injects_config_overrides_when_uid_declared():
    svc = ServiceHints(
        service_id="checkout", transport="grpc", convention_metrics=_cm(),
        datasource_uids={"prometheus": "webstore-metrics", "loki": "webstore-logs"},
    )
    spec = yaml.safe_load(generate_dashboard_spec(svc, BusinessContext(project_id="shop")).content)
    bound = spec["config_overrides"]["datasources"]
    assert bound["prometheusBound"] == {"uid": "webstore-metrics", "type": "prometheus"}
    assert bound["lokiBound"] == {"uid": "webstore-logs", "type": "loki"}


def test_dashboard_spec_no_config_overrides_without_uid():
    svc = ServiceHints(service_id="checkout", transport="grpc", convention_metrics=_cm())
    spec = yaml.safe_load(generate_dashboard_spec(svc, BusinessContext(project_id="shop")).content)
    # FR-7: absent binding ⇒ no config_overrides key at all (byte-identical path).
    assert "config_overrides" not in spec


def test_dashboard_spec_byte_identical_when_no_uid():
    """The emitted spec content must not change for the no-UID path."""
    a = generate_dashboard_spec(
        ServiceHints(service_id="checkout", transport="grpc", convention_metrics=_cm()),
        BusinessContext(project_id="shop"),
    ).content
    b = generate_dashboard_spec(
        ServiceHints(service_id="checkout", transport="grpc", convention_metrics=_cm(),
                     datasource_uids={}),
        BusinessContext(project_id="shop"),
    ).content
    assert a == b


# ─────────────────────────── end-to-end render ─────────────────────────────


def _render_panel_datasources(spec_yaml: str):
    from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow

    spec = yaml.safe_load(spec_yaml)
    with tempfile.TemporaryDirectory() as d:
        result = DashboardCreatorWorkflow().run(
            {"spec": spec, "output_dir": d, "enforce_uid": False}
        )
        assert result.success, getattr(result, "error", None)
        for f in os.listdir(d):
            if f.endswith(".json"):
                j = json.loads(open(os.path.join(d, f)).read())
                return [p.get("datasource") for p in j.get("panels", []) if p.get("datasource")]
    return []


def test_render_binds_real_uid(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    with_uid = generate_dashboard_spec(
        ServiceHints(service_id="checkout", transport="grpc", convention_metrics=_cm(),
                     datasource_uids={"prometheus": "webstore-metrics"}),
        BusinessContext(project_id="shop"),
    ).content
    ds = _render_panel_datasources(with_uid)
    assert ds and all(d == {"type": "prometheus", "uid": "webstore-metrics"} for d in ds)


def test_render_default_uses_datasource_variable(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    no_uid = generate_dashboard_spec(
        ServiceHints(service_id="checkout", transport="grpc", convention_metrics=_cm()),
        BusinessContext(project_id="shop"),
    ).content
    ds = _render_panel_datasources(no_uid)
    assert ds and all(d == {"type": "prometheus", "uid": "${datasource}"} for d in ds)
