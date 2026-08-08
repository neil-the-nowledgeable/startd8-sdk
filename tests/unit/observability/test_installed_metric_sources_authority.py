# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Class-A metabolize (PROPOSAL_generation_invariant_classes.md): _installed_metric_sources is the
single enumeration authority for the INSTALLED-gated emit loops (sdk#439 freshness SLO + sdk#440's
two alert loops). These are CHARACTERIZATION tests — they pin the union so a future edit cannot
silently drop declared_emitted_series from one loop again (the recurring enumeration-incompleteness
class), and they assert all three emit lanes draw from the same authority.

Corpus deliberately includes an exporter whose declared_emitted_series gauge is NOT in
convention_metrics (the Harbor exporter shape) — the exact case the class kept mis-handling.
"""

from startd8.observability.artifact_generator_generators import (
    _installed_metric_sources,
    generate_alert_rules,
    generate_slo_definitions,
)
from startd8.observability.artifact_generator_models import (
    BusinessContext,
    ConventionMetric,
    DeclaredEmittedSeries,
    ServiceHints,
)

DECLARED_GAUGE = "harbor_statistics_total_projects"


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


def _exporter():
    """Exporter shape: real surface lives in declared_emitted_series, empty convention_metrics."""
    return ServiceHints(
        service_id="exp",
        transport="http",
        convention_metrics=[],
        declared_emitted_series=[DeclaredEmittedSeries(name=DECLARED_GAUGE, type="gauge")],
    )


class TestInstalledMetricSourcesHelper:
    def test_installed_unions_declared_emitted_series(self):
        names = [getattr(m, "name", "") for m in _installed_metric_sources(_exporter(), _business("installed"))]
        assert names == [DECLARED_GAUGE]

    def test_default_and_deployed_are_convention_only(self):
        for mode in (None, "deployed"):
            assert _installed_metric_sources(_exporter(), _business(mode)) == []

    def test_convention_first_ordering_so_convention_wins_dedup(self):
        """Convention entries precede declared, so a prom-name dedup at the call site keeps the
        convention metric when both collections name the same series."""
        svc = ServiceHints(
            service_id="dup",
            transport="http",
            convention_metrics=[ConventionMetric("shared_gauge", "gauge", "conv")],
            declared_emitted_series=[DeclaredEmittedSeries(name="shared_gauge", type="gauge")],
        )
        sources = _installed_metric_sources(svc, _business("installed"))
        assert isinstance(sources[0], ConventionMetric)  # convention object first
        assert isinstance(sources[1], DeclaredEmittedSeries)
        assert [getattr(m, "name", "") for m in sources] == ["shared_gauge", "shared_gauge"]


class TestAllEmitLanesShareTheAuthority:
    """The three converged emit lanes (gauge-absence alert, error-counter alert, freshness SLO) all
    reference the exporter's declared gauge in installed mode, and none of them do in default mode —
    proof they enumerate the same authority."""

    def test_installed_all_lanes_reference_declared_gauge(self):
        alerts = generate_alert_rules(_exporter(), _business("installed")).content or ""
        slos = generate_slo_definitions(_exporter(), _business("installed")).content or ""
        assert DECLARED_GAUGE in alerts  # gauge-absence alert lane
        assert DECLARED_GAUGE in slos    # freshness SLO lane

    def test_default_no_lane_references_declared_gauge(self):
        alerts = generate_alert_rules(_exporter(), _business(None))
        slos = generate_slo_definitions(_exporter(), _business(None))
        assert DECLARED_GAUGE not in (alerts.content or "")
        assert DECLARED_GAUGE not in (slos.content or "")
