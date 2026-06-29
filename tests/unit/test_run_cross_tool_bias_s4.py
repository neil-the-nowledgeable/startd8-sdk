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


def _accepted_s4_store(tmp_path: Path, *, ledger_row: dict | None = None) -> tuple[Path, Path, Path, Path]:
    store = tmp_path / "store"
    batch = store / "batch"
    _write_json(batch / "reconciliation-report.json", {"status": "accepted"})
    suite_path = batch / "normalized/run_01/suite.py"
    suite_path.parent.mkdir(parents=True)
    suite_path.write_text("def configure(adapter):\n    return adapter\n", encoding="utf-8")
    _write_json(
        batch / "normalized/run_01/suite_manifest.json",
        {"adapter_contract": {"configure": "suite.configure(adapter)"}},
    )
    row = {
        "run_id": "run_01", "status": "accepted", "experiment": "suite_author",
        "author_vendor": "openai", "sample_index": 1, "normalized_sha256": s4.sha256(suite_path),
    }
    if ledger_row:
        row.update(ledger_row)
    _write_json(batch / "intake-ledger.json", {"total": 1, "runs": [row]})
    gate = tmp_path / "gate.json"
    _write_json(gate, {"status": "accepted"})
    mutants = tmp_path / "mutants.json"
    _write_json(mutants, {"status": "accepted", "mutants": [{"id": "m1"}]})
    pre_registration = tmp_path / "pre-registration.json"
    _write_json(pre_registration, {"status": "pre_registered", "batch_id": "batch"})
    return store, gate, mutants, pre_registration


def test_target_inventory_inherits_accepted_status_from_manifest(tmp_path: Path) -> None:
    manifest = {"status": "accepted", "mutants": [{"id": "m1", "source": "src/m1.py"}]}
    source = tmp_path / "src/m1.py"
    source.parent.mkdir()
    source.write_text("# mutant\n", encoding="utf-8")

    targets = s4.target_inventory(manifest, tmp_path / "manifest.json")

    assert [target["target_id"] for target in targets] == ["reference_oracle", "m1"]
    assert targets[1]["sha256"] == s4.sha256(source)


def test_preflight_refuses_to_execute_without_reviewed_bridge(tmp_path: Path) -> None:
    store, gate, mutants, pre_registration = _accepted_s4_store(tmp_path)

    code, result = s4.run_preflight(
        store_root=store, batch_id="batch", results_root=tmp_path / "results", gate_path=gate,
        mutants_path=mutants, pre_registration_path=pre_registration,
    )

    assert code == 2
    assert result["status"] == "blocked"
    assert result["targets"][1]["target_id"] == "m1"
    assert result["suites"][0]["normalized_sha256_actual"] == result["suites"][0]["normalized_sha256"]
    assert result["suites"][0]["bridge"]["status"] == "bridge_required"
    assert result["bridge"]["status"] == "not_installed"
    assert any(error.startswith("reviewed S4 bridge manifest is not installed:") for error in result["errors"])
    assert "S4 bridge execution remains disabled until the reviewed executor consumes the dry-run gate" in result["errors"]
    assert (tmp_path / "results/mutant_kill_matrix.csv").is_file()


def test_preflight_blocks_when_normalized_suite_checksum_mismatches(tmp_path: Path) -> None:
    store, gate, mutants, pre_registration = _accepted_s4_store(
        tmp_path, ledger_row={"normalized_sha256": "not-the-actual-sha"}
    )

    _, result = s4.run_preflight(
        store_root=store, batch_id="batch", results_root=tmp_path / "results", gate_path=gate,
        mutants_path=mutants, pre_registration_path=pre_registration,
    )

    assert "accepted suite_author normalized_sha256 mismatch:run_01" in result["errors"]
    assert result["suites"][0]["bridge"]["status"] == "invalid_intake"


def test_preflight_blocks_when_normalized_suite_is_missing(tmp_path: Path) -> None:
    store, gate, mutants, pre_registration = _accepted_s4_store(tmp_path)
    (store / "batch/normalized/run_01/suite.py").unlink()

    _, result = s4.run_preflight(
        store_root=store, batch_id="batch", results_root=tmp_path / "results", gate_path=gate,
        mutants_path=mutants, pre_registration_path=pre_registration,
    )

    assert "accepted suite_author missing normalized suite.py:run_01" in result["errors"]
    assert result["suites"][0]["bridge"]["status"] == "invalid_intake"


def test_preflight_blocks_when_suite_author_row_is_rejected(tmp_path: Path) -> None:
    store, gate, mutants, pre_registration = _accepted_s4_store(
        tmp_path, ledger_row={"status": "rejected_with_reason"}
    )

    _, result = s4.run_preflight(
        store_root=store, batch_id="batch", results_root=tmp_path / "results", gate_path=gate,
        mutants_path=mutants, pre_registration_path=pre_registration,
    )

    assert "intake ledger has rejected suite_author artifacts:1" in result["errors"]
    assert "intake ledger has no accepted suite_author artifacts" in result["errors"]


