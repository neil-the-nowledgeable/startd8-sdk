# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-tests-completeness
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.completeness import compute_completeness


def test_completeness_full():
    r = compute_completeness({"OrderConfirmation": 99})
    assert r.score == 1.0
    assert r.nudges == []


def test_completeness_empty():
    r = compute_completeness({})
    assert r.score == 0.0
    assert len(r.nudges) == 1
