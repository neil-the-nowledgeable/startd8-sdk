"""startd8.navigator — NODE-SCHEMA Node home in the SDK (Phase 1).

Grammar cite: ``dev-os/NODE-SCHEMA.md``. Field-compatible with ContextCore's
``navigator/models.py`` (copy port; shared package deferred). Does not import
ContextCore.
"""

from __future__ import annotations

from .models import (
    NODE_SHARED_FIELDS,
    Node,
    NodeEvidence,
    NodeStatus,
    StatusFacet,
    default_confidence,
    derive_status,
)
from .view_definition import (
    BASE_NAVIG8R_DEFINITION,
    ResolvedDefinition,
    ViewDefinition,
    resolve,
    to_render_profile,
)

__all__ = [
    "NODE_SHARED_FIELDS",
    "Node",
    "NodeEvidence",
    "NodeStatus",
    "StatusFacet",
    "default_confidence",
    "derive_status",
    "BASE_NAVIG8R_DEFINITION",
    "ResolvedDefinition",
    "ViewDefinition",
    "resolve",
    "to_render_profile",
]
