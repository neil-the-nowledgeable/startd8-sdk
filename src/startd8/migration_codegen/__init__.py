"""Deterministic Alembic migration generation from the Prisma contract (OQ-SCAF-2 fork B).

$0, no live DB: diff the previous contract snapshot (embedded in the latest revision) against the
current contract and emit an additive-only revision. See ``generator`` for the FR-MG-2/3/6 logic.
"""

from .generator import (
    MigrationPlan,
    latest_snapshot,
    next_revision,
    plan_migration,
    render_revision,
)

__all__ = [
    "MigrationPlan",
    "plan_migration",
    "render_revision",
    "next_revision",
    "latest_snapshot",
]
