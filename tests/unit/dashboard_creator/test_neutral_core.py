"""Neutral dashboard core and behavior-preserving Grafana lowering contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from startd8.dashboard_creator.neutral import (
    Dashboard,
    DatasourceRef,
    Panel,
    Placement,
    Query,
    QueryLanguage,
    Section,
    VisualizationKind,
)
from startd8.dashboard_creator.v2 import v2_json

pytestmark = pytest.mark.unit

_FIXTURES = Path(__file__).parent / "fixtures"

# The exhaustive pre-extraction byte boundary. The pre_refactor fixture is intentionally included:
# it is historical evidence rather than a current builder output, but its bytes are still immutable.
_V2_GOLDEN_SHA256 = {
    "v2_conditional.golden.json": "b629becb36da0c37a541ec5d7a753fe2a8154775b1cc50eae2afc47c43f97cbf",
    "v2_foundation.golden.json": "a03087e3f58ea85303a30b61fcd72065b5ca7dc8efa2ab34f61aa7b29214b00b",
    "v2_sectioned_fleet.golden.json": "3050cca55822e705a909a551957e9415c05159e0cdb9b1b1c54ace12a3566f9f",
    "v2_sections.golden.json": "f2e2dba4b04742d89bd1a3dc84b152ad1305873fd0905ec64a19405b63fd3d6a",
    "v2_tabs.golden.json": "c844ed075ee5562e657b6a2e3dd1c978195b5350d7735e6cb706e542a1fdecc9",
    "v2_workbook.golden.json": "4192ae8db69a88ee5181a6ca04ffd4a2dde173bbd5988e63a8d422ae5151d863",
    "v2_workbook_status_content.pre_refactor.golden.json": "0702d8eac05abfab3cb8f4d9f9bca195a8b0ccdde004d545b2ed482fdb6c5a8f",
}


def test_every_v2_golden_is_in_the_byte_identity_manifest():
    actual = {p.name for p in _FIXTURES.glob("v2_*.golden.json")}
    assert actual == set(_V2_GOLDEN_SHA256)


@pytest.mark.parametrize("name,expected", sorted(_V2_GOLDEN_SHA256.items()))
def test_v2_golden_bytes_and_canonical_serializer_are_unchanged(name, expected):
    raw = (_FIXTURES / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected
    assert v2_json(json.loads(raw)) == raw.decode("utf-8")


def test_neutral_core_rejects_target_specific_or_mismatched_payloads():
    datasource = DatasourceRef(name="metrics")
    with pytest.raises(ValidationError, match="requires markdown content"):
        Panel(id=1, visualization=VisualizationKind.MARKDOWN)
    with pytest.raises(ValidationError, match="require promql"):
        Panel(
            id=1,
            visualization=VisualizationKind.TIME_SERIES,
            queries=[
                Query(
                    expression='{job="x"}',
                    language=QueryLanguage.LOGQL,
                    datasource=datasource,
                )
            ],
        )
    with pytest.raises(ValidationError, match="undeclared panel"):
        Dashboard(
            name="bad",
            title="bad",
            sections=[Section(placements=[Placement(panel="missing")])],
        )


def test_neutral_models_have_no_grafana_serialization_methods_or_payload_fields():
    panel_fields = set(Panel.model_fields)
    assert "viz_config" not in panel_fields and "data" not in panel_fields
    assert not hasattr(Panel, "to_v2") and not hasattr(Dashboard, "to_v2")
