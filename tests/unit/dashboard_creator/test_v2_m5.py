"""Tests for dynamic-dashboards M5 — schema-aware validation, version gating, provisioning (FR-7/6/11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.dashboard_creator.json_validator import validate_dashboard_json
from startd8.dashboard_creator.v2 import (
    CustomVariable,
    GridItem,
    RowsLayout,
    RowsLayoutRow,
    V2ProvisionResult,
    emit_v2_dashboard,
    parse_version,
    provision_v2,
    supports_v2_dynamic,
    text_panel,
    v2_json,
    validate_v2_dashboard,
    version_gate_reason,
)
from startd8.dashboard_creator.v2 import constructs as C

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_M0_NAMES = _REPO / "docs/design/dynamic-dashboards/m0-spike/v2-construct-names.json"


def _board() -> dict:
    return emit_v2_dashboard(
        name="m5",
        title="M5",
        elements={"p1": text_panel(1, "a", "b")},
        layout=RowsLayout(rows=[RowsLayoutRow(items=[GridItem(element="p1")])]),
    )


# --- FR-7: schema discriminator + v2 validation --------------------------------------------------


def test_discriminator_routes_v2_board_to_v2_validation():
    r = validate_dashboard_json(v2_json(_board()), expected_uid="m5")
    assert r.valid and r.errors == []


def test_classic_validation_unchanged():
    ok = json.dumps(
        {"title": "t", "uid": "u", "panels": [], "templating": {}, "schemaVersion": 39}
    )
    assert validate_dashboard_json(ok, expected_uid="u").valid
    # a classic board missing keys still errors the classic way (not the v2 path)
    bad = validate_dashboard_json(json.dumps({"title": "t"}), expected_uid="u")
    assert not bad.valid and any("Missing required keys" in e for e in bad.errors)


def test_v2_validation_positively_asserts_envelope():
    assert validate_v2_dashboard(_board()) == []
    assert any(
        "apiVersion" in e
        for e in validate_v2_dashboard({"kind": "Dashboard", "spec": {}})
    )
    assert any(
        "object 'spec'" in e
        for e in validate_v2_dashboard(
            {"apiVersion": C.V2_API_VERSION, "kind": "Dashboard"}
        )
    )


def test_v2_uid_via_metadata_name_not_top_level():
    assert any(
        "UID mismatch" in e
        for e in validate_v2_dashboard(_board(), expected_uid="WRONG")
    )
    assert validate_v2_dashboard(_board(), expected_uid="m5") == []


def test_nr6_rejects_out_of_scope_layout_and_variable():
    b = json.loads(v2_json(_board()))
    b["spec"]["layout"]["kind"] = "MasonryLayout"
    assert any("MasonryLayout" in e for e in validate_v2_dashboard(b))
    b2 = json.loads(v2_json(_board()))
    b2["spec"]["variables"] = [{"kind": "QueryVariable", "spec": {"name": "q"}}]
    assert any("QueryVariable" in e and "NR-6" in e for e in validate_v2_dashboard(b2))


def test_construct_allowlists_match_m0_doc():
    # the in-code allowlist (constructs.py) must not drift from the M0-verified doc
    doc = json.loads(_M0_NAMES.read_text(encoding="utf-8"))
    assert set(doc["layout_kinds"]) == set(C.LAYOUT_KINDS)
    assert set(doc["variable_kinds"]) >= set(C.VARIABLE_KINDS)
    cond = {
        doc["conditional_rendering"]["group"],
        *doc["conditional_rendering"]["conditions"],
    }
    assert cond == set(C.CONDITION_KINDS)


# --- FR-11: version gating (minor-aware) ---------------------------------------------------------


@pytest.mark.parametrize(
    "ver,ok",
    [
        ("13.1.0", True),
        ("13.1.2", True),
        ("v14.0", True),
        ("13.0.9", False),
        ("12.5.0", False),
        ("bogus", False),
    ],
)
def test_supports_v2_dynamic(ver, ok):
    assert supports_v2_dynamic(ver) is ok


def test_parse_version():
    assert parse_version("13.1.0") == (13, 1, 0)
    assert parse_version("v13.1") == (13, 1, 0)
    assert parse_version("nope") is None


def test_version_gate_reason():
    assert version_gate_reason("13.1.0") is None
    assert "13.1" in version_gate_reason("13.0.0")


# --- FR-6: provisioning (version gate + collision guard + idempotent upsert) ----------------------


class _Resp:
    def __init__(self, success, data=None, error=None):
        self.success, self.data, self.error = success, data or {}, error


class _MockClient:
    def __init__(self, ver="13.1.0", existing=None):
        self.ver, self.existing, self.upserted = ver, existing, False

    def check_version(self):
        return _Resp(True, {"version": self.ver})

    def get_dashboard(self, uid):
        return _Resp(
            bool(self.existing), {"dashboard": self.existing} if self.existing else {}
        )

    def upsert_dashboard(self, b):
        self.upserted = True
        return _Resp(True, {"uid": b["metadata"]["name"]})


def test_provision_refuses_below_13_1():
    c = _MockClient(ver="13.0.9")
    res = provision_v2(c, _board())
    assert not res.success and "13.1" in res.skipped_reason and not c.upserted


def test_provision_success_records_endpoint():
    c = _MockClient(ver="13.1.0")
    res = provision_v2(c, _board())
    assert res.success and res.provision_api == "/api/dashboards/db" and c.upserted


def test_provision_idempotent_for_same_title():
    # UID exists with the SAME title (our own board) → re-provisions cleanly (no false collision)
    c = _MockClient(existing={"title": "M5"})
    res = provision_v2(c, _board())
    assert res.success and c.upserted


def test_provision_refuses_different_titled_uid_collision():
    c = _MockClient(existing={"title": "Someone Else", "schemaVersion": 39})
    res = provision_v2(c, _board())
    assert (
        not res.success
        and "different dashboard" in res.skipped_reason
        and not c.upserted
    )


def test_provision_force_overrides_collision():
    c = _MockClient(existing={"title": "Someone Else"})
    res = provision_v2(c, _board(), force=True)
    assert res.success and c.upserted


def test_provision_no_name_fails():
    res = provision_v2(
        _MockClient(), {"apiVersion": "dashboard.grafana.app/v2", "spec": {}}
    )
    assert not res.success and "metadata.name" in res.skipped_reason


def test_provision_version_unverifiable_degrades():
    class _C(_MockClient):
        def check_version(self):
            return _Resp(False, error="boom")

    res = provision_v2(_C(), _board())
    assert not res.success and "cannot verify" in res.skipped_reason
