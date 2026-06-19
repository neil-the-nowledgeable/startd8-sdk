"""Outbound context client registry (OpenAPI Role 3 — P2 bucket-3 integration seam).

Emits ``app/context_clients.py`` — factory accessors for generated ``clients/{id}_client.py``
artifacts. Integration passes import from here instead of inventing raw httpx or reaching into
``app.tables`` for entities owned by remote producer contexts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from ..frontend_codegen.schema_renderer import schema_sha256
from ._headers import header_context_integration
from .context_client_renderer import _class_name
from .context_manifest import (
    OutboundContext,
    contract_sha256,
    filter_spec_for_client,
    parse_contexts,
)

CONTEXT_INTEGRATION_KIND = "python-context-integration"
CONTEXT_INTEGRATION_PATH = "app/context_clients.py"


@dataclass(frozen=True)
class ContextClientBinding:
    """One outbound producer wired for integration."""

    producer_id: str
    class_name: str
    module_path: str
    contract_sha: str
    factory_name: str
    default_base_url: str


def _contract_sha_for_ctx(
    schema_text: str,
    contexts_text: str,
    ctx: OutboundContext,
    *,
    project_root: Optional[str] = None,
) -> str:
    from .context_client_renderer import _resolve_producer_spec

    raw = _resolve_producer_spec(schema_text, ctx, project_root=project_root)
    filtered = filter_spec_for_client(raw, schema_text, routes=ctx.routes)
    return contract_sha256(filtered)


def context_client_bindings(
    schema_text: str,
    contexts_text: str,
    *,
    project_root: Optional[str] = None,
) -> List[ContextClientBinding]:
    """Resolve integration bindings for every outbound context."""
    bindings: List[ContextClientBinding] = []
    for ctx in parse_contexts(contexts_text):
        class_name = _class_name(ctx.id)
        factory = f"get_{ctx.id}_client"
        bindings.append(
            ContextClientBinding(
                producer_id=ctx.id,
                class_name=class_name,
                module_path=f"clients/{ctx.id}_client.py",
                contract_sha=_contract_sha_for_ctx(
                    schema_text, contexts_text, ctx, project_root=project_root
                ),
                factory_name=factory,
                default_base_url=(ctx.base_url or "").strip() or "http://127.0.0.1:8001",
            )
        )
    return bindings


def render_context_clients_module(
    schema_text: str,
    contexts_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    project_root: Optional[str] = None,
) -> str:
    """Render ``app/context_clients.py`` registry with factory accessors."""
    bindings = context_client_bindings(
        schema_text, contexts_text, project_root=project_root
    )
    if not bindings:
        return ""
    sha = schema_sha256(schema_text)
    contexts_sha = schema_sha256(contexts_text)
    header = header_context_integration(
        source_file, sha, contexts_sha, CONTEXT_INTEGRATION_KIND
    )
    imports = ["from __future__ import annotations", "", "import os", "import re", ""]
    for b in bindings:
        mod = b.module_path.replace("/", ".").removesuffix(".py")
        imports.append(f"from {mod} import {b.class_name}")
    lines = imports + [
        "",
        "",
        '"""Outbound context client registry (Role 3 P2 integration seam).',
        "",
        "For entities owned by remote producer contexts (prisma/contexts.yaml), use the",
        "typed factories below — NOT direct SQLModel/session access via app.tables.",
        "Integration glue may compose these clients; provenance constants are embedded per producer.",
        '"""',
        "",
        "",
        "def _context_env_key(producer_id: str) -> str:",
        '    """Env override: STARTD8_CONTEXT_<ID>_BASE_URL."""',
        '    safe = re.sub(r"[^0-9A-Z_]", "_", producer_id.upper())',
        '    return f"STARTD8_CONTEXT_{safe}_BASE_URL"',
        "",
    ]
    for b in bindings:
        lines += [
            f"_PRODUCER_{b.producer_id.upper()}_ID = {b.producer_id!r}",
            f"_CONTRACT_SHA_{b.producer_id.upper()} = {b.contract_sha!r}",
            f"_DEFAULT_BASE_{b.producer_id.upper()} = {b.default_base_url!r}",
            "",
            f"def {b.factory_name}() -> {b.class_name}:",
            f'    """Factory for outbound producer {b.producer_id!r} ({b.module_path})."""',
            f"    override = (os.environ.get(_context_env_key(_PRODUCER_{b.producer_id.upper()}_ID)) or '').strip()",
            f"    base = override or _DEFAULT_BASE_{b.producer_id.upper()}",
            f"    return {b.class_name}(base.rstrip('/'))",
            "",
        ]
    return header + "\n\n" + "\n".join(lines).rstrip() + "\n"


def extract_client_methods(client_source: str) -> List[str]:
    """Best-effort public method names from a generated context client."""
    return re.findall(r"^\s+def (\w+)\(self", client_source, re.MULTILINE)
