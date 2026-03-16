"""Tests for ContextSeed.service_communication_graph — REQ-SIG-200."""

from startd8.seeds.models import ContextSeed


class TestContextSeedCommunicationGraph:
    """REQ-SIG-200 §3.3: ContextSeed carries service_communication_graph."""

    def test_graph_in_to_dict(self):
        graph = {
            "services": {"emailservice": {"imports": ["demo_pb2"], "protocol": "grpc"}},
            "shared_modules": {"demo_pb2": {"type": "proto_stub", "used_by": ["emailservice"]}},
        }
        seed = ContextSeed(service_communication_graph=graph)
        d = seed.to_dict()
        assert d["service_communication_graph"] == graph

    def test_default_none_omitted(self):
        seed = ContextSeed()
        assert seed.service_communication_graph is None
        assert "service_communication_graph" not in seed.to_dict()

    def test_empty_dict_serialized(self):
        seed = ContextSeed(service_communication_graph={})
        # Empty dict is not None, so it should be serialized
        assert seed.to_dict()["service_communication_graph"] == {}
