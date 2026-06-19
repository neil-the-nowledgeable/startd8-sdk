"""gRPC outbound context client stub (OpenAPI Role 3 — deferred D5 / ProtoStubProvider track).

Emits ``clients/{id}_grpc_client.py`` when ``protocol: grpc`` — thin channel wrapper over
protoc-generated ``*_pb2_grpc`` stubs (stubs themselves remain build-time / vendored).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from ..proto_codegen.proto_parser import get_service, parse_proto
from ._headers import header_context_client
from .context_manifest import (
    OutboundContext,
    load_proto_contract,
    parse_contexts,
    proto_contract_sha256,
)

CONTEXT_GRPC_CLIENT_KIND = "python-context-grpc-client"


def _stub_modules(proto_path: str) -> Tuple[str, str]:
    stem = Path(proto_path).stem
    return f"{stem}_pb2", f"{stem}_pb2_grpc"


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def render_context_grpc_client(
    schema_text: str,
    contexts_text: str,
    ctx: OutboundContext,
    source_file: str = "prisma/schema.prisma",
    *,
    project_root: Optional[str] = None,
) -> str:
    """Render ``clients/{id}_grpc_client.py`` for one gRPC outbound context."""
    if ctx.protocol != "grpc":
        return ""
    root = Path(project_root) if project_root else None
    proto_text = load_proto_contract(ctx.contract, project_root=root)
    doc = parse_proto(proto_text)
    svc = get_service(doc, ctx.grpc_service)
    stub_pb2, stub_grpc = _stub_modules(ctx.contract)
    sha = schema_sha256(schema_text)
    contexts_sha = schema_sha256(contexts_text)
    contract_sha = proto_contract_sha256(proto_text)
    class_name = "".join(
        p[:1].upper() + p[1:] for p in re.split(r"[^0-9a-zA-Z]+", ctx.id) if p
    ) + "GrpcClient"
    header = header_context_client(
        source_file,
        sha,
        contexts_sha,
        contract_sha,
        CONTEXT_GRPC_CLIENT_KIND,
        producer_id=ctx.id,
    )
    target_doc = ctx.base_url or "localhost:50051"
    if ctx.auth:
        auth_block = [
            f"    _AUTH_ENV = {ctx.auth.env!r}",
            "    def _metadata(self) -> tuple[tuple[str, str], ...]:",
            "        token = (os.environ.get(self._AUTH_ENV) or '').strip()",
            "        if not token:",
            "            return ()",
            "        return (('authorization', f'Bearer {token}'),)",
            "",
        ]
        rpc_meta = ", metadata=self._metadata()"
    else:
        auth_block = [
            "    def _metadata(self) -> tuple[tuple[str, str], ...]:",
            "        return ()",
            "",
        ]
        rpc_meta = ""
    rpc_methods: List[str] = []
    for rpc in svc.rpcs:
        rpc_methods += [
            f"    def {_snake(rpc.name)}(self, request, *, timeout: float | None = None):",
            f'        """gRPC {rpc.name}({rpc.request}) -> {rpc.response}"""',
            f"        return self._stub.{rpc.name}(request, timeout=timeout{rpc_meta})",
            "",
        ]
    body = (
        '"""Generated gRPC client for outbound context — requires protoc stubs on PYTHONPATH."""\n'
        "from __future__ import annotations\n\n"
        "import os\n\n"
        "import grpc\n"
        f"import {stub_pb2}  # noqa: F401 — request types\n"
        f"import {stub_grpc}\n\n\n"
        f"class {class_name}:\n"
        f'    """gRPC client for outbound producer {ctx.id!r} ({ctx.contract})."""\n'
        f"    # Default target (override in __init__): {target_doc}\n"
        "\n"
        "    def __init__(self, target: str, *, channel: grpc.Channel | None = None) -> None:\n"
        "        self._target = target\n"
        "        self._owns_channel = channel is None\n"
        "        self._channel = channel or grpc.insecure_channel(self._target)\n"
        f"        self._stub = {stub_grpc}.{svc.name}Stub(self._channel)\n"
        "\n"
        + "\n".join(auth_block)
        + "    def close(self) -> None:\n"
        "        if self._owns_channel:\n"
        "            self._channel.close()\n"
        "\n"
        f"    def __enter__(self) -> \"{class_name}\":\n"
        "        return self\n"
        "\n"
        "    def __exit__(self, *exc: object) -> None:\n"
        "        self.close()\n"
        "\n"
        + "\n".join(rpc_methods)
    )
    return header + "\n\n" + body


def render_context_grpc_clients(
    schema_text: str,
    contexts_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    project_root: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """All gRPC client pairs for ``protocol: grpc`` outbound entries."""
    pairs: List[Tuple[str, str]] = []
    for ctx in parse_contexts(contexts_text):
        if ctx.protocol != "grpc":
            continue
        text = render_context_grpc_client(
            schema_text,
            contexts_text,
            ctx,
            source_file,
            project_root=project_root,
        )
        if text:
            pairs.append((f"clients/{ctx.id}_grpc_client.py", text))
    return pairs
