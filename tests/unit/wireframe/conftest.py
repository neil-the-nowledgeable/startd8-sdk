"""Shared fixtures for the wireframe tests (golden fixture per R3-S3)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

GOLDEN_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "wireframe"


@pytest.fixture()
def golden_root() -> Path:
    """The named golden fixture (read-only — do not mutate in tests)."""
    assert GOLDEN_FIXTURE.is_dir(), f"golden fixture missing: {GOLDEN_FIXTURE}"
    return GOLDEN_FIXTURE


@pytest.fixture()
def golden_copy(tmp_path: Path) -> Path:
    """A mutable copy of the golden fixture for degradation tests."""
    dest = tmp_path / "proj"
    shutil.copytree(GOLDEN_FIXTURE, dest)
    return dest


MINI_SCHEMA = """\
model Profile {
  id   String @id @default(cuid())
  name String
}
"""


@pytest.fixture()
def mini_root(tmp_path: Path) -> Path:
    """Schema-only project: every other manifest absent."""
    root = tmp_path / "mini"
    (root / "prisma").mkdir(parents=True)
    (root / "prisma" / "schema.prisma").write_text(MINI_SCHEMA, encoding="utf-8")
    return root
