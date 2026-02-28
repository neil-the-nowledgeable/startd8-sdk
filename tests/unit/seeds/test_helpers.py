"""Tests for startd8.seeds.helpers."""

import hashlib
from pathlib import Path

from startd8.seeds.helpers import (
    context_files_with_checksums,
    ensure_onboarding_in_context_files,
    sha256_file_hex,
)


class TestSha256FileHex:
    def test_computes_correct_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert sha256_file_hex(f) == expected


class TestContextFilesWithChecksums:
    def test_empty_input(self):
        assert context_files_with_checksums(None) == []
        assert context_files_with_checksums([]) == []

    def test_existing_file(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("pass")
        result = context_files_with_checksums(["a.py"], base_dir=tmp_path)
        assert len(result) == 1
        assert result[0]["path"] == "a.py"
        assert result[0]["checksum"] is not None

    def test_missing_file(self, tmp_path):
        result = context_files_with_checksums(["nonexistent.py"], base_dir=tmp_path)
        assert len(result) == 1
        assert result[0]["checksum"] is None

    def test_absolute_path(self, tmp_path):
        f = tmp_path / "abs.py"
        f.write_text("# absolute")
        result = context_files_with_checksums([str(f)])
        assert len(result) == 1
        assert result[0]["checksum"] is not None


class TestEnsureOnboardingInContextFiles:
    def test_appends_when_missing(self, tmp_path):
        ob_path = tmp_path / "onboarding-metadata.json"
        ob_path.write_text("{}")
        files_list = [{"path": "other.py", "checksum": "abc"}]
        ensure_onboarding_in_context_files(
            files_list, {"key": "val"}, tmp_path
        )
        assert len(files_list) == 2
        assert files_list[1]["path"] == str(ob_path)

    def test_skips_when_already_present(self, tmp_path):
        ob_path = tmp_path / "onboarding-metadata.json"
        ob_path.write_text("{}")
        files_list = [
            {"path": str(ob_path), "checksum": "abc"},
        ]
        ensure_onboarding_in_context_files(
            files_list, {"key": "val"}, tmp_path
        )
        assert len(files_list) == 1

    def test_no_op_when_no_onboarding(self, tmp_path):
        files_list = [{"path": "a.py"}]
        ensure_onboarding_in_context_files(files_list, None, tmp_path)
        assert len(files_list) == 1

    def test_no_op_when_no_files(self, tmp_path):
        ensure_onboarding_in_context_files(None, {"key": "val"}, tmp_path)
        ensure_onboarding_in_context_files([], {"key": "val"}, tmp_path)
