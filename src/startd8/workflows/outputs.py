"""Helpers for resolving output paths for workflow runs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def resolve_output_path(desc_id: str, base_dir: str | None, filename: str) -> Path:
    """
    Build a deterministic output path under the workflow namespace.
    """
    root = Path(base_dir or "~/.startd8/outputs").expanduser()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return root / desc_id / f"{timestamp}_{filename}"


__all__ = ["resolve_output_path"]
