# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-tests-completeness
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.completeness import compute_completeness


def test_completeness_full():
    r = compute_completeness({"PlaceOrderSession": 99})
    assert r.score == 1.0
    assert r.nudges == []


def test_completeness_empty():
    r = compute_completeness({})
    assert r.score == 0.0
    assert len(r.nudges) == 1
