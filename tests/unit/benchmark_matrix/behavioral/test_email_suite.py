"""Pure-Python validation of the emailservice ground-truth suite (no subprocess).

Stand up an in-process gRPC EmailService and prove ``run_email_suite`` reaches coverage 1.00 against
a *correct* servicer (so the suite's expected status outcomes are internally consistent), then prove
it DISCRIMINATES per case against deliberately-broken servicers. Also covers the equal-weight per-case
coverage shape, suite registration on the leaf path, and jinja2-template provisioning.

EmailService returns ``Empty``, so correctness is verified via gRPC STATUS: a valid request must be
accepted (OK), and malformed requests must be rejected (INVALID_ARGUMENT).
"""
from __future__ import annotations

import socket
from concurrent import futures

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import demo_pb2, demo_pb2_grpc, execute
from startd8.benchmark_matrix.behavioral.email_suite import (
    CONFIRMATION_TEMPLATE_FILENAME,
    SUITE_VERSION,
    run_email_suite,
)

pytestmark = pytest.mark.unit


def _email_valid(s: str) -> bool:
    import re
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s or ""))


class _ReferenceEmail(demo_pb2_grpc.EmailServiceServicer):
    """A correct EmailService — the in-process oracle the suite is validated against."""

    def SendOrderConfirmation(self, request, context):
        if not _email_valid(request.email):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid email")
        if not request.HasField("order") or not request.order.order_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "missing order")
        return demo_pb2.Empty()


class _BrokenAcceptsBadEmail(_ReferenceEmail):
    """Skips email validation: accepts a malformed email (the invalid-email case must fail)."""

    def SendOrderConfirmation(self, request, context):
        if not request.HasField("order") or not request.order.order_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "missing order")
        return demo_pb2.Empty()


class _BrokenAcceptsMissingOrder(_ReferenceEmail):
    """Skips order validation: accepts a request with no order (the missing-order case must fail)."""

    def SendOrderConfirmation(self, request, context):
        if not _email_valid(request.email):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid email")
        return demo_pb2.Empty()


class _BrokenRejectsEverything(_ReferenceEmail):
    """Rejects even a valid request (the valid-accepted case must fail)."""

    def SendOrderConfirmation(self, request, context):
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "always rejects")


class _BrokenWrongCode(_ReferenceEmail):
    """Rejects malformed email but with the WRONG status code (must fail: not INVALID_ARGUMENT)."""

    def SendOrderConfirmation(self, request, context):
        if not _email_valid(request.email):
            context.abort(grpc.StatusCode.INTERNAL, "wrong code")
        if not request.HasField("order") or not request.order.order_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "missing order")
        return demo_pb2.Empty()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _serve(servicer):
    port = _free_port()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_EmailServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    return server, port


@pytest.fixture()
def reference_port():
    server, port = _serve(_ReferenceEmail())
    try:
        yield port
    finally:
        server.stop(grace=None)


# --------------------------------------------------------------------------- oracle self-consistency


def test_reference_email_scores_full_coverage(reference_port):
    suite = run_email_suite(reference_port)
    failing = [r.__dict__ for r in suite.results if not r.passed]
    assert suite.coverage == 1.0, f"coverage={suite.coverage}; failing={failing}"
    assert suite.suite_version == SUITE_VERSION
    # Three equal-weight per-case checks.
    assert len(suite.results) == 3
    assert {r.name for r in suite.results} == {
        "send_valid_request_accepted",
        "send_invalid_email_rejected",
        "send_missing_order_rejected",
    }


# --------------------------------------------------------------------------- per-case discrimination


def test_broken_accepts_bad_email_fails_only_invalid_email_case():
    server, port = _serve(_BrokenAcceptsBadEmail())
    try:
        suite = run_email_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"send_invalid_email_rejected"}, [r.__dict__ for r in suite.results]
    assert suite.coverage == 2 / 3


def test_broken_accepts_missing_order_fails_only_missing_order_case():
    server, port = _serve(_BrokenAcceptsMissingOrder())
    try:
        suite = run_email_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"send_missing_order_rejected"}, [r.__dict__ for r in suite.results]


def test_broken_rejects_everything_fails_only_valid_case():
    server, port = _serve(_BrokenRejectsEverything())
    try:
        suite = run_email_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"send_valid_request_accepted"}, [r.__dict__ for r in suite.results]


def test_broken_wrong_code_fails_invalid_email_case():
    server, port = _serve(_BrokenWrongCode())
    try:
        suite = run_email_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    # Rejected, but not with INVALID_ARGUMENT → the invalid-email case is a MISS.
    assert "send_invalid_email_rejected" in failed, [r.__dict__ for r in suite.results]


def test_connect_error_when_no_server():
    suite = run_email_suite(_free_port(), connect_timeout=0.5)
    assert suite.connect_error
    assert suite.coverage == 0.0
    assert suite.results == []


# --------------------------------------------------------------------------- wiring


def test_email_registered_in_suites_leaf_path():
    assert execute._SUITES.get("emailservice") is run_email_suite
    # Leaf path: NOT the checkout dedicated branch, NOT a per-service proto override (shared demo.proto).
    assert "emailservice" not in execute._PROTO_BY_SERVICE


def test_provision_email_template_writes_confirmation_html(tmp_path):
    target_files = ["src/emailservice/server.py"]
    written = execute.provision_email_template(tmp_path, target_files)
    svc_file = tmp_path / "src" / "emailservice" / CONFIRMATION_TEMPLATE_FILENAME
    root_file = tmp_path / CONFIRMATION_TEMPLATE_FILENAME
    assert svc_file.is_file() and root_file.is_file()
    assert "{{ order.order_id }}" in svc_file.read_text()
    assert f"src/emailservice/{CONFIRMATION_TEMPLATE_FILENAME}" in written
