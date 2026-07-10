"""Parity guard for resolve_kickoff_state — the one home for the KickoffState derivation.

Pins the extracted helper to the canonical `load_kickoff_docs → build_kickoff_state(…,
live_schema_text=…)` composition it replaced across the oracle / web / chat / portal surfaces, so the
consolidation can't silently drift from what those 4 call sites used to do inline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.kickoff_experience.docs import live_schema_text, load_kickoff_docs
from startd8.kickoff_experience.state import build_kickoff_state, resolve_kickoff_state

pytestmark = pytest.mark.unit


def _canonical(project_root):
    # the exact inline derivation the 4 surfaces re-typed before the extraction
    docs = load_kickoff_docs(project_root)
    return build_kickoff_state(docs, live_schema_text=live_schema_text(project_root))


def test_resolve_matches_canonical_composition(tmp_path):
    assert resolve_kickoff_state(tmp_path).to_dict() == _canonical(tmp_path).to_dict()


def test_resolve_accepts_str_and_path_equivalently(tmp_path):
    # agentic_view previously wrapped the root in str(); the helper must treat str == Path
    as_path = resolve_kickoff_state(tmp_path).to_dict()
    as_str = resolve_kickoff_state(str(tmp_path)).to_dict()
    assert as_path == as_str


def test_surfaces_route_through_the_helper(tmp_path):
    # web.load_state is now a thin pass-through — same state as the helper (no divergence)
    from startd8.kickoff_experience.web import load_state

    assert load_state(tmp_path).to_dict() == resolve_kickoff_state(tmp_path).to_dict()
