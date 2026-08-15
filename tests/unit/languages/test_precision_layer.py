"""Tier-2 precision layer — wire the SDK's contract-IDL parsers into per-domain operation extraction.

Corpus-independent: writes tiny OpenAPI / .proto / .prisma fixtures and asserts the extractors wire
the real SDK parsers correctly.

Module: src/startd8/coverage_map/precision.py · Spec: docs/design/REQ-precision-layer-contract-idl-operations.md
"""

from __future__ import annotations

from startd8.coverage_map.precision import PRECISION_DOMAINS, extract_precision


_OPENAPI = """openapi: 3.0.1
info: {title: t, version: "1"}
paths:
  /users:
    get: {operationId: listUsers}
    post: {operationId: createUser}
  /orders/{id}:
    get: {operationId: getOrder}
"""
_PROTO = """
syntax = "proto3";
service CartService {
  rpc AddItem(AddItemReq) returns (Empty) {}
  rpc GetCart(GetCartReq) returns (Cart) {}
}
"""
_PRISMA = """
model User { id Int @id\n name String }
model Order { id Int @id\n total Float }
"""


class TestRegistry:
    def test_three_domains_wired(self):
        assert set(PRECISION_DOMAINS) == {"http", "rpc", "db"}
        assert PRECISION_DOMAINS["http"]["idl"] == "OpenAPI"
        assert PRECISION_DOMAINS["rpc"]["idl"] == "Protocol Buffers"


class TestHttpPrecision:
    def test_openapi_endpoints_extracted(self, tmp_path):
        (tmp_path / "openapi.yaml").write_text(_OPENAPI)
        r = extract_precision(tmp_path, "http")
        assert r["precision_available"] and r["total_operations"] == 3
        ops = {o["op"] for f in r["idl_files"] for o in f["operations"]}
        assert {"GET /users", "POST /users", "GET /orders/{id}"} == ops
        assert all(o["role"] == "SERVER" for f in r["idl_files"] for o in f["operations"])

    def test_non_3_0_spec_recorded_not_crashed(self, tmp_path):
        (tmp_path / "swagger.yaml").write_text('swagger: "2.0"\npaths: {}\n')
        r = extract_precision(tmp_path, "http")
        # load_openapi_document rejects 2.0 → recorded as a parse_error, not a crash
        assert not r["precision_available"] and r["parse_errors"]


class TestRpcPrecision:
    def test_proto_service_methods_extracted(self, tmp_path):
        (tmp_path / "svc.proto").write_text(_PROTO)
        r = extract_precision(tmp_path, "rpc")
        ops = {o["op"] for f in r["idl_files"] for o in f["operations"]}
        assert {"CartService.AddItem", "CartService.GetCart"} == ops
        add = next(o for f in r["idl_files"] for o in f["operations"] if o["op"].endswith("AddItem"))
        assert add["request"] == "AddItemReq" and add["response"] == "Empty"


class TestDbPrecision:
    def test_prisma_models_extracted(self, tmp_path):
        (tmp_path / "schema.prisma").write_text(_PRISMA)
        r = extract_precision(tmp_path, "db")
        ops = {o["op"] for f in r["idl_files"] for o in f["operations"]}
        assert {"User", "Order"} <= ops


class TestCorrectAbsence:
    def test_no_idl_is_coverage_only_not_error(self, tmp_path):
        (tmp_path / "readme.md").write_text("nothing here")
        r = extract_precision(tmp_path, "http")
        assert not r["precision_available"] and r["total_operations"] == 0 and not r["parse_errors"]
