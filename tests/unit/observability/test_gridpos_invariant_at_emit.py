# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Class-B invariant-at-emit guard (PROPOSAL_generation_invariant_classes.md): every panel in every
EMITTED dashboard_spec must carry a gridPos — even panels appended by a LATE stage (the AffordanceMap
coverage bind) that runs AFTER Phase-4.5's gridPos repair.

This is an INVARIANT test, not a parity test: it asserts a property of the FINAL artifact regardless
of how many stages contributed panels, so it fails the moment a future late appender reintroduces the
"invariant-not-re-established-after-late-mutation" class. Running the FULL pipeline INCLUDING the
coverage-bind stage — and asserting AFTER it — is the load-bearing detail; a pre-bind assertion is
exactly the blind spot that let the class ship (dashboard_spec capped at 0.8333 by OBS-100h).
"""

import json

import yaml

from startd8.observability.artifact_generator import (
    _COVERAGE_BIND_GROUP,
    generate_observability_artifacts,
)


def _run(tmp_path):
    """Full generate with an AffordanceMap that appends coverage-bind panels for families NOT
    otherwise panelled (so the bind actually adds unpositioned panels — reproduces the class)."""
    onb = tmp_path / "onboarding-metadata.json"
    onb.write_text(
        json.dumps(
            {
                "project_id": "harbor",
                "instrumentation_hints": {
                    "exp": {
                        "service_id": "exp",
                        "transport": "http",
                        "language": "go",
                        "metrics": {
                            "declared_emitted_series": [
                                {"name": "harbor_statistics_total_projects", "type": "gauge", "labels": {"job": "exp"}},
                            ]
                        },
                    }
                },
            }
        )
    )
    affordance_map = [
        {
            "element_id": "exp",
            "locus_status": "source_backed",
            "source_loci": [
                {"family_or_signal": "harbor_core_operation_total", "signal_kind": "metric"},
                {"family_or_signal": "harbor_registry_request_total", "signal_kind": "metric"},
            ],
        }
    ]
    out = tmp_path / "out"
    generate_observability_artifacts(
        onboarding_metadata_path=onb, output_dir=out, affordance_map=affordance_map
    )
    return out


def _emitted_dashboards(out):
    return list((out / "dashboards").glob("*-dashboard-spec.yaml"))


def test_every_emitted_panel_has_gridpos_after_coverage_bind(tmp_path):
    out = _run(tmp_path)
    specs = _emitted_dashboards(out)
    assert specs, "no dashboard specs emitted"

    saw_coverage_bind_panel = False
    for spec in specs:
        doc = yaml.safe_load(spec.read_text()) or {}
        panels = doc.get("panels") or []
        assert panels, f"{spec.name} has no panels"
        for panel in panels:
            if panel.get("group") == _COVERAGE_BIND_GROUP:
                saw_coverage_bind_panel = True
            assert "gridPos" in panel, (
                f"{spec.name} panel {panel.get('title')!r} "
                f"(group {panel.get('group')!r}) missing gridPos after the bind stage"
            )

    # Non-vacuous: the late coverage-bind stage really did append panels — otherwise the invariant
    # would pass trivially without exercising the class this guards.
    assert saw_coverage_bind_panel, "coverage-bind stage added no panels — test would be vacuous"


def test_bound_dashboard_not_gridpos_capped_in_quality(tmp_path):
    """The emitted quality report scores the exporter dashboard without the OBS-100h gridPos cap
    (0.8333). After the terminal normalize the dashboard_spec is not gridPos-flagged."""
    out = _run(tmp_path)
    quality = json.loads((out / "observability-quality.json").read_text())
    dash = ((quality.get("services") or {}).get("exp") or {}).get("dashboard_spec")
    assert dash is not None, "no exp dashboard_spec quality in report"
    issues = " ".join(i.get("message", "") for i in (dash.get("issues") or []))
    assert "gridPos" not in issues, f"dashboard still flags gridPos: {issues}"
    # The OBS-100h cap held the score at 0.8333 pre-fix; post-fix it clears that ceiling.
    assert dash.get("score", 0) > 0.8333, f"dashboard score still capped: {dash.get('score')}"
