"""Tests for the derived, fail-closed oracle and mutant admission gate."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "validate_cross_tool_oracle_gate.py"

spec = importlib.util.spec_from_file_location("validate_cross_tool_oracle_gate", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _configure_evidence(tmp_path, monkeypatch, *, accepted: bool) -> Path:
    root = tmp_path / "audit"
    oracle = root / "oracle"
    mutants = root / "mutants"
    oracle.mkdir(parents=True)
    mutants.mkdir()

    status = "accepted" if accepted else "pending"
    (oracle / "oracle-provenance.json").write_text(json.dumps({"status": status}))
    (oracle / "fixed-open-evidence.json").write_text(json.dumps({"status": status}))
    signoffs = [
        {
            "reviewer_id": "r1",
            "role": "reviewer",
            "blinded": True,
            "evidence_reviewed": ["oracle"],
            "decision": "accept",
            "rationale": "complete",
            "date": "2026-06-20",
        },
        {
            "reviewer_id": "r2",
            "role": "reviewer",
            "blinded": False,
            "evidence_reviewed": ["mutants"],
            "decision": "accept",
            "rationale": "complete",
            "date": "2026-06-20",
        },
    ] if accepted else []
    (oracle / "reviewer-signoffs.json").write_text(
        json.dumps({"status": status, "signoffs": signoffs})
    )
    (mutants / "adequacy-report.json").write_text(json.dumps({"status": status}))
    (mutants / "manifest.json").write_text(json.dumps({"status": status}))
    (mutants / "expected-kill-matrix.csv").write_text(
        "mutant_id,killed\nm1,true\n" if accepted else "mutant_id,killed\n"
    )
    gate = oracle / "validation-gate.json"
    gate.write_text(json.dumps({"schema_version": "1.0", "checks": []}))

    evidence = {
        "oracle_provenance": oracle / "oracle-provenance.json",
        "evidence_mapping": oracle / "fixed-open-evidence.json",
        "reviewer_signoff": oracle / "reviewer-signoffs.json",
        "mutant_adequacy": mutants / "adequacy-report.json",
    }
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "GATE", gate)
    monkeypatch.setattr(module, "JSON_EVIDENCE", evidence)
    return gate


def test_validate_marks_each_incomplete_evidence_check_blocked(tmp_path, monkeypatch):
    _configure_evidence(tmp_path, monkeypatch, accepted=False)

    result = module.validate()

    assert result["status"] == "blocked"
    assert {check["status"] for check in result["checks"]} == {"blocked"}
    assert len(result["errors"]) == 6


def test_sync_writes_derived_check_statuses_and_errors(tmp_path, monkeypatch):
    gate = _configure_evidence(tmp_path, monkeypatch, accepted=True)

    assert module.main(["--sync-status"]) == 0

    synced = json.loads(gate.read_text())
    assert synced["status"] == "accepted"
    assert synced["validation_errors"] == []
    assert {check["status"] for check in synced["checks"]} == {"accepted"}


def test_sync_keeps_incomplete_evidence_explicitly_blocked(tmp_path, monkeypatch):
    gate = _configure_evidence(tmp_path, monkeypatch, accepted=False)

    assert module.main(["--sync-status"]) == 2

    synced = json.loads(gate.read_text())
    assert synced["status"] == "blocked"
    assert len(synced["validation_errors"]) == 6
    assert {check["status"] for check in synced["checks"]} == {"blocked"}


def test_non_accepting_reviewer_decision_does_not_admit_gate(tmp_path, monkeypatch):
    _configure_evidence(tmp_path, monkeypatch, accepted=True)
    signoffs_path = module.JSON_EVIDENCE["reviewer_signoff"]
    signoffs = json.loads(signoffs_path.read_text())
    signoffs["signoffs"][0]["decision"] = "blocked"
    signoffs_path.write_text(json.dumps(signoffs))

    result = module.validate()

    assert result["status"] == "blocked"
    reviewer_check = next(check for check in result["checks"] if check["id"] == "reviewer_signoff")
    assert reviewer_check["errors"] == ["requires two complete accepting sign-offs"]
