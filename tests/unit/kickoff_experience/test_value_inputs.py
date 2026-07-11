"""Oracle value-input coverage — the confirmed.yaml/inputs layout folded into resolve_kickoff_state.

The oracle's markdown-extraction path is blind to the value-input layout that instantiated packages use;
this pins the fix: value-input projects populate the oracle, while bare/markdown projects are unchanged.
"""

from __future__ import annotations

import pytest

from startd8.concierge.confirmation import confirmable_fields
from startd8.kickoff_experience.state import Attention, resolve_kickoff_state
from startd8.kickoff_experience.value_inputs import value_input_field_states

pytestmark = pytest.mark.unit


def _confirmable_value_paths():
    vps = [f["value_path"] for f in confirmable_fields()]
    assert vps, "SDK config must have confirmable fields for these tests to mean anything"
    return vps


def _write_confirmed(root, value_path, value="X"):
    conf = root / "docs" / "kickoff" / "confirmed.yaml"
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(
        "schema: kickoff.confirmed.v1\n"
        "confirmed:\n"
        f'  {value_path}:\n    at: "2026-07-10"\n    mode: as-is\n    value: {value}\n',
        encoding="utf-8",
    )


# --- FR-4 regression: bare / markdown-only projects are unchanged (no phantom fields) ---------------

def test_bare_project_has_no_fields(tmp_path):
    # no inputs/ dir, no confirmed.yaml, no markdown → the gate returns [] → oracle stays "no inputs"
    assert value_input_field_states(tmp_path) == []
    assert resolve_kickoff_state(tmp_path).fields == ()


# --- FR-1/FR-2: confirmed value-inputs become ok fields; unconfirmed → review ----------------------

def test_confirmed_value_input_is_ok_and_folds_into_state(tmp_path):
    vps = _confirmable_value_paths()
    _write_confirmed(tmp_path, vps[0])

    fields = value_input_field_states(tmp_path)
    by = {f.value_path: f for f in fields}
    assert by[vps[0]].attention == Attention.OK          # confirmed → ok
    if len(vps) > 1:
        assert by[vps[1]].attention == Attention.REVIEW  # unconfirmed → review (never ok)

    # resolve_kickoff_state folds it in — the oracle now reflects the value-input project
    st = resolve_kickoff_state(tmp_path)
    assert any(f.value_path == vps[0] and f.attention == Attention.OK for f in st.fields)
    assert st.attention_counts["ok"] >= 1


# --- FR-5/FR-7: a project WITH the inputs layout is never "no inputs", even before confirmation ------

def test_inputs_layout_present_but_unconfirmed_shows_review_not_empty(tmp_path):
    # inputs/ dir present (value-input project) but confirmed.yaml absent → all confirmable → review,
    # NOT "no inputs / 0 fields". This is the FR-5 consistency + FR-7 parity fix.
    (tmp_path / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    fields = value_input_field_states(tmp_path)
    assert fields, "a project with the inputs/ layout must not read as 'no inputs'"
    assert all(f.attention == Attention.REVIEW for f in fields)


# --- Gate: audience-default is not ok (don't over-report machine defaults) --------------------------

def test_audience_default_is_review_not_ok(tmp_path):
    vps = _confirmable_value_paths()
    conf = tmp_path / "docs" / "kickoff" / "confirmed.yaml"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "schema: kickoff.confirmed.v2\n"
        "confirmed:\n"
        f'  {vps[0]}:\n    at: "2026-07-10"\n    provenance: audience-default:beginner\n    value: X\n',
        encoding="utf-8",
    )
    by = {f.value_path: f for f in value_input_field_states(tmp_path)}
    assert by[vps[0]].attention == Attention.REVIEW  # a machine default the human hasn't ratified
