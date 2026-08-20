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
    NODE_SCHEMA_DEFINITION,
    ResolvedDefinition,
    ViewDefinition,
    activation_severity_from_cockpit_attention,
    attention_counts_from_navig8r_statuses,
    cockpit_attention_colors,
    cockpit_statuses_from_node_state,
    cross_surface_consumption_advisories,
    definition_diff,
    load_definition,
    resolve,
    resolve_external,
    resolve_bindings,
    resolve_surface_link_href,
    rollup_cockpit_attentions,
    rollup_navig8r_statuses_to_attention,
    to_render_profile,
    validate_definitions,
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
    "NODE_SCHEMA_DEFINITION",
    "ResolvedDefinition",
    "ViewDefinition",
    "activation_severity_from_cockpit_attention",
    "attention_counts_from_navig8r_statuses",
    "cockpit_attention_colors",
    "cockpit_statuses_from_node_state",
    "cross_surface_consumption_advisories",
    "definition_diff",
    "load_definition",
    "resolve",
    "resolve_external",
    "resolve_bindings",
    "resolve_surface_link_href",
    "rollup_cockpit_attentions",
    "rollup_navig8r_statuses_to_attention",
    "to_render_profile",
    "validate_definitions",
]
