"""Round-3 N-service compose-fleet generator (M1).

Projects the canonical OB service inventory (``fleet.services``) into a docker-compose that stands a
finalist's full backend fleet up together — egress-denied, peers wired by service-DNS — generalizing
the validated 2-service ``compose-prototype`` (COMPOSE_FLEET_PROTOTYPE.md) to all 8 v1 backends.

The substrate mechanism (REUSED from the prototype, proven on macOS Docker):
  * an ``internal: true`` ``fleet`` network → network-layer egress-deny (no route out) + service-DNS;
  * a normal ``edge`` bridge carrying ONLY host↔ingress traffic (so an optional ingress service is
    host-reachable while pure backends stay internal and unreachable from the host);
  * each dep edge injected as ``{ADDR_ENV}: {peer}:{dial_port}`` env (the OB ``*_SERVICE_ADDR``
    convention) so a consumer dials its peer by compose service-DNS;
  * ``depends_on`` for dependency-ordered bring-up.

NET-NEW at N (vs the prototype): the per-service env fan-out from the inventory, the redis-cart infra
sidecar, the emailservice listen≠dial port remap, and dependency-ordered wiring across all services.
"""
from __future__ import annotations

from typing import Optional

import yaml

from .services import ServiceSpec, default_fleet, get_service, topo_order

FLEET_NETWORK = "fleet"
EDGE_NETWORK = "edge"


def _service_block(
    spec: ServiceSpec,
    *,
    image_namespace: str,
    is_ingress: bool,
    host_port: Optional[int],
) -> dict:
    """Render one compose service entry from its inventory spec."""
    block: dict = {}

    # Infra (redis-cart) runs a stock image; contestant backends are built from the M0 image tag
    # (r3/<service>:<language>) the build_service_image cascade produces.
    if spec.image is not None:
        block["image"] = spec.image
    else:
        block["image"] = f"{image_namespace}/{spec.name}:{spec.language}"

    # PORT is the port peers DIAL this service on (dial_port). For every service except emailservice
    # that equals the listen port; for emailservice (dial 5000 ≠ listen 8080) we inject PORT=5000 so
    # the process listens where peers dial it — the compose collapse of the k8s Service remap. redis
    # ignores PORT (fixed 6379), so setting it is a harmless no-op.
    env: dict[str, str] = {}
    if not spec.is_infra:
        env["PORT"] = str(spec.dial_port)

    # Dependency fan-out: each peer this service dials becomes {PEER_ADDR_ENV}: peer:dial_port.
    for dep_name in spec.deps:
        dep = get_service(dep_name)
        env[dep.addr_env] = f"{dep.name}:{dep.dial_port}"

    if env:
        block["environment"] = env

    if spec.deps:
        block["depends_on"] = list(spec.deps)

    # Networking: every service is on the internal fleet network (egress-deny + service-DNS). An
    # optional ingress service ALSO joins edge and publishes a host port so a host-side driver can
    # reach the SUT while the inter-service dials are still forced through the internal network.
    networks = [FLEET_NETWORK]
    if is_ingress:
        networks.append(EDGE_NETWORK)
        if host_port is not None:
            block["ports"] = [f"127.0.0.1:{host_port}:{spec.dial_port}"]
    block["networks"] = networks

    return block


def generate_compose_dict(
    fleet: tuple[ServiceSpec, ...] = default_fleet(),
    *,
    image_namespace: str = "r3",
    ingress: Optional[str] = None,
    host_port: Optional[int] = None,
) -> dict:
    """Build the docker-compose mapping for ``fleet``.

    ingress: name of a service to additionally expose on the ``edge`` network + a published host port
      (the host-reachable entry, e.g. checkoutservice for an Adapter-B driver). None => a pure-backend
      fleet with NO host ingress (validation probes from inside a container, like the prototype).
    host_port: the loopback host port to publish the ingress on (required when ingress is set).
    """
    if ingress is not None:
        get_service(ingress)  # validate the name (raises KeyError otherwise)
        if host_port is None:
            raise ValueError("host_port is required when an ingress service is specified")

    # Emit services in dependency order (depended-on first) — cosmetic for compose (which resolves
    # depends_on itself) but it surfaces a corrupt/cyclic inventory early and reads top-down.
    services = {
        spec.name: _service_block(
            spec,
            image_namespace=image_namespace,
            is_ingress=(spec.name == ingress),
            host_port=host_port if spec.name == ingress else None,
        )
        for spec in topo_order(fleet)
    }

    compose: dict = {
        "services": services,
        "networks": {
            # internal: true => Docker creates NO route/gateway out. Peers reach each other by
            # service-DNS but CANNOT reach any external host (network-layer egress-deny).
            FLEET_NETWORK: {"internal": True},
        },
    }
    # Only declare the edge bridge when something uses it (an ingress) — a pure-backend fleet has none.
    if ingress is not None:
        compose["networks"][EDGE_NETWORK] = {"driver": "bridge"}

    return compose


def generate_compose_yaml(
    fleet: tuple[ServiceSpec, ...] = default_fleet(),
    *,
    image_namespace: str = "r3",
    ingress: Optional[str] = None,
    host_port: Optional[int] = None,
) -> str:
    """``generate_compose_dict`` serialized to a docker-compose YAML string."""
    compose = generate_compose_dict(
        fleet, image_namespace=image_namespace, ingress=ingress, host_port=host_port
    )
    return yaml.safe_dump(compose, sort_keys=False, default_flow_style=False)
