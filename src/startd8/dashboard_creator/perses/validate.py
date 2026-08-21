"""Offline validation against the vendored, version-pinned Perses CUE oracle."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


class PersesValidationError(ValueError):
    """The emitted resource does not conform to the pinned Perses CUE schemas."""


class PersesValidationUnavailable(RuntimeError):
    """CUE validation was requested but no CUE executable is available."""


_SCHEMA_DIR = Path(__file__).with_name("schema")
_ORACLE = _SCHEMA_DIR / "oracle.cue"


def validate_perses_dashboard(
    dashboard: Dict[str, Any],
    *,
    cue_binary: Optional[str] = None,
) -> None:
    """Validate one emitted dashboard; return ``None`` or raise a typed, actionable error.

    Validation never silently degrades to a structural approximation. Callers may provide a pinned
    executable path; otherwise ``cue`` is resolved from ``PATH`` and absence is a hard error.
    """

    binary = cue_binary or os.environ.get("STARTD8_CUE_BINARY") or shutil.which("cue")
    if not binary:
        raise PersesValidationUnavailable(
            "Perses validation requires the CUE CLI (pinned development version: v0.16.1); "
            "install it or pass cue_binary explicitly"
        )
    if not _ORACLE.is_file():  # pragma: no cover - packaging invariant
        raise PersesValidationUnavailable(f"vendored Perses oracle is missing: {_ORACLE}")

    with tempfile.TemporaryDirectory(prefix="startd8-perses-validate-") as temp_dir:
        candidate = Path(temp_dir) / "dashboard.json"
        candidate.write_text(
            json.dumps(dashboard, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        completed = subprocess.run(
            [binary, "vet", "-c", "-d", "#Dashboard", str(_ORACLE), str(candidate)],
            cwd=_SCHEMA_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise PersesValidationError(
            "dashboard failed pinned Perses v0.54.0 CUE validation"
            + (f": {detail}" if detail else "")
        )
