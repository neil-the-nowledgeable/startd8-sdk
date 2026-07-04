"""Phase 1 hardening controls for the cross-tool authoring controller.

Focused, offline tests (no live CLI, no network, no real credentials): command construction,
per-tool environment allow-listing, isolation/metadata-without-secrets, fail-closed credentials,
immutable retry capture, and dry-run behavior.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "run_cross_tool_bias_authoring.py"

spec = importlib.util.spec_from_file_location("run_cross_tool_bias_authoring", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

VENDOR_CREDENTIAL = {
    "claude-code": "ANTHROPIC_API_KEY",
    "codex-cli": "OPENAI_API_KEY",
    "gemini-cli": "GOOGLE_API_KEY",
}
ALL_CREDENTIALS = {name: f"secret-value-for-{name}" for name in set(VENDOR_CREDENTIAL.values())}


# --- command construction (declarative single source of truth) ----------------------------------

@pytest.mark.parametrize("tool_id", list(mod.TOOL_POLICY))
def test_command_uses_policy_argv(tool_id):
    cmd = mod.build_tool_command(tool_id, "/opt/bin/tool")
    assert cmd[0] == "/opt/bin/tool"
    assert cmd[1:] == mod.TOOL_POLICY[tool_id]["argv"]


def test_unknown_tool_is_rejected():
    with pytest.raises((KeyError, ValueError)):
        mod.build_tool_command("not-a-tool", "/opt/bin/tool")


def test_every_privilege_flag_has_a_documented_rationale():
    # Guide req 2: no privilege bypass without an approved rationale. Every flag in argv must be
    # accounted for in flag_rationale (individually or as part of a comma-joined rationale key).
    for tool_id, policy in mod.TOOL_POLICY.items():
        documented = set()
        for key in policy["flag_rationale"]:
            for part in key.split(","):
                documented.add(part.split("=")[0])
        for flag in policy["argv"]:
            if flag.startswith("-"):
                assert flag in documented, f"{tool_id}: flag {flag!r} lacks a documented rationale"


# --- environment allow-listing + isolation (the security crux) ----------------------------------

@pytest.mark.parametrize("tool_id,cred_name", VENDOR_CREDENTIAL.items())
def test_env_contains_only_this_tools_credential(tool_id, cred_name):
    env, exposure = mod.build_tool_env(tool_id, ALL_CREDENTIALS)
    policy = mod.TOOL_POLICY[tool_id]
    # this tool's credential present under each declared injection name
    for name in policy["inject_as"]:
        assert env[name] == ALL_CREDENTIALS[cred_name]
    # NO other vendor's credential leaks into this child
    other_names = set()
    for other_id, other in mod.TOOL_POLICY.items():
        if other_id != tool_id:
            other_names |= set(other["inject_as"])
    leaked = (other_names - set(policy["inject_as"])) & set(env)
    assert not leaked, f"{tool_id} child leaked other-vendor env: {leaked}"


def test_env_is_scrubbed_not_full_environment(monkeypatch):
    # An unrelated ambient secret must NEVER reach a child (guide completion criterion).
    monkeypatch.setenv("UNRELATED_PROD_DB_PASSWORD", "should-not-propagate")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env, _ = mod.build_tool_env("codex-cli", ALL_CREDENTIALS)
    assert "UNRELATED_PROD_DB_PASSWORD" not in env
    assert env.get("PATH") == "/usr/bin:/bin"  # base allow-list still passes through
    # only allow-listed base names + this tool's injected/extra names are present
    allowed = set(mod._BASE_ENV_ALLOWLIST) | set(mod.TOOL_POLICY["codex-cli"]["inject_as"]) \
        | set(mod.TOOL_POLICY["codex-cli"]["extra_env"])
    assert set(env) <= allowed


def test_missing_credential_fails_closed():
    with pytest.raises(RuntimeError):
        mod.build_tool_env("gemini-cli", {})  # no GOOGLE_API_KEY available


def test_execute_run_converts_timeout_to_failed_result(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        raise mod.subprocess.TimeoutExpired(
            cmd=kwargs.get("args", args[0]),
            timeout=kwargs["timeout"],
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    code, stdout, stderr = mod.execute_run(
        "codex-cli",
        "/opt/bin/codex",
        "prompt",
        tmp_path,
        {},
        timeout_s=0.5,
    )

    assert code == 124
    assert stdout == "partial stdout"
    assert "partial stderr" in stderr
    assert "timed out after 0.5 seconds" in stderr


def test_failure_output_preview_falls_back_to_stdout():
    assert mod.failure_output_preview("Credit balance is too low\n", "") == "Credit balance is too low"
    assert mod.failure_output_preview("stdout detail", "stderr detail") == "stderr detail"


def test_classify_attempt_status_distinguishes_timeout_with_complete_files():
    assert mod.classify_attempt_status(0, []) == "success"
    assert mod.classify_attempt_status(124, []) == "completed_with_timeout"
    assert mod.classify_attempt_status(124, ["suite_manifest.json"]) == "failed"
    assert mod.classify_attempt_status(1, []) == "failed"


def test_attempt_has_required_artifacts_for_success_and_completed_timeout():
    assert mod.attempt_has_required_artifacts("success")
    assert mod.attempt_has_required_artifacts("completed_with_timeout")
    assert not mod.attempt_has_required_artifacts("failed")


def test_metadata_records_names_not_secret_values():
    meta = mod.command_policy_metadata("claude-code", "/opt/bin/claude", "1.2.3")
    blob = json.dumps(meta)
    for secret in ALL_CREDENTIALS.values():
        assert secret not in blob
    assert meta["tool_policy_version"] == mod.TOOL_POLICY_VERSION
    assert meta["exposed_secret_env_names"] == mod.TOOL_POLICY["claude-code"]["inject_as"]
    assert meta["credential_source"] == "ANTHROPIC_API_KEY"


def test_required_credentials_are_exactly_the_three_vendors():
    assert mod.required_credential_names() == set(VENDOR_CREDENTIAL.values())


def test_smoke_plan_is_bounded_and_non_evidence(tmp_path):
    manifest = mod.prepare._load_manifest(mod.prepare.DEFAULT_MANIFEST)

    plan = mod.build_authoring_plan(manifest, tmp_path / "out", smoke=True)

    assert plan["evidence_role"] == "non_evidence_smoke"
    assert "must not be reconciled" in plan["artifact_policy"]
    assert plan["raw_capture_root"] == str(tmp_path / "out" / "smoke" / "raw")
    assert plan["normalized_artifact_root"] == str(tmp_path / "out" / "smoke" / "normalized")
    assert plan["run_count"] == 6
    assert {run["ordinal"] for run in plan["runs"]} == set(range(1, 7))
    assert all(run["scheduled_ordinal"] >= run["ordinal"] for run in plan["runs"])
    assert {
        (run["experiment"], run["tool_id"])
        for run in plan["runs"]
    } == {
        ("suite_author", "claude-code"),
        ("suite_author", "codex-cli"),
        ("suite_author", "gemini-cli"),
        ("spec_author", "claude-code"),
        ("spec_author", "codex-cli"),
        ("spec_author", "gemini-cli"),
    }


def test_smoke_plan_rejects_zero_samples(tmp_path):
    manifest = mod.prepare._load_manifest(mod.prepare.DEFAULT_MANIFEST)

    with pytest.raises(ValueError, match="samples_per_cell must be >= 1"):
        mod.build_authoring_plan(manifest, tmp_path / "out", smoke=True, smoke_samples_per_cell=0)


def test_smoke_timeout_must_be_positive(tmp_path):
    with pytest.raises(SystemExit):
        mod.main([
            "--output-dir",
            str(tmp_path / "out"),
            "--smoke",
            "--smoke-timeout-seconds",
            "0",
        ])


def _render_suite_prompt(tmp_path: Path, *, tool_id: str, author_vendor: str) -> str:
    return mod.render_prompt(
        repo=REPO,
        experiment="suite_author",
        tool_id=tool_id,
        author_vendor=author_vendor,
        sample_index=1,
        ordinal=1,
        run_id=f"render-diff-{tool_id}",
        working_directory=tmp_path / tool_id,
        clean_workspace=tmp_path / tool_id,
        executable_path=f"/opt/bin/{tool_id}",
        executable_version="test",
    )


def _normalize_run_metadata(prompt: str) -> str:
    before, after = prompt.split("\n## Run Metadata\n\n", 1)
    _, rest = after.split("\n\n## Role\n", 1)
    return f"{before}\n## Run Metadata\n\n<RUN_METADATA>\n\n## Role\n{rest}"


def test_openai_and_gemini_suite_prompts_share_bridge_contract(tmp_path):
    openai_prompt = _render_suite_prompt(tmp_path, tool_id="codex-cli", author_vendor="openai")
    gemini_prompt = _render_suite_prompt(tmp_path, tool_id="gemini-cli", author_vendor="google")

    assert _normalize_run_metadata(openai_prompt) == _normalize_run_metadata(gemini_prompt)
    for required in (
        "## Bridge Executability Contract",
        "`suite_manifest.json` must declare the seam under a top-level `bridge_contract` object",
        "bind_invoker(fn)",
        "configure(adapter)",
        "run_ok_cases(call=None)",
        "JSON-compatible request and response dictionaries",
        "INVALID_ARGUMENT",
    ):
        assert required in openai_prompt
        assert required in gemini_prompt


def test_rendered_prompt_uses_current_working_directory_not_ephemeral_path(tmp_path):
    prompt = _render_suite_prompt(tmp_path, tool_id="claude-code", author_vendor="anthropic")

    assert "- working_directory: current working directory" in prompt
    assert "- clean_workspace: current working directory, freshly provisioned for this run" in prompt
    assert "Write exactly these files in the current working directory" in prompt
    assert str(tmp_path) not in prompt


def test_suite_author_prompt_orders_manifests_before_suite(tmp_path):
    prompt = _render_suite_prompt(tmp_path, tool_id="claude-code", author_vendor="anthropic")

    assert "Write the two manifest files before writing `suite.py`" in prompt
    suite_manifest_index = prompt.index("- `suite_manifest.json`")
    authoring_manifest_index = prompt.index("- `authoring_manifest.json`")
    suite_py_index = prompt.index("- `suite.py`")

    assert suite_manifest_index < suite_py_index
    assert authoring_manifest_index < suite_py_index


# --- immutable retry capture (R-Phase1-4) --------------------------------------------------------

def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "inputs").mkdir(parents=True)
    (ws / "suite.py").write_text("# generated\n", encoding="utf-8")
    (ws / "__pycache__").mkdir()
    (ws / "__pycache__" / "suite.cpython-314.pyc").write_text("junk", encoding="utf-8")
    return ws


def test_record_attempt_is_immutable_and_excludes_junk(tmp_path):
    run_dir = tmp_path / "run_01"
    ws = _workspace(tmp_path)
    meta = {"attempt": 1, "status": "failed"}
    a1 = mod.record_attempt(run_dir, 1, prompt_text="P", stdout="O", stderr="E",
                            workspace=ws, attempt_meta=meta)
    assert (a1 / "rendered_prompt.md").read_text() == "P"
    assert (a1 / "workspace" / "suite.py").is_file()
    assert not (a1 / "workspace" / "__pycache__").exists()  # execution junk excluded
    # a second attempt writes a SEPARATE record; attempt 1 is untouched
    mod.record_attempt(run_dir, 2, prompt_text="P2", stdout="O2", stderr="E2",
                       workspace=ws, attempt_meta={"attempt": 2, "status": "success"})
    assert (a1 / "rendered_prompt.md").read_text() == "P"  # unchanged
    assert (run_dir / "attempts" / "attempt_02" / "rendered_prompt.md").read_text() == "P2"


def test_record_attempt_refuses_to_overwrite(tmp_path):
    run_dir = tmp_path / "run_01"
    ws = _workspace(tmp_path)
    mod.record_attempt(run_dir, 1, prompt_text="P", stdout="", stderr="", workspace=ws,
                       attempt_meta={"attempt": 1})
    with pytest.raises(FileExistsError):
        mod.record_attempt(run_dir, 1, prompt_text="CLOBBER", stdout="", stderr="", workspace=ws,
                           attempt_meta={"attempt": 1})


# --- dry-run behavior ----------------------------------------------------------------------------

def test_dry_run_emits_plan_and_spends_nothing(tmp_path, capsys):
    rc = mod.main(["--output-dir", str(tmp_path / "out")])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "dry_run"
    assert out["plan"]["run_count"] == 30
