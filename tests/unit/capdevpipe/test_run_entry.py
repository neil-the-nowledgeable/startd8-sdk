"""Tests for ``startd8 capdevpipe run`` (FR-17 / Increment D3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.capdevpipe_runner import (
    build_pipeline_run_argv,
    ensure_pipeline_import,
    resolve_embed_dir,
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
        with pytest.raises(ValidationError, match="missing the managed `pipeline/` package"):
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
        (embed / "pipeline.yaml").write_text("project:\n  name: demo\n", encoding="utf-8")

        argv = build_pipeline_run_argv(embed, ["--interactive"])
        assert "--yes" not in argv


class TestRunEmbeddedPipeline:
    def test_delegates_to_pipeline_main(self, tmp_path: Path, monkeypatch) -> None:
        project = tmp_path / "project"
        project.mkdir()
        embed = project / ".cap-dev-pipe"
        (embed / "pipeline").mkdir(parents=True)
        (embed / "pipeline.yaml").write_text("project:\n  name: demo\n", encoding="utf-8")

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
