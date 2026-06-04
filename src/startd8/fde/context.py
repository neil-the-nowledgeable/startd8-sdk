# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""FDE posting + idempotency (FR-2 / FR-13 / FR-19 / FR-27 context).

The FDE is "deployed to the project": its project-scoped footprint lives under
``.startd8/fde/`` (auto-created on first invocation; optional ``startd8 fde init``). The
posting bundle (``fde-context.json``) records the project id, SDK + protocol version, and a
``project_context`` block populated by the *same* rules the Service Assistant uses (reused via
``service_assistant.context.load_project_context`` — FDE→SA is the allowed direction, no cycle).

Idempotency (FR-19) mirrors the SA cursor shape but keys on what actually changed: explain on
``run_id`` + consumed-artifact checksums; preflight on plan/requirements checksums. A regenerated
``prime-result.json`` (new mechanism checksum) re-explains rather than serving a stale answer.
"""

from __future__ import annotations

import hashlib
import json
from ..logging_config import get_logger
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .models import PROTOCOL_VERSION

logger = get_logger(__name__)

FDE_DIRNAME = ".startd8/fde"
CONTEXT_FILENAME = "fde-context.json"
CURSOR_FILENAME = "fde-cursor.json"
SCRATCH_DIRNAME = "preflight-scratch"


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def fde_dir(project_root: Path) -> Path:
    return Path(project_root) / FDE_DIRNAME


def checksum_file(path: Path) -> Optional[str]:
    if not Path(path).exists():
        return None
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return f"sha256:{h.hexdigest()}"


def checksum_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def checksum_glob(directory: Path, pattern: str) -> Optional[str]:
    """Stable checksum over all files matching ``pattern`` (sorted). ``None`` if none match."""
    import glob as _glob

    paths = sorted(_glob.glob(str(Path(directory) / pattern)))
    if not paths:
        return None
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).name.encode("utf-8"))
        h.update(Path(p).read_bytes())
    return f"sha256:{h.hexdigest()}"


def checksum_json_excluding(path: Path, exclude_keys: tuple = ()) -> Optional[str]:
    """Checksum a JSON file's content ignoring top-level keys we mutate ourselves.

    The FDE write-back patches ``fde_explanation`` onto the triage; if that field were part
    of the idempotency key, every explain would invalidate its own cursor entry (FR-19). Hash
    a normalized copy with those keys removed so re-invocation on unchanged inputs is a no-op.
    """
    if not Path(path).exists():
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in exclude_keys}
        blob = json.dumps(data, sort_keys=True)
    except Exception:
        return checksum_file(path)
    return f"sha256:{hashlib.sha256(blob.encode('utf-8')).hexdigest()}"


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".fde-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# --------------------------------------------------------------------------------------
# Posting bundle (FR-2)
# --------------------------------------------------------------------------------------


def ensure_posting(project_root: Path, *, sdk_version: str) -> Path:
    """Auto-create ``.startd8/fde/`` and (re)stamp ``fde-context.json``. Idempotent.

    Returns the context file path. Refreshes the SDK-version stamp each invocation so the
    FR-19 staleness key reflects the current SDK.
    """
    d = fde_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    ctx_path = d / CONTEXT_FILENAME

    project_context = _load_project_context(Path(project_root))
    existing: Dict[str, Any] = {}
    if ctx_path.exists():
        try:
            existing = json.loads(ctx_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    bundle = {
        "kind": "fde-context",
        "protocol_version": PROTOCOL_VERSION,
        "sdk_version": sdk_version,
        "created_at": existing.get("created_at") or _utcnow(),
        "updated_at": _utcnow(),
        "project_context": project_context,
    }
    _atomic_write_json(ctx_path, bundle)
    return ctx_path


def _load_project_context(project_root: Path) -> Dict[str, Any]:
    """Reuse SA FR-5 project-context rules (R4-F5). Best-effort; degrades to a minimal block."""
    try:
        from ..service_assistant.context import load_project_context

        pc = load_project_context(project_root)
        # ProjectContext is a dataclass; serialize defensively.
        import dataclasses

        return dataclasses.asdict(pc) if dataclasses.is_dataclass(pc) else dict(pc)
    except Exception:
        logger.debug(
            "FDE: project-context load failed; using minimal block", exc_info=True
        )
        return {"project_id": None, "source": "none"}


def scratch_dir(project_root: Path, key: str) -> Path:
    """Ephemeral, gitignored scratch for Track-2 plan-ingestion (R2-S3). Never the real run dir."""
    safe = key.replace("/", "_").replace(":", "_")[:48]
    d = fde_dir(project_root) / SCRATCH_DIRNAME / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------------------
# Idempotency cursor (FR-13 / FR-19)
# --------------------------------------------------------------------------------------


def cursor_path(project_root: Path) -> Path:
    return fde_dir(project_root) / CURSOR_FILENAME


def _load_cursor(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"schema_version": "1.0", "processed": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("FDE cursor unreadable, treating as empty: %s", path)
        return {"schema_version": "1.0", "processed": {}}


def fingerprint(parts: Dict[str, Optional[str]]) -> str:
    """Stable fingerprint over the keying parts (checksums + sdk_version)."""
    blob = json.dumps({k: parts[k] for k in sorted(parts)}, sort_keys=True)
    return f"sha256:{hashlib.sha256(blob.encode('utf-8')).hexdigest()}"


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
        "processed_at": _utcnow(),
        **{k: v for k, v in parts.items() if v is not None},
    }
    _atomic_write_json(path, cursor)
