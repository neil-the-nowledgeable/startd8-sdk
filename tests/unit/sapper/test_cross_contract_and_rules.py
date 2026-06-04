"""Phase 3 — cross-contract (FR-SAP-5) + per-element rules (FR-SAP-6)."""

from __future__ import annotations

import pytest

from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.sapper.cross_contract import run_cross_contract
from startd8.sapper.models import AssumptionKind, AssumptionVerdict
from startd8.sapper.rules_sapper import run_per_element_rules
from startd8.utils.code_manifest import ElementKind

pytestmark = pytest.mark.unit


def _endpoint(cid, schema, tasks=None):
    return InterfaceContract(
        contract_id=cid,
        category=ContractCategory.API_ENDPOINT,
        confidence=ContractConfidence.EXPLICIT,
        description="d",
        binding_text="b",
        endpoint="/jobs",
        response_schema=schema,
        applicable_task_ids=tasks or [],
    )


# --- cross-contract (FR-SAP-5) ------------------------------------------------


def test_contradictory_endpoint_schemas_refuted():
    m = ForwardManifest(
        contracts=[
            _endpoint("c1", {"id": "str"}),
            _endpoint("c2", {"id": "int"}),  # same endpoint, conflicting response schema
        ]
    )
    findings = run_cross_contract(m)
    assert len(findings) == 1
    assert findings[0].verdict is AssumptionVerdict.REFUTED
    assert findings[0].kind is AssumptionKind.INTERFACE_SIGNATURE


def test_versioned_endpoints_not_flagged():
    # Distinct endpoints (different resolved identity) never collide (R2-F2).
    c1 = _endpoint("c1", {"id": "str"})
    c2 = InterfaceContract(
        contract_id="c2",
        category=ContractCategory.API_ENDPOINT,
        confidence=ContractConfidence.EXPLICIT,
        description="d",
        binding_text="b",
        endpoint="/v2/jobs",
        response_schema={"id": "int"},
    )
    assert run_cross_contract(ForwardManifest(contracts=[c1, c2])) == []


def test_disjoint_task_scopes_not_flagged():
    m = ForwardManifest(
        contracts=[
            _endpoint("c1", {"id": "str"}, tasks=["T1"]),
            _endpoint("c2", {"id": "int"}, tasks=["T2"]),  # different tasks → not compared
        ]
    )
    assert run_cross_contract(m) == []


def test_agreeing_contracts_no_finding():
    m = ForwardManifest(contracts=[_endpoint("c1", {"id": "str"}), _endpoint("c2", {"id": "str"})])
    assert run_cross_contract(m) == []


# --- per-element rules (FR-SAP-6) ---------------------------------------------


def test_empty_type_only_file_is_refuted_unbuildable():
    m = ForwardManifest(
        file_specs={
            "app/empty.py": ForwardFileSpec(
                file="app/empty.py",
                elements=[ForwardElementSpec(kind=ElementKind.CLASS, name="Empty")],
            )
        }
    )
    findings = run_per_element_rules(m)
    assert any(
        f.kind is AssumptionKind.DECOMPOSITION_INTEGRITY and f.verdict is AssumptionVerdict.REFUTED
        for f in findings
    )


def test_reserved_metadata_name_refuted():
    m = ForwardManifest(
        file_specs={
            "app/tables.py": ForwardFileSpec(
                file="app/tables.py",
                elements=[
                    ForwardElementSpec(kind=ElementKind.CLASS, name="Job"),
                    ForwardElementSpec(
                        kind=ElementKind.VARIABLE,
                        name="metadata",
                        parent_class="Job",
                        type_annotation="str",
                    ),
                ],
            )
        }
    )
    findings = run_per_element_rules(m)
    ids = [f for f in findings if f.kind is AssumptionKind.IDENTITY_COLLISION]
    assert ids and "metadata" in ids[0].found


def test_override_tolerated():
    m = ForwardManifest(
        file_specs={
            "app/tables.py": ForwardFileSpec(
                file="app/tables.py",
                elements=[
                    ForwardElementSpec(kind=ElementKind.CLASS, name="Job"),
                    ForwardElementSpec(
                        kind=ElementKind.VARIABLE,
                        name="metadata",
                        parent_class="Job",
                        type_annotation="str",
                        decorators=["override"],
                    ),
                ],
            )
        }
    )
    findings = [f for f in run_per_element_rules(m) if f.kind is AssumptionKind.IDENTITY_COLLISION]
    assert findings == [], "an explicit @override must not be flagged (R3-F5)"
