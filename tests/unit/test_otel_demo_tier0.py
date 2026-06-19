"""Unit tests for Tier 0 OTel Demo coverage helpers (no live backends)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.otel_demo.adapters.collector import _parse_yaml_receivers
from scripts.otel_demo.coverage_sections import (
    default_sections,
    validate_schema_version,
)


@pytest.mark.unit
def test_validate_schema_version_accepts_current() -> None:
    validate_schema_version("1.0")


@pytest.mark.unit
def test_validate_schema_version_rejects_unknown_major() -> None:
    with pytest.raises(ValueError, match="unsupported schema_version major"):
        validate_schema_version("2.0")


@pytest.mark.unit
def test_default_sections_count_observe_tier() -> None:
    sections = default_sections(include_profiles=False)
    assert len(sections) == 9
    ids = {s.section_id for s in sections}
    assert "5.4-messaging" in ids
    assert "2-profiles" not in ids


@pytest.mark.unit
def test_default_sections_profile_tier_adds_profiles() -> None:
    sections = default_sections(include_profiles=True)
    assert any(s.section_id == "2-profiles" for s in sections)


@pytest.mark.unit
def test_parse_otlp_receivers_minimal_yaml() -> None:
    yaml_text = """
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
exporters:
  debug:
"""
    found = _parse_yaml_receivers(yaml_text)
    assert "grpc" in found
    assert "http" in found
