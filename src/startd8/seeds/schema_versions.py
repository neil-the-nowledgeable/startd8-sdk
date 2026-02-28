"""
Canonical home for seed / pipeline schema version constants.

Re-exported by ``workflows.builtin.schema_versions`` for backward compat.
"""

__all__ = [
    "ARTISAN_SCHEMA_VERSION",
    "SEED_SCHEMA_VERSION",
    "SUPPORTED_SEED_SCHEMA_VERSIONS",
]

# Shared schema version for artifact manifest, onboarding metadata, seed, handoff.
# Bump on breaking changes to any of these schemas.
ARTISAN_SCHEMA_VERSION = "1.0"

# Alias used by SeedBuilder / ContextSeed
SEED_SCHEMA_VERSION = ARTISAN_SCHEMA_VERSION

# Seed versions accepted by DomainPreflightWorkflow (avoids hardcoding in workflow).
# Includes "1.0.0" for backward compat with seeds written before Item 15.
SUPPORTED_SEED_SCHEMA_VERSIONS = frozenset({ARTISAN_SCHEMA_VERSION, "1.0.0"})
