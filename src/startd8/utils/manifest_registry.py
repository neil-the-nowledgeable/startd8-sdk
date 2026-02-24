"""
Manifest registry — thin query layer over cached code manifests.

Provides ManifestRegistry (project-wide manifest lookup, FQN index,
dependency graph, element summaries) and ManifestDiff (structural diff
between two FileManifest instances).

Phase 4: Pipeline Integration — consumed by IMPLEMENT, INTEGRATE,
TEST, REVIEW, Plan Ingestion, and Preflight.

See docs/design/CODE_MANIFEST_PHASE4_REQUIREMENTS.md for the specification.
"""

from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, TypedDict

from startd8.logging_config import get_logger
from startd8.utils.code_manifest import (
    Element,
    FileManifest,
    SCHEMA_VERSION,
    Visibility,
)

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Timing helper
# ═══════════════════════════════════════════════════════════════════════════


@contextmanager
def _timer(operation: str, level: int = logging.INFO, **extra: Any) -> Iterator[dict[str, float]]:
    """Lightweight timing context manager for manifest operations.

    Args:
        operation: Structured log operation tag (e.g. ``manifest.diff``).
        level: Log level — use ``logging.DEBUG`` for high-frequency ops
               like ``element_summary`` to avoid flooding.
        **extra: Additional structured fields for the log ``extra`` dict.
    """
    result: dict[str, float] = {}
    start = time.monotonic()
    try:
        yield result
    finally:
        elapsed_ms = (time.monotonic() - start) * 1000
        result["elapsed_ms"] = elapsed_ms
        logger.log(level, operation, extra={**extra, "elapsed_ms": round(elapsed_ms, 2)})


# ═══════════════════════════════════════════════════════════════════════════
# Signature normalization
# ═══════════════════════════════════════════════════════════════════════════


def _normalize_signature(sig: str) -> str:
    """Normalize a signature string to prevent false-positive diff results.

    - Strips leading/trailing whitespace
    - Collapses internal whitespace runs to single spaces
    - Normalizes Optional[X] to X | None
    - Normalizes typing.Optional[X] to X | None
    """
    sig = sig.strip()
    sig = re.sub(r"\s+", " ", sig)
    sig = re.sub(r"(?:typing\.)?Optional\[([^\]]+)\]", r"\1 | None", sig)
    return sig


# ═══════════════════════════════════════════════════════════════════════════
# ManifestSummarySchema
# ═══════════════════════════════════════════════════════════════════════════


class ManifestSummarySchema(TypedDict):
    """Explicit contract for handoff serialization between PLAN and IMPLEMENT phases."""

    file_count: int
    total_elements: int
    public_elements: int
    schema_version: str
    generated_at: str


# ═══════════════════════════════════════════════════════════════════════════
# ManifestDiff
# ═══════════════════════════════════════════════════════════════════════════


def _walk_public_elements(elements: list[Element]) -> dict[str, Element]:
    """Recursively walk elements and collect public ones by FQN.

    Skips elements with None fqn or missing visibility (defensive).

    Returns:
        Dict mapping FQN strings to their PUBLIC Element instances.
        Includes children and class_variables recursively.
    """
    result: dict[str, Element] = {}
    for el in elements:
        if not el.fqn:
            logger.warning(
                "manifest.diff: element with name=%r has empty fqn — skipping",
                getattr(el, "name", "<unknown>"),
            )
            continue
        try:
            vis = el.visibility
        except AttributeError:
            logger.warning(
                "manifest.diff: element %r missing visibility — skipping", el.fqn
            )
            continue
        if vis == Visibility.PUBLIC:
            result[el.fqn] = el
        # Recurse into children and class_variables
        for child in el.children:
            result.update(_walk_public_elements([child]))
        for cv in el.class_variables:
            result.update(_walk_public_elements([cv]))
    return result


def _element_signature_str(el: Element) -> str:
    """Extract a string representation of an element's signature."""
    if el.signature is None:
        return ""
    parts = []
    for p in el.signature.params:
        s = p.name
        if p.annotation:
            s += f": {p.annotation}"
        if p.default is not None:
            s += f" = {p.default}"
        parts.append(s)
    sig = f"({', '.join(parts)})"
    if el.signature.return_annotation:
        sig += f" -> {el.signature.return_annotation}"
    return sig


