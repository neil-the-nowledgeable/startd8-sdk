"""Oracle value-input coverage — the confirmed.yaml/inputs layout folded into resolve_kickoff_state.

The oracle's markdown-extraction path is blind to the value-input layout that instantiated packages use;
this pins the fix: value-input projects populate the oracle, while bare/markdown projects are unchanged.
"""

from __future__ import annotations

import pytest

from startd8.concierge.confirmation import confirmable_fields
from startd8.kickoff_experience.manifest import default_config
from startd8.kickoff_experience.state import Ambiguity, Attention, resolve_kickoff_state
from startd8.kickoff_experience.value_inputs import value_input_field_states

pytestmark = pytest.mark.unit


def _confirmable_value_paths():
    vps = [f["value_path"] for f in confirmable_fields()]
    assert vps, "SDK config must have confirmable fields for these tests to mean anything"
    return vps


def _required_fields():
    """The required, NON-confirmable writable fields (FR-2's blocked candidates)."""
    confirmable = {f["value_path"] for f in confirmable_fields()}
    reqd = [
        f
        for f in default_config().writable_fields()
        if f.required and f.value_path not in confirmable
    ]
    assert reqd, "SDK config must have required non-confirmable fields for these tests to mean anything"
    return reqd


def _touch_inputs(root):
    """Make the project read as a value-input project (inputs/ dir present)."""
    (root / "docs" / "kickoff" / "inputs").mkdir(parents=True, exist_ok=True)


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
    # inputs/ dir present (value-input project) but confirmed.yaml absent → confirmable fields → review,
    # NOT "no inputs / 0 fields". This is the FR-5 consistency + FR-7 parity fix. (Required inputs, with
    # no on-disk value here, are blocked — asserted separately below; here we pin the confirmable set.)
    (tmp_path / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    fields = value_input_field_states(tmp_path)
    assert fields, "a project with the inputs/ layout must not read as 'no inputs'"
    confirmable = set(_confirmable_value_paths())
    review = [f for f in fields if f.value_path in confirmable]
    assert review and all(f.attention == Attention.REVIEW for f in review)


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


# --- FR-2 blocked case: a REQUIRED, non-defaulted value-input that is absent → blocked --------------


def _write_input_value(root, write_target, value):
    """Set the dotted key in the domain's inputs/<file>.yaml (a real provided value)."""
    import yaml

    path = root / "docs" / "kickoff" / "inputs" / write_target.file
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    node = data
    parts = write_target.key.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value
    path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")


def test_required_input_absent_is_blocked(tmp_path):
    # value-input project (inputs/ present) but a required, non-confirmable input's on-disk value is
    # absent (domain file missing) → that field is BLOCKED, not review/ok. This is FR-2's blocked case:
    # a project missing a required, non-derivable input must gate, not read "ready".
    _touch_inputs(tmp_path)
    reqd = _required_fields()
    by = {f.value_path: f for f in value_input_field_states(tmp_path)}
    for f in reqd:
        assert f.value_path in by, f"required field {f.value_path} must be surfaced"
        assert by[f.value_path].attention == Attention.BLOCKED
        assert by[f.value_path].ambiguity == Ambiguity.MALFORMED_BLOCK


def test_required_input_placeholder_is_blocked(tmp_path):
    # an unfilled <…> placeholder on a required input is NOT a provided value → still blocked.
    _touch_inputs(tmp_path)
    f = _required_fields()[0]
    _write_input_value(tmp_path, f.write_target, "<python | …>")
    by = {fs.value_path: fs for fs in value_input_field_states(tmp_path)}
    assert by[f.value_path].attention == Attention.BLOCKED


def test_required_input_provided_is_ok(tmp_path):
    # a real on-disk value for a required input → ok (not blocked).
    _touch_inputs(tmp_path)
    f = _required_fields()[0]
    real = f.choices[0] if f.choices else "python"
    _write_input_value(tmp_path, f.write_target, real)
    by = {fs.value_path: fs for fs in value_input_field_states(tmp_path)}
    assert by[f.value_path].attention == Attention.OK
    assert by[f.value_path].value == str(real)


def test_blocked_required_input_folds_into_state_and_gates(tmp_path):
    # the blocked required input is folded into resolve_kickoff_state → the oracle's blocked_fields()
    # worklist and attention_counts reflect it, so kickoff check gates (activation blocked).
    _touch_inputs(tmp_path)
    reqd = _required_fields()
    st = resolve_kickoff_state(tmp_path)
    blocked_vps = {f.value_path for f in st.blocked_fields()}
    for f in reqd:
        assert f.value_path in blocked_vps
    assert st.attention_counts["blocked"] >= len(reqd)


# --- data_model.money is now OPTIONAL (doesn't gate) + the "intentionally N/A" affordance -----------

_MONEY_VP = "conventions.yaml#/data_model.money"


def _write_conventions(root, body):
    conv = root / "docs" / "kickoff" / "inputs" / "conventions.yaml"
    conv.parent.mkdir(parents=True, exist_ok=True)
    conv.write_text(body, encoding="utf-8")


def test_is_not_applicable_recognizes_sentinels():
    from startd8.kickoff_experience.value_inputs import is_not_applicable

    for v in ["n/a", "N/A", "not applicable", "not-applicable", "None", " - ", "n.a."]:
        assert is_not_applicable(v), v
    for v in ["cents", "python", "", None, "n/a stuff", 0]:
        assert not is_not_applicable(v), v


def test_optional_money_absent_does_not_block(tmp_path):
    # money is optional now — a project that never declares it is NOT blocked on it (and it doesn't gate)
    (tmp_path / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    money = [f for f in value_input_field_states(tmp_path) if f.value_path == _MONEY_VP]
    assert all(f.attention != Attention.BLOCKED for f in money)  # never blocked (typically omitted)


def test_optional_money_declared_is_ok(tmp_path):
    _write_conventions(tmp_path, "data_model:\n  money: cents\n")
    money = [f for f in value_input_field_states(tmp_path) if f.value_path == _MONEY_VP]
    assert money and money[0].attention == Attention.OK and money[0].value == "cents"


def test_not_applicable_declares_a_decision_ok_with_distinct_status(tmp_path):
    _write_conventions(tmp_path, "data_model:\n  money: not-applicable\n")
    money = [f for f in value_input_field_states(tmp_path) if f.value_path == _MONEY_VP]
    assert money and money[0].attention == Attention.OK and money[0].status == "not_applicable"


def test_required_field_declared_na_is_an_intentional_ok_not_blocked(tmp_path):
    # N/A is the escape hatch for a GENUINELY-required convention too: declaring it n/a satisfies it.
    _write_conventions(tmp_path, "language: not-applicable\nstack:\n  framework: not-applicable\n")
    fields = value_input_field_states(tmp_path)
    required = {f.value_path for f in _required_fields()}
    req_fields = [f for f in fields if f.value_path in required]
    assert req_fields and all(f.attention == Attention.OK for f in req_fields)
