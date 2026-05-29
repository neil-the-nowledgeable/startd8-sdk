"""Tests for the embedding builders (task #4): symlink embed, copy embed, copy reconcile.

Covers FR-5 (symlink the curated 17-entry set with **absolute** targets + copy resource
dirs; NFR-3), FR-6 (shell out to the rsync installer; post-rsync reconcile that merges only
the four managed pipeline.env keys preserving non-managed ones — R3-F5 — and removes the
auto-linked root java profile), and the managed-key block-on-empty guard (R2-S6).
"""

import os

import pytest

from startd8.capdevpipe_installer import (
    EMBED_ALIASES,
    EMBED_DIR_NAME,
    EMBED_RESOURCE_DIRS,
    EMBED_SCRIPTS,
    Action,
    ActionType,
    CapDevPipeInstaller,
    InstallConfig,
    InstallMethod,
)
from startd8.exceptions import ConfigurationError

pytestmark = pytest.mark.unit


@pytest.fixture
def installer():
    return CapDevPipeInstaller()


@pytest.fixture
def fake_source(tmp_path):
    """A checkout with all embed-set files + design/prompts present."""
    src = tmp_path / "cap-dev-pipe"
    src.mkdir()
    for name in (*EMBED_SCRIPTS, *EMBED_ALIASES, "install-cap-dev-pipe.sh"):
        (src / name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    for d in EMBED_RESOURCE_DIRS:
        (src / d).mkdir()
        (src / d / "sample.txt").write_text("x", encoding="utf-8")
    return src


@pytest.fixture
def target(tmp_path):
    t = tmp_path / "project"
    t.mkdir()
    return t


def _cfg(source, target, method=InstallMethod.SYMLINK, env=None, profiles=None):
    return InstallConfig(
        source_path=source,
        target_root=target,
        method=method,
        pipeline_env=env or {},
        default_lang="python",
        profiles=profiles or [],
        trust_source=True,  # fixture source; trust check covered in test_hardening.py
    )


FULL_ENV = {
    "CONTEXTCORE_ROOT": "/home/u/ContextCore",
    "SDK_ROOT": "/home/u/startd8-sdk",
    "PROJECT_ROOT": "/home/u/proj",
    "PROJECT_NAME": "proj",
}


# --------------------------------------------------------------------------- #
# embed_symlink (FR-5 / NFR-3)
# --------------------------------------------------------------------------- #


class TestEmbedSymlink:
    def test_action_count_and_shape(self, installer, fake_source, target):
        actions = installer.embed_symlink(_cfg(fake_source, target))
        # 1 mkdir + 17 symlinks + 2 resource copy-trees
        assert len(actions) == 1 + 17 + 2
        assert actions[0].type is ActionType.MKDIR
        symlinks = [a for a in actions if a.type is ActionType.SYMLINK]
        assert len(symlinks) == 17
        copies = [a for a in actions if a.type is ActionType.COPY_TREE]
        assert {a.target.name for a in copies} == set(EMBED_RESOURCE_DIRS)

    def test_symlink_sources_are_absolute(self, installer, fake_source, target):
        actions = installer.embed_symlink(_cfg(fake_source, target))
        for a in actions:
            if a.type is ActionType.SYMLINK:
                assert a.source.is_absolute()  # NFR-3: absolute source targets

    def test_includes_underscore_aliases(self, installer, fake_source, target):
        actions = installer.embed_symlink(_cfg(fake_source, target))
        linked = {a.target.name for a in actions if a.type is ActionType.SYMLINK}
        assert set(EMBED_ALIASES) <= linked

    def test_apply_creates_absolute_symlinks_and_copies_resources(
        self, installer, fake_source, target
    ):
        cfg = _cfg(fake_source, target)
        result = installer._run_actions(installer.embed_symlink(cfg), cfg)
        assert result.success
        embed = target / EMBED_DIR_NAME
        # A representative script + an underscore alias resolve to the absolute source file.
        assert os.readlink(embed / "run.sh") == str((fake_source / "run.sh").resolve())
        assert os.readlink(embed / "enrich_seed.py") == str(
            (fake_source / "enrich_seed.py").resolve()
        )
        # design/ + prompts/ are real copied dirs, not symlinks.
        for d in EMBED_RESOURCE_DIRS:
            assert (embed / d).is_dir() and not (embed / d).is_symlink()
            assert (embed / d / "sample.txt").read_text() == "x"


# --------------------------------------------------------------------------- #
# embed_copy (FR-6)
# --------------------------------------------------------------------------- #


class TestEmbedCopy:
    def test_builds_force_pipeline_env_subprocess(self, installer, fake_source, target):
        actions = installer.embed_copy(_cfg(fake_source, target, InstallMethod.COPY))
        assert len(actions) == 1
        a = actions[0]
        assert a.type is ActionType.RUN_SUBPROCESS
        assert a.argv == [
            str((fake_source / "install-cap-dev-pipe.sh").resolve()),
            "--force-pipeline-env",
            str(target),
        ]
        assert a.cwd == fake_source.resolve()

    def test_missing_installer_script_raises(self, installer, tmp_path, target):
        src = tmp_path / "incomplete"
        src.mkdir()
        with pytest.raises(ConfigurationError) as exc:
            installer.embed_copy(_cfg(src, target, InstallMethod.COPY))
        assert "install-cap-dev-pipe.sh" in str(exc.value)


# --------------------------------------------------------------------------- #
# reconcile (FR-6, R3-F5, R2-S6)
# --------------------------------------------------------------------------- #


class TestReconcileCopyInstall:
    def test_returns_single_reconcile_action(self, installer, fake_source, target):
        actions = installer.reconcile_copy_install(
            _cfg(fake_source, target, InstallMethod.COPY)
        )
        assert len(actions) == 1 and actions[0].type is ActionType.RECONCILE_COPY

    def _seed_rsync_output(self, target, env_text):
        """Simulate what install-cap-dev-pipe.sh leaves behind: pipeline.env + java profile."""
        embed = target / EMBED_DIR_NAME
        embed.mkdir(parents=True, exist_ok=True)
        (embed / "pipeline.env").write_text(env_text, encoding="utf-8")
        java = embed / "java"
        java.mkdir()
        (java / "java-plan.md").write_text("link", encoding="utf-8")
        return embed

    def test_merges_managed_keys_and_preserves_non_managed(
        self, installer, fake_source, target
    ):
        embed = self._seed_rsync_output(
            target,
            "# header\n"
            'CONTEXTCORE_ROOT="/wrong/cc"\n'
            'SDK_ROOT="/wrong/sdk"\n'
            'PROJECT_ROOT="/wrong/proj"\n'
            'PROJECT_NAME="wrong"\n'
            'CUSTOM_KEY="keepme"\n',  # non-managed -> must survive (R3-F5)
        )
        cfg = _cfg(fake_source, target, InstallMethod.COPY, env=FULL_ENV)
        installer._apply_action(
            Action(type=ActionType.RECONCILE_COPY, target=embed), cfg
        )

        text = (embed / "pipeline.env").read_text()
        assert 'CONTEXTCORE_ROOT="/home/u/ContextCore"' in text
        assert 'PROJECT_NAME="proj"' in text
        assert "/wrong/" not in text  # all four managed keys overwritten
        assert 'CUSTOM_KEY="keepme"' in text  # non-managed preserved
        assert "# header" in text  # comment preserved

    def test_pipeline_env_is_0600(self, installer, fake_source, target):
        embed = self._seed_rsync_output(target, 'PROJECT_NAME="x"\n')
        cfg = _cfg(fake_source, target, InstallMethod.COPY, env=FULL_ENV)
        installer._apply_action(
            Action(type=ActionType.RECONCILE_COPY, target=embed), cfg
        )
        assert (os.stat(embed / "pipeline.env").st_mode & 0o777) == 0o600  # NFR-6

    def test_removes_auto_linked_java_profile(self, installer, fake_source, target):
        embed = self._seed_rsync_output(target, 'PROJECT_NAME="x"\n')
        assert (embed / "java").is_dir()
        cfg = _cfg(fake_source, target, InstallMethod.COPY, env=FULL_ENV)
        installer._apply_action(
            Action(type=ActionType.RECONCILE_COPY, target=embed), cfg
        )
        assert not (
            embed / "java"
        ).exists()  # cleared; TUI profile step is authoritative

    def test_blocks_on_missing_managed_key(self, installer, fake_source, target):
        embed = self._seed_rsync_output(target, 'PROJECT_NAME="x"\n')
        partial = {
            "PROJECT_NAME": "proj"
        }  # CONTEXTCORE_ROOT/SDK_ROOT/PROJECT_ROOT missing
        cfg = _cfg(fake_source, target, InstallMethod.COPY, env=partial)
        with pytest.raises(ConfigurationError) as exc:
            installer._apply_action(
                Action(type=ActionType.RECONCILE_COPY, target=embed), cfg
            )
        msg = str(exc.value)
        assert "CONTEXTCORE_ROOT" in msg and "SDK_ROOT" in msg and "PROJECT_ROOT" in msg


# --------------------------------------------------------------------------- #
# managed-env helpers (shared with task #5)
# --------------------------------------------------------------------------- #


class TestManagedEnvHelpers:
    def test_require_managed_keys_blocks_on_blank(self, installer, fake_source, target):
        cfg = _cfg(fake_source, target, env={**FULL_ENV, "SDK_ROOT": "   "})
        with pytest.raises(ConfigurationError):
            installer._require_managed_keys(cfg)

    def test_require_managed_keys_strips_and_returns_all_four(
        self, installer, fake_source, target
    ):
        cfg = _cfg(fake_source, target, env={**FULL_ENV, "PROJECT_NAME": "  proj  "})
        out = installer._require_managed_keys(cfg)
        assert out["PROJECT_NAME"] == "proj"
        assert set(out) == set(FULL_ENV)

    def test_merge_appends_missing_keys_to_empty_text(self, installer):
        merged = installer._merge_managed_env("", FULL_ENV)
        for key, val in FULL_ENV.items():
            assert f'{key}="{val}"' in merged

    def test_merge_replaces_in_place_once_dropping_duplicates(self, installer):
        existing = 'PROJECT_NAME="old"\nPROJECT_NAME="dup"\nKEEP="z"\n'
        merged = installer._merge_managed_env(existing, FULL_ENV)
        assert merged.count('PROJECT_NAME="proj"') == 1
        assert "old" not in merged and "dup" not in merged
        assert 'KEEP="z"' in merged
