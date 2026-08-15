"""Wireframe Visual Preview (FR-WV) — the end-user-facing HTML sibling of the terminal wireframe.

Sibling of ``kickoff_view`` (same self-contained, escape-first, $0-re-render philosophy). This package
renders the wireframe PLAN as a browsable lo-fi preview: an inverted-pyramid summary that drills into
per-page/form/list mockups (spec: docs/design/wireframe/WIREFRAME_VISUAL_REQUIREMENTS.md).

M-WV0 (this module): ``compose(plan) -> view-model`` + the form-field ``detail`` parser. The HTML shell
(M-WV1), outline renderer (M-WV2), and mockup renderer (M-WV3) build on this pure view-model.
"""
from __future__ import annotations

from .compose import compose, parse_form_detail
from .node_lenses import (  # REQ-04 FR-4: the shared lens transform's public surface
    GAP_STATUSES,
    HONEST_SKIP_ROUTES,
    apply_node_lenses,
    apply_section_lenses,
    has_jargon,
    project_nodes,
)
from .view import EXPECTED_SCHEMA_VERSION, render_html, render_to_file, view_model_json

__all__ = [
    "compose",
    "parse_form_detail",
    "render_html",
    "render_to_file",
    "view_model_json",
    "EXPECTED_SCHEMA_VERSION",
    # REQ-04: shared audience × fluency lens transform
    "apply_node_lenses",
    "apply_section_lenses",
    "project_nodes",
    "has_jargon",
    "GAP_STATUSES",
    "HONEST_SKIP_ROUTES",
]
