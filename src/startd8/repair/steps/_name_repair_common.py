"""Shared helpers for the name-repair steps (Inc 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models import Diagnostic


def diagnostic_targets_file(diag: Diagnostic, file_path: Path) -> bool:
    """True if *diag* (whose ``file`` is a project-relative path) targets *file_path*.

    Matches on a normalized suffix or an exact basename, so a relative diagnostic
    path (``lib/ai/enrich.ts``) lines up with the absolute file the orchestrator
    is repairing.
    """
    if not diag.file:
        return False
    df = diag.file.replace("\\", "/").lstrip("./")
    fp = str(file_path).replace("\\", "/")
    if fp.endswith(df):
        return True
    return Path(diag.file).name == Path(file_path).name


def resolve_truth_source(injected, project_root: Optional[Path]):
    """Return the injected truth source, or build a live one from *project_root*."""
    if injected is not None:
        return injected
    from ..truth_source import LiveDiskTruthSource

    return LiveDiskTruthSource(project_root if project_root is not None else Path("."))
