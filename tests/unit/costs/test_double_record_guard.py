"""Tests for the cross-API cost double-record guard (REQ-AAO-002)."""

import logging

import pytest

from startd8.costs.double_record_guard import note_cost_recorded, _reset_for_tests


@pytest.fixture(autouse=True)
def _clean_guard():
    _reset_for_tests()
    yield
    _reset_for_tests()


def test_single_source_does_not_warn(caplog):
    with caplog.at_level(logging.WARNING):
        note_cost_recorded("cost_tracker", "cid-1")
        note_cost_recorded("cost_tracker", "cid-1")  # same source, repeated
    assert not [r for r in caplog.records if "multiple APIs" in r.getMessage()]


def test_two_sources_same_correlation_id_warns_once(caplog):
    with caplog.at_level(logging.WARNING):
        note_cost_recorded("cost_tracker", "cid-2")
        note_cost_recorded("session_tracker", "cid-2")
        note_cost_recorded("session_tracker", "cid-2")  # repeat must not re-warn
    warnings = [r for r in caplog.records if "multiple APIs" in r.getMessage()]
    assert len(warnings) == 1
    assert "cid-2" in warnings[0].getMessage()


def test_falsy_correlation_id_is_ignored(caplog):
    with caplog.at_level(logging.WARNING):
        note_cost_recorded("cost_tracker", None)
        note_cost_recorded("session_tracker", "")
    assert not caplog.records


def test_distinct_correlation_ids_do_not_cross_warn(caplog):
    with caplog.at_level(logging.WARNING):
        note_cost_recorded("cost_tracker", "cid-a")
        note_cost_recorded("session_tracker", "cid-b")
    assert not [r for r in caplog.records if "multiple APIs" in r.getMessage()]