def test_suite_replacement_validation_requires_accepted_replacement_row() -> None:
    replaced, errors = s4.validated_suite_replacement_ids({
        "runs": [{
            "run_id": "run-27",
            "status": "rejected_with_reason",
            "experiment": "suite_author",
        }],
        "dispositions": [{
            "rejected_run_id": "run-27",
            "replacement_run_id": "run-27-replacement-1",
            "reason_code": "forbidden_import",
        }],
    })

    assert replaced == set()
    assert errors == [
        "suite replacement disposition references missing replacement run:run-27-replacement-1"
    ]


def test_suite_replacement_validation_accepts_replacement_row() -> None:
    replaced, errors = s4.validated_suite_replacement_ids({
        "runs": [
            {
                "run_id": "run-27",
                "status": "rejected_with_reason",
                "experiment": "suite_author",
            },
            {
                "run_id": "run-27-replacement-1",
                "status": "accepted",
                "experiment": "suite_author",
            },
        ],
        "dispositions": [{
            "rejected_run_id": "run-27",
            "replacement_run_id": "run-27-replacement-1",
            "reason_code": "forbidden_import",
        }],
    })

    assert errors == []
    assert replaced == {"run-27"}


def test_preflight_does_not_suppress_rejected_suite_with_invalid_replacement(tmp_path: Path) -> None:
    store, gate, mutants, pre_registration = _accepted_s4_store(
        tmp_path, ledger_row={"status": "rejected_with_reason"}
    )
    _write_json(store / "batch/intake-ledger.json", {
        "total": 1,
        "runs": [{
            "run_id": "run_01",
            "status": "rejected_with_reason",
            "experiment": "suite_author",
            "author_vendor": "openai",
            "sample_index": 1,
            "normalized_sha256": None,
        }],
        "dispositions": [{
            "rejected_run_id": "run_01",
            "replacement_run_id": "missing-replacement",
            "reason_code": "forbidden_import",
        }],
    })

    _, result = s4.run_preflight(
        store_root=store, batch_id="batch", results_root=tmp_path / "results", gate_path=gate,
        mutants_path=mutants, pre_registration_path=pre_registration,
    )

    assert "suite replacement disposition references missing replacement run:missing-replacement" in result["errors"]
    assert "intake ledger has rejected suite_author artifacts:1" in result["errors"]


def test_bridge_env_scrubs_secrets_and_redirects_home(tmp_path: Path) -> None:
    env = s4.scrub_bridge_env(
        tmp_path,
        {
            "PATH": "/bin",
            "OPENAI_API_KEY": "secret",
            "GEMINI_TOKEN": "secret",
            "HOME": "/Users/real",
            "PYTHONPATH": "/repo/src",
        },
    )

    assert env["PATH"] == "/bin"
    assert env["HOME"] == str(tmp_path)
    assert env["TMPDIR"] == str(tmp_path)
    assert "OPENAI_API_KEY" not in env
    assert "GEMINI_TOKEN" not in env
    assert "PYTHONPATH" not in env


def test_bridge_dry_run_gate_requires_reviewed_manifest(tmp_path: Path) -> None:
    bridge, errors = s4.bridge_dry_run_gate(tmp_path / "missing.json", tmp_path / "results")

    assert bridge["status"] == "not_installed"
    assert errors == [f"reviewed S4 bridge manifest is not installed:{tmp_path / 'missing.json'}"]


def test_bridge_dry_run_gate_runs_trusted_sentinel_with_real_isolation(tmp_path: Path) -> None:
    manifest = tmp_path / "s4-bridge-manifest.json"
    _write_json(
        manifest,
        {
            "status": "reviewed",
            "require_no_egress": True,
            "require_scrubbed_env": True,
            "require_identical_inventory": True,
            "timeout_seconds": 3,
            "max_output_bytes": 128,
        },
    )
    captured = {}

    def fake_runner(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        return s4.subprocess.CompletedProcess(command, 0, stdout="s4-bridge-dry-run-ok\n", stderr="")

    bridge, errors = s4.bridge_dry_run_gate(
        manifest,
        tmp_path / "results",
        caps={"sandbox_exec": True, "unshare": False},
        runner=fake_runner,
    )

    assert errors == []
    assert bridge["status"] == "ready"
    assert bridge["dry_run"]["returncode"] == 0
    assert bridge["dry_run"]["isolation"] == "seatbelt-no-egress"
    assert captured["command"][:3] == ["sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"]
    assert captured["env"]["HOME"] == str(tmp_path / "results/bridge-dry-run-workspace")
    assert "PYTHONPATH" not in captured["env"]
