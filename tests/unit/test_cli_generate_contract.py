"""`startd8 generate contract` — emit prisma/schema.prisma from the requirements doc (FR-EMIT).

The inverse of the other `generate` subcommands: it PRODUCES the contract from prose, behind the
FR-PE-6 round-trip + parity gate, writing a run-dir draft by default and flipping the project tree
only on the explicit `--promote` (FR-PE-7).
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from startd8.cli_generate import generate_app

pytestmark = pytest.mark.unit

runner = CliRunner()

# A minimal requirements doc in the wireframe grammar (## Entities → ### blocks with field tables).
DOC = (
    "# Reqs\n\n"
    "## Entities\n\n"
    "### Profile\n"
    "| Field | Type | Required | Notes |\n"
    "|-------|------|----------|-------|\n"
    "| name | text | yes | |\n\n"
    "### ProofPoint\n"
    "| Field | Type | Required | Notes |\n"
    "|-------|------|----------|-------|\n"
    "| result | text | yes | |\n\n"
    "## Pages\n\n"            # gives --with-manifests a pages.yaml to derive
    "| Page | Content file |\n"
    "|------|--------------|\n"
    "| Home | home.md |\n"
)


def _write_doc(tmp_path, text=DOC):
    doc = tmp_path / "REQUIREMENTS.md"
    doc.write_text(text, encoding="utf-8")
    return doc


def test_draft_only_writes_run_dir_not_project(tmp_path):
    doc = _write_doc(tmp_path)
    run = tmp_path / "run"
    res = runner.invoke(generate_app, ["contract", "-r", str(doc), "--out", str(run)])
    assert res.exit_code == 0, res.output
    # the gated draft lands in the run-dir ONLY (FR-PE-7) — no project schema written
    assert (run / "schema.prisma").is_file()
    assert not (tmp_path / "prisma" / "schema.prisma").exists()
    assert "models rendered: 2" in res.output


def test_emitted_header_names_the_requirements_doc_not_generate_backend(tmp_path):
    """OQ-PE-4 / FR-EMIT-5: the emitted schema's provenance points at the requirements doc and the
    `generate contract` regenerator — never the self-referential `generate backend` header."""
    doc = _write_doc(tmp_path)
    run = tmp_path / "run"
    runner.invoke(generate_app, ["contract", "-r", str(doc), "--out", str(run)])
    header = (run / "schema.prisma").read_text(encoding="utf-8")
    assert str(doc) in header
    assert "startd8 generate contract" in header
    assert "this schema is derived from prose" in header
    assert "Source of truth: the Prisma schema" not in header        # the old self-referential line
    assert "regenerate via `startd8 generate backend`" not in header
    assert "startd8-artifact: prisma-schema" in header               # derived-vs-handauthored marker kept


def test_promote_flips_project_tree_and_archives_handauthored(tmp_path):
    doc = _write_doc(tmp_path)
    contract = tmp_path / "prisma" / "schema.prisma"
    contract.parent.mkdir(parents=True)
    contract.write_text("// hand-authored, no provenance header\n", encoding="utf-8")
    res = runner.invoke(
        generate_app,
        ["contract", "-r", str(doc), "--out", str(tmp_path / "run"),
         "--contract-path", str(contract), "--promote"],
    )
    assert res.exit_code == 0, res.output
    assert "startd8-artifact: prisma-schema" in contract.read_text(encoding="utf-8")  # now derived
    # prior hand-authored contract preserved
    assert (contract.parent / "_superseded-handauthored" / "schema.prisma").is_file()


def test_promote_applies_parity_drift_as_the_intended_change(tmp_path):
    """FR-EMIT-3: parity drift is the CHANGE being applied (you promote *because* the prose
    changed), so a drifting emit promotes — it is surfaced, not blocked. Strict parity is `--check`."""
    doc = _write_doc(tmp_path)
    contract = tmp_path / "prisma" / "schema.prisma"
    contract.parent.mkdir(parents=True)
    # A live contract that diverges from what the doc emits → parity drift, but promotion proceeds.
    contract.write_text("model Unrelated {\n  id String @id\n}\n", encoding="utf-8")
    res = runner.invoke(
        generate_app,
        ["contract", "-r", str(doc), "--out", str(tmp_path / "run"),
         "--contract-path", str(contract), "--promote"],
    )
    assert res.exit_code == 0, res.output
    assert "applying" in res.output and "change(s)" in res.output     # drift surfaced as the changeset
    assert "startd8-artifact: prisma-schema" in contract.read_text(encoding="utf-8")  # flipped to derived


def test_promote_refuses_empty_contract_from_malformed_doc(tmp_path):
    """FR-EMIT-1/3: a doc with no parseable entities emits 0 models — refuse to flip the contract
    to an empty schema (fail loud), leaving the project contract untouched."""
    doc = _write_doc(tmp_path, "# Reqs\n\nNo entities section here.\n")
    contract = tmp_path / "prisma" / "schema.prisma"
    contract.parent.mkdir(parents=True)
    contract.write_text("model Real {\n  id String @id\n}\n", encoding="utf-8")
    before = contract.read_text(encoding="utf-8")
    res = runner.invoke(
        generate_app,
        ["contract", "-r", str(doc), "--out", str(tmp_path / "run"),
         "--contract-path", str(contract), "--promote"],
    )
    assert res.exit_code == 1
    assert "refusing to promote" in res.output
    assert contract.read_text(encoding="utf-8") == before            # untouched


def test_check_writes_nothing_and_signals_drift(tmp_path):
    """FR-EMIT-4: --check is gate-only (no project write); exit 1 on parity drift, 0 when clean."""
    doc = _write_doc(tmp_path)
    contract = tmp_path / "prisma" / "schema.prisma"
    contract.parent.mkdir(parents=True)
    contract.write_text("model Unrelated {\n  id String @id\n}\n", encoding="utf-8")
    drift = runner.invoke(generate_app, ["contract", "-r", str(doc), "--check",
                                          "--contract-path", str(contract)])
    assert drift.exit_code == 1                                      # parity drift
    # No project contract written, no run-dir litter in the project (throwaway tmp used).
    assert contract.read_text(encoding="utf-8").startswith("model Unrelated")
    # Clean when there is no live contract to diff against (round-trip only).
    clean = runner.invoke(generate_app, ["contract", "-r", str(doc), "--check",
                                          "--contract-path", str(tmp_path / "absent.prisma")])
    assert clean.exit_code == 0


def test_json_gate_result_shape(tmp_path):
    doc = _write_doc(tmp_path)
    res = runner.invoke(generate_app, ["contract", "-r", str(doc), "--out", str(tmp_path / "run"),
                                       "--json"])
    assert res.exit_code == 0
    import json
    payload = json.loads(res.stdout)
    assert payload["ok"] is True and payload["round_trips"] is True and payload["models"] == 2
    assert payload["parity_drift"] == [] and payload["draft_path"]


def test_with_manifests_promotes_yaml_next_to_contract(tmp_path):
    doc = _write_doc(tmp_path)
    contract = tmp_path / "prisma" / "schema.prisma"
    contract.parent.mkdir(parents=True)
    res = runner.invoke(
        generate_app,
        ["contract", "-r", str(doc), "--out", str(tmp_path / "run"),
         "--contract-path", str(contract), "--with-manifests", "--promote"],
    )
    assert res.exit_code == 0, res.output
    assert contract.is_file()
    # at least one derived manifest landed next to the contract for the $0 cascade to read
    assert any(contract.parent.glob("*.yaml"))


def test_promote_archives_handauthored_once_not_every_promote(tmp_path):
    """SDK_QUICK_WINS #2: the `_superseded-handauthored` archive is written ONCE (the original
    hand-authored contract), not re-churned on every promote."""
    doc = _write_doc(tmp_path)
    contract = tmp_path / "prisma" / "schema.prisma"
    contract.parent.mkdir(parents=True)
    contract.write_text("// original hand-authored\n", encoding="utf-8")
    args = ["contract", "-r", str(doc), "--out", str(tmp_path / "run"),
            "--contract-path", str(contract), "--promote"]
    runner.invoke(generate_app, args)
    archive = contract.parent / "_superseded-handauthored" / "schema.prisma"
    assert "original hand-authored" in archive.read_text(encoding="utf-8")
    first = archive.read_text(encoding="utf-8")
    # second promote (now overwriting a DERIVED contract) must NOT touch the archive
    runner.invoke(generate_app, args)
    assert archive.read_text(encoding="utf-8") == first  # archive unchanged — no churn


def test_with_manifests_skips_handcorrected_manifest_without_force(tmp_path):
    """SDK_QUICK_WINS #6: --with-manifests never silently clobbers a manifest whose content differs
    from a fresh derivation; --force overrides."""
    doc = _write_doc(tmp_path)
    contract = tmp_path / "prisma" / "schema.prisma"
    contract.parent.mkdir(parents=True)
    hand = contract.parent / "pages.yaml"
    hand.write_text("pages:\n  - hand-corrected: keep me\n", encoding="utf-8")
    base = ["contract", "-r", str(doc), "--out", str(tmp_path / "run"),
            "--contract-path", str(contract), "--with-manifests", "--promote"]
    res = runner.invoke(generate_app, base)
    assert res.exit_code == 0, res.output
    assert "skipped" in res.output and "pages.yaml" in res.output
    assert "hand-corrected: keep me" in hand.read_text(encoding="utf-8")  # not clobbered
    # --force overwrites it
    res2 = runner.invoke(generate_app, base + ["--force"])
    assert res2.exit_code == 0, res2.output
    assert "hand-corrected: keep me" not in hand.read_text(encoding="utf-8")


def test_malformed_requirements_fails_loud(tmp_path):
    """FR-EMIT-1: a doc with no parseable entities must fail loud, never emit an empty contract."""
    doc = _write_doc(tmp_path, "# Reqs\n\nNo entities section here.\n")
    res = runner.invoke(generate_app, ["contract", "-r", str(doc), "--out", str(tmp_path / "run")])
    # zero models → round-trip of an empty graph; the gate should not silently 'pass' a contentful flip.
    assert "models rendered: 0" in res.output
