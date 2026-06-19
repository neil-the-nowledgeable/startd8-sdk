# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-ai-schemas
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

from __future__ import annotations

from typing import Any, Dict, Type

from pydantic import BaseModel

from .models import PlaceOrderSessionSchema


AI_SCHEMAS: Dict[str, Type[BaseModel]] = {
    'PlaceOrderSession': PlaceOrderSessionSchema,
}


def json_schema(entity: str) -> Dict[str, Any]:
    """The JSON Schema an AI pass targets for structured output of *entity*."""
    return AI_SCHEMAS[entity].model_json_schema()
