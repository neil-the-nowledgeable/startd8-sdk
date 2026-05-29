"""Hardening test suite (P2, task #17).

Covers the defensive layer: manifest schema versioning + forward-compat (#11 / R3-S5),
TOCTOU symlink confinement (#12 / R2-S5), source-execution trust (#13 / R3-S1), the
pending/complete crash marker + stale-pending repair (#14 / R2-S7), copy-path manifest
re-scan (#15 / R3-S2), the doctor mode + source-relocation detection (#16 / FR-17), and
diagnosability logging (NFR-8).
"""

import json
import logging

import pytest

from startd8.capdevpipe_installer import (
    DEFAULT_SOURCE,
    EMBED_DIR_NAME,
    MANIFEST_FILENAME,
    MANIFEST_VERSION,
    ActionType,
    InstallMethod,
    Manifest,
    ManifestState,
    ReRunMode,
)
from startd8.exceptions import ConfigurationError, FileOperationError

pytestmark = pytest.mark.unit


def _manifest_path(target):
    return target / EMBED_DIR_NAME / MANIFEST_FILENAME


# --------------------------------------------------------------------------- #
# #11 manifest schema_version + forward-compat (R3-S5)
# --------------------------------------------------------------------------- #


class TestManifestVersioning:
    def test_written_manifest_carries_version(self, installer, cfg_factory, target):
        installer.execute(cfg_factory())
        data = json.loads(_manifest_path(target).read_text())
        assert data["manifest_version"] == MANIFEST_VERSION

    def test_newer_version_degrades_to_none(self, installer, cfg_factory, target):
        installer.execute(cfg_factory())
        path = _manifest_path(target)
        data = json.loads(path.read_text())
        data["manifest_version"] = (
            MANIFEST_VERSION + 99
        )  # written by a future installer
        path.write_text(json.dumps(data), encoding="utf-8")
        # Graceful fallback: no crash, returns None so callers re-derive from disk.
        assert installer.read_manifest(target) is None

    def test_detect_existing_survives_unknown_version(
        self, installer, cfg_factory, target
    ):
        installer.execute(cfg_factory())
        path = _manifest_path(target)
        data = json.loads(path.read_text())
        data["manifest_version"] = 999
        path.write_text(json.dumps(data), encoding="utf-8")
        state = installer.detect_existing(target)
        assert state.exists and state.manifest is None  # re-derived, not crashed


# --------------------------------------------------------------------------- #
# #12 TOCTOU symlink confinement (R2-S5)
# --------------------------------------------------------------------------- #


class TestTOCTOUConfinement:
    def test_preexisting_embed_symlink_escape_refused(
        self, installer, cfg_factory, target, tmp_path
    ):
        outside = tmp_path / "evil"
        outside.mkdir()
        (target / EMBED_DIR_NAME).symlink_to(outside)  # planted escape
        with pytest.raises(FileOperationError) as exc:
            installer.execute(cfg_factory())
        assert "symlink" in str(exc.value).lower()
        # Nothing was written into the outside dir.
        assert list(outside.iterdir()) == []

    def test_preflight_guard_directly(self, installer, cfg_factory, target, tmp_path):
        outside = tmp_path / "evil2"
        outside.mkdir()
        (target / EMBED_DIR_NAME).symlink_to(outside)
        with pytest.raises(FileOperationError):
            installer._assert_embed_not_escaping(cfg_factory())


# --------------------------------------------------------------------------- #
# #13 source-execution trust (R3-S1)
# --------------------------------------------------------------------------- #


class TestSourceTrust:
    def test_untrusted_source_refused_for_copy(self, installer, full_source, target):
        from startd8.capdevpipe_installer import InstallConfig

        cfg = InstallConfig(
            source_path=full_source,  # a fixture dir, not the default checkout
            target_root=target,
            method=InstallMethod.COPY,
            pipeline_env=dict.fromkeys(
                ("CONTEXTCORE_ROOT", "SDK_ROOT", "PROJECT_ROOT", "PROJECT_NAME"), "x"
            ),
            trust_source=False,
        )
        with pytest.raises(ConfigurationError) as exc:
            installer.embed_copy(cfg)
        assert "untrusted" in str(exc.value).lower()

    def test_trust_source_opt_in_allows_copy(self, installer, cfg_factory):
        # cfg_factory sets trust_source=True; embed_copy builds the action.
        actions = installer.embed_copy(cfg_factory(method=InstallMethod.COPY))
        assert actions and actions[0].type is ActionType.RUN_SUBPROCESS

    def test_default_source_is_trusted(self, installer):
        assert installer._is_trusted_source(DEFAULT_SOURCE)

    def test_symlink_method_unaffected_by_trust(self, installer, full_source, target):
        from startd8.capdevpipe_installer import InstallConfig

        cfg = InstallConfig(
            source_path=full_source,
            target_root=target,
            method=InstallMethod.SYMLINK,
            pipeline_env=dict.fromkeys(
                ("CONTEXTCORE_ROOT", "SDK_ROOT", "PROJECT_ROOT", "PROJECT_NAME"), "x"
            ),
            trust_source=False,  # symlink path never executes the source script
        )
        assert installer.execute(cfg).success


# --------------------------------------------------------------------------- #
# #14 crash marker + stale-pending repair (R2-S7)
# --------------------------------------------------------------------------- #


