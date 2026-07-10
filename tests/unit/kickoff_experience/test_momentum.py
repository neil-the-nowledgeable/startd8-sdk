"""Close-the-loop momentum + leverage (Tier D) — readiness slope + highest-leverage batch."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from startd8.kickoff_experience.momentum import (
    TREND_FALLING,
    TREND_RISING,
    TREND_STALLED,
    TREND_UNKNOWN,
    leverage_groups,
    leverage_nudge,
    readiness_trend,
)

pytestmark = pytest.mark.unit


def _entries(*percents):
    return [{"readiness_percent": p} for p in percents]


def test_trend_unknown_with_too_little_history():
    assert readiness_trend([]).trend == TREND_UNKNOWN
    assert readiness_trend(_entries(60)).trend == TREND_UNKNOWN


def test_trend_rising_falling_stalled():
    r = readiness_trend(_entries(60, 80))
    assert r.trend == TREND_RISING and r.delta == 20 and "→ 80%" in r.summary
    assert readiness_trend(_entries(80, 60)).trend == TREND_FALLING
    stalled = readiness_trend(_entries(60, 60, 60))
    assert stalled.trend == TREND_STALLED and "stalled at 60%" in stalled.summary


def test_trend_skips_none_readings():
    r = readiness_trend([{"readiness_percent": None}, {"readiness_percent": 50}, {"readiness_percent": 70}])
    assert r.trend == TREND_RISING and r.previous == 50 and r.latest == 70


@dataclass
class _F:
    value_path: str
    attention: str


@dataclass
class _State:
    fields: list


def test_leverage_ranks_classes_by_clearable_count():
    state = _State(
        fields=[
            _F("conventions.tz", "blocked"),
            _F("conventions.locale", "blocked"),
            _F("conventions.currency", "review"),
            _F("data_model.orders", "blocked"),
            _F("value_inputs.pitch", "ok"),  # ok → not counted
        ]
    )
    groups = leverage_groups(state)
    assert groups[0].subject == "conventions" and groups[0].count == 3
    assert groups[0].blocked == 2 and groups[0].review == 1
    assert groups[1].subject == "data_model" and groups[1].count == 1
    # ok field's class never appears
    assert all(g.subject != "value_inputs" for g in groups)


def test_leverage_empty_when_all_ok_or_no_state():
    assert leverage_groups(None) == ()
    assert leverage_groups(_State(fields=[_F("a.b", "ok")])) == ()


def test_leverage_nudge_combines_top_class_and_stalled_momentum():
    state = _State(fields=[_F("conventions.tz", "blocked"), _F("conventions.locale", "blocked")])
    trend = readiness_trend(_entries(60, 60))  # stalled
    nudge = leverage_nudge(state, trend)
    assert "resolve `conventions`" in nudge and "clears 2 fields" in nudge
    assert "stalled at 60%" in nudge


def test_leverage_nudge_none_when_nothing_actionable():
    assert leverage_nudge(None) is None
    assert leverage_nudge(_State(fields=[_F("a.b", "ok")])) is None
