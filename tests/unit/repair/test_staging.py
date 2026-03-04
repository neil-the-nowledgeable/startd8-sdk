"""Tests for startd8.repair.staging."""

import os
import time
from pathlib import Path

import pytest

from startd8.repair.models import StagingError
from startd8.repair.staging import (
    StagingContext,
    cleanup_expired_staging,
    create_staging,
)


class TestCreateStaging:
    def test_creates_unique_directory(self, tmp_path):
        files = {tmp_path / "a.py": "x = 1"}
        (tmp_path / "a.py").write_text("x = 1")

        staging_root = tmp_path / "staging"
        with create_staging(
            files, staging_root, "my_feature", 1, project_root=tmp_path,
        ) as ctx:
            assert ctx.staging_dir.exists()
            assert "my_feature" in str(ctx.staging_dir)
            assert len(ctx.file_paths) == 1

    def test_copies_file_content(self, tmp_path):
        files = {tmp_path / "a.py": "hello = 'world'"}
        (tmp_path / "a.py").write_text("hello = 'world'")

        staging_root = tmp_path / "staging"
        with create_staging(
            files, staging_root, "feat", 1, project_root=tmp_path,
        ) as ctx:
            staged_path = ctx.file_paths[tmp_path / "a.py"]
            assert staged_path.read_text() == "hello = 'world'"

    def test_staging_dir_mode(self, tmp_path):
        files = {tmp_path / "a.py": "x = 1"}
        (tmp_path / "a.py").write_text("x = 1")

        staging_root = tmp_path / "staging"
        with create_staging(
            files, staging_root, "feat", 1, project_root=tmp_path,
        ) as ctx:
            mode = ctx.staging_dir.stat().st_mode & 0o777
            assert mode == 0o700

    def test_cleans_up_on_success(self, tmp_path):
        files = {tmp_path / "a.py": "x = 1"}
        (tmp_path / "a.py").write_text("x = 1")

        staging_root = tmp_path / "staging"
        staging_dir = None
        with create_staging(
            files, staging_root, "feat", 1, project_root=tmp_path,
        ) as ctx:
            staging_dir = ctx.staging_dir
            assert staging_dir.exists()

        # After context exits successfully, staging dir should be cleaned up
        assert not staging_dir.exists()

    def test_retains_on_failure(self, tmp_path):
        files = {tmp_path / "a.py": "x = 1"}
        (tmp_path / "a.py").write_text("x = 1")

        staging_root = tmp_path / "staging"
        staging_dir = None
        try:
            with create_staging(
                files, staging_root, "feat", 1, project_root=tmp_path,
            ) as ctx:
                staging_dir = ctx.staging_dir
                raise RuntimeError("simulated failure")
        except RuntimeError:
            pass

        # On failure, staging dir is retained for debugging
        assert staging_dir.exists()

    def test_rejects_symlink_input(self, tmp_path):
        real_file = tmp_path / "real.py"
        real_file.write_text("x = 1")
        link = tmp_path / "link.py"
        link.symlink_to(real_file)

        files = {link: "x = 1"}
        staging_root = tmp_path / "staging"
        with pytest.raises(StagingError, match="Symlink input rejected"):
            with create_staging(
                files, staging_root, "feat", 1, project_root=tmp_path,
            ):
                pass

    def test_default_staging_root(self, tmp_path):
        files = {tmp_path / "a.py": "x = 1"}
        (tmp_path / "a.py").write_text("x = 1")

        with create_staging(
            files, None, "feat", 1, project_root=tmp_path,
        ) as ctx:
            assert ".startd8" in str(ctx.staging_dir)
            assert "repair" in str(ctx.staging_dir)

    def test_multiple_files(self, tmp_path):
        files = {
            tmp_path / "a.py": "x = 1",
            tmp_path / "b.py": "y = 2",
        }
        for p, c in files.items():
            p.write_text(c)

        staging_root = tmp_path / "staging"
        with create_staging(
            files, staging_root, "feat", 1, project_root=tmp_path,
        ) as ctx:
            assert len(ctx.file_paths) == 2
            assert len(ctx.paths) == 2


class TestStagingContext:
    def test_write_repaired(self, tmp_path):
        staged_a = tmp_path / "a.py"
        staged_a.write_text("original")
        orig_a = Path("/project/a.py")

        ctx = StagingContext(
            staging_dir=tmp_path,
            files={orig_a: "original"},
            file_paths={orig_a: staged_a},
        )
        ctx.write_repaired({orig_a: "repaired content"})
        assert staged_a.read_text() == "repaired content"

    def test_write_repaired_skips_unknown(self, tmp_path):
        ctx = StagingContext(staging_dir=tmp_path)
        # Should not raise, just log warning
        ctx.write_repaired({Path("/unknown.py"): "content"})

    def test_apply_atomic(self, tmp_path):
        # Create original file
        orig_file = tmp_path / "project" / "a.py"
        orig_file.parent.mkdir(parents=True)
        orig_file.write_text("original")

        # Create staged file
        staged_file = tmp_path / "staging" / "a.py"
        staged_file.parent.mkdir(parents=True)
        staged_file.write_text("repaired")

        ctx = StagingContext(
            staging_dir=tmp_path / "staging",
            files={orig_file: "original"},
            file_paths={orig_file: staged_file},
        )
        ctx.apply_atomic()
        assert orig_file.read_text() == "repaired"
        assert ctx._applied is True

    def test_paths_property(self, tmp_path):
        p1 = tmp_path / "a.py"
        p2 = tmp_path / "b.py"
        ctx = StagingContext(
            staging_dir=tmp_path,
            file_paths={Path("/a.py"): p1, Path("/b.py"): p2},
        )
        assert set(ctx.paths) == {p1, p2}


class TestCleanupExpiredStaging:
    def test_removes_old_dirs(self, tmp_path):
        staging_root = tmp_path / "staging"
        feat_dir = staging_root / "feat"
        old_dir = feat_dir / "1_1000"
        old_dir.mkdir(parents=True)

        # Set mtime to 48 hours ago
        old_time = time.time() - (48 * 3600)
        os.utime(old_dir, (old_time, old_time))

        removed = cleanup_expired_staging(staging_root, retention_hours=24)
        assert removed == 1
        assert not old_dir.exists()

    def test_keeps_recent_dirs(self, tmp_path):
        staging_root = tmp_path / "staging"
        feat_dir = staging_root / "feat"
        recent_dir = feat_dir / "1_recent"
        recent_dir.mkdir(parents=True)

        removed = cleanup_expired_staging(staging_root, retention_hours=24)
        assert removed == 0
        assert recent_dir.exists()

    def test_nonexistent_root_returns_zero(self, tmp_path):
        assert cleanup_expired_staging(tmp_path / "nonexistent") == 0

    def test_cleans_empty_feature_dirs(self, tmp_path):
        staging_root = tmp_path / "staging"
        feat_dir = staging_root / "feat"
        old_dir = feat_dir / "1_1000"
        old_dir.mkdir(parents=True)

        old_time = time.time() - (48 * 3600)
        os.utime(old_dir, (old_time, old_time))

        cleanup_expired_staging(staging_root, retention_hours=24)
        # Feature dir should also be removed since it's empty now
        assert not feat_dir.exists()
