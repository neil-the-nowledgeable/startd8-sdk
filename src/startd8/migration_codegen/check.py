"""Pending migration probe for ``generate backend --check`` (Tier-1 FR-C3)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from .generator import MigrationPlan, next_revision


def pending_migration_message(
    versions_dir: Path, current_text: str
) -> Optional[str]:
    """Return a human message when a revision is pending, else ``None``."""
    result = next_revision(versions_dir, current_text, "auto")
    if result is None:
        return None
    fname, _, plan = result
    kind = "baseline" if plan.is_baseline else f"{len(plan.upgrade_ops)} additive op(s)"
    return (
        f"migration pending: {kind} → run `startd8 generate migrate` "
        f"(would write alembic/versions/{fname})"
    )


def pending_migration(
    versions_dir: Path, current_text: str
) -> Optional[Tuple[str, str, MigrationPlan]]:
    """Return ``next_revision`` tuple when pending, else ``None``."""
    return next_revision(versions_dir, current_text, "auto")
