"""Tests for the REQ-OAT-023 taxonomy keystone + REQ-OBS-SHARED-004 route_state
consumption in artifact_generator (step C).

Covers: the type-keyed registry + projections (REQ-OAT-070a), central taxonomy
stamping on ArtifactResult (REQ-OAT-023), route_state classification with the
stale-metadata clause (REQ-OBS-SHARED-004), honest skips + the owned_elsewhere
coverage-denominator exclusion (REQ-OAT-052), and that the legacy 4-value
capability axis is NOT touched (CRP R2-F1).
"""

import json

import pytest

from startd8.observability.artifact_generator import (
    _ARTIFACT_TYPE_REGISTRY,
    _ARTIFACT_TYPE_TO_CATEGORY,
    ArtifactResult,
    ConventionMetric,
    ServiceHints,
    _coverage_by_category,
    _infer_metric_category,
    _owned_elsewhere_types,
    _stamp_taxonomy,
    classify_route_state,
    classify_route_states,
    generate_observability_artifacts,
    resolve_artifact_spec,
)
from startd8.observability.taxonomy_enums import (
    CATEGORY_VALUES,
    ORIENTATION_VALUES,
    ROUTE_STATE_VALUES,
    Category,
    RouteState,
)


# ---------------------------------------------------------------------------
# Registry + projections (REQ-OAT-070a)
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_every_row_uses_valid_taxonomy_values(self):
        for declared, spec in _ARTIFACT_TYPE_REGISTRY.items():
            assert spec.declared_type == declared
            assert spec.category in CATEGORY_VALUES
            assert spec.orientation in ORIENTATION_VALUES

    def test_resolve_by_declared_and_runtime_label(self):
        # runtime "alert_rule" → declared "prometheus_rule"
        assert resolve_artifact_spec("alert_rule").declared_type == "prometheus_rule"
        # runtime "dashboard_spec" AND rendered "dashboard" → declared "dashboard"
        assert resolve_artifact_spec("dashboard_spec").declared_type == "dashboard"
        assert resolve_artifact_spec("dashboard").declared_type == "dashboard"
        # declared == runtime
        assert resolve_artifact_spec("slo_definition").declared_type == "slo_definition"

    def test_resolve_unknown_returns_none(self):
        assert resolve_artifact_spec("not_a_real_type") is None

    def test_order_is_producers_before_consumers(self):
        # capability_index / portal (project consumers) come after the per-service rows.
        triplet = _ARTIFACT_TYPE_REGISTRY["prometheus_rule"].order
        cap = _ARTIFACT_TYPE_REGISTRY["capability_index"].order
        assert triplet < cap


class TestLegacyAxisUntouched:
    """CRP R2-F1: the legacy 4-value capability axis must NOT leak taxonomy strings."""

    def test_legacy_values_are_the_capability_axis(self):
        assert set(_ARTIFACT_TYPE_TO_CATEGORY.values()) <= {
            "observe", "integration", "action", "reference",
        }

    def test_legacy_values_are_disjoint_from_taxonomy(self):
        assert set(_ARTIFACT_TYPE_TO_CATEGORY.values()).isdisjoint(CATEGORY_VALUES)


# ---------------------------------------------------------------------------
# Central taxonomy stamping (REQ-OAT-023)
# ---------------------------------------------------------------------------


class TestStampTaxonomy:
    def test_stamps_category_orientation_declared_runtime(self):
        r = _stamp_taxonomy(ArtifactResult(
            artifact_type="alert_rule", service_id="svc", output_path="p", status="generated",
        ))
        assert r.category == Category.SERVICE.value
        assert r.orientation in ORIENTATION_VALUES
        assert r.declared_type == "prometheus_rule"
        assert r.runtime_type == "alert_rule"

    def test_unknown_label_leaves_axes_unset(self):
        r = _stamp_taxonomy(ArtifactResult(
            artifact_type="mystery", service_id="svc", output_path="p", status="error",
        ))
        assert r.category == ""
        assert r.declared_type == ""


# ---------------------------------------------------------------------------
# route_state classification (REQ-OBS-SHARED-004)
# ---------------------------------------------------------------------------


class TestClassifyRouteState:
    def test_sdk_emitted(self):
        assert classify_route_state("startd8_cost_total", sdk_emitted=True) is RouteState.SDK_EMITTED

    def test_convention_is_external(self):
        assert classify_route_state("http.server.duration", is_convention=True) is RouteState.EXTERNAL_CONVENTION

    def test_stale_contextcore_wins_over_sdk_emitted(self):
        # REQ-OBS-SHARED-004 stale-metadata clause: contextcore_* listed as declared
        # MUST classify as contextcore_owned, never mis-attributed to the SDK.
        assert classify_route_state(
            "contextcore_task_progress", sdk_emitted=True,
        ) is RouteState.CONTEXTCORE_OWNED

    def test_declared_route_state_is_honored(self):
        assert classify_route_state(
            "anything", declared="external_convention",
        ) is RouteState.EXTERNAL_CONVENTION

    def test_invalid_declared_falls_through_to_inference(self):
        assert classify_route_state(
            "startd8_x", sdk_emitted=True, declared="bogus",
        ) is RouteState.SDK_EMITTED


class TestInferMetricCategory:
    @pytest.mark.parametrize("name,expected", [
        ("startd8_cost_total", Category.AI_AGENT.value),
        ("contextcore_task_status", Category.PROJECT.value),
        ("http.server.duration", Category.SERVICE.value),
        ("rpc.server.duration", Category.SERVICE.value),
        ("totally_unknown", ""),
    ])
    def test_inference(self, name, expected):
        assert _infer_metric_category(name) == expected


