"""Go gRPC server skeleton renderer."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..frontend_codegen.schema_renderer import schema_sha256
from .headers import header_proto
from .models import GrpcServiceSpec
from .proto_parser import get_service, parse_proto

_KIND = "proto-skeleton-go"


def _go_pb_import(spec: GrpcServiceSpec, doc_go_package: Optional[str], proto_path: Path) -> str:
    if doc_go_package:
        return doc_go_package
    return f"example.com/{proto_path.stem}"


def _struct_name(service_name: str) -> str:
    if not service_name:
        return "serviceImpl"
    return service_name[0].lower() + service_name[1:]


def render_go_skeleton(
    *,
    spec: GrpcServiceSpec,
    proto_text: str,
    source_label: str,
) -> str:
    doc = parse_proto(proto_text)
    svc = get_service(doc, spec.service)
    sha = schema_sha256(proto_text)
    header = header_proto(source_label, sha, _KIND, spec.service)
    pb_import = _go_pb_import(spec, doc.go_package, Path(spec.proto))
    struct = _struct_name(svc.name)

    methods: list[str] = []
    for rpc in svc.rpcs:
        methods.append(
            f"func (s *{struct}) {rpc.name}(ctx context.Context, req *pb.{rpc.request}) "
            f"(*pb.{rpc.response}, error) {{\n"
            f'\treturn nil, status.Errorf(codes.Unimplemented, "{rpc.name} not implemented")\n'
            f"}}"
        )

    body = (
        "// Generated gRPC server skeleton — implement RPC handlers before production use.\n"
        "package main\n\n"
        "import (\n"
        '\t"context"\n'
        '\t"fmt"\n'
        '\t"net"\n'
        '\t"os"\n\n'
        f'\tpb "{pb_import}"\n'
        '\t"google.golang.org/grpc"\n'
        '\t"google.golang.org/grpc/codes"\n'
        '\t"google.golang.org/grpc/health"\n'
        '\thealthpb "google.golang.org/grpc/health/grpc_health_v1"\n'
        '\t"google.golang.org/grpc/status"\n'
        ")\n\n"
        f"type {struct} struct {{\n"
        f"\tpb.Unimplemented{svc.name}Server\n"
        "}\n\n"
        + ("\n\n".join(methods) + "\n\n" if methods else "")
        + "func main() {\n"
        '\tport := os.Getenv("PORT")\n'
        '\tif port == "" {\n'
        '\t\tport = "50051"\n'
        "\t}\n"
        '\tlis, err := net.Listen("tcp", fmt.Sprintf(":%s", port))\n'
        "\tif err != nil {\n"
        "\t\tpanic(err)\n"
        "\t}\n"
        "\tsrv := grpc.NewServer()\n"
        f"\tpb.Register{svc.name}Server(srv, &{struct}{{}})\n"
        "\thealthSrv := health.NewServer()\n"
        "\thealthpb.RegisterHealthServer(srv, healthSrv)\n"
        "\tif err := srv.Serve(lis); err != nil {\n"
        "\t\tpanic(err)\n"
        "\t}\n"
        "}\n"
    )
    return header + "\n\n" + body


def default_go_out(service_name: str) -> str:
    return "server.go"
