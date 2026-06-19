"""Proto parser tests — demo.proto conformance."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.proto_codegen import get_service, parse_proto

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_PROTO = REPO_ROOT / "docs" / "design" / "model-benchmark" / "seeds" / "demo.proto"


@pytest.fixture(scope="module")
def demo_text() -> str:
    return DEMO_PROTO.read_text(encoding="utf-8")


def test_parse_demo_services(demo_text: str):
    doc = parse_proto(demo_text)
    assert doc.package == "hipstershop"
    names = {s.name for s in doc.services}
    assert "ProductCatalogService" in names
    assert "CartService" in names


def test_get_service_rpcs(demo_text: str):
    svc = get_service(parse_proto(demo_text), "ProductCatalogService")
    rpc_names = {r.name for r in svc.rpcs}
    assert rpc_names == {"ListProducts", "GetProduct", "SearchProducts"}


def test_missing_service_raises(demo_text: str):
    with pytest.raises(ValueError, match="not found"):
        get_service(parse_proto(demo_text), "NoSuchService")


def test_streaming_rpcs_are_not_dropped():
    """The `stream` keyword on request/response must not cause the RPC to be omitted."""
    proto = """
    syntax = "proto3";
    package chat;

    service ChatService {
      rpc Send(Message) returns (Ack) {}
      rpc Subscribe(SubReq) returns (stream Message) {}
      rpc Upload(stream Chunk) returns (UploadAck) {}
      rpc Echo(stream Frame) returns (stream Frame) {}
    }
    """
    svc = get_service(parse_proto(proto), "ChatService")
    by_name = {r.name: r for r in svc.rpcs}
    assert set(by_name) == {"Send", "Subscribe", "Upload", "Echo"}
    assert by_name["Subscribe"].response == "Message"
    assert by_name["Upload"].request == "Chunk"
    assert by_name["Echo"].request == "Frame"
    assert by_name["Echo"].response == "Frame"
