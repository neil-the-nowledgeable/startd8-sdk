"""Deterministic frontend generation (no-LLM).

Generates the *mechanical* frontend artifacts an LLM keeps inventing wrong — starting
with the Prisma→Zod/TS schema renderer — so they are never generated wrong (prevention
by construction). See `docs/design/deterministic-frontend/`.

Inc 1 (this commit): the field model + scalar/optionality/enum/list mapping
(`schema_renderer`). Later increments add the convention layer, file assembly, the
symmetry + fidelity gates, project-convention detection, and the CLI / pipeline hook.
"""

from __future__ import annotations

from .conventions import (
    DEFAULT_CONVENTIONS,
    FieldConventions,
    ProjectConventions,
    detect_project_conventions,
)
from .drift import (
    DriftResult,
    check_drift,
    embedded_schema_sha,
    embedded_source_file,
    is_owned_generated_file,
    owned_file_in_sync,
)
from .gates import assert_symmetric, verify_render_fidelity
from .telemetry import record_drift_check, record_render
from .skeleton import (
    SkeletonArtifact,
    SkeletonPlan,
    plan_frontend_skeleton,
    render_barrel,
    render_css_module_stub,
)
from .schema_renderer import (
    SCALAR_MAP,
    RenderResult,
    UnrenderableField,
    composite_type_names,
    field_completeness_issues,
    model_field_sets,
    render_field,
    render_field_base,
    render_zod_schema,
    schema_sha256,
    unrenderable_fields,
)

__all__ = [
    "DEFAULT_CONVENTIONS",
    "FieldConventions",
    "ProjectConventions",
    "RenderResult",
    "SCALAR_MAP",
    "UnrenderableField",
    "DriftResult",
    "SkeletonArtifact",
    "SkeletonPlan",
    "assert_symmetric",
    "check_drift",
    "composite_type_names",
    "detect_project_conventions",
    "embedded_schema_sha",
    "embedded_source_file",
    "field_completeness_issues",
    "is_owned_generated_file",
    "owned_file_in_sync",
    "plan_frontend_skeleton",
    "record_drift_check",
    "record_render",
    "render_barrel",
    "render_css_module_stub",
    "model_field_sets",
    "render_field",
    "render_field_base",
    "render_zod_schema",
    "schema_sha256",
    "unrenderable_fields",
    "verify_render_fidelity",
]
