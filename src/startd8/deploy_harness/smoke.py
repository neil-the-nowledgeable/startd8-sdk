"""Smoke-CRUD: synthesize a POST body from the live OpenAPI and round-trip it (FR-9/10).

Schema resolution and body synthesis live in :mod:`startd8.openapi_contract.schema_resolve`
(M4 extract) and are re-exported here for backward compatibility. This module owns the live
HTTP round-trip (:func:`run_smoke`) and grading outcomes.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from startd8.logging_config import get_logger
from startd8.openapi_contract.schema_resolve import (
    ResourceChoice,
    select_crud_resource,
    synthesize_body,
)

logger = get_logger("startd8.deploy_harness.smoke")

__all__ = [
    "SmokeOutcome",
    "ResourceChoice",
    "run_smoke",
    "select_crud_resource",
    "synthesize_body",
]


@dataclass
class SmokeOutcome:
    status: str  # pass | fail | skipped
    reason: Optional[str] = None
    resource: Optional[str] = None
    post_status: Optional[int] = None
    get_status: Optional[int] = None


def _http(
    method: str, url: str, *, body: Any = None, timeout: float = 10.0
) -> Tuple[Optional[int], Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method
    )  # noqa: S310 - loopback only
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _maybe_json(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _maybe_json(exc.read())
    except (urllib.error.URLError, OSError) as exc:
        return None, str(exc)


def _maybe_json(raw: Any) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def run_smoke(
    base_url: str, *, spec: Optional[Dict[str, Any]] = None, timeout: float = 10.0
) -> SmokeOutcome:
    """Derive and execute a create→list round-trip against the live server. Never raises."""
    if spec is None:
        status, spec = _http(
            "GET", base_url.rstrip("/") + "/openapi.json", timeout=timeout
        )
        if status is None or not isinstance(spec, dict):
            return SmokeOutcome(status="skipped", reason="skipped:no-openapi")

    choice, skip = select_crud_resource(spec)
    if choice is None:
        return SmokeOutcome(status="skipped", reason=skip)

    try:
        body = synthesize_body(choice.create_schema, spec)
    except Exception as exc:
        logger.debug("body synthesis failed for %s: %s", choice.path, exc)
        return SmokeOutcome(
            status="skipped", reason="skipped:body-synth-failed", resource=choice.path
        )

    url = base_url.rstrip("/") + choice.path
    post_status, post_body = _http("POST", url, body=body, timeout=timeout)
    if post_status is None:
        return SmokeOutcome(
            status="fail", reason="post-no-response", resource=choice.path
        )
    if not (200 <= post_status < 300):
        return SmokeOutcome(
            status="fail",
            reason=f"post-{post_status}",
            resource=choice.path,
            post_status=post_status,
        )

    get_status, get_body = _http("GET", url, timeout=timeout)
    if get_status is None or not (200 <= get_status < 300):
        return SmokeOutcome(
            status="fail",
            reason=f"get-{get_status}",
            resource=choice.path,
            post_status=post_status,
            get_status=get_status,
        )

    if not _round_trip_ok(post_body, get_body):
        return SmokeOutcome(
            status="fail",
            reason="no-round-trip",
            resource=choice.path,
            post_status=post_status,
            get_status=get_status,
        )
    return SmokeOutcome(
        status="pass",
        resource=choice.path,
        post_status=post_status,
        get_status=get_status,
    )


def _round_trip_ok(post_body: Any, get_body: Any) -> bool:
    """The created row should be observable in the subsequent list."""
    items = (
        get_body
        if isinstance(get_body, list)
        else (get_body.get("items") if isinstance(get_body, dict) else None)
    )
    if items is None:
        return False
    if not items:
        return False
    created_id = post_body.get("id") if isinstance(post_body, dict) else None
    if created_id is None:
        return True
    return any(isinstance(it, dict) and it.get("id") == created_id for it in items)