class TestClassifyRouteStates:
    def test_both_manifests_validation_fixture(self):
        # REQ-OBS-SHARED-004 Validation: a generator fed both manifests routes cat-5
        # metrics sdk_emitted, contextcore_* contextcore_owned, convention external.
        svc = ServiceHints(
            service_id="sdk",
            transport="http",
            declared_metrics=[
                ConventionMetric("startd8_cost_total", "counter", "manifest", category=Category.AI_AGENT.value, route_state="sdk_emitted"),
                ConventionMetric("contextcore_task_status", "gauge", "manifest"),  # stale, undeclared
            ],
            convention_metrics=[
                ConventionMetric("http.server.duration", "histogram", "otel_semconv:http"),
            ],
        )
        rows = {r["name"]: r for r in classify_route_states([svc])}
        assert rows["startd8_cost_total"]["route_state"] == "sdk_emitted"
        assert rows["contextcore_task_status"]["route_state"] == "contextcore_owned"
        assert rows["contextcore_task_status"]["owner"] == "contextcore"
        assert rows["http.server.duration"]["route_state"] == "external_convention"

    def test_declared_vs_inferred_source_recorded(self):
        svc = ServiceHints(
            service_id="sdk", transport="http",
            declared_metrics=[
                ConventionMetric("startd8_cost_total", "counter", "m", category=Category.AI_AGENT.value),
                ConventionMetric("startd8_tokens_total", "counter", "m"),  # no declared category
            ],
        )
        rows = {r["name"]: r for r in classify_route_states([svc])}
        assert rows["startd8_cost_total"]["classification_source"] == "declared"
        assert rows["startd8_tokens_total"]["classification_source"] == "inferred"

    def test_changing_category_does_not_change_route_state(self):
        # R3-F6: route_state is independent of category.
        base = ConventionMetric("startd8_cost_total", "counter", "m", category=Category.AI_AGENT.value)
        relabelled = ConventionMetric("startd8_cost_total", "counter", "m", category=Category.SERVICE.value)
        svc_a = ServiceHints(service_id="a", transport="http", declared_metrics=[base])
        svc_b = ServiceHints(service_id="b", transport="http", declared_metrics=[relabelled])
        rs_a = classify_route_states([svc_a])[0]["route_state"]
        rs_b = classify_route_states([svc_b])[0]["route_state"]
        assert rs_a == rs_b == "sdk_emitted"


# ---------------------------------------------------------------------------
# owned_elsewhere + coverage denominator (REQ-OAT-052)
# ---------------------------------------------------------------------------


class TestOwnedElsewhere:
    def test_owner_field_marks_cede(self):
        meta = {"artifact_types": {"capability_index": {"owner": "contextcore"}, "dashboard": {}}}
        assert _owned_elsewhere_types(meta) == {"capability_index": "contextcore"}

    def test_route_state_marks_cede(self):
        meta = {"artifact_types": {"capability_index": {"route_state": "contextcore_owned"}}}
        assert _owned_elsewhere_types(meta) == {"capability_index": "contextcore"}

    def test_list_form_has_no_owners(self):
        assert _owned_elsewhere_types({"artifact_types": ["dashboard", "slo_definition"]}) == {}


class TestCoverageByCategory:
    def test_buckets_by_registry_category(self):
        cov = _coverage_by_category({"prometheus_rule", "dashboard", "slo_definition"})
        # all three are service_observability + implemented → 1.0
        assert cov[Category.SERVICE.value] == 1.0


class TestCoverageDenominatorExclusion:
    """REQ-OAT-052 R4-F2: a ceded capability_index must NOT drag coverage below 1.0."""

    def _meta(self, artifact_types):
        return {
            "project_id": "demo",
            "instrumentation_hints": {
                "api": {
                    "service_id": "api", "transport": "http",
                    "metrics": {"convention_based": [
                        {"name": "http.server.duration", "type": "histogram", "source": "otel"},
                    ]},
                },
            },
            "artifact_types": artifact_types,
        }

    def test_ceded_type_excluded_from_denominator(self, tmp_path):
        meta = self._meta({
            "dashboard": {}, "prometheus_rule": {}, "slo_definition": {},
            "capability_index": {"owner": "contextcore"},  # ceded
        })
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(meta))
        report = generate_observability_artifacts(
            onboarding_metadata_path=meta_path, output_dir=tmp_path / "out",
        )
        # capability_index is NOT produced (ceded) and is recorded as an owned_elsewhere skip.
        ceded = [a for a in report.artifacts if a.skip_reason == "owned_elsewhere"]
        assert any(a.artifact_type == "capability_index" for a in ceded)
        assert all(a.route_state == "contextcore_owned" and a.owner == "contextcore" for a in ceded)
        assert not any(
            a.artifact_type == "capability_index" and a.status == "generated"
            for a in report.artifacts
        )
        # The owned_elsewhere type is excluded from the coverage denominator (R4-F2).
        declared = set(report.declared_artifact_types)
        counted = declared - {a.artifact_type for a in ceded}
        assert "capability_index" not in counted

    def test_unimplemented_type_is_declared_unimplemented(self, tmp_path):
        meta = self._meta({"dashboard": {}, "trace_config": {}})  # trace_config has no generator
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(meta))
        report = generate_observability_artifacts(
            onboarding_metadata_path=meta_path, output_dir=tmp_path / "out",
        )
        skips = {a.artifact_type: a for a in report.artifacts if a.status == "skipped"}
        assert skips["trace_config"].skip_reason == "unimplemented"
        assert skips["trace_config"].route_state == "declared_unimplemented"
        assert skips["trace_config"].owner is None


class TestRouteStateValuesEnum:
    def test_four_states(self):
        assert ROUTE_STATE_VALUES == {
            "sdk_emitted", "contextcore_owned", "declared_unimplemented", "external_convention",
        }
