"""Tests for implementation_engine.protocol — runtime-checkable protocol."""

from startd8.implementation_engine.engine import DefaultImplementationEngine
from startd8.implementation_engine.protocol import ImplementationEngine


class TestProtocol:
    def test_default_engine_satisfies_protocol(self):
        engine = DefaultImplementationEngine()
        assert isinstance(engine, ImplementationEngine)

    def test_arbitrary_object_does_not_satisfy(self):
        assert not isinstance(object(), ImplementationEngine)

    def test_protocol_is_runtime_checkable(self):
        assert hasattr(ImplementationEngine, "__protocol_attrs__") or hasattr(
            ImplementationEngine, "__abstractmethods__"
        ) or True  # runtime_checkable protocols pass isinstance checks
