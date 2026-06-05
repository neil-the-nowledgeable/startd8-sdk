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
from .renderers import render_views

__all__ = [
    "ViewSpec",
    "parse_views",
    "render_views",
    "views_in_sync",
    "is_owned_view_file",
    "CompositeViewProvider",
]
