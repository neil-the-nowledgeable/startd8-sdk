"""Unit tests for the R3-M1 compose-fleet generator (fleet.services + fleet.compose) — NO docker.

Exercises the inventory (canonical OB topology + dependency fan-out), the two encoded faithfulness
traps (emailservice listen≠dial remap; redis-cart infra sidecar), dependency ordering, and the
compose projection (internal egress-deny network, service-DNS dep wiring, ingress edge exposure).
The live bring-up/egress-deny/teardown is a separate gated path (validate_m1 / a gated integration).
"""
from __future__ import annotations

import pytest
import yaml

from startd8.benchmark_matrix.fleet import compose as C
from startd8.benchmark_matrix.fleet import services as S

pytestmark = pytest.mark.unit


# --- inventory ------------------------------------------------------------------------------------

def test_default_fleet_is_8_backends_plus_redis():
    fleet = S.default_fleet()
    assert len(fleet) == 9  # 8 contestant backends + redis-cart
    assert len(S.contestant_services()) == 8  # redis-cart excluded from scored services
    # adservice (Java) is deferred; frontend is the M4 bonus lane — neither is in the backend fleet.
    names = {s.name for s in fleet}
    assert "adservice" not in names and "frontend" not in names
    assert "redis-cart" in names


def test_redis_is_infra_stock_image():
    redis = S.get_service("redis-cart")
    assert redis.is_infra and redis.image == "redis:alpine" and redis.language is None


def test_email_port_asymmetry_encoded():
    """THE trap: emailservice listens 8080 but is dialed 5000 (the k8s Service remap)."""
    email = S.get_service("emailservice")
    assert email.listen_port == 8080 and email.dial_port == 5000
    assert email.port_asymmetric
    # every other service has listen == dial
    assert all(not s.port_asymmetric for s in S.default_fleet() if s.name != "emailservice")


def test_checkout_six_dep_fanout():
    checkout = S.get_service("checkoutservice")
    assert set(checkout.deps) == {
        "productcatalogservice", "shippingservice", "paymentservice",
        "emailservice", "currencyservice", "cartservice",
    }


def test_topo_order_places_deps_before_dependents():
    order = [s.name for s in S.topo_order()]
    # checkoutservice depends on 6 peers → must come after all of them
    ci = order.index("checkoutservice")
    for dep in S.get_service("checkoutservice").deps:
        assert order.index(dep) < ci
    # recommendationservice after productcatalog; cartservice after redis-cart
    assert order.index("productcatalogservice") < order.index("recommendationservice")
    assert order.index("redis-cart") < order.index("cartservice")


def test_topo_order_rejects_cycle_and_unknown_dep():
    cyclic = (
        S.ServiceSpec("a", "go", 1, 1, "A_ADDR", deps=("b",)),
        S.ServiceSpec("b", "go", 1, 1, "B_ADDR", deps=("a",)),
    )
    with pytest.raises(ValueError, match="cycle"):
        S.topo_order(cyclic)
    bad = (S.ServiceSpec("a", "go", 1, 1, "A_ADDR", deps=("ghost",)),)
    with pytest.raises(ValueError, match="unknown service"):
        S.topo_order(bad)


# --- compose projection ---------------------------------------------------------------------------

def test_fleet_network_is_internal_egress_deny():
    compose = C.generate_compose_dict()
    assert compose["networks"]["fleet"]["internal"] is True
    # pure-backend fleet (no ingress) declares no edge network
    assert "edge" not in compose["networks"]
    # every service sits on the internal fleet network
    for name, block in compose["services"].items():
        assert "fleet" in block["networks"]


def test_dep_edges_wired_as_service_dns():
    svcs = C.generate_compose_dict()["services"]
    # checkoutservice gets all six *_SERVICE_ADDR envs pointing at peer:dial_port
    env = svcs["checkoutservice"]["environment"]
    assert env["PRODUCT_CATALOG_SERVICE_ADDR"] == "productcatalogservice:3550"
    assert env["PAYMENT_SERVICE_ADDR"] == "paymentservice:50051"
    # THE trap surfaces here: checkout dials emailservice on 5000, not its listen port 8080
    assert env["EMAIL_SERVICE_ADDR"] == "emailservice:5000"
    assert set(svcs["checkoutservice"]["depends_on"]) == set(S.get_service("checkoutservice").deps)


def test_email_listens_on_dial_port():
    """The container must listen where peers dial it (PORT=dial_port=5000), or checkout's email step
    silently misses."""
    email = C.generate_compose_dict()["services"]["emailservice"]
    assert email["environment"]["PORT"] == "5000"


def test_cart_redis_sidecar_wired():
    svcs = C.generate_compose_dict()["services"]
    assert svcs["cartservice"]["environment"]["REDIS_ADDR"] == "redis-cart:6379"
    assert "redis-cart" in svcs["cartservice"]["depends_on"]
    redis = svcs["redis-cart"]
    assert redis["image"] == "redis:alpine"
    assert "environment" not in redis  # infra: no PORT/addr injection


def test_backend_image_tag_matches_m0():
    svcs = C.generate_compose_dict(image_namespace="r3")["services"]
    assert svcs["productcatalogservice"]["image"] == "r3/productcatalogservice:go"
    assert svcs["cartservice"]["image"] == "r3/cartservice:csharp"


def test_ingress_exposes_edge_and_host_port():
    compose = C.generate_compose_dict(ingress="checkoutservice", host_port=18090)
    assert compose["networks"]["edge"]["driver"] == "bridge"
    co = compose["services"]["checkoutservice"]
    assert "edge" in co["networks"] and "fleet" in co["networks"]
    assert co["ports"] == ["127.0.0.1:18090:5050"]
    # a pure backend stays internal-only (no ports, no edge)
    assert "ports" not in compose["services"]["paymentservice"]
    assert compose["services"]["paymentservice"]["networks"] == ["fleet"]


def test_ingress_requires_host_port():
    with pytest.raises(ValueError, match="host_port"):
        C.generate_compose_dict(ingress="checkoutservice")


def test_yaml_round_trips():
    text = C.generate_compose_yaml()
    parsed = yaml.safe_load(text)
    assert parsed["networks"]["fleet"]["internal"] is True
    assert set(parsed["services"]) == {s.name for s in S.default_fleet()}
