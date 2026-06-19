"""Deterministic Alembic migration generation from the Prisma contract (OQ-SCAF-2 fork B).

$0, no live DB: diff the previous contract snapshot (embedded in the latest revision) against the
current contract and emit an additive-only revision. See ``generator`` for the FR-MG-2/3/6 logic.
"""

from .check import pending_migration, pending_migration_message
from .drift import is_owned_migration_file, migration_revision_in_sync, rerender_revision
from .generator import (
    MigrationPlan,
    latest_snapshot,
    next_revision,
    plan_migration,
    render_revision,
)
from .provider import MigrationFileProvider

__all__ = [
    "MigrationPlan",
    "MigrationFileProvider",
    "is_owned_migration_file",
    "latest_snapshot",
    "migration_revision_in_sync",
    "next_revision",
    "pending_migration",
    "pending_migration_message",
    "plan_migration",
    "render_revision",
    "rerender_revision",
]
