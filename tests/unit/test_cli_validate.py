"""`startd8 validate` — cross-language semantic validators → text / JSON / SARIF.

Module: src/startd8/cli_validate.py
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from startd8.cli import app

runner = CliRunner()

_BARE_EXCEPT = "def h():\n    try:\n        risky()\n    except:\n        pass\n"   # warning
_STUB = "import time\ndef fetch(u):\n    time.sleep(1)\n    return {'id': 1}\n"        # error (fake_work_stub)
_CLEAN = "def add(a, b):\n    return a + b\n"


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_clean_file_exits_zero(tmp_path):
    f = _write(tmp_path, "clean.py", _CLEAN)
    res = runner.invoke(app, ["validate", str(f)])
    assert res.exit_code == 0
    assert "no semantic findings" in res.stdout


def test_warning_finding_reported_but_exit_zero(tmp_path):
    f = _write(tmp_path, "bad.py", _BARE_EXCEPT)
    res = runner.invoke(app, ["validate", str(f)])
    assert res.exit_code == 0  # warnings never fail the exit
    assert "bare_except_pass" in res.stdout
    assert "warning" in res.stdout


def test_error_finding_exits_one(tmp_path):
    f = _write(tmp_path, "stub.py", _STUB)
    res = runner.invoke(app, ["validate", str(f)])
    assert res.exit_code == 1
    assert "fake_work_stub" in res.stdout


def test_sarif_format_is_valid_210(tmp_path):
    f = _write(tmp_path, "bad.py", _BARE_EXCEPT)
    res = runner.invoke(app, ["validate", str(f), "--format", "sarif"])
    doc = json.loads(res.stdout)
    assert doc["version"] == "2.1.0"
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "startd8-semantic"
    assert "bare_except_pass" in {r["id"] for r in run["tool"]["driver"]["rules"]}
    result = run["results"][0]
    assert result["ruleId"] == "bare_except_pass"
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == str(f)
    assert run["invocations"][0]["properties"]["corpus"] == str(f)


def test_json_format_lists_findings(tmp_path):
    f = _write(tmp_path, "bad.py", _BARE_EXCEPT)
    res = runner.invoke(app, ["validate", str(f), "--format", "json"])
    data = json.loads(res.stdout)
    assert len(data) == 1
    assert set(data[0]) == {"check", "severity", "message", "line", "file_path"}
    assert data[0]["check"] == "bare_except_pass"


def test_directory_walk_excludes_vendor_dirs(tmp_path):
    _write(tmp_path, "app.py", _STUB)
    vendor = tmp_path / "node_modules"
    vendor.mkdir()
    _write(vendor, "dep.py", _STUB)  # must be excluded
    res = runner.invoke(app, ["validate", str(tmp_path), "--format", "json"])
    data = json.loads(res.stdout)
    files = {d["file_path"] for d in data}
    assert any(fp.endswith("app.py") for fp in files)
    assert not any("node_modules" in fp for fp in files)


def test_bad_format_exits_two(tmp_path):
    f = _write(tmp_path, "clean.py", _CLEAN)
    res = runner.invoke(app, ["validate", str(f), "--format", "yaml"])
    assert res.exit_code == 2


def test_out_writes_sarif_file(tmp_path):
    f = _write(tmp_path, "bad.py", _BARE_EXCEPT)
    out = tmp_path / "findings.sarif"
    res = runner.invoke(app, ["validate", str(f), "--format", "sarif", "--out", str(out)])
    assert res.exit_code == 0
    doc = json.loads(out.read_text())
    assert doc["version"] == "2.1.0"


def test_missing_path_errors(tmp_path):
    res = runner.invoke(app, ["validate", str(tmp_path / "nope.py")])
    assert res.exit_code != 0  # typer's exists=True guard
