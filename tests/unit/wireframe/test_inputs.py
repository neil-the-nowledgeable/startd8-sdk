"""Assembly-inputs resolution tests (FR-W6, FR-W7, FR-W8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.wireframe import AssemblyInputsError, CATALOG_KEYS, load_assembly_inputs
from startd8.wireframe.inputs import CONVENTION_PATHS


def test_convention_defaults_map_exact_filenames(tmp_path: Path) -> None:
    """FR-W8/R6-F2: per-key exact paths — no glob; a stray prisma/extra.yaml is ignored."""
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "extra.yaml").write_text("stray: true", encoding="utf-8")
    inputs = load_assembly_inputs(project_root=tmp_path)
    assert set(inputs.entries) == set(CATALOG_KEYS)
    for key, rel in CONVENTION_PATHS.items():
        entry = inputs.entry(key)
        assert entry.source == "convention"
        assert entry.resolved_path == (tmp_path / rel).resolve()
    assert not any("extra.yaml" in str(e.resolved_path) for e in inputs.entries.values())


def test_yaml_merge_last_wins_and_warns(tmp_path: Path) -> None:
    """FR-W6 last-wins per key; overwrites recorded in merge_warnings (R5-S5)."""
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("inputs:\n  schema: {path: one.prisma}\n", encoding="utf-8")
    b.write_text("inputs:\n  schema: {path: two.prisma}\n", encoding="utf-8")
    inputs = load_assembly_inputs(yaml_paths=[a, b], project_root=tmp_path)
    assert inputs.entry("schema").path.name == "two.prisma"
    assert inputs.entry("schema").source == "yaml"
    assert len(inputs.merge_warnings) == 1
    w = inputs.merge_warnings[0]
    assert w["key"] == "schema" and w["source_file"] == str(b)
    # Single file ⇒ no warnings.
    assert load_assembly_inputs(yaml_paths=[a], project_root=tmp_path).merge_warnings == ()


def test_paths_resolve_relative_to_yaml_dir(tmp_path: Path) -> None:
    sub = tmp_path / "docs"
    sub.mkdir()
    inv = sub / "inputs.yaml"
    inv.write_text("inputs:\n  schema: {path: ../prisma/schema.prisma}\n", encoding="utf-8")
    inputs = load_assembly_inputs(yaml_paths=[inv], project_root=tmp_path)
    assert inputs.entry("schema").resolved_path == (tmp_path / "prisma" / "schema.prisma").resolve()


def test_flags_override_yaml(tmp_path: Path) -> None:
    """FR-W7: direct flags win over YAML-provided values."""
    inv = tmp_path / "inputs.yaml"
    inv.write_text("inputs:\n  views: {path: prisma/views.yaml}\n", encoding="utf-8")
    inputs = load_assembly_inputs(
        yaml_paths=[inv],
        overrides={"views": tmp_path / "other" / "views.yaml"},
        project_root=tmp_path,
    )
    assert inputs.entry("views").source == "flag"
    assert inputs.entry("views").resolved_path == (tmp_path / "other" / "views.yaml").resolve()


def test_status_override_parsed(tmp_path: Path) -> None:
    inv = tmp_path / "inputs.yaml"
    inv.write_text(
        "inputs:\n  completeness: {path: prisma/completeness.yaml, status: absent}\n",
        encoding="utf-8",
    )
    inputs = load_assembly_inputs(yaml_paths=[inv], project_root=tmp_path)
    assert inputs.entry("completeness").status_override == "absent"


@pytest.mark.parametrize(
    "content, match",
    [
        ("inputs:\n  bogus_key: {path: x}\n", "unknown catalog keys"),
        ("inputs:\n  schema: {path: x, surprise: 1}\n", "unknown keys"),
        ("toplevel_extra: 1\ninputs: {}\n", "unknown top-level keys"),
        ("inputs:\n  schema: {status: authored}\n", "needs a string `path`"),
        ("inputs:\n  schema: {path: x, status: wip}\n", "status override"),
        ("- just\n- a\n- list\n", "must be a mapping"),
    ],
)
def test_strict_inputs_yaml_loud_fails(tmp_path: Path, content: str, match: str) -> None:
    """FR-W9/R2-F3 fatal class: garbled inventory never silently continues."""
    inv = tmp_path / "inputs.yaml"
    inv.write_text(content, encoding="utf-8")
    with pytest.raises(AssemblyInputsError, match=match):
        load_assembly_inputs(yaml_paths=[inv], project_root=tmp_path)


def test_unreadable_and_non_utf8_inputs_fatal(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    with pytest.raises(AssemblyInputsError, match="unreadable"):
        load_assembly_inputs(yaml_paths=[missing], project_root=tmp_path)
    binary = tmp_path / "bin.yaml"
    binary.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(AssemblyInputsError, match="not valid UTF-8"):
        load_assembly_inputs(yaml_paths=[binary], project_root=tmp_path)


def test_path_escape_rejected(tmp_path: Path) -> None:
    """R3-F4: confinement to project_root, checked before any read."""
    inv = tmp_path / "inputs.yaml"
    inv.write_text("inputs:\n  schema: {path: ../../../../etc/passwd}\n", encoding="utf-8")
    with pytest.raises(AssemblyInputsError, match="outside the project root"):
        load_assembly_inputs(yaml_paths=[inv], project_root=tmp_path)
    with pytest.raises(AssemblyInputsError, match="outside the project root"):
        load_assembly_inputs(
            overrides={"schema": Path("/etc/passwd")}, project_root=tmp_path
        )
