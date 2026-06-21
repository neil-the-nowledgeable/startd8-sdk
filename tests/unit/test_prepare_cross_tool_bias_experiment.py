"""Pre-registration controls for the cross-tool authoring experiment."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "prepare_cross_tool_bias_experiment.py"
MANIFEST = REPO / "docs/design/benchmark-bias-audit/bias_audit_openai/cross_tool_experiment_manifest.json"

spec = importlib.util.spec_from_file_location("prepare_cross_tool_bias_experiment", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_manifest_is_valid_and_schedule_is_balanced():
    manifest = module._load_manifest(MANIFEST)
    module.validate_manifest(manifest)
    schedule = module.build_schedule(manifest)

    assert len(schedule) == 30
    assert {item["experiment"] for item in schedule} == {"suite_author", "spec_author"}
    assert {item["author_vendor"] for item in schedule} == {"anthropic", "openai", "google"}
    assert [item["ordinal"] for item in schedule] == list(range(1, 31))


def test_prepare_writes_immutable_schedule_outside_repo(tmp_path):
    output_dir = tmp_path / "clean" / "experiment"
    result = module.prepare(MANIFEST, output_dir)

    assert result["authoring_runs_planned"] == 30
    assert json.loads((output_dir / "pre-registration.json").read_text())["experiment_id"] == result["experiment_id"]
    assert len(json.loads((output_dir / "authoring-schedule.json").read_text())) == 30


def test_workspace_inside_repo_is_rejected():
    manifest = module._load_manifest(MANIFEST)

    with pytest.raises(module.ManifestError, match="outside the repository"):
        module._assert_clean_workspace(REPO / ".startd8" / "bias-audit", manifest["execution_controls"])


def test_checksum_mismatch_is_rejected():
    manifest = module._load_manifest(MANIFEST)
    manifest["source_artifacts"][0]["sha256"] = "0" * 64

    with pytest.raises(module.ManifestError, match="checksum mismatch"):
        module.validate_manifest(manifest)
