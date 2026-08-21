"""Live Perses generation: observability.yaml → neutral model → validated resource."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
import yaml

from startd8.dashboard_creator.perses import emitter
from startd8.dashboard_creator.perses import live_generation

_REPO = Path(__file__).resolve().parents[3]
_PILOT = _REPO / "docs/design/dashboard-vendor-neutrality/pilot"


def _cue_binary():
    return os.environ.get("STARTD8_CUE_BINARY") or shutil.which("cue")


def _source(tmp_path):
    path = tmp_path / "observability.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "domain": "observability",
                "alerting": {
                    "metric_thresholds": {
                        "requests_total": {
                            "op": ">",
                            "value": 10,
                            "severity": "critical",
                            "unit": "count",
                        },
                        "latency_seconds": {
                            "op": ">",
                            "value": 1,
                            "severity": "critical",
                            "unit": "seconds",
                        },
                        "error_ratio": {
                            "op": ">",
                            "value": 0.01,
                            "severity": "warning",
                            "unit": "percentunit",
                        },
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def validated_emitter(monkeypatch):
    calls = []

    def emit(dashboard, *, project, validate):
        calls.append({"project": project, "validate": validate})
        return emitter.emit_perses_dashboard(
            dashboard, project=project, validate=False
        )

    monkeypatch.setattr(live_generation, "emit_perses_dashboard", emit)
    return calls


def test_writes_canonical_validated_perses_artifact(
    tmp_path, validated_emitter
):
    output = tmp_path / "out"
    result = live_generation.generate_domain_perses_dashboard(
        _source(tmp_path), project="dash0-pilot", output_dir=output
    )

    assert validated_emitter == [{"project": "dash0-pilot", "validate": True}]
    assert result.output_path == output / "obs-domain-dash0-pilot-v2.perses.json"
    assert result.output_path.read_text(encoding="utf-8") == result.json_text
    assert result.json_text == json.dumps(
        result.dashboard, sort_keys=True, indent=2
    ) + "\n"
    assert result.dashboard["metadata"] == {
        "name": "obs-domain-dash0-pilot-v2",
        "project": "dash0-pilot",
        "tags": ["observability", "domain", "dynamic"],
    }
    critical_items = result.dashboard["spec"]["layouts"][0]["spec"]["items"]
    assert [item["y"] for item in critical_items] == [0, 6]
    first_query = result.dashboard["spec"]["panels"]["sec0-p0"]["spec"]["queries"][0]
    assert first_query["spec"]["plugin"]["spec"]["datasource"] == {
        "kind": "PrometheusDatasource",
        "name": "default",
    }
    assert not list(output.glob("*.tmp"))


@pytest.mark.parametrize("mode", ["check", "dry_run"])
def test_no_write_modes_still_validate(tmp_path, validated_emitter, mode):
    output = tmp_path / "out"
    kwargs = {mode: True}
    result = live_generation.generate_domain_perses_dashboard(
        _source(tmp_path), project="pilot", output_dir=output, **kwargs
    )

    assert validated_emitter == [{"project": "pilot", "validate": True}]
    assert result.output_path is None
    assert not output.exists()


def test_check_and_dry_run_are_mutually_exclusive(tmp_path):
    with pytest.raises(ValueError, match="both --dry-run and --check"):
        live_generation.generate_domain_perses_dashboard(
            _source(tmp_path), check=True, dry_run=True
        )


@pytest.mark.parametrize("project", ["Upper", "has spaces", "path/escape", "-leading"])
def test_project_must_be_a_safe_identifier(tmp_path, project):
    with pytest.raises(ValueError, match="lowercase identifier"):
        live_generation.generate_domain_perses_dashboard(
            _source(tmp_path), project=project
        )


def test_malformed_observability_input_fails_before_emission(
    tmp_path, validated_emitter
):
    source = tmp_path / "observability.yaml"
    source.write_text("alerting: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="alerting.*mapping"):
        live_generation.generate_domain_perses_dashboard(source)
    assert validated_emitter == []


@pytest.mark.skipif(not _cue_binary(), reason="CUE CLI not installed")
def test_pilot_artifact_regenerates_byte_identically_and_validates():
    result = live_generation.generate_domain_perses_dashboard(
        _PILOT / "dash0-pilot.observability.yaml",
        project="dash0-pilot",
        check=True,
    )
    golden = _PILOT / "obs-domain-dash0-pilot-v2.perses.json"
    assert result.json_text == golden.read_text(encoding="utf-8")
