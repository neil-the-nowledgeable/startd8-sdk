"""Cross-context smoke via generated consumer clients (OpenAPI Role 3 — M2 / FR-6).

Reuses :func:`startd8.openapi_contract.schema_resolve.select_crud_resource` and
:func:`synthesize_body` to pick an FK-free list+create collection, then executes the round-trip
through a generated ``clients/{id}_client.py`` (``list_*`` + ``create_*`` methods) instead of raw
urllib. Loopback uses in-process ``TestClient`` (generated tests); remote/deployed producers use
:func:`run_remote_producer_smoke` / :func:`run_outbound_context_smokes` against a live ``base_url``.
"""

from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from startd8.deploy_harness.smoke import SmokeOutcome, _round_trip_ok, run_smoke
from startd8.openapi_contract.schema_resolve import (
    resolve_schema,
    select_crud_resource,
    synthesize_body,
)

__all__ = [
    "OutboundSmokeResult",
    "context_base_url_env_key",
    "create_dto_name",
    "resolve_context_base_url",
    "run_context_client_smoke",
    "run_outbound_context_smokes",
    "run_remote_producer_smoke",
]


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


@dataclass(frozen=True)
class OutboundSmokeResult:
    """One outbound producer smoke outcome (deploy harness / CI)."""

    producer_id: str
    outcome: SmokeOutcome
    base_url: Optional[str] = None


def context_base_url_env_key(producer_id: str) -> str:
    """Env override for a producer base URL: ``STARTD8_CONTEXT_<ID>_BASE_URL``."""
    safe = re.sub(r"[^0-9A-Z_]", "_", producer_id.upper())
    return f"STARTD8_CONTEXT_{safe}_BASE_URL"


def resolve_context_base_url(
    ctx: Any,
    *,
    loopback_port: Optional[int] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Resolve live producer base URL: env wins, then manifest ``base_url``, then loopback for local."""
    env_map = env if env is not None else os.environ
    override = (env_map.get(context_base_url_env_key(ctx.id)) or "").strip()
    if override:
        return override.rstrip("/")
    manifest_url = (getattr(ctx, "base_url", None) or "").strip()
    if manifest_url:
        url = manifest_url.rstrip("/")
        if "{port}" in url and loopback_port is not None:
            url = url.replace("{port}", str(loopback_port))
        return url
    if getattr(ctx, "local", False) and loopback_port is not None:
        return f"http://127.0.0.1:{loopback_port}"
    return None


def _load_schema_text(project_root: Path) -> Optional[str]:
    schema_path = project_root / "prisma" / "schema.prisma"
    if not schema_path.is_file():
        return None
    try:
        return schema_path.read_text(encoding="utf-8")
    except OSError:
        return None


def _producer_spec_for_smoke(
    ctx: Any,
    project_root: Path,
    schema_text: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Pinned contract for remote producers; ``None`` ⇒ fetch live ``/openapi.json``."""
    if getattr(ctx, "local", False):
        return None
    from startd8.backend_codegen.context_manifest import (
        filter_spec_for_context,
        load_contract_spec,
    )

    raw = load_contract_spec(ctx.contract, project_root=project_root)
    if schema_text:
        return filter_spec_for_context(raw, schema_text, ctx)
    return raw


def run_remote_producer_smoke(
    base_url: str,
    *,
    spec: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0,
) -> SmokeOutcome:
    """Live list+create round-trip against a remote/deployed producer (urllib, FR-6 remote path)."""
    return run_smoke(base_url, spec=spec, timeout=timeout)


def run_outbound_context_smokes(
    project_root: Path | str,
    *,
    schema_text: Optional[str] = None,
    loopback_port: Optional[int] = None,
    timeout: float = 10.0,
    env: Optional[Mapping[str, str]] = None,
) -> Tuple[OutboundSmokeResult, ...]:
    """Run smoke for every ``contexts.yaml`` outbound entry with a resolvable base URL."""
    from startd8.backend_codegen.context_manifest import parse_contexts

    root = Path(project_root).resolve()
    contexts_path = root / "prisma" / "contexts.yaml"
    if not contexts_path.is_file():
        return ()
    try:
        contexts_text = contexts_path.read_text(encoding="utf-8")
    except OSError:
        return ()

    contexts = parse_contexts(contexts_text)
    if not contexts:
        return ()

    if schema_text is None:
        schema_text = _load_schema_text(root)

    results: list[OutboundSmokeResult] = []
    for ctx in contexts:
        base_url = resolve_context_base_url(
            ctx, loopback_port=loopback_port, env=env
        )
        if not base_url:
            results.append(
                OutboundSmokeResult(
                    ctx.id,
                    SmokeOutcome(status="skipped", reason="skipped:no-base-url"),
                    None,
                )
            )
            continue
        try:
            spec = _producer_spec_for_smoke(ctx, root, schema_text)
        except ValueError as exc:
            results.append(
                OutboundSmokeResult(
                    ctx.id,
                    SmokeOutcome(
                        status="skipped",
                        reason=f"skipped:contract-error:{exc}",
                    ),
                    base_url,
                )
            )
            continue
        outcome = run_remote_producer_smoke(base_url, spec=spec, timeout=timeout)
        results.append(OutboundSmokeResult(ctx.id, outcome, base_url))
    return tuple(results)


def aggregate_outbound_smoke(
    results: Sequence[OutboundSmokeResult],
) -> Tuple[str, Optional[str]]:
    """Roll up outbound results → (status, reason) for ladder recording."""
    if not results:
        return "skipped", "skipped:no-contexts"
    if any(r.outcome.status == "fail" for r in results):
        failed = [r.producer_id for r in results if r.outcome.status == "fail"]
        return "fail", f"outbound-fail:{','.join(failed)}"
    if all(r.outcome.status == "skipped" for r in results):
        return "skipped", results[0].outcome.reason or "skipped:no-targets"
    return "pass", None
