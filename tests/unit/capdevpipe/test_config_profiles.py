"""Tests for config (#5), profiles (#6), gitignore + verify (#7).

Covers FR-7 (detection + block-on-empty + 0600 + non-managed preservation), FR-8 (wrapper
template substitution + 0755), FR-9 (doc detection with exclusions; relative-symlink vs copy
profiles), FR-10 (idempotent gitignore), FR-11 (verify pass/fail, zero-profile skip, dangling
source).
"""

import os

import pytest

from startd8.capdevpipe_installer import (
    EMBED_DIR_NAME,
    InstallMethod,
    Manifest,
    ManifestState,
    ProfileSpec,
)
from startd8.exceptions import ConfigurationError

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# pipeline.env detection + write (FR-7)
# --------------------------------------------------------------------------- #


class TestDetectPipelineEnv:
    def test_derives_project_root_and_name_from_target(self, installer, cfg_factory):
        cfg = cfg_factory(env={})
        detected = installer.detect_pipeline_env(cfg)
        assert detected["PROJECT_ROOT"] == str(cfg.target_root.resolve())
        assert detected["PROJECT_NAME"] == cfg.target_root.name

    def test_env_var_wins_for_contextcore_root(
        self, installer, cfg_factory, monkeypatch
    ):
        monkeypatch.setenv("CONTEXTCORE_ROOT", "/from/env/cc")
        detected = installer.detect_pipeline_env(cfg_factory(env={}))
        assert detected["CONTEXTCORE_ROOT"] == "/from/env/cc"

    def test_walk_up_finds_sibling_checkout(
        self, installer, cfg_factory, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("CONTEXTCORE_ROOT", raising=False)
        monkeypatch.delenv("SDK_ROOT", raising=False)
        # Create an ancestor sibling: <tmp>/ContextCore next to the target's parent chain.
        cc = tmp_path / "ContextCore"
        cc.mkdir()
        proj = tmp_path / "proj"
        proj.mkdir()
        detected = installer.detect_pipeline_env(cfg_factory(target=proj, env={}))
        assert detected["CONTEXTCORE_ROOT"] == str(cc)

    def test_explicit_value_overrides_detection(self, installer, cfg_factory):
        cfg = cfg_factory(env={"CONTEXTCORE_ROOT": "/explicit/cc"})
        assert installer.detect_pipeline_env(cfg)["CONTEXTCORE_ROOT"] == "/explicit/cc"


class TestWritePipelineEnv:
    def test_blocks_on_missing_key(self, installer, cfg_factory):
        cfg = cfg_factory(env={"PROJECT_NAME": "p"})  # three keys missing
        with pytest.raises(ConfigurationError):
            installer.write_pipeline_env(cfg)

    def test_writes_all_four_keys_at_0600(self, installer, cfg_factory):
        cfg = cfg_factory()
        installer._run_actions(installer.write_pipeline_env(cfg), cfg)
        env_path = cfg.target_root / EMBED_DIR_NAME / "pipeline.env"
        text = env_path.read_text()
        for key in ("CONTEXTCORE_ROOT", "SDK_ROOT", "PROJECT_ROOT", "PROJECT_NAME"):
            assert f"{key}=" in text
        assert (os.stat(env_path).st_mode & 0o777) == 0o600  # NFR-6

    def test_preserves_non_managed_keys_on_rerun(self, installer, cfg_factory):
        cfg = cfg_factory()
        embed = cfg.target_root / EMBED_DIR_NAME
        embed.mkdir(parents=True)
        (embed / "pipeline.env").write_text(
            'CUSTOM="keep"\nPROJECT_NAME="old"\n', encoding="utf-8"
        )
        installer._run_actions(installer.write_pipeline_env(cfg), cfg)
        text = (embed / "pipeline.env").read_text()
        assert 'CUSTOM="keep"' in text  # R3-F5
        assert text.count("PROJECT_NAME=") == 1 and "old" not in text


# --------------------------------------------------------------------------- #
# wrapper (FR-8)
# --------------------------------------------------------------------------- #


class TestGenerateWrapper:
    def test_substitutes_placeholders_and_is_executable(self, installer, cfg_factory):
        cfg = cfg_factory(default_lang="go")
        installer._run_actions(installer.generate_wrapper(cfg), cfg)
        wrapper = cfg.target_root / EMBED_DIR_NAME / "proj-cap-dlv-pipe.sh"
        text = wrapper.read_text()
        assert "{{PROJECT_NAME}}" not in text and "{{DEFAULT_LANG}}" not in text
        assert "proj" in text and "go" in text
        assert os.stat(wrapper).st_mode & 0o111  # executable (FR-8)

    def test_missing_template_raises(self, installer, cfg_factory, tmp_path):
        bare = tmp_path / "bare"
        bare.mkdir()
        with pytest.raises(ConfigurationError):
            installer.generate_wrapper(cfg_factory(source=bare))


# --------------------------------------------------------------------------- #
# doc detection + profiles (FR-9)
# --------------------------------------------------------------------------- #


class TestDetectDocCandidates:
    def test_detects_root_and_docs_excluding_review_artifacts(self, installer, target):
        (target / "PLAN.md").write_text("p", encoding="utf-8")
        (target / "REQUIREMENTS.md").write_text("r", encoding="utf-8")
        docs = target / "docs"
        docs.mkdir()
        (docs / "feature-plan.md").write_text("p", encoding="utf-8")
        # Decoys that must be excluded:
        (target / "CRP_something_plan.md").write_text("x", encoding="utf-8")
        (docs / "convergent-review-prompt-plan.md").write_text("x", encoding="utf-8")
        arc = docs / "arc-review"
        arc.mkdir()
        (arc / "old-plan.md").write_text(
            "x", encoding="utf-8"
        )  # one-level glob won't reach anyway

        result = installer.detect_doc_candidates(target)
        plan_names = [p.name for p in result.plans]
        req_names = [p.name for p in result.reqs]
        assert "PLAN.md" in plan_names and "feature-plan.md" in plan_names
        assert "REQUIREMENTS.md" in req_names
        assert "CRP_something_plan.md" not in plan_names  # CRP_ excluded
        assert "convergent-review-prompt-plan.md" not in plan_names  # *review* excluded

    def test_deterministic_ordering_and_dedup(self, installer, target):
        (target / "b-plan.md").write_text("p", encoding="utf-8")
        (target / "a-plan.md").write_text("p", encoding="utf-8")
        result = installer.detect_doc_candidates(target)
        assert [p.name for p in result.plans] == ["a-plan.md", "b-plan.md"]


class TestCreateProfile:
    def test_symlink_profile_uses_relative_links(self, installer, cfg_factory, target):
        plan = target / "docs" / "py-plan.md"
        plan.parent.mkdir(parents=True)
        plan.write_text("p", encoding="utf-8")
        reqs = target / "REQUIREMENTS.md"
        reqs.write_text("r", encoding="utf-8")
        cfg = cfg_factory()
        profile = ProfileSpec(lang="python", plan=plan, reqs=reqs)
        installer._run_actions(installer.create_profile(cfg, profile), cfg)

        pdir = target / EMBED_DIR_NAME / "python"
        link = pdir / "python-plan.md"
        assert link.is_symlink()
        assert not os.path.isabs(os.readlink(link))  # NFR-3: relative
        assert link.resolve() == plan.resolve()  # resolves correctly
        assert (pdir / "python-requirements.md").resolve() == reqs.resolve()

    def test_copy_profile_when_symlinks_unavailable(
        self, installer, cfg_factory, target, monkeypatch
    ):
        monkeypatch.setattr(
            type(installer), "_symlinks_available", staticmethod(lambda: False)
        )
        plan = target / "PLAN.md"
        plan.write_text("content", encoding="utf-8")
        cfg = cfg_factory()
        installer._run_actions(
            installer.create_profile(cfg, ProfileSpec(lang="go", plan=plan)), cfg
        )
        link = target / EMBED_DIR_NAME / "go" / "go-plan.md"
        assert (
            link.is_file() and not link.is_symlink()
        )  # copied (Windows fallback, D-9)
        assert link.read_text() == "content"


# --------------------------------------------------------------------------- #
# gitignore (FR-10) + verify (FR-11)
# --------------------------------------------------------------------------- #


class TestUpdateGitignore:
    def test_idempotent_ensure(self, installer, cfg_factory, target):
        cfg = cfg_factory()
        installer._run_actions(installer.update_gitignore(cfg), cfg)
        gi = target / ".gitignore"
        assert ".cap-dev-pipe/pipeline-output/" in gi.read_text()
        # Second run does not duplicate the line.
        installer._run_actions(installer.update_gitignore(cfg), cfg)
        assert gi.read_text().count(".cap-dev-pipe/pipeline-output/") == 1


class TestParseListedLangs:
    """The --list-langs parser must read real cap-dev-pipe output, not substrings."""

    REAL_OUTPUT = (
        "Available language profiles:\n"
        "\n"
        "  python/\n"
        "    plan: python-plan.md\n"
        "    reqs: python-requirements.md\n"
        "\n"
        "  django/\n"
        "    plan: django-plan.md\n"
        "    reqs: django-requirements.md\n"
        "\n"
    )

    def test_extracts_only_profile_lines(self, installer):
        langs = installer._parse_listed_langs(self.REAL_OUTPUT)
        assert langs == ["python", "django"]

    def test_no_profiles_help_text_yields_empty(self, installer):
        stdout = (
            "No language profiles found in /tmp/.cap-dev-pipe/\n"
            "\n"
            "Create a subdirectory with a *plan*.md and *requirements*.md file.\n"
        )
        assert installer._parse_listed_langs(stdout) == []

    def test_substring_does_not_count_as_present(self, installer, cfg_factory, target):
        """'go' must not verify-pass against a 'django/' profile (substring trap)."""
        plan = target / "PLAN.md"
        plan.write_text("p", encoding="utf-8")
        cfg = cfg_factory(profiles=[ProfileSpec(lang="django", plan=plan, reqs=None)])
        TestVerify()._install_symlink(installer, cfg)
        # Manifest records 'django'; verify must list exactly that, not 'go'.
        vr = installer.verify(target)
        assert "django" in vr.listed_langs
        assert "go" not in vr.listed_langs


class TestVerify:
    def _install_symlink(self, installer, cfg):
        result = installer.execute(cfg)
        assert result.success, result.error
        return result

    def test_pass_with_profiles_present(self, installer, cfg_factory, target):
        plan = target / "PLAN.md"
        plan.write_text("p", encoding="utf-8")
        reqs = target / "REQUIREMENTS.md"
        reqs.write_text("r", encoding="utf-8")
        cfg = cfg_factory(profiles=[ProfileSpec(lang="python", plan=plan, reqs=reqs)])
        self._install_symlink(installer, cfg)
        vr = installer.verify(target)
        assert vr.passed, vr.message
        assert "python" in vr.listed_langs
        assert vr.single_source_ok

    def test_zero_profile_skip_is_valid_pass(self, installer, cfg_factory, target):
        cfg = cfg_factory(profiles=[])  # R2-F7
        self._install_symlink(installer, cfg)
        vr = installer.verify(target)
        assert vr.passed and vr.expected_langs == []

    def test_nothing_installed_fails(self, installer, target):
        # Nothing installed → no manifest → honest "cannot verify" (profile-aware; the message
        # no longer names run.sh, which is only one profile's script — finding #2).
        vr = installer.verify(target)
        assert not vr.passed
        assert "manifest" in vr.message.lower() or "install" in vr.message.lower()

    def test_dangling_source_reported(self, installer, cfg_factory, target):
        cfg = cfg_factory()
        installer.execute(cfg)
        # Simulate the source moving: repoint run.sh symlink to a non-existent target.
        run_sh = target / EMBED_DIR_NAME / "run.sh"
        run_sh.unlink()
        os.symlink(cfg.source_path / "GONE-run.sh", run_sh)
        vr = installer.verify(target)
        assert not vr.passed and vr.dangling_source is not None
        assert "upgrade" in vr.message


# --------------------------------------------------------------------------- #
# detect_existing (FR-12)
# --------------------------------------------------------------------------- #


class TestDetectExisting:
    def test_absent(self, installer, target):
        assert not installer.detect_existing(target).exists

    def test_present_reads_manifest(self, installer, cfg_factory, target):
        cfg = cfg_factory()
        installer.execute(cfg)
        state = installer.detect_existing(target)
        assert state.exists and state.manifest is not None
        assert state.manifest.method is InstallMethod.SYMLINK

    def test_detects_pending_marker(self, installer, target):
        embed = target / EMBED_DIR_NAME
        embed.mkdir()
        installer.write_manifest(
            target,
            Manifest(
                method=InstallMethod.SYMLINK,
                source_path=target,
                state=ManifestState.PENDING,
            ),
        )
        assert installer.detect_existing(target).pending
