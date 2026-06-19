# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-tests-contract
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from pydantic import ValidationError

from app.models import OrderConfirmationSchema


def test_orderconfirmation_roundtrip():
    inst = OrderConfirmationSchema(**{"id": "sample", "orderId": "sample", "email": "sample", "createdAt": "2020-01-01T00:00:00"})
    assert OrderConfirmationSchema.model_validate(inst.model_dump()) == inst


def test_orderconfirmation_fields():
    f = OrderConfirmationSchema.model_fields
    assert 'id' in f and f['id'].is_required()
    assert 'orderId' in f and f['orderId'].is_required()
    assert 'email' in f and f['email'].is_required()
    assert 'createdAt' in f and f['createdAt'].is_required()
