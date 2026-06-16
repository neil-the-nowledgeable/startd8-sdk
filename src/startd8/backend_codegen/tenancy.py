"""Tier B tenant isolation helpers (M3 / FR-TEN-2/3).

A generated app is *row-scoped* per principal when ``deployment.tenant: {model, owner_field}`` is
declared. **No synthesis**: an entity is scoped iff it ALREADY carries a field named ``owner_field``
(an FK to the principal). This module is the single source of truth for two questions the router/web
generators ask: which entities are scoped, and is the declaration valid against the schema.
"""

from __future__ import annotations

from typing import List

from ..frontend_codegen.schema_renderer import composite_type_names
from ..languages.prisma_parser import parse_prisma_schema


def scoped_entities(schema_text: str, owner_field: str) -> List[str]:
    """The models row-scoped to the principal: those that already declare *owner_field* (FR-TEN-2).

    Entities without the owner FK stay shared/unscoped (e.g. lookup tables, the principal model
    itself). Order follows the schema's model order (deterministic).
    """
    schema = parse_prisma_schema(schema_text)
    composites = composite_type_names(schema_text)
    out: List[str] = []
    for name in schema.models:
        if name in composites:
            continue
        m = schema.model(name)
        if m is not None and m.field(owner_field) is not None:
            out.append(name)
    return out


def validate_tenant(schema_text: str, model: str, owner_field: str) -> List[str]:
    """Validate a ``deployment.tenant`` declaration against the schema (B1). Returns issues (empty=OK).

    Checks the principal *model* exists and that *owner_field* scopes at least one entity — a tenancy
    contract that isolates nothing is almost certainly a misconfiguration, so it is a hard error.
    """
    schema = parse_prisma_schema(schema_text)
    issues: List[str] = []
    if model not in schema.models:
        issues.append(f"deployment.tenant.model {model!r} is not a model in the schema")
    if not scoped_entities(schema_text, owner_field):
        issues.append(
            f"deployment.tenant.owner_field {owner_field!r} is present on no entity — tenancy "
            "would scope nothing (add the owner FK to the entities you want isolated)"
        )
    return issues