class TestCrashMarker:
    def test_successful_install_marks_complete(self, installer, cfg_factory, target):
        installer.execute(cfg_factory())
        data = json.loads(_manifest_path(target).read_text())
        assert data["state"] == ManifestState.COMPLETE.value

    def test_fresh_execute_refuses_to_layer_on_pending(
        self, installer, cfg_factory, target
    ):
        # Simulate a crashed run: a pending manifest left behind.
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
        result = installer.execute(cfg_factory())
        assert not result.success and result.repairable
        assert "repair" in (result.error or "").lower()

    def test_repair_completes_a_pending_install(self, installer, cfg_factory, target):
        cfg = cfg_factory()
        # Leave a pending marker, then repair (bypasses the execute guard intentionally).
        embed = target / EMBED_DIR_NAME
        embed.mkdir()
        installer.write_manifest(
            target,
            Manifest(
                method=InstallMethod.SYMLINK,
                source_path=cfg.source_path,
                state=ManifestState.PENDING,
            ),
        )
        installer.apply_mode(target, ReRunMode.REPAIR, cfg)
        data = json.loads(_manifest_path(target).read_text())
        assert data["state"] == ManifestState.COMPLETE.value
        assert (embed / "run.sh").is_symlink()

    def test_symlink_failure_rolls_back_pending_marker(
        self, installer, cfg_factory, target, monkeypatch
    ):
        cfg = cfg_factory()
        real_apply = installer._apply_action

        def failing(action, c):
            if action.type is ActionType.WRITE_FILE:
                raise RuntimeError("boom")
            return real_apply(action, c)

        monkeypatch.setattr(installer, "_apply_action", failing)
        result = installer.execute(cfg)
        assert not result.success and result.rolled_back
        # Fresh-install rollback removed the embed dir and its pending manifest.
        assert not (target / EMBED_DIR_NAME).exists()


# --------------------------------------------------------------------------- #
# #15 copy-path manifest re-scan (R3-S2)
# --------------------------------------------------------------------------- #


class TestCopyManifestSubtree:
    def test_copy_manifest_records_embed_subtree(self, installer, cfg_factory, target):
        installer.execute(cfg_factory(method=InstallMethod.COPY))
        manifest = installer.read_manifest(target)
        embed = target / EMBED_DIR_NAME
        assert manifest.method is InstallMethod.COPY
        # The rsync-produced tree is captured via the embed-dir subtree entry.
        assert embed in manifest.created_paths

    def test_symlink_manifest_lists_precise_paths_not_subtree(
        self, installer, cfg_factory, target
    ):
        installer.execute(cfg_factory())
        manifest = installer.read_manifest(target)
        embed = target / EMBED_DIR_NAME
        # Symlink installs enumerate precise owned paths; the run.sh symlink is one of them.
        assert (embed / "run.sh") in manifest.created_paths


# --------------------------------------------------------------------------- #
# #16 doctor mode + source-relocation (FR-17 / R2-S4)
# --------------------------------------------------------------------------- #


class TestDoctorSourceRelocation:
    def test_detects_moved_source_via_manifest(
        self, installer, full_source, target, tmp_path
    ):
        cfg = installer_cfg = None  # noqa
        from startd8.capdevpipe_installer import InstallConfig

        cfg = InstallConfig(
            source_path=full_source,
            target_root=target,
            method=InstallMethod.SYMLINK,
            pipeline_env=dict.fromkeys(
                ("CONTEXTCORE_ROOT", "SDK_ROOT", "PROJECT_ROOT", "PROJECT_NAME"), "x"
            ),
            trust_source=True,
        )
        installer.execute(cfg)
        # Move the canonical source away.
        moved = tmp_path / "cap-dev-pipe-moved"
        full_source.rename(moved)
        result = installer.doctor(target)
        assert not result.passed
        assert result.dangling_source is not None
        assert "upgrade" in result.message and str(full_source) in result.message

    def test_apply_mode_doctor_logs_and_returns(
        self, installer, cfg_factory, target, full_source, tmp_path
    ):
        cfg = cfg_factory()
        installer.execute(cfg)
        full_source.rename(tmp_path / "gone")
        installer.apply_mode(target, ReRunMode.DOCTOR, cfg)  # no raise


# --------------------------------------------------------------------------- #
# NFR-8 diagnosability
# --------------------------------------------------------------------------- #


class TestDiagnosability:
    def test_failed_action_is_logged(
        self, installer, cfg_factory, target, monkeypatch, caplog
    ):
        cfg = cfg_factory()
        real_apply = installer._apply_action

        def failing(action, c):
            if action.type is ActionType.WRITE_FILE:
                raise RuntimeError("disk full")
            return real_apply(action, c)

        monkeypatch.setattr(installer, "_apply_action", failing)
        with caplog.at_level(logging.ERROR, logger="startd8.capdevpipe_installer"):
            installer.execute(cfg)
        assert any(
            "execute failed" in r.message and "disk full" in r.message
            for r in caplog.records
        )

    def test_subprocess_invocation_is_logged(
        self, installer, cfg_factory, target, caplog
    ):
        with caplog.at_level(logging.INFO, logger="startd8.capdevpipe_installer"):
            installer.execute(cfg_factory(method=InstallMethod.COPY))
        assert any("subprocess" in r.message for r in caplog.records)
