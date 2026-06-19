# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: sqlmodel-tables
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _gen_id() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlaceOrderSession(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=_gen_id)
    userId: str
    email: str
    createdAt: datetime = Field(default_factory=_utcnow)


class PlaceOrderSessionCreate(SQLModel):
    userId: str
    email: str


class PlaceOrderSessionRead(SQLModel):
    id: str
    userId: str
    email: str
    createdAt: datetime


class PlaceOrderSessionUpdate(SQLModel):
    userId: Optional[str] = None
    email: Optional[str] = None
    createdAt: Optional[datetime] = None
