"""M0 unit tests for the LadderResult model (FR-11). Serialization + highest-stage logic."""

from __future__ import annotations

import json

import pytest

from startd8.deploy_harness import (
    EntryPoint,
    LadderResult,
    Stage,
    StageStatus,
)

pytestmark = pytest.mark.unit


def test_record_advances_highest_stage() -> None:
    r = LadderResult(app_root="/tmp/x")
    assert r.highest_stage == Stage.DISCOVER.value
    r.record(Stage.DISCOVER, StageStatus.PASS)
    r.record(Stage.INSTALL, StageStatus.PASS)
    r.record(Stage.BOOT, StageStatus.FAIL, reason="ImportError: app.tables")
    assert r.highest_stage == Stage.BOOT.value
    assert r.stages["boot"].status == StageStatus.FAIL
    assert r.stages["boot"].reason == "ImportError: app.tables"


def test_highest_stage_does_not_regress_on_later_lower_record() -> None:
    r = LadderResult(app_root="/tmp/x")
    r.record(Stage.HEALTH, StageStatus.PASS)
    r.record(
        Stage.DISCOVER, StageStatus.PASS
    )  # out-of-order record must not lower the high-water
    assert r.highest_stage == Stage.HEALTH.value


def test_skipped_rung_counts_as_reached() -> None:
    r = LadderResult(app_root="/tmp/x", mode="deployed")
    r.record(Stage.BOOT, StageStatus.SKIPPED, reason="skipped:deployed-needs-db")
    assert r.highest_stage == Stage.BOOT.value
    assert r.stages["boot"].reason == "skipped:deployed-needs-db"


def test_deviations_accumulate() -> None:
    r = LadderResult(app_root="/tmp/x")
    r.add_deviation("entrypoint-noncanonical", "root-level main.py")
    r.add_deviation("deps-missing", "dep floor")
    assert [d.code for d in r.deviations] == ["entrypoint-noncanonical", "deps-missing"]


def test_to_json_roundtrips_and_includes_provenance() -> None:
    r = LadderResult(
        app_root="/tmp/x",
        model="anthropic:claude-opus-4-8",
        entrypoint=EntryPoint(target="app.main:app", matched_by="manifest"),
        dep_source="requirements.txt",
    )
    r.record(Stage.SMOKE, StageStatus.PASS, ms=12.5)
    payload = json.loads(r.to_json())
    assert payload["model"] == "anthropic:claude-opus-4-8"
    assert payload["entrypoint"]["matched_by"] == "manifest"
    assert payload["stages"]["smoke"]["ms"] == 12.5
    assert payload["highest_stage"] == "smoke"
    # harness_env present (all-None in M0) for forward-compatible reproducibility schema.
    assert "harness_env" in payload


def test_summary_line_is_compact() -> None:
    r = LadderResult(app_root="/tmp/x", model="m")
    r.record(Stage.DISCOVER, StageStatus.PASS)
    r.record(Stage.INSTALL, StageStatus.FAIL, reason="pip exit 1")
    s = r.summary()
    assert "/tmp/x" in s and "discover:pass" in s and "install:fail" in s
