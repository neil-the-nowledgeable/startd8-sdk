# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Tests for deterministic ``startd8 project init`` (project-init M0–M2).

Covers shape detection (M0/FR-2), postings + inbox-ready + idempotency + the FR-11 scaffold parity
refactor (M1/FR-3/FR-4/FR-11), and the $0 non-interactive producer seam (M2/FR-5/FR-12/FR-13/FR-14),
plus the SOTTO byte-identical-when-absent invariant (FR-6) and the read-only ``--check`` audit (FR-10).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.cli_project import project_app
from startd8.kickoff_experience import vipp_seam as seam
from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction
from startd8.project.init import (
    SHAPE_BROWNFIELD_PARTIAL,
    SHAPE_BROWNFIELD_READY,
    SHAPE_GREENFIELD,
    ProposalsFileError,
    detect_shape,
    run_project_init,
)

runner = CliRunner()


def _proj(tmp_path) -> Path:
    """Realpath the tmp dir so the macOS ``/var`→`/private/var`` symlink doesn't trip confinement."""
    return Path(os.path.realpath(tmp_path))


def _brownfield_ready(root: Path) -> None:
    (root / "prisma").mkdir(parents=True, exist_ok=True)
    (root / "prisma" / "schema.prisma").write_text("model A { id Int @id }\n", encoding="utf-8")
    inputs = root / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    for dom in ("business-targets", "observability", "conventions", "build-preferences"):
        (inputs / f"{dom}.yaml").write_text("provenance_default: authored\n", encoding="utf-8")


# --- M0: shape detection (FR-2) -------------------------------------------------------------------


def test_detect_greenfield(tmp_path):
    shape = detect_shape(_proj(tmp_path))
    assert shape.verdict == SHAPE_GREENFIELD
    assert shape.is_greenfield


def test_detect_brownfield_ready(tmp_path):
    root = _proj(tmp_path)
    _brownfield_ready(root)
    shape = detect_shape(root)
    assert shape.verdict == SHAPE_BROWNFIELD_READY
    assert shape.has_contract
    assert len(shape.kickoff_inputs_present) == 4


def test_detect_brownfield_partial_contract_only(tmp_path):
    root = _proj(tmp_path)
    (root / "prisma").mkdir()
    (root / "prisma" / "schema.prisma").write_text("model A { id Int @id }\n", encoding="utf-8")
    assert detect_shape(root).verdict == SHAPE_BROWNFIELD_PARTIAL


def test_detect_brownfield_partial_inputs_only(tmp_path):
    root = _proj(tmp_path)
    inputs = root / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "conventions.yaml").write_text("provenance_default: authored\n", encoding="utf-8")
    assert detect_shape(root).verdict == SHAPE_BROWNFIELD_PARTIAL


# --- M1: postings + inbox-ready + idempotency (FR-3/FR-4/FR-6) ------------------------------------


def test_init_establishes_vipp_posting_and_inbox_ready(tmp_path):
    root = _proj(tmp_path)
    summary = run_project_init(root, sdk_version="9.9.9")
    assert "vipp" in summary["postings"]
    assert "fde" not in summary["postings"]
    assert (root / ".startd8" / "vipp" / "vipp-context.json").is_file()
    assert (root / ".startd8" / "vipp" / ".gitignore").read_text().strip() == "*"
    assert (root / ".startd8" / "vipp" / "inbox-seq").is_file()
    # default outcome is inbox-*ready*, not inbox-*produced* (OQ-4)
    assert summary["producer"]["status"] == "no_gap"
    assert not (root / ".startd8" / "vipp" / "proposals-inbox.json").exists()


def test_with_fde_opt_in(tmp_path):
    root = _proj(tmp_path)
    summary = run_project_init(root, with_fde=True, sdk_version="9.9.9")
    assert "fde" in summary["postings"]
    assert (root / ".startd8" / "fde" / "fde-context.json").is_file()


def test_init_is_idempotent_second_run_writes_nothing(tmp_path):
    root = _proj(tmp_path)
    run_project_init(root, sdk_version="9.9.9")
    second = run_project_init(root, sdk_version="9.9.9")
    # No project-content writes on the re-run (postings restamp SDK metadata, not project content).
    assert second["inbox_ready"]["written"] == []


def test_sotto_byte_identical_when_never_initialized(tmp_path):
    """FR-6 — a directory that never runs init is unchanged (no .startd8/ appears)."""
    root = _proj(tmp_path)
    (root / "keep.txt").write_text("hi\n", encoding="utf-8")
    before = {p.name for p in root.iterdir()}
    detect_shape(root)  # read-only — must not write
    run_project_init(root, check=True, sdk_version="9.9.9")  # --check is read-only
    after = {p.name for p in root.iterdir()}
    assert before == after
    assert not (root / ".startd8").exists()


# --- M1: FR-11 scaffold parity --------------------------------------------------------------------


