"""
Shared schema version for the Artisan/Plan-Ingestion pipeline (Item 15).

Use a single version string across artifact manifest, onboarding metadata,
context seed, and design handoff so consumers can branch on version for
compatibility or migration logic.

Where to include schema_version (or schema_version_str):
- Context seed: top-level "schema_version" key
- Design handoff: "schema_version_str" key
- Artifact manifest (ContextCore/Wayfinder): include "schema_version": "1.0"
- Onboarding metadata (onboarding-metadata.json): include "schema_version": "1.0"
"""

__all__ = ["ARTISAN_SCHEMA_VERSION", "SUPPORTED_SEED_SCHEMA_VERSIONS"]

# Shared schema version for artifact manifest, onboarding metadata, seed, handoff.
# Bump on breaking changes to any of these schemas.
ARTISAN_SCHEMA_VERSION = "1.0"

# Seed versions accepted by DomainPreflightWorkflow (avoids hardcoding in workflow).
SUPPORTED_SEED_SCHEMA_VERSIONS = frozenset({ARTISAN_SCHEMA_VERSION, "1.0.0"})
