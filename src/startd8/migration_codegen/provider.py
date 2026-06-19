"""Deterministic-file provider for owned Alembic revisions (Tier-1 PR2)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from .drift import is_owned_migration_file, migration_revision_in_sync


class MigrationFileProvider:
    """Recognizes ``alembic/versions/*.py`` revisions and verifies chain re-render."""

    name = "migration"

    def owns(self, path: Path, content: str) -> bool:
        return is_owned_migration_file(content)

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        versions_dir = self._versions_dir(path, context)
        if versions_dir is None:
            return False
        return migration_revision_in_sync(path, content, versions_dir)

    @staticmethod
    def _versions_dir(path: Path, context: ProviderContext) -> Optional[Path]:
        if path.parent.name == "versions" and path.parent.parent.name == "alembic":
            return path.parent
        root = Path(context.project_root)
        conventional = root / "alembic" / "versions"
        return conventional if conventional.is_dir() else None
