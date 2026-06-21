from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/run_cross_tool_bias_s4.py"
SPEC = importlib.util.spec_from_file_location("run_cross_tool_bias_s4", SCRIPT)
assert SPEC and SPEC.loader
s4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s4)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_target_inventory_inherits_accepted_status_from_manifest(tmp_path: Path) -> None:
    manifest = {"status": "accepted", "mutants": [{"id": "m1", "source": "src/m1.py"}]}
    source = tmp_path / "src/m1.py"
    source.parent.mkdir()
    source.write_text("# mutant\n", encoding="utf-8")

    targets = s4.target_inventory(manifest, tmp_path / "manifest.json")

    assert [target["target_id"] for target in targets] == ["reference_oracle", "m1"]
    assert targets[1]["sha256"] == s4.sha256(source)


def test_preflight_refuses_to_execute_without_reviewed_bridge(tmp_path: Path) -> None:
    store = tmp_path / "store"
    batch = store / "batch"
    _write_json(batch / "reconciliation-report.json", {"status": "accepted"})
    _write_json(
        batch / "intake-ledger.json",
        {
            "total": 1,
            "runs": [{
                "run_id": "run_01", "status": "accepted", "experiment": "suite_author",
                "author_vendor": "openai", "sample_index": 1, "normalized_sha256": "abc",
            }],
        },
    )
    (batch / "normalized/run_01").mkdir(parents=True)
    (batch / "normalized/run_01/suite.py").write_text("def configure(adapter):\n    return adapter\n", encoding="utf-8")
    _write_json(batch / "normalized/run_01/suite_manifest.json", {"adapter_contract": {"configure": "suite.configure(adapter)"}})
    gate = tmp_path / "gate.json"
    _write_json(gate, {"status": "accepted"})
    mutants = tmp_path / "mutants.json"
    _write_json(mutants, {"status": "accepted", "mutants": [{"id": "m1"}]})
    pre_registration = tmp_path / "pre-registration.json"
    _write_json(pre_registration, {"status": "pre_registered", "batch_id": "batch"})

    code, result = s4.run_preflight(
        store_root=store, batch_id="batch", results_root=tmp_path / "results", gate_path=gate,
        mutants_path=mutants, pre_registration_path=pre_registration,
    )

    assert code == 2
    assert result["status"] == "blocked"
    assert result["targets"][1]["target_id"] == "m1"
    assert "no reviewed isolated no-egress S4 execution bridge is installed" in result["errors"]
    assert (tmp_path / "results/mutant_kill_matrix.csv").is_file()
