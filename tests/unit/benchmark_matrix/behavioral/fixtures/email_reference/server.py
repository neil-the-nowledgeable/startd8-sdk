"""CORRECT reference EmailService — the known-good oracle for the email behavioral suite.

A standalone Python gRPC server launched by the Python startup contract
(``cd src/emailservice && exec python3 server.py`` with ``$PORT`` in the env). It implements
``SendOrderConfirmation`` with the validation the suite asserts:

  - a well-formed email (has a local part, ``@``, and a dotted domain) AND a present order
    → renders the jinja2 ``confirmation.html`` template and returns ``Empty`` (OK).
  - a malformed / empty email → ``INVALID_ARGUMENT``.
  - a missing (empty) order   → ``INVALID_ARGUMENT``.

The gRPC stubs (``demo_pb2`` / ``demo_pb2_grpc``) and the jinja2 ``confirmation.html`` template are
co-located into this server's cwd by the harness (the broken/reference stager + the harness's
``provision_email_template``), mirroring the catalog Go fixture's co-located ``products.json``.
"""
from __future__ import annotations

import os
import re
from concurrent import futures

import grpc
import jinja2

import demo_pb2
import demo_pb2_grpc

# A pragmatic well-formed-email check (local@domain.tld). Not RFC-complete — just enough that the
# suite's INVALID_EMAIL ("not-an-email") and EMPTY_EMAIL ("") are rejected and VALID_EMAIL accepted.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_TEMPLATE_FILE = "confirmation.html"


class EmailService(demo_pb2_grpc.EmailServiceServicer):
    def __init__(self) -> None:
        with open(_TEMPLATE_FILE, encoding="utf-8") as fh:
            self._template = jinja2.Template(fh.read())

    def SendOrderConfirmation(self, request, context):
        if not _EMAIL_RE.match(request.email or ""):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"invalid email: {request.email!r}")
        # proto3 message presence: an unset order field is the default (empty order_id).
        if not request.HasField("order") or not request.order.order_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "missing order")
        # Render the confirmation body (a side effect proving the template is usable); the rendered
        # text is not returned over the wire — the RPC contract is Empty.
        self._template.render(order=request.order, email=request.email)
        return demo_pb2.Empty()


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_EmailServiceServicer_to_server(EmailService(), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    main()
