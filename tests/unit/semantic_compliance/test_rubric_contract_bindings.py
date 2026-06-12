"""WI-4 / FR-CL-2 (E2): the LLM rubric validates against the forward-manifest
contract bindings (binding_text), not raw api_signatures prose. The Run-029
missing-symbol guarantee is held by the deterministic backstop (WI-3) regardless
of the rubric; these gates cover the prompt content, the feature-scoped binding
extraction, and graceful fallback when no manifest is present.
"""

from __future__ import annotations

from startd8.forward_manifest import (
    ForwardManifest,
    InterfaceContract,
    ContractCategory,
    ContractConfidence,
)
from startd8.semantic_compliance.prompts import render_rubric
from startd8.semantic_compliance.reviewer import contract_bindings_for_feature


def _contract(**ov) -> InterfaceContract:
    d = dict(
        contract_id="C-1",
        category=ContractCategory.FUNCTION_NAME,
        confidence=ContractConfidence.INFERRED,
        description="Function compute_total from API signature",
        binding_text="[BINDING] function=compute_total(items) -> int",
        function_name="compute_total",
        source_reference="deterministic",
        applicable_task_ids=["F-1"],
    )
    d.update(ov)
    return InterfaceContract(**d)


def _render(contract_bindings):
    return render_rubric(
        feature_id="F-1",
        element_fqn="src/totals.py",
        language="python",
        seed_task_id="F-1",
        requirement_text="Compute the order total.",
        api_signatures=["def compute_total(items) -> int"],
        negative_scope=[],
        generated_code="def compute_total(items): return sum(items)",
        contract_bindings=contract_bindings,
    )


def test_rubric_uses_bindings_when_present() -> None:
    prompt = _render(["[BINDING] function=compute_total(items) -> int"])
    assert "INTERFACE CONTRACT BINDINGS" in prompt
    assert "[BINDING] function=compute_total(items) -> int" in prompt
    # Raw api_signatures prose round-trip is dropped (FR-CL-3b spirit).
    assert "API SIGNATURES:" not in prompt


def test_rubric_falls_back_to_api_signatures_without_manifest() -> None:
    prompt = _render(None)
    assert "API SIGNATURES:" in prompt
    assert "def compute_total(items) -> int" in prompt
    assert "INTERFACE CONTRACT BINDINGS" not in prompt


def test_bindings_scoped_to_feature() -> None:
    manifest = ForwardManifest(
        contracts=[
            _contract(),
            _contract(
                contract_id="C-2",
                binding_text="[BINDING] function=other()",
                function_name="other",
                applicable_task_ids=["F-2"],
            ),
        ]
    )
    got = contract_bindings_for_feature(manifest.contracts, "F-1")
    assert got == ["[BINDING] function=compute_total(items) -> int"]


def test_bindings_empty_without_contracts() -> None:
    assert contract_bindings_for_feature(None, "F-1") == []
    # Non-deterministic contracts are ignored (only api-sig-derived bindings).
    c = _contract(source_reference="design-doc")
    assert contract_bindings_for_feature([c], "F-1") == []
