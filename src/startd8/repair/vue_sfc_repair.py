"""Vue SFC projection for JS repair steps (REQ-VUE-P-009).

Node-targeted repair steps operate on plain ``.js`` / ``.ts`` text. For ``.vue``
files, the same steps run on the **primary extracted** ``<script>`` body and
changes are merged back via :func:`startd8.languages.vue_sfc.reinject_vue_script`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from startd8.languages.vue_sfc import extract_vue_script, reinject_vue_script


@dataclass(frozen=True)
class VueScriptRepairSlice:
    """Full SFC source plus the editable primary script slice."""

    original: str
    script: str
    inner_suffix: str


def vue_script_slice(code: str, file_path: Path) -> VueScriptRepairSlice | None:
    """Return script slice for ``.vue`` with a primary block; else ``None``."""
    if file_path.suffix.lower() != ".vue":
        return None
    ext = extract_vue_script(code)
    if ext is None:
        return None
    inner = ".ts" if ext.lang == "ts" else ".js"
    return VueScriptRepairSlice(original=code, script=ext.script, inner_suffix=inner)


def synthetic_script_path(file_path: Path, inner_suffix: str) -> Path:
    """Same basename with ``.js`` / ``.ts`` for steps that branch on suffix."""
    return file_path.with_suffix(inner_suffix)


def merge_script_back(
    sl: VueScriptRepairSlice | None,
    original_full: str,
    new_script: str,
    modified: bool,
) -> str:
    """Reinject into the SFC when ``modified``; otherwise return ``original_full``."""
    if sl is None:
        return new_script
    if not modified:
        return original_full
    return reinject_vue_script(original_full, new_script)
