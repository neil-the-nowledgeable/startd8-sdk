"""Essential-core integration tests (task #10).

Full ``execute`` end-to-end for both methods, idempotent re-run, the four re-run modes
(FR-12), Windows copy-fallback (D-9), the standalone TUI handler (S8), and the NFR-7
"installer usable with no TUI imported" invariant.
"""

import os
import sys

import pytest

from startd8.capdevpipe_embed_manifest import (
    DEFAULT_EMBED_PROFILE,
    resolve_embed_inventory,
)
from startd8.capdevpipe_installer import (
    EMBED_DIR_NAME,
    InstallMethod,
    ProfileSpec,
    ReRunMode,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# full install (symlink + copy)
# --------------------------------------------------------------------------- #


class TestFullInstallSymlink:
    def test_end_to_end_then_verify(self, installer, cfg_factory, target):
        plan = target / "PLAN.md"
        plan.write_text("p", encoding="utf-8")
        cfg = cfg_factory(profiles=[ProfileSpec(lang="python", plan=plan)])
        result = installer.execute(cfg)
        assert result.success, result.error
        embed = target / EMBED_DIR_NAME
        inv = resolve_embed_inventory(cfg.source_path, DEFAULT_EMBED_PROFILE)
        for name in (*inv.scripts, *inv.python_aliases):
            assert (embed / name).is_symlink()
        assert (embed / "pipeline").is_symlink()
        assert (embed / "pipeline.env").is_file()
        assert (embed / "proj-cap-dlv-pipe.sh").is_file()
        assert (embed / "python" / "python-plan.md").is_symlink()
        assert ".cap-dev-pipe/pipeline-output/" in (target / ".gitignore").read_text()
        vr = installer.verify(target)
        assert vr.passed and "python" in vr.listed_langs

    def test_idempotent_full_rerun(self, installer, cfg_factory):
        cfg = cfg_factory()
        installer.execute(cfg)
        second = installer.execute(cfg)  # plan_actions all satisfied
        assert second.success and second.actions_applied == []


class TestFullInstallCopy:
    def test_copy_path_end_to_end_and_reconcile(self, installer, cfg_factory, target):
        cfg = cfg_factory(method=InstallMethod.COPY)
        result = installer.execute(cfg)
        assert result.success, result.error
        embed = target / EMBED_DIR_NAME
        assert (embed / "run.sh").is_file() and not (
            embed / "run.sh"
        ).is_symlink()  # copied
        env_text = (embed / "pipeline.env").read_text()
        assert "/wrong" not in env_text  # reconcile overwrote the rsync defaults
        assert 'PROJECT_NAME="proj"' in env_text
        assert installer.read_manifest(target).method is InstallMethod.COPY


# --------------------------------------------------------------------------- #
# re-run modes (FR-12)
# --------------------------------------------------------------------------- #


class TestReRunModes:
    def test_repair_recreates_missing_symlink(self, installer, cfg_factory, target):
        cfg = cfg_factory()
        installer.execute(cfg)
        (target / EMBED_DIR_NAME / "run.sh").unlink()  # simulate breakage
        installer.apply_mode(target, ReRunMode.REPAIR, cfg)
        assert (target / EMBED_DIR_NAME / "run.sh").is_symlink()

    def test_upgrade_prunes_orphaned_symlink(self, installer, cfg_factory, target):
        cfg = cfg_factory()
        installer.execute(cfg)
        # An orphan: a top-level symlink whose name is not in the current embed set.
        orphan = target / EMBED_DIR_NAME / "run-removed-upstream.sh"
        os.symlink(cfg.source_path / "run.sh", orphan)
        installer.apply_mode(target, ReRunMode.UPGRADE, cfg)
        assert not orphan.exists()  # R2-F6 shrinking-source
        assert (target / EMBED_DIR_NAME / "run.sh").is_symlink()  # real ones kept

    def test_replace_pipeline_env_preserves_non_managed(
        self, installer, cfg_factory, target
    ):
        cfg = cfg_factory()
        installer.execute(cfg)
        env_path = target / EMBED_DIR_NAME / "pipeline.env"
        env_path.write_text(env_path.read_text() + 'EXTRA="keep"\n', encoding="utf-8")
        installer.apply_mode(target, ReRunMode.REPLACE_PIPELINE_ENV, cfg)
        assert 'EXTRA="keep"' in env_path.read_text()  # R3-F5

    def test_reconfigure_leaves_scripts_rewrites_config(
        self, installer, cfg_factory, target
    ):
        cfg = cfg_factory()
        installer.execute(cfg)
        run_link = target / EMBED_DIR_NAME / "run.sh"
        before = os.readlink(run_link)
        installer.apply_mode(target, ReRunMode.RECONFIGURE, cfg)
        assert os.readlink(run_link) == before  # scripts untouched
        assert (target / EMBED_DIR_NAME / "pipeline.env").is_file()

    def test_doctor_on_healthy_install_passes(self, installer, cfg_factory, target):
        cfg = cfg_factory()
        installer.execute(cfg)
        # On a healthy symlink install, doctor delegates to verify and passes (FR-17).
        assert installer.doctor(target).passed
        installer.apply_mode(target, ReRunMode.DOCTOR, cfg)  # no raise


# --------------------------------------------------------------------------- #
# Windows copy-fallback (D-9 / FR-4)
# --------------------------------------------------------------------------- #


class TestWindowsFallback:
    def test_symlink_request_forced_to_copy_when_unavailable(
        self, installer, cfg_factory, target, monkeypatch
    ):
        monkeypatch.setattr(
            type(installer), "_symlinks_available", staticmethod(lambda: False)
        )
        cfg = cfg_factory(method=InstallMethod.SYMLINK)  # requested symlink...
        result = installer.execute(cfg)
        assert result.success, result.error
        # ...but scripts were copied (no symlinks) and the manifest records copy.
        assert not (target / EMBED_DIR_NAME / "run.sh").is_symlink()
        assert installer.read_manifest(target).method is InstallMethod.COPY


# --------------------------------------------------------------------------- #
# standalone TUI handler (S8) + NFR-7
# --------------------------------------------------------------------------- #


class TestStandaloneHandler:
    def test_handler_runs_headless_from_config_dict(
        self, full_source, target, monkeypatch, tmp_path
    ):
        # Point ConfigManager at a temp dir so pref persistence (FR-15) doesn't touch ~/.startd8.
        import startd8.config as config_mod
        from startd8.config import ConfigManager
        from startd8.tui_improved import ImprovedTUI
        from rich.console import Console

        monkeypatch.setattr(
            config_mod, "_config_manager", ConfigManager(tmp_path / "cfg")
        )

        # Construct the TUI without its heavy __init__ — the handler only needs .console.
        tui = object.__new__(ImprovedTUI)
        tui.console = Console()

        result = tui.install_capdevpipe_flow(
            {
                "source_path": str(full_source),
                "target_root": str(target),
                "method": "symlink",
                "pipeline_env": {
                    "CONTEXTCORE_ROOT": "/cc",
                    "SDK_ROOT": "/sdk",
                },  # PROJECT_ROOT/NAME auto-detected
            }
        )
        assert result is not None and result.success  # S8: callable standalone
        assert (target / EMBED_DIR_NAME / "run.sh").is_symlink()
        # FR-15: prefs were persisted.
        assert (
            config_mod._config_manager.get_preference("capdevpipe.install_method")
            == "symlink"
        )

    def test_handler_headless_honors_rerun_mode(
        self, full_source, target, monkeypatch, tmp_path
    ):
        """Headless re-run with an explicit rerun_mode applies that mode (not a dark field)."""
        import startd8.config as config_mod
        from startd8.config import ConfigManager
        from startd8.tui_improved import ImprovedTUI
        from rich.console import Console

        monkeypatch.setattr(
            config_mod, "_config_manager", ConfigManager(tmp_path / "cfg")
        )
        tui = object.__new__(ImprovedTUI)
        tui.console = Console()
        base_config = {
            "source_path": str(full_source),
            "target_root": str(target),
            "method": "symlink",
            "pipeline_env": {"CONTEXTCORE_ROOT": "/cc", "SDK_ROOT": "/sdk"},
        }

        # First install (fresh) returns an ExecuteResult.
        first = tui.install_capdevpipe_flow(base_config)
        assert first is not None and first.success

        # Break an embedded symlink, then re-run headlessly in 'repair' mode.
        run_sh = target / EMBED_DIR_NAME / "run.sh"
        run_sh.unlink()
        assert not run_sh.exists()
        vr = tui.install_capdevpipe_flow({**base_config, "rerun_mode": "repair"})
        # Apply-mode path returns a VerifyResult (per the documented contract) and repair
        # recreated the missing symlink.
        assert vr is not None and vr.passed, getattr(vr, "message", vr)
        assert run_sh.is_symlink()

    def test_handler_headless_doctor_detects_moved_source(
        self, full_source, target, monkeypatch, tmp_path
    ):
        """Headless rerun_mode='doctor' surfaces the dangling-source diagnostic (FR-17/R4-F6)."""
        import shutil

        import startd8.config as config_mod
        from startd8.config import ConfigManager
        from startd8.tui_improved import ImprovedTUI
        from rich.console import Console

        monkeypatch.setattr(
            config_mod, "_config_manager", ConfigManager(tmp_path / "cfg")
        )
        tui = object.__new__(ImprovedTUI)
        tui.console = Console()
        base_config = {
            "source_path": str(full_source),
            "target_root": str(target),
            "method": "symlink",
            "pipeline_env": {"CONTEXTCORE_ROOT": "/cc", "SDK_ROOT": "/sdk"},
        }
        assert tui.install_capdevpipe_flow(base_config).success

        # Move the canonical source. doctor() compares against the manifest's recorded
        # source_path (the original, now-missing location); the flow still needs *a* valid
        # source to build its config, so point it at the relocated checkout — exactly the
        # "my source moved, where do I re-point?" workflow doctor exists for.
        moved = tmp_path / "relocated-cap-dev-pipe"
        shutil.move(str(full_source), str(moved))
        vr = tui.install_capdevpipe_flow(
            {**base_config, "source_path": str(moved), "rerun_mode": "doctor"}
        )
        assert vr is not None and not vr.passed
        assert vr.dangling_source is not None
        assert "upgrade" in vr.message

    def test_installer_imports_without_tui_or_questionary(self):
        # NFR-7, robustly: in a *fresh* interpreter, importing/using the installer must not
        # pull in the TUI layer. (A sibling test that imports the TUI would pollute this
        # process's sys.modules, so isolate in a subprocess.)
        import subprocess

        code = (
            "import sys; import startd8.capdevpipe_installer as m;"
            "i = m.CapDevPipeInstaller();"
            "assert 'questionary' not in sys.modules, 'questionary leaked';"
            "assert 'startd8.tui_improved' not in sys.modules, 'tui_improved leaked';"
            "print('ok')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        assert proc.returncode == 0, proc.stderr
        assert "ok" in proc.stdout

    def test_installer_runs_a_full_install(self, full_source, target):
        from startd8.capdevpipe_installer import CapDevPipeInstaller, InstallConfig

        cfg = InstallConfig(
            source_path=full_source,
            target_root=target,
            method=InstallMethod.SYMLINK,
            pipeline_env={
                "CONTEXTCORE_ROOT": "/cc",
                "SDK_ROOT": "/sdk",
                "PROJECT_ROOT": str(target),
                "PROJECT_NAME": target.name,
            },
        )
        assert CapDevPipeInstaller().execute(cfg).success


# --------------------------------------------------------------------------- #
# profile-aware verify (cap-dev-pipe issue #2)
# --------------------------------------------------------------------------- #

# Minimal run.sh stand-in: lists local <lang>/ profile dirs for --list-langs (full path).
_FAKE_RUN_SH = """#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ " $* " == *" --list-langs "* ]]; then
    echo "Available language profiles:"
    for d in "$SCRIPT_DIR"/*/; do
        name="$(basename "$d")"
        ls "$d"/*plan*.md >/dev/null 2>&1 && echo "  $name/"
    done
    exit 0
fi
exit 0
"""


def _mk_exec(path, text):
    import stat as _stat

    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)


def _build_embed(target, *, profile, with_run_sh, langs=("python",)):
    """Construct a minimal embed tree + install manifest for verify() tests."""
    import json

    from startd8.capdevpipe_installer import (
        MANIFEST_FILENAME,
        InstallMethod,
        Manifest,
    )

    embed = target / EMBED_DIR_NAME
    (embed / "design").mkdir(parents=True)
    (embed / "prompts").mkdir()
    for lang in langs:
        (embed / lang).mkdir()
        (embed / lang / f"{lang}-plan.md").write_text("# plan\n", encoding="utf-8")
        (embed / lang / f"{lang}-requirements.md").write_text(
            "# reqs\n", encoding="utf-8"
        )
    _mk_exec(embed / "run-cap-delivery.sh", "#!/usr/bin/env bash\nexit 0\n")
    if with_run_sh:
        _mk_exec(embed / "run.sh", _FAKE_RUN_SH)
    managed = ["design", "prompts", "run-cap-delivery.sh", *langs]
    if profile == "full":
        # The full profile DECLARES run.sh in its inventory regardless of whether the file is
        # on disk — so a full install with a missing run.sh is a real breakage (behavioral
        # path), not a valid run.sh-less profile. `with_run_sh` controls only the file.
        managed.append("run.sh")
    manifest = Manifest(
        method=InstallMethod.SYMLINK,
        source_path=target,
        profiles=list(langs),
        embed_profile=profile,
        managed_paths=managed,
    )
    (embed / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.to_dict()), encoding="utf-8"
    )
    return embed


