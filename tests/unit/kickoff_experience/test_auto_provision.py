"""FR-E3 — auto-provision the cockpit on session end (best-effort, never breaks session exit)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.cli_kickoff import _maybe_provision_cockpit  # noqa: E402


def test_no_url_is_a_noop(tmp_path):
    _maybe_provision_cockpit(tmp_path, None)          # must not raise, must not attempt anything


def test_best_effort_on_a_project_without_a_kickoff_package(tmp_path):
    # No docs/kickoff → build_workbook_v2_and_maybe_provision returns a skipped_reason; the helper
    # swallows it (prints, never raises, never blocks session exit).
    _maybe_provision_cockpit(tmp_path, "http://127.0.0.1:9")   # unroutable — must be swallowed too
