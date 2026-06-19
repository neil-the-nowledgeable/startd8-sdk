"""Cross-context smoke via generated consumer clients (OpenAPI Role 3 — M2 / FR-6).

Reuses :func:`startd8.openapi_contract.schema_resolve.select_crud_resource` and
:func:`synthesize_body` to pick an FK-free list+create collection, then executes the round-trip
through a generated ``clients/{id}_client.py`` (``list_*`` + ``create_*`` methods) instead of raw
urllib. Intended for loopback (``httpx.ASGITransport`` / deployed base URL) — not in-process
``TestClient`` on the consumer alone.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, Optional

from startd8.deploy_harness.smoke import SmokeOutcome, _round_trip_ok
from startd8.openapi_contract.schema_resolve import (
    ResourceChoice,
    resolve_schema,
    select_crud_resource,
    synthesize_body,
)

__all__ = ["run_context_client_smoke", "create_dto_name"]


def create_dto_name(create_schema: Dict[str, Any], spec: Dict[str, Any]) -> Optional[str]:
    """Resolve the ``FooCreate`` components name for a POST body schema."""
    schema = resolve_schema(create_schema, spec)
    ref = schema.get("$ref") or create_schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        return ref.rsplit("/", 1)[-1]
    return None


def _entity_segment(path: str) -> str:
    return path.strip("/").split("/")[0]


def run_context_client_smoke(
    client: Any,
    spec: Dict[str, Any],
    *,
    tables_module: str = "app.tables",
) -> SmokeOutcome:
    """List+create round-trip through a generated context client. Never raises."""
    choice, skip = select_crud_resource(spec)
    if choice is None:
        return SmokeOutcome(status="skipped", reason=skip)

    entity_seg = _entity_segment(choice.path)
    list_fn = getattr(client, f"list_{entity_seg}", None)
    create_fn = getattr(client, f"create_{entity_seg}", None)
    if list_fn is None or create_fn is None:
        return SmokeOutcome(
            status="skipped",
            reason="skipped:no-client-methods",
            resource=choice.path,
        )

    dto_name = create_dto_name(choice.create_schema, spec)
    if not dto_name:
        return SmokeOutcome(
            status="skipped",
            reason="skipped:no-create-dto",
            resource=choice.path,
        )

    try:
        tables = importlib.import_module(tables_module)
        create_cls = getattr(tables, dto_name)
        body_dict = synthesize_body(choice.create_schema, spec)
        item = create_cls.model_validate(body_dict)
    except Exception:
        return SmokeOutcome(
            status="skipped",
            reason="skipped:body-synth-failed",
            resource=choice.path,
        )

    try:
        created = create_fn(item)
        listed = list_fn()
    except Exception:
        return SmokeOutcome(
            status="fail",
            reason="client-request-failed",
            resource=choice.path,
        )

    post_body = created.model_dump() if hasattr(created, "model_dump") else created
    get_body = [row.model_dump() if hasattr(row, "model_dump") else row for row in listed]
    if not _round_trip_ok(post_body, get_body):
        return SmokeOutcome(
            status="fail",
            reason="no-round-trip",
            resource=choice.path,
        )
    return SmokeOutcome(status="pass", resource=choice.path)
