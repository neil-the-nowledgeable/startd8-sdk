"""Bounded kickoff-doc loader — both monolithic and per-domain authoring layouts."""

from __future__ import annotations

import textwrap
from pathlib import Path

from startd8.kickoff_experience.docs import live_schema_text, load_kickoff_docs


def test_loads_per_domain_authoring_dir(tmp_path: Path) -> None:
    authoring = tmp_path / "docs" / "kickoff" / "authoring"
    authoring.mkdir(parents=True)
    (authoring / "conventions.md").write_text("## Technology conventions\n", encoding="utf-8")
    (authoring / "views.md").write_text("## Views\n", encoding="utf-8")
    docs = load_kickoff_docs(tmp_path)
    assert set(docs) == {"conventions.md", "views.md"}


def test_loads_monolithic_requirements(tmp_path: Path) -> None:
    kdir = tmp_path / "docs" / "kickoff"
    kdir.mkdir(parents=True)
    (kdir / "REQUIREMENTS.md").write_text("## Entities\n", encoding="utf-8")
    docs = load_kickoff_docs(tmp_path)
    assert "REQUIREMENTS.md" in docs


def test_both_layouts_merge_without_clobber(tmp_path: Path) -> None:
    authoring = tmp_path / "docs" / "kickoff" / "authoring"
    authoring.mkdir(parents=True)
    (authoring / "conventions.md").write_text("## Technology conventions\n", encoding="utf-8")
    (tmp_path / "docs" / "kickoff" / "PLAN.md").write_text("## Views\n", encoding="utf-8")
    docs = load_kickoff_docs(tmp_path)
    assert {"conventions.md", "PLAN.md"} <= set(docs)


def test_empty_project_returns_empty(tmp_path: Path) -> None:
    assert load_kickoff_docs(tmp_path) == {}


def test_live_schema_text_reads_prisma(tmp_path: Path) -> None:
    prisma = tmp_path / "prisma"
    prisma.mkdir()
    (prisma / "schema.prisma").write_text("model A {\n  id Int @id\n}\n", encoding="utf-8")
    assert "model A" in (live_schema_text(tmp_path) or "")
    # No contract → None.
    assert live_schema_text(tmp_path / "nope") is None
