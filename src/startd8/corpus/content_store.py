"""Durable proven-content store (DETERMINISTIC_PROVIDER_REQUIREMENTS FR-9).

Exemplar `code_artifact_path` is run-dir-relative and non-durable, so proven file content
cannot be retrieved on a later run. This store copies proven content into a durable,
project-scoped location keyed by ``(term_id, source_checksum)`` — so when a feature's
requirement changes (its run's ``source_checksum`` changes) the stale content simply misses
and the provider falls through to the LLM (resolves OQ-2 invalidation).

Layout: ``.startd8/corpus-content/<safe_term_id>/<source_checksum>``

This module is PURE/ADDITIVE — nothing here is invoked by any live workflow. The live
postmortem write-wiring is deferred to plan increment I3 (flag-gated). v1 populate is used
by the validator / bootstrap / tests only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from startd8.corpus.canonical import canonical_key
from startd8.corpus.models import term_id_for
from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = ["ContentStore", "content_store_resolver", "populate_from_run"]


def _safe(term_id: str) -> str:
    return term_id.replace(":", "_").replace("/", "_")


class ContentStore:
    """Durable, project-scoped store of proven file content (FR-9)."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, term_id: str, source_checksum: str) -> Path:
        return self._root / _safe(term_id) / (source_checksum or "nochecksum")

    def put(self, term_id: str, source_checksum: str, content: str) -> None:
        p = self._path(term_id, source_checksum)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(p)  # atomic

    def get(self, term_id: str, source_checksum: str) -> Optional[str]:
        p = self._path(term_id, source_checksum)
        if not p.is_file():
            return None
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return None

    def has(self, term_id: str, source_checksum: str) -> bool:
        return self._path(term_id, source_checksum).is_file()


def content_store_resolver(corpus, store: ContentStore, source_checksum: str) -> Callable[[str], Optional[str]]:
    """FR-2 resolver backed by the durable store, bound to the CURRENT run's source_checksum.

    Returns content only if it was proven under the same input checksum (OQ-2 invalidation):
    a changed feature/input → checksum miss → None → LLM fall-through.
    """
    def resolve(target_file: str) -> Optional[str]:
        term = corpus.find_by_canonical_key("file", target_file)
        if term is None:
            return None
        return store.get(term.term_id, source_checksum)
    return resolve


def populate_from_run(report: Any, source_checksum: str, store: ContentStore) -> int:
    """Copy proven content from a completed run's features into the durable store.

    Wiring (I3 — corrected 2026-07): this IS wired into the live postmortem —
    `prime_postmortem._extract_corpus` (contractors/prime_postmortem.py) imports and calls
    `populate_from_run` per run. Prior docstring said "NOT wired ... in v1" — stale. For each
    successful feature with a target_file + readable generated content, store it keyed by
    (term_id, source_checksum). Returns the number of files stored. Best-effort; never raises.
    """
    stored = 0
    for fpm in getattr(report, "features", []) or []:
        if not getattr(fpm, "success", False):
            continue
        target_files = getattr(fpm, "target_files", None) or []
        generated = getattr(fpm, "generated_files", None) or []
        if not target_files:
            continue
        content = None
        for gf in generated:
            try:
                gp = Path(gf)
                if gp.is_file():
                    content = gp.read_text(encoding="utf-8", errors="replace")
                    break
            except OSError:
                continue
        if content is None:
            continue
        target = target_files[0]
        tid = term_id_for("file", canonical_key("file", "", target))
        try:
            store.put(tid, source_checksum, content)
            stored += 1
        except OSError as exc:
            logger.debug("content_store.put failed for %s: %s", target, exc)
    return stored
