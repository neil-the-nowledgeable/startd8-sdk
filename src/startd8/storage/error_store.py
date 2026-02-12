"""
Unified task error persistence for the StartD8 SDK.

Provides a single location (``.startd8/task_errors/``) for all workflow and
phase errors, making it easy to inspect what failed, when, and why.

Each error is written as an individual JSON file under::

    {project_root}/.startd8/task_errors/{workflow_id}/{timestamp}_{source}.json

The store also maintains a rolling ``errors.jsonl`` (JSON Lines) file for
quick ``tail -f`` or grep-based inspection.

Usage::

    from startd8.storage.error_store import TaskErrorStore

    store = TaskErrorStore(project_root="/path/to/project")
    store.record_error(
        workflow_id="artisan-PI-001",
        source="implement",
        error_message="LLM returned empty output",
        context={"task_id": "PI-001", "chunk_id": "chunk-3"},
    )

    # List recent errors
    errors = store.list_errors(workflow_id="artisan-PI-001")
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

# Default subdirectory under .startd8/
_ERRORS_DIR = "task_errors"
_ERRORS_JSONL = "errors.jsonl"


@dataclass
class TaskError:
    """A structured error record persisted to disk.

    Attributes:
        workflow_id: The workflow execution that produced this error.
        source: Where the error originated (phase name, handler, workflow).
        error_type: Exception class name or error category.
        error_message: Human-readable error description.
        timestamp: ISO-8601 UTC timestamp.
        context: Arbitrary key/value pairs (task_id, chunk_id, feature_id, etc.)
        traceback: Optional Python traceback string.
    """

    workflow_id: str
    source: str
    error_type: str
    error_message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context: Dict[str, Any] = field(default_factory=dict)
    traceback: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        d = asdict(self)
        # Strip None traceback to keep files clean
        if d.get("traceback") is None:
            del d["traceback"]
        return d


class TaskErrorStore:
    """Persist workflow/phase errors to ``.startd8/task_errors/``.

    Thread-safe for concurrent writes (each error gets its own file, and
    the JSONL append uses a single write+flush).

    Args:
        project_root: Absolute path to the project root.  The store
            creates ``.startd8/task_errors/`` underneath it.
        base_dir: Override the ``.startd8`` directory name (mainly for testing).
    """

    def __init__(
        self,
        project_root: str | Path,
        base_dir: str = ".startd8",
    ) -> None:
        self.project_root = Path(project_root)
        self.errors_dir = self.project_root / base_dir / _ERRORS_DIR
        self.jsonl_path = self.errors_dir / _ERRORS_JSONL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_error(
        self,
        workflow_id: str,
        source: str,
        error_message: str,
        *,
        error_type: str = "WorkflowError",
        context: Optional[Dict[str, Any]] = None,
        exception: Optional[BaseException] = None,
    ) -> Path:
        """Persist a single error record.

        Args:
            workflow_id: Workflow execution ID.
            source: Origin of the error (e.g. ``"implement"``, ``"plan"``).
            error_message: Human-readable description.
            error_type: Exception class name or category string.
            context: Optional dict with extra context (task_id, feature_id, …).
            exception: Optional exception — traceback is extracted automatically.

        Returns:
            Path to the written JSON error file.
        """
        tb_str: Optional[str] = None
        if exception is not None:
            error_type = type(exception).__name__
            tb_str = "".join(
                traceback.format_exception(type(exception), exception, exception.__traceback__)
            )

        record = TaskError(
            workflow_id=workflow_id,
            source=source,
            error_type=error_type,
            error_message=error_message,
            context=context or {},
            traceback=tb_str,
        )

        return self._write(record)

    def record_phase_error(
        self,
        workflow_id: str,
        phase: str,
        error_message: str,
        *,
        cost: float = 0.0,
        duration_seconds: float = 0.0,
        exception: Optional[BaseException] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Convenience wrapper for artisan phase failures.

        Args:
            workflow_id: Workflow execution ID.
            phase: Phase name (e.g. ``"implement"``).
            error_message: Error description.
            cost: Cost incurred before failure.
            duration_seconds: Seconds elapsed before failure.
            exception: Optional originating exception.
            extra: Additional context key/value pairs.

        Returns:
            Path to the written JSON error file.
        """
        ctx: Dict[str, Any] = {
            "phase": phase,
            "cost": cost,
            "duration_seconds": duration_seconds,
        }
        if extra:
            ctx.update(extra)

        return self.record_error(
            workflow_id=workflow_id,
            source=phase,
            error_message=error_message,
            error_type="PhaseExecutionError",
            context=ctx,
            exception=exception,
        )

    def record_generation_error(
        self,
        workflow_id: str,
        task_id: str,
        error_message: str,
        *,
        target_file: Optional[str] = None,
        exception: Optional[BaseException] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Convenience wrapper for code-generation task failures.

        Args:
            workflow_id: Workflow execution ID.
            task_id: The task/chunk that failed generation.
            error_message: Error description.
            target_file: Target file path if known.
            exception: Optional originating exception.
            extra: Additional context key/value pairs.

        Returns:
            Path to the written JSON error file.
        """
        ctx: Dict[str, Any] = {"task_id": task_id}
        if target_file:
            ctx["target_file"] = target_file
        if extra:
            ctx.update(extra)

        return self.record_error(
            workflow_id=workflow_id,
            source="generation",
            error_message=error_message,
            error_type="GenerationError",
            context=ctx,
            exception=exception,
        )

    def record_workflow_result_error(
        self,
        workflow_id: str,
        error_message: str,
        *,
        steps: Optional[List[Dict[str, Any]]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        exception: Optional[BaseException] = None,
    ) -> Path:
        """Persist error information from a failed WorkflowResult.

        Args:
            workflow_id: Workflow ID.
            error_message: The WorkflowResult.error string.
            steps: Serialized step results (with per-step errors).
            metrics: Serialized workflow metrics.
            exception: Optional originating exception.

        Returns:
            Path to the written JSON error file.
        """
        ctx: Dict[str, Any] = {}
        if steps:
            failed_steps = [s for s in steps if s.get("error")]
            ctx["failed_steps"] = failed_steps
            ctx["total_steps"] = len(steps)
        if metrics:
            ctx["metrics"] = metrics

        return self.record_error(
            workflow_id=workflow_id,
            source="workflow",
            error_message=error_message,
            error_type="WorkflowResultError",
            context=ctx,
            exception=exception,
        )

    def list_errors(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Read persisted errors, newest first.

        Args:
            workflow_id: Filter to a specific workflow. If None, returns all.
            limit: Maximum number of records to return.

        Returns:
            List of error dicts, sorted by timestamp descending.
        """
        records: List[Dict[str, Any]] = []

        if not self.errors_dir.exists():
            return records

        if workflow_id:
            search_dirs = [self.errors_dir / workflow_id]
        else:
            search_dirs = [
                d for d in self.errors_dir.iterdir()
                if d.is_dir()
            ]

        for d in search_dirs:
            if not d.exists():
                continue
            for f in d.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    records.append(data)
                except (json.JSONDecodeError, OSError):
                    continue

        # Sort newest first
        records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return records[:limit]

    def clear(self, workflow_id: Optional[str] = None) -> int:
        """Remove persisted errors.

        Args:
            workflow_id: Clear only errors for this workflow. If None,
                clears all errors.

        Returns:
            Number of error files removed.
        """
        removed = 0
        if not self.errors_dir.exists():
            return removed

        if workflow_id:
            target = self.errors_dir / workflow_id
            if target.exists():
                for f in target.glob("*.json"):
                    f.unlink(missing_ok=True)
                    removed += 1
                # Remove directory if empty
                try:
                    target.rmdir()
                except OSError:
                    pass
        else:
            for d in self.errors_dir.iterdir():
                if d.is_dir():
                    for f in d.glob("*.json"):
                        f.unlink(missing_ok=True)
                        removed += 1
                    try:
                        d.rmdir()
                    except OSError:
                        pass
            # Clean up JSONL
            if self.jsonl_path.exists():
                self.jsonl_path.unlink(missing_ok=True)

        return removed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write(self, record: TaskError) -> Path:
        """Write a TaskError to both a JSON file and the JSONL log."""
        # Ensure directories exist
        wf_dir = self.errors_dir / record.workflow_id
        wf_dir.mkdir(parents=True, exist_ok=True)

        # Build filename: {timestamp}_{source}.json
        # Use a compact timestamp for filenames (no colons for filesystem compat)
        ts_slug = record.timestamp.replace(":", "").replace("-", "").replace("T", "_")[:15]
        filename = f"{ts_slug}_{record.source}.json"
        filepath = wf_dir / filename

        # Handle filename collisions by appending a counter
        counter = 1
        while filepath.exists():
            filename = f"{ts_slug}_{record.source}_{counter}.json"
            filepath = wf_dir / filename
            counter += 1

        data = record.to_dict()

        try:
            filepath.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError:
            logger.warning(
                "Failed to write error file %s", filepath, exc_info=True,
            )
            return filepath

        # Append to JSONL for quick scanning
        try:
            self.errors_dir.mkdir(parents=True, exist_ok=True)
            with open(self.jsonl_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(data, default=str) + "\n")
                fh.flush()
        except OSError:
            logger.debug(
                "Failed to append to JSONL log %s", self.jsonl_path, exc_info=True,
            )

        logger.debug(
            "Recorded error for workflow=%s source=%s: %s",
            record.workflow_id, record.source, record.error_message[:120],
        )
        return filepath
