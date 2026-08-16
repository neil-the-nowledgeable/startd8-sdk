"""REQ-16 FR-3 — status-derivation agreement (SDK-side) + a portable cross-repo contract.

A shared fixture set runs through the SDK's two status/gap classifiers — ``models.derive_status``
(NodeStatus) and det_req's ``fr_health`` gap classifier — asserting each fixture yields the SAME
gap-class across both. The fixtures are exported as ``fixtures/status_contract.json``: a self-contained
data file (no SDK import) that the cross-repo twins (``extract.py``, ``req-health.mjs``) can adopt by
running the same inputs through their own classifiers and checking the recorded native output + gap_class.
"""

from __future__ import annotations

import json
from pathlib import Path

from startd8.navigator.det_req import fr_health
from startd8.navigator.models import (
    GAP_CLASSES,
    derive_status,
    health_gap_class,
    node_field_names,  # noqa: F401  (import proves the classifiers live in the SDK model layer)
    status_gap_class,
)

CONTRACT = Path(__file__).parent / "fixtures" / "status_contract.json"


def _load():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_every_fixture_agrees_across_the_two_sdk_classifiers():
    """FR-3: each fixture yields the same gap-class through derive_status AND fr_health."""
    doc = _load()
    assert doc["fixtures"], "the contract has no fixtures"
    for fx in doc["fixtures"]:
        want = fx["gap_class"]
        # derive_status arm
        status = derive_status(**fx["derive_status"]["input"])
        assert status == fx["derive_status"]["expect"], f"{fx['id']}: derive_status native mismatch"
        assert status_gap_class(status) == want, f"{fx['id']}: derive_status gap-class != {want}"
        # fr_health arm
        health = fr_health(fx["fr_health"]["input"])
        assert health == fx["fr_health"]["expect"], f"{fx['id']}: fr_health native mismatch"
        assert health_gap_class(health) == want, f"{fx['id']}: fr_health gap-class != {want}"
        # the two agree
        assert status_gap_class(status) == health_gap_class(health), f"{fx['id']}: classifiers disagree"


def test_gap_class_maps_in_contract_match_the_sdk_normalizers():
    """FR-3: the maps embedded in the portable contract match the SDK normalizers (so a foreign impl
    that trusts the file agrees with the SDK)."""
    doc = _load()
    for status, gap in doc["status_to_gap"].items():
        assert status_gap_class(status) == gap
    for health, gap in doc["health_to_gap"].items():
        assert health_gap_class(health) == gap
    assert set(doc["gap_classes"]) <= set(GAP_CLASSES)


def test_contract_is_self_contained_and_portable():
    """FR-3: the exported file is loadable, carries native inputs + expected outputs + the normalization
    maps — everything a second implementation needs, with NO SDK import."""
    doc = _load()
    for key in ("status_to_gap", "health_to_gap", "gap_classes", "fixtures"):
        assert key in doc, f"portable contract missing {key!r}"
    for fx in doc["fixtures"]:
        assert {"id", "gap_class"} <= set(fx)
        for arm in ("derive_status", "fr_health"):
            assert "input" in fx[arm] and "expect" in fx[arm], f"{fx['id']} {arm} missing input/expect"
    # portability guard: the file text carries no SDK import token a foreign runner would choke on.
    assert "import startd8" not in CONTRACT.read_text(encoding="utf-8")
