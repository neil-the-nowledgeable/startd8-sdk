"""WI-1 / FR-CL-1 (keystone): persist the forward manifest to the run dir.

The forward manifest is the single canonical interface contract the generator was
bound to. Persisting it (``forward-manifest.json``) makes it reachable to the
post-mortem and the *detached* Semantic Compliance Reviewer, which otherwise
re-derive intent from raw ``api_signatures`` prose (the generation↔validation
asymmetry). These tests pin the write behaviour and the clean Pydantic round-trip
that makes the read side (WI-2) trivial.

Also covers REQ-FM-PROVENANCE-FUEL: trio fuel at persist, optional committed-file
evidence in metadata, and fail-honest provenance completeness (not delivery health).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
    provenance_completeness,
)
from startd8.utils.code_manifest import ElementKind, Signature

_FIXTURES = Path(__file__).parent / "fixtures"
_NULL_SPECIMEN = _FIXTURES / "portal_v2_forward_manifest_null_provenance.json"


def _make_manifest(**overrides) -> ForwardManifest:
    """A representative manifest: one api-sig-sourced contract + one file spec."""
    contract = InterfaceContract(
        contract_id="C-001",
        category=ContractCategory.FUNCTION_NAME,
        confidence=ContractConfidence.EXPLICIT,
        description="Must use this name",
        binding_text="[BINDING] function=compute_total | Must use this name",
        function_name="compute_total",
        source_reference="deterministic",
    )
    element = ForwardElementSpec(
        kind=ElementKind.FUNCTION,
        name="compute_total",
        signature=Signature(params=[]),
        source_contract_id="C-001",
    )
    file_spec = ForwardFileSpec(file="src/totals.py", elements=[element])
    kwargs = dict(
        pipeline_run_id="run-001",
        contracts=[contract],
        file_specs={"src/totals.py": file_spec},
        stages_completed=["DESIGN"],
    )
    kwargs.update(overrides)
    return ForwardManifest(**kwargs)


def _contractor_with(
    manifest,
    project_root: Path,
    *,
    seed_path: Path | None = None,
) -> PrimeContractorWorkflow:
    """Build a bare PrimeContractor wired only with what the writer needs.

    Avoids the heavy __init__ (queue/engine/agents) — ``_write_forward_manifest``
    depends solely on ``self._forward_manifest``, ``self.project_root``, and
    optionally ``self._seed_path`` for checksum fuel.
    """
    pc = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
    pc._forward_manifest = manifest
    pc.project_root = project_root
    pc._seed_path = seed_path
    return pc


def _clear_kaizen_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAIZEN_RUN_ID", raising=False)


def test_forward_manifest_path_is_in_dot_startd8(tmp_path: Path) -> None:
    pc = _contractor_with(None, tmp_path)
    assert pc._forward_manifest_path() == tmp_path / ".startd8" / "forward-manifest.json"


def test_write_forward_manifest_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_kaizen_run_id(monkeypatch)
    manifest = _make_manifest()
    pc = _contractor_with(manifest, tmp_path)

    pc._write_forward_manifest()

    path = tmp_path / ".startd8" / "forward-manifest.json"
    assert path.exists(), "forward-manifest.json must be persisted"

    # Clean Pydantic round-trip (OQ-3): reload and compare by serialized form.
    # Fuel mutates the in-memory model before dump (generated_at at minimum).
    reloaded = ForwardManifest.model_validate_json(path.read_text(encoding="utf-8"))
    assert reloaded.model_dump() == manifest.model_dump()
    assert reloaded.contracts[0].function_name == "compute_total"
    assert reloaded.file_specs["src/totals.py"].elements[0].source_contract_id == "C-001"
    assert reloaded.generated_at  # FR-1 / FR-6: fuelled without schema bump


def test_write_forward_manifest_noop_when_absent(tmp_path: Path) -> None:
    """No seed manifest -> nothing written, no crash (FR-CC-1 degrade ethos)."""
    pc = _contractor_with(None, tmp_path)

    pc._write_forward_manifest()

    assert not (tmp_path / ".startd8" / "forward-manifest.json").exists()


# --- REQ-FM-PROVENANCE-FUEL -------------------------------------------------


def test_write_fuels_generated_at_and_run_id_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KAIZEN_RUN_ID", "test-run-42")
    manifest = _make_manifest(pipeline_run_id=None, generated_at=None, source_checksum=None)
    pc = _contractor_with(manifest, tmp_path)

    pc._write_forward_manifest()

    data = json.loads((tmp_path / ".startd8" / "forward-manifest.json").read_text())
    assert data["pipeline_run_id"] == "test-run-42"
    assert data["generated_at"]
    assert data["source_checksum"] is None


def test_write_copies_source_checksum_from_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_kaizen_run_id(monkeypatch)
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"source_checksum": "sha256:abc"}), encoding="utf-8")
    manifest = _make_manifest(pipeline_run_id=None, generated_at=None, source_checksum=None)
    pc = _contractor_with(manifest, tmp_path, seed_path=seed)

    pc._write_forward_manifest()

    data = json.loads((tmp_path / ".startd8" / "forward-manifest.json").read_text())
    assert data["source_checksum"] == "sha256:abc"
    assert data["generated_at"]
    assert data["pipeline_run_id"] is None


def test_write_leaves_run_id_and_checksum_null_when_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_kaizen_run_id(monkeypatch)
    manifest = _make_manifest(pipeline_run_id=None, generated_at=None, source_checksum=None)
    pc = _contractor_with(manifest, tmp_path)  # no seed_path

    pc._write_forward_manifest()

    data = json.loads((tmp_path / ".startd8" / "forward-manifest.json").read_text())
    assert data["pipeline_run_id"] is None
    assert data["source_checksum"] is None
    assert data["generated_at"]  # always settable at write (FR-3)


def test_write_does_not_overwrite_existing_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KAIZEN_RUN_ID", "env-should-not-win")
    manifest = _make_manifest(pipeline_run_id="already-set", generated_at=None)
    pc = _contractor_with(manifest, tmp_path)

    pc._write_forward_manifest()

    data = json.loads((tmp_path / ".startd8" / "forward-manifest.json").read_text())
    assert data["pipeline_run_id"] == "already-set"


def test_persisted_file_evidence_for_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_kaizen_run_id(monkeypatch)
    src = tmp_path / "src"
    src.mkdir()
    target = src / "a.py"
    content = b"def a():\n    return 1\n"
    target.write_bytes(content)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "src/a.py"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "a"],
        cwd=tmp_path,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    manifest = _make_manifest(
        pipeline_run_id=None,
        generated_at=None,
        source_checksum=None,
        file_specs={"src/a.py": ForwardFileSpec(file="src/a.py", elements=[])},
    )
    pc = _contractor_with(manifest, tmp_path)
    pc._write_forward_manifest()

    data = json.loads((tmp_path / ".startd8" / "forward-manifest.json").read_text())
    evidence = data["metadata"]["persisted_file_evidence"]
    assert len(evidence) == 1
    row = evidence[0]
    assert row["path"] == "src/a.py"
    assert row["locator"] == f"git:{head}:src/a.py"
    assert row["sha256"] == hashlib.sha256(content).hexdigest()
    assert row["provenance"] == "prime-contractor-persist"


def test_persisted_file_evidence_skips_uncommitted_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_kaizen_run_id(monkeypatch)
    (tmp_path / "src").mkdir()
    committed = tmp_path / "src" / "ok.py"
    committed.write_text("x = 1\n", encoding="utf-8")
    uncommitted = tmp_path / "src" / "wip.py"
    uncommitted.write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "templates").mkdir()

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "src/ok.py"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "ok"],
        cwd=tmp_path,
        check=True,
    )
    # wip.py stays untracked / uncommitted

    manifest = _make_manifest(
        pipeline_run_id=None,
        file_specs={
            "src/ok.py": ForwardFileSpec(file="src/ok.py", elements=[]),
            "src/wip.py": ForwardFileSpec(file="src/wip.py", elements=[]),
            "app/templates/": ForwardFileSpec(file="app/templates/", elements=[]),
        },
    )
    pc = _contractor_with(manifest, tmp_path)
    pc._write_forward_manifest()

    data = json.loads((tmp_path / ".startd8" / "forward-manifest.json").read_text())
    evidence = data["metadata"].get("persisted_file_evidence", [])
    assert [e["path"] for e in evidence] == ["src/ok.py"]


def test_persisted_file_evidence_skips_path_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """file_specs keys that escape project_root must not produce evidence rows."""
    _clear_kaizen_run_id(monkeypatch)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("x=1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "src/ok.py"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "ok"],
        cwd=tmp_path,
        check=True,
    )
    # Outside the repo root
    outside = tmp_path.parent / f"escape-{tmp_path.name}.py"
    outside.write_text("evil=1\n", encoding="utf-8")
    try:
        manifest = _make_manifest(
            pipeline_run_id=None,
            file_specs={
                "src/ok.py": ForwardFileSpec(file="src/ok.py", elements=[]),
                f"../{outside.name}": ForwardFileSpec(file=f"../{outside.name}", elements=[]),
            },
        )
        pc = _contractor_with(manifest, tmp_path)
        pc._write_forward_manifest()
        data = json.loads((tmp_path / ".startd8" / "forward-manifest.json").read_text())
        evidence = data["metadata"].get("persisted_file_evidence", [])
        assert [e["path"] for e in evidence] == ["src/ok.py"]
    finally:
        outside.unlink(missing_ok=True)


def test_null_specimen_is_unknown_provenance() -> None:
    manifest = ForwardManifest.model_validate_json(_NULL_SPECIMEN.read_text(encoding="utf-8"))
    assert provenance_completeness(manifest) == "unknown"


def test_fuelled_manifest_not_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KAIZEN_RUN_ID", "fuel-me")
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"source_checksum": "sha256:deadbeef"}), encoding="utf-8")
    manifest = ForwardManifest.model_validate_json(_NULL_SPECIMEN.read_text(encoding="utf-8"))
    assert provenance_completeness(manifest) == "unknown"

    pc = _contractor_with(manifest, tmp_path, seed_path=seed)
    pc._write_forward_manifest()

    reloaded = ForwardManifest.model_validate_json(
        (tmp_path / ".startd8" / "forward-manifest.json").read_text(encoding="utf-8")
    )
    assert provenance_completeness(reloaded) == "complete"
    assert provenance_completeness(
        ForwardManifest(generated_at="2026-08-13T00:00:00+00:00")
    ) == "partial"


# --- WI-2: post-mortem read side --------------------------------------------


def test_postmortem_loads_persisted_manifest(tmp_path: Path) -> None:
    """The post-mortem disk loader round-trips what the contractor wrote (FR-CL-1)."""
    from startd8.contractors.prime_postmortem import _load_forward_manifest_from_disk

    manifest = _make_manifest()
    (tmp_path / "forward-manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    loaded = _load_forward_manifest_from_disk(str(tmp_path))

    assert loaded is not None
    assert loaded.model_dump() == manifest.model_dump()


def test_postmortem_loader_absent_returns_none(tmp_path: Path) -> None:
    from startd8.contractors.prime_postmortem import _load_forward_manifest_from_disk

    assert _load_forward_manifest_from_disk(str(tmp_path)) is None
