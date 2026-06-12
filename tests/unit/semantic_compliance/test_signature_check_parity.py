"""WI-3 / FR-CL-3 (E1) parity gate.

The keystone makes the forward manifest reachable; E1 wants the SCR's missing-symbol
backstop to read symbol names from that structured contract instead of re-parsing
raw ``api_signatures`` with ``_NAME_RE``. This test runs the REAL extractor over
representative signatures and compares the manifest-derived names against the regex
names — empirically establishing exactly where parity holds (functions/classes) and
where it cannot (variables/constants are not tagged as api-sig-sourced; OQ-5).
"""

from __future__ import annotations

from startd8.forward_manifest_extractor import DeterministicExtractor, ParsedFeature
from startd8.semantic_compliance.signature_check import (
    required_symbol_names,
    required_symbol_names_from_contracts,
)


def _extract(api_signatures, feature_id="F-1", target="src/totals.py"):
    feat = ParsedFeature(
        feature_id=feature_id,
        name="t",
        description="",
        target_files=[target],
        dependencies=[],
        estimated_loc=10,
        labels=[],
        design_doc_sections=[],
        artifact_types_addressed=[],
        api_signatures=list(api_signatures),
    )
    contracts, _file_elements = DeterministicExtractor().extract([feat])
    return contracts


def test_parity_holds_for_functions_and_classes() -> None:
    """The manifest's deterministic contracts reproduce the regex names for the
    function/class subset — so E1 can use the contract as the authority there."""
    sigs = [
        "def jobs_dashboard(request) -> Response",
        "async def resolve_matches(seed) -> list",
        "class JobsRouter",
    ]
    contracts = _extract(sigs)

    from_manifest = set(required_symbol_names_from_contracts(contracts, "F-1"))
    from_regex = set(required_symbol_names(sigs))

    assert from_manifest == from_regex == {"jobs_dashboard", "resolve_matches", "JobsRouter"}


def test_variables_are_not_manifest_tagged() -> None:
    """OQ-5: variable/constant api_signatures produce untagged elements with NO
    deterministic contract, so the manifest cannot represent them as required
    symbols. The regex still must cover them — E1 stays narrowed to func/class."""
    sigs = ["router = APIRouter()", "MAX_RETRIES = 3"]
    contracts = _extract(sigs)

    from_manifest = set(required_symbol_names_from_contracts(contracts, "F-1"))
    from_regex = set(required_symbol_names(sigs))

    assert from_manifest == set()  # no func/class contracts for bare assignments
    assert "router" in from_regex and "MAX_RETRIES" in from_regex


def test_contracts_filtered_by_feature() -> None:
    """Names are scoped to the feature (applicable_task_ids), never leaking across."""
    contracts = _extract(["def alpha() -> None"], feature_id="F-1")
    assert required_symbol_names_from_contracts(contracts, "F-1") == ["alpha"]
    assert required_symbol_names_from_contracts(contracts, "F-OTHER") == []
