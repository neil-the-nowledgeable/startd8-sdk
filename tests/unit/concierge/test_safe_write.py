"""Security suite for the Concierge safe-writer (FR-C3.1–C3.6).

The load-bearing tests from CONCIERGE_MCP_WRITE_PATH_PLAN Step 5: traversal, absolute-escape,
symlinked root, symlinked parent, no-clobber, append-not-truncate, append durability, and the
WritePlan-as-untrusted-input case. Each maps to a confinement invariant.
"""

from __future__ import annotations

import os

import pytest

from startd8.concierge.safe_write import (
    ACTION_APPEND,
    ACTION_NEW,
    ACTION_OVERWRITE,
    PlannedWrite,
    SafeWriteError,
    apply_write_plan,
    resolve_confined_root,
)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    return r


# ── FR-C3.2 / C3.6 — confinement of untrusted paths ──────────────────────────

def test_traversal_blocked(root):
    res = apply_write_plan(root, [PlannedWrite("../../etc/evil", ACTION_NEW, content="x")])
    assert res.written == []
    assert res.blocked and "escapes" in res.blocked[0]["reason"]


def test_absolute_path_blocked(root):
    res = apply_write_plan(root, [PlannedWrite("/etc/evil", ACTION_NEW, content="x")])
    assert res.blocked and not res.written


def test_injected_escaping_path_in_plan_blocked(root):
    """FR-C3.6 — the WritePlan is untrusted; an escaping path is re-confined at the writer."""
    plan = [
        PlannedWrite("legit.txt", ACTION_NEW, content="ok"),
        PlannedWrite("a/../../escape.txt", ACTION_NEW, content="bad"),
    ]
    res = apply_write_plan(root, plan)
    assert "legit.txt" in res.written
    assert any("escape" in b["path"] for b in res.blocked)
    assert not (root.parent / "escape.txt").exists()


# ── FR-C3.1 — root integrity ─────────────────────────────────────────────────

def test_symlinked_root_rejected(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(SafeWriteError):
        apply_write_plan(link, [PlannedWrite("f.txt", ACTION_NEW, content="x")])


def test_allowlist_permits_symlinked_root(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("STARTD8_CONCIERGE_ALLOWED_ROOTS", str(tmp_path))
    res = apply_write_plan(link, [PlannedWrite("f.txt", ACTION_NEW, content="x")])
    assert "f.txt" in res.written


# ── FR-C3.2/C3.3 — symlinked parent component ────────────────────────────────

def test_symlinked_parent_blocked(root, tmp_path):
    evil = tmp_path / "evil"
    evil.mkdir()
    (root / "a").symlink_to(evil, target_is_directory=True)  # parent component is a symlink
    res = apply_write_plan(root, [PlannedWrite("a/b.txt", ACTION_NEW, content="x")])
    assert res.blocked and not res.written
    assert not (evil / "b.txt").exists()  # nothing landed in the symlink target


# ── FR-C3.4 — no clobber ─────────────────────────────────────────────────────

def test_new_refuses_existing(root):
    (root / "f.txt").write_text("original", encoding="utf-8")
    res = apply_write_plan(root, [PlannedWrite("f.txt", ACTION_NEW, content="new")])
    assert res.skipped and not res.written
    assert (root / "f.txt").read_text() == "original"


def test_overwrite_needs_force(root):
    (root / "f.txt").write_text("original", encoding="utf-8")
    res = apply_write_plan(root, [PlannedWrite("f.txt", ACTION_OVERWRITE, content="new")])
    assert res.skipped and (root / "f.txt").read_text() == "original"
    res2 = apply_write_plan(root, [PlannedWrite("f.txt", ACTION_OVERWRITE, content="new")], force=True)
    assert "f.txt" in res2.written and (root / "f.txt").read_text() == "new"


# ── FR-C3.5 — append never truncates; nested create ──────────────────────────

def test_append_creates_then_preserves(root):
    res1 = apply_write_plan(root, [PlannedWrite("log.jsonl", ACTION_APPEND, append_text='{"a":1}\n')])
    assert "log.jsonl" in res1.written
    res2 = apply_write_plan(root, [PlannedWrite("log.jsonl", ACTION_APPEND, append_text='{"b":2}\n')])
    assert "log.jsonl" in res2.written
    lines = (root / "log.jsonl").read_text().splitlines()
    assert lines == ['{"a":1}', '{"b":2}']  # prior content preserved, both whole


def test_new_creates_nested_dirs(root):
    res = apply_write_plan(root, [PlannedWrite("docs/kickoff/inputs/x.yaml", ACTION_NEW, content="k: v\n")])
    assert "docs/kickoff/inputs/x.yaml" in res.written
    assert (root / "docs" / "kickoff" / "inputs" / "x.yaml").read_text() == "k: v\n"
    # no temp files left behind
    assert not list(root.rglob("*.concierge.tmp"))


# ── basics ───────────────────────────────────────────────────────────────────

def test_resolve_confined_root_rejects_nonexistent(tmp_path):
    with pytest.raises(SafeWriteError):
        resolve_confined_root(tmp_path / "nope")


def test_unknown_action_is_error_not_crash(root):
    res = apply_write_plan(root, [PlannedWrite("f.txt", "nuke", content="x")])
    assert res.errors and not res.written


def test_partial_apply_valid_written_blocked_reported(root):
    """R1-S10 — valid files written, blocked files reported, deterministic."""
    plan = [
        PlannedWrite("good.txt", ACTION_NEW, content="ok"),
        PlannedWrite("../bad.txt", ACTION_NEW, content="no"),
    ]
    res = apply_write_plan(root, plan)
    assert "good.txt" in res.written
    assert any("bad" in b["path"] for b in res.blocked)
    assert not res.ok  # ok is False when anything was blocked
