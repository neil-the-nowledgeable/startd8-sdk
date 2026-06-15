"""Tests for the defect ledger (FR-B2 / FR-A3) — consolidated, non-collapsed defect record."""

from unittest.mock import MagicMock

from startd8.contractors.defect_ledger import DefectLedger, collect_defects, write_ledger


def _failed(name, errors):
    from startd8.contractors.checkpoint import CheckpointStatus
    r = MagicMock()
    r.name = name
    r.status = CheckpointStatus.FAILED
    r.errors = errors
    r.message = "failed"
    return r


def _passed(name):
    from startd8.contractors.checkpoint import CheckpointStatus
    r = MagicMock()
    r.name = name
    r.status = CheckpointStatus.PASSED
    r.errors = []
    return r


def test_collect_from_failed_checkpoints():
    from startd8.contractors.checkpoint import CheckpointStatus
    results = [_failed("Import Check", ["no module 'x'"]), _passed("Syntax Check")]
    led = collect_defects("u", results, {}, failed_status=CheckpointStatus.FAILED)
    cats = led.by_category()
    assert cats.get("import") == 1
    assert led.error_count() == 1
    # passed checkpoint contributes nothing
    assert all(e.source != "Syntax Check" for e in led.entries)


def test_collect_from_disk_compliance():
    from startd8.contractors.checkpoint import CheckpointStatus
    compliance = {
        "app/svc.py": {
            "ast_valid": True,
            "stubs_remaining": 2,
            "duplicate_definitions": 1,
            "import_completeness": 0.8,
            "contract_compliance": 0.9,
            "semantic_issues": [
                {"category": "unchecked_error", "severity": "warning", "message": "err not checked"},
                {"category": "sql_injection_risk", "severity": "error", "message": "concat sql"},
            ],
        }
    }
    led = collect_defects("u", [], compliance, failed_status=CheckpointStatus.FAILED)
    cats = led.by_category()
    assert cats.get("stub") == 1
    assert cats.get("duplicate") == 1
    assert cats.get("import") == 1
    assert cats.get("contract") == 1
    assert cats.get("unchecked_error") == 1
    assert cats.get("sql_injection_risk") == 1
    sev = led.by_severity()
    assert sev.get("error") == 1  # the sql_injection_risk
    assert sev.get("warning") >= 3


def test_clean_file_yields_empty_ledger():
    from startd8.contractors.checkpoint import CheckpointStatus
    led = collect_defects("clean", [_passed("Syntax Check")], {}, failed_status=CheckpointStatus.FAILED)
    assert led.entries == []
    assert led.to_dict()["total"] == 0


def test_to_dict_and_markdown_and_write(tmp_path):
    led = DefectLedger(unit="u")
    led.add(category="stub", severity="warning", source="disk_compliance", file="a.py", message="1 stub")
    d = led.to_dict()
    assert d["total"] == 1 and d["by_category"] == {"stub": 1}
    assert "defect ledger" in led.to_markdown().lower()
    write_ledger(led, tmp_path)
    assert (tmp_path / ".startd8" / "defect-ledger" / "u.json").exists()
    assert (tmp_path / ".startd8" / "defect-ledger" / "u.md").exists()
