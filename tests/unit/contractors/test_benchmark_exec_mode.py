"""M1 — benchmark / LLM-maximize execution mode (FR-1/FR-2/FR-27, R1-S4).

Verifies the Phase-0 deterministic shortcut off-switch: in benchmark mode every
deterministic shortcut is bypassed (so the LLM does the work) and the skip counter
stays 0; in normal mode shortcuts fire and the counter records them.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.contractors.queue import FeatureSpec


@pytest.fixture()
def feature() -> FeatureSpec:
    return FeatureSpec(id="f1", name="svc", description="d", target_files=["a.py"])


@pytest.fixture()
def project_root():
    return Path(tempfile.mkdtemp())


def _fires(_feature):
    """A stand-in shortcut that always 'fires' (would skip the LLM)."""
    return True


def test_normal_mode_shortcut_fires_and_counts(project_root, feature):
    wf = PrimeContractorWorkflow(project_root=project_root)
    assert wf.skip_deterministic_shortcut is False
    assert wf._run_shortcut("copy", _fires, feature) is True
    assert wf.deterministic_skip_count == 1


def test_benchmark_kwarg_bypasses_shortcut(project_root, feature):
    wf = PrimeContractorWorkflow(project_root=project_root, skip_deterministic_shortcut=True)
    assert wf.skip_deterministic_shortcut is True
    # Shortcut is bypassed (returns None → LLM path runs) and nothing is counted.
    assert wf._run_shortcut("copy", _fires, feature) is None
    assert wf._run_shortcut("corpus", _fires, feature) is None
    assert wf.deterministic_skip_count == 0


def test_benchmark_env_var_sets_flag(project_root, monkeypatch):
    monkeypatch.setenv("STARTD8_LLM_MAXIMIZE", "1")
    wf = PrimeContractorWorkflow(project_root=project_root)
    assert wf.skip_deterministic_shortcut is True


@pytest.mark.parametrize("val,expected", [("0", False), ("", False), ("true", True), ("on", True), ("YES", True)])
def test_env_var_truthiness(project_root, monkeypatch, val, expected):
    monkeypatch.setenv("STARTD8_LLM_MAXIMIZE", val)
    wf = PrimeContractorWorkflow(project_root=project_root)
    assert wf.skip_deterministic_shortcut is expected
