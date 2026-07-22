"""#226 Phase 2b — FR-5 emission (functional SLOs) + FR-9 coverage report.

FR-5: each declared non-triplet functional[] FR emits an SLO on a convention series
(FR-6a) with the FR's target + a `source_fr` label (FR-8). FRs the emitter can't
ground become FR-9's `unfulfilled` class — never faked. FR-9: the report distinguishes
∅ services from unfulfilled FRs (the pilot's "6 of 7 → nothing" made visible).
"""

import json

import yaml

from startd8.observability.artifact_generator import (
    BusinessContext,
    ConventionMetric,
    FunctionalRequirement,
    ServiceHints,
    generate_functional_slos,
    generate_observability_artifacts,
)


def _worker(signal_kinds_targets):
    return ServiceHints(service_id="mailer", transport="", kinds=["async_worker"])


class TestFunctionalEmission:
    def test_queue_depth_fr_emits_slo_on_convention_series(self):
        business = BusinessContext(
            criticality="high",
            functional_requirements=[
                FunctionalRequirement(id="FR-006", signal_kind="queue_depth", target="1000"),
            ],
        )
        result = generate_functional_slos(_worker(None), business)
        assert result.status == "generated"
        assert "messaging_client_queued_messages" in result.content
        assert "source_fr: FR-006" in result.content
        assert result.quality["emitted_fr_ids"] == ["FR-006"]
        assert "http_server_duration" not in result.content

    def test_custom_fr_uses_its_own_query(self):
        business = BusinessContext(
            functional_requirements=[
                FunctionalRequirement(id="FR-X", signal_kind="custom", target="my_metric{a=\"b\"} > 5"),
            ],
        )
        result = generate_functional_slos(_worker(None), business)
        assert 'my_metric{a="b"} > 5' in result.content

    def test_ungroundable_fr_is_unfulfilled_not_faked(self):
        business = BusinessContext(
            functional_requirements=[
                FunctionalRequirement(id="FR-Z", signal_kind="freshness"),  # no target
                FunctionalRequirement(id="FR-Q", signal_kind="mystery", target="1"),  # unknown kind
            ],
        )
        result = generate_functional_slos(_worker(None), business)
        assert result.status == "skipped"  # nothing groundable
        ids = {u["id"] for u in result.quality["unfulfilled"]}
        assert ids == {"FR-Z", "FR-Q"}

    def test_triplet_kinds_skipped_here(self):
        # availability/latency/throughput are the convention triplet, not functional SLOs.
        business = BusinessContext(
            functional_requirements=[FunctionalRequirement(id="FR-1", signal_kind="latency", target="500ms")],
        )
        assert generate_functional_slos(_worker(None), business).status == "skipped"

    def test_no_functional_is_skipped(self):
        assert generate_functional_slos(_worker(None), BusinessContext()).status == "skipped"

    def test_fr_scoped_to_other_service_skipped(self):
        business = BusinessContext(
            functional_requirements=[
                FunctionalRequirement(id="FR-9", signal_kind="queue_depth", target="1", service="someone-else"),
            ],
        )
        assert generate_functional_slos(_worker(None), business).status == "skipped"


class TestFr9Coverage:
    def test_report_fr_coverage_populated(self, tmp_path):
        # Onboarding metadata with a worker; manifest with a groundable + an
        # ungroundable FR → report.fr_coverage shows emitted + unfulfilled.
        meta = tmp_path / "onboarding-metadata.json"
        meta.write_text(json.dumps({
            "project_id": "p",
            "instrumentation_hints": {
                "mailer": {
                    "service_id": "mailer",
                    "kind": "async_worker",
                    "metrics": {"convention_based": [
                        {"name": "messaging.process.duration", "type": "histogram", "source": "otel_semconv:messaging"}
                    ]},
                },
            },
        }))
        manifest = tmp_path / ".contextcore.yaml"
        manifest.write_text(
            "spec:\n"
            "  business: {criticality: high}\n"
            "  requirements:\n"
            "    functional:\n"
            "      - {id: FR-006, signal_kind: queue_depth, target: '1000'}\n"
            "      - {id: FR-007, signal_kind: freshness}\n"
        )
        report = generate_observability_artifacts(
            onboarding_metadata_path=meta, output_dir=tmp_path / "out",
            manifest_path=manifest, dry_run=True,
        )
        cov = report.fr_coverage
        assert "FR-006" in cov["emitted"]
        assert any(u["id"] == "FR-007" for u in cov["unfulfilled"])