def test_fr11_ready_inbox_matches_serialize_scaffold(tmp_path):
    """The inbox-ready scaffold and the producer's scaffold are the same bytes (single source)."""
    a = _proj(tmp_path) / "a"
    b = _proj(tmp_path) / "b"
    a.mkdir()
    b.mkdir()

    # Path A: project-init readies the inbox.
    run_project_init(a, sdk_version="9.9.9")
    # Path B: a producer serializes (which bootstraps the scaffold via the shared function).
    buf = ProposalBuffer()
    buf.add(ProposedAction(kind="instantiate", params={"posture": "prototype"}, id="i1"))
    seam.serialize_buffer(buf, str(b))

    for name in (".gitignore",):
        assert (a / ".startd8" / "vipp" / name).read_text() == (
            b / ".startd8" / "vipp" / name
        ).read_text()
    # Both paths establish the inbox-seq counter file.
    assert (a / ".startd8" / "vipp" / "inbox-seq").is_file()
    assert (b / ".startd8" / "vipp" / "inbox-seq").is_file()


def test_fr11_scaffold_does_not_reset_advanced_seq(tmp_path):
    """Standing up the scaffold on a mid-loop project keeps the monotonic seq (no-clobber)."""
    root = _proj(tmp_path)
    buf = ProposalBuffer()
    buf.add(ProposedAction(kind="instantiate", params={"posture": "prototype"}, id="i1"))
    seam.serialize_buffer(buf, str(root))  # seq -> 1
    seq_after_first = (root / ".startd8" / "vipp" / "inbox-seq").read_text().strip()
    assert seq_after_first == "1"
    # ready_inbox must not reset the counter to 0.
    from startd8.project.init import ready_inbox

    ready_inbox(root)
    assert (root / ".startd8" / "vipp" / "inbox-seq").read_text().strip() == "1"


# --- M2: producer seam (FR-5/FR-12/FR-13/FR-14) ---------------------------------------------------


def test_greenfield_instantiate_produces_one_proposal(tmp_path):
    root = _proj(tmp_path)
    summary = run_project_init(root, instantiate=True, sdk_version="9.9.9")
    assert summary["producer"]["status"] == "produced"
    assert summary["producer"]["proposal_count"] == 1
    env = json.loads((root / ".startd8" / "vipp" / "proposals-inbox.json").read_text())
    # FR-14 — built via ProposedAction + serialize_buffer, so envelope parity holds.
    assert env["kind"] == "vipp-proposal-envelope"
    assert env["envelope_seq"] == 1
    assert len(env["proposals"]) == 1
    assert env["proposals"][0]["kind"] == "instantiate"
    assert env["proposals"][0]["params"] == {"posture": "prototype"}


def test_instantiate_on_brownfield_is_not_produced(tmp_path):
    root = _proj(tmp_path)
    _brownfield_ready(root)
    summary = run_project_init(root, instantiate=True, sdk_version="9.9.9")
    assert summary["producer"]["status"] == "not_greenfield"
    assert not (root / ".startd8" / "vipp" / "proposals-inbox.json").exists()


def test_brownfield_ready_produces_no_inbox(tmp_path):
    root = _proj(tmp_path)
    _brownfield_ready(root)
    summary = run_project_init(root, sdk_version="9.9.9")
    assert summary["producer"]["status"] == "no_gap"


def test_proposals_file_produces_inbox(tmp_path):
    root = _proj(tmp_path)
    pf = root / "props.yaml"
    pf.write_text(
        "proposals:\n"
        "  - kind: friction\n"
        "    friction: onboarding unclear\n"
        "    what_happened: no single init\n"
        "    implication: manual errors\n"
        "  - kind: instantiate\n"
        "    posture: prototype\n",
        encoding="utf-8",
    )
    summary = run_project_init(root, proposals_file=pf, sdk_version="9.9.9")
    assert summary["producer"]["status"] == "produced"
    assert summary["producer"]["proposal_count"] == 2
    env = json.loads((root / ".startd8" / "vipp" / "proposals-inbox.json").read_text())
    assert [p["kind"] for p in env["proposals"]] == ["friction", "instantiate"]


def test_proposals_file_bad_kind_rejected_nothing_written(tmp_path):
    """FR-12 — an entry with a kind outside PROPOSAL_KINDS fails before serialize (exit 2)."""
    root = _proj(tmp_path)
    pf = root / "bad.yaml"
    pf.write_text("- kind: nonsense\n  foo: bar\n", encoding="utf-8")
    with pytest.raises(ProposalsFileError):
        run_project_init(root, proposals_file=pf, sdk_version="9.9.9")
    assert not (root / ".startd8" / "vipp" / "proposals-inbox.json").exists()


def test_proposals_file_bad_per_kind_validation_rejected(tmp_path):
    """FR-12 — a valid kind that fails its per-kind validator (empty friction) is rejected."""
    root = _proj(tmp_path)
    pf = root / "bad2.yaml"
    pf.write_text("- kind: friction\n  friction: ''\n  what_happened: x\n  implication: y\n", encoding="utf-8")
    with pytest.raises(ProposalsFileError):
        run_project_init(root, proposals_file=pf, sdk_version="9.9.9")
    assert not (root / ".startd8" / "vipp" / "proposals-inbox.json").exists()


