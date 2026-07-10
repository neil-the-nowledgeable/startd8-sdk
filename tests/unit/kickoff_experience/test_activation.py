"""Kickoff activation surface (Tier B) — evaluate gate + append-only ledger."""

from __future__ import annotations

import json

import pytest

from startd8.kickoff_experience.activation import (
    ACTIVATION_SCHEMA,
    ActivationLedger,
    evaluate_activation,
)

pytestmark = pytest.mark.unit


def _status(**over):
    base = {
        "project_root": "/p",
        "readiness_percent": 100,
        "attention_counts": {"ok": 3, "review": 0, "blocked": 0, "backlog": 0},
        "field_count": 3,
        "proposals": [],
        "snapshot_status": "present",
        "next_action": None,
    }
    base.update(over)
    return base


def test_all_clear_is_ok_exit_zero():
    r = evaluate_activation(_status())
    assert r.overall == "ok" and r.ready is True and r.exit_code == 0
    assert len(r.open) == 0


def test_no_inputs_fires_attention():
    r = evaluate_activation(_status(field_count=0, attention_counts={}, readiness_percent=None))
    assert r.overall == "attention" and r.exit_code == 1
    assert any(c.key == "no_inputs" for c in r.open)


def test_blocked_fields_dominates_as_blocked_exit_three():
    r = evaluate_activation(
        _status(attention_counts={"ok": 1, "review": 2, "blocked": 1, "backlog": 0})
    )
    # blocked outranks the co-firing review-backlog attention condition
    assert r.overall == "blocked" and r.exit_code == 3
    keys = {c.key for c in r.open}
    assert "blocked_fields" in keys and "review_backlog" in keys


def test_pending_proposals_and_readiness_below_target():
    r = evaluate_activation(
        _status(readiness_percent=60, proposals=[{"id": "P-1"}]), min_readiness=100
    )
    keys = {c.key for c in r.open}
    assert "pending_proposals" in keys and "readiness_below_target" in keys
    assert r.overall == "attention"


def test_to_dict_schema_and_json_serializable():
    d = evaluate_activation(_status(proposals=[{"id": "P-1"}])).to_dict()
    assert d["schema"] == ACTIVATION_SCHEMA
    assert d["open_count"] == 1 and d["ready"] is False
    json.dumps(d)  # must not raise


def test_ledger_appends_on_change_and_dedups(tmp_path):
    led = ActivationLedger(tmp_path)
    e1 = led.record(_status(readiness_percent=50), now="2026-01-01T00:00:00Z")
    assert e1 is not None and e1["changed"]  # first row records everything
    # identical signature → no duplicate row
    assert led.record(_status(readiness_percent=50), now="2026-01-01T00:05:00Z") is None
    # a real transition → appended, with the changed field named
    e2 = led.record(_status(readiness_percent=100), now="2026-01-01T01:00:00Z")
    assert e2 is not None and "readiness_percent" in e2["changed"]
    assert len(led.entries()) == 2


def test_ledger_tolerates_malformed_rows(tmp_path):
    led = ActivationLedger(tmp_path)
    led.record(_status(), now="t0")
    led.path.write_text(led.path.read_text() + "not-json\n", encoding="utf-8")
    assert len(led.entries()) == 1  # malformed line skipped, valid row survives
