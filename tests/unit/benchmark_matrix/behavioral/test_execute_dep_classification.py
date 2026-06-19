"""R3-F3 / FR-T2-DEPS2 — off-contract dependency classification (model fault vs harness gap).

Pure unit tests over the classifier the behavioral launch path uses to decide whether a missing
module floors the cell (model abandoned its wire protocol) or degrades it (harness provisioning gap).
"""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix.behavioral.execute import _is_off_contract_dep, _package_root


@pytest.mark.parametrize("module,expected", [
    ("express", "express"),
    ("express/lib/router", "express"),
    ("@grpc/grpc-js", "@grpc/grpc-js"),
    ("@grpc/grpc-js/build/src/foo", "@grpc/grpc-js"),
    ("@apollo/server", "@apollo/server"),
])
def test_package_root(module, expected):
    assert _package_root(module) == expected


def test_grpc_contract_floors_http_framework():
    # A gRPC ("tcp") service that require()s an HTTP/GraphQL framework abandoned its contract → floor.
    for fw in ("express", "fastify", "koa", "@apollo/server", "body-parser"):
        assert _is_off_contract_dep(fw, "tcp") is True, fw


def test_grpc_contract_degrades_protocol_and_unknown_deps():
    # A protocol-appropriate dep (or a vendored/unknown one) missing is a harness gap → degrade.
    for dep in ("@grpc/grpc-js", "@grpc/proto-loader", "pino", "uuid", "lodash"):
        assert _is_off_contract_dep(dep, "tcp") is False, dep


def test_http_contract_floors_grpc_package():
    # Symmetric: a REST/GraphQL ("http") service reaching for a gRPC package is off-contract → floor.
    assert _is_off_contract_dep("@grpc/grpc-js", "http") is True
    assert _is_off_contract_dep("grpc", "http") is True


def test_http_contract_allows_http_frameworks():
    # express/apollo on an HTTP contract is the EXPECTED stack — must NOT floor (no false inversion).
    for fw in ("express", "fastify", "@apollo/server", "graphql-yoga"):
        assert _is_off_contract_dep(fw, "http") is False, fw
