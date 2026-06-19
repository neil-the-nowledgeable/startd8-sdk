"""Deterministic gRPC server skeleton generation from ``grpc.yaml`` + ``.proto`` (Tier-1 PR3)."""

from __future__ import annotations

from .drift import is_owned_proto_skeleton, proto_skeleton_in_sync
from .engine import render_grpc_skeletons
from .grpc_manifest import parse_grpc_manifest
from .models import GrpcServiceSpec, ProtoDocument, ProtoRpc, ProtoService
from .proto_parser import get_service, parse_proto
from .provider import ProtoSkeletonProvider

__all__ = [
    "GrpcServiceSpec",
    "ProtoDocument",
    "ProtoRpc",
    "ProtoService",
    "ProtoSkeletonProvider",
    "get_service",
    "is_owned_proto_skeleton",
    "parse_grpc_manifest",
    "parse_proto",
    "proto_skeleton_in_sync",
    "render_grpc_skeletons",
]
