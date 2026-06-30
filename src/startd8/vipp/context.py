# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""VIPP posting + idempotency (FR-3 / FR-13 / FR-18).

The VIPP's project-scoped footprint lives under ``.startd8/vipp/`` (auto-created on first
``run_vipp_negotiate``). The posting bundle (``vipp-context.json``) records the project id and the
SDK + protocol versions; the cursor (``vipp-cursor.json``) keys idempotency on what actually changed —
the inbox content (excluding the volatile ``generated_at``/``envelope_seq``, FR-18) + the project
ground-truth checksum + the SDK version — so a host re-serialize of *unchanged* proposals is a no-op
(CRP R1 B-S1), while a real change re-negotiates rather than serving a stale disposition.

The pure checksum/fingerprint helpers are **reused from** ``startd8.fde.context`` (``vipp`` → ``fde``
is the sanctioned one-way direction, FR-8) rather than re-implemented.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Reuse the FDE's pure, stable hashing helpers (vipp → fde is allowed; no cycle).
from ..fde.context import (  # noqa: F401  (checksum_text re-exported for callers)
    checksum_file,
    checksum_glob,
    checksum_json_excluding,
    checksum_text,
    fingerprint,
)
from ..logging_config import get_logger
from .models import PROTOCOL_VERSION

logger = get_logger(__name__)

VIPP_DIRNAME = ".startd8/vipp"
CONTEXT_FILENAME = "vipp-context.json"
CURSOR_FILENAME = "vipp-cursor.json"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def vipp_dir(project_root: Path) -> Path:
    return Path(project_root) / VIPP_DIRNAME


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".vipp-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def ensure_posting(project_root: Path, *, sdk_version: str) -> Path:
    """Auto-create ``.startd8/vipp/`` and (re)stamp ``vipp-context.json``. Idempotent.

    Refreshes the SDK-version stamp each invocation so the FR-18 staleness key reflects the current
    SDK. Returns the context file path.
    """
    d = vipp_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    ctx_path = d / CONTEXT_FILENAME

    existing: Dict[str, Any] = {}
    if ctx_path.exists():
        try:
            existing = json.loads(ctx_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    bundle = {
        "kind": "vipp-context",
        "protocol_version": PROTOCOL_VERSION,
        "sdk_version": sdk_version,
        "created_at": existing.get("created_at") or utcnow(),
        "updated_at": utcnow(),
    }
    _atomic_write_json(ctx_path, bundle)
    return ctx_path


# --- idempotency cursor (FR-13 / FR-18) -----------------------------------------------------------


def cursor_path(project_root: Path) -> Path:
    return vipp_dir(project_root) / CURSOR_FILENAME


def _load_cursor(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"schema_version": "1.0", "processed": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("VIPP cursor unreadable, treating as empty: %s", path)
        return {"schema_version": "1.0", "processed": {}}


def already_processed(project_root: Path, key: str, fp: str) -> bool:
    cursor = _load_cursor(cursor_path(Path(project_root)))
    entry = cursor.get("processed", {}).get(key)
    return bool(entry and entry.get("fingerprint") == fp)


def record_processed(
    project_root: Path, key: str, fp: str, parts: Dict[str, Any]
) -> None:
    path = cursor_path(Path(project_root))
    cursor = _load_cursor(path)
    cursor.setdefault("processed", {})[key] = {
        "fingerprint": fp,
        "processed_at": utcnow(),
        **{k: v for k, v in parts.items() if v is not None},
    }
    _atomic_write_json(path, cursor)


# The exact source set ``sapper.ground_truth.oracle_for_project`` reads to build the oracle
# (``_GROUND_TRUTH_GLOBS`` + the Controlled Corpus). The idempotency checksum must cover the SAME
# inputs — checksumming only ``*.prisma`` (and an unused friction report) would serve a stale no-op
# when a TS interface or the corpus changed the oracle's verdicts (code-review M2).
_ORACLE_SOURCE_GLOBS = ("**/*.prisma", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx")


def ground_truth_checksum(project_root: Path) -> Optional[str]:
    """Idempotency key over the SAME inputs the oracle is built from (FR-18 / A-S3 / M2).

    Checksums the Prisma/TS/JS source globs plus the Controlled Corpus file — the actual inputs
    ``oracle_for_project`` consumes — so a change that alters a verdict re-negotiates. ``None`` when
    none are present.
    """
    root = Path(project_root)
    parts = [checksum_glob(root, pattern) for pattern in _ORACLE_SOURCE_GLOBS]
    try:
        from ..paths import controlled_corpus_path

        parts.append(checksum_file(controlled_corpus_path(root)))
    except Exception:
        pass
    if all(p is None for p in parts):
        return None
    return checksum_text("|".join(p or "" for p in parts))
