"""M3 unit tests for batch.py — discovery, sidecar join key, roll-up, join (network-free).

Uses deployed-mode apps + ``runner_python`` so each app skips venv install and skips boot (no
network, no live server) while still exercising the full batch orchestration + report assembly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from startd8.deploy_harness import deploy_batch, discover_app_roots

pytestmark = pytest.mark.unit


def _make_model_dir(
    batch_root: Path, slug_name: str, *, sidecar: str | None = None
) -> Path:
    wd = batch_root / slug_name / "workdir"
    app = wd / "app"
    app.mkdir(parents=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    (app / "settings.py").write_text(
        "# startd8-mode: deployed\n", encoding="utf-8"
    )  # skips boot
    if sidecar is not None:
        (batch_root / slug_name / ".model").write_text(sidecar, encoding="utf-8")
    return wd


# --------------------------------------------------------------------------- discovery + join key


def test_discover_reads_sidecar_model_id(tmp_path: Path) -> None:
    _make_model_dir(
        tmp_path, "anthropic-claude-opus-4-8", sidecar="anthropic:claude-opus-4-8"
    )
    roots = discover_app_roots(tmp_path)
    assert len(roots) == 1
    assert roots[0].model == "anthropic:claude-opus-4-8"
    assert roots[0].model_source == "sidecar"
    assert roots[0].path.name == "workdir"


def test_discover_reverse_slug_fallback(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, "openai-gpt-5", sidecar=None)
    roots = discover_app_roots(tmp_path)
    assert roots[0].model == "openai-gpt-5"
    assert roots[0].model_source == "reverse-slug"


def test_discover_manifest_json_sidecar(tmp_path: Path) -> None:
    wd = _make_model_dir(tmp_path, "m", sidecar=None)
    (wd.parent / "deploy-manifest.json").write_text(
        json.dumps({"model": "x:y"}), encoding="utf-8"
    )
    roots = discover_app_roots(tmp_path)
    assert roots[0].model == "x:y" and roots[0].model_source == "sidecar"


# --------------------------------------------------------------------------- batch orchestration


def test_deploy_batch_rollup_and_files(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, "anthropic-opus", sidecar="anthropic:opus")
    _make_model_dir(tmp_path, "openai-gpt", sidecar="openai:gpt")
    report = deploy_batch(tmp_path, runner_python=sys.executable)

    assert report["app_count"] == 2
    # both are deployed-mode → reached boot (skipped), passed boot = 0
    assert report["rollup"]["reached"]["boot"] == 2
    assert report["rollup"]["passed"]["boot"] == 0
    assert report["rollup"]["passed"]["discover"] == 2
    models = {row["model"] for row in report["apps"]}
    assert models == {"anthropic:opus", "openai:gpt"}
    assert (tmp_path / "deploy-report.json").is_file()
    assert (tmp_path / "deploy-report.md").is_file()


def test_deploy_batch_reverse_slug_warns(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, "openai-gpt-5", sidecar=None)
    report = deploy_batch(tmp_path, runner_python=sys.executable)
    assert any("reverse-slugged" in w for w in report["warnings"])


def test_deploy_batch_joins_comparison_report_by_verbatim_model(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, "anthropic-opus", sidecar="anthropic:opus")
    (tmp_path / "comparison-report.json").write_text(
        json.dumps(
            {"ranked": [{"model": "anthropic:opus", "metrics": {"disk_quality": 0.91}}]}
        ),
        encoding="utf-8",
    )
    report = deploy_batch(tmp_path, runner_python=sys.executable)
    assert report["joined_to_comparison"] is True
    row = report["apps"][0]
    assert row["join_basis"] == "exact"
    assert row["comparison"]["disk_quality"] == 0.91


def test_deploy_batch_join_no_match(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, "anthropic-opus", sidecar="anthropic:opus")
    (tmp_path / "comparison-report.json").write_text(
        json.dumps(
            {"ranked": [{"model": "someone:else", "metrics": {"disk_quality": 0.5}}]}
        ),
        encoding="utf-8",
    )
    report = deploy_batch(tmp_path, runner_python=sys.executable)
    row = report["apps"][0]
    assert row["join_basis"] == "no-match" and row["comparison"] is None
