"""Python gRPC server skeleton renderer."""

from __future__ import annotations

import os
import re
from pathlib import Path

from ..frontend_codegen.schema_renderer import schema_sha256
from .headers import header_proto
from .models import GrpcServiceSpec, ProtoService
from .proto_parser import get_service, parse_proto

_KIND = "proto-skeleton-python"


def _stub_modules(spec: GrpcServiceSpec, proto_path: Path) -> tuple[str, str]:
    if spec.stub_module:
        base = spec.stub_module
        if base.endswith("_grpc"):
            return base.replace("_grpc", "_pb2"), base
        return f"{base}_pb2", f"{base}_pb2_grpc"
    stem = proto_path.stem
    return f"{stem}_pb2", f"{stem}_pb2_grpc"


def render_python_skeleton(
    *,
    spec: GrpcServiceSpec,
    proto_text: str,
    source_label: str,
) -> str:
    doc = parse_proto(proto_text)
    svc = get_service(doc, spec.service)
    stub_pb2, stub_grpc = _stub_modules(spec, Path(spec.proto))
    sha = schema_sha256(proto_text)
    header = header_proto(source_label, sha, _KIND, spec.service)

    methods: list[str] = []
    for rpc in svc.rpcs:
        methods.append(
            f"    def {rpc.name}(self, request, context):\n"
            f'        context.abort(grpc.StatusCode.UNIMPLEMENTED, "{rpc.name} not implemented")\n'
        )

    body = (
        '"""Generated gRPC server skeleton — implement RPC handlers, then remove UNIMPLEMENTED stubs."""\n'
        "from __future__ import annotations\n\n"
        "import os\n"
        "from concurrent import futures\n\n"
        "import grpc\n"
        f"import {stub_pb2}\n"
        f"import {stub_grpc}\n"
        "from grpc_health.v1 import health\n"
        "from grpc_health.v1 import health_pb2_grpc\n\n\n"
        f"class {svc.name}({stub_grpc}.{svc.name}Servicer):\n"
        + ("\n".join(methods) if methods else "    pass\n")
        + "\n\n\n"
        "def serve() -> None:\n"
        '    port = os.environ.get("PORT", "50051")\n'
        "    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))\n"
        f"    {stub_grpc}.add_{svc.name}Servicer_to_server({svc.name}(), server)\n"
        "    health_pb2_grpc.add_HealthServicer_to_server(health.HealthServicer(), server)\n"
        '    server.add_insecure_port(f"127.0.0.1:{port}")\n'
        "    server.start()\n"
        "    server.wait_for_termination()\n\n\n"
        'if __name__ == "__main__":\n'
        "    serve()\n"
    )
    return header + "\n\n" + body


def default_python_out(service_name: str) -> str:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", service_name).lower()
    return f"{snake}_server.py"
