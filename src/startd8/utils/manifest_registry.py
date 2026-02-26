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
    CallEdge,
    CallGraphInfo,
    Element,
    ElementKind,
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


def _resolved_signature_str(el: Element) -> str | None:
    """Extract signature from inspect_info.resolved_signature when available.

    Returns None when element has no resolved signature (fall back to AST).
    """
    info = getattr(el, "inspect_info", None)
    if info is None or not hasattr(info, "resolved_signature"):
        return None
    rs = info.resolved_signature
    if rs is None:
        return None
    parts = []
    for p in rs.params:
        s = p.name
        if p.annotation:
            s += f": {p.annotation}"
        if p.default is not None:
            s += f" = {p.default}"
        parts.append(s)
    sig = f"({', '.join(parts)})"
    if rs.return_annotation:
        sig += f" -> {rs.return_annotation}"
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
    # Phase 6: Call edge diff fields
    removed_call_edges: list[CallEdge] = field(default_factory=list)  # edges in old, not in new
    added_call_edges: list[CallEdge] = field(default_factory=list)    # edges in new, not in old
    # (fqn, old_sig, new_sig, callers) — populated only when registry is provided
    signature_changes_with_callers: list[tuple[str, str, str, frozenset[str]]] = field(default_factory=list)
    # Phase 5: Introspect diff fields (IN-1, IN-2, IN-3)
    # (fqn, old_resolved, new_resolved) — resolved type changes invisible to AST diff
    changed_resolved_signatures: list[tuple[str, str, str]] = field(default_factory=list)
    # (fqn, old_mro, new_mro) — MRO restructuring detection
    mro_changes: list[tuple[str, list[str], list[str]]] = field(default_factory=list)
    # (added_exports, removed_exports) or None if __all__ absent on either side
    module_all_diff: tuple[list[str], list[str]] | None = None

    @property
    def has_breaking_changes(self) -> bool:
        """True if public elements were removed or signatures changed."""
        return bool(self.removed_public) or bool(self.changed_signatures)

    @staticmethod
    def call_edge_diff(
        old: FileManifest, new: FileManifest,
    ) -> tuple[list[CallEdge], list[CallEdge]]:
        """Compute call edge differences between two manifests.

        Returns:
            ``(removed_edges, added_edges)`` as lists of :class:`CallEdge`.
        """
        def _collect_edges(manifest: FileManifest) -> set[tuple[str, str]]:
            edges: set[tuple[str, str]] = set()
            for elem in _flatten_elements(manifest.elements):
                if elem.call_graph is not None and elem.fqn:
                    for call in elem.call_graph.calls:
                        if call.target_fqn is not None:
                            edges.add((elem.fqn, call.target_fqn))
            return edges

        old_edges = _collect_edges(old)
        new_edges = _collect_edges(new)
        removed = [CallEdge(caller_fqn=c, callee_fqn=t) for c, t in sorted(old_edges - new_edges)]
        added = [CallEdge(caller_fqn=c, callee_fqn=t) for c, t in sorted(new_edges - old_edges)]
        return removed, added

    @staticmethod
    def diff(old: FileManifest, new: FileManifest, registry: ManifestRegistry | None = None) -> ManifestDiff:
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

            # Phase 6: Call edge diff
            try:
                removed_edges, added_edges = ManifestDiff.call_edge_diff(old, new)
            except Exception:
                removed_edges, added_edges = [], []

            # Phase 6: signature changes with callers (when registry available)
            sig_with_callers: list[tuple[str, str, str, frozenset[str]]] = []
            if registry is not None and changed:
                for fqn, old_sig, new_sig in changed:
                    try:
                        callers = registry.callers_of(fqn)
                        if callers:
                            sig_with_callers.append(
                                (fqn, old_sig, new_sig, frozenset(callers))
                            )
                    except Exception:
                        pass

            # Phase 5: Resolved signature diff (IN-1) — catch type changes invisible to AST
            changed_resolved: list[tuple[str, str, str]] = []
            try:
                for fqn in sorted(old_fqns & new_fqns):
                    old_el = old_public[fqn]
                    new_el = new_public[fqn]
                    old_rs = getattr(getattr(old_el, "inspect_info", None), "resolved_signature", None)
                    new_rs = getattr(getattr(new_el, "inspect_info", None), "resolved_signature", None)
                    if old_rs is not None and new_rs is not None:
                        old_str = str(old_rs)
                        new_str = str(new_rs)
                        if old_str != new_str:
                            changed_resolved.append((fqn, old_str, new_str))
            except Exception:
                pass

            # Phase 5: MRO change diff (IN-2)
            mro_changes: list[tuple[str, list[str], list[str]]] = []
            try:
                for fqn in sorted(old_fqns & new_fqns):
                    old_el = old_public[fqn]
                    new_el = new_public[fqn]
                    old_mro = getattr(getattr(old_el, "inspect_info", None), "mro", None)
                    new_mro = getattr(getattr(new_el, "inspect_info", None), "mro", None)
                    if old_mro is not None and new_mro is not None and old_mro != new_mro:
                        mro_changes.append((fqn, list(old_mro), list(new_mro)))
            except Exception:
                pass

            # Phase 5: __all__ diff (IN-3)
            module_all_diff: tuple[list[str], list[str]] | None = None
            try:
                old_all = getattr(old, "module_all", None)
                new_all = getattr(new, "module_all", None)
                if old_all is not None and new_all is not None:
                    old_set = set(old_all)
                    new_set = set(new_all)
                    added_exports = sorted(new_set - old_set)
                    removed_exports = sorted(old_set - new_set)
                    module_all_diff = (added_exports, removed_exports)
            except Exception:
                pass

            return ManifestDiff(
                removed_public=removed,
                added_public=added,
                changed_signatures=changed,
                element_count_delta=new_count - old_count,
                removed_call_edges=removed_edges,
                added_call_edges=added_edges,
                signature_changes_with_callers=sig_with_callers,
                changed_resolved_signatures=changed_resolved,
                mro_changes=mro_changes,
                module_all_diff=module_all_diff,
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
        self._call_graph: dict[str, set[str]] | None = None
        self._reverse_call_graph: dict[str, set[str]] | None = None
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

    def file_element_summary(
        self,
        relative_path: str,
        budget_chars: int = 4000,
        *,
        include_resolved_types: bool = False,
    ) -> str:
        """Build a budget-constrained element summary for a file.

        Elements are emitted in source-order (by span.start_line), truncated bottom-up.

        Progressive truncation (4 tiers):
        1. Full: FQN + signature + docstring (1 line) + span
        2. Compact: drop docstrings
        3. Public-only: drop private/protected
        4. FQN-only: public FQNs + signatures only

        When include_resolved_types is True and element.inspect_info.resolved_signature
        is available, uses resolved parameter types instead of AST-extracted types (PI-2).
        """
        with _timer("manifest.element_summary", level=logging.DEBUG, path=relative_path, budget=budget_chars):
            manifest = self._manifests.get(relative_path)
            if manifest is None:
                return ""

            all_elements = _flatten_elements(manifest.elements)
            # Sort by source order (span.start_line)
            all_elements.sort(key=lambda e: e.span.start_line if e.span else 0)

            fmt_kw = {"include_resolved_types": include_resolved_types}

            # Tier 1: Full — FQN + signature + docstring (1 line) + span
            lines = _format_elements_tier1(all_elements, **fmt_kw)
            result = "\n".join(lines)
            if len(result) <= budget_chars:
                return result

            # Tier 2: Compact — drop docstrings
            lines = _format_elements_tier2(all_elements, **fmt_kw)
            result = "\n".join(lines)
            if len(result) <= budget_chars:
                return result

            # Tier 3: Public-only — drop private/protected
            public_elements = [
                e for e in all_elements if e.visibility == Visibility.PUBLIC
            ]
            lines = _format_elements_tier2(public_elements, **fmt_kw)
            result = "\n".join(lines)
            if len(result) <= budget_chars:
                return result

            # Tier 4: FQN-only — public FQNs + signatures only
            lines = _format_elements_tier4(public_elements, **fmt_kw)
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

    def module_version_for(self, relative_path: str) -> str | None:
        """Return FileManifest.module_version for the given file (PI-1).

        Returns None when the file has no manifest or module_version is unset.
        """
        manifest = self._manifests.get(relative_path)
        if manifest is None:
            return None
        return getattr(manifest, "module_version", None) or None

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

    # ───────────────────────────────────────────────────────────────────
    # Phase 5: Introspect query methods (DS-1..DS-4, IM-1..IM-3, PF-1, PI-1)
    # ───────────────────────────────────────────────────────────────────

    def file_resolved_type_summary(
        self,
        relative_path: str,
        budget_chars: int = 2000,
    ) -> str:
        """Compact LLM-readable summary of resolved types for a file's callables (PR-1, DS-1).

        Format per callable: ``element_name: (param: Type, ...) -> ReturnType``
        Progressive truncation: full → public-only → count-only.

        Returns empty string when no elements have resolved type data or file
        is not in the registry (graceful degradation, Phase 5 DS-6).
        """
        with _timer("manifest.file_resolved_type_summary", level=logging.DEBUG, path=relative_path):
            try:
                manifest = self._manifests.get(relative_path)
                if manifest is None:
                    return ""

                all_elements = _flatten_elements(manifest.elements)
                entries: list[tuple[str, str, bool]] = []  # (fqn, resolved_str, is_public)
                for elem in all_elements:
                    if not elem.fqn:
                        continue
                    inspect_info = getattr(elem, "inspect_info", None)
                    if inspect_info is None:
                        continue
                    rs = getattr(inspect_info, "resolved_signature", None)
                    if rs is None:
                        continue
                    is_public = elem.visibility == Visibility.PUBLIC
                    entries.append((elem.fqn, str(rs), is_public))

                if not entries:
                    return ""

                # Tier 1: Full (all elements)
                lines = [f"{fqn}: {rs}" for fqn, rs, _ in entries]
                result = "\n".join(lines)
                if len(result) <= budget_chars:
                    return result

                # Tier 2: Public-only
                public_lines = [f"{fqn}: {rs}" for fqn, rs, pub in entries if pub]
                result = "\n".join(public_lines)
                if len(result) <= budget_chars:
                    return result

                # Tier 3: Count-only
                return f"{len(entries)} elements with resolved type data ({len(public_lines)} public)"

            except Exception as exc:
                logger.debug("manifest.file_resolved_type_summary failed for %s: %s", relative_path, exc)
                return ""

    def file_mro_summary(
        self,
        relative_path: str,
    ) -> dict[str, list[str]]:
        """MRO chains for class elements with meaningful inheritance (DS-2).

        Returns a dict mapping class FQN to its MRO list, excluding
        ``builtins.object`` and classes whose MRO has only 1 entry.
        Returns empty dict when file not in registry or no eligible classes.
        """
        with _timer("manifest.file_mro_summary", level=logging.DEBUG, path=relative_path):
            try:
                manifest = self._manifests.get(relative_path)
                if manifest is None:
                    return {}

                result: dict[str, list[str]] = {}
                for elem in _flatten_elements(manifest.elements):
                    if not elem.fqn:
                        continue
                    inspect_info = getattr(elem, "inspect_info", None)
                    if inspect_info is None:
                        continue
                    mro = getattr(inspect_info, "mro", None)
                    if not mro:
                        continue
                    # Filter out builtins.object, keep only non-trivial chains
                    filtered = [m for m in mro if m != "builtins.object"]
                    if len(filtered) > 1:
                        result[elem.fqn] = filtered
                return result

            except Exception as exc:
                logger.debug("manifest.file_mro_summary failed for %s: %s", relative_path, exc)
                return {}

    def file_runtime_attributes(
        self,
        relative_path: str,
    ) -> dict[str, list[str]]:
        """Runtime-only attributes for dataclass/namedtuple elements (DS-4, IM-2).

        Returns a dict mapping element FQN to its list of runtime attributes.
        Only elements with non-empty ``inspect_info.runtime_attributes`` are included.
        Returns empty dict when file not in registry or no eligible elements.
        """
        with _timer("manifest.file_runtime_attributes", level=logging.DEBUG, path=relative_path):
            try:
                manifest = self._manifests.get(relative_path)
                if manifest is None:
                    return {}

                result: dict[str, list[str]] = {}
                for elem in _flatten_elements(manifest.elements):
                    if not elem.fqn:
                        continue
                    inspect_info = getattr(elem, "inspect_info", None)
                    if inspect_info is None:
                        continue
                    attrs = getattr(inspect_info, "runtime_attributes", None)
                    if attrs:
                        result[elem.fqn] = list(attrs)
                return result

            except Exception as exc:
                logger.debug("manifest.file_runtime_attributes failed for %s: %s", relative_path, exc)
                return {}

    def module_all_for(
        self,
        relative_path: str,
    ) -> list[str] | None:
        """Runtime ``__all__`` list for the given file (DS-3, IN-3, PF-1).

        Returns the ``FileManifest.module_all`` list, or None when:
        - file is not in the registry
        - ``module_all`` is absent or None (no introspect data, or module has no ``__all__``)
        Never raises.
        """
        try:
            manifest = self._manifests.get(relative_path)
            if manifest is None:
                return None
            val = getattr(manifest, "module_all", None)
            return list(val) if val else None
        except Exception as exc:
            logger.debug("manifest.module_all_for failed for %s: %s", relative_path, exc)
            return None


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

    # ───────────────────────────────────────────────────────────────────
    # Phase 6: call graph queries
    # ───────────────────────────────────────────────────────────────────

    def call_graph(self) -> dict[str, set[str]]:
        """Full project call graph: caller_fqn → {callee_fqns}.

        Lazy-computed from element call_graph data. Invalidated by
        with_updated_files() (new instance gets None caches).
        """
        if self._call_graph is not None:
            return self._call_graph

        graph: dict[str, set[str]] = {}
        for _rel_path, manifest in self._manifests.items():
            self._collect_call_graph_from_elements(manifest.elements, graph)

        self._call_graph = graph
        return graph

    def _collect_call_graph_from_elements(
        self, elements: list[Element], graph: dict[str, set[str]],
    ) -> None:
        """Recursively collect call graph edges from elements."""
        for elem in elements:
            if elem.call_graph is not None:
                for call in elem.call_graph.calls:
                    if call.target_fqn is not None:
                        graph.setdefault(elem.fqn, set()).add(call.target_fqn)
            self._collect_call_graph_from_elements(elem.children, graph)
            self._collect_call_graph_from_elements(elem.class_variables, graph)

    def reverse_call_graph(self) -> dict[str, set[str]]:
        """Reverse call graph: callee_fqn → {caller_fqns}.

        Lazy-computed transpose of call_graph().
        """
        if self._reverse_call_graph is not None:
            return self._reverse_call_graph

        forward = self.call_graph()
        reverse: dict[str, set[str]] = {}
        for caller, callees in forward.items():
            for callee in callees:
                reverse.setdefault(callee, set()).add(caller)

        self._reverse_call_graph = reverse
        return reverse

    def blast_radius(self, fqn: str, max_depth: int = 10) -> set[str]:
        """Compute all transitive callers of a FQN (reverse reachability).

        BFS from ``fqn`` through reverse_call_graph edges, limited by
        ``max_depth`` to prevent unbounded traversal.
        """
        reverse = self.reverse_call_graph()
        visited: set[str] = set()
        frontier = {fqn}
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for node in frontier:
                for caller in reverse.get(node, set()):
                    if caller not in visited and caller != fqn:
                        visited.add(caller)
                        next_frontier.add(caller)
            if not next_frontier:
                break
            frontier = next_frontier
        return visited

    def dead_candidates(
        self,
        *,
        use_runtime_callable: bool = False,
    ) -> list[str]:
        """Public callables with zero inbound call edges.

        These are candidate dead code — public functions/methods that
        are never called from within the project. Sorted alphabetically.

        Args:
            use_runtime_callable: When True (Phase 5, CG-1), use
                ``inspect_info.is_callable`` as the callable classifier instead
                of the AST-based ``ElementKind`` heuristic. Elements with
                ``is_callable=True`` are included regardless of kind; elements
                with ``is_callable=False`` are excluded regardless of kind.
                Defaults to False (Phase 4 + Phase 6 behaviour).
        """
        reverse = self.reverse_call_graph()
        callable_kinds = frozenset({
            ElementKind.FUNCTION,
            ElementKind.ASYNC_FUNCTION,
            ElementKind.METHOD,
            ElementKind.ASYNC_METHOD,
        })
        candidates: list[str] = []
        for fqn, (_path, elem) in self._fqn_index.items():
            if use_runtime_callable:
                # Phase 5 CG-1: use runtime is_callable truth
                is_callable = getattr(getattr(elem, "inspect_info", None), "is_callable", None)
                if is_callable is None:
                    # No introspect data — fall through to kind heuristic
                    callable_by_kind = elem.kind in callable_kinds
                else:
                    callable_by_kind = is_callable
            else:
                callable_by_kind = elem.kind in callable_kinds

            if (
                callable_by_kind
                and elem.visibility == Visibility.PUBLIC
                and fqn not in reverse
            ):
                candidates.append(fqn)
        return sorted(candidates)

    def callers_of(self, fqn: str) -> set[str]:
        """Direct (1-hop) callers of the given FQN."""
        return self.reverse_call_graph().get(fqn, set())

    def callees_of(self, fqn: str) -> set[str]:
        """Direct (1-hop) callees of the given FQN."""
        return self.call_graph().get(fqn, set())

    # ───────────────────────────────────────────────────────────────────
    # Phase 6 pipeline: higher-level call graph queries
    # ───────────────────────────────────────────────────────────────────

    def callers_of_file(self, relative_path: str) -> dict[str, set[str]]:
        """For each element in the file, return callers from *other* files.

        Returns:
            Dict mapping element FQN → set of caller FQNs from other files.
            Only elements with at least one cross-file caller are included.
        """
        with _timer("manifest.callers_of_file", level=logging.DEBUG, path=relative_path):
            try:
                manifest = self._manifests.get(relative_path)
                if manifest is None:
                    return {}

                file_elements = _flatten_elements(manifest.elements)
                file_fqns = {e.fqn for e in file_elements if e.fqn}

                reverse = self.reverse_call_graph()
                result: dict[str, set[str]] = {}
                for fqn in file_fqns:
                    callers = reverse.get(fqn, set())
                    # Filter to callers from OTHER files
                    cross_file_callers = set()
                    for caller in callers:
                        resolved = self._fqn_index.get(caller)
                        if resolved is not None:
                            caller_path, _ = resolved
                            if caller_path != relative_path:
                                cross_file_callers.add(caller)
                    if cross_file_callers:
                        result[fqn] = cross_file_callers
                return result
            except Exception as exc:
                logger.debug("manifest.callers_of_file failed for %s: %s", relative_path, exc)
                return {}

    def call_graph_summary(self, relative_path: str, budget: int = 2000) -> str:
        """Budget-aware text summary of call relationships for a file.

        3-tier truncation: full → top-N → count-only.

        Args:
            relative_path: File to summarize.
            budget: Maximum character budget.

        Returns:
            Formatted summary string, or ``""`` if no data.
        """
        with _timer("manifest.call_graph_summary", level=logging.DEBUG, path=relative_path, budget=budget):
            try:
                manifest = self._manifests.get(relative_path)
                if manifest is None:
                    return ""

                file_elements = _flatten_elements(manifest.elements)
                forward = self.call_graph()
                reverse = self.reverse_call_graph()

                entries: list[tuple[str, int, int]] = []  # (name, callers, callees)
                for elem in file_elements:
                    if not elem.fqn:
                        continue
                    n_callers = len(reverse.get(elem.fqn, set()))
                    n_callees = len(forward.get(elem.fqn, set()))
                    if n_callers > 0 or n_callees > 0:
                        entries.append((elem.fqn, n_callers, n_callees))

                if not entries:
                    return ""

                # Sort by total connections descending for truncation priority
                entries.sort(key=lambda e: e[1] + e[2], reverse=True)

                # Tier 1: Full detail
                lines = [
                    f"- {name}: called by {callers}, calls {callees}"
                    for name, callers, callees in entries
                ]
                result = "\n".join(lines)
                if len(result) <= budget:
                    return result

                # Tier 2: Top-N by connection count
                for n in range(len(entries) - 1, 0, -1):
                    lines = [
                        f"- {name}: called by {callers}, calls {callees}"
                        for name, callers, callees in entries[:n]
                    ]
                    lines.append(f"  ... and {len(entries) - n} more")
                    result = "\n".join(lines)
                    if len(result) <= budget:
                        return result

                # Tier 3: Count-only
                return f"{len(entries)} functions with call relationships"

            except Exception as exc:
                logger.debug("manifest.call_graph_summary failed for %s: %s", relative_path, exc)
                return ""

    def max_blast_radius(self, fqns: list[str]) -> tuple[str, int]:
        """Return the FQN with the largest blast radius and its count.

        Args:
            fqns: List of FQNs to evaluate.

        Returns:
            ``(fqn_with_max, count)`` or ``("", 0)`` if empty.
        """
        with _timer("manifest.max_blast_radius", level=logging.DEBUG, count=len(fqns)):
            try:
                if not fqns:
                    return ("", 0)

                max_fqn = ""
                max_count = 0
                for fqn in fqns:
                    radius = self.blast_radius(fqn, max_depth=3)
                    if len(radius) > max_count:
                        max_count = len(radius)
                        max_fqn = fqn
                return (max_fqn, max_count)
            except Exception as exc:
                logger.debug("manifest.max_blast_radius failed: %s", exc)
                return ("", 0)

    def call_graph_cycles(self, max_depth: int = 10) -> list[list[str]]:
        """DFS cycle detection on the call graph.

        Returns cycle paths as ``[a, b, c, a]`` (last element repeats first).
        Bounded by ``max_depth`` to prevent unbounded traversal.

        Args:
            max_depth: Maximum DFS depth.

        Returns:
            List of cycle paths found.
        """
        with _timer("manifest.call_graph_cycles", level=logging.DEBUG, max_depth=max_depth):
            try:
                graph = self.call_graph()
                if not graph:
                    return []

                cycles: list[list[str]] = []
                visited: set[str] = set()
                seen_cycles: set[frozenset[str]] = set()  # dedup

                def _dfs(node: str, path: list[str], depth: int) -> None:
                    if depth > max_depth:
                        return
                    for neighbor in graph.get(node, set()):
                        if neighbor in path:
                            # Found a cycle — extract it
                            idx = path.index(neighbor)
                            cycle = path[idx:] + [neighbor]
                            cycle_key = frozenset(cycle[:-1])
                            if cycle_key not in seen_cycles:
                                seen_cycles.add(cycle_key)
                                cycles.append(cycle)
                            continue
                        if neighbor not in visited:
                            path.append(neighbor)
                            _dfs(neighbor, path, depth + 1)
                            path.pop()

                for start in sorted(graph.keys()):
                    if start not in visited:
                        _dfs(start, [start], 0)
                        visited.add(start)

                return cycles
            except Exception as exc:
                logger.debug("manifest.call_graph_cycles failed: %s", exc)
                return []


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
    el: Element,
    *,
    include_docstring: bool = False,
    include_span: bool = False,
    include_resolved_types: bool = False,
) -> str:
    """Format a single element as a summary line.

    Args:
        el: The element to format.
        include_docstring: Append first-line docstring (tier 1 only).
        include_span: Append source span ``[start-end]`` (tiers 1-3).
        include_resolved_types: Prefer resolved signature from inspect_info when available.
    """
    if include_resolved_types:
        sig_str = _resolved_signature_str(el) or (
            _element_signature_str(el) if el.signature else ""
        )
    else:
        sig_str = _element_signature_str(el) if el.signature else ""
    parts = [f"- {el.fqn}{sig_str}"]
    if include_docstring and el.docstring:
        first_line = el.docstring.strip().split("\n")[0][:80]
        parts.append(f'  """{first_line}"""')
    if include_span and el.span:
        parts.append(f"  [{el.span.start_line}-{el.span.end_line}]")
    return "".join(parts)


def _format_elements_tier1(
    elements: list[Element], *, include_resolved_types: bool = False
) -> list[str]:
    """Tier 1: Full — FQN + signature + docstring (1 line) + span."""
    return [
        _format_element_line(
            el,
            include_docstring=True,
            include_span=True,
            include_resolved_types=include_resolved_types,
        )
        for el in elements
    ]


def _format_elements_tier2(
    elements: list[Element], *, include_resolved_types: bool = False
) -> list[str]:
    """Tier 2: Compact — FQN + signature + span (no docstrings)."""
    return [
        _format_element_line(
            el, include_span=True, include_resolved_types=include_resolved_types
        )
        for el in elements
    ]


def _format_elements_tier4(
    elements: list[Element], *, include_resolved_types: bool = False
) -> list[str]:
    """Tier 4: FQN-only — public FQNs + signatures only."""
    return [
        _format_element_line(el, include_resolved_types=include_resolved_types)
        for el in elements
    ]
