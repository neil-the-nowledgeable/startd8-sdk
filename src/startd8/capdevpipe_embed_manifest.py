"""Resolve cap-dev-pipe embed inventory from embed-manifest.yaml (Increment A6 / FR-16).

The canonical planner lives in the cap-dev-pipe checkout at
``pipeline/embed_manifest.py``. This adapter imports it dynamically so the SDK installer
shares the same profile resolution as ``install-cap-dev-pipe.sh`` and ``pipeline embed``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .exceptions import ConfigurationError

if TYPE_CHECKING:
    from pipeline import embed_manifest as _embed_manifest  # pragma: no cover

DEFAULT_EMBED_PROFILE = "full"
_MANIFEST_FILENAME = "embed-manifest.yaml"
_PLANNER_REL = Path("pipeline") / "embed_manifest.py"


@dataclass(frozen=True)
class ResolvedEmbedInventory:
    """Paths included in a resolved embed profile."""

    profile: str
    scripts: tuple[str, ...]
    python_aliases: tuple[str, ...]
    resource_trees: tuple[str, ...]
    packages: tuple[str, ...]
    copy_files: tuple[str, ...]

    def symlink_top_level_names(self) -> frozenset[str]:
        """Top-level embed-dir names that should be symlinks (for orphan pruning)."""
        return frozenset((*self.scripts, *self.python_aliases, *self.packages))


def _import_planner(source_root: Path) -> type[_embed_manifest]:
    source = source_root.resolve()
    manifest_path = source / _MANIFEST_FILENAME
    planner_path = source / _PLANNER_REL
    if not manifest_path.is_file():
        raise ConfigurationError(
            f"{source} is missing {_MANIFEST_FILENAME}. Point to a cap-dev-pipe checkout "
            f"with modular embed support (Increment A+)."
        )
    if not planner_path.is_file():
        raise ConfigurationError(
            f"{source} is missing {_PLANNER_REL}. Point to a cap-dev-pipe checkout "
            f"with modular embed support (Increment A+)."
        )
    source_str = str(source)
    added = False
    if source_str not in sys.path:
        sys.path.insert(0, source_str)
        added = True
    try:
        from pipeline import embed_manifest as em

        return em
    except ImportError as exc:
        raise ConfigurationError(
            f"Could not import pipeline.embed_manifest from {source}: {exc}. "
            f"Ensure the checkout includes the pipeline/ package."
        ) from exc
    finally:
        if added:
            sys.path.remove(source_str)


def resolve_embed_inventory(
    source_root: Path, profile: str = DEFAULT_EMBED_PROFILE
) -> ResolvedEmbedInventory:
    """Load embed-manifest.yaml from *source_root* and resolve *profile*."""
    em = _import_planner(source_root)
    try:
        manifest = em.load_embed_manifest(source_root=source_root)
        resolved = em.resolve_embed_profile(manifest, profile)
    except em.EmbedManifestError as exc:
        raise ConfigurationError(str(exc)) from exc
    return ResolvedEmbedInventory(
        profile=profile,
        scripts=resolved.scripts,
        python_aliases=resolved.python_aliases,
        resource_trees=resolved.resource_trees,
        packages=resolved.packages,
        copy_files=resolved.copy_files,
    )
