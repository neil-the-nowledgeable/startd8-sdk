"""Presentation Polish engine — apply a theme's deterministic design system to a target project.

``apply_polish`` writes the polish-owned artifacts (stylesheet + static-mount module) and a manifest,
idempotently and non-destructively:

- **Idempotent** (FR-15): outputs are pure functions of (theme, version), so a re-run with the same
  theme reports every file ``unchanged``.
- **Non-destructive** (FR-20): a target that exists but lacks the polish marker is treated as
  user-authored and is **skipped, never overwritten** — surfaced as a warning.
- **$0** (FR-24): no LLM is involved; cost is reported as ``0.0`` explicitly.

The engine never touches ``backend_codegen``-owned files (``base.html``, ``main.py``); those carry
the stylesheet ``<link>`` and the tolerant ``static_setup`` import from the generator itself, so the
two paths coexist without either clobbering the other (FR-21).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple

from ..logging_config import get_logger
from .components import (
    render_components_macros,
    render_footer_partial,
    render_head_extra,
    render_header_partial,
)
from .css import POLISH_VERSION, render_static_setup, render_stylesheet
from .themes import DEFAULT_THEME, get_theme

logger = get_logger(__name__)

# Polish-owned artifacts, relative to the project root. (path -> how to render its content.)
STYLESHEET_RELPATH = "app/static/css/app.css"
STATIC_SETUP_RELPATH = "app/static_setup.py"
# Theme partials filling backend's tolerant base.html hooks (the {% import %} seam).
THEME_COMPONENTS_RELPATH = "app/templates/theme/_components.html"
THEME_HEADER_RELPATH = "app/templates/theme/_header.html"
THEME_FOOTER_RELPATH = "app/templates/theme/_footer.html"
THEME_HEAD_EXTRA_RELPATH = "app/templates/theme/_head_extra.html"
MANIFEST_RELPATH = ".startd8/polish-manifest.json"


class FileStatus(str, Enum):
    """Outcome for a single polish-owned file on an apply/check pass."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    SKIPPED_USER_OWNED = (
        "skipped_user_owned"  # exists without polish marker — never overwritten
    )
    DRIFT = "drift"  # --check only: polish-owned but out of date
    MISSING = "missing"  # --check only: not yet written


@dataclass(frozen=True)
class PolishConfig:
    """Fully-resolved inputs for an apply/check pass (headless-drivable — no interactive state)."""

    project_root: Path
    theme: str = DEFAULT_THEME
    check: bool = False  # report drift without writing


@dataclass
class PolishResult:
    """What an apply/check pass did. ``cost_usd`` is always 0.0 (deterministic, no LLM)."""

    theme: str
    files: List[Tuple[str, FileStatus]] = field(default_factory=list)
    manifest_path: str = MANIFEST_RELPATH
    cost_usd: float = 0.0

    @property
    def wrote_anything(self) -> bool:
        return any(s in (FileStatus.CREATED, FileStatus.UPDATED) for _, s in self.files)

    @property
    def has_drift(self) -> bool:
        return any(s in (FileStatus.DRIFT, FileStatus.MISSING) for _, s in self.files)

    @property
    def skipped_user_owned(self) -> List[str]:
        return [p for p, s in self.files if s == FileStatus.SKIPPED_USER_OWNED]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _planned_artifacts(theme_name: str) -> Dict[str, str]:
    """The polish-owned (relpath -> content) map for *theme_name*. Pure; deterministic."""
    theme = get_theme(theme_name)  # raises KeyError on unknown theme
    return {
        STYLESHEET_RELPATH: render_stylesheet(theme),
        STATIC_SETUP_RELPATH: render_static_setup(),
        # Theme partials are theme-independent markup (the stylesheet themes them); constant + deterministic.
        THEME_COMPONENTS_RELPATH: render_components_macros(),
        THEME_HEADER_RELPATH: render_header_partial(),
        THEME_FOOTER_RELPATH: render_footer_partial(),
        THEME_HEAD_EXTRA_RELPATH: render_head_extra(),
    }


def _classify(target: Path, new_content: str, *, check: bool) -> FileStatus:
    """Decide the status for one target without (yet) writing."""
    from .css import POLISH_MARKER

    if not target.exists():
        return FileStatus.MISSING if check else FileStatus.CREATED
    try:
        existing = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Unreadable (binary, a directory, bad perms) → we can't confirm it's ours, so never
        # overwrite it. Treat as the user's (FR-20 non-destructive); safer than crashing.
        return FileStatus.SKIPPED_USER_OWNED
    if POLISH_MARKER not in existing:
        # User-authored a file at our path — respect it, never clobber (FR-20).
        return FileStatus.SKIPPED_USER_OWNED
    if existing == new_content:
        return FileStatus.UNCHANGED
    return FileStatus.DRIFT if check else FileStatus.UPDATED


def apply_polish(config: PolishConfig) -> PolishResult:
    """Apply (or, with ``config.check``, audit) the polish design system on ``config.project_root``."""
    root = Path(config.project_root)
    if not root.is_dir():
        raise NotADirectoryError(f"project root not found: {root}")

    artifacts = _planned_artifacts(config.theme)
    result = PolishResult(theme=config.theme)
    file_shas: Dict[str, str] = {}

    for relpath, content in artifacts.items():
        target = root / relpath
        status = _classify(target, content, check=config.check)
        result.files.append((relpath, status))

        if status == FileStatus.SKIPPED_USER_OWNED:
            logger.warning(
                "polish: %s exists without the polish marker — leaving the user's file untouched",
                relpath,
            )
            continue

        if not config.check and status in (FileStatus.CREATED, FileStatus.UPDATED):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        # Record the intended (post-apply) sha for the manifest regardless of write, except for
        # user-owned files we declined to manage.
        file_shas[relpath] = _sha256(content)

    if not config.check:
        _write_manifest(root, config.theme, file_shas)

    logger.info(
        "polish: theme=%s %s — %d file(s); cost=$0.00",
        config.theme,
        "checked" if config.check else "applied",
        len(result.files),
    )
    return result


def _write_manifest(root: Path, theme: str, file_shas: Dict[str, str]) -> None:
    """Write the deterministic polish manifest (no timestamp → byte-stable / idempotent)."""
    manifest = {
        "polish_version": POLISH_VERSION,
        "theme": theme,
        "files": dict(sorted(file_shas.items())),
    }
    path = root / MANIFEST_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
