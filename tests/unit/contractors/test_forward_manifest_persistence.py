"""WI-1 / FR-CL-1 (keystone): persist the forward manifest to the run dir.

The forward manifest is the single canonical interface contract the generator was
bound to. Persisting it (``forward-manifest.json``) makes it reachable to the
post-mortem and the *detached* Semantic Compliance Reviewer, which otherwise
re-derive intent from raw ``api_signatures`` prose (the generation↔validation
asymmetry). These tests pin the write behaviour and the clean Pydantic round-trip
that makes the read side (WI-2) trivial.
"""

from __future__ import annotations

from pathlib import Path

from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.forward_manifest import ContractCategory, ContractConfidence
from startd8.utils.code_manifest import ElementKind, Signature


def _make_manifest() -> ForwardManifest:
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
    return ForwardManifest(
        pipeline_run_id="run-001",
        contracts=[contract],
        file_specs={"src/totals.py": file_spec},
        stages_completed=["DESIGN"],
    )


def _contractor_with(manifest, project_root: Path) -> PrimeContractorWorkflow:
    """Build a bare PrimeContractor wired only with what the writer needs.

    Avoids the heavy __init__ (queue/engine/agents) — ``_write_forward_manifest``
    depends solely on ``self._forward_manifest`` and ``self.project_root``.
    """
    pc = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
    pc._forward_manifest = manifest
    pc.project_root = project_root
    return pc


def test_forward_manifest_path_is_in_dot_startd8(tmp_path: Path) -> None:
    pc = _contractor_with(None, tmp_path)
    assert pc._forward_manifest_path() == tmp_path / ".startd8" / "forward-manifest.json"


def test_write_forward_manifest_round_trips(tmp_path: Path) -> None:
    manifest = _make_manifest()
    pc = _contractor_with(manifest, tmp_path)

    pc._write_forward_manifest()

    path = tmp_path / ".startd8" / "forward-manifest.json"
    assert path.exists(), "forward-manifest.json must be persisted"

    # Clean Pydantic round-trip (OQ-3): reload and compare by serialized form.
    reloaded = ForwardManifest.model_validate_json(path.read_text(encoding="utf-8"))
    assert reloaded.model_dump() == manifest.model_dump()
    # The api-sig-sourced element survives so E1/E2 can read names from it.
    assert reloaded.contracts[0].function_name == "compute_total"
    assert reloaded.file_specs["src/totals.py"].elements[0].source_contract_id == "C-001"


def test_write_forward_manifest_noop_when_absent(tmp_path: Path) -> None:
    """No seed manifest -> nothing written, no crash (FR-CC-1 degrade ethos)."""
    pc = _contractor_with(None, tmp_path)

    pc._write_forward_manifest()

    assert not (tmp_path / ".startd8" / "forward-manifest.json").exists()


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
