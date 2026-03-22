"""Tests for query_prime.fp_registry — false positive tracking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.query_prime.fp_registry import FPEntry, FalsePositiveRegistry
from startd8.query_prime.models import SecurityCheckType, SecurityFinding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _finding(
    check_type: SecurityCheckType = SecurityCheckType.CREDENTIAL_LEAKAGE,
    pattern_hash: str = "hash-001",
) -> SecurityFinding:
    return SecurityFinding(
        check_type=check_type,
        severity="warning",
        message="Test finding",
        pattern_hash=pattern_hash,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFalsePositiveRegistry:
    """Tests for FalsePositiveRegistry."""

    def test_register_increments_count(self, tmp_path: Path):
        reg = FalsePositiveRegistry(path=tmp_path / "fp.json")
        finding = _finding()
        reg.register(finding)
        assert reg.entries["hash-001"].occurrences == 1
        reg.register(finding)
        assert reg.entries["hash-001"].occurrences == 2

    def test_auto_suppress_at_threshold(self, tmp_path: Path):
        reg = FalsePositiveRegistry(
            path=tmp_path / "fp.json", suppression_threshold=3,
        )
        finding = _finding()
        for _ in range(3):
            reg.register(finding)
        assert reg.is_suppressed(finding)

    def test_not_suppressed_below_threshold(self, tmp_path: Path):
        reg = FalsePositiveRegistry(
            path=tmp_path / "fp.json", suppression_threshold=3,
        )
        finding = _finding()
        for _ in range(2):
            reg.register(finding)
        assert not reg.is_suppressed(finding)

    def test_injection_never_suppressed(self, tmp_path: Path):
        reg = FalsePositiveRegistry(
            path=tmp_path / "fp.json", suppression_threshold=1,
        )
        finding = _finding(check_type=SecurityCheckType.INJECTION)
        for _ in range(10):
            reg.register(finding)
        assert not reg.is_suppressed(finding)

    def test_save_and_load(self, tmp_path: Path):
        path = tmp_path / "fp.json"
        reg = FalsePositiveRegistry(path=path, suppression_threshold=2)
        finding = _finding()
        for _ in range(3):
            reg.register(finding)
        reg.save()

        reg2 = FalsePositiveRegistry(path=path)
        reg2.load()
        assert len(reg2) == 1
        assert reg2.entries["hash-001"].occurrences == 3

    def test_load_missing_file(self, tmp_path: Path):
        reg = FalsePositiveRegistry(path=tmp_path / "nonexistent.json")
        reg.load()  # Should not raise
        assert len(reg) == 0

    def test_empty_pattern_hash_ignored(self, tmp_path: Path):
        reg = FalsePositiveRegistry(path=tmp_path / "fp.json")
        finding = _finding(pattern_hash="")
        reg.register(finding)
        assert len(reg) == 0
        assert not reg.is_suppressed(finding)

    def test_custom_suppression_threshold(self, tmp_path: Path):
        reg = FalsePositiveRegistry(
            path=tmp_path / "fp.json", suppression_threshold=5,
        )
        finding = _finding()
        for _ in range(4):
            reg.register(finding)
        assert not reg.is_suppressed(finding)
        reg.register(finding)
        assert reg.is_suppressed(finding)

    def test_multiple_findings_independent(self, tmp_path: Path):
        reg = FalsePositiveRegistry(
            path=tmp_path / "fp.json", suppression_threshold=2,
        )
        f1 = _finding(pattern_hash="a")
        f2 = _finding(pattern_hash="b")
        for _ in range(2):
            reg.register(f1)
        reg.register(f2)
        assert reg.is_suppressed(f1)
        assert not reg.is_suppressed(f2)

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "nested" / "dir" / "fp.json"
        reg = FalsePositiveRegistry(path=path)
        reg.register(_finding())
        reg.save()
        assert path.is_file()

    def test_lifecycle_finding_can_be_suppressed(self, tmp_path: Path):
        reg = FalsePositiveRegistry(
            path=tmp_path / "fp.json", suppression_threshold=2,
        )
        finding = _finding(check_type=SecurityCheckType.LIFECYCLE)
        for _ in range(2):
            reg.register(finding)
        assert reg.is_suppressed(finding)


class TestFPEntry:
    """Tests for FPEntry serialization."""

    def test_roundtrip(self):
        entry = FPEntry(
            pattern_hash="abc",
            check_type="credential_leakage",
            message="test",
            database="postgresql",
            framework="npgsql",
            occurrences=5,
            suppressed=True,
        )
        d = entry.to_dict()
        restored = FPEntry.from_dict(d)
        assert restored == entry

    def test_from_dict_ignores_extra_keys(self):
        d = {
            "pattern_hash": "abc",
            "check_type": "lifecycle",
            "message": "test",
            "database": "",
            "framework": "",
            "occurrences": 1,
            "suppressed": False,
            "extra_key": "ignored",
        }
        entry = FPEntry.from_dict(d)
        assert entry.pattern_hash == "abc"
