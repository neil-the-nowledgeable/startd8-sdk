"""Concierge `derive-contract` — reverse-derive a schema.prisma contract from Pydantic models.

Step 1 (this layer): introspect the project's Pydantic models into normalized *facts*
(`introspect.py`), run under a security-contained subprocess (`containment.py` / FR-DC-14).
Steps 2–5 (mapper → EntityGraph, emit via render_prisma_schema, drift, markers) build on top.

Spec: docs/design/kickoff/CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md v0.3 (FR-DC-3/10/14).
"""

from .introspect import (
    SCHEMA_VERSION,
    DeriveError,
    DeriveImportError,
    EntityFact,
    EnumFact,
    FieldFact,
    IntrospectionResult,
    introspect_models,
    resolve_models,
)
from .containment import run_contained_introspection

__all__ = [
    "SCHEMA_VERSION",
    "DeriveError",
    "DeriveImportError",
    "FieldFact",
    "EntityFact",
    "EnumFact",
    "IntrospectionResult",
    "introspect_models",
    "resolve_models",
    "run_contained_introspection",
]
