# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Advisory registry of known agent surfaces (FR-22 — open, not a closed enum).

Unknown ``surface_id`` values are allowed at enqueue as long as the surface
conforms to VASI (``docs/design/cursor-workflow-loop/VENDOR_AGENT_SURFACE_INTERFACE.md``).
Registering a new surface never requires an SDK release.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class KnownSurface:
    surface_id: str
    display_name: str
    ownership: str
    status: str


KNOWN_SURFACES: List[KnownSurface] = [
    KnownSurface(
        surface_id="cursor",
        display_name="Cursor",
        ownership="startd8-sdk (reference adapter, shipped)",
        status="shipped",
    ),
    KnownSurface(
        surface_id="codex",
        display_name="Codex",
        ownership="vendor / integrator (implement VASI downstream)",
        status="external",
    ),
    KnownSurface(
        surface_id="antigravity",
        display_name="Antigravity",
        ownership="vendor / integrator (implement VASI downstream)",
        status="external",
    ),
    KnownSurface(
        surface_id="claude-code",
        display_name="Claude Code",
        # A2 (code-asks 2026-08-04): the dev-os VJO in-agent adapter shipped + armed
        # 2026-08-05 (vjo/bin/drain-claude.py: selector + single-flight + reviewer gate +
        # fleet emit). Registered here so `wloop list-surfaces` recognizes it and enqueue
        # accepts `surface_id=claude-code` without inline surface_conformance.
        ownership="dev-os (VJO in-agent adapter; drain-claude.py)",
        status="shipped",
    ),
]


def list_surfaces() -> List[KnownSurface]:
    return list(KNOWN_SURFACES)


def is_known_surface(surface_id: str) -> bool:
    return any(s.surface_id == surface_id for s in KNOWN_SURFACES)