def _rewrite_manifest(embed, **changes):
    """Mutate the embed's install-manifest.json in place (test helper)."""
    import json

    from startd8.capdevpipe_installer import MANIFEST_FILENAME

    mpath = embed / MANIFEST_FILENAME
    data = json.loads(mpath.read_text())
    data.update(changes)
    mpath.write_text(json.dumps(data))
    return mpath


class TestVerifyProfileAware:
    """verify() is profile-aware (finding #2): a profile with no run.sh verifies structurally.

    OQ-3 resolved: the structural check mirrors canonical ``verify_embed`` (per-``managed_paths``,
    subprocess-free) rather than shelling to a run.sh/wrapper — so it does not depend on the
    (separately-broken) orchestrator wrapper (cap-dev-pipe#2) or the source checkout.
    """

    def test_orchestrator_verifies_structurally_without_run_sh(self, installer, target):
        _build_embed(target, profile="orchestrator", with_run_sh=False)
        vr = installer.verify(target)
        assert vr.passed, vr.message
        assert "python" in vr.listed_langs

    def test_full_still_requires_run_sh(self, installer, target):
        # A full install missing run.sh is a real breakage — must NOT be masked.
        _build_embed(target, profile="full", with_run_sh=False)
        vr = installer.verify(target)
        assert not vr.passed
        assert "run.sh not found" in vr.message

    def test_full_verifies_through_run_sh_when_present(self, installer, target):
        _build_embed(target, profile="full", with_run_sh=True)
        vr = installer.verify(target)
        assert vr.passed, vr.message
        assert "python" in vr.listed_langs

    def test_orchestrator_missing_managed_path_fails_actionably(
        self, installer, target
    ):
        # FR-1: a declared managed path gone on disk fails, naming the path.
        embed = _build_embed(target, profile="orchestrator", with_run_sh=False)
        (embed / "run-cap-delivery.sh").unlink()
        vr = installer.verify(target)
        assert not vr.passed
        assert "run-cap-delivery.sh" in vr.message

    def test_minimal_without_prompts_still_passes(self, installer, target):
        # FR-2: the `minimal` profile ships design/ but NOT prompts/ — must not falsely fail.
        import shutil

        embed = _build_embed(target, profile="minimal", with_run_sh=False)
        _rewrite_manifest(
            embed,
            embed_profile="minimal",
            managed_paths=["design", "run-cap-delivery.sh", "python"],
        )
        shutil.rmtree(embed / "prompts")
        vr = installer.verify(target)
        assert vr.passed, vr.message

    def test_manifest_absent_degrades_not_assumes_full(self, installer, target):
        # FR-3: no manifest → honest "cannot verify", never a false run.sh requirement.
        from startd8.capdevpipe_installer import MANIFEST_FILENAME

        embed = _build_embed(target, profile="orchestrator", with_run_sh=False)
        (embed / MANIFEST_FILENAME).unlink()
        vr = installer.verify(target)
        assert not vr.passed
        assert "manifest" in vr.message.lower()
        assert "run.sh not found" not in vr.message

    def test_orchestrator_reports_missing_expected_profile(self, installer, target):
        embed = _build_embed(target, profile="orchestrator", with_run_sh=False)
        _rewrite_manifest(embed, profiles=["python", "rust"])  # rust not on disk
        vr = installer.verify(target)
        assert not vr.passed
        assert "rust" in vr.message

    def test_doctor_orchestrator_passes(self, installer, target):
        # doctor() falls through to the profile-aware verify() for a healthy orchestrator.
        _build_embed(target, profile="orchestrator", with_run_sh=False)
        vr = installer.doctor(target)
        assert vr.passed, vr.message
