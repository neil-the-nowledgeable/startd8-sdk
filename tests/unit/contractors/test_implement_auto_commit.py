"""Unit tests for ImplementPhaseHandler auto-commit feature."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from startd8.contractors.context_seed_handlers import (
    HandlerConfig,
    ImplementPhaseHandler,
    SeedTask,
)
from startd8.contractors.protocols import GenerationResult


def _seed_task(task_id: str = "T1", title: str = "Feature A") -> SeedTask:
    return SeedTask(
        task_id=task_id,
        title=title,
        task_type="task",
        story_points=3,
        priority="medium",
        labels=[],
        depends_on=[],
        description="Implement feature",
        target_files=["src/feature.py"],
        estimated_loc=50,
        feature_id="F1",
        domain="backend",
        domain_reasoning="test",
        environment_checks=[],
        prompt_constraints=[],
        post_generation_validators=[],
        available_siblings=[],
        existing_content_hash=None,
        design_doc_sections=[],
        artifact_types_addressed=[],
        file_scope={},
    )


def _gen_result(
    paths: list[str],
    success: bool = True,
) -> GenerationResult:
    return GenerationResult(
        success=success,
        generated_files=[Path(p) for p in paths],
        error=None if success else "failed",
        input_tokens=100,
        output_tokens=60,
        cost_usd=0.01,
        iterations=1,
        model="mock:mock",
    )


class TestCommitFeatures:
    """Tests for ImplementPhaseHandler._commit_features."""

    def test_commits_successful_tasks(self):
        """Each successful task gets git add + git commit."""
        config = HandlerConfig(auto_commit=True)
        handler = ImplementPhaseHandler(handler_config=config)
        project_root = Path("/project")

        tasks = [
            _seed_task("T1", "Feature Alpha"),
            _seed_task("T2", "Feature Beta"),
        ]
        gen_results = {
            "T1": _gen_result(["src/alpha.py", "src/alpha_utils.py"]),
            "T2": _gen_result(["src/beta.py"]),
        }

        with patch(
            "startd8.contractors.context_seed.phases.implement.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            handler._commit_features(gen_results, tasks, project_root)

        # T1: 2 git-add calls + 1 commit; T2: 1 git-add + 1 commit = 5 total
        assert mock_run.call_count == 5

        # Verify git add calls for T1
        mock_run.assert_any_call(
            ["git", "add", "src/alpha.py"],
            cwd=project_root, capture_output=True, timeout=30,
        )
        mock_run.assert_any_call(
            ["git", "add", "src/alpha_utils.py"],
            cwd=project_root, capture_output=True, timeout=30,
        )
        # Verify git add for T2
        mock_run.assert_any_call(
            ["git", "add", "src/beta.py"],
            cwd=project_root, capture_output=True, timeout=30,
        )

    def test_skips_failed_tasks(self):
        """Failed tasks are not committed."""
        config = HandlerConfig(auto_commit=True)
        handler = ImplementPhaseHandler(handler_config=config)

        tasks = [_seed_task("T1", "Good"), _seed_task("T2", "Bad")]
        gen_results = {
            "T1": _gen_result(["src/good.py"]),
            "T2": _gen_result(["src/bad.py"], success=False),
        }

        with patch(
            "startd8.contractors.context_seed.phases.implement.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            handler._commit_features(gen_results, tasks, Path("/p"))

        # Only T1: 1 git-add + 1 commit = 2
        assert mock_run.call_count == 2

    def test_skips_empty_generated_files(self):
        """Tasks with no generated files are skipped."""
        config = HandlerConfig(auto_commit=True)
        handler = ImplementPhaseHandler(handler_config=config)

        tasks = [_seed_task("T1", "Empty")]
        gen_results = {
            "T1": _gen_result([]),
        }

        with patch(
            "startd8.contractors.context_seed.phases.implement.subprocess.run"
        ) as mock_run:
            handler._commit_features(gen_results, tasks, Path("/p"))

        mock_run.assert_not_called()

    def test_commit_failure_logged_not_raised(self):
        """A failed git commit logs a warning but doesn't raise."""
        config = HandlerConfig(auto_commit=True)
        handler = ImplementPhaseHandler(handler_config=config)

        tasks = [_seed_task("T1", "Oops")]
        gen_results = {"T1": _gen_result(["src/oops.py"])}

        with patch(
            "startd8.contractors.context_seed.phases.implement.subprocess.run"
        ) as mock_run:
            # git add succeeds, git commit fails
            mock_run.side_effect = [
                MagicMock(returncode=0),  # git add
                MagicMock(returncode=1, stderr="nothing to commit"),  # git commit
            ]
            # Should not raise
            handler._commit_features(gen_results, tasks, Path("/p"))

        assert mock_run.call_count == 2

    def test_commit_message_format(self):
        """Commit message follows feat(task_id): title format."""
        config = HandlerConfig(auto_commit=True)
        handler = ImplementPhaseHandler(handler_config=config)

        tasks = [_seed_task("T42", "Add login page")]
        gen_results = {"T42": _gen_result(["src/login.py"])}

        with patch(
            "startd8.contractors.context_seed.phases.implement.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            handler._commit_features(gen_results, tasks, Path("/p"))

        # Find the commit call (second call)
        commit_call = mock_run.call_args_list[1]
        commit_cmd = commit_call[0][0]
        assert commit_cmd[0:2] == ["git", "commit"]
        msg = commit_cmd[commit_cmd.index("-m") + 1]
        assert msg.startswith("feat(T42): Add login page")
        assert "Artisan IMPLEMENT phase" in msg


class TestHandlerConfigAutoCommit:
    """HandlerConfig.auto_commit default and override."""

    def test_default_true(self):
        """Default is opt-out: auto_commit=True for safety."""
        config = HandlerConfig()
        assert config.auto_commit is True

    def test_cli_override(self):
        config = HandlerConfig.from_config({"auto_commit": False})
        assert config.auto_commit is False


class TestCreateAllAutoCommit:
    """ContextSeedHandlers.create_all forwards auto_commit."""

    def test_auto_commit_forwarded(self):
        from startd8.contractors.context_seed_handlers import ContextSeedHandlers

        handlers = ContextSeedHandlers.create_all(
            enriched_seed_path="/fake/seed.json",
            auto_commit=True,
        )
        from startd8.contractors.artisan_contractor import WorkflowPhase

        impl_handler = handlers[WorkflowPhase.IMPLEMENT]
        assert impl_handler.config.auto_commit is True

    def test_auto_commit_default_true(self):
        """Default is opt-out: handlers get auto_commit=True unless overridden."""
        from startd8.contractors.context_seed_handlers import ContextSeedHandlers

        handlers = ContextSeedHandlers.create_all(
            enriched_seed_path="/fake/seed.json",
        )
        from startd8.contractors.artisan_contractor import WorkflowPhase

        impl_handler = handlers[WorkflowPhase.IMPLEMENT]
        assert impl_handler.config.auto_commit is True

    def test_auto_commit_opt_out(self):
        """--no-auto-commit passes auto_commit=False to disable commits."""
        from startd8.contractors.context_seed_handlers import ContextSeedHandlers

        handlers = ContextSeedHandlers.create_all(
            enriched_seed_path="/fake/seed.json",
            auto_commit=False,
        )
        from startd8.contractors.artisan_contractor import WorkflowPhase

        impl_handler = handlers[WorkflowPhase.IMPLEMENT]
        assert impl_handler.config.auto_commit is False
