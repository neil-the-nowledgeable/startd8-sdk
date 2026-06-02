"""Scaffold levers: create missing resolvable targets (Inc 4, FR-5/FR-6).

Two levers, both **non-destructive** (create-only, never overwrite) and
**realpath-confined** to the run's ``generated/`` root (R3-S2: resolve before the
containment check so a ``../``/symlink escape can't write outside the tree):

* ``scaffold_cofile`` — an empty CSS module for a missing ``*.module.css`` import.
* ``scaffold_barrel`` — an ``index.ts`` re-exporting a directory's sibling modules.
  Bounded to what the regex ``extract_ts_exports`` can soundly name (R2-S2):
  default-export siblings become ``export { default as <FileStem> }``; a name that
  collides across siblings is dropped; never a blind ``export *``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import List, Optional

from ...contractors.upstream_interface import extract_ts_exports
from ...logging_config import get_logger

logger = get_logger(__name__)

_MODULE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_INDEX_STEMS = (
    "index.ts",
    "index.tsx",
    "index.js",
    "index.jsx",
    "index.mjs",
    "index.cjs",
)
_CSS_STUB = "/* scaffolded by repair-retry; styling TODO */\n"


def _confine(candidate: Path, generated_root: Path) -> Optional[Path]:
    """Resolve *candidate* and return it only if it stays under *generated_root*."""
    cand = candidate.resolve(strict=False)
    root = generated_root.resolve(strict=False)
    if cand == root or cand.is_relative_to(root):
        return cand
    logger.warning(
        "repair-retry: refused scaffold escaping the run tree: %s", candidate
    )
    return None


def scaffold_cofile(
    importer_abs: Path, specifier: str, generated_root: Path
) -> Optional[Path]:
    """Create an empty CSS module for *specifier* (relative or ``@/``), if missing.

    Returns the created path, or None (escape / already exists / unsupported form).
    """
    if specifier.startswith("@/"):
        candidate = generated_root / specifier[2:]
    elif specifier.startswith("."):
        candidate = importer_abs.parent / specifier
    else:
        return None
    target = _confine(candidate, generated_root)
    if target is None or target.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_CSS_STUB, encoding="utf-8")
    logger.info("repair-retry: scaffolded co-file %s", target)
    return target


def scaffold_barrel(directory: Path, generated_root: Path) -> Optional[Path]:
    """Create ``<directory>/index.ts`` re-exporting sibling modules, if missing.

    Returns the created index path, or None (escape / has index / nothing safe).
    """
    confined = _confine(directory, generated_root)
    if confined is None or not confined.is_dir():
        return None
    directory = confined
    if any((directory / stem).is_file() for stem in _INDEX_STEMS):
        return None  # already has a barrel

    siblings = [
        f
        for f in sorted(directory.iterdir())
        if f.is_file() and f.suffix in _MODULE_EXTS and f.name not in _INDEX_STEMS
    ]
    if not siblings:
        return None

    # First pass: gather each sibling's exports; count named-export occurrences so
    # a name colliding across siblings can be dropped (R2-S2 collision-safety).
    # NB: the regex `extract_ts_exports` reports `export default function Foo` as
    # BOTH "default" AND "Foo" (R2-F1) — "Foo" is the default's name, not a real
    # named export, so exclude each sibling's own stem from its named set.
    per_sibling = []
    name_counts: Counter = Counter()
    for sib in siblings:
        exports = extract_ts_exports(sib.read_text(encoding="utf-8"))
        named = sorted(n for n in exports if n != "default" and n != sib.stem)
        per_sibling.append((sib.stem, "default" in exports, named))
        for n in named:
            name_counts[n] += 1

    lines: List[str] = []
    emitted: set = set()
    for stem, has_default, named in per_sibling:
        rel = f"./{stem}"
        # default export -> named re-export under the (unique) filename stem
        if has_default and stem not in emitted:
            lines.append(f"export {{ default as {stem} }} from '{rel}';")
            emitted.add(stem)
        # named exports that don't collide across siblings
        safe = [n for n in named if name_counts[n] == 1 and n not in emitted]
        if safe:
            lines.append(f"export {{ {', '.join(safe)} }} from '{rel}';")
            emitted.update(safe)

    if not lines:
        logger.info(
            "repair-retry: barrel for %s had nothing safe to export — abstained",
            directory,
        )
        return None

    index = directory / "index.ts"
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(
        "repair-retry: scaffolded barrel %s (%d re-export line(s))", index, len(lines)
    )
    return index
