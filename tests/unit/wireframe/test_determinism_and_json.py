"""Determinism + JSON contract tests (FR-W2, FR-W10, FR-W12)."""

from __future__ import annotations

import json
from pathlib import Path

from startd8.wireframe import build_wireframe_plan, load_assembly_inputs
from startd8.wireframe.render import (
    SCHEMA_VERSION,
    canonical_json,
    persist_plan,
    plan_to_json,
)


def _plan(root: Path):
    return build_wireframe_plan(load_assembly_inputs(project_root=root), authoring=True)


def test_canonical_json_byte_identical(golden_root: Path) -> None:
    """FR-W2/R1-F5: same inputs ⇒ byte-identical canonical JSON."""
    assert canonical_json(_plan(golden_root)) == canonical_json(_plan(golden_root))


def test_meta_excluded_from_canonical_body(golden_root: Path) -> None:
    """R5-F1/R5-S1: _meta carries audit fields and is outside the canonical body."""
    plan = _plan(golden_root)
    full = json.loads(plan_to_json(plan))
    body = json.loads(canonical_json(plan))
    assert "_meta" in full and "_meta" not in body
    assert set(full["_meta"]) >= {"generated_at", "startd8_version", "emit_context"}
    full.pop("_meta")
    assert full == body


def test_schema_version_and_fingerprint(golden_root: Path, golden_copy: Path) -> None:
    """FR-W10 schema_version; R3-F2 fingerprint moves only when inputs change."""
    body = json.loads(canonical_json(_plan(golden_root)))
    assert body["schema_version"] == SCHEMA_VERSION == 1
    fp1 = body["inputs_fingerprint"]
    assert fp1 == json.loads(canonical_json(_plan(golden_root)))["inputs_fingerprint"]
    # Editing the contract bumps the fingerprint.
    schema = golden_copy / "prisma" / "schema.prisma"
    schema.write_text(schema.read_text(encoding="utf-8") + "\n// touched\n", encoding="utf-8")
    assert json.loads(canonical_json(_plan(golden_copy)))["inputs_fingerprint"] != fp1


def test_paths_are_project_relative_forward_slash(golden_root: Path) -> None:
    """FR-W2/R5-F4: claimed + provenance paths are project-relative posix."""
    body = json.loads(canonical_json(_plan(golden_root)))
    for path in body["claimed_paths"]:
        assert "\\" not in path and not path.startswith("/"), path
    for entry in body["input_provenance"].values():
        assert "\\" not in entry["resolved_path"], entry


def test_persist_atomic_and_advisory(golden_root: Path, tmp_path: Path) -> None:
    """FR-W12/R6-F4: atomic write, dir created; unwritable target warns, never raises."""
    plan = _plan(golden_root)
    target = tmp_path / "deep" / "nested" / "wireframe"
    written = persist_plan(plan, target, with_markdown=True)
    assert written["json"] and written["json"].is_file()
    assert written["markdown"] and written["markdown"].is_file()
    json.loads(written["json"].read_text(encoding="utf-8"))  # complete, parseable
    assert not list(target.glob(".*tmp"))  # no temp residue

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)  # read+execute only — unwritable
    try:
        result = persist_plan(plan, blocked / "wireframe")
        assert result["json"] is None  # degraded, no exception (advisory contract)
    finally:
        blocked.chmod(0o700)
