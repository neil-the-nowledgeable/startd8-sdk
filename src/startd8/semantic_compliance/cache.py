# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Verdict cache for idempotency (S-R1-2).

Keyed by ``(run_id, feature_id, code_checksum)`` so a re-run with unchanged code reuses prior
verdicts and pays **zero** new agent cost. Mirrors the Service Assistant cursor pattern.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional

from ..logging_config import get_logger
from ..utils.file_operations import atomic_write_json

logger = get_logger(__name__)

CACHE_FILENAME = ".scr-verdict-cache.json"


def code_checksum(generated_files: List[str], root: Optional[Path] = None) -> str:
    """Stable fingerprint of a feature's generated files (sha256 of sorted contents)."""
    h = hashlib.sha256()
    for rel in sorted(generated_files):
        p = (root / rel) if root else Path(rel)
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(rel.encode("utf-8"))  # missing file still contributes to the key
    return f"sha256:{h.hexdigest()[:32]}"


class VerdictCache:
    """Per-run cache of ``feature_id → {checksum, verdict_payload}``."""

    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self._data: dict = {"schema_version": "1.0", "run_id": run_id, "verdicts": {}}

    @classmethod
    def load(cls, output_dir: Path, run_id: str) -> "VerdictCache":
        path = Path(output_dir) / CACHE_FILENAME
        cache = cls(path, run_id)
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if loaded.get("run_id") == run_id:
                    cache._data = loaded
            except (json.JSONDecodeError, OSError):
                logger.warning("SCR: verdict cache unreadable, starting fresh: %s", path)
        return cache

    def get(self, feature_id: str, checksum: str) -> Optional[dict]:
        entry = self._data.get("verdicts", {}).get(feature_id)
        if entry and entry.get("checksum") == checksum:
            return entry.get("payload")
        return None

    def put(self, feature_id: str, checksum: str, payload: dict) -> None:
        self._data.setdefault("verdicts", {})[feature_id] = {
            "checksum": checksum,
            "payload": payload,
        }

    def save(self) -> None:
        try:
            atomic_write_json(self.path, self._data, indent=2)
        except Exception:  # pragma: no cover - best effort
            logger.warning("SCR: failed to persist verdict cache: %s", self.path, exc_info=True)
