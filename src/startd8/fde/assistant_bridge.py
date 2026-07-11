# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Service Assistant handshake (FR-17 / FR-24).

One-directional coupling: the FDE reads the SA triage **only as a JSON artifact** (no typed
``TriageReport`` import — no build/version lockstep) and patches an ``fde_explanation`` ref
back onto it. SA never imports the ``fde`` package. ``FdeRef`` is owned by
``service_assistant.models`` (we construct the same dict shape here without importing it at
module scope, to keep the import graph clean for the deterministic core).
"""

from __future__ import annotations

import hashlib
import json
from ..logging_config import get_logger
import os
import tempfile
from pathlib import Path
from typing import Optional

from .models import PROTOCOL_VERSION

logger = get_logger(__name__)

TRIAGE_FILENAME = "service-assistant-triage.json"
TRIAGE_MD_FILENAME = "service-assistant-triage.md"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return f"sha256:{h.hexdigest()}"


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".fde-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)  # atomic on POSIX
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def attach_fde_ref_to_triage(run_output_dir: Path, explanation_md_path: Path) -> bool:
    """Atomically patch the SA triage with an ``fde_explanation`` ref (FR-24 write-back).

    Returns True on success. Returns False (logged) if the triage is absent or unreadable —
    the caller treats that as a partial success (explanation written, ref not attached) and
    exits non-zero. The FDE never *creates* the triage; SA owns it.
    """
    run_output_dir = Path(run_output_dir)
    triage_path = run_output_dir / TRIAGE_FILENAME
    if not triage_path.exists():
        logger.warning("FDE: no %s to attach ref to (partial success)", TRIAGE_FILENAME)
        return False
    if not explanation_md_path.exists():
        logger.warning(
            "FDE: explanation %s missing; cannot attach ref", explanation_md_path
        )
        return False
    try:
        triage = json.loads(triage_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning(
            "FDE: %s is unreadable; cannot attach ref", TRIAGE_FILENAME, exc_info=True
        )
        return False

    triage["fde_explanation"] = {
        "report_path": str(explanation_md_path),
        "checksum": _sha256(explanation_md_path),
        "generated_at": _utcnow(),
        "protocol_version": PROTOCOL_VERSION,
    }
    try:
        _atomic_write_json(triage_path, triage)
    except OSError:
        # A write failure (permissions, full disk) must not crash the explain run — the
        # explanation itself is already written; report partial success (FR-24).
        logger.warning(
            "FDE: failed to write fde_explanation ref to %s (partial success)",
            TRIAGE_FILENAME,
            exc_info=True,
        )
        return False
    _append_markdown_link(run_output_dir / TRIAGE_MD_FILENAME, explanation_md_path)
    return True


def _append_markdown_link(triage_md: Path, explanation_md: Path) -> None:
    """R4-S4: surface the explanation link in the triage markdown operators already open.

    Idempotent — does not duplicate the line on re-attach. Best-effort.
    """
    if not triage_md.exists():
        return
    marker = "**FDE mechanism explanation:**"
    try:
        text = triage_md.read_text(encoding="utf-8")
        if marker in text:
            return
        text += f"\n\n{marker} [{explanation_md.name}]({explanation_md.name})\n"
        triage_md.write_text(text, encoding="utf-8")
    except Exception:  # pragma: no cover - best-effort
        logger.debug("FDE: failed to append link to %s", triage_md, exc_info=True)


def detect_relocated_ref(triage: dict) -> Optional[str]:
    """FR-24 / R1-F15: detect a dangling ref whose path no longer resolves.

    Returns a human message if the ref's ``report_path`` is missing but a same-name file
    exists in the triage's own dir (relocated run), else None.
    """
    ref = triage.get("fde_explanation")
    if not ref:
        return None
    rp = Path(ref.get("report_path", ""))
    if rp.exists():
        return None
    return (
        f"fde_explanation ref points at a missing path ({rp}); the run dir may have been "
        f"relocated. Re-run `startd8 fde explain` to refresh the ref."
    )
