"""Mirror guard for the .startd8 store-path consolidation (S1 distillation).

Pins the resolved locations to the exact literal paths that were re-typed across the feature group
before `paths.startd8_dir` became their single home — so the consolidation can't silently move a
store location. If a location legitimately changes, this test changes with it, in ONE place.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.kickoff_experience import paths
from startd8.kickoff_experience.activation import ledger_path
from startd8.kickoff_experience.session_snapshot import snapshot_path
from startd8.kickoff_experience.vipp_seam import dispositions_path, inbox_path

pytestmark = pytest.mark.unit

ROOT = Path("/tmp/proj")


def test_root_helper_appends_startd8():
    assert paths.startd8_dir(ROOT) == ROOT / ".startd8"
    assert paths.startd8_dir("/tmp/proj") == ROOT / ".startd8"  # str == Path


def test_owner_paths_resolve_to_their_historical_literals():
    assert ledger_path(ROOT) == ROOT / ".startd8" / "kickoff" / "activation-ledger.jsonl"
    assert snapshot_path(ROOT) == ROOT / ".startd8" / "kickoff" / "agentic-session.json"
    assert inbox_path(ROOT) == ROOT / ".startd8" / "vipp" / "proposals-inbox.json"
    assert dispositions_path(ROOT) == ROOT / ".startd8" / "vipp" / "dispositions.json"


def test_leaf_subdir_names_are_stable():
    # the well-known subdir vocabulary, pinned so a rename is a one-line, test-caught change
    assert paths.startd8_dir(ROOT) / paths.DASHBOARDS == ROOT / ".startd8" / "dashboards"
    assert paths.startd8_dir(ROOT) / paths.KICKOFF_PANEL == ROOT / ".startd8" / "kickoff-panel"
    assert paths.startd8_dir(ROOT) / paths.KICKOFF_SCRATCH == ROOT / ".startd8" / "kickoff-scratch"
    assert paths.startd8_dir(ROOT) / paths.STAKEHOLDER_PANEL == ROOT / ".startd8" / "stakeholder-panel"
    assert paths.startd8_dir(ROOT) / paths.STAKEHOLDER_RUN == ROOT / ".startd8" / "stakeholder-run"


def test_exemplars_dir_is_home_based_not_project_based(monkeypatch):
    # the global registry uses ~/.startd8 (a DIFFERENT base) — startd8_dir generalises to any base
    monkeypatch.delenv("STARTD8_KICKOFF_EXEMPLARS_DIR", raising=False)
    from startd8.kickoff_experience.promotion import exemplars_dir

    assert exemplars_dir() == Path.home() / ".startd8" / "kickoff-exemplars"
