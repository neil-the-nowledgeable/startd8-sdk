# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-tests-contract
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from pydantic import ValidationError

from app.models import PlaceOrderSessionSchema


def test_placeordersession_roundtrip():
    inst = PlaceOrderSessionSchema(**{"id": "sample", "userId": "sample", "email": "sample", "createdAt": "2020-01-01T00:00:00"})
    assert PlaceOrderSessionSchema.model_validate(inst.model_dump()) == inst


def test_placeordersession_fields():
    f = PlaceOrderSessionSchema.model_fields
    assert 'id' in f and f['id'].is_required()
    assert 'userId' in f and f['userId'].is_required()
    assert 'email' in f and f['email'].is_required()
    assert 'createdAt' in f and f['createdAt'].is_required()
