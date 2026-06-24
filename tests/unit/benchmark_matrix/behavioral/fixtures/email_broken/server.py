"""DELIBERATELY-BROKEN EmailService — proves the email suite DISCRIMINATES.

Identical to the reference except it SKIPS email validation: it accepts ANY email (including the
suite's malformed ``"not-an-email"``) and returns ``Empty`` (OK). It still rejects a missing order,
so exactly ONE case — ``send_invalid_email_rejected`` — must fail, attributing the defect precisely.
"""
from __future__ import annotations

import os
from concurrent import futures

import grpc
import jinja2

import demo_pb2
import demo_pb2_grpc

_TEMPLATE_FILE = "confirmation.html"


class EmailService(demo_pb2_grpc.EmailServiceServicer):
    def __init__(self) -> None:
        with open(_TEMPLATE_FILE, encoding="utf-8") as fh:
            self._template = jinja2.Template(fh.read())

    def SendOrderConfirmation(self, request, context):
        # BUG: no email validation — a malformed email is accepted instead of INVALID_ARGUMENT.
        if not request.HasField("order") or not request.order.order_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "missing order")
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
