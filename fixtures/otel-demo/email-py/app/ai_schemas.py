# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-ai-schemas
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

from __future__ import annotations

from typing import Any, Dict, Type

from pydantic import BaseModel

from .models import OrderConfirmationSchema


AI_SCHEMAS: Dict[str, Type[BaseModel]] = {
    'OrderConfirmation': OrderConfirmationSchema,
}


def json_schema(entity: str) -> Dict[str, Any]:
    """The JSON Schema an AI pass targets for structured output of *entity*."""
    return AI_SCHEMAS[entity].model_json_schema()
