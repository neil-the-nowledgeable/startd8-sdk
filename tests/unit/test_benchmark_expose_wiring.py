"""FR-B5 (build_command flags) + FR-B3 (ledger aggregation into the cell score)."""

import json
from pathlib import Path

from startd8.benchmark_matrix.runner import SubprocessCellExecutor
from startd8.model_comparison import build_command


class TestBuildCommandFlags:
    def test_default_omits_quality_flags(self):
        cmd = build_command(Path("s.json"), Path("/w"), Path("/o"), "m", 1.0)
        assert "--repair-mode" not in cmd
        assert "--expose-defects" not in cmd

    def test_shadow_expose_appended(self):
        cmd = build_command(Path("s.json"), Path("/w"), Path("/o"), "m", 1.0,
                            repair_mode="shadow", expose_defects=True)
        assert cmd[cmd.index("--repair-mode") + 1] == "shadow"
        assert "--expose-defects" in cmd

    def test_apply_mode_not_appended(self):
        cmd = build_command(Path("s.json"), Path("/w"), Path("/o"), "m", 1.0, repair_mode="apply")
        assert "--repair-mode" not in cmd


class TestLedgerAggregation:
    def test_merges_multiple_ledgers(self, tmp_path):
        led = tmp_path / ".startd8" / "defect-ledger"
        led.mkdir(parents=True)
        (led / "A.json").write_text(json.dumps(
            {"total": 3, "by_category": {"stub": 2, "sql_injection_risk": 1},
             "by_severity": {"warning": 2, "error": 1}}))
        (led / "B.json").write_text(json.dumps(
            {"total": 1, "by_category": {"stub": 1}, "by_severity": {"warning": 1}}))
        agg = SubprocessCellExecutor._aggregate_defect_ledger(tmp_path)
        assert agg["total"] == 4
        assert agg["by_category"] == {"stub": 3, "sql_injection_risk": 1}
        assert agg["by_severity"] == {"warning": 3, "error": 1}

    def test_no_ledger_returns_none(self, tmp_path):
        assert SubprocessCellExecutor._aggregate_defect_ledger(tmp_path) is None
