"""Drift / staleness checking for the Python contract-codegen path.

The Python sibling of ``frontend_codegen.drift``. The two-stage check is the same operational
idea (R2-S6) — distinguish **stale** (schema changed, file not regenerated; caught cheaply by the
embedded ``schema-sha256``) from **tampered** (schema unchanged, file hand-edited; caught by a full
re-render comparison) — but it is *mirrored, not reused*: a ``.py`` file carries a ``#`` GENERATED
header (not the TS ``//``), and the re-render goes through :func:`render_pydantic_models`. Both are
hardwired in ``frontend_codegen.drift``, so the regexes and renderer differ here.

Exit-code contract: ``0`` in-sync, ``1`` drift (stale/tampered/missing), ``2`` error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..frontend_codegen.schema_renderer import schema_sha256
from .pydantic_renderer import render_pydantic_models

IN_SYNC = 0
DRIFT = 1
ERROR = 2

_HEADER_SHA_RE = re.compile(r"#\s*schema-sha256:\s*([0-9a-f]{64})")
_HEADER_SRC_RE = re.compile(r"#\s*GENERATED from\s+(\S+)")
_GENERATED_MARKER = "# GENERATED from"


@dataclass(frozen=True)
class DriftResult:
    """Outcome of a drift check. ``exit_code`` follows the contract above."""

    status: str  # "in_sync" | "stale" | "tampered" | "missing"
    exit_code: int
    detail: str


def embedded_schema_sha(ondisk_text: str) -> Optional[str]:
    """The ``schema-sha256`` recorded in a generated file's header, or ``None``."""
    m = _HEADER_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_source_file(ondisk_text: str) -> Optional[str]:
    """The ``GENERATED from <source_file>`` label recorded in a generated header, or ``None``."""
    m = _HEADER_SRC_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def is_owned_generated_file(ondisk_text: str) -> bool:
    """True if *ondisk_text* is a file this generator produced (carries the GENERATED header).

    Necessary but **not** sufficient to skip in the pipeline — a stale/hand-edited file also
    carries the header. Pair with :func:`owned_file_in_sync` before treating it as provided.
    """
    text = ondisk_text or ""
    return _GENERATED_MARKER in text and embedded_schema_sha(text) is not None


def owned_file_in_sync(schema_text: str, ondisk_text: str) -> bool:
    """True iff *ondisk_text* is an owned generated file that is **currently in-sync**.

    The safe predicate for the pipeline skip-hook: header presence alone is rejected; the file
    must re-render byte-identically from the current schema. The embedded source-label is
    recovered so the re-render's header line matches (avoiding a false "tampered"). Any doubt →
    ``False`` (the caller falls through to the LLM — a safe failure).
    """
    if not is_owned_generated_file(ondisk_text):
        return False
    source_file = embedded_source_file(ondisk_text) or "prisma/schema.prisma"
    return (
        check_drift(schema_text, ondisk_text, source_file=source_file).status
        == "in_sync"
    )


def check_drift(
    schema_text: str,
    ondisk_text: Optional[str],
    *,
    source_file: str = "prisma/schema.prisma",
) -> DriftResult:
    """Compare an on-disk owned file against the schema. No writes.

    ``ondisk_text is None`` means the file is absent (drift — it should exist). Otherwise: a
    missing/old embedded hash means tampered/stale; matching hash with differing bytes means
    tampered; matching hash and bytes means in-sync.
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

    rendered = render_pydantic_models(schema_text, source_file=source_file).text
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned file was hand-edited (content differs from a fresh render of the "
            "unchanged schema)",
        )
    return DriftResult("in_sync", IN_SYNC, "owned file matches the schema")
