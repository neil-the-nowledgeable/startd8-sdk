"""Round-trip tests for FeatureSpec metadata serialization (Task 4)."""

from startd8.contractors.queue import FeatureSpec, FeatureStatus


class TestFeatureSpecMetadataRoundTrip:
    """Verify that FeatureSpec.metadata survives to_dict/from_dict cycle."""

    def test_metadata_round_trip_empty(self):
        """Empty metadata round-trips correctly."""
        spec = FeatureSpec(id="T-001", name="test feature")
        d = spec.to_dict()
        restored = FeatureSpec.from_dict(d)
        assert restored.metadata == {}
        assert restored.id == "T-001"

    def test_metadata_round_trip_with_data(self):
        """Metadata with nested structures round-trips correctly."""
        metadata = {
            "service_metadata": {
                "transport_protocol": "grpc",
                "runtime_dependencies": ["grpcio", "protobuf"],
            },
            "_enrichment": {
                "prompt_constraints": ["Use async patterns"],
            },
            "custom_field": 42,
        }
        spec = FeatureSpec(
            id="T-002",
            name="grpc service",
            description="Generate gRPC service",
            target_files=["src/service.py"],
            metadata=metadata,
        )
        d = spec.to_dict()

        # Verify dict contains metadata
        assert d["metadata"] == metadata
        assert d["status"] == "pending"

        # Round-trip
        restored = FeatureSpec.from_dict(d)
        assert restored.metadata == metadata
        assert restored.metadata["service_metadata"]["transport_protocol"] == "grpc"
        assert restored.target_files == ["src/service.py"]

    def test_from_dict_missing_metadata_defaults_empty(self):
        """State files lacking metadata field get empty dict default."""
        d = {
            "id": "T-003",
            "name": "legacy feature",
            "description": "",
            "dependencies": [],
            "target_files": [],
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "error_message": None,
            "integration_attempts": 0,
            "generated_files": [],
        }
        # No "metadata" key at all -- simulates legacy state file
        restored = FeatureSpec.from_dict(d)
        assert restored.metadata == {}

    def test_metadata_survives_status_transitions(self):
        """Metadata persists through status changes and re-serialization."""
        spec = FeatureSpec(
            id="T-004",
            name="status test",
            metadata={"key": "value"},
        )
        spec.status = FeatureStatus.GENERATED
        spec.generated_files = ["out/code.py"]

        d = spec.to_dict()
        assert d["status"] == "generated"
        assert d["metadata"] == {"key": "value"}

        restored = FeatureSpec.from_dict(d)
        assert restored.status == FeatureStatus.GENERATED
        assert restored.metadata == {"key": "value"}
        assert restored.generated_files == ["out/code.py"]
