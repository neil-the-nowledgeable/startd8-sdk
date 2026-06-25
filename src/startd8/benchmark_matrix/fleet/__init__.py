"""Round-3 fleet substrate: per-service container image build + compose-fleet generation.

M0 ships ``containerize.build_service_image`` + ``boot_and_probe`` + per-language Dockerfile templates
so a model-generated service workdir becomes a buildable/runnable container image, REUSING the
behavioral harness's offline-dep provisioning. M1 adds ``services`` (the canonical OB topology) +
``compose`` (the N-service compose-fleet generator). See ``docs/design/round3-full-app/PLAN.md``
(M0/M1) and ``CONTAINERIZATION_SCOPING.md`` / ``COMPOSE_FLEET_PROTOTYPE.md``.
"""
from __future__ import annotations

from .compose import generate_compose_dict, generate_compose_yaml
from .containerize import (
    BootProbeResult,
    ImageBuildResult,
    ImageSpec,
    boot_and_probe,
    build_service_image,
    docker_available,
)
from .services import (
    ServiceSpec,
    contestant_services,
    default_fleet,
    get_service,
    topo_order,
)

__all__ = [
    "BootProbeResult",
    "ImageBuildResult",
    "ImageSpec",
    "ServiceSpec",
    "boot_and_probe",
    "build_service_image",
    "contestant_services",
    "default_fleet",
    "docker_available",
    "generate_compose_dict",
    "generate_compose_yaml",
    "get_service",
    "topo_order",
]
