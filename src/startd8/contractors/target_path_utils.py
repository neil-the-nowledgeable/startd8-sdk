"""Target-path classification — the "FR-1 belt" home (recovers the module `e0c3ec33` imported but
never created).

A feature's ``target_files`` should name **concrete files** to generate. A *directory target* — a path
that denotes a directory rather than a file — cannot be generated into. ``prime_contractor.develop_feature``
uses these helpers to (a) **refuse** a feature whose targets are *all* directories before any LLM spend,
and (b) **drop** directory entries from a mixed target list, keeping the concrete files.

Classification is deliberately **conservative**: only unambiguous directories are flagged, so a valid
extension-less file (``Dockerfile``, ``Makefile``, ``go.mod``'s neighbours, ``README``) is never mistaken
for a directory and wrongly refused. Anything not clearly a directory is treated as a file target and
allowed through — preserving the pre-belt behaviour for ambiguous names.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def is_directory_target(target: str) -> bool:
    """True when *target* denotes a directory rather than a concrete file.

    Flags only unambiguous directories:
      * an explicit trailing path separator (``"src/"``, ``"pkg/handlers/"``), or
      * a path that already exists on disk and is a directory.

    Everything else — any concrete or merely ambiguous filename — is treated as a file target
    (returns ``False``), so an extension-less real file is never refused.
    """
    if not target:
        return False
    t = str(target).strip()
    if not t:
        return False
    if t.endswith("/") or t.endswith(os.sep):
        return True
    try:
        return Path(t).is_dir()
    except OSError:  # pragma: no cover - defensive (e.g. path too long / permission)
        return False


def any_directory_targets(targets: Iterable[str]) -> bool:
    """True if any entry in *targets* is a directory target (see :func:`is_directory_target`)."""
    return any(is_directory_target(t) for t in targets)
