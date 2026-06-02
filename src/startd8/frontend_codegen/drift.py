"""Drift / staleness checking (Inc 8 / FR-11).

The standalone CI value: compare an on-disk owned file against what the schema *would*
generate, with a two-stage check that distinguishes the two operationally-different
failures (R2-S6):

1. **stale** — the schema changed but the file wasn't regenerated (caught cheaply by the
   embedded ``schema-sha256`` header vs the current schema hash).
2. **tampered** — the schema is unchanged but the owned file was hand-edited (caught by a
   full re-render comparison).

Exit-code contract: ``0`` in-sync, ``1`` drift (stale/tampered/missing), ``2`` error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .schema_renderer import render_zod_schema, schema_sha256

IN_SYNC = 0
DRIFT = 1
ERROR = 2

_HEADER_SHA_RE = re.compile(r"//\s*schema-sha256:\s*([0-9a-f]{64})")


@dataclass(frozen=True)
class DriftResult:
    """Outcome of a drift check. ``exit_code`` follows the FR-11 contract."""

    status: str  # "in_sync" | "stale" | "tampered" | "missing"
    exit_code: int
    detail: str


def embedded_schema_sha(ondisk_text: str) -> Optional[str]:
    """The ``schema-sha256`` recorded in a generated file's header, or ``None``."""
    m = _HEADER_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def check_drift(
    schema_text: str,
    ondisk_text: Optional[str],
    *,
    source_file: str = "prisma/schema.prisma",
) -> DriftResult:
    """Compare an on-disk owned file against the schema (FR-11). No writes.

    ``ondisk_text is None`` means the file is absent (drift — it should exist). Otherwise:
    a missing/old embedded hash means tampered/stale; matching hash with differing bytes
    means tampered; matching hash and bytes means in-sync.
    """
    if ondisk_text is None:
        return DriftResult("missing", DRIFT, "owned file does not exist on disk")

    current_sha = schema_sha256(schema_text)
    embedded = embedded_schema_sha(ondisk_text)
    if embedded is None:
        return DriftResult(
            "tampered",
            DRIFT,
            "no schema-sha256 header — file was not generated or the header was stripped",
        )
    if embedded != current_sha:
        return DriftResult(
            "stale",
            DRIFT,
            f"schema changed (header {embedded[:12]}… != current {current_sha[:12]}…) "
            f"— regenerate",
        )

    rendered = render_zod_schema(schema_text, source_file=source_file).text
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned file was hand-edited (content differs from a fresh render of the "
            "unchanged schema)",
        )
    return DriftResult("in_sync", IN_SYNC, "owned file matches the schema")
