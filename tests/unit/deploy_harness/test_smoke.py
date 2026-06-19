"""Unit tests for deploy_harness.smoke round-trip grading (network-free)."""

from __future__ import annotations

import pytest

from startd8.deploy_harness.smoke import _round_trip_ok

pytestmark = pytest.mark.unit


def test_round_trip_matches_created_id() -> None:
    assert _round_trip_ok({"id": 3}, [{"id": 1}, {"id": 3}])
    assert not _round_trip_ok({"id": 3}, [{"id": 1}])
    assert not _round_trip_ok({"id": 1}, [])  # empty list after create = failure


def test_round_trip_no_id_accepts_nonempty_list() -> None:
    assert _round_trip_ok({"ok": True}, [{"x": 1}])
    assert _round_trip_ok(None, {"items": [{"x": 1}]})  # wrapped list shape
