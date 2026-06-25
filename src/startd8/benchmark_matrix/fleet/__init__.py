"""Round-3 fleet substrate: per-service container image build + (later) compose-fleet generation.

M0 ships ``containerize.build_service_image`` + ``boot_and_probe`` + per-language Dockerfile templates
so a model-generated service workdir becomes a buildable/runnable container image, REUSING the
behavioral harness's offline-dep provisioning. See ``docs/design/round3-full-app/PLAN.md`` (M0) and
``CONTAINERIZATION_SCOPING.md`` (§5/§7b).
"""
from __future__ import annotations

from .containerize import (
    BootProbeResult,
    ImageBuildResult,
    ImageSpec,
    boot_and_probe,
    build_service_image,
    docker_available,
)

__all__ = [
    "BootProbeResult",
    "ImageBuildResult",
    "ImageSpec",
    "boot_and_probe",
    "build_service_image",
    "docker_available",
]
