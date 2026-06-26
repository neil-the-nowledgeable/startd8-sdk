"""DB → ``docs/kickoff/inputs/*.yaml`` exporter — the bridge that closes the Option-B loop.

The Welcome Mat's input UI is a deterministically-generated (``$0``) CRUD app over a ``schema.prisma``
that models the kickoff inputs as entities. Authors fill the generated forms; the rows land in the
app's SQLite DB. This exporter reads those rows and writes each value back into the kickoff grammar's
``inputs/*.yaml`` via the M6 capture path — so a value collected through the generated UI flows into
the same allow-listed, comment-preserving, round-trip-gated write-back the hand surface uses.

The mapping (DB ``table.column`` → kickoff ``value_path``) is developer-defined config, not user
input; identifiers are still validated to keep the SQL identifier-safe.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from .capture import CaptureError, apply_capture, build_capture_plan
from .manifest import KickoffExperienceConfig

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class FieldMapping:
    """One DB column → one kickoff value_path."""

    table: str
    column: str
    value_path: str

    def _validate(self) -> None:
        if not _IDENT_RE.match(self.table) or not _IDENT_RE.match(self.column):
            raise ValueError(f"unsafe SQL identifier in mapping: {self.table}.{self.column}")


@dataclass(frozen=True)
class ExportResult:
    value_path: str
    value: str
    code: str                 # "ok" | "no_row" | "db_error" | a CaptureCode on a write refusal
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.code == "ok"


def export_db_rows(
    project_root: str | Path,
    db_path: str | Path,
    mapping: Sequence[FieldMapping],
    *,
    config: Optional[KickoffExperienceConfig] = None,
    order_by: str = "createdAt",
) -> List[ExportResult]:
    """Export the latest row's mapped columns into ``inputs/*.yaml`` via the M6 capture path.

    Each value is written through ``build_capture_plan`` + ``apply_capture``, so it inherits the
    allow-list/traversal guard, the comment/order-preserving splice, the round-trip gate, and the
    stale-file precondition. A per-field failure is recorded and does not abort the others.
    """
    if not _IDENT_RE.match(order_by):
        raise ValueError(f"unsafe order_by identifier: {order_by!r}")
    for m in mapping:
        m._validate()

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    out: List[ExportResult] = []
    try:
        for m in mapping:
            try:
                cur = con.execute(
                    f'SELECT "{m.column}" AS v FROM "{m.table}" ORDER BY "{order_by}" DESC LIMIT 1'
                )
                row = cur.fetchone()
            except sqlite3.OperationalError as exc:
                out.append(ExportResult(m.value_path, "", "db_error", str(exc)))
                continue
            if row is None or row["v"] is None:
                out.append(ExportResult(m.value_path, "", "no_row"))
                continue
            value = str(row["v"])
            try:
                plan = build_capture_plan(project_root, m.value_path, value, config=config)
                apply_capture(project_root, plan)
                out.append(ExportResult(m.value_path, value, "ok"))
            except CaptureError as exc:
                out.append(ExportResult(m.value_path, value, exc.code, str(exc)))
    finally:
        con.close()
    return out
