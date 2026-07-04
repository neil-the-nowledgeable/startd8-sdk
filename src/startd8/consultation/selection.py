"""Image input selection with the untrusted-path trust boundary (M3.3 / FR-MMC-14).

Shared by the TUI and the ``startd8 consult`` CLI so both select byte-identical images
from the same folder (no logic fork). The rules:

* **Trust boundary (R2-S1, FR-MMC-14):** paths are resolved; **symlinks** and **non-regular**
  files (FIFO/device/socket) are refused; an optional ``allowed_root`` rejects anything that
  resolves outside it (``..`` traversal).
* **Bounded scan (R2-S9):** a directory scan examines at most ``max_dir_entries`` entries, so a
  huge or special-file directory cannot hang selection.
* **Deterministic (R2-F3/FR-MMC-1):** directory candidates are sorted lexicographically by name
  and the first ``max_images`` that pass magic-byte validation are chosen.
* **Mutual exclusion (R2-F6/FR-MMC-13):** :func:`resolve_images` accepts explicit paths *or* a
  directory, never both.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .. agents.multimodal import DEFAULT_MAX_BYTES, ImageInput, ImageValidationError, load_image

DEFAULT_MAX_DIR_ENTRIES = 10_000
MAX_IMAGES = 2  # FR-MMC-1


class ImageSelectionError(ValueError):
    """Raised when path/dir selection violates the trust boundary or count limits."""


def _guard_regular_file(p: Path, *, allowed_root: Optional[Path]) -> Path:
    """Resolve ``p`` and enforce: no symlink, regular file, within ``allowed_root``."""
    if p.is_symlink():
        raise ImageSelectionError(f"refusing symlinked path: {p}")
    resolved = p.resolve()
    if allowed_root is not None:
        root = Path(allowed_root).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as e:
            raise ImageSelectionError(f"path escapes allowed root {root}: {resolved}") from e
    if not resolved.is_file():
        raise ImageSelectionError(f"not a regular file: {resolved}")
    return resolved


def load_paths(
    paths: "list[str | Path]",
    *,
    max_images: int = MAX_IMAGES,
    allowed_root: Optional[str | Path] = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> "list[ImageInput]":
    """Validate an explicit list of image paths (trust boundary + format/size)."""
    if len(paths) > max_images:
        raise ImageSelectionError(
            f"{len(paths)} images supplied, exceeds the limit of {max_images}"
        )
    out: list[ImageInput] = []
    for raw in paths:
        resolved = _guard_regular_file(Path(raw), allowed_root=allowed_root)
        out.append(load_image(resolved, max_bytes=max_bytes))
    return out


def select_from_dir(
    image_dir: "str | Path",
    *,
    max_images: int = MAX_IMAGES,
    allowed_root: Optional[str | Path] = None,
    max_dir_entries: int = DEFAULT_MAX_DIR_ENTRIES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> "list[ImageInput]":
    """Deterministically select up to ``max_images`` valid images from a directory.

    Scans direct children only (bounded), skipping symlinks and non-regular files, sorts
    the candidate regular files lexicographically by name, and returns the first
    ``max_images`` that pass magic-byte validation.
    """
    d = Path(image_dir)
    resolved_dir = d.resolve()
    if allowed_root is not None:
        root = Path(allowed_root).resolve()
        try:
            resolved_dir.relative_to(root)
        except ValueError as e:
            raise ImageSelectionError(f"directory escapes allowed root {root}: {resolved_dir}") from e
    if not resolved_dir.is_dir():
        raise ImageSelectionError(f"not a directory: {resolved_dir}")

    # Bounded scan: collect candidate regular (non-symlink) files, capped.
    candidates: list[Path] = []
    examined = 0
    with os.scandir(resolved_dir) as it:
        for entry in it:
            examined += 1
            if examined > max_dir_entries:
                break
            try:
                if entry.is_symlink():
                    continue
                if not entry.is_file(follow_symlinks=False):  # skip FIFO/device/dir
                    continue
            except OSError:
                continue
            candidates.append(Path(entry.path))

    selected: list[ImageInput] = []
    for path in sorted(candidates, key=lambda p: p.name):  # deterministic order
        if len(selected) >= max_images:
            break
        try:
            selected.append(load_image(path, max_bytes=max_bytes))
        except ImageValidationError:
            continue  # not a valid image — skip, keep scanning in order
    return selected


def resolve_images(
    *,
    paths: "Optional[list[str | Path]]" = None,
    image_dir: "Optional[str | Path]" = None,
    max_images: int = MAX_IMAGES,
    allowed_root: Optional[str | Path] = None,
) -> "list[ImageInput]":
    """Entry point: explicit ``paths`` XOR ``image_dir`` (mutually exclusive, FR-MMC-13)."""
    if paths and image_dir:
        raise ImageSelectionError("provide image paths OR an image directory, not both")
    if paths:
        return load_paths(paths, max_images=max_images, allowed_root=allowed_root)
    if image_dir:
        return select_from_dir(image_dir, max_images=max_images, allowed_root=allowed_root)
    return []
