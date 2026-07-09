# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""FR-6/FR-14 — backlog render byte-stability + the guarded append's write-safety (H-16..H-21)."""
from __future__ import annotations

import os

import pytest

from startd8.stakeholder_panel.synthesis_bridge import (
    BacklogAppendError,
    Candidate,
    InputKind,
    Lane,
    TriageReport,
    append_backlog,
    compute_append,
    render_backlog_section,
)


def _report():
    return TriageReport(session_id="sess-1", candidates=[
        Candidate(title="Bills-first screen", source_section="UX Improvements",
                  raw_text="A bills-first due-soon screen", lane=Lane.NON_DECIDABLE,
                  input_kind=InputKind.suggestion),
        Candidate(title="Push vs privacy", source_section="Tensions",
                  raw_text="Push notifications vs local-only medical privacy", lane=Lane.NON_DECIDABLE,
                  input_kind=InputKind.tension),
        Candidate(title="digest", source_section="(unsectioned)", raw_text="A weekly digest email",
                  lane=Lane.UNSTRUCTURED, input_kind=InputKind.content),
    ])


def _doc(tmp_path, body):
    p = tmp_path / "ENHANCEMENTS_BACKLOG.md"
    p.write_text(body, encoding="utf-8")
    return p


# ── FR-6 / H-20: render is byte-stable and empty-safe ────────────────────────
def test_render_is_byte_stable():
    r = _report()
    assert render_backlog_section(r) == render_backlog_section(r)


def test_render_empty_report_is_empty_string():
    assert render_backlog_section(TriageReport(session_id="x")) == ""


# ── FR-14: preview-default, write, idempotent (H-18) ─────────────────────────
def test_preview_default_does_not_write(tmp_path):
    p = _doc(tmp_path, "# Backlog\n\nexisting content\n\n*footer*\n")
    before = p.read_text()
    section = render_backlog_section(_report())
    result = compute_append(p, section, "sess-1")
    assert result.action == "would-write"
    assert p.read_text() == before  # compute never writes


def test_write_then_rerun_is_idempotent(tmp_path):
    p = _doc(tmp_path, "# Backlog\n\nexisting content\n\n*footer line*\n")
    section = render_backlog_section(_report())
    w1 = append_backlog(p, section, "sess-1", confirm=True)
    assert w1.action == "written"
    after1 = p.read_text()
    # marker present exactly once; existing content + footer preserved (append-only, H-17)
    assert after1.count("<!-- startd8-panel-backlog: sess-1 -->") == 1
    assert "existing content" in after1 and after1.rstrip().endswith("*footer line*")
    # re-run with the same session → no-op, byte-identical (H-18 idempotent)
    w2 = append_backlog(p, section, "sess-1", confirm=True)
    assert w2.action == "no-op"
    assert p.read_text() == after1


def test_insertion_is_before_the_single_footer(tmp_path):
    p = _doc(tmp_path, "# Backlog\n\nbody\n\n*the footer*\n")
    section = render_backlog_section(_report())
    append_backlog(p, section, "sess-1", confirm=True)
    text = p.read_text()
    assert text.index("startd8-panel-backlog") < text.index("*the footer*")  # inserted before footer


def test_bold_line_is_not_treated_as_footer_block_goes_to_eof(tmp_path):
    # H-17 regression: a **bold** callout must NOT be mistaken for the italic footer (else the block
    # lands mid-document). With no real footer, insertion falls through to EOF.
    p = _doc(tmp_path, "# Backlog\n\n**Important Note**\n\nbody one\n\nbody two\n")
    section = render_backlog_section(_report())
    append_backlog(p, section, "sess-1", confirm=True)
    text = p.read_text()
    assert text.index("**Important Note**") < text.index("startd8-panel-backlog")  # block after the bold line
    assert text.index("body two") < text.index("startd8-panel-backlog")  # at EOF, not mid-doc


# ── H-16: marker injection fails closed ──────────────────────────────────────
def test_marker_injection_fails_closed(tmp_path):
    p = _doc(tmp_path, "# Backlog\n\n*footer*\n")
    hostile = "## X\n\n- a residual line with <!-- startd8-panel-backlog: evil --> inside it\n"
    with pytest.raises(BacklogAppendError):
        compute_append(p, hostile, "sess-1")


# ── H-18: malformed existing marker fails closed ─────────────────────────────
def test_unclosed_marker_fails_closed(tmp_path):
    p = _doc(tmp_path, "# Backlog\n\n<!-- startd8-panel-backlog: sess-1 -->\nleftover\n\n*footer*\n")
    section = render_backlog_section(_report())
    with pytest.raises(BacklogAppendError):
        compute_append(p, section, "sess-1")


# ── fail-closed on a missing target ──────────────────────────────────────────
def test_missing_target_fails_closed(tmp_path):
    section = render_backlog_section(_report())
    with pytest.raises(BacklogAppendError):
        compute_append(tmp_path / "does-not-exist.md", section, "sess-1")


# ── empty section (zero candidates) → no-op, never touches the file (H-5) ─────
def test_empty_section_is_noop(tmp_path):
    p = _doc(tmp_path, "# Backlog\n\n*footer*\n")
    before = p.read_text()
    result = append_backlog(p, "", "sess-1", confirm=True)
    assert result.action == "no-op"
    assert p.read_text() == before


# ── H-19: a symlinked target is written through to the real file, link preserved ─
def test_symlink_target_written_through(tmp_path):
    real = tmp_path / "real_backlog.md"
    real.write_text("# Backlog\n\nbody\n\n*footer*\n", encoding="utf-8")
    link = tmp_path / "ENHANCEMENTS_BACKLOG.md"
    link.symlink_to(real)
    section = render_backlog_section(_report())
    append_backlog(link, section, "sess-1", confirm=True)
    assert link.is_symlink()  # the link is preserved, not clobbered with a regular file
    assert "startd8-panel-backlog" in real.read_text()  # written through to the target