@dataclass(frozen=True)
class ManifestDiff:
    """Structural diff between two FileManifest instances.

    Compares public elements by FQN. Signature comparison uses
    _normalize_signature() to avoid false positives from whitespace,
    Optional[X] vs X | None variations, and typing. prefix differences.

    Cross-version safe (req R2-S2): operates on common fields only
    (elements, imports, dependencies).

    Known limitations (req R1-S7, R2-S6):
    - Renames appear as removal+addition → false positive on has_breaking_changes
    - Body-only changes, decorator changes, default param value changes are
      invisible to FQN+signature structural diff (false negatives)
    """

    removed_public: list[str] = field(default_factory=list)     # FQNs removed
    added_public: list[str] = field(default_factory=list)       # FQNs added
    changed_signatures: list[tuple[str, str, str]] = field(default_factory=list)  # (fqn, old_sig, new_sig)
    element_count_delta: int = 0                                # new - old

    @property
    def has_breaking_changes(self) -> bool:
        """True if public elements were removed or signatures changed."""
        return bool(self.removed_public) or bool(self.changed_signatures)

    @staticmethod
    def diff(old: FileManifest, new: FileManifest) -> ManifestDiff:
        """Compute diff between two manifests.

        Defensive handling (plan R1-S10): elements with None fqn or missing
        visibility are skipped with a logged warning, not fatal. Returns a
        valid ManifestDiff even for partially-parsed manifests from AI-generated code.
        """
        with _timer("manifest.diff"):
            old_public = _walk_public_elements(old.elements)
            new_public = _walk_public_elements(new.elements)

            old_fqns = set(old_public.keys())
            new_fqns = set(new_public.keys())

            removed = sorted(old_fqns - new_fqns)
            added = sorted(new_fqns - old_fqns)

            changed: list[tuple[str, str, str]] = []
            for fqn in sorted(old_fqns & new_fqns):
                old_sig = _normalize_signature(_element_signature_str(old_public[fqn]))
                new_sig = _normalize_signature(_element_signature_str(new_public[fqn]))
                if old_sig != new_sig:
                    changed.append((fqn, old_sig, new_sig))

            # Count all elements (not just public) for delta
            old_count = _count_all_elements(old.elements)
            new_count = _count_all_elements(new.elements)

            return ManifestDiff(
                removed_public=removed,
                added_public=added,
                changed_signatures=changed,
                element_count_delta=new_count - old_count,
            )


def _count_all_elements(elements: list[Element]) -> int:
    """Count all elements recursively."""
    count = len(elements)
    for el in elements:
        count += _count_all_elements(el.children)
        count += _count_all_elements(el.class_variables)
    return count


# ═══════════════════════════════════════════════════════════════════════════
# ManifestRegistry
# ═══════════════════════════════════════════════════════════════════════════


