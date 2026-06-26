"""Bounded loader for the kickoff authoring docs (the inputs to manifest extraction).

Read posture (R3-F7): we read only the conventional authoring markdown under ``docs/kickoff/`` (and
the project root), never a broadened scan — the same bounded surface the CLI checker uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

# Conventional authoring docs the grammar consumes (REQUIREMENTS/PLAN-shaped markdown).
_AUTHORING_GLOBS = ("REQUIREMENTS*.md", "REQUIREMENT*.md", "PLAN*.md")


def load_kickoff_docs(project_root: str | Path) -> Dict[str, str]:
    """Load the project's kickoff authoring docs (label -> text), deterministically ordered."""
    root = Path(project_root).expanduser()
    docs: Dict[str, str] = {}
    for base in (root / "docs" / "kickoff", root):
        if not base.is_dir():
            continue
        for pattern in _AUTHORING_GLOBS:
            for f in sorted(base.glob(pattern)):
                if f.is_file() and f.name not in docs:
                    try:
                        docs[f.name] = f.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        continue
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
