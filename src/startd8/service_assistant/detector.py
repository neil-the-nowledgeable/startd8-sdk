"""Filesystem detection + idempotency cursor for the Service Assistant.

Implements FR-1 (run sentinel), FR-2 (post-mortem sentinel), FR-3 (idempotent cursor),
FR-4 (ordering tolerance), and FR-13 (hard-abort detection). Detection is a one-shot
filesystem *scan* — there is no daemon (NR-2).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..logging_config import get_logger
from ..utils.file_operations import atomic_write_json

logger = get_logger(__name__)

RUN_SENTINEL_GLOB = "prime-result*.json"
POSTMORTEM_SENTINEL = "prime-postmortem-report.json"
STATE_FILE = ".prime_contractor_state.json"
CURSOR_FILENAME = "service-assistant-cursor.json"

# A state file older than this with no result is treated as a crashed run (FR-13).
HARD_ABORT_STALENESS_SECONDS = 60


@dataclass
class DetectionResult:
    """What a single scan of a run output dir found."""

    output_dir: Path
    run_id: str
    run_sentinel: Optional[Path]
    postmortem_sentinel: Optional[Path]
    state_file: Optional[Path]
    hard_abort: bool
    features_attempted: Optional[int]
    aux_signals: Any = None  # models.AuxSignals; Any to avoid an import cycle

    @property
    def run_sentinel_present(self) -> bool:
        return self.run_sentinel is not None

    @property
    def postmortem_present(self) -> bool:
        return self.postmortem_sentinel is not None

    @property
    def state_file_present(self) -> bool:
        return self.state_file is not None

    @property
    def status(self) -> str:
        """Coarse run status derived from on-disk evidence."""
        if self.hard_abort:
            return "aborted"
        if not self.run_sentinel_present:
            return "in_progress"  # state present but no result yet (FR-4)
        if not self.postmortem_present:
            return "partial"  # result present, post-mortem not yet (FR-4)
        return "completed"

    @property
    def checksum(self) -> str:
        """Stable fingerprint of the run artifacts, for cursor dedup (FR-3)."""
        h = hashlib.sha256()
        for path in (self.run_sentinel, self.postmortem_sentinel):
            if path and path.is_file():
                h.update(path.read_bytes())
        return f"sha256:{h.hexdigest()[:32]}"

    @property
    def actionable(self) -> bool:
        """True when there is enough on disk to triage (run done, aborted, or aux errors)."""
        aux_total = getattr(self.aux_signals, "total", 0) if self.aux_signals else 0
        return self.run_sentinel_present or self.hard_abort or bool(aux_total)


def resolve_run_id(output_dir: Path, explicit_id: Optional[str] = None) -> str:
    """Derive the run id (mirrors ``run_prime_postmortem._resolve_run_id``).

    Order: explicit arg -> run-metadata.json -> KAIZEN_RUN_ID env -> ``run-*`` dir name.
    """
    if explicit_id:
        return explicit_id

    for parent in (output_dir, output_dir.parent):
        meta_path = parent / "run-metadata.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                rid = meta.get("run_id", "")
                if rid:
                    return rid
            except (json.JSONDecodeError, OSError):
                pass

    env_id = os.environ.get("KAIZEN_RUN_ID", "")
    if env_id and env_id != "latest":
        return env_id

    for parent in (output_dir.parent, output_dir):
        if parent.name.startswith("run-"):
            return parent.name

    return "unknown"


def _count_jsonl_lines(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def scan_aux_error_sources(output_dir: Path) -> "AuxSignals":
    """Detect auxiliary error stores beyond the run/post-mortem sentinels (HOWL prior art).

    Looks for the same error surfaces the Coyote HOWL watcher monitored:
    failed phase checkpoints, the ``.startd8/task_errors`` error store, and per-task
    ``PI-*-error.json`` files. Presence + counts are surfaced; contents are not parsed.
    """
    from .models import AuxSignals

    output_dir = Path(output_dir)
    sources: list[str] = []

    failed_checkpoints = 0
    for cp in output_dir.glob("checkpoints/*.checkpoint.json"):
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        status = str(data.get("status", "")).lower()
        if status in ("failed", "error") or data.get("error"):
            failed_checkpoints += 1
            sources.append(str(cp))

    pi_errors = 0
    for pe in output_dir.glob("PI-*-error.json"):
        pi_errors += 1
        sources.append(str(pe))

    task_errors = 0
    for parent in [output_dir, *output_dir.parents][:6]:
        errors_file = parent / ".startd8" / "task_errors" / "errors.jsonl"
        if errors_file.is_file():
            task_errors = _count_jsonl_lines(errors_file)
            if task_errors:
                sources.append(str(errors_file))
            break

    return AuxSignals(
        failed_checkpoints=failed_checkpoints,
        task_errors=task_errors,
        pi_errors=pi_errors,
        sources=sources,
    )


def detect_run(output_dir: Path, explicit_run_id: Optional[str] = None) -> DetectionResult:
    """Scan a single run output dir for run/post-mortem sentinels and aborts."""
    output_dir = Path(output_dir)

    run_sentinels = sorted(output_dir.glob(RUN_SENTINEL_GLOB))
    run_sentinel = run_sentinels[0] if run_sentinels else None

    pm_path = output_dir / POSTMORTEM_SENTINEL
    postmortem_sentinel = pm_path if pm_path.is_file() else None

    state_path = output_dir / STATE_FILE
    state_file = state_path if state_path.is_file() else None

    hard_abort = False
    features_attempted: Optional[int] = None
    if state_file is not None and run_sentinel is None:
        # State written before generation; no result => possible crash (FR-13).
        age = time.time() - state_file.stat().st_mtime
        if age >= HARD_ABORT_STALENESS_SECONDS:
            hard_abort = True
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
                features_attempted = len(state.get("order", []))
            except (json.JSONDecodeError, OSError):
                features_attempted = None

    return DetectionResult(
        output_dir=output_dir,
        run_id=resolve_run_id(output_dir, explicit_run_id),
        run_sentinel=run_sentinel,
        postmortem_sentinel=postmortem_sentinel,
        state_file=state_file,
        hard_abort=hard_abort,
        features_attempted=features_attempted,
        aux_signals=scan_aux_error_sources(output_dir),
    )


# ---------------------------------------------------------------------------
# Idempotency cursor (FR-3) — per pipeline-output base, keyed by run_id (OQ-8).
# ---------------------------------------------------------------------------


def cursor_path_for(output_dir: Path) -> Path:
    """Locate the cursor file at the pipeline-output base (parent of run-* dirs)."""
    output_dir = Path(output_dir)
    for parent in (output_dir.parent, output_dir.parent.parent):
        if parent.name.startswith("run-"):
            return parent.parent / CURSOR_FILENAME
    # Fallback: alongside the run dir.
    return output_dir.parent / CURSOR_FILENAME


def _load_cursor(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Service Assistant cursor unreadable, treating as empty: %s", path)
    return {"schema_version": "1.0", "processed": {}}


def already_processed(detection: DetectionResult) -> tuple[bool, Path]:
    """Return (seen_before, cursor_path) for this run+checksum (FR-3)."""
    path = cursor_path_for(detection.output_dir)
    cursor = _load_cursor(path)
    entry = cursor.get("processed", {}).get(detection.run_id)
    seen = bool(entry) and entry.get("checksum") == detection.checksum
    return seen, path


def record_processed(detection: DetectionResult, cursor_path: Path) -> None:
    """Mark this run+checksum as handled so re-invocation is a no-op (FR-3)."""
    cursor = _load_cursor(cursor_path)
    cursor.setdefault("processed", {})[detection.run_id] = {
        "checksum": detection.checksum,
        "status": detection.status,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        atomic_write_json(cursor_path, cursor, indent=2)
    except Exception:  # pragma: no cover - cursor write is best-effort
        logger.warning("Failed to persist Service Assistant cursor: %s", cursor_path, exc_info=True)
