"""Structural tests for the R3-M4 frontend reference server (frontend_reference/main.go) — no docker.

Locks the server↔contract correspondence (every frontend_contract route is wired) + the lessons-folded
invariants (bind 0.0.0.0 not localhost; real 302 redirects for the cart/currency POSTs; the decisive
order-id render). The behavioral journey is validated live by the M4 gate runner; here we keep the Go
source honest to the contract (the vocabulary-drift rule). The image is proven to COMPILE by the Go
lane (build ok=True); this guards the contract surface without a multi-minute build.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from startd8.benchmark_matrix.fleet import frontend_contract as FC

pytestmark = pytest.mark.unit

_REF = Path(__file__).resolve().parent / "behavioral" / "fixtures" / "frontend_reference"
_MAIN = (_REF / "main.go").read_text()
_GOMOD = (_REF / "go.mod").read_text()

# how a contract (method, path) maps to its Go 1.22 ServeMux registration pattern
_MUX_PATTERN = {
    ("GET", "/"): 'GET /{$}',
    ("GET", "/product/{id}"): 'GET /product/',   # subtree → extracts the id (empty → 400)
    ("POST", "/setCurrency"): 'POST /setCurrency',
    ("POST", "/cart"): 'POST /cart',
    ("GET", "/cart"): 'GET /cart',
    ("POST", "/cart/checkout"): 'POST /cart/checkout',
}


def test_go_module_is_frontend():
    assert "module frontend" in _GOMOD


def test_every_contract_route_is_registered():
    for r in FC.JOURNEY_ROUTES:
        pattern = _MUX_PATTERN[(r.method, r.path)]
        assert f'mux.HandleFunc("{pattern}"' in _MAIN, f"route {r.method} {r.path} not wired ({pattern})"
    # the health route the gate's BOOT stage polls
    assert 'mux.HandleFunc("GET /_healthz"' in _MAIN


def test_binds_all_interfaces_not_localhost():
    # #31: a published container port reaches the external interface, not loopback.
    assert 'ListenAndServe("0.0.0.0:' in _MAIN
    assert 'ListenAndServe("localhost' not in _MAIN and 'ListenAndServe("127.0.0.1' not in _MAIN


def test_cart_and_currency_posts_do_a_real_302_redirect():
    # Leg 16 #21: a real http.Redirect(302), not an HX-Redirect-style header a browser form ignores.
    assert _MAIN.count("http.StatusFound") >= 2  # setCurrency + addToCart
    assert "http.Redirect(w, r" in _MAIN


def test_checkout_renders_the_real_order_id():
    # the DECISIVE gate signal (#5/#28): the confirmation page renders the real PlaceOrder order id.
    assert "PlaceOrder(" in _MAIN
    assert "GetOrder().GetOrderId()" in _MAIN
    assert 'id=\\"order-id\\"' in _MAIN or 'order-id' in _MAIN


def test_empty_product_id_is_400_and_malformed_payloads_are_422():
    assert "StatusBadRequest" in _MAIN          # GET /product/ (empty id) → 400
    assert "StatusUnprocessableEntity" in _MAIN  # malformed add/checkout → 422


def test_fans_out_to_checkout_and_threads_cookies():
    for client in ("ProductCatalogServiceClient", "CurrencyServiceClient", "CartServiceClient",
                   "ShippingServiceClient", "CheckoutServiceClient"):
        assert client in _MAIN
    assert FC.SESSION_COOKIE in _MAIN and FC.CURRENCY_COOKIE in _MAIN
