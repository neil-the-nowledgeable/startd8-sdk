"""Round-3 fleet service inventory (M1) — the canonical Online Boutique topology the compose-fleet
generator (``fleet.compose``) projects into a runnable docker-compose.

This is the single authoritative encoding of JOURNEY_DESIGN §3's service table + dependency fan-out:
each service's wire ports, the ``*_SERVICE_ADDR`` env peers consume it by, and the dep edges. Two
faithfulness traps are encoded HERE (not in the generator) so they cannot be silently dropped:

  1. **emailservice port asymmetry** — the canonical k8s containerPort is 8080 but peers dial it on
     5000 (``EMAIL_SERVICE_ADDR=emailservice:5000``; the k8s Service remaps 5000→8080). Every service
     carries an explicit ``(listen_port, dial_port)`` pair rather than assuming they're equal — email
     is the canonical proof they aren't. All other services have listen == dial.
  2. **redis-cart infra sidecar** — cartservice is stateful and dials ``REDIS_ADDR=redis-cart:6379``.
     redis-cart is a NON-contestant infra dependency (a stock ``redis`` image, not a built service),
     flagged ``is_infra=True`` so scoring never treats it as a model service.

v1 fleet = 8 contestant backends (adservice/Java is deferred — leaf, off the checkout journey) + the
redis-cart infra sidecar. frontend is the M4 BONUS lane, not a backend, so it is not in this inventory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ServiceSpec:
    """One node of the fleet topology — a contestant backend or an infra sidecar.

    listen_port: the port the process binds ($PORT — the OB convention every reference server honors).
    dial_port:   the port peers reach it on via service-DNS (``name:dial_port``). Equals listen_port
                 for every service EXCEPT emailservice (5000 dial vs 8080 listen — the k8s Service
                 remap). The compose generator injects ``PORT=dial_port`` so the process listens where
                 peers dial it, collapsing the k8s Service remap into a direct listen (kind/k8s parity
                 — OQ-C7 — would instead reproduce the Service remap).
    addr_env:    the ``*_SERVICE_ADDR`` env name by which peers consume this service.
    deps:        names of the services this service dials (its ``*_SERVICE_ADDR`` fan-out).
    is_infra:    True for non-contestant infra (redis-cart) — built from ``image``, never scored.
    image:       a stock image ref for infra; None => the service is built from its generated workdir.
    """

    name: str
    language: Optional[str]
    listen_port: int
    dial_port: int
    addr_env: str
    deps: tuple[str, ...] = field(default_factory=tuple)
    is_infra: bool = False
    image: Optional[str] = None

    @property
    def port_asymmetric(self) -> bool:
        """True when peers dial a different port than the process listens on (emailservice)."""
        return self.listen_port != self.dial_port


# --- The canonical OB v1 inventory (JOURNEY_DESIGN §3) --------------------------------------------
# Ports are the real upstream values from release/kubernetes-manifests.yaml.

_SERVICES: tuple[ServiceSpec, ...] = (
    ServiceSpec("productcatalogservice", "go", 3550, 3550, "PRODUCT_CATALOG_SERVICE_ADDR"),
    ServiceSpec("shippingservice", "go", 50051, 50051, "SHIPPING_SERVICE_ADDR"),
    ServiceSpec("currencyservice", "node", 7000, 7000, "CURRENCY_SERVICE_ADDR"),
    ServiceSpec("paymentservice", "node", 50051, 50051, "PAYMENT_SERVICE_ADDR"),
    # emailservice: THE port-asymmetry trap — listens 8080, dialed 5000.
    ServiceSpec("emailservice", "python", 8080, 5000, "EMAIL_SERVICE_ADDR"),
    # cartservice: stateful — dials the redis-cart infra sidecar.
    ServiceSpec("cartservice", "csharp", 7070, 7070, "CART_SERVICE_ADDR", deps=("redis-cart",)),
    ServiceSpec("recommendationservice", "python", 8080, 8080, "RECOMMENDATION_SERVICE_ADDR",
                deps=("productcatalogservice",)),
    # checkoutservice: the 6-dep PlaceOrder fan-out (the journey's deepest node).
    ServiceSpec("checkoutservice", "go", 5050, 5050, "CHECKOUT_SERVICE_ADDR",
                deps=("productcatalogservice", "shippingservice", "paymentservice",
                      "emailservice", "currencyservice", "cartservice")),
    # redis-cart: NON-contestant infra sidecar (stock redis image), cartservice's backing store.
    ServiceSpec("redis-cart", None, 6379, 6379, "REDIS_ADDR", is_infra=True, image="redis:alpine"),
)

_BY_NAME = {s.name: s for s in _SERVICES}


def default_fleet() -> tuple[ServiceSpec, ...]:
    """The canonical v1 fleet inventory (8 backends + redis-cart). Order is dependency-friendly
    (leaves first, checkoutservice last) but callers must not rely on it for ordering — use
    ``topo_order``."""
    return _SERVICES


def get_service(name: str) -> ServiceSpec:
    """Look up a spec by service name (raises KeyError for an unknown service)."""
    return _BY_NAME[name]


def contestant_services(fleet: tuple[ServiceSpec, ...] = _SERVICES) -> tuple[ServiceSpec, ...]:
    """The scored backends (excludes infra sidecars like redis-cart)."""
    return tuple(s for s in fleet if not s.is_infra)


def topo_order(fleet: tuple[ServiceSpec, ...] = _SERVICES) -> tuple[ServiceSpec, ...]:
    """Dependency-ordered services (a depended-on service precedes its dependents) for readiness
    wiring / bring-up. Raises ValueError on an unknown dep or a dependency cycle (the OB graph is a
    DAG; a cycle means the inventory is corrupt — never silently proceed)."""
    by_name = {s.name: s for s in fleet}
    ordered: list[ServiceSpec] = []
    placed: set[str] = set()
    visiting: set[str] = set()

    def visit(spec: ServiceSpec) -> None:
        if spec.name in placed:
            return
        if spec.name in visiting:
            raise ValueError(f"dependency cycle through {spec.name!r}")
        visiting.add(spec.name)
        for dep in spec.deps:
            if dep not in by_name:
                raise ValueError(f"{spec.name!r} dials unknown service {dep!r}")
            visit(by_name[dep])
        visiting.discard(spec.name)
        placed.add(spec.name)
        ordered.append(spec)

    for spec in fleet:
        visit(spec)
    return tuple(ordered)
