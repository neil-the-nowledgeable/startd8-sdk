# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: sqlmodel-tables
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _gen_id() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrderConfirmation(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=_gen_id)
    orderId: str
    email: str
    createdAt: datetime = Field(default_factory=_utcnow)


class OrderConfirmationCreate(SQLModel):
    orderId: str
    email: str


class OrderConfirmationRead(SQLModel):
    id: str
    orderId: str
    email: str
    createdAt: datetime


class OrderConfirmationUpdate(SQLModel):
    orderId: Optional[str] = None
    email: Optional[str] = None
    createdAt: Optional[datetime] = None
