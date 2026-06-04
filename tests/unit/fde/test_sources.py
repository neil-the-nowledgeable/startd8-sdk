# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""sources.py — mechanism reads, the R2-F2 generation_strategy fix, trust gate (FR-18)."""

from __future__ import annotations

import json

import pytest

from startd8.fde import sources
from startd8.fde.models import ClaimLabel


def test_generation_strategy_read_from_raw_not_postmortem(run_dir):
    # R2-F2: generation_strategy is raw-only; the post-mortem ElementPostMortem lacks it.
    claims = sources.read_element_mechanism(run_dir, "PI-001", "resolve_matches")
    texts = [c.text for c in claims]
    sources_cited = [c.source for c in claims]
    assert any("generation strategy was `template`" in t for t in texts)
    assert any("prime-result" in s for s in sources_cited)
    assert all(c.label == ClaimLabel.MECHANISM for c in claims)


def test_tier_and_repair_from_postmortem(run_dir):
    claims = sources.read_element_mechanism(run_dir, "PI-001", "resolve_matches")
    texts = " ".join(c.text for c in claims)
    assert "tier **simple**" in texts
    assert "dedupe_imports" in texts


def test_double_absence_yields_unavailable(tmp_path):
    # FR-18 / R1-F14: neither post-mortem nor raw → labeled "mechanism unavailable", no crash.
    empty = tmp_path / "run-empty"
    empty.mkdir()
    claims = sources.read_element_mechanism(empty, "PI-X")
    assert len(claims) == 1
    assert claims[0].qualifier == "unavailable"
    assert claims[0].label == ClaimLabel.MECHANISM


def test_trust_gate_raises_on_malformed_artifact(tmp_path):
    run = tmp_path / "run-bad"
    run.mkdir()
    (run / "service-assistant-triage.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(sources.ArtifactTrustError):
        sources.read_triage(run)


def test_trust_gate_raises_on_schema_mismatch(tmp_path):
    run = tmp_path / "run-schema"
    run.mkdir()
    (run / "prime-postmortem-report.json").write_text(
        json.dumps({"wrong": "shape"}), encoding="utf-8"
    )
    with pytest.raises(sources.ArtifactTrustError):
        sources.read_postmortem(run)


def test_missing_artifact_is_clean_none(tmp_path):
    run = tmp_path / "run-none"
    run.mkdir()
    assert sources.read_triage(run) is None
    assert sources.read_postmortem(run) is None


def test_classify_live_is_prediction_labeled():
    from startd8.complexity.models import TaskComplexitySignals

    _result, claim = sources.classify_live(
        TaskComplexitySignals(estimated_loc=40, edit_mode="create", target_file_count=1)
    )
    assert claim is not None
    assert claim.label == ClaimLabel.PREDICTION
    assert "classify_tier" in claim.source


def test_language_capability_unsupported_is_unavailable():
    sources.ensure_registries()
    cap = sources.language_capability("rust")
    assert cap.label == ClaimLabel.PREDICTION
    assert cap.qualifier == "unavailable"