def test_proposals_file_malformed_shape_rejected(tmp_path):
    root = _proj(tmp_path)
    pf = root / "notalist.yaml"
    pf.write_text("just: a mapping\n", encoding="utf-8")
    with pytest.raises(ProposalsFileError):
        run_project_init(root, proposals_file=pf, sdk_version="9.9.9")


def test_undrained_inbox_is_skip_not_error(tmp_path):
    """FR-13 — re-producing over an undrained inbox is a clean skip (exit 0), not a failure."""
    root = _proj(tmp_path)
    run_project_init(root, instantiate=True, sdk_version="9.9.9")  # first inbox
    summary = run_project_init(root, instantiate=True, sdk_version="9.9.9")
    assert summary["producer"]["status"] == "skipped_undrained"


# --- M3 preview: --check drift audit (FR-10) ------------------------------------------------------


def test_check_reports_in_sync_after_init(tmp_path):
    root = _proj(tmp_path)
    run_project_init(root, sdk_version="9.9.9")
    audit = run_project_init(root, check=True, sdk_version="9.9.9")
    assert audit["action"] == "init-check"
    assert audit["in_sync"] is True
    assert audit["drift"] == []


def test_check_reports_drift_on_bare_dir(tmp_path):
    root = _proj(tmp_path)
    audit = run_project_init(root, check=True, sdk_version="9.9.9")
    assert audit["in_sync"] is False
    assert audit["initialized"] is False
    assert "vipp_posting" in audit["drift"]


def test_check_nonexistent_root_is_error(tmp_path):
    """FR-10 — an unreadable / non-directory root is an error (exit 2), not drift."""
    missing = _proj(tmp_path) / "does-not-exist"
    audit = run_project_init(missing, check=True, sdk_version="9.9.9")
    assert "error" in audit
    assert audit["in_sync"] is False


# --- M3: FR-6 SOTTO + FR-7 confined writes --------------------------------------------------------


def test_sotto_project_content_byte_identical_across_double_init(tmp_path):
    """FR-6/FR-7 — a second init leaves *project content* (the inbox scaffold) byte-identical.

    The SDK-owned posting metadata (``vipp-context.json``) legitimately restamps each run — that is
    the documented FR-7 boundary — so the SOTTO claim is about the confined content writes.
    """
    root = _proj(tmp_path)
    run_project_init(root, sdk_version="9.9.9")
    vipp = root / ".startd8" / "vipp"
    before = {name: (vipp / name).read_bytes() for name in (".gitignore", "inbox-seq")}

    second = run_project_init(root, sdk_version="9.9.9")
    assert second["inbox_ready"]["written"] == []  # no content write on the re-run
    after = {name: (vipp / name).read_bytes() for name in (".gitignore", "inbox-seq")}
    assert before == after  # byte-identical project content


def test_fr7_content_writes_are_confined_symlinked_root_refused(tmp_path):
    """FR-7 — project-content writes ride the confined ``apply_write_plan``; a symlinked root is
    refused by ``ensure_inbox_scaffold`` (``resolve_confined_root``) before any inbox scaffold lands."""
    from startd8.concierge.safe_write import SafeWriteError

    target = _proj(tmp_path) / "real"
    target.mkdir()
    link = _proj(tmp_path) / "link"
    os.symlink(target, link)

    with pytest.raises(SafeWriteError):
        run_project_init(link, sdk_version="9.9.9")
    # No inbox scaffold was written into the real target through the symlink.
    assert not (target / ".startd8" / "vipp" / ".gitignore").exists()


# --- CLI surface (FR-1/FR-9) ----------------------------------------------------------------------


def test_cli_init_greenfield_exit0(tmp_path):
    root = str(_proj(tmp_path))
    result = runner.invoke(project_app, ["init", root])
    assert result.exit_code == 0
    assert "project init" in result.stdout


def test_cli_init_json_output(tmp_path):
    root = str(_proj(tmp_path))
    result = runner.invoke(project_app, ["init", root, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "init"
    assert payload["schema_version"] == 1


def test_cli_check_drift_exit1(tmp_path):
    root = str(_proj(tmp_path))
    result = runner.invoke(project_app, ["init", root, "--check"])
    assert result.exit_code == 1  # bare dir → drift


def test_cli_check_in_sync_exit0(tmp_path):
    root = str(_proj(tmp_path))
    runner.invoke(project_app, ["init", root])
    result = runner.invoke(project_app, ["init", root, "--check"])
    assert result.exit_code == 0


def test_cli_bad_proposals_exit2(tmp_path):
    root = _proj(tmp_path)
    pf = root / "bad.yaml"
    pf.write_text("- kind: nonsense\n", encoding="utf-8")
    result = runner.invoke(project_app, ["init", str(root), "--proposals", str(pf)])
    assert result.exit_code == 2
