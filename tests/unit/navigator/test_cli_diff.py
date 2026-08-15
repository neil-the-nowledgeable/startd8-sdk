"""REQ-07 FR-5 — the `navigator diff` CLI subcommand."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from startd8.navigator.cli_navigator import navigator_app

_RUNNER = CliRunner()


def _write_nodes_json(path, nodes):
    path.write_text(json.dumps({"nodes": nodes}), encoding="utf-8")


def test_diff_listed_in_help():
    res = _RUNNER.invoke(navigator_app, ["--help"])
    assert res.exit_code == 0
    assert "diff" in res.stdout


def test_diff_html_exit_0(tmp_path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    _write_nodes_json(before, [{"key": "A", "does": "old", "status": "spec"}])
    _write_nodes_json(
        after,
        [
            {"key": "A", "does": "new", "status": "built"},
            {"key": "B", "does": "added", "status": "spec"},
        ],
    )
    out = tmp_path / "delta.html"
    res = _RUNNER.invoke(
        navigator_app,
        ["diff", "--before", str(before), "--after", str(after), "--out", str(out)],
    )
    assert res.exit_code == 0, res.stdout
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "<!doctype html>" in html
    assert "1 added" in html and "1 changed" in html


def test_diff_json_emits_nodediff(tmp_path):
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    _write_nodes_json(before, [{"key": "A", "does": "old"}])
    _write_nodes_json(after, [{"key": "A", "does": "new"}, {"key": "B", "does": "x"}])
    res = _RUNNER.invoke(
        navigator_app,
        ["diff", "--before", str(before), "--after", str(after), "--json"],
    )
    assert res.exit_code == 0, res.stdout
    payload = json.loads(res.stdout)
    assert payload["rollup"]["added"] == 1
    assert payload["added"] == ["B"]
    assert payload["changed"][0]["key"] == "A"


def test_diff_bad_input_exit_1(tmp_path):
    missing = tmp_path / "nope.json"
    after = tmp_path / "a.json"
    _write_nodes_json(after, [{"key": "A", "does": "x"}])
    res = _RUNNER.invoke(
        navigator_app,
        ["diff", "--before", str(missing), "--after", str(after), "--out", str(tmp_path / "o.html")],
    )
    assert res.exit_code == 1


def test_diff_missing_out_without_json_exit_1(tmp_path):
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    _write_nodes_json(before, [{"key": "A", "does": "x"}])
    _write_nodes_json(after, [{"key": "A", "does": "y"}])
    res = _RUNNER.invoke(
        navigator_app, ["diff", "--before", str(before), "--after", str(after)]
    )
    assert res.exit_code == 1


def test_diff_max_detail_counts_only(tmp_path):
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    _write_nodes_json(before, [{"key": f"K{i}", "does": "o"} for i in range(6)])
    _write_nodes_json(after, [{"key": f"K{i}", "does": "n"} for i in range(6)])
    out = tmp_path / "d.html"
    res = _RUNNER.invoke(
        navigator_app,
        [
            "diff", "--before", str(before), "--after", str(after),
            "--out", str(out), "--max-detail", "2",
        ],
    )
    assert res.exit_code == 0, res.stdout
    assert "diff too large" in out.read_text(encoding="utf-8")


def test_build_still_works(tmp_path):
    """FR-5 additive — the existing build command is untouched."""
    src = tmp_path / "nodes.json"
    _write_nodes_json(src, [{"key": "A", "does": "x", "status": "built"}])
    res = _RUNNER.invoke(
        navigator_app,
        ["build", "--source", "nodes-json", "--nodes-json", str(src), "--format", "json"],
    )
    assert res.exit_code == 0, res.stdout
    assert '"key": "A"' in res.stdout
