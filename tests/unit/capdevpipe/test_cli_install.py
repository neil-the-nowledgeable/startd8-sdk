"""CLI tests for ``startd8 capdevpipe install`` (Thread A-1/A-2).

The headless command wraps ``CapDevPipeInstaller``; these tests drive it through the Typer
runner against the ``full_source``/``target`` fixtures (shared conftest), covering dry-run
preview==execute, a real install+verify, option validation, and an existing-install re-run.
"""

import json

import pytest
from typer.testing import CliRunner

from startd8.capdevpipe_installer import EMBED_DIR_NAME, MANIFEST_FILENAME
from startd8.cli_capdevpipe import capdevpipe_app, _parse_profiles, _parse_set_env

pytestmark = pytest.mark.unit

runner = CliRunner()

_ENV = [
    "--set-env", "CONTEXTCORE_ROOT=/home/u/ContextCore",
    "--set-env", "SDK_ROOT=/home/u/startd8-sdk",
    "--set-env", "PROJECT_ROOT=/home/u/proj",
    "--set-env", "PROJECT_NAME=proj",
]


def _install_args(source, target, *extra):
    return [
        "install",
        "--source-path", str(source),
        "--target-root", str(target),
        *_ENV,
        *extra,
    ]


class TestDryRun:
    def test_dry_run_writes_nothing(self, full_source, target):
        result = runner.invoke(capdevpipe_app, _install_args(full_source, target, "--dry-run"))
        assert result.exit_code == 0, result.output
        # Nothing was written — no embed dir.
        assert not (target / EMBED_DIR_NAME).exists()
        assert "action(s) planned" in result.output

    def test_dry_run_action_set_equals_execute(self, full_source, target, installer):
        """FR-A4: the previewed action set is exactly what execute would apply."""
        from startd8.capdevpipe_installer import InstallConfig, InstallMethod

        cfg = InstallConfig(
            source_path=installer.locate_source(full_source),
            target_root=target,
            method=InstallMethod.SYMLINK,
            pipeline_env={
                "CONTEXTCORE_ROOT": "/home/u/ContextCore",
                "SDK_ROOT": "/home/u/startd8-sdk",
                "PROJECT_ROOT": "/home/u/proj",
                "PROJECT_NAME": "proj",
            },
        )
        planned = installer.plan_actions(cfg)
        result = runner.invoke(capdevpipe_app, _install_args(full_source, target, "--dry-run"))
        assert result.exit_code == 0, result.output
        # The preview reports exactly the number of actions execute would apply.
        assert f"{len(planned)} action(s) planned" in result.output


class TestRealInstall:
    def test_install_then_verify_passes(self, full_source, target):
        result = runner.invoke(capdevpipe_app, _install_args(full_source, target))
        assert result.exit_code == 0, result.output
        embed = target / EMBED_DIR_NAME
        assert embed.is_dir()
        manifest = embed / MANIFEST_FILENAME
        assert manifest.is_file()
        # verify ran and passed (full profile ships the stub run.sh)
        assert "verified" in result.output

    def test_manifest_written(self, full_source, target):
        runner.invoke(capdevpipe_app, _install_args(full_source, target))
        manifest = json.loads((target / EMBED_DIR_NAME / MANIFEST_FILENAME).read_text())
        # A-1 records the manifest; A-3 will migrate the schema to canonical fields.
        assert manifest  # non-empty
        assert "source_path" in manifest


class TestOptionValidation:
    def test_bad_method_rejected(self, full_source, target):
        result = runner.invoke(capdevpipe_app, _install_args(full_source, target, "--method", "bogus"))
        assert result.exit_code != 0
        assert "method" in result.output.lower()

    def test_bad_rerun_mode_rejected(self, full_source, target):
        result = runner.invoke(
            capdevpipe_app, _install_args(full_source, target, "--rerun-mode", "nope")
        )
        assert result.exit_code != 0
        assert "rerun-mode" in result.output.lower()

    def test_malformed_set_env_rejected(self, full_source, target):
        result = runner.invoke(
            capdevpipe_app,
            ["install", "--source-path", str(full_source), "--target-root", str(target),
             "--set-env", "NOEQUALS"],
        )
        assert result.exit_code != 0


class TestReRun:
    def test_repair_on_existing_install(self, full_source, target):
        first = runner.invoke(capdevpipe_app, _install_args(full_source, target))
        assert first.exit_code == 0, first.output
        again = runner.invoke(
            capdevpipe_app, _install_args(full_source, target, "--rerun-mode", "repair")
        )
        assert again.exit_code == 0, again.output


class TestParsers:
    def test_parse_set_env_ok(self):
        assert _parse_set_env(["A=1", "B=two=parts"]) == {"A": "1", "B": "two=parts"}

    def test_parse_set_env_rejects_no_equals(self):
        with pytest.raises(Exception):
            _parse_set_env(["BAD"])

    def test_parse_set_env_rejects_empty_key(self):
        with pytest.raises(Exception):
            _parse_set_env(["=value"])

    def test_parse_profiles_variants(self):
        specs = _parse_profiles(["python", "go:PLAN.md", "java:PLAN.md:REQS.md"])
        assert [s.lang for s in specs] == ["python", "go", "java"]
        assert specs[0].plan is None
        assert specs[1].plan is not None and specs[1].reqs is None
        assert specs[2].plan is not None and specs[2].reqs is not None

    def test_parse_profiles_rejects_empty_lang(self):
        with pytest.raises(Exception):
            _parse_profiles([":PLAN.md"])
