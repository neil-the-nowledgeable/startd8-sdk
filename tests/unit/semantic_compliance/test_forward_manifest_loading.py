"""WI-2 / FR-CL-1 read side (SCR): the detached reviewer can reach the persisted
forward manifest. Proves OQ-4 reachability — the contract written by the
contractor to the run output dir is loadable next to the seed/post-mortem report.
"""

from __future__ import annotations

from pathlib import Path

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
    ContractCategory,
    ContractConfidence,
)
from startd8.semantic_compliance.requirement_loader import load_forward_manifest
from startd8.utils.code_manifest import ElementKind, Signature


def _manifest() -> ForwardManifest:
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
    return ForwardManifest(
        contracts=[contract],
        file_specs={"src/totals.py": ForwardFileSpec(file="src/totals.py", elements=[element])},
    )


def _write(manifest: ForwardManifest, path: Path) -> None:
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def test_loads_from_output_dir(tmp_path: Path) -> None:
    _write(_manifest(), tmp_path / "forward-manifest.json")

    loaded = load_forward_manifest(tmp_path)

    assert loaded is not None
    assert loaded.contracts[0].binding_text.startswith("[BINDING] function=compute_total")


def test_falls_back_to_seed_dir(tmp_path: Path) -> None:
    """output_dir has no manifest, but it sits next to the seed (OQ-4 fallback)."""
    seed_dir = tmp_path / "run"
    seed_dir.mkdir()
    seed_path = seed_dir / "prime-context-seed.json"
    seed_path.write_text("{}", encoding="utf-8")
    _write(_manifest(), seed_dir / "forward-manifest.json")

    # output_dir distinct from the seed dir, no manifest of its own.
    out = tmp_path / "elsewhere"
    out.mkdir()
    loaded = load_forward_manifest(out, seed_path=seed_path)

    assert loaded is not None
    assert loaded.file_specs["src/totals.py"].elements[0].name == "compute_total"


def test_absent_returns_none(tmp_path: Path) -> None:
    assert load_forward_manifest(tmp_path) is None


def test_unparsable_returns_none(tmp_path: Path) -> None:
    (tmp_path / "forward-manifest.json").write_text("{ not json", encoding="utf-8")
    assert load_forward_manifest(tmp_path) is None
