# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Render a triage into a requirements-backlog section, and guard-append it into an existing doc.

FR-6 — :func:`render_backlog_section` is a pure, byte-stable ($0) renderer over a :class:`TriageReport`
(the same report the triage produces — one extraction, two renderers). FR-7/FR-14 — :func:`append_backlog`
performs a *guarded* append into an existing ``ENHANCEMENTS_BACKLOG.md``:

* **idempotent** — the block is wrapped in ``<!-- startd8-panel-backlog: <sid> -->`` markers; a re-run
  replaces only that block (H-18).
* **marker-injection safe** — refuses to write if the rendered block itself contains a marker (H-16).
* **deterministic insertion** — before the last ``*italic footer*`` line, else EOF (H-17).
* **fail-closed** — missing/unwritable target, or a malformed existing marker pair, aborts (H-18).
* **atomic** — temp file in the target's own directory, ``os.replace``, mode preserved; symlinks are
  resolved-and-replaced, never clobbered (H-19).
* **preview-default** — without ``confirm=True`` it computes but does not write; the CLI maps this to a
  ``polish check``-style exit code (0 = in-sync, 2 = would-write) (H-21).
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .models import InputKind, Lane, TriageReport

MARKER_TOKEN = "startd8-panel-backlog"


def _marker_open(sid: str) -> str:
    return f"<!-- {MARKER_TOKEN}: {sid} -->"


def _marker_close(sid: str) -> str:
    return f"<!-- /{MARKER_TOKEN}: {sid} -->"


# input_kind → backlog subheading, in a FIXED render order (H-20 byte-stability).
_KIND_GROUPS: List[tuple[str, tuple[InputKind, ...]]] = [
    ("Prioritized improvements & suggestions", (InputKind.recommendation, InputKind.suggestion)),
    ("Open questions (human decisions)", (InputKind.question,)),
    ("Tensions & trade-offs", (InputKind.tension,)),
    ("Risks", (InputKind.risk,)),
    ("Decisions & constraints", (InputKind.decision, InputKind.constraint)),
    ("Other captured input (residual)", (InputKind.feedback, InputKind.content, InputKind.uncategorized)),
]


def render_backlog_section(report: TriageReport, *, title: str = "", project: str = "") -> str:
    """FR-6 — a byte-stable markdown backlog section from a triage report. Empty report → ``""`` (H-5)."""
    if not report.candidates:
        return ""
    heading = title or f"Stakeholder-panel input — {report.session_id}"
    proj = f" ({project})" if project else ""
    lines: List[str] = [
        f"## {heading}",
        "",
        f"> **Provenance.** Stakeholder-panel session `{report.session_id}`{proj}. "
        "**SYNTHETIC & UNRATIFIED** — panel input for your judgment, not a decision; ratify before "
        "building. Field-level VIPP candidates (if any) are handled separately by the apply pipeline.",
        "",
    ]
    for subheading, kinds in _KIND_GROUPS:
        group = [c for c in report.candidates if c.input_kind in kinds]  # candidate order preserved (stable)
        if not group:
            continue
        lines += [f"### {subheading}", ""]
        for c in group:
            tag = "" if c.lane is not Lane.UNSTRUCTURED else " _(unstructured)_"
            lines.append(f"- {c.raw_text}{tag} — _{c.source_section} · {c.input_kind.value}_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ─────────────────────────────── guarded append (FR-14) ────────────────────────────────

@dataclass
class AppendResult:
    action: str  # "no-op" | "would-write" | "written"
    reason: str
    new_content: str  # the full file content after append (for preview/diff)


class BacklogAppendError(RuntimeError):
    """Fail-closed diagnostic for the guarded append (missing file, malformed marker, injection)."""


def _find_marked_block(text: str, sid: str) -> Optional[tuple[int, int]]:
    """Return (start, end) char offsets of the existing marked block for *sid*, or None. Fail-closed on
    an unclosed or duplicated opener (H-18)."""
    open_m = _marker_open(sid)
    close_m = _marker_close(sid)
    opens = [m.start() for m in re.finditer(re.escape(open_m), text)]
    closes = [m.end() for m in re.finditer(re.escape(close_m), text)]
    if not opens and not closes:
        return None
    if len(opens) != 1 or len(closes) != 1 or closes[0] < opens[0]:
        raise BacklogAppendError(
            f"target has a malformed/duplicated marker for session {sid!r} "
            f"({len(opens)} open, {len(closes)} close) — refusing to guess the region"
        )
    return opens[0], closes[0]


# An *italic* footer line — single-asterisk emphasis. Excludes **bold** callouts, `***` rules, and
# `* bullet` lines (H-17: those must NOT be treated as the footer, or the block lands mid-doc).
_FOOTER_RE = re.compile(r"^\*(?!\*).*(?<!\*)\*$")


def _insertion_index(lines: List[str]) -> int:
    """H-17 — the line index to insert before: the LAST ``*italic*`` footer line if EXACTLY one such
    trailing block exists, else EOF (never mid-doc)."""
    footer_idxs = [i for i, ln in enumerate(lines) if _FOOTER_RE.match(ln.strip())]
    if len(footer_idxs) == 1:
        return footer_idxs[0]
    return len(lines)  # ambiguous (0 or many) → EOF


def compute_append(target: Path, section: str, sid: str) -> AppendResult:
    """Compute the guarded-append result WITHOUT writing (pure). Raises BacklogAppendError to fail closed."""
    if not section.strip():
        return AppendResult("no-op", "empty section (no candidates) — nothing to append", "")
    if MARKER_TOKEN in section:  # H-16 marker injection
        raise BacklogAppendError(
            "rendered section contains a reserved backlog marker — refusing to write (marker injection)"
        )
    real = target.resolve() if target.is_symlink() else target  # H-19: operate on the link target
    if not real.is_file():
        raise BacklogAppendError(f"append target does not exist or is not a regular file: {target}")
    original = real.read_text(encoding="utf-8")

    block = f"{_marker_open(sid)}\n{section.rstrip()}\n{_marker_close(sid)}\n"
    existing = _find_marked_block(original, sid)
    if existing is not None:
        start, end = existing
        # replace the marked block (extend to swallow the trailing newline if present)
        tail = original[end:]
        if tail.startswith("\n"):
            tail = tail[1:]
        new_content = original[:start] + block.rstrip("\n") + ("\n" + tail if tail else "\n")
    else:
        lines = original.splitlines()
        idx = _insertion_index(lines)
        before = "\n".join(lines[:idx]).rstrip("\n")
        after = "\n".join(lines[idx:])
        parts = [p for p in (before, block.rstrip("\n"), after.rstrip("\n")) if p]
        new_content = "\n\n".join(parts) + "\n"

    if new_content == original:
        return AppendResult("no-op", "already in sync (block byte-identical)", new_content)
    return AppendResult("would-write", "a backlog block would be inserted/updated", new_content)


def append_backlog(target: Path, section: str, sid: str, *, confirm: bool = False) -> AppendResult:
    """Guarded append (FR-14). Preview unless ``confirm``; atomic same-dir temp + ``os.replace`` (H-19)."""
    result = compute_append(target, section, sid)
    if not confirm or result.action != "would-write":
        return result
    real = target.resolve() if target.is_symlink() else target
    mode = real.stat().st_mode
    fd, tmp = tempfile.mkstemp(dir=str(real.parent), prefix=".backlog-", suffix=".tmp")  # same fs → atomic
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(result.new_content)
        os.chmod(tmp, mode)  # preserve target mode
        os.replace(tmp, real)  # atomic
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return AppendResult("written", result.reason, result.new_content)
