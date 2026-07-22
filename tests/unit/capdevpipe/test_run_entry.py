"""Tests for ``startd8 capdevpipe run`` (FR-17 / Increment D3)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from startd8.capdevpipe_runner import (
    build_pipeline_run_argv,
    discover_profile_docs,
    ensure_pipeline_import,
    resolve_embed_dir,
    resolve_run_config,
    run_embedded_pipeline,
)
from startd8.exceptions import ValidationError


class TestResolveEmbedDir:
    def test_explicit_embed_dir(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        assert resolve_embed_dir(tmp_path, embed_dir=embed) == embed.resolve()

    def test_discovers_under_cwd(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        assert resolve_embed_dir(tmp_path) == embed.resolve()

    def test_missing_embed_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="Missing .cap-dev-pipe"):
            resolve_embed_dir(tmp_path)


class TestEnsurePipelineImport:
    def test_requires_pipeline_package(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        with pytest.raises(
            ValidationError, match="missing the managed `pipeline/` package"
        ):
            ensure_pipeline_import(embed)

    def test_inserts_embed_on_sys_path(self, tmp_path: Path, monkeypatch) -> None:
        import startd8.capdevpipe_runner as runner_mod

        embed = tmp_path / ".cap-dev-pipe"
        (embed / "pipeline").mkdir(parents=True)
        monkeypatch.setattr(runner_mod.sys, "path", [])
        ensure_pipeline_import(embed)
        assert str(embed.resolve()) in runner_mod.sys.path


class TestBuildPipelineRunArgv:
    def test_injects_config_and_yes_by_default(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        config = embed / "pipeline.yaml"
        config.write_text("project:\n  name: demo\n", encoding="utf-8")

        argv = build_pipeline_run_argv(embed, ["--dry-run"])
        assert argv[0] == "run"
        assert "--config" in argv
        assert str(config.resolve()) in argv
        assert "--yes" in argv
        assert "--dry-run" in argv

    def test_respects_explicit_interactive(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        (embed / "pipeline.yaml").write_text(
            "project:\n  name: demo\n", encoding="utf-8"
        )

        argv = build_pipeline_run_argv(embed, ["--interactive"])
        assert "--yes" not in argv

    def test_config_free_when_no_pipeline_yaml(self, tmp_path: Path) -> None:
        # Issue #220: an orchestrator install ships no pipeline.yaml — run config-free
        # instead of hard-erroring.
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()

        argv = build_pipeline_run_argv(
            embed, ["--plan", "python/python-plan.md", "--project", "demo"]
        )
        assert argv[0] == "run"
        assert "--config" not in argv
        assert "--plan" in argv
        assert "--yes" in argv

    def test_explicit_missing_config_still_raises(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        with pytest.raises(ValidationError, match="Missing pipeline config"):
            build_pipeline_run_argv(embed, [], config_path=embed / "nope.yaml")

    def test_passthrough_config_is_not_double_added(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        (embed / "pipeline.yaml").write_text(
            "project:\n  name: demo\n", encoding="utf-8"
        )

        argv = build_pipeline_run_argv(embed, ["--config", "/tmp/other.yaml"])
        assert argv.count("--config") == 1
        assert "/tmp/other.yaml" in argv


class TestResolveRunConfig:
    def test_default_pipeline_yaml_used_when_present(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        cfg = embed / "pipeline.yaml"
        cfg.write_text("project:\n  name: demo\n", encoding="utf-8")
        assert resolve_run_config(embed, None) == cfg.resolve()

    def test_none_when_no_default(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        assert resolve_run_config(embed, None) is None

    def test_explicit_missing_raises(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        with pytest.raises(ValidationError, match="Missing pipeline config"):
            resolve_run_config(embed, embed / "absent.yaml")


class TestRunEmbeddedPipeline:
    def test_delegates_to_pipeline_main(self, tmp_path: Path, monkeypatch) -> None:
        project = tmp_path / "project"
        project.mkdir()
        embed = project / ".cap-dev-pipe"
        (embed / "pipeline").mkdir(parents=True)
        (embed / "pipeline.yaml").write_text(
            "project:\n  name: demo\n", encoding="utf-8"
        )

        captured: dict = {}

        def fake_invoke(argv, *, embed_dir):
            captured["argv"] = argv
            captured["embed_dir"] = embed_dir
            return 0

        monkeypatch.setattr(
            "startd8.capdevpipe_runner._invoke_pipeline_main",
            fake_invoke,
        )

        rc = run_embedded_pipeline(cwd=project, extra_argv=["--dry-run"])
        assert rc == 0
        assert captured["embed_dir"] == embed.resolve()
        assert captured["argv"][0] == "run"
        assert "--dry-run" in captured["argv"]
        assert "--config" in captured["argv"]

    def _make_configless_embed(self, tmp_path: Path):
        project = tmp_path / "project"
        project.mkdir()
        embed = project / ".cap-dev-pipe"
        (embed / "pipeline").mkdir(parents=True)
        # Orchestrator-style embed: pipeline.env but no pipeline.yaml.
        (embed / "pipeline.env").write_text(
            'PROJECT_NAME="demo"\nPROJECT_ROOT="/work/demo"\n', encoding="utf-8"
        )
        return project, embed

    def test_config_free_run_hydrates_project_from_pipeline_env(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        project, embed = self._make_configless_embed(tmp_path)
        # Isolate os.environ: the code adds keys via setdefault that monkeypatch's
        # delenv/setenv would not auto-undo. Patch the whole mapping with a copy.
        clean = {
            k: v
            for k, v in os.environ.items()
            if k not in ("PROJECT_NAME", "PROJECT_ROOT")
        }
        monkeypatch.setattr(os, "environ", clean)

        captured: dict = {}

        def fake_invoke(argv, *, embed_dir):
            captured["argv"] = argv
            return 0

        monkeypatch.setattr(
            "startd8.capdevpipe_runner._invoke_pipeline_main", fake_invoke
        )

        rc = run_embedded_pipeline(cwd=project, extra_argv=["--dry-run"])
        assert rc == 0
        assert "--config" not in captured["argv"]
        # Symlink-safe: project identity is exported from the embed's pipeline.env.
        assert os.environ["PROJECT_NAME"] == "demo"
        assert os.environ["PROJECT_ROOT"] == "/work/demo"

    def test_config_free_run_does_not_clobber_cli_project_root(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        project, embed = self._make_configless_embed(tmp_path)
        clean = {
            k: v
            for k, v in os.environ.items()
            if k not in ("PROJECT_NAME", "PROJECT_ROOT")
        }
        monkeypatch.setattr(os, "environ", clean)

        monkeypatch.setattr(
            "startd8.capdevpipe_runner._invoke_pipeline_main",
            lambda argv, *, embed_dir: 0,
        )

        # User passes --project-root explicitly; env must NOT override it (env outranks CLI
        # in the pipeline), so we refuse to export PROJECT_ROOT here.
        run_embedded_pipeline(
            cwd=project, extra_argv=["--project-root", "/explicit/root"]
        )
        assert "PROJECT_ROOT" not in os.environ


class TestDiscoverProfileDocs:
    def _write_profile(self, embed: Path, lang: str) -> None:
        d = embed / lang
        d.mkdir(parents=True)
        (d / f"{lang}-plan.md").write_text("# plan\n", encoding="utf-8")
        (d / f"{lang}-requirements.md").write_text("# reqs\n", encoding="utf-8")

    def test_finds_single_pair_ignores_non_profile_dirs(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        self._write_profile(embed, "python")
        # Embed subtrees that must NOT be mistaken for profiles.
        (embed / "pipeline").mkdir()
        (embed / "design").mkdir()
        (embed / "pipeline.env").write_text("PROJECT_NAME=x\n", encoding="utf-8")

        found = discover_profile_docs(embed)
        assert [lang for lang, _, _ in found] == ["python"]
        _, plan, reqs = found[0]
        assert plan.name == "python-plan.md" and reqs.name == "python-requirements.md"

    def test_partial_pair_does_not_qualify(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        d = embed / "go"
        d.mkdir()
        (d / "go-plan.md").write_text("# plan\n", encoding="utf-8")  # no requirements
        assert discover_profile_docs(embed) == []

    def test_multiple_profiles_sorted(self, tmp_path: Path) -> None:
        embed = tmp_path / ".cap-dev-pipe"
        embed.mkdir()
        self._write_profile(embed, "python")
        self._write_profile(embed, "go")
        assert [lang for lang, _, _ in discover_profile_docs(embed)] == ["go", "python"]


class TestConfigFreeProfileAutofill:
    def _make_embed(self, tmp_path: Path, langs: tuple[str, ...]):
        project = tmp_path / "project"
        project.mkdir()
        embed = project / ".cap-dev-pipe"
        (embed / "pipeline").mkdir(parents=True)
        (embed / "pipeline.env").write_text('PROJECT_NAME="demo"\n', encoding="utf-8")
        for lang in langs:
            d = embed / lang
            d.mkdir()
            (d / f"{lang}-plan.md").write_text("# plan\n", encoding="utf-8")
            (d / f"{lang}-requirements.md").write_text("# reqs\n", encoding="utf-8")
        return project, embed

    def _capture_argv(self, monkeypatch) -> dict:
        captured: dict = {}

        def fake_invoke(argv, *, embed_dir):
            captured["argv"] = argv
            return 0

        monkeypatch.setattr(
            "startd8.capdevpipe_runner._invoke_pipeline_main", fake_invoke
        )
        return captured

    def test_zero_flag_run_autofills_the_single_profile(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        project, embed = self._make_embed(tmp_path, ("python",))
        captured = self._capture_argv(monkeypatch)

        rc = run_embedded_pipeline(cwd=project)  # no extra flags at all
        assert rc == 0
        argv = captured["argv"]
        assert "--config" not in argv
        assert "--plan" in argv
        assert str((embed / "python" / "python-plan.md").resolve()) in argv
        assert str((embed / "python" / "python-requirements.md").resolve()) in argv

    def test_autofill_respects_explicit_plan(self, tmp_path: Path, monkeypatch) -> None:
        project, embed = self._make_embed(tmp_path, ("python",))
        captured = self._capture_argv(monkeypatch)

        run_embedded_pipeline(cwd=project, extra_argv=["--plan", "custom/plan.md"])
        argv = captured["argv"]
        assert argv.count("--plan") == 1
        assert "custom/plan.md" in argv
        # Did not also inject the discovered python plan.
        assert str((embed / "python" / "python-plan.md").resolve()) not in argv

    def test_ambiguous_profiles_raise(self, tmp_path: Path, monkeypatch) -> None:
        project, _ = self._make_embed(tmp_path, ("python", "go"))
        self._capture_argv(monkeypatch)
        with pytest.raises(ValidationError, match="Multiple language profiles"):
            run_embedded_pipeline(cwd=project)
