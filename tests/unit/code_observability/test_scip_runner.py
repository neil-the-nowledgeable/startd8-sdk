"""Inc-0 runner tests (REQ-CKG-200/230) — graceful advisory degrade, never raise."""

from __future__ import annotations

from startd8.code_observability import scip_runner
from startd8.code_observability.scip_runner import run_index


def test_import_safe_without_protobuf_extra():
    # REQ-CKG-710: the package + parse_symbol + runner import and work even when the
    # [code-observability] extra (protobuf) is absent; only the reader needs it.
    from startd8.code_observability import parse_symbol, run_index as _ri  # noqa: F401
    ps = parse_symbol("scip-typescript npm zod 3.25.76 v3/`types.d.cts`/ZodObject#extend().")
    assert ps is not None and ps.package == "zod"


def _project(tmp_path, *, pkg="{}", tsconfig=None):
    (tmp_path / "package.json").write_text(pkg)
    if tsconfig is not None:
        (tmp_path / "tsconfig.json").write_text(tsconfig)
    return tmp_path


def test_none_when_tool_unavailable(tmp_path, monkeypatch):
    _project(tmp_path, pkg='{"dependencies":{}}')
    monkeypatch.setattr(scip_runner.shutil, "which", lambda _name: None)  # no scip-typescript, no npx
    assert run_index(tmp_path) is None


def test_none_on_corrupt_package_json(tmp_path, monkeypatch):
    _project(tmp_path, pkg="{ this is : not json ]")
    # Tool "available" so we prove it's the config guard that degrades, not a missing tool.
    monkeypatch.setattr(scip_runner.shutil, "which", lambda name: "/usr/bin/" + name)
    assert run_index(tmp_path) is None


def test_jsonc_tsconfig_with_comments_is_accepted(tmp_path, monkeypatch):
    # A real Next.js tsconfig has // and /* */ comments + trailing commas — must NOT degrade on that.
    _project(
        tmp_path,
        pkg='{"dependencies":{}}',
        tsconfig='{\n  // comment\n  "compilerOptions": { "strict": true, },\n  /* block */\n}\n',
    )
    calls = {}

    def fake_run(argv, **kw):
        calls["argv"] = argv
        out = kw["cwd"] + "/index.scip"
        open(out, "wb").write(b"")  # tool "succeeds"

        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(scip_runner.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(scip_runner.subprocess, "run", fake_run)
    out = run_index(tmp_path)
    assert out is not None and out.name == "index.scip"
    assert calls["argv"][:2] == ["scip-typescript", "index"]  # resolved tool, fixed argv


def test_none_when_project_root_escapes_workspace(tmp_path, monkeypatch):
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "package.json").write_text("{}")
    monkeypatch.setattr(scip_runner.shutil, "which", lambda name: "/usr/bin/" + name)
    # workspace is a sibling that does NOT contain proj -> refuse
    (tmp_path / "ws").mkdir()
    assert run_index(tmp_path / "proj", workspace_root=tmp_path / "ws") is None


def test_none_on_nonzero_exit(tmp_path, monkeypatch):
    _project(tmp_path, pkg="{}")
    monkeypatch.setattr(scip_runner.shutil, "which", lambda name: "/usr/bin/" + name)

    def fake_run(argv, **kw):
        class R:
            returncode = 2
            stderr = "boom"
        return R()

    monkeypatch.setattr(scip_runner.subprocess, "run", fake_run)
    assert run_index(tmp_path) is None
