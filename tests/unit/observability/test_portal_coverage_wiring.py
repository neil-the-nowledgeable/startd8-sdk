# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""EC-2: the generator threads a coverage payload into build_portal_spec.

Before this wire, _generate_portal_artifact called build_portal_spec WITHOUT coverage, so the
persona coverage section (REQ-TCP-120..124) was unreachable from the canonical generation path.
This asserts the payload now reaches build_portal_spec — spying and short-circuiting before the
DashboardCreatorWorkflow so the test stays a pure unit.
"""

from __future__ import annotations

from startd8.observability.artifact_generator import (
    BusinessContext,
    GenerationReport,
    ServiceHints,
    _generate_portal_artifact,
)


def test_generator_threads_coverage_into_build_portal_spec(monkeypatch, tmp_path):
    captured = {}

    def spy(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("short-circuit before the workflow")

    monkeypatch.setattr(
        "startd8.observability.portal_spec_builder.build_portal_spec", spy
    )

    payload = {"records": [{"service": "web", "presence_status": "bound"}], "summary": {}}
    business = BusinessContext(project_id="p", project_name="P", criticality="critical")
    report = GenerationReport(project_id="p", generated_at="2026-07-24T00:00:00Z",
                              artifacts=[], services_processed=1)

    res = _generate_portal_artifact(
        business, [ServiceHints(service_id="web")], report, {}, tmp_path,
        persona="operator", coverage=payload,
    )

    assert captured.get("coverage") == payload   # the wire EC-2 adds
    assert res is not None and res.status == "error"  # our forced short-circuit
