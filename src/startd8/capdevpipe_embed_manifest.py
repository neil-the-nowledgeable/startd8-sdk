"""Resolve cap-dev-pipe embed inventory from embed-manifest.yaml (Increment A6 / FR-16).

The canonical planner lives in the cap-dev-pipe checkout at
``pipeline/embed_manifest.py``. This adapter imports it dynamically so the SDK installer
shares the same profile resolution as ``install-cap-dev-pipe.sh`` and ``pipeline embed``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

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


class EmbedPlanAction(NamedTuple):
    """A normalized canonical install action (decouples the SDK from canonical types).

    ``action_type`` is one of ``mkdir | symlink | copy_file | copy_tree``; ``target_rel``
    is relative to the embed dir (``"."`` = the embed dir itself); ``source_rel`` is
    relative to the source checkout (empty for mkdir).
    """

    action_type: str
    target_rel: str
    source_rel: str


def resolve_embed_plan(
    source_root: Path, profile: str, method: str, target_root: Path
) -> tuple[EmbedPlanAction, ...]:
    """Delegate embed-plan derivation to the canonical shared planner (FR-A7).

    Canonical ``resolve_install_plan`` is the single owner of the *kind → action* mapping
    (which inventory entries are symlinked vs copied). The SDK translates the returned
    actions to its own ``Action`` type rather than re-deriving that mapping locally.
    """
    em = _import_planner(source_root)
    try:
        actions = em.resolve_install_plan(
            source_root.resolve(), profile, method, Path(target_root)
        )
    except em.EmbedManifestError as exc:  # includes InstallPlanError
        raise ConfigurationError(str(exc)) from exc
    return tuple(
        EmbedPlanAction(
            action_type=str(getattr(a.action_type, "value", a.action_type)),
            target_rel=a.target_rel,
            source_rel=a.source_rel,
        )
        for a in actions
    )


def check_embed_namespace(source_root: Path, profile: str, target_root: Path) -> None:
    """Refuse embed when a generic ``pipeline`` module would shadow the embed package (FR-A8).

    Delegates to canonical ``check_embed_namespace`` when available (Increment A+); a checkout
    predating the guard simply skips the check (no-op) rather than failing the install.
    """
    em = _import_planner(source_root)
    guard = getattr(em, "check_embed_namespace", None)
    if guard is None:  # pragma: no cover - only on a pre-guard canonical checkout
        return
    embed_dir = Path(target_root) / EMBED_DIR_NAME_DEFAULT
    try:
        guard(
            Path(target_root),
            embed_dir,
            profile=profile,
            source_root=source_root.resolve(),
        )
    except em.EmbedManifestError as exc:  # InstallPlanError subclasses EmbedManifestError
        raise ConfigurationError(str(exc)) from exc


#: The embed directory name, mirrored here so the namespace guard can build the embed path
#: without importing the installer (avoids a circular import).
EMBED_DIR_NAME_DEFAULT = ".cap-dev-pipe"
