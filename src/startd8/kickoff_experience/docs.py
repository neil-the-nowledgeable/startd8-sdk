"""Bounded loader for the kickoff authoring docs (the inputs to manifest extraction).

Read posture (R3-F7): we read only the conventional authoring markdown under ``docs/kickoff/`` (and
the project root), never a broadened scan — the same bounded surface the CLI checker uses.

Two real-world layouts are supported (both bounded to ``docs/kickoff/``):
  * monolithic — a ``REQUIREMENTS*.md`` / ``PLAN*.md`` under ``docs/kickoff/`` or the project root;
  * **per-domain** — every markdown under ``docs/kickoff/authoring/`` (e.g. ``conventions.md``,
    ``views.md``, ``observability.md``). This is the layout a real instantiated package uses, so we
    load the whole ``authoring/`` directory rather than guessing filenames.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

# Conventional monolithic authoring docs the grammar consumes (REQUIREMENTS/PLAN-shaped markdown).
_AUTHORING_GLOBS = ("REQUIREMENTS*.md", "REQUIREMENT*.md", "PLAN*.md")
# The per-domain authoring directory an instantiated kickoff package writes to.
_AUTHORING_SUBDIR = ("docs", "kickoff", "authoring")


def load_kickoff_docs(project_root: str | Path) -> Dict[str, str]:
    """Load the project's kickoff authoring docs (label -> text), deterministically ordered."""
    root = Path(project_root).expanduser()
    docs: Dict[str, str] = {}

    def _add(f: Path) -> None:
        if f.is_file() and f.name not in docs:
            try:
                docs[f.name] = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                pass

    # Per-domain layout: every markdown under docs/kickoff/authoring/ (bounded, non-recursive).
    authoring = root.joinpath(*_AUTHORING_SUBDIR)
    if authoring.is_dir():
        for f in sorted(authoring.glob("*.md")):
            _add(f)

    # Monolithic layout: REQUIREMENTS*/PLAN* under docs/kickoff/ then the project root.
    for base in (root / "docs" / "kickoff", root):
        if not base.is_dir():
            continue
        for pattern in _AUTHORING_GLOBS:
            for f in sorted(base.glob(pattern)):
                _add(f)
    return docs


def live_schema_text(project_root: str | Path) -> Optional[str]:
    """The project's authored contract, if present (enables DIFF-mode extraction)."""
    p = Path(project_root).expanduser() / "prisma" / "schema.prisma"
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
    return None
