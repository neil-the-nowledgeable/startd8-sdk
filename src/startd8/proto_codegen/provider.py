"""Deterministic-file provider for gRPC server skeletons."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from .drift import is_owned_proto_skeleton, proto_skeleton_in_sync


class ProtoSkeletonProvider:
    """Recognizes owned Python/Go gRPC skeletons declared in ``grpc.yaml``."""

    name = "proto-skeleton"

    def owns(self, path: Path, content: str) -> bool:
        return is_owned_proto_skeleton(content)

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        manifest_text = self._read_manifest(context)
        if not manifest_text:
            return False
        rel = self._relative_path(path, context)
        if rel is None:
            return False
        return proto_skeleton_in_sync(manifest_text, Path(context.project_root), rel, content)

    @staticmethod
    def _read_manifest(context: ProviderContext) -> Optional[str]:
        root = Path(context.project_root)
        for anchor in context.source_anchors:
            if not str(anchor).endswith("grpc.yaml"):
                continue
            ap = Path(anchor) if Path(anchor).is_absolute() else root / anchor
            if ap.is_file():
                try:
                    return ap.read_text(encoding="utf-8")
                except OSError:
                    return None
        for conventional in (root / "grpc.yaml", root / "prisma" / "grpc.yaml"):
            if conventional.is_file():
                try:
                    return conventional.read_text(encoding="utf-8")
                except OSError:
                    return None
        return None

    @staticmethod
    def _relative_path(path: Path, context: ProviderContext) -> Optional[str]:
        root = Path(context.project_root)
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.name
