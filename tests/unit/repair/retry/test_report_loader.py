"""Inc 1 — report loader + violation extraction tests (FR-2, R1-F1, R1-F9).

The fixture ``fixtures/run012_postmortem.json`` is trimmed byte-for-byte from the
real ``run-012-20260601T1838`` report; the 5 expected specifiers are pinned to the
investigation doc §2 table (R1-F9 — guards against silent drift).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.repair.retry.models import RetryViolation
from startd8.repair.retry.report_loader import load_violations

_FIXTURE = Path(__file__).parent / "fixtures" / "run012_postmortem.json"

# Pinned to investigation doc §2 (the real run-012 incident).
_EXPECTED = {
    "PI-012": "../../../types/wizard",
    "PI-007": "./StepNav.module.css",
    "PI-005": "./ModeToggle.module.css",
    "PI-008": "@/components/wizard/steps",
    "PI-011": "./ProofPointStep.module.css",
}


def test_loads_exactly_the_five_unresolvable_imports():
    violations = load_violations(_FIXTURE)
    assert len(violations) == 5
    assert {v.feature_id for v in violations} == set(_EXPECTED)
    assert all(v.category == "unresolvable_import" for v in violations)
    assert all(v.parse_ok for v in violations)


def test_specifiers_match_the_real_incident_byte_for_byte():
    by_id = {v.feature_id: v for v in load_violations(_FIXTURE)}
    for fid, spec in _EXPECTED.items():
        assert by_id[fid].specifier == spec


def test_file_path_is_the_run_relative_importer():
    by_id = {v.feature_id: v for v in load_violations(_FIXTURE)}
    # disk_compliance.file_path is the run-relative path the artifacts live under.
    assert by_id["PI-007"].file_path.endswith("components/wizard/StepNav.tsx")
    assert by_id["PI-012"].file_path.endswith("components/wizard/steps/EnrichStep.tsx")


def test_out_of_scope_categories_are_ignored():
    # PI-005 (ModeToggle) carries a duplicate_require warning alongside its
    # unresolvable_import — only the unresolvable_import is loaded.
    raw = json.loads(_FIXTURE.read_text())
    pi005 = next(f for f in raw["features"] if f["feature_id"] == "PI-005")
    cats = {i["category"] for i in pi005["disk_compliance"]["semantic_issues"]}
    assert "duplicate_require" in cats  # the fixture really has it
    pi005_violations = [v for v in load_violations(_FIXTURE) if v.feature_id == "PI-005"]
    assert len(pi005_violations) == 1
    assert pi005_violations[0].specifier == "./ModeToggle.module.css"


def test_successful_features_yield_no_violations():
    raw = json.loads(_FIXTURE.read_text())
    assert any(f["success"] is True for f in raw["features"])  # fixture has OK features
    loaded_ids = {v.feature_id for v in load_violations(_FIXTURE)}
    ok_ids = {f["feature_id"] for f in raw["features"] if f["success"] is True}
    assert loaded_ids.isdisjoint(ok_ids)


def test_accepts_a_run_directory(tmp_path):
    # Mirror the real layout: <run>/plan-ingestion/prime-postmortem-report.json
    pi = tmp_path / "plan-ingestion"
    pi.mkdir()
    (pi / "prime-postmortem-report.json").write_text(_FIXTURE.read_text(), encoding="utf-8")
    assert len(load_violations(tmp_path)) == 5


def test_unparseable_message_is_not_dropped(tmp_path):
    """R1-F1: a message with no parseable specifier → parse_ok=False, still returned."""
    report = tmp_path / "prime-postmortem-report.json"
    report.write_text(json.dumps({
        "features": [{
            "feature_id": "PI-099",
            "success": False,
            "disk_compliance": {
                "file_path": "components/X.tsx",
                "semantic_issues": [{
                    "category": "unresolvable_import",
                    "severity": "error",
                    "message": "garbled message with no backticked specifier",
                }],
            },
        }],
    }), encoding="utf-8")
    violations = load_violations(report)
    assert len(violations) == 1
    assert violations[0].parse_ok is False
    assert violations[0].specifier == ""


def test_missing_report_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_violations(tmp_path / "nope")


def test_violation_is_frozen():
    v = load_violations(_FIXTURE)[0]
    assert isinstance(v, RetryViolation)
    with pytest.raises(Exception):
        v.specifier = "mutated"  # type: ignore[misc]
