"""
Schema version constants for the plan-ingestion pipeline.

Canonical definitions live in ``startd8.seeds.schema_versions``.
This module re-exports them for backward compatibility with code that
imports from ``startd8.workflows.builtin.schema_versions``.
"""

from startd8.seeds.schema_versions import (  # noqa: F401
    ARTISAN_SCHEMA_VERSION,
    SEED_SCHEMA_VERSION,
    SUPPORTED_SEED_SCHEMA_VERSIONS,
)

__all__ = [
    "ARTISAN_SCHEMA_VERSION",
    "SEED_SCHEMA_VERSION",
    "SUPPORTED_SEED_SCHEMA_VERSIONS",
]
