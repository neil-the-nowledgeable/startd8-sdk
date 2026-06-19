"""Unit tests for the run-comparison classifier (scripts/compare_runs.py)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from compare_runs import classify  # noqa: E402


def s(func, reason=None):
    return {"func": func, "reason": reason}


def test_single_sample_is_inconclusive():
    assert classify([s(1.0)])[0] == "SCORED"
    assert classify([s(None, "never ready")])[0] == "DEGRADE"


def test_stable_when_samples_agree():
    assert classify([s(1.0), s(1.0)])[0] == "STABLE"


def test_repeated_degrade_same_reason():
    assert classify([s(None, "rc=1 uvicorn"), s(None, "rc=1 uvicorn")])[0] == "CONSISTENT-DEGRADE"


def test_degrade_differing_reasons():
    assert classify([s(None, "never ready"), s(None, "rc=1")])[0] == "VARIANT-DEGRADE"


def test_flip_scored_vs_degraded():
    assert classify([s(1.0), s(None, "rc=1")])[0] == "VARIANT"


def test_flip_differing_scores():
    assert classify([s(1.0), s(0.47)])[0] == "VARIANT"
