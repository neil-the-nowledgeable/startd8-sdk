"""Spec Delivery Loop (LOOP_CATALOG #6) — the deterministic stage-0 gate + --status resilience.

Covers the gate's build-ready verdict on a real spec, a missing-name failure, and the HTH Phase-2
robustness fix: --status must survive one unreadable/non-UTF-8 spec instead of aborting the sweep.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import navigator_spec_delivery_loop as sdl  # noqa: E402

_GOOD_SPEC = """\
# Fixture — Requirements

**Format:** det-req/0.1

> **Readable handle:** `feature/navigator-fixture`
> **Semantic name:** *A fixture requirement that is build-ready.*

- **FR-1 — Do the thing.** It does the thing. Name: navigator does the thing. Verify: `x` exits 0. Serves: O-1
"""


def test_gate_passes_a_build_ready_spec(tmp_path):
    """A spec with a name block + a single-line FR carrying Name/Verify/Serves is build-ready."""
    p = tmp_path / "REQ-fixture.md"
    p.write_text(_GOOD_SPEC, encoding="utf-8")
    v = sdl.gate_spec(p)
    assert v["ok"] is True
    assert v["frs"] == 1
    assert v["blocked"] == []


def test_gate_blocks_missing_name_block(tmp_path):
    """No name block → blocked on 'name-block' (and the FR-level named check)."""
    p = tmp_path / "REQ-noname.md"
    p.write_text("# X\n\n- **FR-1 — Do it.** body. Verify: `x`. Serves: O-1\n", encoding="utf-8")
    v = sdl.gate_spec(p)
    assert v["ok"] is False
    assert "name-block" in v["blocked"]


def test_gate_blocks_hardwrapped_fr(tmp_path):
    """A hard-wrapped FR bullet drops fields → frs-parse mismatch (the single-line rule)."""
    p = tmp_path / "REQ-wrapped.md"
    p.write_text(
        "# X\n\n"
        "> **Readable handle:** `feature/x`\n> **Semantic name:** *x*\n\n"
        "- **FR-1 — Do it.** body.\n  Name: x. Verify: `y`. Serves: O-1\n",  # wrapped 2nd line
        encoding="utf-8",
    )
    v = sdl.gate_spec(p)
    assert v["ok"] is False


def test_status_survives_one_unreadable_spec(tmp_path, monkeypatch, capsys):
    """HTH P2/R1: a non-UTF-8 spec must not abort the whole --status sweep."""
    (tmp_path / "REQ-good.md").write_text(_GOOD_SPEC, encoding="utf-8")
    (tmp_path / "REQ-bad.md").write_bytes(b"\xff\xfe not utf-8 \x80")
    monkeypatch.setattr(sdl, "SPEC_DIR", tmp_path)
    rc = sdl.main(["prog", "--status"])  # must not raise
    assert rc == 0
    out = capsys.readouterr().out
    assert "REQ-good.md" in out
    assert "REQ-bad.md" in out and "unreadable" in out
