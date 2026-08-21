"""Perses lowering, pinned CUE oracle, and dual-target golden contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.dashboard_creator.neutral import (
    Dashboard,
    DatasourceRef,
    Panel,
    Placement,
    Query,
    QueryLanguage,
    Section,
    StaticListVariable,
    Threshold,
    VisualizationKind,
)
from startd8.dashboard_creator.perses import (
    PersesCapabilityError,
    PersesValidationError,
    PersesValidationUnavailable,
    emit_perses_dashboard,
    perses_json,
    validate_perses_dashboard,
)
from startd8.dashboard_creator.v2 import lower_dashboard_to_grafana_v2, v2_json

pytestmark = pytest.mark.unit

_FIXTURES = Path(__file__).parent / "fixtures"
_GRAFANA_GOLDEN = _FIXTURES / "portable_shared.grafana.golden.json"
_PERSES_GOLDEN = _FIXTURES / "portable_shared.perses.golden.json"
_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "src/startd8/dashboard_creator/perses/schema"
)


def _cue_binary():
    return os.environ.get("STARTD8_CUE_BINARY") or shutil.which("cue")


def _portable_dashboard() -> Dashboard:
    return Dashboard(
        name="portable-reference",
        title="Portable reference",
        description="One neutral model lowered to Grafana v2 and Perses.",
        tags=["portable", "golden"],
        variables=[
            StaticListVariable(name="environment", values=["prod", "staging"])
        ],
        panels={
            "intro": Panel(
                id=1,
                title="Overview",
                visualization=VisualizationKind.MARKDOWN,
                markdown="**Portable** dashboard",
            ),
            "rate": Panel(
                id=2,
                title="Request rate",
                visualization=VisualizationKind.TIME_SERIES,
                unit="count",
                thresholds=[
                    Threshold(value=None, color="green"),
                    Threshold(value=10, color="red"),
                ],
                queries=[
                    Query(
                        expression='sum(rate(http_requests_total{env="$environment"}[5m]))',
                        language=QueryLanguage.PROMQL,
                        datasource=DatasourceRef(name="$datasource"),
                    )
                ],
            ),
            "logs": Panel(
                id=3,
                title="Errors",
                visualization=VisualizationKind.LOGS,
                queries=[
                    Query(
                        expression='{app="api"} |= "error"',
                        language=QueryLanguage.LOGQL,
                        datasource=DatasourceRef(name="loki"),
                    )
                ],
            ),
        },
        sections=[
            Section(
                title="Introduction",
                placements=[Placement(panel="intro", height=4)],
            ),
            Section(
                title="Signals",
                placements=[
                    Placement(panel="rate", width=12, height=8),
                    Placement(panel="logs", x=12, width=12, height=8),
                ],
            ),
        ],
    )


def test_one_neutral_fixture_matches_both_target_goldens():
    neutral = _portable_dashboard()
    grafana = lower_dashboard_to_grafana_v2(neutral)
    perses = emit_perses_dashboard(neutral, project="startd8", validate=False)
    assert v2_json(grafana) == _GRAFANA_GOLDEN.read_text(encoding="utf-8")
    assert perses_json(perses) == _PERSES_GOLDEN.read_text(encoding="utf-8")


def test_perses_emission_is_deterministic():
    neutral = _portable_dashboard()
    first = emit_perses_dashboard(neutral, project="startd8", validate=False)
    second = emit_perses_dashboard(neutral, project="startd8", validate=False)
    assert perses_json(first) == perses_json(second)


def test_partial_mappings_fail_loudly():
    dashboard = _portable_dashboard()
    dashboard.panels["rate"].unit = "frobnitz"
    with pytest.raises(PersesCapabilityError, match="no reviewed Perses mapping"):
        emit_perses_dashboard(dashboard, validate=False)

    dashboard = _portable_dashboard()
    dashboard.panels["rate"].queries[0].instant = True
    with pytest.raises(PersesCapabilityError, match="instant queries"):
        emit_perses_dashboard(dashboard, validate=False)

    dashboard = _portable_dashboard()
    dashboard.variables[0].current = "staging"
    with pytest.raises(PersesCapabilityError, match="defaultValue"):
        emit_perses_dashboard(dashboard, validate=False)


def test_validation_is_mandatory_by_default_and_never_silently_skipped(monkeypatch):
    monkeypatch.delenv("STARTD8_CUE_BINARY", raising=False)
    with patch(
        "startd8.dashboard_creator.perses.validate.shutil.which", return_value=None
    ):
        with pytest.raises(PersesValidationUnavailable, match="requires the CUE CLI"):
            emit_perses_dashboard(_portable_dashboard())


def test_validation_honors_explicit_cue_environment_path(monkeypatch):
    monkeypatch.setenv("STARTD8_CUE_BINARY", "/tools/cue-v0.16.1")
    monkeypatch.setattr(
        "startd8.dashboard_creator.perses.validate.shutil.which", lambda _name: None
    )
    completed = MagicMock(returncode=0, stdout="", stderr="")
    with patch(
        "startd8.dashboard_creator.perses.validate.subprocess.run",
        return_value=completed,
    ) as run:
        validate_perses_dashboard(
            emit_perses_dashboard(_portable_dashboard(), validate=False)
        )
    assert run.call_args.args[0][0] == "/tools/cue-v0.16.1"


@pytest.mark.skipif(not _cue_binary(), reason="CUE CLI not installed")
def test_real_pinned_cue_oracle_accepts_the_portable_golden():
    emitted = emit_perses_dashboard(
        _portable_dashboard(),
        project="startd8",
        cue_binary=_cue_binary(),
    )
    assert emitted["kind"] == "Dashboard"


@pytest.mark.skipif(not _cue_binary(), reason="CUE CLI not installed")
def test_real_pinned_cue_oracle_rejects_invalid_plugin_data():
    emitted = emit_perses_dashboard(
        _portable_dashboard(), project="startd8", validate=False
    )
    broken = copy.deepcopy(emitted)
    broken["spec"]["panels"]["rate"]["spec"]["plugin"]["spec"]["thresholds"][
        "steps"
    ][0]["value"] = "not-a-number"
    with pytest.raises(PersesValidationError, match="failed pinned Perses"):
        validate_perses_dashboard(broken, cue_binary=_cue_binary())


def test_vendored_cue_tree_matches_the_pin_manifest():
    pins = json.loads((_SCHEMA / "SCHEMA-PINS.json").read_text(encoding="utf-8"))
    lines = []
    for path in sorted((_SCHEMA / "cue.mod/pkg").rglob("*.cue")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(_SCHEMA)}\n")
    tree_digest = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    assert tree_digest == pins["vendored_cue_tree_sha256"]
