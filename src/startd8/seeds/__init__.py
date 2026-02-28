"""
``startd8.seeds`` — Unified context-seed construction package.

Public API:

* :class:`ContextSeed` — contractor-agnostic seed envelope
* :class:`SeedTask` — parsed task from an enriched seed
* :class:`SeedBuilder` — step-by-step builder for seed construction
* Schema version constants
"""

from .builder import SeedBuilder
from .models import ContextSeed, SeedTask
from .schema_versions import (
    ARTISAN_SCHEMA_VERSION,
    SEED_SCHEMA_VERSION,
    SUPPORTED_SEED_SCHEMA_VERSIONS,
)

__all__ = [
    "ContextSeed",
    "SeedTask",
    "SeedBuilder",
    "ARTISAN_SCHEMA_VERSION",
    "SEED_SCHEMA_VERSION",
    "SUPPORTED_SEED_SCHEMA_VERSIONS",
]
