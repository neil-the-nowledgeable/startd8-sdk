"""Tests for service metadata type guard — REQ-GPC-600."""

from unittest.mock import MagicMock

from startd8.workflows.builtin.plan_ingestion_workflow import _infer_service_metadata


def _make_feature(protocol: str = "", target_files: list | None = None):
    """Create a minimal ParsedFeature-like object."""
    f = MagicMock()
    f.protocol = protocol
    f.runtime_dependencies = []
    f.api_signatures = []
    f.negative_scope = []
    f.target_files = target_files or []
    return f


class TestInferServiceMetadataTypeGuard:
    """REQ-GPC-600: marker dicts produce empty string, not dict transport."""

    def test_marker_dict_becomes_empty_string(self):
        """Omitted marker in transport_protocol → empty string → no key."""
        features = [_make_feature()]
        onboarding = {"transport_protocol": {"_omitted": "profile=source"}}

        result = _infer_service_metadata(features, onboarding)

        # transport should be "" → not included in result
        assert "transport_protocol" not in result

    def test_string_transport_passes_through(self):
        """Normal string transport_protocol works as before."""
        features = [_make_feature()]
        onboarding = {"transport_protocol": "grpc"}

        result = _infer_service_metadata(features, onboarding)
        assert result["transport_protocol"] == "grpc"

    def test_feature_protocol_takes_precedence(self):
        """Feature-derived protocol overrides onboarding."""
        features = [_make_feature(protocol="grpc")]
        onboarding = {"transport_protocol": "http"}

        result = _infer_service_metadata(features, onboarding)
        assert result["transport_protocol"] == "grpc"

    def test_none_onboarding_no_crash(self):
        """None onboarding doesn't crash."""
        features = [_make_feature()]
        result = _infer_service_metadata(features, None)
        assert "transport_protocol" not in result
