# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: pydantic-models
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PlaceOrderSessionSchema(BaseModel):
    id: str
    userId: str
    email: str
    createdAt: datetime
