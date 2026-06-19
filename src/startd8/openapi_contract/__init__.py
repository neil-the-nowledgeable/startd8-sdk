"""Shared OpenAPI contract utilities — schema resolution for harness + codegen."""

from __future__ import annotations

from .schema_resolve import (
    ResourceChoice,
    resolve_schema,
    select_crud_resource,
    synthesize_body,
)

__all__ = [
    "ResourceChoice",
    "resolve_schema",
    "select_crud_resource",
    "synthesize_body",
]
