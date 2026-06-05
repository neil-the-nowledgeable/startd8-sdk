"""Drift / in-sync checking for scaffold artifacts (manifest-sourced sibling of backend drift).

Same operational idea as ``backend_codegen.drift`` — an owned file re-renders byte-identically from
its source or it is stale/tampered — but the **source is ``app.yaml``, not the schema**, so the
header carries ``manifest-sha256`` and the re-render goes through ``SCAFFOLD_RENDERERS``.
"""

from __future__ import annotations

import re
from typing import Optional

from ..frontend_codegen.schema_renderer import schema_sha256
from .renderers import SCAFFOLD_RENDERERS

_MARKER = "# GENERATED from app.yaml"
_KIND_RE = re.compile(r"#\s*startd8-artifact:\s*(\S+)")
_MSHA_RE = re.compile(r"#\s*manifest-sha256:\s*([0-9a-f]{64})")


def embedded_kind(text: str) -> Optional[str]:
    m = _KIND_RE.search(text or "")
    return m.group(1) if m else None


def embedded_manifest_sha(text: str) -> Optional[str]:
    m = _MSHA_RE.search(text or "")
    return m.group(1) if m else None


def is_owned_scaffold_file(text: str) -> bool:
    """True if *text* is a scaffold file we produced (carries the manifest-sourced GENERATED header)."""
    t = text or ""
    return _MARKER in t and embedded_manifest_sha(t) is not None


def scaffold_in_sync(manifest_text: str, ondisk_text: str) -> bool:
    """True iff *ondisk_text* is an owned scaffold file currently in-sync with *manifest_text*.

    Stale (manifest changed) is caught cheaply by the embedded hash; tampered (hand-edited) by a full
    re-render comparison. Any doubt → ``False`` (the caller falls through to the LLM — a safe failure).
    """
    if not is_owned_scaffold_file(ondisk_text):
        return False
    kind = embedded_kind(ondisk_text)
    renderer = SCAFFOLD_RENDERERS.get(kind or "")
    if renderer is None:
        return False
    if embedded_manifest_sha(ondisk_text) != schema_sha256(manifest_text):
        return False  # stale — manifest changed, file not regenerated
    return renderer(manifest_text) == ondisk_text  # tampered if it differs