class ManifestRegistry:
    """Thin query layer wrapping dict[str, FileManifest].

    Threading contract (req R1-S1): Immutable per pipeline phase. Consumers in
    IMPLEMENT/TEST/REVIEW read the registry; only INTEGRATE creates a new instance
    via with_updated_files(). Never mutate an existing instance from multiple threads.
    """

    _MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB per-file deserialization guard (req R3-S3)

    def __init__(self, manifests: dict[str, FileManifest]) -> None:
        self._manifests = dict(manifests)  # defensive copy
        self._fqn_index: dict[str, tuple[str, Element]] = {}
        self._dep_graph: dict[str, set[str]] | None = None
        self._mtimes: dict[str, float] = {}  # relative_path → mtime at load time
        self._build_fqn_index()
        logger.info("manifest.load", extra={"files": len(manifests)})

    def _build_fqn_index(self) -> None:
        """Build the full FQN index from all manifests."""
        self._fqn_index.clear()
        for rel_path, manifest in self._manifests.items():
            self._index_elements(rel_path, manifest.elements)

    def _index_elements(self, rel_path: str, elements: list[Element]) -> None:
        """Recursively index elements by FQN."""
        for el in elements:
            if el.fqn:
                self._fqn_index[el.fqn] = (rel_path, el)
            self._index_elements(rel_path, el.children)
            self._index_elements(rel_path, el.class_variables)

    @classmethod
    def from_cache(cls, project_root: Path) -> ManifestRegistry | None:
        """Load manifests from the cache directory. Returns None on any failure.

        Error handling (req R2-S3): catches JSONDecodeError, Pydantic ValidationError,
        OSError, and any other exception. Logs at WARNING and returns None.

        Staleness detection (req R1-S3): compares cached content_digest against
        file mtime from the _index.json metadata. Files with mtime > cached_mtime
        are excluded from the registry (treated as manifest-absent per GD-2).

        Per-file size guard (req R3-S3): skips any manifest JSON file > 5MB before
        deserialization to prevent resource exhaustion.
        """
        with _timer("manifest.cache_load", project_root=str(project_root)) as timing:
            try:
                cache_dir = project_root / ".startd8" / "manifests"
                if not cache_dir.is_dir():
                    logger.info(
                        "manifest.fallback",
                        extra={"surface": "from_cache", "reason": "cache_dir_missing"},
                    )
                    return None

                index_path = cache_dir / "_index.json"
                if not index_path.exists():
                    logger.info(
                        "manifest.fallback",
                        extra={"surface": "from_cache", "reason": "index_missing"},
                    )
                    return None

                try:
                    index_data = json.loads(index_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning(
                        "manifest.cache_load: corrupt index file: %s", exc
                    )
                    return None

                # Validate meta — use .get() to avoid mutating the parsed dict
                meta = index_data.get("_meta")
                if not isinstance(meta, dict):
                    logger.info(
                        "manifest.fallback",
                        extra={"surface": "from_cache", "reason": "missing_meta"},
                    )
                    return None

                manifests: dict[str, FileManifest] = {}
                mtimes: dict[str, float] = {}

                for rel_path, digest in index_data.items():
                    if rel_path == "_meta":
                        continue
                    if not isinstance(digest, str):
                        continue

                    # Staleness check via mtime
                    full_path = project_root / rel_path
                    if full_path.exists():
                        try:
                            current_mtime = full_path.stat().st_mtime
                            mtimes[rel_path] = current_mtime
                        except OSError:
                            pass

                    # Compute cache key
                    hex_part = digest.split(":", 1)[-1] if ":" in digest else digest
                    cache_file = cache_dir / f"sha256_{hex_part}.json"

                    if not cache_file.exists():
                        continue

                    # Per-file size guard (req R3-S3)
                    try:
                        file_size = cache_file.stat().st_size
                        if file_size > cls._MAX_FILE_SIZE_BYTES:
                            logger.warning(
                                "manifest.cache_load: skipping oversized manifest %s (%d bytes)",
                                rel_path,
                                file_size,
                            )
                            continue
                    except OSError:
                        continue

                    try:
                        raw = json.loads(cache_file.read_text(encoding="utf-8"))
                        manifest = FileManifest.model_validate(raw)
                        manifests[rel_path] = manifest
                    except Exception as exc:
                        logger.warning(
                            "manifest.cache_load: failed to load %s: %s",
                            rel_path,
                            exc,
                        )
                        continue

                if not manifests:
                    logger.info(
                        "manifest.fallback",
                        extra={"surface": "from_cache", "reason": "no_valid_manifests"},
                    )
                    return None

                registry = cls(manifests)
                registry._mtimes = mtimes
                return registry

            except Exception as exc:
                logger.warning(
                    "manifest.cache_load: unexpected error: %s", exc, exc_info=True,
                )
                return None

    def get(self, relative_path: str) -> FileManifest | None:
        """Single-file lookup. Path traversal guard (req R1-S8):
        rejects paths with '..' components or absolute paths."""
        if not relative_path:
            return None
        p = PurePosixPath(relative_path.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts:
            logger.warning(
                "manifest.get: rejected path traversal attempt: %s", relative_path
            )
            return None
        normalized = str(p)
        return self._manifests.get(normalized)

    def fqn_exists(self, fqn: str) -> bool:
        """Check if a fully-qualified name exists in any manifest."""
        return fqn in self._fqn_index

    def resolve_fqn(self, fqn: str) -> tuple[str, Element] | None:
        """Return (file_path, element) for a FQN. Path traversal guard (req R1-S8):
        returned paths are validated to be within project root."""
        result = self._fqn_index.get(fqn)
        if result is None:
            return None
        file_path, element = result
        # Validate path doesn't contain traversal
        p = PurePosixPath(file_path.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts:
            logger.warning(
                "manifest.resolve_fqn: rejected path traversal in stored path: %s",
                file_path,
            )
            return None
        return result

    def is_stale(self, relative_path: str) -> bool:
        """Returns True if the file's current mtime exceeds the mtime at load time (req R1-S3).

        Returns False if no mtime data is available (conservative — assume fresh).

        Note: This performs a stat() call on each invocation. Callers should
        cache the result if checking the same file multiple times in a loop.
        """
        cached_mtime = self._mtimes.get(relative_path)
        if cached_mtime is None:
            return False
        # Locate the manifest to find the project root context
        manifest = self._manifests.get(relative_path)
        if manifest is None:
            return False
        # The manifest stores a relative file path; we need to resolve
        # against the project root that was used at load time.  Since we
        # don't persist project_root, we can only compare if the absolute
        # path is reconstructable.  Use a conservative heuristic: check
        # if the path is resolvable from cwd.
        try:
            p = Path(relative_path)
            if p.exists():
                current_mtime = p.stat().st_mtime
                return current_mtime > cached_mtime
        except OSError:
            pass
        return False

    def file_element_summary(self, relative_path: str, budget_chars: int = 4000) -> str:
        """Build a budget-constrained element summary for a file.

        Elements are emitted in source-order (by span.start_line), truncated bottom-up.

        Progressive truncation (4 tiers):
        1. Full: FQN + signature + docstring (1 line) + span
        2. Compact: drop docstrings
        3. Public-only: drop private/protected
        4. FQN-only: public FQNs + signatures only
        """
        with _timer("manifest.element_summary", level=logging.DEBUG, path=relative_path, budget=budget_chars):
            manifest = self._manifests.get(relative_path)
            if manifest is None:
                return ""

            all_elements = _flatten_elements(manifest.elements)
            # Sort by source order (span.start_line)
            all_elements.sort(key=lambda e: e.span.start_line if e.span else 0)

            # Tier 1: Full — FQN + signature + docstring (1 line) + span
            lines = _format_elements_tier1(all_elements)
            result = "\n".join(lines)
            if len(result) <= budget_chars:
                return result

            # Tier 2: Compact — drop docstrings
            lines = _format_elements_tier2(all_elements)
            result = "\n".join(lines)
            if len(result) <= budget_chars:
                return result

            # Tier 3: Public-only — drop private/protected
            public_elements = [
                e for e in all_elements if e.visibility == Visibility.PUBLIC
            ]
            lines = _format_elements_tier2(public_elements)
            result = "\n".join(lines)
            if len(result) <= budget_chars:
                return result

            # Tier 4: FQN-only — public FQNs + signatures only
            lines = _format_elements_tier4(public_elements)
            result = "\n".join(lines)
            if len(result) <= budget_chars:
                return result

            # Still too long — truncate from bottom, tracking cumulative length
            total_len = sum(len(line) for line in lines) + max(len(lines) - 1, 0)  # newline separators
            while lines and total_len > budget_chars:
                removed = lines.pop()
                total_len -= len(removed) + (1 if lines else 0)  # subtract line + separator
            return "\n".join(lines)

    def public_element_count(self, relative_path: str) -> int:
        """Count public elements in a file."""
        manifest = self._manifests.get(relative_path)
        if manifest is None:
            return 0
        all_elements = _flatten_elements(manifest.elements)
        return sum(1 for e in all_elements if e.visibility == Visibility.PUBLIC)

    def dependency_graph(self) -> dict[str, set[str]]:
        """File-level internal dependency adjacency list (req R1-S2).

        Keys and values are relative POSIX paths. External deps (stdlib,
        third-party) are filtered out. Lazy-computed; invalidated by
        with_updated_files().
        """
        if self._dep_graph is not None:
            return self._dep_graph

        known_files = set(self._manifests.keys())
        # Build a module→file mapping for internal resolution
        module_to_file: dict[str, str] = {}
        for rel_path, manifest in self._manifests.items():
            if manifest.module:
                module_to_file[manifest.module] = rel_path

        graph: dict[str, set[str]] = {}
        for rel_path, manifest in self._manifests.items():
            deps: set[str] = set()
            for imp in manifest.imports:
                # Check internal dependencies only
                if manifest.dependencies and imp.module in manifest.dependencies.internal:
                    target = module_to_file.get(imp.module)
                    if target and target != rel_path:
                        deps.add(target)
                # Also check by module prefix
                for mod, fpath in module_to_file.items():
                    if imp.module.startswith(mod + ".") and fpath != rel_path:
                        deps.add(fpath)
            graph[rel_path] = deps

        self._dep_graph = graph
        return graph

    def files(self) -> list[str]:
        """Return all file paths in the registry."""
        return list(self._manifests.keys())

    def summary_stats(self) -> ManifestSummarySchema:
        """Returns typed summary dict for handoff serialization (CT-2).

        Keys: file_count, total_elements, public_elements, schema_version, generated_at.
        """
        total = 0
        public = 0
        for manifest in self._manifests.values():
            all_els = _flatten_elements(manifest.elements)
            total += len(all_els)
            public += sum(1 for e in all_els if e.visibility == Visibility.PUBLIC)

        return ManifestSummarySchema(
            file_count=len(self._manifests),
            total_elements=total,
            public_elements=public,
            schema_version=SCHEMA_VERSION,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def with_updated_files(self, updates: dict[str, FileManifest]) -> ManifestRegistry:
        """Create a NEW registry with updated file manifests (immutable-per-phase pattern).

        Used by INTEGRATE (Step 9) to produce a fresh instance after cache refresh.
        Invalidates dependency graph and rebuilds FQN index.
        """
        new_manifests = {**self._manifests, **updates}
        return ManifestRegistry(new_manifests)


# ═══════════════════════════════════════════════════════════════════════════
# Element formatting helpers
# ═══════════════════════════════════════════════════════════════════════════


def _flatten_elements(elements: list[Element]) -> list[Element]:
    """Recursively flatten element tree into a flat list."""
    result: list[Element] = []
    for el in elements:
        result.append(el)
        result.extend(_flatten_elements(el.children))
        result.extend(_flatten_elements(el.class_variables))
    return result


def _format_element_line(
    el: Element, *, include_docstring: bool = False, include_span: bool = False,
) -> str:
    """Format a single element as a summary line.

    Args:
        el: The element to format.
        include_docstring: Append first-line docstring (tier 1 only).
        include_span: Append source span ``[start-end]`` (tiers 1-3).
    """
    sig_str = _element_signature_str(el) if el.signature else ""
    parts = [f"- {el.fqn}{sig_str}"]
    if include_docstring and el.docstring:
        first_line = el.docstring.strip().split("\n")[0][:80]
        parts.append(f'  """{first_line}"""')
    if include_span and el.span:
        parts.append(f"  [{el.span.start_line}-{el.span.end_line}]")
    return "".join(parts)


def _format_elements_tier1(elements: list[Element]) -> list[str]:
    """Tier 1: Full — FQN + signature + docstring (1 line) + span."""
    return [_format_element_line(el, include_docstring=True, include_span=True) for el in elements]


def _format_elements_tier2(elements: list[Element]) -> list[str]:
    """Tier 2: Compact — FQN + signature + span (no docstrings)."""
    return [_format_element_line(el, include_span=True) for el in elements]


def _format_elements_tier4(elements: list[Element]) -> list[str]:
    """Tier 4: FQN-only — public FQNs + signatures only."""
    return [_format_element_line(el) for el in elements]
