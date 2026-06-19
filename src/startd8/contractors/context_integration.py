"""Prime Contractor integration guidance for OpenAPI Role 3 outbound clients (P2).

Threads the **real** generated ``clients/{id}_client.py`` + ``app/context_clients.py`` interfaces
into spec/draft prompts so bucket-3 integration passes use typed outbound HTTP instead of inventing
raw httpx or importing remote entities from ``app.tables``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..backend_codegen.context_integration_renderer import (
    CONTEXT_INTEGRATION_PATH,
    context_client_bindings,
    extract_client_methods,
)
from ..backend_codegen.context_manifest import parse_contexts

_HEADER_CONTRACT_SHA_RE = re.compile(r"#\s*contract-sha256:\s*([0-9a-f]{64})")
_HEADER_ENTITY_RE = re.compile(r"#\s*startd8-entity:\s*(\S+)")


@dataclass(frozen=True)
class ContextClientInterface:
    """On-disk outbound client interface for prompt grounding."""

    producer_id: str
    class_name: str
    module_path: str
    factory_name: str
    contract_sha: str
    methods: tuple[str, ...]


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except OSError:
        return None


def build_context_client_interfaces(
    *,
    project_root: str,
    schema_text: str,
    contexts_text: str,
) -> List[ContextClientInterface]:
    """Assemble real outbound client interfaces from generated artifacts on disk."""
    root = Path(project_root)
    bindings = context_client_bindings(schema_text, contexts_text, project_root=project_root)
    if not bindings:
        return []
    interfaces: List[ContextClientInterface] = []
    for binding in bindings:
        client_path = root / binding.module_path
        source = _read_text(client_path)
        if source is None:
            continue
        entity = _HEADER_ENTITY_RE.search(source or "")
        contract = _HEADER_CONTRACT_SHA_RE.search(source or "")
        interfaces.append(
            ContextClientInterface(
                producer_id=entity.group(1) if entity else binding.producer_id,
                class_name=binding.class_name,
                module_path=binding.module_path,
                factory_name=binding.factory_name,
                contract_sha=contract.group(1) if contract else binding.contract_sha,
                methods=tuple(extract_client_methods(source)),
            )
        )
    return interfaces


def render_context_integration(
    interfaces: List[ContextClientInterface],
    *,
    registry_path: str = CONTEXT_INTEGRATION_PATH,
) -> str:
    """Render prompt section for bucket-3 integration passes."""
    if not interfaces:
        return ""
    lines = [
        "## Outbound context clients (Role 3 — cross-process integration)",
        "",
        "These typed httpx clients are **already generated** and **$0-owned** (skip-hook kinds:",
        "`python-context-client`, `python-context-otel`, `python-context-integration`,",
        "`python-tests-cross-context`). For features that read/write remote bounded contexts:",
        "",
        f"- Prefer `from {registry_path.replace('/', '.').removesuffix('.py')} import get_<producer>_client`",
        "- Do **NOT** use `app.tables` / `session.exec(select(...))` for entities served by outbound producers",
        "- Do **NOT** invent raw httpx calls or new client classes — use the generated methods only",
        "- Stamp integration provenance in comments: `producer_id=<id>`, `contract_sha256=<hash>`",
        "",
        "| Producer | Factory | Client | contract-sha256 |",
        "|----------|---------|--------|-----------------|",
    ]
    for iface in sorted(interfaces, key=lambda i: i.producer_id):
        methods = ", ".join(iface.methods[:8])
        if len(iface.methods) > 8:
            methods += ", …"
        lines.append(
            f"| `{iface.producer_id}` | `{iface.factory_name}()` | "
            f"`{iface.class_name}` | `{iface.contract_sha[:12]}…` |"
        )
        if methods:
            lines.append(f"  - methods: {methods}")
    lines.append("")
    lines.append(
        "Example: `with get_catalog_client() as catalog: rows = catalog.list_note()`"
    )
    return "\n".join(lines)


def collect_context_integration_prompt(
    *,
    project_root: str,
    schema_text: Optional[str] = None,
    contexts_text: Optional[str] = None,
) -> str:
    """Build the integration prompt section when contexts.yaml is present."""
    root = Path(project_root)
    if contexts_text is None:
        contexts_path = root / "prisma" / "contexts.yaml"
        contexts_text = _read_text(contexts_path)
    if not contexts_text or not parse_contexts(contexts_text):
        return ""
    if schema_text is None:
        schema_path = root / "prisma" / "schema.prisma"
        schema_text = _read_text(schema_path) or ""
    if not schema_text.strip():
        return ""
    interfaces = build_context_client_interfaces(
        project_root=project_root,
        schema_text=schema_text,
        contexts_text=contexts_text,
    )
    return render_context_integration(interfaces)
