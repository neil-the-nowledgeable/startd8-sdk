"""Local terminal/events/checkpoint output for benchmark operators.

This module observes benchmark execution. It never participates in scoring or changes a cell result.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO

from ..fde.redaction import redact


@dataclass(frozen=True)
class OperatorEvent:
    timestamp: str
    run_id: str
    event: str
    stage: str
    message: str
    cell_id: Optional[str] = None
    service: Optional[str] = None
    model: Optional[str] = None
    repetition: Optional[int] = None
    data: Optional[dict[str, Any]] = None


class OperatorOutput:
    """Emit concise text plus optional JSONL and atomically replaced checkpoints."""

    def __init__(self, run_id: str, output_dir: Path, *, quiet: bool = False, json_events: Optional[Path | str] = None,
                 text_stream: TextIO = sys.stdout) -> None:
        self.run_id = run_id
        self.output_dir = Path(output_dir)
        self.quiet = quiet
        self.json_events = json_events
        self.text_stream = text_stream

    @staticmethod
    def _clean(value: Any) -> Any:
        if isinstance(value, str):
            return redact(value)[0].replace(str(Path.home()), "~")
        if isinstance(value, dict):
            return {str(k): OperatorOutput._clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [OperatorOutput._clean(v) for v in value]
        return value

    def emit(self, event: str, stage: str, message: str, *, cell: Any = None,
             data: Optional[dict[str, Any]] = None) -> OperatorEvent:
        payload = OperatorEvent(
            timestamp=datetime.now(timezone.utc).isoformat(), run_id=self.run_id,
            event=event, stage=stage, message=self._clean(message),
            cell_id=getattr(cell, "cell_id", None), service=getattr(cell, "service", None),
            model=getattr(cell, "model", None), repetition=getattr(cell, "repetition", None),
            data=self._clean(data) if data else None,
        )
        if not self.quiet:
            prefix = f"[{payload.event}:{payload.stage}]"
            cell_label = f" {payload.cell_id}" if payload.cell_id else ""
            print(f"{prefix}{cell_label} {payload.message}", file=self.text_stream, flush=True)
        if self.json_events == "-":
            print(json.dumps(asdict(payload), default=str), file=sys.stdout, flush=True)
        elif self.json_events:
            self.json_events.parent.mkdir(parents=True, exist_ok=True)
            with self.json_events.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(payload), default=str) + "\n")
        return payload

    @staticmethod
    def _atomic_json(path: Path, value: Any) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")
        temp.replace(path)

    def checkpoint(self, cells: list[Any], aggregate: dict[str, Any], total_cells: int) -> None:
        """Best-effort local state; exceptions are intentionally owned by the caller."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        serialized = [cell.to_dict() if hasattr(cell, "to_dict") else cell for cell in cells]
        self._atomic_json(self.output_dir / "cells.json", serialized)
        self._atomic_json(self.output_dir / "aggregate.json", aggregate)
        spent = sum(float((item.get("cost_usd") or 0)) for item in serialized)
        statuses: dict[str, int] = {}
        for item in serialized:
            status = str(item.get("status", "unknown"))
            statuses[status] = statuses.get(status, 0) + 1
        self._atomic_json(self.output_dir / "progress.json", {
            "run_id": self.run_id, "completed_cells": len(serialized), "total_cells": total_cells,
            "status_counts": statuses, "actual_cost_usd": spent,
            "latest_event_utc": datetime.now(timezone.utc).isoformat(),
            "artifacts": ["run-spec.json", "cells.json", "aggregate.json", "leaderboard.md"],
        })
