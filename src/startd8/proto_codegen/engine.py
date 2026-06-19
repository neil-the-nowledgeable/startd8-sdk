"""Orchestrate proto skeleton rendering from ``grpc.yaml`` + ``.proto`` files."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .grpc_manifest import parse_grpc_manifest
from .models import GrpcServiceSpec
from .skeleton_go import default_go_out, render_go_skeleton
from .skeleton_python import default_python_out, render_python_skeleton

_RENDERERS = {
    "python": render_python_skeleton,
    "go": render_go_skeleton,
}
_DEFAULT_OUT = {
    "python": default_python_out,
    "go": default_go_out,
}


def _resolve_out(spec: GrpcServiceSpec) -> str:
    if spec.out:
        return spec.out
    return _DEFAULT_OUT[spec.language](spec.service)


def render_grpc_skeletons(manifest_text: str, project_root: Path) -> List[Tuple[str, str]]:
    """Return ``(relative_path, content)`` pairs for every declared gRPC service."""
    specs = parse_grpc_manifest(manifest_text)
    artifacts: List[Tuple[str, str]] = []
    for spec in specs:
        proto_path = project_root / spec.proto
        if not proto_path.is_file():
            raise ValueError(f"proto file not found: {proto_path}")
        proto_text = proto_path.read_text(encoding="utf-8")
        renderer = _RENDERERS[spec.language]
        resolved = GrpcServiceSpec(
            proto=spec.proto,
            service=spec.service,
            language=spec.language,
            out=_resolve_out(spec),
            stub_module=spec.stub_module,
        )
        content = renderer(
            spec=resolved,
            proto_text=proto_text,
            source_label=spec.proto.replace("\\", "/"),
        )
        artifacts.append((resolved.out, content))
    return artifacts
