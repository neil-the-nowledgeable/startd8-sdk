# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""sdk#439/#440 sibling (binding lane): _select_functional_metric binds a functional SLI to the
series the service ACTUALLY emits — and declared_emitted_series IS the SDK's real-emitted-series
collection (#286/REQ-CCL-107), so it must count as "real evidence of existing".

A prometheus_exporter/worker puts its series in declared_emitted_series, not convention/declared
metrics; omitting that collection made the selector fall back to the aspirational candidates[0]
even when the real series was declared as emitted. These tests pin: (a) a declared_emitted_series
name now wins over the fallback, dot/underscore-insensitively; (b) convention/declared precedence
is unchanged; (c) an empty/non-matching collection is byte-identical (still falls back).
"""

from startd8.observability.artifact_generator_generators import _select_functional_metric
from startd8.observability.artifact_generator_models import (
    ConventionMetric,
    DeclaredEmittedSeries,
    ServiceHints,
)

# candidates[0] is the primary/aspirational; candidates[1] is only real if the service emits it.
CANDIDATES = ("primary_saturation_ratio", "kafka.consumer.records.lag.max")


class TestSelectFunctionalMetricDeclaredSeries:
    def test_declared_emitted_series_binds_over_fallback(self):
        """A real series present ONLY in declared_emitted_series wins over candidates[0],
        compared dot/underscore-insensitively (OTel dotted vs Prom underscored)."""
        svc = ServiceHints(
            service_id="worker",
            transport="grpc",
            declared_emitted_series=[
                DeclaredEmittedSeries(name="kafka_consumer_records_lag_max", type="gauge"),
            ],
        )
        assert _select_functional_metric(CANDIDATES, svc) == "kafka.consumer.records.lag.max"

    def test_no_evidence_still_falls_back_to_primary(self):
        """Byte-identical: no matching series anywhere → the primary candidate (candidates[0])."""
        svc = ServiceHints(service_id="worker", transport="grpc")
        assert _select_functional_metric(CANDIDATES, svc) == CANDIDATES[0]

    def test_declared_emitted_series_non_match_is_unchanged(self):
        """A declared_emitted_series that matches NO candidate does not perturb selection."""
        svc = ServiceHints(
            service_id="worker",
            transport="grpc",
            declared_emitted_series=[
                DeclaredEmittedSeries(name="some_unrelated_series_total", type="counter"),
            ],
        )
        assert _select_functional_metric(CANDIDATES, svc) == CANDIDATES[0]

    def test_convention_metric_precedence_unchanged(self):
        """Convention metrics remain a valid evidence source (unchanged path)."""
        svc = ServiceHints(
            service_id="worker",
            transport="grpc",
            convention_metrics=[
                ConventionMetric("kafka.consumer.records.lag.max", "gauge", "conv"),
            ],
        )
        assert _select_functional_metric(CANDIDATES, svc) == "kafka.consumer.records.lag.max"
