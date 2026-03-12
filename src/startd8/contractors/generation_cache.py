"""Content-addressable generation cache (AC-R3).

Provides a SHA-256-keyed cache for ``GenerationResult`` objects, keyed on
``(description, context_hash, model)``.  This subsumes ad-hoc staleness
detection, Mottainai file-provenance checks, and element cache assembly
into a single lookup:

    key = cache.make_key(feature.description, context_hash, model)
    hit = cache.get(key)
    if hit is not None:
        return hit  # zero-cost reuse

The cache persists to ``.startd8/state/generation_cache/`` as one JSON file
per entry.  Files are named ``{sha256_hex}.json``.

The cache is write-through and read-on-demand — no in-memory index.
This keeps the implementation simple and avoids memory bloat for large runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


def make_cache_key(
    description: str,
    context_hash: str,
    model: str,
    target_files: Optional[List[str]] = None,
) -> str:
    """Compute a SHA-256 cache key from generation inputs.

    Args:
        description: Feature/task description text.
        context_hash: Hash of the generation context (caller computes).
        model: Model agent spec string (e.g. "ollama:qwen2.5-coder:7b").
        target_files: Sorted list of target file paths.  Prevents cache
            collisions when two tasks share description + context but
            target different files.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    files_part = "\x01".join(sorted(target_files)) if target_files else ""
    payload = f"{description}\x00{context_hash}\x00{model}\x00{files_part}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class GenerationCache:
    """Content-addressable cache for generation results.

    Args:
        cache_dir: Directory to store cache entries.  Created on first write.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Look up a cached generation result by key.

        Returns:
            The cached result dict, or None on miss/error.
        """
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info("Generation cache HIT: %s", key[:12])
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Generation cache read error for %s: %s", key[:12], exc)
            return None

    def put(
        self,
        key: str,
        result_data: Dict[str, Any],
    ) -> None:
        """Store a generation result in the cache.

        Only caches successful results.  Failures are not cached to allow
        retry on the next run.

        Args:
            key: SHA-256 hex key from ``make_cache_key()``.
            result_data: Serializable dict of the generation result.
        """
        if not result_data.get("success", False):
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            path = self._cache_dir / f"{key}.json"
            path.write_text(
                json.dumps(result_data, indent=2, default=str),
                encoding="utf-8",
            )
            logger.debug("Generation cache PUT: %s", key[:12])
        except OSError as exc:
            logger.debug("Generation cache write error for %s: %s", key[:12], exc)

    def invalidate(self, key: str) -> bool:
        """Remove a cache entry.

        Returns:
            True if an entry was removed, False if it didn't exist.
        """
        path = self._cache_dir / f"{key}.json"
        if path.exists():
            try:
                path.unlink()
                logger.debug("Generation cache INVALIDATE: %s", key[:12])
                return True
            except OSError:
                pass
        return False

    def stats(self) -> Dict[str, int]:
        """Return cache statistics."""
        if not self._cache_dir.exists():
            return {"entries": 0, "size_bytes": 0}
        entries = list(self._cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in entries)
        return {"entries": len(entries), "size_bytes": total_size}
