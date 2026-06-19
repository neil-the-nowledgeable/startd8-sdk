# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: pydantic-models
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OrderConfirmationSchema(BaseModel):
    id: str
    orderId: str
    email: str
    createdAt: datetime
