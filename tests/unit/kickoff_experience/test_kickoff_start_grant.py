"""M5 — `kickoff start --cloud --grant-store` validation: the trust-chain config must be satisfiable,
else the serve refuses (fail-closed at launch rather than silently denying every request)."""

from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.cli_kickoff import kickoff_app  # noqa: E402

runner = CliRunner()


def _pkg(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    (tmp_path / "docs" / "kickoff" / "inputs" / "business-targets.yaml").write_text("goals: []\n")
    return tmp_path


def test_grant_store_requires_api_key_deployment_and_origin(tmp_path):
    p = _pkg(tmp_path)
    # --cloud --grant-store but NO --api-key / --deployment-id / --cloud-origin → refuse before serving.
    r = runner.invoke(kickoff_app, [
        "start", str(p), "--cloud", "--grant-store", str(tmp_path / "g.json"),
    ])
    assert r.exit_code != 0
    assert "--api-key" in r.output and "--deployment-id" in r.output and "--cloud-origin" in r.output
