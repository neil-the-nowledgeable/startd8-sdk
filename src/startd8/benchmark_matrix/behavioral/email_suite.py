"""emailservice behavioral ground-truth suite (Track-2 expansion — Empty-returning LEAF).

EmailService is a **leaf** service (no gRPC peers). Its single RPC returns ``Empty``::

    SendOrderConfirmation(SendOrderConfirmationRequest{email, OrderResult order}) -> Empty

Because the response is ``Empty``, correctness is NOT response-observable — there is no field to
assert. The discriminating signal is therefore the gRPC **status**: a well-formed request must be
ACCEPTED (``OK``) and malformed requests must be REJECTED (``INVALID_ARGUMENT``). This mirrors how
the checkout suite verifies its email step (the order's confirmation email is observed only as an
accepted/rejected outcome, not a payload). A naive stub that returns ``OK`` for *everything* (never
validating) is exactly what the reject cases catch.

SDK-authored, language-agnostic over the gRPC wire: it talks to a live EmailService on
``127.0.0.1:<port>`` regardless of what language the server was generated in, and asserts the
behavior of three equal-weight cases:

  - valid email + valid OrderResult        → ``OK`` (the RPC returns Empty without error).
  - empty / malformed email                → rejected with ``INVALID_ARGUMENT``.
  - missing (empty) order                  → rejected with ``INVALID_ARGUMENT``.

``coverage`` ∈ [0,1] = passing cases / total (equal weight per case); provenance carries the suite
version + per-case results. Reuses :class:`RpcResult` / :class:`SuiteResult` from ``charge_suite``.
"""
from __future__ import annotations

from typing import Optional

import grpc

from . import demo_pb2, demo_pb2_grpc
from .charge_suite import RpcResult, SuiteResult

SUITE_VERSION = "email-suite/1"

# ---- Ground truth: a single well-formed order the reference service must ACCEPT -----------------
# A deterministic, fully-populated OrderResult: a confirmable email address plus an order that has
# an id, a tracking id, a shipping cost, an address, and one line item. This is the known-good input
# the oracle renders a confirmation for; the reject cases perturb exactly one required field.
VALID_EMAIL = "someone@example.com"
INVALID_EMAIL = "not-an-email"       # no '@' / domain → a validating service must reject it
EMPTY_EMAIL = ""                     # empty string → reject

# Harness-owned jinja2 confirmation template. EmailService is STATELESS over the wire, but the OB
# convention renders the confirmation body from a local ``confirmation.html`` jinja2 template. The
# harness owns it (provisioned into the server's workdir by ``execute.provision_email_template``) so
# a reference server can render without inventing a template — the analogue of catalog's products.json
# (a harness-owned local asset), even though it is not asserted over the wire (Empty response).
CONFIRMATION_TEMPLATE_FILENAME = "confirmation.html"
CONFIRMATION_TEMPLATE = """\
<html><body>
<h1>Your order confirmation</h1>
<p>Order ID: {{ order.order_id }}</p>
<p>Tracking: {{ order.shipping_tracking_id }}</p>
<ul>
{% for item in order.items %}
  <li>{{ item.item.product_id }} x{{ item.item.quantity }}</li>
{% endfor %}
</ul>
</body></html>
"""


def _money(units: int = 10, nanos: int = 0, code: str = "USD") -> demo_pb2.Money:
    return demo_pb2.Money(currency_code=code, units=units, nanos=nanos)


def _valid_order() -> demo_pb2.OrderResult:
    """The ground-truth OrderResult — fully populated so a correct service has nothing to reject."""
    return demo_pb2.OrderResult(
        order_id="ORDER-0001",
        shipping_tracking_id="TRACK-0001",
        shipping_cost=_money(5, 0),
        shipping_address=demo_pb2.Address(
            street_address="1600 Amphitheatre Pkwy", city="Mountain View",
            state="CA", country="USA", zip_code=94043),
        items=[demo_pb2.OrderItem(
            item=demo_pb2.CartItem(product_id="OLJCESPC7Z", quantity=1),
            cost=_money(19, 990_000_000))],
    )


def _send(stub, *, email: str, order: Optional[demo_pb2.OrderResult],
          timeout: float = 5.0):
    """Issue a SendOrderConfirmation. ``order=None`` omits the order field entirely (empty order)."""
    req = demo_pb2.SendOrderConfirmationRequest(email=email)
    if order is not None:
        req.order.CopyFrom(order)
    return stub.SendOrderConfirmation(req, timeout=timeout)


def run_email_suite(port: int, *, host: str = "127.0.0.1",
                    connect_timeout: float = 5.0) -> SuiteResult:
    """Connect to a live EmailService and run the SendOrderConfirmation ground-truth checks (the
    client window). Same SuiteResult/coverage shape as the charge/catalog leaf suites — invoked by
    ``run_service_sandboxed`` as ``client(port)`` on the plain leaf path.

    Verifying an Empty-returning RPC: there is no payload to assert, so each case asserts the gRPC
    *status* — the valid request must return Empty under ``OK`` (no ``RpcError``), and each malformed
    request must raise ``RpcError`` with ``code() == INVALID_ARGUMENT``."""
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001 — failure to connect is an env outcome (degrade upstream)
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite
    try:
        stub = demo_pb2_grpc.EmailServiceStub(channel)

        # 1) Valid email + valid order → ACCEPTED (Empty, no error).
        try:
            _send(stub, email=VALID_EMAIL, order=_valid_order())
            suite.results.append(RpcResult(
                "send_valid_request_accepted", True, "returned Empty (OK) as expected"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult(
                "send_valid_request_accepted", False, f"rejected a valid request: {e.code()}"))

        # 2) Malformed email → must be REJECTED with INVALID_ARGUMENT (not silently OK).
        try:
            _send(stub, email=INVALID_EMAIL, order=_valid_order())
            suite.results.append(RpcResult(
                "send_invalid_email_rejected", False,
                f"accepted a malformed email {INVALID_EMAIL!r}"))
        except grpc.RpcError as e:
            ok = e.code() == grpc.StatusCode.INVALID_ARGUMENT
            suite.results.append(RpcResult(
                "send_invalid_email_rejected", ok,
                "INVALID_ARGUMENT" if ok else f"rejected but wrong code: {e.code()}"))

        # 3) Missing (empty) order → must be REJECTED with INVALID_ARGUMENT.
        try:
            _send(stub, email=VALID_EMAIL, order=None)
            suite.results.append(RpcResult(
                "send_missing_order_rejected", False, "accepted a request with no order"))
        except grpc.RpcError as e:
            ok = e.code() == grpc.StatusCode.INVALID_ARGUMENT
            suite.results.append(RpcResult(
                "send_missing_order_rejected", ok,
                "INVALID_ARGUMENT" if ok else f"rejected but wrong code: {e.code()}"))
    finally:
        channel.close()
    return suite
