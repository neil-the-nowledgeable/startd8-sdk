"""Tests for the cap-dev-pipe install execution engine (task #3).

Covers ``locate_source`` (FR-2), target validation (FR-3), per-action idempotency
(``Action.is_satisfied``, R2-S3), the generic applier, write confinement (NFR-6 basic),
the ``_run_actions`` engine — success / idempotent replay / rollback / repairable
(FR-16) — and manifest round-trip (FR-18). The per-concern builders (embed/pipeline.env/
wrapper/profile/gitignore) land in tasks #4–#7; here the engine is driven with synthetic
action lists, which is exactly how ``repair``/``upgrade`` will replay it.
"""

import os

import pytest

from startd8.capdevpipe_installer import (
    EMBED_DIR_NAME,
    MANIFEST_FILENAME,
    Action,
    ActionType,
    CapDevPipeInstaller,
    InstallConfig,
    InstallMethod,
    Manifest,
    ManifestState,
    ProfileSpec,
)
from startd8.exceptions import ConfigurationError, FileOperationError, ValidationError
from tests.unit.capdevpipe.conftest import seed_capdevpipe_manifest

pytestmark = pytest.mark.unit


@pytest.fixture
def installer():
    return CapDevPipeInstaller()


@pytest.fixture
def fake_source(tmp_path):
    """A minimal directory that passes cap-dev-pipe checkout validation (SOURCE_MARKERS)."""
    src = tmp_path / "cap-dev-pipe"
    src.mkdir()
    (src / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (src / "install-cap-dev-pipe.sh").write_text(
        "#!/usr/bin/env bash\n", encoding="utf-8"
    )
    (src / "design").mkdir()
    (src / "prompts").mkdir()
    seed_capdevpipe_manifest(src)
    return src


@pytest.fixture
def target(tmp_path):
    t = tmp_path / "project"
    t.mkdir()
    return t


def _cfg(source, target, method=InstallMethod.SYMLINK, profiles=None):
    return InstallConfig(
        source_path=source,
        target_root=target,
        method=method,
        pipeline_env={},
        default_lang="python",
        profiles=profiles or [],
    )


# --------------------------------------------------------------------------- #
# locate_source (FR-2)
# --------------------------------------------------------------------------- #


class TestLocateSource:
    def test_valid_override_returns_resolved_path(self, installer, fake_source):
        assert installer.locate_source(fake_source) == fake_source.resolve()

    def test_missing_dir_raises_configuration_error_naming_path(
        self, installer, tmp_path
    ):
        missing = tmp_path / "nope"
        with pytest.raises(ConfigurationError) as exc:
            installer.locate_source(missing)
        assert str(missing) in str(exc.value)  # NFR-5: names the path

    def test_not_a_checkout_raises_with_missing_markers(self, installer, tmp_path):
        bare = tmp_path / "bare"
        bare.mkdir()
        (bare / "run.sh").write_text("", encoding="utf-8")  # only one marker
        with pytest.raises(ConfigurationError) as exc:
            installer.locate_source(bare)
        msg = str(exc.value)
        assert "embed-manifest.yaml" in msg
        assert "install-cap-dev-pipe.sh" in msg and "design" in msg and "prompts" in msg


# --------------------------------------------------------------------------- #
# target validation (FR-3)
# --------------------------------------------------------------------------- #


class TestValidateTarget:
    def test_non_directory_target_raises(self, installer, fake_source, tmp_path):
        cfg = _cfg(fake_source, tmp_path / "does-not-exist")
        with pytest.raises(ValidationError):
            installer._validate_target(cfg)

    def test_refuses_target_equal_to_source(self, installer, fake_source):
        cfg = _cfg(fake_source, fake_source)
        with pytest.raises(ValidationError) as exc:
            installer._validate_target(cfg)
        assert "source tree" in str(exc.value)

    def test_refuses_target_inside_source(self, installer, fake_source):
        inside = fake_source / "sub"
        inside.mkdir()
        cfg = _cfg(fake_source, inside)
        with pytest.raises(ValidationError):
            installer._validate_target(cfg)

    def test_accepts_separate_target(self, installer, fake_source, target):
        installer._validate_target(_cfg(fake_source, target))  # no raise


# --------------------------------------------------------------------------- #
# Action.is_satisfied (idempotency, R2-S3)
# --------------------------------------------------------------------------- #


class TestActionIsSatisfied:
    def test_mkdir(self, target):
        a = Action(type=ActionType.MKDIR, target=target / "d")
        assert not a.is_satisfied()
        (target / "d").mkdir()
        assert a.is_satisfied()

    def test_symlink_correct_vs_wrong_target(self, target, tmp_path):
        src = tmp_path / "src.sh"
        src.write_text("x", encoding="utf-8")
        link = target / "link.sh"
        a = Action(type=ActionType.SYMLINK, target=link, source=src)
        assert not a.is_satisfied()
        os.symlink(src, link)
        assert a.is_satisfied()
        # Re-point elsewhere -> no longer satisfied.
        other = tmp_path / "other.sh"
        other.write_text("y", encoding="utf-8")
        link.unlink()
        os.symlink(other, link)
        assert not a.is_satisfied()

    def test_write_file_content_and_mode(self, target):
        f = target / "pipeline.env"
        a = Action(type=ActionType.WRITE_FILE, target=f, content="A=1\n", mode=0o600)
        assert not a.is_satisfied()
        f.write_text("A=1\n", encoding="utf-8")
        os.chmod(f, 0o600)
        assert a.is_satisfied()
        f.write_text("A=2\n", encoding="utf-8")  # content drift
        assert not a.is_satisfied()

    def test_gitignore_ensure(self, target):
        gi = target / ".gitignore"
        a = Action(
            type=ActionType.GITIGNORE_ENSURE,
            target=gi,
            detail=".cap-dev-pipe/pipeline-output/",
        )
        assert not a.is_satisfied()
        gi.write_text(".cap-dev-pipe/pipeline-output/\n", encoding="utf-8")
        assert a.is_satisfied()

    def test_run_subprocess_never_satisfied(self, target):
        a = Action(type=ActionType.RUN_SUBPROCESS, target=target, argv=["true"])
        assert not a.is_satisfied()


# --------------------------------------------------------------------------- #
# confinement (NFR-6 basic)
# --------------------------------------------------------------------------- #


class TestConfine:
    def test_allows_path_inside_target(self, installer, target):
        installer._confine(target / EMBED_DIR_NAME / "run.sh", target)  # no raise

    def test_refuses_path_outside_target(self, installer, target, tmp_path):
        outside = tmp_path / "elsewhere" / "x"
        with pytest.raises(FileOperationError):
            installer._confine(outside, target)

    def test_refuses_write_through_preexisting_symlink_escape(
        self, installer, target, tmp_path
    ):
        # A pre-existing symlink component that redirects outside the target is refused
        # (basic realpath check; P2 hardens the full TOCTOU story).
        outside = tmp_path / "outside"
        outside.mkdir()
        (target / "link").symlink_to(outside)
        with pytest.raises(FileOperationError):
            installer._confine(target / "link" / "x", target)


# --------------------------------------------------------------------------- #
# _run_actions engine (FR-16)
# --------------------------------------------------------------------------- #


def _basic_actions(source, target):
    """A representative symlink-path slice: mkdir, symlink, write env (0600), gitignore."""
    embed = target / EMBED_DIR_NAME
    return [
        Action(type=ActionType.MKDIR, target=embed),
        Action(
            type=ActionType.SYMLINK, target=embed / "run.sh", source=source / "run.sh"
        ),
        Action(
            type=ActionType.WRITE_FILE,
            target=embed / "pipeline.env",
            content="PROJECT_NAME=demo\n",
            mode=0o600,
        ),
        Action(
            type=ActionType.GITIGNORE_ENSURE,
            target=target / ".gitignore",
            detail=".cap-dev-pipe/pipeline-output/",
        ),
    ]


class TestRunActionsSuccess:
    def test_applies_all_and_writes_manifest(self, installer, fake_source, target):
        cfg = _cfg(fake_source, target, profiles=[ProfileSpec(lang="python")])
        result = installer._run_actions(_basic_actions(fake_source, target), cfg)

        assert result.success and not result.rolled_back and not result.repairable
        embed = target / EMBED_DIR_NAME
        assert (embed / "run.sh").is_symlink()
        assert os.readlink(embed / "run.sh") == str(
            fake_source / "run.sh"
        )  # absolute target
        assert (embed / "pipeline.env").read_text() == "PROJECT_NAME=demo\n"
        assert (os.stat(embed / "pipeline.env").st_mode & 0o777) == 0o600  # NFR-6
        assert ".cap-dev-pipe/pipeline-output/" in (target / ".gitignore").read_text()
        # Manifest written and round-trips with the owned paths + profile.
        assert result.manifest_path == embed / MANIFEST_FILENAME
        m = installer.read_manifest(target)
        assert m is not None and m.method is InstallMethod.SYMLINK
        assert m.profiles == ["python"]
        assert (embed / "pipeline.env") in m.created_paths

    def test_idempotent_replay_is_a_noop(self, installer, fake_source, target):
        cfg = _cfg(fake_source, target)
        actions = _basic_actions(fake_source, target)
        first = installer._run_actions(actions, cfg)
        # The embed dir is pre-created for the pending manifest, so its MKDIR action is
        # already satisfied — the 3 remaining actions (symlink, write, gitignore) apply.
        assert first.success and len(first.actions_applied) == 3
        # Second run: everything already satisfied -> nothing applied, still success.
        second = installer._run_actions(_basic_actions(fake_source, target), cfg)
        assert second.success and second.actions_applied == []


class TestRunActionsFailure:
    def test_rollback_removes_created_paths_on_symlink_path_failure(
        self, installer, fake_source, target, monkeypatch
    ):
        actions = _basic_actions(fake_source, target)
        real_apply = installer._apply_action

        def failing_apply(action, cfg):
            if action.type is ActionType.WRITE_FILE:
                raise RuntimeError("disk full")
            return real_apply(action, cfg)

        monkeypatch.setattr(installer, "_apply_action", failing_apply)
        result = installer._run_actions(actions, _cfg(fake_source, target))

        assert not result.success and result.rolled_back and not result.repairable
        # The mkdir + symlink created before the failure were rolled back.
        assert not (target / EMBED_DIR_NAME).exists()
        assert "disk full" in (result.error or "")

    def test_subprocess_failure_is_repairable_not_rolled_back(
        self, installer, fake_source, target
    ):
        # A path containing an external subprocess cannot be cleanly reversed (R2-S2).
        actions = [
            Action(type=ActionType.MKDIR, target=target / EMBED_DIR_NAME),
            Action(
                type=ActionType.RUN_SUBPROCESS,
                target=target / EMBED_DIR_NAME,
                argv=["sh", "-c", "exit 3"],
            ),
        ]
        result = installer._run_actions(
            actions, _cfg(fake_source, target, InstallMethod.COPY)
        )
        assert not result.success and result.repairable and not result.rolled_back


# --------------------------------------------------------------------------- #
# manifest round-trip (FR-18)
# --------------------------------------------------------------------------- #


class TestManifestRoundTrip:
    def test_to_from_dict(self, fake_source, target):
        m = Manifest(
            method=InstallMethod.SYMLINK,
            source_path=fake_source,
            created_paths=[target / EMBED_DIR_NAME / "run.sh"],
            profiles=["python", "go"],
            state=ManifestState.COMPLETE,
        )
        back = Manifest.from_dict(m.to_dict())
        assert back.method is InstallMethod.SYMLINK
        assert back.source_path == fake_source
        assert back.profiles == ["python", "go"]
        assert back.created_paths == [target / EMBED_DIR_NAME / "run.sh"]
        assert back.manifest_version == m.manifest_version

    def test_read_manifest_absent_returns_none(self, installer, target):
        assert installer.read_manifest(target) is None

    def test_read_manifest_corrupt_returns_none(self, installer, target):
        embed = target / EMBED_DIR_NAME
        embed.mkdir()
        (embed / MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")
        assert installer.read_manifest(target) is None


# --------------------------------------------------------------------------- #
# plan_actions / execute wiring
# --------------------------------------------------------------------------- #


class TestPlanAndExecuteWiring:
    def test_plan_actions_validates_target_before_building(
        self, installer, fake_source, tmp_path
    ):
        # Invalid target raises ValidationError before reaching the (unimplemented) builders.
        cfg = _cfg(fake_source, tmp_path / "missing")
        with pytest.raises(ValidationError):
            installer.plan_actions(cfg)

    def test_execute_delegates_to_run_actions(
        self, installer, fake_source, target, monkeypatch
    ):
        actions = _basic_actions(fake_source, target)
        monkeypatch.setattr(installer, "plan_actions", lambda cfg: actions)
        result = installer.execute(_cfg(fake_source, target))
        assert result.success
        assert (target / EMBED_DIR_NAME / "run.sh").is_symlink()

    def test_execute_consumes_preview_without_recomputing(
        self, installer, cfg_factory, monkeypatch
    ):
        """FR-13/FR-16 (R4-F5): the previewed action list IS the executed list.

        When the preview is passed to execute(), it must NOT recompute plan_actions —
        otherwise preview and execution can drift. Proven by counting plan_actions calls.
        """
        cfg = cfg_factory()
        calls = {"n": 0}
        real_plan = installer.plan_actions

        def counting_plan(c):
            calls["n"] += 1
            return real_plan(c)

        monkeypatch.setattr(installer, "plan_actions", counting_plan)

        preview = installer.plan_actions(cfg)  # the TUI's preview step -> n == 1
        assert calls["n"] == 1
        result = installer.execute(cfg, actions=preview)  # must not recompute
        assert result.success
        assert calls["n"] == 1, "execute() recomputed plan_actions instead of consuming preview"
        # Every applied action came from the previewed list (no surprise writes).
        preview_targets = {a.target for a in preview}
        assert {a.target for a in result.actions_applied} <= preview_targets

    def test_execute_without_actions_still_plans(
        self, installer, cfg_factory, monkeypatch
    ):
        """Headless/library callers that skip the preview get a computed plan (back-compat)."""
        cfg = cfg_factory()
        calls = {"n": 0}
        real_plan = installer.plan_actions

        def counting_plan(c):
            calls["n"] += 1
            return real_plan(c)

        monkeypatch.setattr(installer, "plan_actions", counting_plan)
        result = installer.execute(cfg)  # no actions -> execute computes them
        assert result.success
        assert calls["n"] == 1
