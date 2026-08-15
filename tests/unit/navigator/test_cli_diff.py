"""REQ-07 FR-5 — the `navigator diff` CLI subcommand."""

from __future__ import annotations

import json

from typer.testing import CliRunner

import pytest

from startd8.navigator.cli_navigator import _load_state, navigator_app

_RUNNER = CliRunner()


# --------------------------------------------------------------------------- #
# _load_state structural guard (Phase-2 robustness) — direct, CLI-runner-free
# --------------------------------------------------------------------------- #
def test_load_state_valid_nodes_json_ok(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text(
        json.dumps({"nodes": [{"key": "A", "does": "x", "children": [{"key": "A.1"}]}]}),
        encoding="utf-8",
    )
    nodes = _load_state(p)
    assert [n.key for n in nodes] == ["A"]
    assert nodes[0].children[0].key == "A.1"  # nested children still load (byte-identical path)


def test_load_state_bare_list_ok(tmp_path):
    p = tmp_path / "bare.json"
    p.write_text(json.dumps([{"key": "A"}]), encoding="utf-8")  # no {"nodes": ...} wrapper
    assert [n.key for n in _load_state(p)] == ["A"]


@pytest.mark.parametrize(
    "payload",
    [
        "42",  # bare scalar
        '"hello"',  # bare string
        json.dumps({"nodes": ["str", 1]}),  # non-object entries
        json.dumps({"nodes": [{"key": "A", "lives": ["x"]}]}),  # non-object lives element
        json.dumps({"nodes": [{"key": "A", "lives": "notalist"}]}),  # lives not a list
        json.dumps({"nodes": [{"key": "A", "children": [9]}]}),  # non-object child
    ],
)
def test_load_state_malformed_raises_valueerror(tmp_path, payload):
    p = tmp_path / "bad.json"
    p.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        _load_state(p)


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


def test_diff_malformed_json_exit_1_no_traceback(tmp_path):
    """A well-formed-JSON-but-not-an-array payload → clean exit 1, not a raw traceback."""
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    before.write_text("42", encoding="utf-8")  # valid JSON, wrong shape
    _write_nodes_json(after, [{"key": "A", "does": "x"}])
    res = _RUNNER.invoke(
        navigator_app,
        ["diff", "--before", str(before), "--after", str(after), "--json"],
    )
    assert res.exit_code == 1
    assert res.exception is None or isinstance(res.exception, SystemExit)


def test_diff_non_object_node_entry_exit_1(tmp_path):
    """A JSON array whose entries are not objects → clean ValueError-backed exit 1."""
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    before.write_text(json.dumps({"nodes": ["not-an-object", 3]}), encoding="utf-8")
    _write_nodes_json(after, [{"key": "A", "does": "x"}])
    res = _RUNNER.invoke(
        navigator_app,
        ["diff", "--before", str(before), "--after", str(after), "--json"],
    )
    assert res.exit_code == 1
    assert res.exception is None or isinstance(res.exception, SystemExit)


def test_diff_non_object_lives_entry_exit_1(tmp_path):
    """A node whose ``lives`` list carries a non-object element → clean exit 1 (no AttributeError)."""
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    before.write_text(
        json.dumps({"nodes": [{"key": "A", "lives": ["bare-string"]}]}), encoding="utf-8"
    )
    _write_nodes_json(after, [{"key": "A", "does": "x"}])
    res = _RUNNER.invoke(
        navigator_app,
        ["diff", "--before", str(before), "--after", str(after), "--json"],
    )
    assert res.exit_code == 1
    assert res.exception is None or isinstance(res.exception, SystemExit)


def test_diff_non_object_child_entry_exit_1(tmp_path):
    """A malformed nested ``children`` entry is caught recursively → clean exit 1."""
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    before.write_text(
        json.dumps({"nodes": [{"key": "A", "children": [7]}]}), encoding="utf-8"
    )
    _write_nodes_json(after, [{"key": "A", "does": "x"}])
    res = _RUNNER.invoke(
        navigator_app,
        ["diff", "--before", str(before), "--after", str(after), "--json"],
    )
    assert res.exit_code == 1
    assert res.exception is None or isinstance(res.exception, SystemExit)


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
