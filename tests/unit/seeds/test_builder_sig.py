"""Tests for SeedBuilder.set_service_communication_graph — REQ-SIG-200."""

from startd8.seeds.builder import SeedBuilder


class TestSeedBuilderCommunicationGraph:
    """REQ-SIG-200: Builder sets service_communication_graph."""

    def test_builder_sets_graph(self):
        graph = {
            "services": {"emailservice": {"imports": ["demo_pb2"]}},
            "shared_modules": {"demo_pb2": {"type": "proto_stub"}},
        }
        builder = SeedBuilder()
        builder.set_service_communication_graph(graph)
        seed = builder.build()
        assert seed["service_communication_graph"] == graph

    def test_builder_default_none(self):
        builder = SeedBuilder()
        seed = builder.build()
        assert "service_communication_graph" not in seed

    def test_builder_none_explicit(self):
        builder = SeedBuilder()
        builder.set_service_communication_graph(None)
        seed = builder.build()
        assert "service_communication_graph" not in seed
