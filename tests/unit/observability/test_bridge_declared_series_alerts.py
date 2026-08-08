# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""sdk#439 sibling (bridge lane): the alert loops draw gauges + error counters from
``declared_emitted_series`` too, INSTALLED-mode only.

A prometheus_exporter-style service emits its gauges (e.g. ``harbor_statistics_*``) into
``declared_emitted_series``, NOT ``convention_metrics``. The convention-only alert loops
therefore emitted ZERO absence/error alerts for it — live bridge coverage stuck at 3/22 while
the freshness SLO path (post-#439) already bound 19/22. This mirrors #439's union onto the two
alert loops in ``generate_alert_rules``, gated on ``installed`` mode exactly as #439 gated its
freshness loop — so the default-mode orientation contract (emitted series → HUMAN axis only,
bridge==0) and the whole default-mode golden corpus stay byte-identical.
"""

import yaml

from startd8.observability.artifact_generator_generators import generate_alert_rules
from startd8.observability.artifact_generator_models import (
    BusinessContext,
    ConventionMetric,
    DeclaredEmittedSeries,
    ServiceHints,
)


def _business(deployment_mode=None):
    return BusinessContext(
        criticality="high",
        availability="99.9",
        latency_p99="500ms",
        throughput="100rps",
        project_id="harbor",
        slo_window="30d",
        deployment_mode=deployment_mode,
    )


def _exporter_service():
    """A prometheus_exporter-style service: its real surface lives in
    ``declared_emitted_series`` (gauges + an error counter), never in convention_metrics."""
    return ServiceHints(
        service_id="exporter",
        transport="http",
        convention_metrics=[],
        declared_emitted_series=[
            DeclaredEmittedSeries(name="harbor_statistics_total_projects", type="gauge"),
            DeclaredEmittedSeries(name="harbor_statistics_total_users", type="gauge"),
            DeclaredEmittedSeries(name="harbor_replication_failures_total", type="counter"),
        ],
    )


def _alerts(result):
    """Parse the alert-rule YAML body from an ArtifactResult (``header\\n\\nyaml``)."""
    if result.status != "generated" or "\n\n" not in (result.content or ""):
        return []
    doc = yaml.safe_load(result.content.split("\n\n", 1)[1]) or {}
    return doc.get("groups", [{}])[0].get("rules", []) if "groups" in doc else doc.get("rules", [])


def _exprs(result):
    return {r.get("expr", "") for r in _alerts(result)}


class TestBridgeDeclaredSeriesAlerts:
    def test_installed_mode_alerts_exporter_declared_gauges(self):
        """INSTALLED: each declared_emitted_series gauge gets an absence alert (bridge lift)."""
        result = generate_alert_rules(_exporter_service(), _business("installed"))
        assert result.status == "generated"
        exprs = _exprs(result)
        assert "absent(harbor_statistics_total_projects{})" in exprs
        assert "absent(harbor_statistics_total_users{})" in exprs

    def test_installed_mode_alerts_exporter_declared_error_counter(self):
        """INSTALLED: a declared_emitted_series error/fail-named counter gets an increasing alert."""
        result = generate_alert_rules(_exporter_service(), _business("installed"))
        exprs = _exprs(result)
        assert "increase(harbor_replication_failures_total{}[15m]) > 0" in exprs

    def test_default_mode_leaves_bridge_empty(self):
        """DEFAULT/deployed: declared-only exporter yields NO alerts — orientation contract
        (emitted series → HUMAN axis only) + byte-identity preserved."""
        for mode in (None, "deployed"):
            result = generate_alert_rules(_exporter_service(), _business(mode))
            assert result.status == "skipped", f"mode={mode} unexpectedly emitted alerts"
            assert _exprs(result) == set()

    def test_convention_gauge_still_alerts_in_all_modes(self):
        """Regression guard: convention gauges keep alerting in EVERY mode (unchanged by this
        change — only the declared-series addition is installed-gated)."""
        svc = ServiceHints(
            service_id="queue",
            transport="http",
            convention_metrics=[ConventionMetric("queue_depth", "gauge", "conv")],
        )
        for mode in (None, "deployed", "installed"):
            exprs = _exprs(generate_alert_rules(svc, _business(mode)))
            assert "absent(queue_depth{})" in exprs, f"mode={mode} dropped the convention alert"

    def test_dedup_convention_wins_over_declared(self):
        """A gauge present in BOTH collections yields exactly one absence rule (convention wins)."""
        svc = ServiceHints(
            service_id="dup",
            transport="http",
            convention_metrics=[ConventionMetric("harbor_statistics_total_projects", "gauge", "conv")],
            declared_emitted_series=[
                DeclaredEmittedSeries(name="harbor_statistics_total_projects", type="gauge"),
            ],
        )
        result = generate_alert_rules(svc, _business("installed"))
        absents = [e for e in _exprs(result) if e == "absent(harbor_statistics_total_projects{})"]
        assert len(absents) == 1
