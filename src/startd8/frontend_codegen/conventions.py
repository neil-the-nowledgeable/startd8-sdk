"""Deterministic convention layer (Inc 2).

The format-hint rules that sit *on top of* the base Prisma→Zod mapping (Inc 1): a `String`
field named like an email/URL gets a `.email()` / `.url()` refinement, matching the
project's documented `value-model.ts` convention. Pure, no-LLM, declared once.

Two hard-won rules from the CRP review, both encoded here:

- **Type-guard (R4-S3).** A hint is applied **only** to a plain (non-list) `String` field.
  `emailVerified Boolean` or `thumbnailUrlExpiry DateTime` must NOT get `.email()`/`.url()`
  chained onto a non-string Zod type — that would be an *invention* the "by construction"
  thesis claims is impossible.
- **Bare-name match (R4-F2).** The url pattern must match a field named exactly `url`
  (strtd8's `Artifact.url` → `z.string().url()`, `value-model.ts:166`), not only
  `*Url`-suffixed names — the original `Url$|Uri$` regex missed it and broke FR-9
  byte-equality on the project's own headline file.

`@default` handling is **not** here: defaulted fields stay *present and required* (the base
schema never marks them `.optional()`), which the renderer gets for free by driving
nullability purely off the Prisma `?` modifier — never off `@default` (R2-F9/R2-S12).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Tuple

from ..languages.prisma_parser import PrismaField
from ..utils.jsonc import loads_jsonc

# Field-name → format hint. Anchored so a *bare* `url`/`uri`/`email` matches, plus the
# camelCase suffix forms (`avatarUrl`, `contactEmail`). Case-sensitive by design: Prisma
# field names are camelCase, so `Url$`/`Email$` catch the suffix and `^url$`/`^email$`
# catch the bare name.
_DEFAULT_EMAIL = re.compile(r"(?:^email$)|(?:Email$)")
_DEFAULT_URL = re.compile(r"(?:^(?:url|uri)$)|(?:(?:Url|Uri)$)")


@dataclass(frozen=True)
class FieldConventions:
    """Declared, overridable format-hint rules (OQ-2: a default rule set, not inferred)."""

    email_pattern: re.Pattern = _DEFAULT_EMAIL
    url_pattern: re.Pattern = _DEFAULT_URL

    def format_hint(self, field: PrismaField) -> Optional[str]:
        """Return ``.email()`` / ``.url()`` / ``None`` for *field*.

        Type-guarded: only plain (non-list) ``String`` fields are eligible, so a hint is
        never chained onto a non-string base. Email is checked before url; a field can
        match at most one.
        """
        if field.type != "String" or field.is_list:
            return None
        if self.email_pattern.search(field.name):
            return ".email()"
        if self.url_pattern.search(field.name):
            return ".url()"
        return None


# The default rule set, seeded from the documented `value-model.ts` mapping.
DEFAULT_CONVENTIONS = FieldConventions()


# --------------------------------------------------------------------------- #
# Project-convention detection (Inc 6 / FR-5)
# --------------------------------------------------------------------------- #

# Directories never worth scanning for project conventions.
_PRUNE_DIRS = frozenset({"node_modules", "dist", "build"})

_REEXPORT_RE = re.compile(r"export\s+\*\s+from|export\s*\{[^}]*\}\s*from")


@dataclass(frozen=True)
class ProjectConventions:
    """What the *project* actually does — detected, not assumed (FR-5 / NFR-3).

    The **absence** of a convention is first-class: ``uses_barrels=False`` is the explicit
    signal that the project does not use barrels, so the generator emits none **and** the
    LLM should not invent them (the RUN-012 anti-invention).
    """

    alias: Optional[str]  # e.g. "@/" (the import-alias prefix), or None if undetected
    alias_target: Optional[str]  # e.g. "./" (what the alias resolves to)
    uses_barrels: bool
    uses_css_modules: bool
    has_types_dir: bool


def _detect_alias(root: Path) -> Tuple[Optional[str], Optional[str]]:
    """Read ``tsconfig.json`` ``compilerOptions.paths`` for the import alias.

    ``{"@/*": ["./*"]}`` → ``("@/", "./")``. Tolerant of JSONC (comments / trailing
    commas) via ``loads_jsonc``. Returns ``(None, None)`` if absent/unreadable.
    """
    try:
        data = loads_jsonc((root / "tsconfig.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    paths = ((data or {}).get("compilerOptions") or {}).get("paths") or {}
    for key, targets in paths.items():
        if key.endswith("/*") and isinstance(targets, list) and targets:
            target = targets[0]
            if isinstance(target, str) and target.endswith("/*"):
                return key[:-1], target[:-1]  # drop the trailing "*"
    return None, None


def _walk_source_files(root: Path) -> Iterator[Path]:
    """Yield files under *root*, pruning ``node_modules``/build dirs and hidden dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _PRUNE_DIRS and not d.startswith(".")
        ]
        for name in filenames:
            yield Path(dirpath) / name


def _detect_barrels(root: Path) -> bool:
    """True if any ``index.ts(x)`` re-exports a sibling (a barrel file)."""
    for path in _walk_source_files(root):
        if path.name in ("index.ts", "index.tsx"):
            try:
                if _REEXPORT_RE.search(path.read_text(encoding="utf-8")):
                    return True
            except OSError:
                continue
    return False


def _detect_css_modules(root: Path) -> bool:
    """True if the project contains any ``*.module.css`` file."""
    return any(p.name.endswith(".module.css") for p in _walk_source_files(root))


def detect_project_conventions(project_root: str | os.PathLike) -> ProjectConventions:
    """Detect a project's frontend conventions from its files (FR-5).

    Follows the **project**, never LLM priors: the alias comes from ``tsconfig.json``;
    barrel/CSS-module usage from the actual file tree. The absence of a convention is an
    explicit output (e.g. strtd8 → ``uses_barrels=False``), which prevents the generator
    from emitting — and signals the LLM not to invent — the RUN-012 artifact classes.
    """
    root = Path(project_root)
    alias, target = _detect_alias(root)
    return ProjectConventions(
        alias=alias,
        alias_target=target,
        uses_barrels=_detect_barrels(root),
        uses_css_modules=_detect_css_modules(root),
        has_types_dir=(root / "types").is_dir(),
    )
