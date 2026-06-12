"""Composite-view generator (class-3 determinism — relational/multi-entity views).

The third deterministic-generation class: dashboards, status boards, and polymorphic workspaces —
the views that turn single-entity CRUD into a usable journey. Pure relational logic (joins, counts,
group-by, polymorphic resolution with dangling-ref flagging), derived from the contract + a declared
``views.yaml`` over a closed archetype vocabulary. Owned, $0 LLM, drift-checked, build-gated;
registered on the shared ``deterministic_providers`` entry-point group. Closes the ROADMAP D1 gap.
"""

from __future__ import annotations

from .drift import is_owned_view_file, views_in_sync
from .manifest import ViewSpec, parse_views
from .provider import CompositeViewProvider
from .renderers import (
    compute_binding_names,
    render_control_fragment,
    render_import_result_template,
    render_view_empty_fragment,
    render_view_outcome_fragment,
    render_view_prose_fragment,
    render_views,
)
from .view_prose import ViewProse, parse_view_prose

__all__ = [
    "ViewSpec",
    "parse_views",
    "render_views",
    "compute_binding_names",
    "views_in_sync",
    "is_owned_view_file",
    "CompositeViewProvider",
    "ViewProse",
    "parse_view_prose",
    "render_view_prose_fragment",
    "render_view_empty_fragment",
    "render_view_outcome_fragment",
    "render_import_result_template",
    "render_control_fragment",
]
