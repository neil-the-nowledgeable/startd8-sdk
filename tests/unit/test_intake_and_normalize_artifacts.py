"""Phase 4 controls: review intake + mechanical normalization aligned to the promoted store.

Offline tests: schema validation, artifact acceptance, forbidden imports, normalizer idempotence +
mechanical-only guard, structured rejection paths, store-gating, and raw-evidence preservation.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "intake_and_normalize_artifacts.py"

spec = importlib.util.spec_from_file_location("intake_and_normalize_artifacts", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# --- pure normalization -------------------------------------------------------------------------

def test_normalize_text_is_idempotent():
    raw = "a  \n  b\t\n\n\n"
    once = mod.normalize_text(raw)
    assert mod.normalize_text(once) == once
    assert once.endswith("\n") and not once.endswith("\n\n")


def test_mechanical_only_true_for_whitespace_change():
    raw = "def f():\n    return  1   \n\n"
    assert mod.is_mechanical_only(raw, mod.normalize_text(raw))


def test_mechanical_only_false_for_semantic_change():
    assert not mod.is_mechanical_only("return 1", "return 2")          # value changed
    assert not mod.is_mechanical_only("HALF_UP", "HALF_EVEN")          # rounding changed


# --- import / header checks ---------------------------------------------------------------------

def test_forbidden_imports_flag_non_stdlib():
    assert mod.check_suite_imports("import os\nimport json\n") == []
    assert mod.check_suite_imports("import pytest\n") == []            # pytest explicitly allowed
    assert "grpc" in mod.check_suite_imports("import grpc\n")
    assert "google.protobuf" in mod.check_suite_imports("from google.protobuf import x\n")


def test_spec_headers_detect_missing_sections():
    missing = mod.check_spec_headers("# Title\n## Scope\n")
    assert "scope" not in missing and "title" not in missing
    assert "non-goals" in missing and "assumptions" in missing


# --- evaluate_run reason codes ------------------------------------------------------------------

def _suite_run(tmp_path, suite_src="import os\n\ndef test_x():\n    assert True\n", **meta):
    d = tmp_path / "run_01_suite_author_codex-cli_sample_1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "suite.py").write_text(suite_src, encoding="utf-8")
    (d / "suite_manifest.json").write_text("{}", encoding="utf-8")
    (d / "authoring_manifest.json").write_text("{}", encoding="utf-8")
    m = {"run_id": "r1", "ordinal": 1, "experiment": "suite_author", "tool_id": "codex-cli",
         "author_vendor": "openai", "sample_index": 1, "status": "success", "exit_code": 0}
    m.update(meta)
    return d, m


def test_evaluate_accepts_clean_suite(tmp_path):
    d, m = _suite_run(tmp_path)
    assert mod.evaluate_run(d, m) == (None, "")


def test_evaluate_rejects_failed_run(tmp_path):
    d, m = _suite_run(tmp_path, status="failed", exit_code=1)
    assert mod.evaluate_run(d, m)[0] == mod.REASON_RUN_FAILED


def test_evaluate_rejects_forbidden_import(tmp_path):
    d, m = _suite_run(tmp_path, suite_src="import grpc\n\ndef test():\n    pass\n")
    assert mod.evaluate_run(d, m)[0] == mod.REASON_FORBIDDEN_IMPORT


def test_evaluate_rejects_syntax_error(tmp_path):
    d, m = _suite_run(tmp_path, suite_src="def (:\n")
    assert mod.evaluate_run(d, m)[0] == mod.REASON_SUITE_SYNTAX


def test_evaluate_rejects_missing_artifact(tmp_path):
    d, m = _suite_run(tmp_path)
    (d / "suite.py").unlink()
    assert mod.evaluate_run(d, m) == (mod.REASON_MISSING_ARTIFACT, "suite.py")


# --- store gating + raw preservation (integration-ish) ------------------------------------------

def _promoted_store(tmp_path, status="accepted"):
    store, batch = tmp_path / "store", "b1"
    raw = store / batch / "raw"
    d, m = _suite_run(raw)
    (raw.parent / "reconciliation-report.json").write_text(
        json.dumps({"status": status, "runs": []}), encoding="utf-8")
    (d / "metadata.json").write_text(json.dumps(m), encoding="utf-8")
    return store, batch, raw


def test_gating_refuses_unaccepted_store(tmp_path):
    store, batch, _ = _promoted_store(tmp_path, status="blocked")
    with pytest.raises(SystemExit):
        mod.load_accepted_store(store, batch)


def test_gating_accepts_accepted_store(tmp_path):
    store, batch, raw = _promoted_store(tmp_path, status="accepted")
    assert mod.load_accepted_store(store, batch) == raw


def test_intake_preserves_raw_and_writes_ledger_in_store(tmp_path):
    store, batch, raw = _promoted_store(tmp_path)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in raw.rglob("*") if p.is_file()}
    rc = mod.main(["--store-root", str(store), "--batch-id", batch])
    assert rc == 0
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in raw.rglob("*") if p.is_file()}
    assert before == after, "raw evidence must be immutable"
    batch_root = store / batch
    assert (batch_root / "intake-ledger.json").is_file()       # ledger inside the store
    assert (batch_root / "normalized").is_dir()
    ledger = json.loads((batch_root / "intake-ledger.json").read_text())
    assert ledger["accepted"] == 1 and ledger["total"] == 1
