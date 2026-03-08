"""
ElementRegistry: Persistent, thread-safe, index-addressable element store.

Stores ElementEntry records as individual JSON files on disk under a configurable
state_dir, maintains a shared in-memory index keyed by element_id, supports
multi-phase status tracking with full history, enables element lookup by source
file path, and produces aggregate summary statistics.

Thread-safety
-------------
All public methods are protected by a single ``threading.RLock``.  Re-entrant
locking allows internal helpers (e.g. ``summary()`` called from
``write_run_metrics()``) to acquire the lock without deadlocking.

Persistence
-----------
Each ElementEntry is stored as an individual, prettily-formatted JSON file under
``<state_dir>/elements/<sha256_prefix>.json``.  Writes are atomic: data is
written to a ``.tmp`` sibling first, then renamed via ``os.replace()``.

Run metrics snapshots are stored under ``<state_dir>/runs/<run_id>.json`` using
the same atomic write strategy.

Failure modes
-------------
* File I/O errors during write are logged at ERROR level; the in-memory index
  is still updated so that the current process continues to work.
* File I/O errors during reads (load phase) are logged at WARNING level and
  the offending file is skipped.
* Missing elements referenced by helper methods are logged at WARNING level;
  the method returns a sensible empty/None value.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class PhaseRecord:
    """Record of a single phase-status transition at a point in time."""

    phase: str
    status: str
    timestamp: str  # ISO-8601 UTC, e.g. "2024-01-15T12:00:00Z"
    metadata: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ElementEntry:
    """
    Complete record for a single tracked element (function, class, module, …).

    ``phases`` maps phase-name → ordered list of PhaseRecord objects (oldest
    first).  ``extra`` is a free-form bag for arbitrary caller-supplied data.
    """

    element_id: str
    kind: str
    name: str
    file_path: Optional[str] = None
    parent_class: Optional[str] = None
    line: Optional[int] = None
    source_contract_id: Optional[str] = None
    context_checksum: Optional[str] = None
    phases: dict = dataclasses.field(default_factory=dict)  # phase → list[PhaseRecord]
    extra: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class RegistrySummary:
    """Aggregate statistics over all elements currently in the registry."""

    total: int
    by_kind: dict         # element_kind → count
    by_phase_status: dict  # phase → status → count  (latest status only)
    files_covered: int


@dataclasses.dataclass
class ElementLineage:
    """Complete lineage and status history for a single element."""

    element_id: str
    history: list         # list[PhaseRecord] — all records, time-sorted ascending
    current_phases: dict  # phase → latest_status


@dataclasses.dataclass
class ReconciliationReport:
    """Result of comparing the live registry against an external backup source."""

    matched: list  # element IDs present in both registry and backup
    missing: list  # element IDs in backup but absent from registry
    extra: list    # element IDs in registry but absent from backup
    tool: str      # identifier of the backup tool / source


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _phase_record_to_dict(pr: PhaseRecord) -> dict:
    return {
        "phase": pr.phase,
        "status": pr.status,
        "timestamp": pr.timestamp,
        "metadata": pr.metadata,
    }


def _phase_record_from_dict(data: dict) -> PhaseRecord:
    return PhaseRecord(
        phase=data["phase"],
        status=data["status"],
        timestamp=data.get("timestamp", ""),
        metadata=data.get("metadata", {}),
    )


def _entry_to_dict(entry: ElementEntry) -> dict:
    return {
        "element_id": entry.element_id,
        "kind": entry.kind,
        "name": entry.name,
        "file_path": entry.file_path,
        "parent_class": entry.parent_class,
        "line": entry.line,
        "source_contract_id": entry.source_contract_id,
        "context_checksum": entry.context_checksum,
        "phases": {
            phase: [_phase_record_to_dict(r) for r in records]
            for phase, records in entry.phases.items()
        },
        "extra": entry.extra,
    }


def _entry_from_dict(data: dict) -> ElementEntry:
    return ElementEntry(
        element_id=data["element_id"],
        kind=data["kind"],
        name=data["name"],
        file_path=data.get("file_path"),
        parent_class=data.get("parent_class"),
        line=data.get("line"),
        source_contract_id=data.get("source_contract_id"),
        context_checksum=data.get("context_checksum"),
        phases={
            phase: [_phase_record_from_dict(r) for r in records]
            for phase, records in data.get("phases", {}).items()
        },
        extra=data.get("extra", {}),
    )


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _safe_filename(element_id: str) -> str:
    """
    Derive a filesystem-safe basename from *element_id*.

    Uses the first 40 hex characters of the SHA-256 digest so that arbitrarily
    long or special-character IDs map to stable, collision-resistant filenames.
    """
    return hashlib.sha256(element_id.encode("utf-8")).hexdigest()[:40]


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a ``Z`` suffix."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _sanitize_run_id(run_id: str) -> str:
    """Replace path-separator characters in *run_id* so it is safe as a filename."""
    return run_id.replace("/", "_").replace("\\", "_")


# ---------------------------------------------------------------------------
# ElementRegistry
# ---------------------------------------------------------------------------


class ElementRegistry:
    """
    Persistent, thread-safe registry of ElementEntry records.

    Parameters
    ----------
    state_dir:
        Root directory for all persistent storage.  The registry will create
        two sub-directories:

        * ``elements/`` — one JSON file per element.
        * ``runs/``     — one JSON snapshot file per ``write_run_metrics()`` call.

        If *state_dir* is ``None`` a temporary directory is created
        automatically (useful for testing).

    Usage
    -----
    >>> reg = ElementRegistry("/var/lib/my_tool/registry")
    >>> reg.put(ElementEntry(element_id="pkg.mod.Foo.bar", kind="method", name="bar"))
    >>> reg.set_phase_status("pkg.mod.Foo.bar", phase="lint", status="passed")
    >>> reg.get_phase_status("pkg.mod.Foo.bar", "lint")
    'passed'
    >>> reg.summary().total
    1
    """

    def __init__(self, state_dir: Path | str | None = None) -> None:
        self._lock = threading.RLock()

        if state_dir is None:
            self._state_dir = Path(tempfile.mkdtemp(prefix="element_registry_"))
        else:
            self._state_dir = Path(state_dir)

        self._elements_dir = self._state_dir / "elements"
        self._runs_dir = self._state_dir / "runs"
        self._elements_dir.mkdir(parents=True, exist_ok=True)
        self._runs_dir.mkdir(parents=True, exist_ok=True)

        # In-memory index: element_id → ElementEntry
        self._index: dict[str, ElementEntry] = {}
        self._index_loaded: bool = False

    # ------------------------------------------------------------------
    # Private helpers  (must be called while holding self._lock)
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """
        Populate ``self._index`` from disk on the first call (lazy load).

        Idempotent; subsequent calls return immediately.  Corrupt or
        unreadable files are skipped with a WARNING log entry.
        """
        if self._index_loaded:
            return

        for json_file in sorted(self._elements_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                entry = _entry_from_dict(data)
                self._index[entry.element_id] = entry
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ElementRegistry: skipping corrupt file %s — %s", json_file, exc
                )

        self._index_loaded = True

    def _entry_path(self, element_id: str) -> Path:
        """Return the canonical ``Path`` for *element_id*'s JSON file."""
        return self._elements_dir / f"{_safe_filename(element_id)}.json"

    def _write_entry(self, entry: ElementEntry) -> None:
        """
        Atomically persist *entry* to disk.

        Writes to a ``.tmp`` sibling first, then calls ``os.replace()`` to
        ensure the target file is never partially written.  On failure the
        ``.tmp`` file is removed and the error is logged; the in-memory index
        is *not* rolled back so the current process continues to function.
        """
        path = self._entry_path(entry.element_id)
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(_entry_to_dict(entry), indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, path)
        except OSError as exc:
            logger.error(
                "ElementRegistry: atomic write failed for element %r — %s",
                entry.element_id,
                exc,
            )
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def get(self, element_id: str) -> Optional[ElementEntry]:
        """
        Return the ``ElementEntry`` for *element_id*, or ``None`` if absent.

        Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            return self._index.get(element_id)

    def put(self, entry: ElementEntry) -> None:
        """
        Insert or replace an ``ElementEntry``.

        Persists to disk atomically and updates the in-memory index.
        Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            self._write_entry(entry)
            self._index[entry.element_id] = entry

    def has(self, element_id: str) -> bool:
        """
        Return ``True`` if *element_id* is present in the registry.

        Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            return element_id in self._index

    def remove(self, element_id: str) -> bool:
        """
        Delete the entry for *element_id*.

        Returns ``True`` if the element existed and was removed, ``False`` if
        it was not found.  Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            if element_id not in self._index:
                return False
            try:
                self._entry_path(element_id).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(
                    "ElementRegistry: unlink failed for element %r — %s",
                    element_id,
                    exc,
                )
            del self._index[element_id]
            return True

    def clear(self) -> None:
        """
        Remove *all* entries from the registry (disk and memory).

        Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            for json_file in self._elements_dir.glob("*.json"):
                try:
                    json_file.unlink()
                except OSError as exc:
                    logger.warning(
                        "ElementRegistry: clear could not remove %s — %s",
                        json_file,
                        exc,
                    )
            self._index.clear()

    # ------------------------------------------------------------------
    # File-based lookup
    # ------------------------------------------------------------------

    def elements_for_file(self, file_path: str) -> list[ElementEntry]:
        """
        Return all entries whose ``file_path`` matches *file_path*.

        Paths are normalised via ``str(Path(...))`` before comparison so that
        minor differences in separators or redundant components are tolerated.
        Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            needle = str(Path(file_path))
            return [
                entry
                for entry in self._index.values()
                if entry.file_path is not None
                and str(Path(entry.file_path)) == needle
            ]

    def all_entries(self) -> list[ElementEntry]:
        """Return a snapshot of all entries in the registry.  Thread-safe."""
        with self._lock:
            self._ensure_loaded()
            return list(self._index.values())

    # ------------------------------------------------------------------
    # Phase / status tracking
    # ------------------------------------------------------------------

    def set_phase_status(
        self,
        element_id: str,
        phase: str,
        status: str,
        metadata: dict | None = None,
    ) -> None:
        """
        Append a new phase-status record to *element_id*'s history.

        The record is stamped with the current UTC time.  If *element_id* does
        not exist a WARNING is logged and the call is a no-op.  Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            entry = self._index.get(element_id)
            if entry is None:
                logger.warning(
                    "set_phase_status: element %r not found — ignoring", element_id
                )
                return

            record = PhaseRecord(
                phase=phase,
                status=status,
                timestamp=_now_iso(),
                metadata=metadata or {},
            )
            records = entry.phases.setdefault(phase, [])
            if records:
                # Overwrite the latest record for this phase rather than
                # accumulating duplicates (ER-QW-002).
                records[-1] = record
            else:
                records.append(record)
            self._write_entry(entry)
            # entry is already the object in self._index; update is implicit,
            # but re-assign for explicitness.
            self._index[element_id] = entry

    def get_phase_status(self, element_id: str, phase: str) -> Optional[str]:
        """
        Return the *latest* status string for (element_id, phase).

        Returns ``None`` if the element is not found or the phase has no
        records.  Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            entry = self._index.get(element_id)
            if entry is None:
                return None
            records = entry.phases.get(phase, [])
            return records[-1].status if records else None

    def elements_by_status(self, phase: str, status: str) -> list[ElementEntry]:
        """
        Return all elements whose *latest* status for *phase* equals *status*.

        Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            return [
                entry
                for entry in self._index.values()
                if (
                    (records := entry.phases.get(phase))
                    and records[-1].status == status
                )
            ]

    def element_history(self, element_id: str) -> list[PhaseRecord]:
        """
        Return all ``PhaseRecord`` objects for *element_id*, sorted ascending
        by timestamp.

        Returns an empty list if the element is not found.  Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            entry = self._index.get(element_id)
            if entry is None:
                return []
            all_records: list[PhaseRecord] = [
                record
                for records in entry.phases.values()
                for record in records
            ]
            return sorted(all_records, key=lambda r: r.timestamp)

    # ------------------------------------------------------------------
    # Aggregate statistics
    # ------------------------------------------------------------------

    def summary(self) -> RegistrySummary:
        """
        Compute aggregate statistics over all elements.

        Counts are based on the *latest* status per phase per element.
        Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()

            by_kind: dict[str, int] = {}
            by_phase_status: dict[str, dict[str, int]] = {}
            files: set[str] = set()

            for entry in self._index.values():
                by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1

                if entry.file_path:
                    files.add(entry.file_path)

                for phase, records in entry.phases.items():
                    if not records:
                        continue
                    latest = records[-1].status
                    phase_counts = by_phase_status.setdefault(phase, {})
                    phase_counts[latest] = phase_counts.get(latest, 0) + 1

            return RegistrySummary(
                total=len(self._index),
                by_kind=by_kind,
                by_phase_status=by_phase_status,
                files_covered=len(files),
            )

    # ------------------------------------------------------------------
    # Run metrics
    # ------------------------------------------------------------------

    def write_run_metrics(self, run_id: str) -> None:
        """
        Snapshot the current summary and persist it to
        ``<state_dir>/runs/<run_id>.json``.

        Uses the same atomic write strategy as individual element files.
        ``run_id`` is sanitised before use as a filename.  I/O failures are
        logged at WARNING level and do not raise.  Thread-safe.
        """
        # Acquire summary inside the lock; write outside to minimise hold time.
        snap = self.summary()

        sanitized = _sanitize_run_id(run_id)
        run_file = self._runs_dir / f"{sanitized}.json"
        tmp = run_file.with_suffix(".tmp")

        try:
            payload = {
                "run_id": run_id,
                "timestamp": _now_iso(),
                "summary": dataclasses.asdict(snap),
            }
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, run_file)
        except OSError as exc:
            logger.warning(
                "write_run_metrics: failed to persist metrics for run %r — %s",
                run_id,
                exc,
            )
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def compare_runs(self, run_a: str, run_b: str) -> dict:
        """
        Compare two persisted run-metric snapshots.

        Returns a dict with keys:

        * ``run_a`` — full snapshot dict for *run_a*
        * ``run_b`` — full snapshot dict for *run_b*
        * ``delta`` — ``{total: Δ, files_covered: Δ}`` (run_b minus run_a)

        Returns an empty dict if either snapshot file is missing or corrupt.
        Does not require the registry lock (reads are independent).
        """

        def _load(run_id: str) -> Optional[dict]:
            path = self._runs_dir / f"{_sanitize_run_id(run_id)}.json"
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "compare_runs: cannot load snapshot for run %r — %s", run_id, exc
                )
                return None

        a_data = _load(run_a)
        b_data = _load(run_b)

        if a_data is None or b_data is None:
            return {}

        a_sum = a_data.get("summary", {})
        b_sum = b_data.get("summary", {})

        return {
            "run_a": a_data,
            "run_b": b_data,
            "delta": {
                "total": b_sum.get("total", 0) - a_sum.get("total", 0),
                "files_covered": (
                    b_sum.get("files_covered", 0) - a_sum.get("files_covered", 0)
                ),
            },
        }

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def reconcile(
        self, backup_files: dict[str, str], backup_tool: str
    ) -> ReconciliationReport:
        """
        Compare the live registry against an external backup source.

        Parameters
        ----------
        backup_files:
            Mapping of *element_id* → content-hash (or any string value) as
            reported by the backup tool.  Only the keys are used for set
            comparison.
        backup_tool:
            Human-readable identifier for the backup tool / source.

        Returns
        -------
        ReconciliationReport
            ``matched`` — IDs present in both sources (sorted).
            ``missing`` — IDs in *backup_files* but absent from the registry
                          (i.e. the registry is missing entries).
            ``extra``   — IDs in the registry but absent from *backup_files*
                          (i.e. the registry has entries not in the backup).

        Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            registry_ids = set(self._index.keys())
            backup_ids = set(backup_files.keys())

        return ReconciliationReport(
            matched=sorted(registry_ids & backup_ids),
            missing=sorted(backup_ids - registry_ids),
            extra=sorted(registry_ids - backup_ids),
            tool=backup_tool,
        )

    # ------------------------------------------------------------------
    # Element lineage (ER-018)
    # ------------------------------------------------------------------

    def element_lineage(self, element_id: str) -> Optional[ElementLineage]:
        """Return the complete lineage and status history for an element.

        Collects all phase records across all phases into a single
        time-sorted history, plus a ``current_phases`` dict mapping each
        phase to its latest status.

        Returns ``None`` if the element does not exist.  Thread-safe.
        """
        with self._lock:
            self._ensure_loaded()
            entry = self._index.get(element_id)
            if entry is None:
                return None

            all_records: list[PhaseRecord] = []
            current_phases: dict[str, str] = {}

            for phase, records in entry.phases.items():
                if not records:
                    continue
                all_records.extend(records)
                current_phases[phase] = records[-1].status

            # Sort by timestamp ascending
            all_records.sort(key=lambda r: r.timestamp or "")

            return ElementLineage(
                element_id=element_id,
                history=all_records,
                current_phases=current_phases,
            )

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Return the number of entries currently in the registry."""
        with self._lock:
            self._ensure_loaded()
            return len(self._index)

    def __repr__(self) -> str:
        return (
            f"ElementRegistry(state_dir={str(self._state_dir)!r}, "
            f"loaded={self._index_loaded}, entries={len(self._index)})"
        )